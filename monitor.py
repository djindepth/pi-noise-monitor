import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import datetime
import os
import json
import subprocess
import RPi.GPIO as GPIO
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import signal

# ---------------------------------------------------------------------------
# Settings — edit these to match your environment
# ---------------------------------------------------------------------------
SAMPLE_RATE = 48000
CHANNELS = 1
DEVICE = "USB PnP Sound Device"   # run: python3 -c "import sounddevice; print(sounddevice.query_devices())"
CHUNK_DURATION = 1                 # seconds per monitoring chunk
RECORD_DURATION = 15               # seconds to record when triggered
SUSTAINED_CHUNKS_REQUIRED = 5     # consecutive chunks above threshold before logging
BASE_COOLDOWN = 35                 # seconds before re-triggering after an event
MAX_COOLDOWN = 1800                # cap (30 min) for escalating cooldown

LOG_FILE = "/home/pi/noise_logs/events.json"
CLIP_DIR = "/home/pi/noise_logs"

# Calibration — see README for how to determine these values
A_REF = 0.000740
CALIBRATION_OFFSET = 43.3         # dB offset calibrated against a reference meter

# MP3 / Drive settings
MP3_BITRATE = "96k"
DRIVE_FOLDER_NAME = "NoiseDetector Clips"
CREDENTIALS_FILE = "/home/pi/noisedetector/credentials.json"   # service account key
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
_drive_folder_id = None  # cached after first lookup

# Google Sheet ID — copy from your sheet's URL
SHEET_ID = "YOUR_GOOGLE_SHEET_ID"

# LED GPIO pins (BCM numbering)
LED_RED   = 17   # flashes while recording a clip
LED_GREEN = 27   # on whenever monitor is running

# ---------------------------------------------------------------------------
# GPIO setup
# ---------------------------------------------------------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_RED,   GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.output(LED_GREEN, GPIO.HIGH)

def cleanup_handler(signum, frame):
    GPIO.output(LED_GREEN, GPIO.LOW)
    GPIO.output(LED_RED,   GPIO.LOW)
    GPIO.cleanup()
    exit(0)

signal.signal(signal.SIGTERM, cleanup_handler)
signal.signal(signal.SIGINT,  cleanup_handler)

# ---------------------------------------------------------------------------
# Threshold — adjust dB values to match your local ordinance or preference
# ---------------------------------------------------------------------------
def get_threshold():
    hour = datetime.datetime.now().hour
    if hour >= 22 or hour < 7:
        return 64.0   # stricter nighttime threshold
    return 79.4       # daytime threshold

# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def calculate_db(audio_chunk):
    rms = np.sqrt(np.mean(audio_chunk ** 2))
    if rms == 0:
        return 0
    return 20 * np.log10(rms / A_REF) + CALIBRATION_OFFSET

def get_credentials():
    """Load service account credentials — these never expire."""
    return service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES
    )

def convert_to_mp3(wav_path):
    mp3_path = os.path.splitext(wav_path)[0] + ".mp3"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path,
             "-codec:a", "libmp3lame", "-b:a", MP3_BITRATE, mp3_path],
            check=True, capture_output=True
        )
        os.remove(wav_path)
        return mp3_path
    except Exception as e:
        print(f"MP3 conversion failed: {e}")
        return wav_path

# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------
def get_drive_folder_id(service):
    global _drive_folder_id
    if _drive_folder_id:
        return _drive_folder_id
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{DRIVE_FOLDER_NAME}' and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = results.get("files", [])
    if folders:
        _drive_folder_id = folders[0]["id"]
    else:
        folder = service.files().create(
            body={"name": DRIVE_FOLDER_NAME,
                  "mimeType": "application/vnd.google-apps.folder"},
            fields="id"
        ).execute()
        _drive_folder_id = folder["id"]
    return _drive_folder_id

def upload_to_drive(filepath, filename):
    try:
        creds   = get_credentials()
        service = build("drive", "v3", credentials=creds)
        folder_id = get_drive_folder_id(service)
        uploaded = service.files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=MediaFileUpload(filepath, mimetype="audio/mpeg"),
            fields="id, webViewLink"
        ).execute()
        service.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"}
        ).execute()
        return uploaded.get("webViewLink")
    except Exception as e:
        print(f"Drive upload failed: {e}")
        return None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log_event(timestamp, peak_db, filename, drive_link=None):
    event = {
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "peak_db":   round(float(peak_db), 1),
        "clip":      filename,
        "drive_link": drive_link,
    }
    events = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            events = json.load(f)
    events.append(event)
    with open(LOG_FILE, "w") as f:
        json.dump(events, f, indent=2)

def log_to_sheets(timestamp, peak_db, drive_link=None):
    try:
        creds  = get_credentials()
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(SHEET_ID).sheet1
        sheet.append_row([
            timestamp.strftime("%Y-%m-%d"),
            timestamp.strftime("%H:%M:%S"),
            round(float(peak_db), 1),
            timestamp.strftime("%A"),
            drive_link or "",
        ])
        print("Logged to Google Sheets.")
    except Exception as e:
        print(f"Sheets logging failed: {e}")

# ---------------------------------------------------------------------------
# Clip recording
# ---------------------------------------------------------------------------
def record_clip(peak_db):
    GPIO.output(LED_RED, GPIO.HIGH)
    timestamp = datetime.datetime.now()
    filename  = timestamp.strftime("%Y-%m-%d_%H-%M-%S") + f"_{int(peak_db)}dB.wav"
    filepath  = os.path.join(CLIP_DIR, filename)
    print(f"Recording clip: {filename}")
    recording = sd.rec(
        int(RECORD_DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE, channels=CHANNELS,
        dtype="int32", device=DEVICE
    )
    sd.wait()
    wav.write(filepath, SAMPLE_RATE, recording)

    mp3_path     = convert_to_mp3(filepath)
    mp3_filename = os.path.basename(mp3_path)
    drive_link   = upload_to_drive(mp3_path, mp3_filename)
    if drive_link:
        print(f"Uploaded to Drive: {drive_link}")

    log_event(timestamp, float(peak_db), mp3_filename, drive_link)
    GPIO.output(LED_RED, GPIO.LOW)
    log_to_sheets(timestamp, peak_db, drive_link)
    return mp3_filename

# ---------------------------------------------------------------------------
# Main monitor loop
# ---------------------------------------------------------------------------
def monitor():
    print("Noise monitor started.")
    cooldown               = 0
    sustained_count        = 0
    sustained_peak         = 0.0
    next_cooldown          = BASE_COOLDOWN
    quiet_since_last_trigger = True

    while True:
        chunk = sd.rec(
            int(CHUNK_DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE, channels=CHANNELS,
            dtype="float32", device=DEVICE
        )
        sd.wait()
        db        = calculate_db(chunk)
        threshold = get_threshold()

        if cooldown > 0:
            cooldown -= 1
        print(f"Current level: {db:.1f} dB (threshold: {threshold} dB)", flush=True)

        if db > threshold:
            sustained_count += 1
            sustained_peak   = max(sustained_peak, db)
        else:
            sustained_count  = 0
            sustained_peak   = 0.0
            quiet_since_last_trigger = True

        if sustained_count >= SUSTAINED_CHUNKS_REQUIRED and cooldown == 0:
            print(f"Sustained noise: {sustained_peak:.1f} dB for {sustained_count}+ seconds")
            record_clip(sustained_peak)

            if quiet_since_last_trigger:
                next_cooldown = BASE_COOLDOWN
            else:
                next_cooldown = min(next_cooldown * 2, MAX_COOLDOWN)
                print(f"Continuous source — escalating cooldown to {next_cooldown}s")

            cooldown               = next_cooldown
            quiet_since_last_trigger = False
            sustained_count        = 0
            sustained_peak         = 0.0

if __name__ == "__main__":
    monitor()
