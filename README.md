# tidal-playlist-builder

Build curated Tidal playlists from a JSON track list, and expand a small set of seed tracks into a ranked candidate pool using Tidal's track radio + public playlist co-occurrence.

Designed to pair well with an LLM curator: the LLM picks tracks (with optional `energy` / `vibe` metadata for DJ-style sequencing), and these scripts handle the Tidal API plumbing.

> ⚠️ Uses the unofficial [`tidalapi`](https://github.com/tamland/python-tidal) library, which talks to Tidal's internal endpoints. Tidal doesn't publish a public developer API. Behaviour can change without warning if Tidal updates their backend, and use is technically against Tidal's Terms of Service (though `tidalapi` has been used widely for years without enforcement against individual users). At your own risk.

## Quickstart (no coding experience needed)

If you've never used a terminal before, here's the full path from "I have an idea for a playlist" to "the playlist is on my Tidal account" — roughly 15 minutes the first time.

### 1. Install Python (one-time setup)

This needs Python 3.10 or newer — a free programming language runtime.

- **Mac**: download the installer from [python.org/downloads](https://www.python.org/downloads/) and run it.
- **Windows**: download from [python.org/downloads](https://www.python.org/downloads/). **Tick "Add Python to PATH"** on the first installer screen.
- **Already installed?** Open Terminal (Mac) / Command Prompt (Windows) and type `python3 --version`. If it shows `3.10` or higher, you're set.

### 2. Download this code

Click the green **Code** button at the top of this GitHub page → **Download ZIP**. Unzip it somewhere you'll remember (e.g. your Desktop).

_Note_: if you're non-technical, please don't trust random code you download from GitHub. I put these instructions here in case you want to try this tool, but in general, you should only download random code if you can also read it. At a minimum, copy and paste the URL of this repo into your AI Chat (https://github.com/crystallized-lu/tidal-playlist-builder) and ask it to analyze the contents here for safety before you put it on your computer.

### 3. Open a terminal inside the folder

- **Mac**: open Terminal, type `cd ` (with the trailing space), then drag the unzipped folder into the Terminal window — it'll auto-fill the path. Press enter.
- **Windows**: open the unzipped folder in File Explorer, click the address bar, type `cmd`, press enter.

### 4. Install the dependencies (one-time)

In the terminal, type:

```sh
pip install -r requirements.txt
```

If that errors, try `pip3` instead of `pip`.

### 5. Use an AI chat to write your playlist file

Open [Mistral](https://chat.mistral.ai) (French sovereign), [ChatGPT](https://chat.openai.com) (American), or [Claude](https://claude.ai) (American), and paste the prompt below — fill in the bracketed parts with your own details:

> I want to build a Tidal playlist for **[describe the event — e.g. a 4-hour charity run, a wedding cocktail hour, a dinner party]**. The vibe should be **[describe — e.g. uplifting, family-friendly, mostly Afrobeats and global pop]**. Please give me **[number]** tracks, sequenced as a DJ set with a warmup → build → peak → cooldown energy curve.
>
> Only suggest tracks you're confident actually exist (real artists, real song titles). For each track give me: artist, title, energy (1–10), and vibe (one of: warmup, build, peak, sustain, cooldown).
>
> Output ONLY valid JSON, no commentary, in this exact format:
> ```
> {
>   "name": "Playlist name here",
>   "description": "Optional description",
>   "tracks": [
>     {"artist": "...", "title": "...", "energy": 5, "vibe": "warmup"}
>   ]
> }
> ```

Copy the JSON output. Open TextEdit (Mac) or Notepad (Windows), paste, and save it as `tracks.json` **inside the folder you unzipped**.

> ⚠️ If the AI wraps the JSON in code-fence markers (` ```json ` and ` ``` `), copy **only the lines between** those markers — not the markers themselves.

### 6. Build the playlist

In the terminal, type:

```sh
python3 tidal_playlist.py tracks.json
```

The first time you run it, a Tidal URL will appear. Open it in your browser, log into Tidal, and approve. The script will continue automatically and create the playlist on your Tidal account.

### Done

Open Tidal — your playlist is in **My Collection → Playlists**. To make a different playlist later, repeat steps 5 and 6 only.

---

## Install

Requires **Python 3.10+** (uses PEP 604 `X | None` union syntax).

```sh
pip install -r requirements.txt
```

## Authenticate

All scripts share an OAuth session cached at:

```
$XDG_CONFIG_HOME/tidal-playlist-builder/session.json
(or ~/.config/tidal-playlist-builder/session.json)
```

Override the location with `TIDAL_PLAYLIST_BUILDER_SESSION=/path/to/session.json`. The file is created with `0600` permissions so other users on the machine can't read your refresh token.

On first run, you'll get a URL to open in your browser to approve the device-flow login. After that, subsequent runs are silent until the session expires.

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
- creates a **fresh, private playlist on your authenticated Tidal account** (visible in your Tidal app under "My Collection → Playlists")
- resolves each track (ID lookup or search)
- adds in batches of 20, refreshing the playlist's etag between batches (Tidal's API uses an `If-Match` header that advances after every successful add — without refreshing, batches 3+ fail with `412 Precondition Failed`)
- reports tracks actually added vs found vs not-found

In the per-track output:
- ✅ — track found via exact ID lookup, or search returned a strict artist+title match
- ⚠️ — search fell back to the first result because no strict match existed (worth verifying — see "Notes & caveats")
- ❌ — track could not be found

See [`tracks.example.json`](tracks.example.json).

## Pool tracks from known playlists

```sh
python fetch_playlists.py URL1 URL2 URL3 ... -o candidates.json
```

Use this when you already trust specific source playlists for a theme (e.g. someone else's well-curated mood/genre playlists) and want to pool their tracks for further curation, rather than relying on search-based discovery.

URLs can be `https://tidal.com/playlist/<uuid>`, `https://tidal.com/browse/playlist/<uuid>`, or bare UUIDs. Any number of playlists is supported.

Output is a deduped pool sorted by `source_count` descending — tracks appearing in multiple source playlists float to the top, which is a strong signal they belong in your final set. Each candidate has `track_id`, `artist`, `title`, the list of `sources` it came from, and `source_count`.

Typical follow-up: hand-curate (or hand to an LLM) → produce a `tracks.json` for the playlist builder, pinning the chosen tracks by `track_id`.

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

## End-to-end example

A typical run looks like this:

```sh
# 1. Pool tracks from playlists you trust as source material for the theme.
python fetch_playlists.py \
  https://tidal.com/playlist/aaaaaaaa-1111-2222-3333-444444444444 \
  https://tidal.com/playlist/bbbbbbbb-5555-6666-7777-888888888888 \
  -o candidates.json

# 2. Hand-curate (or paste candidates.json into an LLM and ask it to pick
#    ~80 tracks, assign each an `energy` 1–10 and a `vibe` like
#    warmup/build/peak/cooldown, and order them as a DJ set).
#    Save the result as tracks.json — pin tracks by `track_id` to avoid
#    search ambiguity.

# 3. Build the Tidal playlist from your curated list.
python tidal_playlist.py tracks.json
```

The `expand_seeds.py` workflow is an alternative to step 1 when you don't have specific source playlists in mind — give it a few seed tracks and mood keywords, and it builds the candidate pool from Tidal's recommendation engine instead.

## Notes & caveats

- **Track availability is regional.** A track found by search/ID may still throw an `S6001` playback error in your Tidal market. Worth spot-checking before a real event.
- **Search is best-effort.** When pinning matters, prefer `track_id`. The bundled search heuristic prefers exact artist+title substring matches but falls back to the first result, which can grab karaoke/instrumental versions for ambiguous queries.
- **No BPM data.** `tidalapi` doesn't expose BPM reliably. The optional `energy` and `vibe` fields are the intended substitute — assign them when curating the list and use them to hand-arrange the track order.
- **What the LLM actually knows.** When an LLM assigns `energy` and `vibe`, it's drawing on *textual* knowledge of the songs from its training data (reviews, articles, descriptions) — not audio analysis. This works well for mainstream tracks anyone on the internet has written about, but is unreliable for niche / non-English catalog, deep cuts, or releases past the model's training cutoff. Spot-check the curation for tracks the LLM might not actually know, and treat the exact `energy` number as directional rather than precise.

## Going further: DJ-style transitions

For real beatmatched / key-matched mixing rather than Tidal's basic crossfade, you'll need a DJ app. Notes:

- **djay Pro, Serato DJ Pro, rekordbox** all integrate with Tidal but require Tidal's **DJ Extension** add-on, only available on certain Tidal tiers/regions. They analyze BPM, key and beatgrid automatically on import.
- **VirtualDJ** is free, also integrates with Tidal via the same DJ Extension, and is the lowest-cost path if your Tidal tier supports it.
- **Mixxx** is fully free and open source but does NOT support Tidal streaming directly — you'd need local copies of the tracks (iTunes / Bandcamp / Beatport).

A natural next iteration of this project would be an exporter that emits a track list in a format another DJ app can ingest (e.g. M3U8, Rekordbox XML), so the playlist built here can flow into a real DJ environment.

## License

MIT
