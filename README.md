# tidal-playlist-builder

Build curated Tidal playlists from a JSON track list, and expand a small set of seed tracks into a ranked candidate pool using Tidal's track radio + public playlist co-occurrence.

Designed to pair well with an LLM curator: the LLM picks tracks (with optional `energy` / `vibe` metadata for DJ-style sequencing), and these scripts handle the Tidal API plumbing.

## Install

```sh
pip install -r requirements.txt
```

## Authenticate

Both scripts share an OAuth session cached in `.tidal_session.json` (gitignored). On first run you'll get a URL to open in your browser to approve. After that, subsequent runs are silent.

## Build a playlist

```sh
python tidal_playlist.py tracks.json
```

`tracks.json` schema:

```json
{
  "name": "My Party Playlist",
  "description": "Optional",
  "tracks": [
    { "artist": "Stromae", "title": "Alors on danse", "energy": 5, "vibe": "warmup" },
    { "track_id": 228364626, "artist": "Burna Boy", "title": "Last Last", "energy": 8, "vibe": "peak" }
  ]
}
```

Each track needs EITHER `track_id` (pins the exact Tidal track — recommended) OR both `artist` and `title` (script searches Tidal and picks the best match). `energy` / `vibe` are optional metadata for your own curation; the script preserves track order exactly.

The script:
- creates a fresh playlist on your account
- resolves each track (ID lookup or search)
- adds in batches of 20, refreshing the playlist's etag between batches (Tidal's API uses an `If-Match` header that advances after every successful add — without refreshing, batches 3+ fail with `412 Precondition Failed`)
- reports tracks actually added vs found vs not-found

See [`tracks.example.json`](tracks.example.json).

## Expand seeds into candidates

```sh
python expand_seeds.py seeds.json -o candidates.json
```

`seeds.json` schema:

```json
{
  "seeds": [
    { "artist": "Burna Boy", "title": "Last Last" },
    { "artist": "Stromae", "title": "Alors on danse" }
  ],
  "moods": ["afrobeats running", "global pop party"],
  "playlists_per_mood": 8,
  "tracks_per_playlist": 50,
  "top_n": 150
}
```

Combines two signals:
- **Layer A — track radio.** For each seed, pulls Tidal's algorithmic "tracks similar to this one" (~100 candidates each).
- **Layer B — public playlist co-occurrence.** For each mood keyword, searches public playlists and tallies which tracks appear most often across the results.

Output is a ranked candidate pool (`score = radio_count + 1.5 × playlist_count`) you can hand-curate (or feed to an LLM) and turn into a `tracks.json` for the playlist builder.

See [`seeds.example.json`](seeds.example.json).

## Notes & caveats

- **Track availability is regional.** A track found by search/ID may still throw an `S6001` playback error in your Tidal market. Worth spot-checking before a real event.
- **Search is best-effort.** When pinning matters, prefer `track_id`. The bundled search heuristic prefers exact artist+title substring matches but falls back to the first result, which can grab karaoke/instrumental versions for ambiguous queries.
- **No BPM data.** `tidalapi` doesn't expose BPM reliably. If you want tempo metadata for DJ-style pre-sequencing, populate it from a third-party source (e.g. [getsongbpm.com](https://getsongbpm.com)) or let djay Pro / Serato analyze on import.

## License

MIT
