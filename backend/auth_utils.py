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
from typing import Optional, Tuple
import bcrypt
import httpx

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
# ============================================================
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Wolfee Analytics <noreply@wolfee.com>")

async def send_verification_email(to_email: str, raw_token: str, base_url: str = ""):
    """
    Send an email verification link.
    If SMTP credentials are provided, sends live email.
    Otherwise, logs the verification link to the console for development/staging.
    """
    if not base_url:
        base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")

    verify_link = f"{base_url.rstrip('/')}/api/auth/verify-email?token={raw_token}"
    subject = "Verify your Wolfee Analytics account"
    body = (
        f"Welcome to Wolfee Analytics!\n\n"
        f"Please verify your email address by opening the following link:\n"
        f"{verify_link}\n\n"
        f"This verification link will expire in 24 hours.\n\n"
        f"If you did not register for Wolfee Analytics, please ignore this email."
    )

    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = to_email
            msg.set_content(body)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            logger.info(f"Verification email sent to {to_email}")
            return
        except Exception as e:
            logger.error(f"Failed to send email via SMTP to {to_email}: {e}")

    # Fallback to local dev logger
    logger.warning("=================================================================")
    logger.warning(f"[EMAIL DEV FALLBACK] Verification link for {to_email}:")
    logger.warning(f"-> {verify_link}")
    logger.warning("=================================================================")


async def send_password_reset_email(to_email: str, raw_token: str, base_url: str = ""):
    """
    Send a password reset link.
    Falls back to logger if SMTP is unconfigured.
    """
    if not base_url:
        base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")

    reset_link = f"{base_url.rstrip('/')}/index.html?reset_token={raw_token}"
    subject = "Password Reset - Wolfee Analytics"
    body = (
        f"A password reset was requested for your Wolfee Analytics account.\n\n"
        f"Use this link to reset your password:\n"
        f"{reset_link}\n\n"
        f"This link expires in 1 hour. If you didn't request this, ignore this email."
    )

    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = to_email
            msg.set_content(body)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            logger.info(f"Password reset email sent to {to_email}")
            return
        except Exception as e:
            logger.error(f"Failed to send reset email to {to_email}: {e}")

    logger.warning("=================================================================")
    logger.warning(f"[EMAIL DEV FALLBACK] Password reset link for {to_email}:")
    logger.warning(f"-> {reset_link}")
    logger.warning("=================================================================")
