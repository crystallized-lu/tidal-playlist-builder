"""Shared Tidal authentication.

Caches the OAuth session to disk so repeated runs don't re-prompt.

Default location: $XDG_CONFIG_HOME/tidal-playlist-builder/session.json
                  (or ~/.config/tidal-playlist-builder/session.json)
Override with: TIDAL_PLAYLIST_BUILDER_SESSION=/path/to/session.json

For backwards compatibility, a legacy `.tidal_session.json` in the current
working directory is read if present, but new sessions are always written
to the resolved location above. The file is created with 0600 permissions
so other users on the machine can't read your refresh token.
"""

import json
import os
import stat
import time
from datetime import datetime
from pathlib import Path

import tidalapi

LEGACY_SESSION_FILE = Path(".tidal_session.json")


def _session_path() -> Path:
    override = os.environ.get("TIDAL_PLAYLIST_BUILDER_SESSION")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "tidal-playlist-builder" / "session.json"


def _save(session: tidalapi.Session):
    path = _session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "token_type": session.token_type,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expiry_time": session.expiry_time.isoformat() if session.expiry_time else None,
    })
    # Write with 0600 from the start — never let the file exist world-readable
    # even briefly. os.open + O_CREAT|O_WRONLY|O_TRUNC handles this atomically.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload)
    except Exception:
        os.close(fd)
        raise
    # Defensive chmod in case the file pre-existed with looser perms.
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _load_from(session: tidalapi.Session, path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        session.load_oauth_session(
            token_type=data["token_type"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expiry_time=datetime.fromisoformat(data["expiry_time"]) if data["expiry_time"] else None,
        )
        return session.check_login()
    except Exception as e:
        # Don't print the raw exception — could in theory contain token fragments.
        print(f"⚠️  Cached session at {path} invalid ({type(e).__name__}), re-authenticating...")
        return False


def _load(session: tidalapi.Session) -> bool:
    if _load_from(session, _session_path()):
        return True
    # Backwards compat: pick up an old cwd-relative session file if it exists.
    if _load_from(session, LEGACY_SESSION_FILE):
        return True
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
