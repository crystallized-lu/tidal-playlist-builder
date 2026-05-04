"""Shared Tidal authentication. Caches OAuth session in .tidal_session.json."""

import json
import time
from datetime import datetime
from pathlib import Path

import tidalapi

SESSION_FILE = Path(".tidal_session.json")


def _save(session: tidalapi.Session):
    SESSION_FILE.write_text(json.dumps({
        "token_type": session.token_type,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expiry_time": session.expiry_time.isoformat() if session.expiry_time else None,
    }))


def _load(session: tidalapi.Session) -> bool:
    if not SESSION_FILE.exists():
        return False
    try:
        data = json.loads(SESSION_FILE.read_text())
        session.load_oauth_session(
            token_type=data["token_type"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expiry_time=datetime.fromisoformat(data["expiry_time"]) if data["expiry_time"] else None,
        )
        return session.check_login()
    except Exception as e:
        print(f"⚠️  Cached session invalid ({e}), re-authenticating...")
        return False


def get_session() -> tidalapi.Session:
    """Return a logged-in Tidal session, prompting for OAuth if needed."""
    session = tidalapi.Session()
    if _load(session):
        print(f"✅ Logged in as: {session.user.email}")
        return session

    print("\n🔐 Opening device login flow...")
    login, future = session.login_oauth()
    print(f"\n👉 Open this URL in your browser:\n\n   {login.verification_uri_complete}\n")
    print("Waiting for approval", end="", flush=True)
    while not future.done():
        print(".", end="", flush=True)
        time.sleep(1)
    print()
    if not session.check_login():
        raise RuntimeError("Tidal login failed")
    print(f"✅ Logged in as: {session.user.email}")
    _save(session)
    return session
