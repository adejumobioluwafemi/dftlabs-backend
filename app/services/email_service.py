import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)


def _build_confirmation_html(
    name: str,
    event_title: str,
    event_date: str,
    event_time: str,
    event_location: str,
    is_virtual: bool,
) -> str:
    attendance = "Virtually" if is_virtual else "In Person"
    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;
                padding:40px 24px;background:#f8fafc;">
      <div style="background:#070d1a;border-radius:16px;padding:40px;color:white;">
        <img src="https://deepflytechlabs.com/logo.svg"
             height="48" alt="DFT Labs"
             style="margin-bottom:32px;display:block;" />
        <h1 style="color:#4A8FD4;font-size:24px;margin:0 0 8px;">
          You're registered! 🎉
        </h1>
        <p style="color:#94a3b8;margin:0 0 32px;">
          Hi {name}, your spot is confirmed.
        </p>
        <div style="background:rgba(74,143,212,0.1);
                    border:1px solid rgba(74,143,212,0.3);
                    border-radius:12px;padding:24px;margin-bottom:32px;">
          <h2 style="color:white;font-size:18px;margin:0 0 16px;">
            {event_title}
          </h2>
          <p style="color:#94a3b8;margin:4px 0;">📅 {event_date}</p>
          <p style="color:#94a3b8;margin:4px 0;">🕒 {event_time}</p>
          <p style="color:#94a3b8;margin:4px 0;">📍 {event_location}</p>
          <p style="color:#94a3b8;margin:4px 0;">🖥 Attending: {attendance}</p>
        </div>
        <p style="color:#64748b;font-size:13px;">
          We'll send joining instructions closer to the date.
          Questions? Reply to this email.
        </p>
        <p style="color:#64748b;font-size:13px;margin-top:24px;">
          — The DFT Labs Team
        </p>
      </div>
    </div>
    """


async def send_confirmation_email(
    *,
    to_email: str,
    name: str,
    event_title: str,
    event_date: str,
    event_time: str,
    event_location: str,
    is_virtual: bool,
) -> None:
    """
    Send event registration confirmation.
    Runs as a FastAPI BackgroundTask — failures are logged, never raised.
    """
    if not settings.RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY not configured — skipping confirmation to %s",
            to_email,
        )
        return

    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": f"Registered: {event_title} — DFT Labs",
            "html": _build_confirmation_html(
                name=name,
                event_title=event_title,
                event_date=event_date,
                event_time=event_time,
                event_location=event_location,
                is_virtual=is_virtual,
            ),
        })
        logger.info("Confirmation email sent → %s", to_email)
    except Exception:
        logger.exception("Failed to send confirmation email to %s", to_email)