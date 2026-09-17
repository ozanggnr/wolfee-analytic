"""
Security & Authentication Utilities for Wolfee Analytics
- Password hashing with bcrypt (cost factor 12) with library built-in salting
- Password policy enforcement (min 10 chars, common passwords blocklist)
- Per-account lockout with exponential backoff (1m, 5m, 15m)
- CAPTCHA validation (hCaptcha, reCAPTCHA, Cloudflare Turnstile with dev bypass)
- Cryptographic token generation and SHA-256 hashing
- Email notification handling (SMTP or local development fallback)
"""

import os
import secrets
import hashlib
import logging
import smtplib
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from typing import Optional, Tuple, Any
import bcrypt
import httpx
from starlette.requests import Request

logger = logging.getLogger("auth_security")

# ============================================================
# PASSWORD HASHING (bcrypt cost factor 12)
# ============================================================
BCRYPT_ROUNDS = 12

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt with cost factor 12.
    Uses bcrypt's built-in salt generation (never manual salting).
    """
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed_bytes = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify a raw password against the stored bcrypt hash in constant time.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


# ============================================================
# PASSWORD POLICY & COMMON PASSWORDS BLOCKLIST
# ============================================================
MIN_PASSWORD_LENGTH = 10

# Blocklist of most common, weak, and predictable passwords
COMMON_PASSWORDS_BLOCKLIST = {
    "1234567890",
    "12345678901",
    "123456789012",
    "password123",
    "password1234",
    "password12345",
    "admin12345",
    "administrator",
    "qwerty1234",
    "qwertyuiop",
    "qwertyuiop12",
    "letmein123",
    "letmein1234",
    "iloveyou12",
    "iloveyou123",
    "welcome123",
    "welcome1234",
    "monkey1234",
    "dragon1234",
    "supersecret",
    "secret1234",
    "changeme123",
    "trustnoone1",
    "football123",
    "baseball123",
    "sunshine123",
    "princess123",
    "shadow1234",
    "master1234",
    "hunter1234",
    "pass123456",
    "abc1234567",
    "0123456789",
    "abcdefghij",
    "testing123",
    "testpassword",
    "wolfee1234",
    "wolfeeanalytic",
}

def validate_password_policy(password: str) -> Tuple[bool, Optional[str]]:
    """
    Enforce server-side password policy:
    1. Minimum 10 characters.
    2. Not in common passwords blocklist.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."

    lower_pw = password.lower().strip()
    if lower_pw in COMMON_PASSWORDS_BLOCKLIST:
        return False, "This password is too common and easily guessed. Please choose a stronger password."

    # Check for simple repetitions (e.g. 'aaaaaaaaaa')
    if len(set(lower_pw)) <= 2:
        return False, "Password contains too many repeated characters. Please choose a stronger password."

    return True, None


# ============================================================
# ACCOUNT LOCKOUT & EXPONENTIAL BACKOFF
# ============================================================
def calculate_lockout_cooldown(failed_count: int) -> Optional[timedelta]:
    """
    Exponential backoff lockout after 5 consecutive failed login attempts:
    - Attempt 5: 1 minute cooldown
    - Attempt 6: 5 minutes cooldown
    - Attempt 7+: 15 minutes cooldown
    Returns None if failed_count < 5.
    """
    if failed_count < 5:
        return None
    elif failed_count == 5:
        return timedelta(minutes=1)
    elif failed_count == 6:
        return timedelta(minutes=5)
    else:
        return timedelta(minutes=15)


def is_account_locked(locked_until: Optional[datetime]) -> Tuple[bool, Optional[int]]:
    """
    Check if account is currently locked.
    Returns (is_locked, remaining_seconds).
    """
    if not locked_until:
        return False, None

    now = datetime.now(timezone.utc)
    # Ensure locked_until is timezone-aware
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)

    if locked_until > now:
        remaining = int((locked_until - now).total_seconds())
        return True, max(remaining, 1)

    return False, None


# ============================================================
# CAPTCHA VERIFICATION (hCaptcha / reCAPTCHA / Cloudflare Turnstile)
# ============================================================
CAPTCHA_SECRET_KEY = os.getenv("CAPTCHA_SECRET_KEY", "")
CAPTCHA_SITE_KEY = os.getenv("CAPTCHA_SITE_KEY", "")
CAPTCHA_VERIFY_URL = os.getenv("CAPTCHA_VERIFY_URL", "https://hcaptcha.com/siteverify")

async def verify_captcha(token: Optional[str], remote_ip: Optional[str] = None) -> bool:
    """
    Verify CAPTCHA token.
    If CAPTCHA_SECRET_KEY is not configured (e.g. in local development / testing),
    it allows testing via a bypass token 'dev-captcha-pass' or when running in dev mode.
    """
    # If no secret key is set, log a warning and accept in dev mode
    if not CAPTCHA_SECRET_KEY:
        if token in ("dev-captcha-pass", "test-token", "bypass", None, ""):
            logger.info("Dev mode CAPTCHA bypass used (no CAPTCHA_SECRET_KEY set)")
            return True
        return True

    if not token:
        return False

    # Dev token bypass when explicitly enabled
    if os.getenv("ALLOW_DEV_CAPTCHA_BYPASS", "false").lower() == "true" and token == "dev-captcha-pass":
        return True

    try:
        data = {"secret": CAPTCHA_SECRET_KEY, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(CAPTCHA_VERIFY_URL, data=data)
            resp.raise_for_status()
            res_json = resp.json()
            return bool(res_json.get("success", False))
    except Exception as e:
        logger.error(f"CAPTCHA verification failed with error: {e}")
        return False


# ============================================================
# TOKEN GENERATION & HASHING
# ============================================================
def generate_secure_token() -> str:
    """Generate a high-entropy URL-safe cryptographic token (32 bytes = 256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """
    Hash token with SHA-256 for safe database storage.
    If the database is leaked, raw tokens cannot be used by an attacker.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ============================================================
# EMAIL NOTIFICATIONS (Verification & Password Reset)
# Multi-provider support: Resend API, SendGrid API, and SMTP Relay
# ============================================================

def get_app_base_url(request: Optional[Request] = None) -> str:
    """Resolve public base URL from APP_BASE_URL, RAILWAY_PUBLIC_DOMAIN, or request headers."""
    base_url = os.getenv("APP_BASE_URL")
    if base_url:
        return base_url.rstrip("/")
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        return f"https://{railway_domain.rstrip('/')}"
    if request:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
        return f"{proto}://{host}".rstrip("/")
    return "http://localhost:8000"


def is_email_service_configured() -> bool:
    """Check if any live email dispatch service is configured."""
    if os.getenv("RESEND_API_KEY") or os.getenv("SENDGRID_API_KEY"):
        return True
    if os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"):
        return True
    return False


def create_email_html(title: str, preheader: str, button_label: str, button_url: str, subtext: str) -> str:
    """Generate dark fintech branded HTML email matching Wolfee Analytics aesthetic."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#0c0c0c;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#e8f0fe;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0c0c0c;padding:40px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:520px;background:#140c26;border:1px solid rgba(200,111,255,0.25);border-radius:24px;padding:36px 32px;box-shadow:0 16px 40px rgba(0,0,0,0.7);">
          <!-- Logo -->
          <tr>
            <td align="center" style="padding-bottom:20px;">
              <span style="font-size:24px;font-weight:800;letter-spacing:-0.5px;color:#ffffff;">
                Wolfee<span style="color:#c86fff;">.</span>
              </span>
              <div style="font-size:11px;font-weight:700;letter-spacing:1px;color:#c86fff;text-transform:uppercase;margin-top:4px;">Market Intelligence</div>
            </td>
          </tr>
          <!-- Title -->
          <tr>
            <td style="padding-bottom:12px;text-align:center;">
              <h1 style="margin:0;font-size:22px;font-weight:700;color:#e8f0fe;">{title}</h1>
            </td>
          </tr>
          <!-- Body Text -->
          <tr>
            <td style="padding-bottom:28px;text-align:center;color:#a997ce;font-size:15px;line-height:1.6;">
              {preheader}
            </td>
          </tr>
          <!-- Action Button -->
          <tr>
            <td align="center" style="padding-bottom:28px;">
              <a href="{button_url}" target="_blank" style="display:inline-block;padding:14px 32px;background:linear-gradient(123deg,#B600A8,#7621B0,#BE4C00);color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;border-radius:50px;box-shadow:0 4px 16px rgba(182,0,168,0.4);">
                {button_label}
              </a>
            </td>
          </tr>
          <!-- Subtext / Raw Link -->
          <tr>
            <td style="padding-top:16px;border-top:1px solid rgba(200,111,255,0.12);color:#7a6d96;font-size:12px;line-height:1.5;text-align:center;">
              {subtext}<br><br>
              Direct Link: <a href="{button_url}" style="color:#c86fff;word-break:break-all;text-decoration:underline;">{button_url}</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def dispatch_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    fallback_link: str = "",
    action_name: str = "Email Action"
) -> bool:
    """
    Unified email dispatcher:
    1. Resend API (RESEND_API_KEY) - instant HTTPS setup, no SMTP ports needed
    2. SendGrid API (SENDGRID_API_KEY)
    3. SMTP Relay (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD) - supporting Port 465 (SSL) & 587 (STARTTLS)
    4. Console logger fallback with actionable Railway instructions
    """
    email_from = os.getenv("EMAIL_FROM") or "Wolfee Analytics <onboarding@resend.dev>"

    # 1. Resend HTTP API (Recommended)
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        try:
            headers = {
                "Authorization": f"Bearer {resend_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "from": email_from,
                "to": [to_email],
                "subject": subject,
                "text": text_body,
                "html": html_body
            }
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info(f"Email '{subject}' successfully sent to {to_email} via Resend API.")
                    return True
                else:
                    logger.error(f"Resend API error ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send email via Resend API to {to_email}: {e}")

    # 2. SendGrid HTTP API
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    if sendgrid_key:
        try:
            headers = {
                "Authorization": f"Bearer {sendgrid_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": os.getenv("EMAIL_FROM", "noreply@wolfee.com")},
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": text_body},
                    {"type": "text/html", "value": html_body}
                ]
            }
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)
                if resp.status_code in (200, 202):
                    logger.info(f"Email '{subject}' sent to {to_email} via SendGrid.")
                    return True
                else:
                    logger.error(f"SendGrid API error ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send email via SendGrid to {to_email}: {e}")

    # 3. SMTP Relay
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if smtp_host and smtp_user and smtp_pass:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = os.getenv("EMAIL_FROM", "Wolfee Analytics <noreply@wolfee.com>")
            msg["To"] = to_email
            msg.set_content(text_body)
            if html_body:
                msg.add_alternative(html_body, subtype="html")

            # Handle SSL (Port 465) vs STARTTLS (Port 587, 25, 2525)
            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)

            logger.info(f"Email '{subject}' sent to {to_email} via SMTP ({smtp_host}:{smtp_port}).")
            return True
        except Exception as e:
            logger.error(f"Failed to send email via SMTP ({smtp_host}:{smtp_port}) to {to_email}: {e}")

    # 4. Fallback: Log directly to Railway console
    logger.warning("================================================================================")
    logger.warning(f"⚠️ [NO LIVE EMAIL SENT] No email service configured on Railway.")
    logger.warning(f"Target: {to_email} | Subject: {subject}")
    if fallback_link:
        logger.warning(f"Action Link for {action_name}:")
        logger.warning(f"👉 {fallback_link}")
    logger.warning("To send live emails to inboxes:")
    logger.warning("  Option A (Recommended): Set RESEND_API_KEY=re_... in Railway variables.")
    logger.warning("  Option B: Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM.")
    logger.warning("  Option C (Dev bypass): Set AUTO_VERIFY_DEV=true in Railway variables.")
    logger.warning("================================================================================")
    return False


async def send_verification_email(
    to_email: str,
    raw_token: str,
    base_url: str = "",
    request: Optional[Request] = None
) -> bool:
    """Send an email verification link (via Resend, SendGrid, SMTP, or log fallback)."""
    if not base_url:
        base_url = get_app_base_url(request)

    verify_link = f"{base_url.rstrip('/')}/api/auth/verify-email?token={raw_token}"
    subject = "Verify your Wolfee Analytics account"
    text_body = (
        f"Welcome to Wolfee Analytics!\n\n"
        f"Please verify your email address by opening the following link:\n"
        f"{verify_link}\n\n"
        f"This verification link will expire in 24 hours.\n\n"
        f"If you did not register for Wolfee Analytics, please ignore this email."
    )
    html_body = create_email_html(
        title="Verify Your Account",
        preheader="Welcome to Wolfee Analytics! Please confirm your email address to activate your cloud watchlist and live analytics.",
        button_label="Verify Email Address",
        button_url=verify_link,
        subtext="This link will expire in 24 hours. If you did not create an account, you can safely ignore this email."
    )

    return await dispatch_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        fallback_link=verify_link,
        action_name="Email Verification"
    )


async def send_password_reset_email(
    to_email: str,
    raw_token: str,
    base_url: str = "",
    request: Optional[Request] = None
) -> bool:
    """Send a password reset link (via Resend, SendGrid, SMTP, or log fallback)."""
    if not base_url:
        base_url = get_app_base_url(request)

    reset_link = f"{base_url.rstrip('/')}/index.html?reset_token={raw_token}"
    subject = "Reset your Wolfee Analytics password"
    text_body = (
        f"A password reset was requested for your Wolfee Analytics account.\n\n"
        f"Use this link to reset your password:\n"
        f"{reset_link}\n\n"
        f"This link expires in 1 hour. If you didn't request this, ignore this email."
    )
    html_body = create_email_html(
        title="Reset Your Password",
        preheader="A password reset request was received for your Wolfee account. Click below to choose a new password.",
        button_label="Reset Password",
        button_url=reset_link,
        subtext="This link expires in 1 hour. If you did not request a password reset, you can safely ignore this email."
    )

    return await dispatch_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        fallback_link=reset_link,
        action_name="Password Reset"
    )
