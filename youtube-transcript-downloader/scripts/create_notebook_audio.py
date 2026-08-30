#!/usr/bin/env python3
"""Second-stage pipeline step: take a folder of transcript Markdown files
(the dated output folder produced by fetch_transcripts.py), create a new
Gemini Notebook (NotebookLM) notebook via the `nlm` CLI, add each transcript
as a source, and kick off a Studio Audio Overview.

Requires the `notebooklm-mcp-cli` package (the `nlm` command) to be
installed and already authenticated (`nlm login`) before this script runs.

Usage:
    python create_notebook_audio.py --transcripts-dir ./transcripts/2026-08-29
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

AUDIO_LENGTHS = {"short", "default", "long"}
POLL_INTERVAL_SECONDS = 20
DEFAULT_MAX_WAIT_SECONDS = 600
NLM_COMMAND_TIMEOUT_SECONDS = 300


def run_nlm(args: list[str], profile: str | None = None) -> dict:
    cmd = ["nlm", *args, "--json"]
    if profile:
        cmd += ["--profile", profile]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=NLM_COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"`{' '.join(cmd)}` timed out after {NLM_COMMAND_TIMEOUT_SECONDS}s") from e
    if result.returncode != 0:
        raise RuntimeError(f"`{' '.join(cmd)}` failed: {result.stderr.strip() or result.stdout.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"`{' '.join(cmd)}` returned non-JSON output: {result.stdout!r}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"`{' '.join(cmd)}` returned unexpected JSON shape: {data!r}")
    return data


def create_notebook(title: str, profile: str | None) -> str:
    data = run_nlm(["notebook", "create", title], profile=profile)
    notebook_id = data.get("id") or data.get("notebook_id")
    if not notebook_id:
        raise RuntimeError(f"Could not find notebook id in response: {data}")
    return notebook_id


def add_source(notebook_id: str, file_path: Path, profile: str | None) -> None:
    run_nlm(["source", "add", notebook_id, "--file", str(file_path), "--wait"], profile=profile)


def create_audio_overview(notebook_id: str, length: str, language: str, profile: str | None) -> str:
    data = run_nlm(
        ["audio", "create", notebook_id, "--length", length, "--language", language, "--confirm"],
        profile=profile,
    )
    artifact_id = data.get("artifact_id") or data.get("id")
    if not artifact_id:
        raise RuntimeError(f"Could not find artifact id in response: {data}")
    return artifact_id


def poll_audio_status(notebook_id: str, artifact_id: str, max_wait: int, profile: str | None) -> str:
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        data = run_nlm(
            ["studio", "status", notebook_id, "--artifact-id", artifact_id],
            profile=profile,
        )
        status = data.get("status", "unknown")
        if status in ("completed", "failed"):
            return status
        time.sleep(POLL_INTERVAL_SECONDS)
    return "timed_out"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcripts-dir", required=True, help="Dated folder of transcript .md files from fetch_transcripts.py")
    parser.add_argument("--notebook-title", default=None, help="Notebook title (default: 'YouTube Transcripts - <folder name>')")
    parser.add_argument("--audio-length", default="default", choices=sorted(AUDIO_LENGTHS), help="Audio overview length: short, default (medium), or long")
    parser.add_argument("--language", default="en", help="BCP-47 language code for the audio overview (default: en)")
    parser.add_argument("--no-wait", action="store_true", help="Don't poll for audio generation to finish; just kick it off")
    parser.add_argument("--max-wait", type=int, default=DEFAULT_MAX_WAIT_SECONDS, help="Max seconds to poll for audio completion (default: 600)")
    parser.add_argument("--profile", default=None, help="nlm login profile to use")
    args = parser.parse_args()

    if shutil.which("nlm") is None:
        print(
            "The `nlm` CLI was not found. Install it with `pip install notebooklm-mcp-cli` "
            "(or `uv tool install notebooklm-mcp-cli`) and authenticate with `nlm login` before running this script.",
            file=sys.stderr,
        )
        return 1

    transcripts_dir = Path(args.transcripts_dir)
    if not transcripts_dir.is_dir():
        print(f"Transcripts folder not found: {transcripts_dir}", file=sys.stderr)
        return 1

    md_files = sorted(transcripts_dir.glob("*.md"))
    if not md_files:
        print(f"No .md transcript files found in {transcripts_dir}", file=sys.stderr)
        return 1

    title = args.notebook_title or f"YouTube Transcripts - {transcripts_dir.name}"

    try:
        notebook_id = create_notebook(title, args.profile)
    except RuntimeError as e:
        print(f"Failed to create notebook: {e}", file=sys.stderr)
        return 1
    print(f"Created notebook '{title}' ({notebook_id})")

    added, failed = 0, 0
    for md_file in md_files:
        try:
            add_source(notebook_id, md_file, args.profile)
            added += 1
            print(f"[ok] added source: {md_file.name}")
        except RuntimeError as e:
            failed += 1
            print(f"[error] {md_file.name}: {e}", file=sys.stderr)

    if added == 0:
        print("No sources were added successfully; skipping audio overview.", file=sys.stderr)
        return 1

    try:
        artifact_id = create_audio_overview(notebook_id, args.audio_length, args.language, args.profile)
    except RuntimeError as e:
        print(f"Failed to start audio overview: {e}", file=sys.stderr)
        return 1
    print(f"Started audio overview (artifact {artifact_id}, length={args.audio_length}, language={args.language})")

    if args.no_wait:
        print(f"Not waiting for completion. Check status with: nlm studio status {notebook_id} --artifact-id {artifact_id}")
        return 0

    status = poll_audio_status(notebook_id, artifact_id, args.max_wait, args.profile)
    print(f"Audio overview status: {status}")
    if status == "completed":
        print(f"Download with: nlm download audio {notebook_id} {artifact_id} --output overview.mp3")
    elif status == "timed_out":
        print(f"Still generating after {args.max_wait}s. Check later with: nlm studio status {notebook_id} --artifact-id {artifact_id}")

    print(f"\nNotebook: {notebook_id} ({added} source(s) added, {failed} failed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
