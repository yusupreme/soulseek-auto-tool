# Soulseek Auto Tool

A command-line tool that takes a public **SoundCloud playlist**, cleans up each track's name into a
Soulseek-friendly search, lets you **accept or edit every search term**, and then searches them on
**Soulseek** one at a time, 3 to 4.5 seconds apart, so you don't hammer the network.

It produces a ranked Markdown report of the best matches for each track, and can optionally download your picks into
a folder named after the playlist.

## How it works

```
SoundCloud playlist ──yt-dlp──▶ track titles ──Claude (or regex)──▶ "Artist Title"
        ──you accept / edit / skip──▶ paced searches via slskd ──▶ ranked report
```

1. **Fetch**: [yt-dlp](https://github.com/yt-dlp/yt-dlp) reads the playlist metadata (no audio is downloaded).
2. **Parse**: Claude turns messy titles like `DJ X - Song (Remix) [FREE DL] 🔥` into artist + title in one batch
   call. Without an API key, or if the call fails, a regex cleaner is used instead.
3. **Review**: you press Enter to accept, type to replace, `s` to skip, `a` to accept the rest, or `q` to save and quit.
   Low-confidence guesses are flagged.
4. **Search**: queries go to [slskd](https://github.com/slskd/slskd) (a Soulseek client with a REST API) with a
   random 3 to 4.5 second gap between them.
5. **Rank**: only **320 kbps MP3s** whose file names match the search are kept (FLAC, lower bitrates and files with an
   unknown bitrate are ignored). They are sorted by **largest file size**; a free upload slot and a short queue only
   break ties. The rules live in `src/soulseek_auto_tool/ranking.py`.

Progress is saved after every step, so you can stop and resume any time.

## Setup

You need Python 3.10+ and a running slskd instance.

### 1. Install the tool

```bash
git clone https://github.com/yusupreme/soulseek-auto-tool.git
cd soulseek-auto-tool
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Run slskd

A Soulseek account can only be logged in once at a time, so create a **second account** for slskd (any new
username/password works on first login) or close your desktop client while the tool runs.

Download slskd from its [releases page](https://github.com/slskd/slskd/releases) (or use its Docker image) and add this
to its `slskd.yml`:

```yaml
soulseek:
  username: your-second-account
  password: your-password
web:
  authentication:
    api_keys:
      soulseek_auto_tool:
        key: pick-a-long-random-string
        role: readwrite
shares:
  directories:
    - /path/to/your/music   # many Soulseek users won't share with accounts that share nothing
```

Sharing is per account: slskd does not inherit the shares of another Soulseek client, so point it at your music folder.

### 3. Configure the tool

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Required | Purpose |
|---|---|---|
| `SLSKD_API_KEY` | yes | The key you put in `slskd.yml` |
| `SLSKD_URL` | no | Defaults to `http://localhost:5030` |
| `ANTHROPIC_API_KEY` | no | Enables AI title parsing. Without it, regex parsing is used |

`.env` is gitignored. **Never commit real keys.**

## Usage

```bash
slsk-auto "https://soundcloud.com/<user>/sets/<playlist>"
```

Options: `--no-ai`, `--no-auto`, `--auto-tolerance`, `--search-only`, `--retry-empty`, `--min-delay`, `--max-delay`, `--wait`, `--library-dir`, `--data-dir`, `--output-dir`.

Run the same command again to resume an interrupted session. The report is written to `output/`.

**Private playlists:** use the playlist's **Share → private link** (including `on.soundcloud.com/...` short links).
The secret in that link grants access, so treat it like a password and don't commit it.

### Choosing and downloading

**Auto-select.** Before you are asked anything, the tool picks the obvious ones itself. A file is taken automatically
only when all of these hold: every word of the search is in the file name, the file has no version word (remix, edit,
dub, live, extended...) that the SoundCloud title lacks, and its real length is within 3 seconds of the SoundCloud track
(`--auto-tolerance` changes this). Of the files that pass, the largest wins. Snippets and tracks with an unknown length
are never auto-picked. Each auto-pick is printed as it is made and marked `auto` in the log. Use `--no-auto` to
review every track yourself.

Everything else is decided by you. Each remaining track gets a comparison card: the SoundCloud title and
**track length** next to each Soulseek file's length, with the difference colored (green within 3 s, red beyond 10 s),
plus file size, upload slot and the sharing user. Snippet/preview tracks get a note that a longer file is expected.

| Key | Action |
|---|---|
| Enter | take file #1 (the largest 320 kbps MP3) |
| number | pick that file (numbering continues across pages) |
| `m` | show the next 5 results (up to 20 are kept) |
| `e` | edit the search term and search again |
| `s` | skip the track entirely |
| `q` | save and quit; run the same command to continue |

Use `--search-only` to skip this step and just get the report. After the review, downloads are queued and finished files are moved into
`<LIBRARY_DIR>/<playlist name>/`, so each SoundCloud playlist gets its own folder. Existing files are never
overwritten. If some downloads are still queued on other users' machines when `--wait` minutes run out, run the same
command later and they are filed then.

## The log

Every run writes `output/<playlist name>/` with:

- `log.md`: a summary table plus sections for **Downloaded**, **Still queued**, **Download failed**, **Not found**,
  **Skipped by you** and **Not decided yet**.
- `downloaded.csv`: one row per downloaded file, ready for a spreadsheet.
- `tracks.json`: everything the tool knows about every track.

For each downloaded file the tool reads the **real file** (not what the sender claimed) and records its length,
bitrate and CBR/VBR mode, sample rate, channels, size and who it came from, next to the SoundCloud length. Anything
worth a second look is flagged: a bitrate other than 320, VBR, a sample rate other than 44.1 kHz, a length more than
10 s away from SoundCloud (except for snippets), or a sender who reported a different length than the real file has.

For tracks that were **not found**, the log says why: nobody answered, or how many files came back and in which
formats, and whether 320 kbps MP3s were seen but did not match the track name. Failed transfers list the reason.

`--retry-empty` searches again for tracks that found nothing.

## Development

```bash
pytest
```

Tests cover title parsing, ranking, auto-select, request pacing, the review prompt, and the slskd client (against a mocked API),
and run in CI on every push.

## Roadmap

- Multiple playlists with de-duplication
- Local web UI for the review step

## Disclaimer

Make sure that whatever you download is something you have the right to obtain, and follow
the terms of SoundCloud, Soulseek and your local laws. Use the pacing defaults to stay a good citizen on the network.

## License

MIT
