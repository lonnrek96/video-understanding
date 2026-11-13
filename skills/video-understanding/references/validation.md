# Validation

## Environment and scope

2026-11-13: macOS Apple Silicon, Python 3.11.15, system FFmpeg, yt-dlp 2026.10.26 with EJS, openai-whisper 20250625, CPU tiny model.

The following are scoped observations, not a guarantee that all videos, websites or agent hosts work.

## Observed behavior

- Skill frontmatter/scaffold and SkillHub native resource validation passed.
- Local integration tests exercise VTT markup/repeated cues; real FFmpeg scene changes, caption alignment, nonempty JPEGs, no-audio status, existing-output refusal and out-of-range frame rejection.
- A locally synthesized spoken tutorial was transcribed with tiny Whisper, preserving the instruction to open the file menu, choose Save and enter a name. This validates the ASR wiring, not general recognition accuracy.
- A public direct MP4, https://www.w3schools.com/html/mov_bbb.mp4, downloaded and produced frames. ASR was explicitly skipped in that trial.
- A public YouTube sample, https://www.youtube.com/watch?v=jNQXAC9IVRw, downloaded with English manual captions. The host opened actual frame images: a person stood in front of elephant enclosures, then looked toward them. The transcript described long trunks and a closing remark. This is a short sample demonstration.
- An initial end-frame failure showed that container duration can exceed the last decodable image. JPEG-compatible pixel formatting and a final sample one second before the end were applied; local reprocessing of the downloaded media produced three frames with no warnings. No new download/ASR trial was needed for that change.
- The skill was renamed from `watch-video-free` without changing the processing script. Local integration tests passed from the renamed layout. Native packaging initially rejected README/test placement; sharing notes were moved under references/ and tests under scripts/tests/, then validation passed.

The above media/ASR trials ran locally without paid inference APIs or extra model processes. Host image inspection used the active conversation's normal usage. Sample media, transcripts and caches are not redistributed.

## Unverified coverage

- Other video platforms, login-protected content and platform automatic-caption retrieval.
- Multilingual/noisy speech recognition accuracy, hours-long inspection and rapid-motion completeness.
- Windows/Linux installation and complete Claude Code/other host behavior.
- Automatic skill selection in a fresh host session. Explicitly enabled metadata and installed files do not prove actual selection.

## Repeatable local checks

From the repository root, with Python and FFmpeg installed:

```sh
python3 -B -m unittest discover -s skills/video-understanding/scripts/tests -v
```

From an installed skill directory:

```sh
python3 -B -m unittest discover -s scripts/tests -v
```

These tests need no network or model download. The standalone installer can be checked against a temporary `--skills-dir`; a second installation must fail without changing existing content. Full real-world recognition and host behavior require separate video trials.
