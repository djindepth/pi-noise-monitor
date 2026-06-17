# pi-noise-monitor

A Raspberry Pi 4 project that continuously monitors ambient noise levels, records audio clips when thresholds are exceeded, uploads them to Google Drive, logs events to a Google Sheet, sends a daily HTML email digest, and provides on-demand status via a Telegram bot.

Originally built to document noise ordinance violations, but adaptable to any environment where you want automated audio event detection and logging.

---

## Features

### Real-Time Noise Detection
- Samples audio in 1-second chunks from a USB microphone
- Calculates calibrated dB levels using a configurable reference level and offset
- Separate thresholds for daytime and nighttime (configurable to match local ordinances or personal preference)

### False Positive Suppression
- **Sustained noise requirement**: noise must stay above threshold for a configurable number of consecutive seconds (default: 5) before triggering a recording — eliminates door slams, passing cars, and other brief transient sounds
- **Escalating cooldown**: if the same noise source stays active continuously, the cooldown between recordings doubles each time (up to a configurable cap of 30 minutes), preventing log spam from a single sustained source

### Audio Recording and Storage
- Records a 15-second MP3 clip centered on the trigger moment
- Converts WAV to MP3 at 96kbps using ffmpeg to minimize storage use
- Uploads clip to a dedicated Google Drive folder with a public sharing link
- Clips are named with timestamp and peak dB for easy identification

### Google Sheets Logging
- Appends one row per event to a Google Sheet with: date, time, peak dB, day of week, and a clickable Drive link to the clip
- Uses a service account (credentials never expire — no OAuth re-auth required)

### Daily Email Digest
- Sends an HTML email every morning via Gmail SMTP with the previous day's events
- Each event row is a clickable timestamp hyperlink that opens the clip on Google Drive
- Includes retry logic (5 attempts, 30-second intervals) to handle cases where the Pi boots before DNS/network is ready
- Supports a configurable recipient list (BCC)
- Can be tested immediately with `python3 digest.py test` (sends today's events)

### Telegram Bot
- On-demand status from anywhere via iPhone or Android
- Commands:
  - `/status` — confirms Pi is online, shows today's event count and last event time/dB
  - `/today` — lists all of today's events with timestamps and peak dB
  - `/yesterday` — same for yesterday
  - `/help` — command reference
- Locks to a single authorized user on first `/start` — no one else can query your Pi
- Runs as a persistent systemd service; auto-restarts on crash or reboot

### LED Status Indicators
- Green LED: on whenever the monitor service is running
- Red LED: flashes while a clip is being recorded
- Both LEDs shut off cleanly on service stop

### Resilient by Design
- Both monitor and Telegram bot run as systemd services with automatic restart on failure
- Service account credentials never expire (no Google OAuth 7-day token rotation issue)
- SMTP retries handle network-not-ready-at-boot scenarios
- Graceful GPIO cleanup on SIGTERM/SIGINT

---

## Hardware

| Component | Notes |
|---|---|
| Raspberry Pi 4 | Any RAM configuration works |
| USB microphone | Any USB audio device; run `python3 -c "import sounddevice; print(sounddevice.query_devices())"` to find your device name |
| 2× LED + resistors | Green (GPIO 27) and Red (GPIO 17), BCM numbering; ~220–330Ω resistors |
| MicroSD card | 16GB+ recommended |

---

## Prerequisites

### Google Cloud Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project
2. Enable the **Google Drive API** and **Google Sheets API** for the project
3. Create a **Service Account** (IAM & Admin → Service Accounts → Create)
4. Download a JSON key for the service account — this becomes your `credentials.json`
5. Create a Google Sheet and share it with the service account's email address (Editor access)
6. Copy the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`

### Gmail App Password

1. Enable 2-Factor Authentication on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Generate an app password for "Mail" — this goes in `secrets.json`

### Telegram Bot Token

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the token BotFather provides — this goes in `bot.py`

---

## Installation

Clone this repo onto the Pi (or copy the files over):

```bash
git clone https://github.com/YOUR_USERNAME/pi-noise-monitor.git
cd pi-noise-monitor
```

Run the install script:

```bash
bash setup/install.sh
```

The script installs system packages, Python dependencies, copies the project files to `/home/pi/noisedetector/`, and registers the systemd services. It will pause and list the manual configuration steps you need to complete before starting.

---

## Configuration

### 1. Credentials and secrets

```bash
# Service account key from Google Cloud Console
cp config/credentials.json.example /home/pi/noisedetector/credentials.json
nano /home/pi/noisedetector/credentials.json   # paste your actual key

# Gmail app password
cp config/secrets.json.example /home/pi/noisedetector/secrets.json
nano /home/pi/noisedetector/secrets.json

# Email recipients
cp config/recipients.txt.example /home/pi/noisedetector/recipients.txt
nano /home/pi/noisedetector/recipients.txt
```

### 2. Edit the Python files

In `monitor.py`:
- `DEVICE` — set to your USB microphone's name (run `python3 -c "import sounddevice; print(sounddevice.query_devices())"`)
- `SHEET_ID` — your Google Sheet ID
- `SENDER_EMAIL` — your Gmail address

In `digest.py`:
- `SENDER_EMAIL` — your Gmail address

In `bot.py`:
- `TOKEN` — your Telegram bot token from BotFather

### 3. Calibration

The default thresholds assume a specific microphone and room. To calibrate for your setup:

1. Use a reference sound meter app (e.g., NIOSH SLM on iOS) to measure a known sound
2. Run the monitor in a terminal and watch the `Current level:` output
3. Adjust `CALIBRATION_OFFSET` in `monitor.py` until the Pi's readings match the reference meter
4. Set your `get_threshold()` return values to match your local noise ordinance limits plus a margin

### 4. Daily digest cron job

```bash
crontab -e
```

Add the line from `setup/crontab.example` (sends at 7:00 AM daily).

---

## Starting the Services

```bash
sudo systemctl start noisedetector
sudo systemctl start noisebot

# Check status
sudo systemctl status noisedetector
sudo systemctl status noisebot

# View live logs
journalctl -u noisedetector -f
journalctl -u noisebot -f
```

Both services are enabled at boot by the install script.

---

## File Structure

```
pi-noise-monitor/
├── monitor.py              # Main monitoring loop
├── digest.py               # Daily email digest
├── bot.py                  # Telegram bot
├── config/
│   ├── credentials.json.example   # Google service account key template
│   ├── secrets.json.example       # Gmail app password template
│   └── recipients.txt.example     # Email recipient list template
├── setup/
│   ├── install.sh                 # One-command setup script
│   ├── noisedetector.service      # systemd unit for monitor
│   ├── noisebot.service           # systemd unit for Telegram bot
│   └── crontab.example            # Daily digest cron entry
└── .gitignore
```

Runtime files (not in repo):
- `/home/pi/noisedetector/credentials.json` — service account key (never commit)
- `/home/pi/noisedetector/secrets.json` — Gmail app password (never commit)
- `/home/pi/noisedetector/recipients.txt` — email list (never commit)
- `/home/pi/noisedetector/bot_config.json` — stores authorized Telegram chat ID
- `/home/pi/noise_logs/events.json` — all logged events
- `/home/pi/noise_logs/*.mp3` — audio clips (uploaded to Drive, can be deleted locally)

---

## Tuning

| Parameter | Location | Default | Description |
|---|---|---|---|
| `SUSTAINED_CHUNKS_REQUIRED` | monitor.py | 5 | Seconds of sustained noise before logging |
| `BASE_COOLDOWN` | monitor.py | 35 | Seconds between events from fresh noise |
| `MAX_COOLDOWN` | monitor.py | 1800 | Max seconds between events from a continuous source |
| `RECORD_DURATION` | monitor.py | 15 | Seconds of audio to record per clip |
| `MP3_BITRATE` | monitor.py | 96k | Audio quality / file size tradeoff |
| `SMTP_MAX_RETRIES` | digest.py | 5 | Email send attempts on network failure |
| `SMTP_RETRY_DELAY` | digest.py | 30 | Seconds between retry attempts |

---

## License

MIT
