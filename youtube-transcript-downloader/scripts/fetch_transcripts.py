#!/usr/bin/env python3
"""Download the transcript of the most recent video from each YouTube channel
in a YAML channel list, saving one Markdown file per video into a folder
named for today's date.

Usage:
    python fetch_transcripts.py --channels channels.yaml --output ./transcripts
"""

import argparse
import datetime
import re
import sys
import tempfile
from pathlib import Path

import yaml
from yt_dlp import YoutubeDL

SUBTITLE_LANGS = ["en", "en-US", "en-orig"]


def normalize_channel_url(entry: str) -> str:
    entry = entry.strip().strip('"').strip("'")
    if entry.startswith("http://") or entry.startswith("https://"):
        return entry
    handle = entry if entry.startswith("@") else f"@{entry}"
    return f"https://www.youtube.com/{handle}"


def load_channels(channels_path: Path) -> list:
    with open(channels_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries = data.get("channels", [])
    if not isinstance(entries, list):
        raise ValueError(f"'channels' must be a YAML list, got {type(entries).__name__}: {entries!r}")
    if not entries:
        raise ValueError(f"No channels found in {channels_path}")
    return entries


def get_most_recent_video_url(channel_url: str) -> str:
    videos_url = channel_url.rstrip("/") + "/videos"
    opts = {
        "extract_flat": True,
        "playlistend": 1,
        "quiet": True,
        "no_warnings": True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(videos_url, download=False)
    entries = info.get("entries") or []
    if not entries:
        raise RuntimeError(f"No videos found for channel {channel_url}")
    video_id = entries[0]["id"]
    return f"https://www.youtube.com/watch?v={video_id}"


def sanitize(name: str, max_len: int = 80) -> str:
    name = re.sub(r"[^\w\-. ]", "", name).strip().replace(" ", "-")
    return name[:max_len] or "untitled"


def vtt_to_text(vtt_path: Path) -> str:
    lines = vtt_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out = []
    for line in lines:
        line = line.strip()
        if not line or line == "WEBVTT":
            continue
        if "-->" in line or re.match(r"^\d+$", line) or line.startswith(("Kind:", "Language:")):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        # Rolling auto-captions repeat the same line across consecutive cues;
        # only collapse those adjacent repeats, not genuine repeated dialogue.
        if line and (not out or out[-1] != line):
            out.append(line)
    return "\n".join(out)


def select_vtt_file(tmpdir: Path, video_id: str, preferred_langs: list[str]) -> Path | None:
    for lang in preferred_langs:
        candidate = tmpdir / f"{video_id}.{lang}.vtt"
        if candidate.exists():
            return candidate
    remaining = sorted(tmpdir.glob(f"{video_id}*.vtt"))
    return remaining[0] if remaining else None


def fetch_video_and_transcript(video_url: str, tmpdir: Path) -> tuple[dict, str]:
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
        "subtitleslangs": SUBTITLE_LANGS,
        "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=True)

    vtt_file = select_vtt_file(tmpdir, info["id"], SUBTITLE_LANGS)
    if vtt_file is None:
        raise RuntimeError("no captions available")

    transcript = vtt_to_text(vtt_file)
    if not transcript.strip():
        raise RuntimeError("captions file was empty")

    return info, transcript


def build_markdown(info: dict, transcript: str, download_date: str) -> str:
    title = info.get("title", "Untitled")
    channel = info.get("uploader") or info.get("channel") or info.get("uploader_id") or "Unknown channel"
    url = info.get("webpage_url", "")
    upload_date_raw = info.get("upload_date", "")
    if upload_date_raw and len(upload_date_raw) == 8:
        uploaded = f"{upload_date_raw[:4]}-{upload_date_raw[4:6]}-{upload_date_raw[6:]}"
    else:
        uploaded = upload_date_raw or "unknown"

    return (
        f"# {title}\n\n"
        f"- **Channel:** {channel}\n"
        f"- **Video URL:** {url}\n"
        f"- **Uploaded:** {uploaded}\n"
        f"- **Downloaded:** {download_date}\n\n"
        f"---\n\n"
        f"{transcript}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", default="channels.yaml", help="Path to YAML channel list (default: ./channels.yaml)")
    parser.add_argument("--output", required=True, help="Base output folder")
    args = parser.parse_args()

    channels_path = Path(args.channels)
    if not channels_path.exists():
        print(f"Channel list not found: {channels_path}", file=sys.stderr)
        return 1

    try:
        channel_urls = load_channels(channels_path)
    except Exception as e:
        print(f"Failed to load channel list: {e}", file=sys.stderr)
        return 1

    download_date = datetime.date.today().isoformat()
    output_dir = Path(args.output) / download_date
    output_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    results = []

    for raw_entry in channel_urls:
        channel_url = None
        try:
            channel_url = normalize_channel_url(raw_entry)
            video_url = get_most_recent_video_url(channel_url)
            with tempfile.TemporaryDirectory() as tmpdir:
                info, transcript = fetch_video_and_transcript(video_url, Path(tmpdir))

            md = build_markdown(info, transcript, download_date)
            channel_name = sanitize(info.get("uploader") or info.get("channel") or info.get("uploader_id") or channel_url)
            title = sanitize(info.get("title", "untitled"))
            out_path = output_dir / f"{channel_name}_{title}.md"
            out_path.write_text(md, encoding="utf-8")

            results.append((channel_url, "ok", str(out_path)))
            ok_count += 1
        except Exception as e:
            label = channel_url or raw_entry
            status = "skipped: no captions" if "captions" in str(e) else "error"
            results.append((label, status, str(e)))

    print(f"\nSaved transcripts to: {output_dir}\n")
    for channel_url, status, detail in results:
        print(f"[{status}] {channel_url} -> {detail}")
    print(f"\n{ok_count}/{len(channel_urls)} channels succeeded.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
