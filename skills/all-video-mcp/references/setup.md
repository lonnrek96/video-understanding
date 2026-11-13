# Setup and portability

Requires Python 3.10+ and FFmpeg (`ffmpeg`, `ffprobe`) on PATH. Use current upstream releases. FFmpeg installation: https://ffmpeg.org/download.html . macOS: `brew install ffmpeg`; Ubuntu/Debian: `sudo apt install ffmpeg`; Windows: install an upstream-linked build and put its bin directory on PATH.

Create an isolated environment outside the distributable folder:

```sh
python3 -m venv ~/.local/share/all-video-mcp/venv
~/.local/share/all-video-mcp/venv/bin/python -m pip install -U "yt-dlp[default]" openai-whisper
```

Set `VIDEO_PYTHON="$HOME/.local/share/all-video-mcp/venv/bin/python"` and use `"$VIDEO_PYTHON"` for the script. On Windows use a user-chosen venv and its `Scripts/python.exe`. Installation requires internet/disk space; Whisper depends on PyTorch. On CPU the default `base` model is slower than cloud inference; `--model tiny` is faster but less accurate, `small` is more accurate and heavier. Models download locally on first use. Do not set API keys: there are no paid inference API calls. User AI platform quotas still apply to interpreting frames. A text-only host cannot perform visual interpretation.

Upstream sources:
- yt-dlp: https://github.com/yt-dlp/yt-dlp (community downloader, not a YouTube official API). For YouTube install Deno 2.3+ or Node 22+ on PATH; the helper enables both and uses the bundled yt-dlp-ejs package from yt-dlp[default]. Some sites may still reject automated retrieval. Follow upstream documentation on real failures; do not promise universal support.
- FFmpeg: https://ffmpeg.org/
- Whisper: https://github.com/openai/whisper (official open-source local model, not a paid API).

`--language` prefers matching manual captions, then matching automatic captions, then original-language captions, then other available captions. Review `transcript_source` rather than assuming it matches the spoken language. Automatic platform captions and Whisper can contain errors. Burned-in captions are visible only in frames; no automatic OCR is bundled. Remote live streams and playlists are rejected. Local HTTP/HTTPS media URLs supported by yt-dlp are accepted; users must have permission to access them. URL retrieval runs on the user's machine: do not feed untrusted intranet addresses to a shared hosted service.

## Sharing/installing

Copy this entire skill directory as `all-video-mcp` into the agent's skills directory (Codex: `~/.codex/skills/all-video-mcp`; Claude Code: `~/.claude/skills/all-video-mcp`). Start a new session if needed. Other hosts must support skill instructions, local command execution and local image viewing; compatibility must be tested per host.

Share only skill instructions/scripts/license, not downloaded videos, model caches, transcripts, cookies or local run output. Dependencies retain their own licenses; the skill does not redistribute their binaries or weights.
