#!/bin/bash
# pi-noise-monitor install script
# Run this on a fresh Raspberry Pi 4 running Raspberry Pi OS (Bookworm or later).
# Usage: bash setup/install.sh

set -e

echo "==> Updating package lists..."
sudo apt-get update -y

echo "==> Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    ffmpeg \
    portaudio19-dev \
    python3-dev

echo "==> Installing Python packages..."
pip3 install \
    sounddevice \
    numpy \
    scipy \
    RPi.GPIO \
    gspread \
    google-auth \
    google-auth-oauthlib \
    google-api-python-client \
    python-telegram-bot \
    --break-system-packages

echo "==> Creating project directories..."
mkdir -p /home/pi/noisedetector
mkdir -p /home/pi/noise_logs

echo "==> Copying project files..."
cp monitor.py  /home/pi/noisedetector/
cp digest.py   /home/pi/noisedetector/
cp bot.py      /home/pi/noisedetector/

echo ""
echo "==> MANUAL STEPS REQUIRED before starting services:"
echo ""
echo "  1. Copy your service account key:"
echo "     cp config/credentials.json.example /home/pi/noisedetector/credentials.json"
echo "     (then replace placeholder values with your actual Google Cloud key)"
echo ""
echo "  2. Create secrets.json with your Gmail app password:"
echo "     cp config/secrets.json.example /home/pi/noisedetector/secrets.json"
echo "     nano /home/pi/noisedetector/secrets.json"
echo ""
echo "  3. Add email recipients:"
echo "     cp config/recipients.txt.example /home/pi/noisedetector/recipients.txt"
echo "     nano /home/pi/noisedetector/recipients.txt"
echo ""
echo "  4. Edit monitor.py and set your SHEET_ID and SENDER_EMAIL"
echo "  5. Edit digest.py and set your SENDER_EMAIL"
echo "  6. Edit bot.py and set your TOKEN"
echo ""
echo "==> Installing systemd services..."
sudo cp setup/noisedetector.service /etc/systemd/system/
sudo cp setup/noisebot.service      /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable noisedetector noisebot

echo ""
echo "==> Once manual steps above are done, start services with:"
echo "    sudo systemctl start noisedetector"
echo "    sudo systemctl start noisebot"
echo ""
echo "==> Setup complete."
