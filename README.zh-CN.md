# Video Understanding

[English](README.md)

让支持图片理解的 AI 结合**真实影片画面、字幕和时间轴**，解释影片在说什么。支持可访问的影片链接及本机文件，不需要付费推理 API 或 API key。

这个项目提供的是 **agent skill**，不需要启动独立 MCP server。脚本在本机准备素材，AI 再读取图片和字幕进行分析。这是社区项目，并非 Google 或 OpenAI 官方集成。

## 能做什么

- 用 yt-dlp 获取可访问的影片，包含受支持的 YouTube 链接。
- 优先读取平台字幕；没有可用字幕时用本机 Whisper 转录。
- 用 FFmpeg 抽取定时画面和场景变化，按时间对齐字幕。
- 针对操作、图表、代码或不清楚的位置，补看指定时间的画面。
- 引导 AI 按时间顺序说明内容、例子、画面信息和不确定之处。

## 安装

需要 Python **3.10+**、FFmpeg（`ffmpeg` 和 `ffprobe`），以及能执行本机命令、读取本机图片的 AI 工具。YouTube 另需 Deno 2.3+ 或 Node 22+。系统工具的安装见[环境设置](skills/video-understanding/references/setup.md)。

macOS / Linux：

```sh
git clone https://github.com/lonnrek96/video-understanding.git
cd video-understanding
python3 -m venv "$HOME/.local/share/video-understanding/venv"
"$HOME/.local/share/video-understanding/venv/bin/python" -m pip install -r requirements.txt
python3 tools/install.py --host codex
```

安装工具只复制 skill，不会安装系统依赖、修改 host 配置或覆盖已有技能。Codex 支持 `CODEX_HOME`，默认安装到 `~/.codex/skills/video-understanding`。Claude Code 使用 `--host claude-code`；其他兼容工具可用 `--skills-dir /path/to/skills`。安装后刷新技能列表或开启新对话。其他 host 的完整行为尚未验证。

Windows PowerShell：安装 Python、FFmpeg 和 Node / Deno 后执行：

```powershell
python -m venv "$env:LOCALAPPDATA\video-understanding\venv"
& "$env:LOCALAPPDATA\video-understanding\venv\Scripts\python.exe" -m pip install -r requirements.txt
python tools/install.py --host codex
```

Windows／Ubuntu 的安装与离线字幕、画面、接续测试已通过[公开 CI](https://github.com/lonnrek96/video-understanding/actions/runs/43424232790)；Windows 的 Whisper 安装和转录仍未验证。Linux／Windows 只用 CPU 时，先按[设置说明](skills/video-understanding/references/setup.md)选择 CPU 版 PyTorch。Whisper 首次使用会下载开放模型权重，需要本机储存空间和计算资源。

## 使用

对 AI 说：

> 用 $video-understanding 完整解释这部影片，包括画面中的操作和字幕内容：https://www.youtube.com/watch?v=VIDEO_ID

也可以直接说「帮我看这部影片并解释内容」。技能已启用自动选用，但是否选中仍取决于 host。也支持本机路径，例如 `/path/to/video.mp4`。

AI 应读取完整字幕、实际打开画面图片，并补看重要片段，再给出带时间戳的解说。素材准备成功不代表 AI 已看过画面。

从 repo 手动准备素材：

```sh
VIDEO_PYTHON="$HOME/.local/share/video-understanding/venv/bin/python"
"$VIDEO_PYTHON" skills/video-understanding/scripts/prepare_video.py "影片链接或本机路径" --output "$HOME/video-evidence/run-001"
```

常用选项：

- 先看影片资料：加 `--inspect`，查看时长、章节和下载解析度，不下载影片。
- 跑到一半停了：用原命令加 `--resume`，已完成且核对无误的部分不用重做。
- 自己提供字幕：加 `--subtitle captions.srt`。
- 指定字幕或识别语言：例如 `--language zh`。
- 多看一些画面：加 `--interval 5`，每 5 秒取一张。
- 加快语音识别：加 `--model tiny`，但准确率会较低。

一般运行请使用新的输出目录；只有接续原任务才加 `--resume`。只有明确不需要语音转录时才用 `--skip-asr`，其他选项见 `--help`。

产物包括 `manifest.json`、`transcript.json`、`timeline.md`、`frames/*.jpg`、画面总览图和本机进度记录；网络影片还会保留下载文件。脚本不会上传素材，但 AI 读取的图片与文字会按其 host 的政策处理。

## 免费范围和限制

没有付费 API 或云端推理服务调用。使用者自己的 AI 方案仍可能有订阅费和额度限制，本机计算、储存及网络也由使用者提供。

- 不保证任何链接都可用。私人／已删除影片、登入、DRM、网站限流及改版都可能阻塞获取；不包含自动提取 cookies 或绕过权限。
- 每次处理一部已结束的影片，不支持直播和播放清单。默认上限为 60 分钟、下载最高 720p、240 张定时画面、60 张场景画面、60 个章节定位与一张末段画面。
- 抽帧可能漏掉短暂动作；硬字幕由 AI 从画面读取，未内置自动 OCR 或内嵌字幕提取。
- 语音识别和自动字幕可能出错；无音轨影片会标记为无转录。
- 影片、字幕、manifest 和本机路径属于工作产物，请保存在 repo 外，只处理有权访问的内容。

## 验证

[验证纪录](skills/video-understanding/references/validation.md)列出了实际跑通的样片及尚未确认的范围。安装 FFmpeg 与 Pillow（`python3 -m pip install Pillow`）后可运行本机测试；测试本身不需要网络或下载模型：

```sh
python3 -B -m unittest discover -s skills/video-understanding/scripts/tests -v
```

本技能由 SkillHub 维护，并在此独立分发；使用时不依赖 SkillHub CLI。

## 授权

原始代码、技能指令和文件采用自订的[免费使用且须署名授权 1.0](LICENSE)：可免费使用、修改及分发，包含商业用途，但必须保留作者署名。

署名内容：**Video Understanding by madebyteh (@lonnrek96)** — https://github.com/lonnrek96/video-understanding

复制或分发时保留授权文件，并在项目 README、说明文件、关于页或致谢处提供署名。私人本机使用保留原文件中的署名即可，不要求每次 AI 回答都重复署名；完整条款以 LICENSE 为准。外部工具、模型权重及影片保留各自的授权和权利；本项目不打包它们。
