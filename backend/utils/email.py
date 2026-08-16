import httpx

from config import EMAIL_FROM, RESEND_API_KEY

# TODO: once the frontend has real routes for these, point the links there
# instead of at the bare API paths (e.g. https://app.example.com/verify-email?token=...).
VERIFY_EMAIL_PATH = "/api/auth/verify-email?token={token}"
RESET_PASSWORD_PATH = "/reset-password?token={token}"


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via Resend if RESEND_API_KEY is configured, otherwise fall back
    to logging the content to the console (dev/demo mode - no email provider wired up)."""
    if not RESEND_API_KEY:
        print(f"[DEV] Email to {to} - {subject}\n{body}")
        return False

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": EMAIL_FROM,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        print(f"[EMAIL FAILED] Could not send to {to} - {subject}\n{body}")
        return False


def send_verification_email(to: str, token: str) -> bool:
    link = VERIFY_EMAIL_PATH.format(token=token)
    return send_email(
        to,
        "Verify your LearnWise email",
        f"Confirm your email address by visiting: {link}",
    )


def send_password_reset_email(to: str, token: str) -> bool:
    link = RESET_PASSWORD_PATH.format(token=token)
    return send_email(
        to,
        "Reset your LearnWise password",
        f"Reset your password by visiting: {link}\nIf you didn't request this, you can ignore this email.",
    )
