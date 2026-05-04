#!/usr/bin/env python3
"""
Build a Tidal playlist from a JSON track list.

Usage:
    pip install tidalapi
    python tidal_playlist.py tracks.json

JSON schema:
    {
      "name": "My Party Playlist",
      "description": "Optional description",
      "tracks": [
        {"artist": "Artist Name", "title": "Track Title"},
        {"track_id": 12345678, "artist": "...", "title": "..."},
        {"artist": "...", "title": "...", "energy": 7, "vibe": "peak"}
      ]
    }

Each track needs EITHER `track_id` (preferred — pins exact Tidal track) OR
both `artist` and `title` (script searches Tidal). When both are given,
`track_id` wins; the artist/title are kept for human readability only.

`energy` and `vibe` are optional metadata — not used by this script, but
useful when curating an intended DJ flow. Track ORDER is preserved exactly.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import tidalapi
from tidal_session import get_session


MAX_SPEC_BYTES = 10_000_000  # 10 MB hard cap — guards against accidental huge inputs


def find_track(session: tidalapi.Session, artist: str, title: str):
    """Search Tidal for a track. Returns (track, exact_match: bool) or (None, False).

    `exact_match=False` means we fell back to the first search result because
    no result strictly matched both artist and title — caller should surface
    this so the user can spot mis-pinnings without verifying after the fact.
    """
    query = f"{artist} {title}"
    try:
        results = session.search(query, models=[tidalapi.Track], limit=5)
        tracks = results.get("tracks", [])
        if not tracks:
            return None, False
        artist_lower = artist.lower()
        title_lower = title.lower()
        for track in tracks:
            track_artists = [a.name.lower() for a in track.artists]
            if any(artist_lower in a for a in track_artists) and title_lower in track.name.lower():
                return track, True
        return tracks[0], False
    except Exception as e:
        print(f"    ⚠️  Search error for '{query}': {e}")
        return None, False


def load_spec(path: Path) -> dict:
    size = path.stat().st_size
    if size > MAX_SPEC_BYTES:
        raise SystemExit(f"{path}: {size} bytes exceeds {MAX_SPEC_BYTES}-byte cap")
    spec = json.loads(path.read_text())
    if not spec.get("name") or not isinstance(spec.get("tracks"), list):
        raise ValueError(f"{path}: must have 'name' (str) and 'tracks' (list)")
    for i, t in enumerate(spec["tracks"]):
        if not t.get("track_id") and not (t.get("artist") and t.get("title")):
            raise ValueError(f"{path}: track {i} needs 'track_id' OR ('artist' AND 'title')")
    return spec


def main():
    parser = argparse.ArgumentParser(description="Build a Tidal playlist from JSON.")
    parser.add_argument("spec", type=Path, help="Path to tracks.json")
    args = parser.parse_args()

    spec = load_spec(args.spec)
    name = spec["name"]
    description = spec.get("description", "")
    tracks_in = spec["tracks"]

    print("\n🎵 Tidal Playlist Builder")
    print("=" * 55)
    session = get_session()

    print(f"\n📋 Creating playlist: '{name}'...")
    playlist = session.user.create_playlist(name, description)
    print(f"✅ Playlist created (ID: {playlist.id})")

    print(f"\n🔍 Resolving {len(tracks_in)} tracks...\n")
    found_ids = []
    not_found = []
    for i, t in enumerate(tracks_in, 1):
        artist = t.get("artist", "")
        title = t.get("title", "")
        label = f"{artist} — {title}" if artist or title else f"id:{t.get('track_id')}"
        print(f"  [{i:02d}/{len(tracks_in)}] {label} ... ", end="", flush=True)
        track = None
        exact = True  # ID lookups are always exact; only search can fall back.
        if t.get("track_id"):
            try:
                track = session.track(t["track_id"])
            except Exception as e:
                print(f"❌  id lookup failed: {e}")
        else:
            track, exact = find_track(session, artist, title)
        if track:
            found_ids.append(track.id)
            duration = f"{track.duration // 60}:{track.duration % 60:02d}"
            actual = f"{track.artists[0].name} — {track.name}" if track.artists else track.name
            marker = "✅" if exact else "⚠️ "  # ⚠️  = fell back to first search result
            print(f"{marker}  ({duration})  {actual}")
        else:
            not_found.append((artist, title))
            if not t.get("track_id"):
                print("❌  not found")
        time.sleep(0.2)

    # Add in batches. Tidal's playlist API uses an If-Match etag that advances
    # after every successful add — re-fetch the playlist between batches or
    # subsequent adds fail with 412 Precondition Failed.
    print(f"\n➕ Adding {len(found_ids)} tracks to playlist...")
    BATCH_SIZE = 20
    added = 0
    failed = []
    for i in range(0, len(found_ids), BATCH_SIZE):
        batch = found_ids[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        ok = False
        for attempt in range(2):
            try:
                playlist.add(batch)
                added += len(batch)
                print(f"   Batch {batch_num}: added {len(batch)} tracks")
                ok = True
                break
            except Exception as e:
                if attempt == 0:
                    try:
                        playlist = session.playlist(playlist.id)
                    except Exception:
                        pass
                else:
                    print(f"   ⚠️  Batch {batch_num} failed after retry: {e}")
                    failed.append((batch_num, len(batch), str(e)))
        if ok:
            try:
                playlist = session.playlist(playlist.id)
            except Exception:
                pass
        time.sleep(0.5)

    print("\n" + "=" * 55)
    print(f"✅ Done! {added}/{len(tracks_in)} tracks actually added "
          f"({len(found_ids)} found, {len(not_found)} not found).")
    if not_found:
        print(f"\n⚠️  {len(not_found)} tracks not found on Tidal:")
        for artist, title in not_found:
            print(f"   • {artist} — {title}")
    if failed:
        print(f"\n⚠️  {len(failed)} batch(es) failed:")
        for num, size, err in failed:
            print(f"   • Batch {num} ({size} tracks): {err}")
    print(f"\n🎉 Playlist URL: https://tidal.com/browse/playlist/{playlist.id}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
