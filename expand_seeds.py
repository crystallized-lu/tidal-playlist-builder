#!/usr/bin/env python3
"""
Expand a small set of seed tracks into a ranked candidate pool by combining:
  Layer A — Tidal track radio for each seed (~100 algorithmic neighbours each)
  Layer B — Tracks pulled from public Tidal playlists matching mood keywords

Tracks that appear across multiple seeds and/or multiple mood playlists
score highest. Output is a candidate pool you (or Claude) can curate into
a tracks.json for tidal_playlist.py.

SCOPE: This tool handles playlist METADATA only — it queries Tidal's
recommendation engine and public playlist contents (track titles, artist
names, IDs). It does NOT download, decode, stream, or analyze any audio.

Usage:
    python expand_seeds.py seeds.json -o candidates.json

seeds.json schema:
    {
      "seeds": [
        {"artist": "Burna Boy", "title": "Last Last"},
        {"artist": "Rosalía", "title": "Malamente"}
      ],
      "moods": ["afrobeats party", "global pop workout"],
      "playlists_per_mood": 8,
      "tracks_per_playlist": 50,
      "top_n": 150
    }
"""

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import tidalapi
from tidal_session import get_session

MAX_SPEC_BYTES = 10_000_000  # 10 MB hard cap


def find_track(session, artist: str, title: str):
    """Returns (track, exact_match) or (None, False) — exact_match=False means
    we fell back to the first result because no strict match existed."""
    query = f"{artist} {title}"
    try:
        results = session.search(query, models=[tidalapi.Track], limit=5)
        tracks = results.get("tracks", [])
        if not tracks:
            return None, False
        a_lower, t_lower = artist.lower(), title.lower()
        for tr in tracks:
            if any(a_lower in a.name.lower() for a in tr.artists) and t_lower in tr.name.lower():
                return tr, True
        return tracks[0], False
    except Exception as e:
        print(f"    ⚠️  Search error '{query}': {e}")
        return None, False


def search_playlists(session, query: str, limit: int):
    try:
        results = session.search(query, models=[tidalapi.Playlist], limit=limit)
        return results.get("playlists", []) or []
    except Exception as e:
        print(f"    ⚠️  Playlist search error '{query}': {e}")
        return []


def track_key(track) -> tuple[str, str]:
    """Dedupe key: lowercase primary artist + lowercase title."""
    primary = track.artists[0].name if track.artists else ""
    return (primary.lower().strip(), track.name.lower().strip())


def display(track) -> tuple[str, str]:
    primary = track.artists[0].name if track.artists else "Unknown"
    return (primary, track.name)


def main():
    parser = argparse.ArgumentParser(description="Expand seeds into candidate tracks.")
    parser.add_argument("seeds", type=Path, help="Path to seeds.json")
    parser.add_argument("-o", "--output", type=Path, default=Path("candidates.json"))
    args = parser.parse_args()

    size = args.seeds.stat().st_size
    if size > MAX_SPEC_BYTES:
        raise SystemExit(f"{args.seeds}: {size} bytes exceeds {MAX_SPEC_BYTES}-byte cap")
    spec = json.loads(args.seeds.read_text())
    seeds = spec.get("seeds", [])
    moods = spec.get("moods", [])
    playlists_per_mood = spec.get("playlists_per_mood", 8)
    tracks_per_playlist = spec.get("tracks_per_playlist", 50)
    top_n = spec.get("top_n", 150)

    if not seeds and not moods:
        raise SystemExit("seeds.json must contain at least 'seeds' or 'moods'")

    print("\n🌱 Tidal Seed Expander")
    print("=" * 55)
    session = get_session()

    # key -> aggregated info
    pool: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "artist": "", "title": "", "radio_count": 0, "playlist_count": 0,
        "sources": set(), "track_id": None,
    })
    seed_keys: set[tuple[str, str]] = set()

    # ── Layer A: track radio for each seed ─────────────────────
    if seeds:
        print(f"\n🔎 Resolving {len(seeds)} seeds and pulling track radio...\n")
    for i, s in enumerate(seeds, 1):
        artist, title = s["artist"], s["title"]
        print(f"  [{i}/{len(seeds)}] {artist} — {title}")
        seed_track, exact = find_track(session, artist, title)
        if not seed_track:
            print(f"      ⚠️  seed not found on Tidal, skipping")
            continue
        if not exact:
            got = seed_track.artists[0].name if seed_track.artists else "?"
            print(f"      ⚠️  no strict match, using first result: {got} — {seed_track.name}")
        seed_keys.add(track_key(seed_track))
        try:
            radio = seed_track.get_track_radio()
        except Exception as e:
            print(f"      ⚠️  radio error: {e}")
            continue
        for rt in radio:
            k = track_key(rt)
            entry = pool[k]
            entry["artist"], entry["title"] = display(rt)
            entry["radio_count"] += 1
            entry["sources"].add("radio")
            entry["track_id"] = rt.id
        print(f"      + {len(radio)} radio tracks")
        time.sleep(0.3)

    # ── Layer B: public playlist search per mood ───────────────
    if moods:
        print(f"\n🎯 Searching playlists for {len(moods)} mood keyword(s)...\n")
    for mood in moods:
        print(f"  🔍 '{mood}'")
        playlists = search_playlists(session, mood, playlists_per_mood)
        print(f"      found {len(playlists)} playlists")
        for pl in playlists:
            try:
                pl_tracks = pl.tracks(limit=tracks_per_playlist)
            except Exception as e:
                print(f"      ⚠️  playlist tracks error: {e}")
                continue
            for pt in pl_tracks:
                k = track_key(pt)
                entry = pool[k]
                entry["artist"], entry["title"] = display(pt)
                entry["playlist_count"] += 1
                entry["sources"].add("playlist")
                entry["track_id"] = pt.id
            time.sleep(0.2)
        time.sleep(0.3)

    # ── Rank ───────────────────────────────────────────────────
    # Score: a track that appears in multiple seed radios AND multiple mood
    # playlists is most "central". Weight playlist co-occurrence slightly
    # higher than radio because radio is per-seed (mechanically inflates).
    candidates = []
    for k, entry in pool.items():
        if k in seed_keys:
            continue
        score = entry["radio_count"] + 1.5 * entry["playlist_count"]
        candidates.append({
            "artist": entry["artist"],
            "title": entry["title"],
            "score": round(score, 2),
            "radio_count": entry["radio_count"],
            "playlist_count": entry["playlist_count"],
            "sources": sorted(entry["sources"]),
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    candidates = candidates[:top_n]

    out = {
        "seeds": seeds,
        "moods": moods,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print("\n" + "=" * 55)
    print(f"✅ Wrote {len(candidates)} candidates to {args.output}")
    print(f"\nTop 15 preview:")
    for c in candidates[:15]:
        print(f"  {c['score']:>5}  {c['artist']} — {c['title']}  "
              f"(radio:{c['radio_count']}, playlists:{c['playlist_count']})")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
