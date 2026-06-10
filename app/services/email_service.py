"""
Email Service — Handles sending transactional emails (OTP, Notifications).
"""
import logging
import aiosmtplib
from email.message import EmailMessage
from app.config import settings

logger = logging.getLogger(__name__)

async def send_email(to_email: str, subject: str, body: str, html_body: str = None) -> bool:
    """
    Generic async function to send emails using aiosmtplib.
    """
    try:
        message = EmailMessage()
        message["From"] = settings.SMTP_USER
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        if html_body:
            message.add_alternative(html_body, subtype='html')

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=settings.SMTP_PORT == 465,
            start_tls=settings.SMTP_PORT == 587,
        )

        logger.info(f"Email successfully sent to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        return False


async def send_otp_email(email: str, otp: str) -> bool:
    subject = "WanderKashmir - Your Password Reset Code"

    # Plain text fallback
    body = f"Your verification code is {otp}. It expires in 10 minutes."

    # Branded HTML layout
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #2F4F4F;">Password Reset Verification</h2>
        <p style="color: #555; line-height: 1.5;">You requested a password reset for your WanderKashmir portal account. Your 6-digit verification code is:</p>
        <div style="background-color: #f5f5f5; padding: 15px; text-align: center; border-radius: 6px; margin: 20px 0;">
            <h1 style="color: #D4822A; letter-spacing: 8px; margin: 0;">{otp}</h1>
        </div>
        <p style="color: #888; font-size: 0.85rem;">This code will expire in 10 minutes. If you did not request this reset, please ignore this email.</p>
    </div>
    """

    return await send_email(email, subject, body, html_body=html_body)