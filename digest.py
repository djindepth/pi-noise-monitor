import json
import os
import smtplib
import socket
import time
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
LOG_FILE    = "/home/pi/noise_logs/events.json"
SENDER_EMAIL  = "your-sender@gmail.com"    # Gmail address that sends the digest
SECRETS_FILE  = "/home/pi/noisedetector/secrets.json"

# Retry settings — cron can fire right after boot before DNS is ready
SMTP_MAX_RETRIES  = 5
SMTP_RETRY_DELAY  = 30   # seconds between attempts

# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------
def load_secrets():
    with open(SECRETS_FILE) as f:
        return json.load(f)

SENDER_PASSWORD = load_secrets()["sender_password"]

def load_recipients():
    path = "/home/pi/noisedetector/recipients.txt"
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

RECIPIENTS = load_recipients()

# ---------------------------------------------------------------------------
# Event loading
# ---------------------------------------------------------------------------
def load_yesterdays_events():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r") as f:
        events = json.load(f)
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    return [e for e in events if e["timestamp"].startswith(yesterday)]

def load_todays_events():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r") as f:
        events = json.load(f)
    today = datetime.date.today().strftime("%Y-%m-%d")
    return [e for e in events if e["timestamp"].startswith(today)]

# ---------------------------------------------------------------------------
# HTML email body
# ---------------------------------------------------------------------------
def build_email_body(events):
    if not events:
        return None

    rows = []
    for e in events:
        try:
            dt    = datetime.datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S")
            label = dt.strftime("%a %b %-d, %H:%M")
        except Exception:
            label = e["timestamp"]

        peak       = e["peak_db"]
        drive_link = e.get("drive_link")
        clip_cell  = (f'<a href="{drive_link}">{label}</a>'
                      if drive_link else label)

        rows.append(f"""
        <tr>
          <td style="padding:4px 12px 4px 0;">{clip_cell}</td>
          <td style="padding:4px 12px 4px 0;">{peak} dB</td>
        </tr>""")

    rows_html = "".join(rows)
    total     = len(events)

    return f"""<html><body>
<p>Noise events exceeding ordinance limits detected yesterday:</p>
<table style="border-collapse:collapse; font-family:monospace; font-size:14px;">
  <thead>
    <tr style="text-align:left; border-bottom:1px solid #ccc;">
      <th style="padding:4px 12px 4px 0;">Time</th>
      <th style="padding:4px 12px 4px 0;">Peak</th>
    </tr>
  </thead>
  <tbody>{rows_html}
  </tbody>
</table>
<p><strong>Total events: {total}</strong></p>
<p style="color:#888; font-size:12px;">
Each linked timestamp plays the recorded audio clip on Google Drive.
</p>
</body></html>"""

# ---------------------------------------------------------------------------
# SMTP sending with retry
# ---------------------------------------------------------------------------
def send_via_smtp(msg, recipients):
    last_error = None
    for attempt in range(1, SMTP_MAX_RETRIES + 1):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
            return
        except (socket.gaierror, ConnectionError, TimeoutError,
                smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as e:
            last_error = e
            print(f"SMTP attempt {attempt}/{SMTP_MAX_RETRIES} failed: {e!r}")
            if attempt < SMTP_MAX_RETRIES:
                time.sleep(SMTP_RETRY_DELAY)
    raise last_error

def send_email(events, body):
    msg = MIMEMultipart()
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = SENDER_EMAIL
    msg["Bcc"]     = ", ".join(RECIPIENTS)
    msg["Subject"] = f"Noise Report – {datetime.date.today().strftime('%B %d, %Y')}"
    msg.attach(MIMEText(body, "html"))
    send_via_smtp(msg, RECIPIENTS)
    print(f"Email sent with {len(events)} events.")

# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def send_digest():
    events = load_yesterdays_events()
    if not events:
        print("No events yesterday. No email sent.")
        return
    body = build_email_body(events)
    send_email(events, body)
    print(f"Digest sent with {len(events)} events.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Send today's events as a test
        events = load_todays_events()
        if not events:
            print("No events today to send. Make some noise first!")
        else:
            body = build_email_body(events)
            send_email(events, body)
    else:
        send_digest()
