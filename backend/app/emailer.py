# backend/app/emailer.py
import os, asyncio, ssl
from email.message import EmailMessage
import aiosmtplib

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@smart-librarian")
# starttls | ssl | none   (ssl = implicit TLS on connect / port 465, starttls = explicit TLS / port 587)
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").lower()

def _build_msg(to: str, subject: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("HTML email")
    msg.add_alternative(html, subtype="html")
    return msg

async def _send_async(to: str, subject: str, html: str):
    # Dev fallback: no SMTP configured → just print and exit
    if not SMTP_HOST:
        print(f"\n[DEV EMAIL] To: {to}\nSubject: {subject}\n{html}\n")
        return

    msg = _build_msg(to, subject, html)

    if SMTP_SECURITY in ("ssl", "implicit"):
        # implicit TLS (e.g., Gmail 465)
        ctx = ssl.create_default_context()
        smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=True, tls_context=ctx)
        await smtp.connect()
        if SMTP_USER: await smtp.login(SMTP_USER, SMTP_PASS)
        await smtp.send_message(msg)
        await smtp.quit()

    elif SMTP_SECURITY in ("starttls", "tls"):
        # explicit TLS (e.g., port 587)
        ctx = ssl.create_default_context()
        smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=False)
        await smtp.connect()
        await smtp.starttls(tls_context=ctx)
        if SMTP_USER: await smtp.login(SMTP_USER, SMTP_PASS)
        await smtp.send_message(msg)
        await smtp.quit()

    else:
        # plain (no TLS) — for local mail relays
        smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=False)
        await smtp.connect()
        if SMTP_USER: await smtp.login(SMTP_USER, SMTP_PASS)
        await smtp.send_message(msg)
        await smtp.quit()

def send_email(to: str, subject: str, html: str) -> None:
    """Fire-and-forget if there is an event loop, otherwise run synchronously.
    Never raises (we don’t want 500s for email hiccups)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_async(to, subject, html))
    except RuntimeError:
        # No loop in this worker thread → run now
        try:
            asyncio.run(_send_async(to, subject, html))
        except Exception as e:
            print(f"[EMAIL ERROR] {e}. Falling back to console print.")
            print(f"\n[DEV EMAIL] To: {to}\nSubject: {subject}\n{html}\n")
