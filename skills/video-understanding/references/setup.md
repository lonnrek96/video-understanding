# Setup and portability

Requires Python 3.10+ and FFmpeg (`ffmpeg`, `ffprobe`) on PATH. Use current upstream releases. FFmpeg installation: https://ffmpeg.org/download.html . macOS: `brew install ffmpeg`; Ubuntu/Debian: `sudo apt install ffmpeg`; Windows: install an upstream-linked build and put its bin directory on PATH.

Create an isolated environment outside the distributable folder:

```sh
python3 -m venv ~/.local/share/video-understanding/venv
~/.local/share/video-understanding/venv/bin/python -m pip install -U "yt-dlp[default]" openai-whisper "Pillow>=10"
```

Set `VIDEO_PYTHON="$HOME/.local/share/video-understanding/venv/bin/python"` and use `"$VIDEO_PYTHON"` for the script. On Windows use a user-chosen venv and its `Scripts/python.exe`. Installation requires internet/disk space; Whisper depends on PyTorch. On CPU the default `base` model is slower than cloud inference; `--model tiny` is faster but less accurate, `small` is more accurate and heavier. Models download locally on first use. Do not set API keys: there are no paid inference API calls. User AI platform quotas still apply to interpreting frames. A text-only host cannot perform visual interpretation.

For Linux/Windows machines doing CPU-only transcription, install the CPU build of PyTorch into that venv before installing Whisper. Use the command for your OS/Python from the [official PyTorch selector](https://pytorch.org/get-started/locally/) (CPU wheel index: `https://download.pytorch.org/whl/cpu`). A generic PyTorch installation can otherwise download large CUDA dependencies that this CPU-only helper does not use. macOS uses its normal supported PyTorch build. Keep this choice local to the venv; do not replace a project's existing GPU environment.

Upstream sources:
- yt-dlp: https://github.com/yt-dlp/yt-dlp (community downloader, not a YouTube official API). For YouTube install Deno 2.3+ or Node 22+ on PATH; the helper enables both and uses the bundled yt-dlp-ejs package from yt-dlp[default]. Some sites may still reject automated retrieval. Follow upstream documentation on real failures; do not promise universal support.
- FFmpeg: https://ffmpeg.org/
- Whisper: https://github.com/openai/whisper (official open-source local model, not a paid API).

`--language` prefers matching manual captions, then matching automatic captions, then original-language captions, then other available captions. Review `transcript_source` rather than assuming it matches the spoken language. Automatic platform captions and Whisper can contain errors. Burned-in captions are visible only in frames; no automatic OCR is bundled. Remote live streams and playlists are rejected. Local HTTP/HTTPS media URLs supported by yt-dlp are accepted; users must have permission to access them. URL retrieval runs on the user's machine: do not feed untrusted intranet addresses to a shared hosted service.

## Sharing/installing

Copy this entire skill directory as `video-understanding` into the agent's skills directory (Codex: `~/.codex/skills/video-understanding`; Claude Code: `~/.claude/skills/video-understanding`). Start a new session if needed. Other hosts must support skill instructions, local command execution and local image viewing; compatibility must be tested per host.

Share only skill instructions/scripts/license, not downloaded videos, model caches, transcripts, cookies or local run output. Dependencies retain their own licenses; the skill does not redistribute their binaries or weights.

## Inspection, progress and recovery

`prepare_video.py URL --inspect` prints title, chapters, duration, selected video height, whether the default time limit is exceeded, and the suggested `--max-duration`. It does not download media or transcribe audio. Metadata discovery still contacts the source site.

A normal run emits concise stage messages on stderr and a final JSON summary on stdout. Captions/ASR and visuals run independently; the transcript is saved as soon as complete. `run.json` checkpoints bind the input/options to artifact hashes. Retry the same command with `--resume`; changing source, subtitle, ASR or sampling options requires a new output directory. Missing/changed completed artifacts are rejected rather than silently reused. Old schema-v1 output has no resumable checkpoints and must not be relabeled as a new run.

An active `.prepare.lock` prevents concurrent writers. A hard-killed process can leave a stale lock: verify its recorded PID has stopped before moving that lock aside. Never remove another active run's lock. Interrupted uncheckpointed download files are handled by yt-dlp's normal resume; verified stages are reused.

Chapter anchors (up to 60) supplement interval frames even with `--max-scenes 0`; scene detection analyzes downscaled 1 fps images. Overview sheets group consecutive near-similar frames while retaining every original image and timestamp. Similarity is a navigation aid, not evidence that text or actions are identical. Pillow is required for overview generation.
