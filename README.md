# Soulseek Auto Tool

A command-line tool that takes a public **SoundCloud playlist**, cleans up each track's name into a
Soulseek-friendly search, lets you **accept or edit every search term**, and then searches them on
**Soulseek** one at a time, 3 to 4.5 seconds apart, so you don't hammer the network.

It produces a ranked Markdown report of the best matches for each track. It does not download anything.

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
5. **Rank**: results are scored on format and bitrate, free upload slot, queue length, speed, filename match, and
   duration match against the SoundCloud track.

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
```

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

Options: `--no-ai`, `--min-delay`, `--max-delay`, `--data-dir`, `--output-dir`.

Run the same command again to resume an interrupted session. The report is written to `output/`.

## Development

```bash
pytest
```

Tests cover title parsing, ranking, request pacing, the review prompt, and the slskd client (against a mocked API),
and run in CI on every push.

## Roadmap

- Optional auto-download of the top match through slskd
- Multiple playlists with de-duplication
- Local web UI for the review step

## Disclaimer

This tool only searches. Make sure that whatever you download is something you have the right to obtain, and follow
the terms of SoundCloud, Soulseek and your local laws. Use the pacing defaults to stay a good citizen on the network.

## License

MIT
