"""Get an X OAuth 2.0 user-context token that can read your bookmarks.

One-time setup in the X developer portal (your app → User authentication settings):
  - enable OAuth 2.0, type "Web App" (confidential) or "Native App" (public)
  - callback URL: http://127.0.0.1:8765/callback
  - put X_OAUTH_CLIENT_ID (and X_OAUTH_CLIENT_SECRET for a Web App) in backend/keys.env

Usage:
  uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/x_user_token.py
      Prints an authorize link; open it, approve, then paste the URL your browser
      was redirected to (the page itself will not load, which is fine).
  uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/x_user_token.py --refresh
      Swaps X_USER_REFRESH_TOKEN for a fresh access token (they expire after 2 hours).

Writes X_USER_ACCESS_TOKEN and X_USER_REFRESH_TOKEN into backend/keys.env and
prints only the authenticated @handle, never the token values.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import sys
import urllib.parse
import urllib.request
from pathlib import Path

KEYS_FILE = Path("backend/keys.env").resolve()  # run from the repository root
REDIRECT_URI = "http://127.0.0.1:8765/callback"
SCOPES = "tweet.read users.read bookmark.read offline.access"
CLIENT_ID = os.environ["X_OAUTH_CLIENT_ID"]
CLIENT_SECRET = os.environ.get("X_OAUTH_CLIENT_SECRET")


def token_request(fields):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "curl/8.5.0",
    }
    if CLIENT_SECRET:
        basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        headers["Authorization"] = f"Basic {basic}"
    else:
        fields = {**fields, "client_id": CLIENT_ID}
    request = urllib.request.Request(
        "https://api.x.com/2/oauth2/token",
        data=urllib.parse.urlencode(fields).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def save_tokens(tokens):
    values = {
        "X_USER_ACCESS_TOKEN": tokens["access_token"],
        "X_USER_REFRESH_TOKEN": tokens["refresh_token"],
    }
    text = KEYS_FILE.read_text()
    for name, value in values.items():
        line = f"{name}={value}"
        pattern = re.compile(rf"^{name}=.*$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(lambda _: line, text)
        else:
            text = text.rstrip("\n") + f"\n{line}\n"
    KEYS_FILE.write_text(text)


def whoami(access_token):
    request = urllib.request.Request(
        "https://api.x.com/2/users/me",
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": "curl/8.5.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["data"]["username"]


if "--refresh" in sys.argv:
    tokens = token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": os.environ["X_USER_REFRESH_TOKEN"],
        }
    )
else:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    print("Open this link, approve access, then paste the full redirected URL:\n")
    print(f"https://x.com/i/oauth2/authorize?{query}\n")
    params = urllib.parse.parse_qs(
        urllib.parse.urlparse(input("Redirected URL: ").strip()).query
    )
    if params.get("state", [None])[0] != state:
        sys.exit("State mismatch: paste the URL from this run's authorize link.")
    tokens = token_request(
        {
            "grant_type": "authorization_code",
            "code": params["code"][0],
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
    )

save_tokens(tokens)
print(
    f"Saved X user tokens to {KEYS_FILE} for @{whoami(tokens['access_token'])} (scopes: {tokens.get('scope')})."
)
