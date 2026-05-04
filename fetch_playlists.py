#!/usr/bin/env python3
"""
Fetch tracks from one or more known Tidal playlists and emit a
candidate pool JSON.

Use this when you already trust specific source playlists (e.g. ones a
human curated for a theme) and want to pool their tracks for further
curation, rather than relying on search-based discovery.

SCOPE: This tool reads playlist METADATA only — track titles, artist
names, IDs, and which source playlist each track came from. It does NOT
download, decode, stream, or analyze any audio.

Usage:
    python fetch_playlists.py URL1 URL2 URL3 ... -o candidates.json

URLs can be any of:
    https://tidal.com/playlist/<uuid>
    https://tidal.com/browse/playlist/<uuid>
    <uuid>                  (bare playlist ID)

Output schema:
    {
      "sources": [{"id": "<uuid>", "name": "<playlist name>"}, ...],
      "track_count": N,
      "tracks": [
        {
          "track_id": 12345,
          "artist": "Artist Name",
          "title": "Track Title",
          "sources": ["Playlist A", "Playlist B"],
          "source_count": 2
        },
        ...
      ]
    }

Tracks are sorted by `source_count` (descending) — tracks appearing
in multiple source playlists are most likely thematically central, and
are good candidates to seed your final tracks.json for tidal_playlist.py.
"""

import argparse
import json
import re
from pathlib import Path

from tidal_session import get_session

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
TIDAL_PLAYLIST_URL_RE = re.compile(
    r"https?://(?:[\w.-]+\.)?tidal\.com/(?:browse/)?playlist/("
    + UUID_RE.pattern + r")/?$",
    re.IGNORECASE,
)


def parse_playlist_id(arg: str) -> str:
    """Extract a Tidal playlist UUID from a URL or accept a bare UUID.

    Strict: rejects strings that aren't a recognised Tidal playlist URL or a
    bare UUID. This avoids accidentally picking a UUID out of unrelated text.
    """
    arg = arg.strip()
    if UUID_RE.fullmatch(arg):
        return arg.lower()
    m = TIDAL_PLAYLIST_URL_RE.match(arg)
    if m:
        return m.group(1).lower()
    raise ValueError(
        f"Not a Tidal playlist URL or UUID: {arg!r}. "
        "Expected https://tidal.com/playlist/<uuid>, "
        "https://tidal.com/browse/playlist/<uuid>, or a bare UUID."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Fetch tracks from Tidal playlists into a candidate pool.")
    parser.add_argument("urls", nargs="+",
                        help="One or more Tidal playlist URLs or UUIDs")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=300,
                        help="Max tracks to fetch per playlist (default 300)")
    args = parser.parse_args()

    ids = [parse_playlist_id(u) for u in args.urls]
    print(f"\n📥 Fetching {len(ids)} playlist(s)...\n")
    session = get_session()

    sources = []
    pool: dict[int, dict] = {}  # track_id -> aggregate info
    for pid in ids:
        try:
            pl = session.playlist(pid)
            tracks = pl.tracks(limit=args.limit)
        except Exception as e:
            print(f"  ⚠️  {pid}: {e}")
            continue
        sources.append({"id": pid, "name": pl.name})
        print(f"  ✅ {pl.name}  ({len(tracks)} tracks)")
        for t in tracks:
            artist = t.artists[0].name if t.artists else "?"
            title = t.name
            entry = pool.setdefault(t.id, {
                "track_id": t.id,
                "artist": artist,
                "title": title,
                "sources": [],
            })
            if pl.name not in entry["sources"]:
                entry["sources"].append(pl.name)

    candidates = list(pool.values())
    for c in candidates:
        c["source_count"] = len(c["sources"])
    # Sort: tracks shared across most source playlists first.
    candidates.sort(key=lambda c: (-c["source_count"], c["artist"].lower()))

    out = {
        "sources": sources,
        "track_count": len(candidates),
        "tracks": candidates,
    }
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print(f"\n✅ Wrote {len(candidates)} unique tracks to {args.output}")
    overlap = sum(1 for c in candidates if c["source_count"] > 1)
    if overlap:
        print(f"   ({overlap} appear in multiple source playlists)")


if __name__ == "__main__":
    main()
