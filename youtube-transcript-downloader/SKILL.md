---
name: youtube-transcript-downloader
description: Downloads the transcript of the most recent video from each channel in a user-supplied list of YouTube channels, saving one Markdown file per video into a folder named for today's date, then creates a Gemini Notebook (NotebookLM) notebook from those transcripts and generates a Studio Audio Overview. Use when the user wants to archive, batch-download, or keep an updated local copy of transcripts from a set of YouTube channels they follow, and/or wants those transcripts turned into a notebook and podcast-style audio overview.
---

# YouTube Transcript Downloader

Two-stage pipeline, run as two separate processes:

1. **Download transcripts** — given a list of YouTube channels, downloads the transcript of the **single most recently uploaded video** from each channel and saves it as a Markdown file into a subfolder named for today's date, under a base output folder the user chooses.
2. **Create notebook + audio overview** — takes that day's folder of transcripts, creates a new Gemini Notebook (NotebookLM) notebook, adds every transcript as a source, and starts a Studio Audio Overview.

Re-running stage 1 later the same day overwrites that day's files; running on a new day creates a new dated subfolder, so historical days are preserved. Stage 2 always creates a fresh notebook, so re-running it for the same day creates a second notebook — invoke it once per day's download.

## Setup

### Stage 1: transcript download

Needs `yt-dlp`. If it isn't already installed, install it before running the script:

```
pip install -U yt-dlp
```

No YouTube Data API key or other credentials are required — `yt-dlp` reads public channel and caption data directly.

### Stage 2: notebook + audio overview

Needs the `nlm` CLI from [`notebooklm-mcp-cli`](https://github.com/jacob-bd/notebooklm-mcp-cli):

```
pip install notebooklm-mcp-cli
```

Then authenticate **once**, interactively, before running the pipeline unattended — this launches a browser to extract Google session cookies, which are cached (~2-4 weeks) and auto-refreshed after that:

```
nlm login
```

`nlm login --check` confirms whether a session is already authenticated. Stage 2 will fail with a clear error if `nlm` isn't installed or isn't authenticated — it cannot complete the browser login step on its own.

## Channel list format

Maintain a YAML file listing the channels to check, one per entry. Full channel URLs or `@handle` shorthand both work:

```yaml
channels:
  - https://www.youtube.com/@channelhandle
  - "@anotherchannel"
  - https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx
```

This file is the user's own data, not part of the skill package — keep it wherever is convenient (e.g. alongside the output folder) and pass its path with `--channels`. If `--channels` is omitted, the script looks for `./channels.yaml` in the current directory.

## Usage

Run stage 1, then stage 2 against the dated folder stage 1 just created:

```
python scripts/fetch_transcripts.py --channels <path/to/channels.yaml> --output <path/to/output/base/folder>
python scripts/create_notebook_audio.py --transcripts-dir <path/to/output/base/folder>/<YYYY-MM-DD>
```

### Stage 1: `fetch_transcripts.py`

- `--channels PATH` — path to the YAML channel list (default: `./channels.yaml`)
- `--output PATH` — base folder under which today's dated subfolder is created (required)

### Stage 2: `create_notebook_audio.py`

- `--transcripts-dir PATH` — the dated folder of `.md` transcripts produced by stage 1 (required)
- `--notebook-title TEXT` — notebook title (default: `YouTube Transcripts - <folder name>`)
- `--audio-length {short,default,long}` — Studio Audio Overview length; **`default` is the medium/standard length** — `nlm`'s CLI has no literal "medium" option, so `default` is what "medium" maps to (default: `default`)
- `--language CODE` — BCP-47 language code for the audio overview (default: `en` for English)
- `--no-wait` — kick off audio generation and return immediately instead of polling for completion (generation normally takes 1-5 minutes)
- `--max-wait SECONDS` — max time to poll for completion when waiting (default: 600)
- `--profile NAME` — `nlm` login profile to use, if not the default

It creates one notebook, adds every `.md` file in the folder as a source (`nlm source add ... --file ... --wait`), starts the audio overview (`nlm audio create ... --length default --language en --confirm`), and — unless `--no-wait` is passed — polls `nlm studio status` until the overview completes, fails, or the wait times out, printing the notebook ID and (once ready) the download command.

## Output layout

```
<output>/
└── 2026-08-25/
    ├── ChannelOne_Video-Title-Here.md
    ├── ChannelTwo_Another-Video-Title.md
    └── ...
```

Each Markdown file has a metadata header followed by the transcript body:

```markdown
# <video title>

- **Channel:** <channel name>
- **Video URL:** <url>
- **Uploaded:** <upload date>
- **Downloaded:** <today's date>

---

<transcript text>
```

Filenames are derived from the channel name and video title with filesystem-unsafe characters stripped.

## Behavior notes

- **Most recent video**: for each channel, the script lists the channel's uploads (newest first) and takes only the first one — it does not download every video, and it does not walk back through a channel's history.
- **Missing transcripts**: if a video has no captions (manual or auto-generated) available, that channel is skipped for the run with a warning printed to the console; the script continues on to the remaining channels rather than stopping.
- **Bad channel entries**: an unresolvable channel URL/handle is logged as an error and skipped; it does not abort the rest of the run.
- **Re-running the same day**: output filenames are deterministic per channel/video, so re-running simply overwrites that day's file with the same content (or a new file if the channel has since posted a newer video).
- **Summary**: at the end of a run, the script prints one line per channel (`ok` / `skipped: no captions` / `error: ...`) plus a final success count.
- **Failed source uploads (stage 2)**: if adding one transcript as a source fails, that file is skipped and logged; the notebook is still created and the audio overview still runs against whichever sources succeeded, as long as at least one did.
- **No sources added (stage 2)**: if every source upload fails, the script stops before starting the audio overview (an overview needs at least one source) and exits with an error.
