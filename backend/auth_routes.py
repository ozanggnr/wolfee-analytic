"""
Authentication Routes for Wolfee Analytics
Endpoints:
- POST /api/auth/register
- GET  /api/auth/verify-email
- POST /api/auth/resend-verification
- POST /api/auth/login
- POST /api/auth/logout
- GET  /api/auth/me
- POST /api/auth/forgot-password
- POST /api/auth/reset-password
- GET  /api/auth/csrf
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, UserSession, AuthToken, SecurityLog
from auth_utils import (
    hash_password, verify_password, validate_password_policy,
    calculate_lockout_cooldown, is_account_locked, verify_captcha,
    generate_secure_token, hash_token,
    send_verification_email, send_password_reset_email
)
from security_middleware import (
    get_client_ip, create_user_session, set_auth_cookies, clear_auth_cookies,
    get_current_user, SESSION_COOKIE_NAME, CSRF_COOKIE_NAME
)

logger = logging.getLogger("auth_routes")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_token: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_token: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    captcha_token: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    email: str
    email_verified: bool
    created_at: Optional[str] = None


# Generic anti-enumeration messages
GENERIC_LOGIN_ERROR = "Invalid email or password."
GENERIC_REGISTER_SUCCESS = (
    "If this email is eligible for an account, a verification email has been sent. "
    "Please check your inbox."
)
GENERIC_FORGOT_SUCCESS = (
    "If that email address exists in our system, password reset instructions have been sent."
)


# ============================================================
# REGISTER ENDPOINT
# ============================================================
@router.post("/register", status_code=status.HTTP_200_OK)
async def register_user(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user account:
    - Enforces server-side password policy (min 10 chars, blocklist)
    - Validates CAPTCHA
    - Hashes password using bcrypt (cost factor 12)
    - Requires email verification before login
    - Returns generic anti-enumeration response
    """
    client_ip = get_client_ip(request)
    email_normalized = req.email.lower().strip()

    # 1. Enforce password policy
    is_valid_pw, pw_error = validate_password_policy(req.password)
    if not is_valid_pw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_error)

    # 2. Enforce CAPTCHA on registration
    captcha_valid = await verify_captcha(req.captcha_token, remote_ip=client_ip)
    if not captcha_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA verification failed. Please complete the CAPTCHA."
        )

    # 3. Check for existing user (Anti-enumeration: don't disclose whether email exists)
    result = await db.execute(select(User).where(User.email == email_normalized))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # Anti-enumeration: log silently and return uniform generic success message
        logger.info(f"Registration attempted for existing email: {email_normalized} from {client_ip}")
        return {"message": GENERIC_REGISTER_SUCCESS}

    # 4. Hash password with bcrypt cost factor 12
    pw_hash = hash_password(req.password)

    # 5. Create user (unverified by default)
    new_user = User(
        email=email_normalized,
        password_hash=pw_hash,
        email_verified=False,
        failed_login_count=0
    )
    db.add(new_user)
    await db.flush()  # Populates new_user.id

    # 6. Generate email verification token (24 hour expiration)
    raw_token = generate_secure_token()
    token_h = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)

    auth_tok = AuthToken(
        user_id=new_user.id,
        token_hash=token_h,
        token_type="verify_email",
        created_at=now,
        expires_at=expires_at,
        is_used=False
    )
    db.add(auth_tok)

    # 7. Audit log
    sec_log = SecurityLog(
        event_type="REGISTER_SUCCESS",
        email=email_normalized,
        ip_address=client_ip,
        user_agent=request.headers.get("User-Agent", "")[:250],
        details="Account created, verification email dispatched"
    )
    db.add(sec_log)
    await db.commit()

    # 8. Send verification email
    base_url = str(request.base_url)
    await send_verification_email(email_normalized, raw_token, base_url=base_url)

    return {"message": GENERIC_REGISTER_SUCCESS}


# ============================================================
# EMAIL VERIFICATION ENDPOINTS
# ============================================================
@router.get("/verify-email")
async def verify_email(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify account via token link:
    - Verifies token hash, expiration, and unused status
    - Marks user account email_verified = True
    - Redirects or returns verification success
    """
    client_ip = get_client_ip(request)
    tok_hash = hash_token(token.strip())
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == tok_hash,
            AuthToken.token_type == "verify_email",
            AuthToken.is_used == False,
            AuthToken.expires_at > now
        )
    )
    tok_record = result.scalar_one_or_none()

    if not tok_record:
        # Invalid or expired token
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head><title>Verification Failed</title><meta name="viewport" content="width=device-width, initial-scale=1"></head>
            <body style="background:#0c0c0c;color:#e8f0fe;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="background:#16161e;padding:2.5rem;border-radius:18px;border:1px solid #ff4f6e;max-width:440px;text-align:center;">
                    <h2 style="color:#ff4f6e;margin-top:0;">Verification Link Expired or Invalid</h2>
                    <p style="color:#a997ce;">This link is no longer valid. Please request a new verification link from the login page.</p>
                    <a href="/index.html" style="display:inline-block;margin-top:1.5rem;background:#c86fff;color:#fff;padding:0.75rem 1.5rem;border-radius:12px;text-decoration:none;font-weight:600;">Return to Wolfee</a>
                </div>
            </body>
            </html>
            """,
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # Fetch user and activate
    user_result = await db.execute(select(User).where(User.id == tok_record.user_id))
    user = user_result.scalar_one_or_none()

    if user:
        user.email_verified = True
        tok_record.is_used = True

        sec_log = SecurityLog(
            event_type="EMAIL_VERIFIED",
            email=user.email,
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", "")[:250],
            details="Email successfully verified"
        )
        db.add(sec_log)
        await db.commit()

    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html>
        <head><title>Email Verified</title><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="background:#0c0c0c;color:#e8f0fe;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="background:#16161e;padding:2.5rem;border-radius:18px;border:1px solid #10f5a8;max-width:440px;text-align:center;">
                <h2 style="color:#10f5a8;margin-top:0;">Email Verified!</h2>
                <p style="color:#a997ce;">Your Wolfee Analytics account is now verified and active. You may now log in to sync your portfolio.</p>
                <a href="/index.html?verified=true" style="display:inline-block;margin-top:1.5rem;background:#10f5a8;color:#0c0c0c;padding:0.75rem 1.5rem;border-radius:12px;text-decoration:none;font-weight:700;">Proceed to Login</a>
            </div>
        </body>
        </html>
        """
    )


@router.post("/resend-verification")
async def resend_verification(
    req: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Resend email verification link with anti-enumeration protection."""
    client_ip = get_client_ip(request)
    email_normalized = req.email.lower().strip()

    result = await db.execute(select(User).where(User.email == email_normalized))
    user = result.scalar_one_or_none()

    if user and not user.email_verified:
        raw_token = generate_secure_token()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24)

        auth_tok = AuthToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            token_type="verify_email",
            created_at=now,
            expires_at=expires_at,
            is_used=False
        )
        db.add(auth_tok)
        await db.commit()

        base_url = str(request.base_url)
        await send_verification_email(email_normalized, raw_token, base_url=base_url)

    return {
        "message": (
            "If an unverified account exists with that email address, a new verification link has been sent."
        )
    }


# ============================================================
# LOGIN ENDPOINT
# ============================================================
@router.post("/login")
async def login_user(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    User login with:
    - Per-account lockout with exponential backoff (1m, 5m, 15m)
    - CAPTCHA enforcement on 3+ failed attempts
    - Password validation using bcrypt
    - Mandatory email verification check
    - Audit logging of failed/successful logins with IP and timestamp
    - HttpOnly, Secure, SameSite=Strict session cookie
    - Generic anti-enumeration error messages
    """
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")[:250]
    email_normalized = req.email.lower().strip()

    # 1. Fetch user record
    result = await db.execute(select(User).where(User.email == email_normalized))
    user = result.scalar_one_or_none()

    # 2. Check if account is locked
    if user:
        locked, remaining_seconds = is_account_locked(user.locked_until)
        if locked:
            # Log lockout attempt
            sec_log = SecurityLog(
                event_type="LOCKED_ACCOUNT_ATTEMPT",
                email=email_normalized,
                ip_address=client_ip,
                user_agent=user_agent,
                details=f"Locked account attempted login. {remaining_seconds}s cooldown remaining"
            )
            db.add(sec_log)
            await db.commit()

            # Generic error message to prevent enumeration, with safe cooldown hint
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Account temporarily locked due to consecutive failed attempts. Please retry in {remaining_seconds} seconds."
            )

        # 3. Check CAPTCHA requirement (triggered when failed_login_count >= 3)
        if user.failed_login_count >= 3:
            captcha_ok = await verify_captcha(req.captcha_token, remote_ip=client_ip)
            if not captcha_ok:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Security verification required. Please complete the CAPTCHA.",
                    headers={"X-Captcha-Required": "true"}
                )

    # 4. Verify password
    password_correct = False
    if user:
        password_correct = verify_password(req.password, user.password_hash)

    # 5. Handle failed authentication
    if not user or not password_correct:
        captcha_required = False
        if user:
            user.failed_login_count += 1

            # Apply exponential backoff lockout cooldown
            cooldown = calculate_lockout_cooldown(user.failed_login_count)
            if cooldown:
                user.locked_until = datetime.now(timezone.utc) + cooldown
                logger.warning(
                    f"Account {email_normalized} locked for {cooldown.total_seconds()}s "
                    f"after {user.failed_login_count} failed attempts."
                )

            captcha_required = user.failed_login_count >= 3

            # Record failed login attempt in security logs with IP and timestamp
            sec_log = SecurityLog(
                event_type="LOGIN_FAILED",
                email=email_normalized,
                ip_address=client_ip,
                user_agent=user_agent,
                details=f"Failed password attempt #{user.failed_login_count}"
            )
            db.add(sec_log)
            await db.commit()
        else:
            # Record failed attempt for non-existent user (anti-enumeration log)
            sec_log = SecurityLog(
                event_type="LOGIN_FAILED_UNKNOWN_USER",
                email=email_normalized,
                ip_address=client_ip,
                user_agent=user_agent,
                details="Attempt with unregistered email"
            )
            db.add(sec_log)
            await db.commit()

        # Always return generic message (anti-enumeration)
        headers = {}
        if captcha_required:
            headers["X-Captcha-Required"] = "true"

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_LOGIN_ERROR,
            headers=headers
        )

    # 6. Check Email Verification
    if not user.email_verified:
        sec_log = SecurityLog(
            event_type="LOGIN_UNVERIFIED_EMAIL",
            email=email_normalized,
            ip_address=client_ip,
            user_agent=user_agent,
            details="Login blocked: email not verified"
        )
        db.add(sec_log)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not verified. Please check your email inbox to verify your account before logging in."
        )

    # 7. Successful Authentication: Reset lockout counters
    user.failed_login_count = 0
    user.locked_until = None

    # 8. Create server-side session in database
    session_record, session_id = await create_user_session(
        db=db,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent
    )

    # 9. Set HttpOnly, Secure, SameSite=Strict cookies
    set_auth_cookies(response=response, session_id=session_id, request=request)

    # 10. Audit log
    sec_log = SecurityLog(
        event_type="LOGIN_SUCCESS",
        email=email_normalized,
        ip_address=client_ip,
        user_agent=user_agent,
        details="User successfully authenticated"
    )
    db.add(sec_log)
    await db.commit()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "email_verified": user.email_verified
        },
        "message": "Login successful"
    }


# ============================================================
# LOGOUT ENDPOINT
# ============================================================
@router.post("/logout")
async def logout_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Revoke session on server and clear cookies."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        await db.execute(delete(UserSession).where(UserSession.id == session_id))
        await db.commit()

    clear_auth_cookies(response=response, request=request)
    return {"message": "Logged out successfully"}


# ============================================================
# CURRENT USER PROFILE ENDPOINT
# ============================================================
@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(user: User = Depends(get_current_user)):
    """Return profile data for the active authenticated session."""
    return UserResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        created_at=user.created_at.isoformat() if user.created_at else None
    )


# ============================================================
# FORGOT & RESET PASSWORD ENDPOINTS
# ============================================================
@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Request password reset link.
    Returns generic anti-enumeration response.
    """
    client_ip = get_client_ip(request)
    email_normalized = req.email.lower().strip()

    result = await db.execute(select(User).where(User.email == email_normalized))
    user = result.scalar_one_or_none()

    if user:
        raw_token = generate_secure_token()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=1)  # 1 hour expiration for reset

        auth_tok = AuthToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            token_type="password_reset",
            created_at=now,
            expires_at=expires_at,
            is_used=False
        )
        db.add(auth_tok)

        sec_log = SecurityLog(
            event_type="PASSWORD_RESET_REQUEST",
            email=email_normalized,
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", "")[:250],
            details="Password reset token issued"
        )
        db.add(sec_log)
        await db.commit()

        base_url = str(request.base_url)
        await send_password_reset_email(email_normalized, raw_token, base_url=base_url)
    else:
        logger.info(f"Password reset requested for unregistered email: {email_normalized} from {client_ip}")

    # Anti-enumeration generic message
    return {"message": GENERIC_FORGOT_SUCCESS}


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Reset password using valid reset token:
    - Enforces password policy
    - Hashes with bcrypt cost factor 12
    - Invalidates all existing sessions for security
    """
    client_ip = get_client_ip(request)
    is_valid_pw, pw_error = validate_password_policy(req.new_password)
    if not is_valid_pw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_error)

    tok_hash = hash_token(req.token.strip())
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == tok_hash,
            AuthToken.token_type == "password_reset",
            AuthToken.is_used == False,
            AuthToken.expires_at > now
        )
    )
    tok_record = result.scalar_one_or_none()

    if not tok_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token is invalid or has expired."
        )

    user_result = await db.execute(select(User).where(User.id == tok_record.user_id))
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account not found.")

    # Update password
    user.password_hash = hash_password(req.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    tok_record.is_used = True

    # Invalidate all active sessions for this user on password reset
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))

    sec_log = SecurityLog(
        event_type="PASSWORD_RESET_SUCCESS",
        email=user.email,
        ip_address=client_ip,
        user_agent=request.headers.get("User-Agent", "")[:250],
        details="Password successfully reset, active sessions revoked"
    )
    db.add(sec_log)
    await db.commit()

    return {"message": "Your password has been successfully reset. You may now log in."}


# ============================================================
# CSRF TOKEN ENDPOINT
# ============================================================
@router.get("/csrf")
async def get_csrf_token(request: Request, response: Response):
    """
    Fetch or initialize CSRF token for the frontend client.
    """
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not csrf_token:
        import secrets
        csrf_token = secrets.token_hex(32)
        is_secure = request.url.scheme == "https"
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=csrf_token,
            max_age=60 * 60 * 24 * 30,
            path="/",
            httponly=False,
            secure=is_secure,
            samesite="strict"
        )
    return {"csrf_token": csrf_token}
