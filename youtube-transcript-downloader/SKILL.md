---
name: youtube-transcript-downloader
description: Downloads the transcript of the most recent video from each channel in a user-supplied list of YouTube channels, saving one Markdown file per video into a folder named for today's date. Use when the user wants to archive, batch-download, or keep an updated local copy of transcripts from a set of YouTube channels they follow.
---

# YouTube Transcript Downloader

Given a list of YouTube channels, downloads the transcript of the **single most recently uploaded video** from each channel and saves it as a Markdown file into a subfolder named for today's date, under a base output folder the user chooses. Re-running later the same day overwrites that day's files; running on a new day creates a new dated subfolder, so historical days are preserved.

## Setup

This skill needs `yt-dlp`. If it isn't already installed, install it before running the script:

```
pip install -U yt-dlp
```

No YouTube Data API key or other credentials are required — `yt-dlp` reads public channel and caption data directly.

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

```
python scripts/fetch_transcripts.py --channels <path/to/channels.yaml> --output <path/to/output/base/folder>
```

- `--channels PATH` — path to the YAML channel list (default: `./channels.yaml`)
- `--output PATH` — base folder under which today's dated subfolder is created (required)

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
