"""
Email Service — Handles sending transactional emails (OTP, Notifications).
"""
import logging
from app.config import settings

# Example using a placeholder approach;
# You would typically integrate with an SMTP server or an API like SendGrid/AWS SES.

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, body: str):
    """
    Generic async function to send emails.
    """
    try:
        # In a real production app, use 'fastapi-mail' or 'aiosmtplib' here
        logger.info(f"Sending email to {to_email} with subject: {subject}")

        # Integration logic (e.g., SMTP connect, send, disconnect)
        # await smtp_client.send_message(...)

        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        return False


async def send_otp_email(email: str, otp: str):
    subject = "Your Verification Code"
    body = f"Your verification code is {otp}. It expires in 10 minutes."
    return await send_email(email, subject, body)