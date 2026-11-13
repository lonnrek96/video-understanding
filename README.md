# All Video MCP

[简体中文](README.zh-CN.md)

An agent skill that helps a vision-capable AI explain videos using **actual frames and timestamped transcripts**. Accepts supported video links and local files. No paid inference API or API key is required.

Despite the name, this is an **agent skill**, not a standalone MCP server. It prepares local evidence; your AI host reads the images and transcript and explains the video. Community project, not an official Google or OpenAI integration.

## What it does

- Downloads accessible videos with yt-dlp, including supported YouTube links.
- Prefers platform subtitles; uses local OpenAI Whisper when usable subtitles are absent.
- Extracts overview and scene-change frames with FFmpeg, aligned with captions.
- Lets the agent inspect extra timestamps for demonstrations, charts, code or unclear moments.
- Guides a chronological explanation, including visual details, examples and uncertainty.

## Install

Requires Python **3.10+**, FFmpeg (`ffmpeg` and `ffprobe`) and a host that can execute local commands **and view local images**. YouTube also requires a supported JavaScript runtime, such as Deno 2.3+ or Node 22+. See [runtime setup](skills/all-video-mcp/references/setup.md).

```sh
git clone https://github.com/lonnrek96/all-video-mcp.git
cd all-video-mcp
python3 -m venv "$HOME/.local/share/all-video-mcp/venv"
"$HOME/.local/share/all-video-mcp/venv/bin/python" -m pip install -r requirements.txt
python3 tools/install.py --host codex
```

The installer only copies the skill; it does not install system tools, change host configuration or overwrite an existing skill. Codex honors `CODEX_HOME`, otherwise uses `~/.codex/skills/all-video-mcp`. For Claude Code use `--host claude-code`; for another compatible host use `--skills-dir /path/to/skills`. Reload the host's skill catalog or start a new session if needed. Non-Codex host behavior remains unverified.

Windows PowerShell: use Python 3.10+ and install FFmpeg/Node or Deno on PATH, then:

```powershell
python -m venv "$env:LOCALAPPDATA\all-video-mcp\venv"
& "$env:LOCALAPPDATA\all-video-mcp\venv\Scripts\python.exe" -m pip install -r requirements.txt
python tools/install.py --host codex
```

Windows instructions have not been tested. Whisper downloads open model weights on first use and needs local disk space and compute.

## Use

Ask your agent:

> Use $all-video-mcp to explain this video in detail: https://www.youtube.com/watch?v=VIDEO_ID

Or simply ask it to watch and explain a video. Automatic invocation is enabled for supporting hosts; actual selection depends on the host. For local files:

> Use $all-video-mcp to explain /path/to/video.mp4, including the on-screen steps.

The agent should read the complete transcript, open the actual frame images, inspect important moments more densely and provide a timestamped account. Merely generating files does not mean the video has been visually understood.

To prepare evidence manually, from this checkout:

```sh
VIDEO_PYTHON="$HOME/.local/share/all-video-mcp/venv/bin/python"
"$VIDEO_PYTHON" skills/all-video-mcp/scripts/prepare_video.py "VIDEO_URL_OR_PATH" --output "$HOME/video-evidence/run-001"
```

Use a new output directory for every run. `--subtitle captions.srt` supplies local captions; `--language en` prefers English captions or sets the ASR language; `--interval 5` samples more densely; `--model tiny` runs faster with lower recognition accuracy. Set `--skip-asr` only when a transcript is intentionally unnecessary. Run `--help` for all options.

Outputs: `manifest.json`, `transcript.json`, `timeline.md` and `frames/*.jpg`; remote runs also retain the downloaded media. Nothing is uploaded by the helper. Frames/text that the agent sends to its AI host are processed under that host's policies.

## Costs and limits

The scripts use no paid API or cloud inference. Your AI host may require a subscription or consume usage quotas. Local compute, storage and internet are supplied by you; this is not unlimited free AI inference.

- Arbitrary URLs are not guaranteed. Private/deleted content, login requirements, DRM, rate limits and site changes can block retrieval. No cookie harvesting or access bypass is included.
- One completed video per run; live streams and playlists are not supported. Defaults: 60 minutes, downloaded video up to 720p, up to 240 overview frames plus 60 scene samples and a final sample.
- Samples can miss brief actions. Burned-in text is read by the host from frames; automatic OCR and embedded-subtitle extraction are not bundled.
- Whisper and automatic captions can mishear or hallucinate. A video with no audio is valid but is marked transcript-unavailable.
- Downloaded media, captions, manifests and local paths are private working artifacts. Keep them outside this repository. Only process content you are authorized to access.

## Validation and development

[Validation record](skills/all-video-mcp/references/validation.md) distinguishes short sample evidence from unverified platform/host coverage. To run the local tests, install FFmpeg and use Python; no model or network download is needed:

```sh
python3 -B -m unittest discover -s skills/all-video-mcp/scripts/tests -v
```

The skill source is maintained alongside SkillHub and distributed here as a standalone repository. This repository has no dependency on the SkillHub CLI.

## License

[MIT](LICENSE) for the original code and instructions. External tools, weights and source videos retain their own licenses and rights. No binaries, model weights or sample videos are bundled.
