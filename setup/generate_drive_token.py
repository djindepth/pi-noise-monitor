#!/usr/bin/env python3
"""
Run this script ONCE on your Mac or PC (not on the Pi) to generate drive_token.json.
It opens a browser, asks you to log in with the Google account that owns the Drive
folder, and writes the token file to the current directory.

Then copy drive_token.json to the Pi:
    scp drive_token.json pi@<PI_IP>:/home/pi/noisedetector/drive_token.json

Prerequisites:
    pip install google-auth-oauthlib

You'll need a Google Cloud project with:
  - Drive API enabled
  - An OAuth 2.0 Client ID (type: Desktop app)
  - App published to Production (so the refresh token never expires)

Fill in your client_id and client_secret below before running.
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID     = "YOUR_CLIENT_ID.apps.googleusercontent.com"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"

SCOPES = ["https://www.googleapis.com/auth/drive"]

client_config = {
    "installed": {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
creds = flow.run_local_server(port=0)

token_data = {
    "token":         creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri":     creds.token_uri,
    "client_id":     creds.client_id,
    "client_secret": creds.client_secret,
    "scopes":        list(creds.scopes),
}

with open("drive_token.json", "w") as f:
    json.dump(token_data, f, indent=2)

print("drive_token.json written.")
print("Copy it to the Pi: scp drive_token.json pi@<PI_IP>:/home/pi/noisedetector/drive_token.json")
