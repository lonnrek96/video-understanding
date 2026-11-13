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

- Successful end-to-end retrieval on other video platforms, login-protected content and platform automatic-caption retrieval. A Vimeo follow-up attempt failed; see below.
- General multilingual/noisy speech recognition accuracy, hours-long inspection and rapid-motion completeness. A natural Chinese fallback trial is documented below with observed recognition and timing errors; it does not establish general accuracy.
- Windows installation, Linux speech recognition/network acquisition, and complete Claude Code/other host behavior. The Linux provided-subtitle path below has been exercised.
- Implicit selection across other hosts and fresh URL-only acquisition. One fresh Codex CLI session using prepared evidence has been observed below; metadata visibility alone still does not prove selection.

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

## Recovery and sampling checks

A 64:02 lecture exposed three issues: a combined unknown/over-limit error, subtitles rate-limited with HTTP 429, and an actual 1080p download despite the advertised 720p selector. ASR completed but could not be read until the later visual stage finished. These are observed defects, not inferred cost savings.

This revision adds selection before metadata format resolution plus a downloaded-height guard; separate duration diagnostics/inspection; independent transcript/visual checkpoints, hash-checked resume and a single-writer lock; downscaled scene analysis, chapter anchors and timestamped overview sheets. Originals remain available even when overview representatives are grouped by similarity.

Six local tests passed, including preserved transcript after a simulated visual failure, no retranscription on resume, tampered checkpoint refusal, actual-resolution rejection, and chapter sampling with scene analysis disabled. A real short YouTube acquisition completed and passed the height guard; a metadata-only check on the original lecture now selects 720p and reports its duration/chapters. The lecture has not been re-downloaded or re-transcribed for this revision.

The existing lecture media and its already-completed ASR (converted to a supplied SRT) were also processed locally with a sparse 5-minute overview: 674 segments, 14 original frames and two overview sheets. A repeated `--resume` reused acquisition, transcript and visuals, with the transcript file's modification time unchanged. This checks real artifact reuse, not a new recognition result or dense whole-video inspection.

## Chinese and Linux follow-up

2026-11-13: an 8.17-second synthetic Chinese tutorial used local macOS TTS and three slides: open Settings, choose Language, click Save. Local tiny Whisper with `--language zh` recovered all three instructions in one 0–7-second segment. Six sampled originals and one overview were produced without warnings; the host inspected the actual overview and relevant original frames, which showed the three instructions. This verifies a clean synthetic input, not natural Chinese speech, software interaction, fine-grained word timing or general recognition accuracy. A single cue spanning several slides also illustrates why transcript timing alone is insufficient.

An isolated Linux container (Python 3.11.18, FFmpeg 7.1.5, yt-dlp and Pillow) then processed the same locally generated video with three explicitly supplied Chinese SRT cues. It produced six frames and one overview with `transcript_source: user-subtitle`; `--resume` reused acquisition, transcript and visuals. No Whisper/PyTorch model or network-video acquisition was exercised inside Linux. The temporary container was removed; no downloaded source media is redistributed.

A metadata-only request to https://vimeo.com/76979871 failed through the upstream downloader in this environment. The public-safe diagnostic did not establish a precise cause. This is an observed access failure, not successful Vimeo support; no login cookies or access bypass was attempted.

Private run/checkpoint/log evidence is retained under `~/.local/state/skillhub-followups-6qawOP/`, with a central `evidence.json` receipt. These follow-ups used no paid inference APIs or additional AI processes. At that stage, fresh-session selection was unverified. The later scoped Codex result is below; other hosts and real model quality/cost comparisons remain unverified.

## Real Chinese tutorial follow-up

2026-11-13: https://www.youtube.com/watch?v=u3GHIkpwyHI (Microsoft ExpertZone TW, a 232-second Windows Snipping Tool tutorial) completed real YouTube acquisition at an independently probed 1280×720. It supplied 55 manual Traditional Chinese caption segments (`platform-manual:zh-Hant`, 0.45–231.634 seconds), 71 timestamped original frames and six overview sheets representing 68 samples. The active host read every caption segment, viewed all six overview sheets and enlarged nine relevant originals across recording and screenshot demonstrations. This is sampled whole-timeline inspection, not every video frame.

The frames and captions aligned on mode switching, region selection, starting/pausing/stopping recording, preview/save, screenshot modes and annotation. Original frames additionally showed the capture delay menu (none, 3, 5 and 10 seconds) and the demonstrated recording file’s properties. The nested example file’s 1920×1080 resolution is on-screen content, not the downloaded video resolution. The tutorial is from 2023: its audio-recording limitation describes that demonstrated version, not a verified current Windows limitation.

No ASR was invoked in that acquisition because manual Chinese captions were available. The separate no-sidecar fallback trial below exercises local recognition; actual Windows operation remains untested. A fresh-session implicit-selection test used a frozen pre-result skill snapshot so these observations did not disclose its expected answers. Its result is documented separately below. Private evidence: `~/.local/state/video-real-zh-TadYyp/`. Media, captions and outputs are not redistributed with the skill.

## Natural speech and direct-file follow-up

The same 232-second Chinese tutorial was passed as local media without a sidecar subtitle, forcing the complete local Whisper base path. It produced 48 segments, 27 original frames and three overview sheets; the active host read all segments and viewed all three sheets. Recording, screenshot, annotation and delay instructions remained understandable, but proper names and terms were mistranscribed (for example, 矩形 became 舉行). Some recording instructions were early by roughly 9–13 seconds after the opening montage, and one phrase repeated. This is a successful fallback pipeline with observed accuracy limitations, not accurate word alignment or a subtitle-free source claim (the source itself has captions, deliberately withheld from the pipeline).

A fresh direct-file download from https://www.w3schools.com/html/mov_bbb.mp4 completed at 320×176, lasting 10.027 seconds, with seven original frames and one overview. The host viewed the actual sheet showing an animated rabbit and butterfly. Local Whisper returned suspicious text, including a segment ending at 23.86 seconds, beyond the video. No reliable speech interpretation is claimed. The processor now reports approximate-ASR and out-of-range timestamp warnings while retaining raw evidence; a new local processing run confirmed both warnings. Eight offline tests pass, including unknown remote dimensions and invalid ASR timing.

Unknown-height downloader formats are now probed before downloading and rejected when no video height can be established or it exceeds 720p; the downloaded-file guard remains. This fixes missing-dimension handling without accepting an unchecked resolution. Separate MDN/W3C requests failed; a diagnostic for the W3C URL reported an upstream 403 challenge. Neither failure establishes platform support, and no impersonation, cookies or bypass was attempted.

The portable GitHub workflow uses standard Ubuntu/Windows runners, requires FFmpeg rather than silently skipping media checks, runs the offline suite and verifies both install layouts and overwrite refusal. Workflow presence alone is not evidence of a passing Windows run; actual run results are recorded separately.

## Observed fresh-session implicit selection

2026-11-13: after explicit approval for one new Codex subscription round (gpt-6.1-sol, medium, one slot, at most 240 seconds, no automatic turn rerun), a fresh CLI dialogue completed in 47.602 seconds. The user request named only the video URL and an existing local evidence directory; it did not name this skill. The ordinary installed skill catalog was retained, with this skill frozen before the current sample findings were added to validation notes. A read-only prompt preflight showed its catalog entry, but not its full body, in initial context.

The first recorded command read this skill’s complete SKILL.md. Tool output contained the complete 55-segment transcript. Native rollout records then contained six actual overview image blocks and seven original-frame image blocks (13 input_image blocks), not merely paths or an assistant claim. The answer’s visual-only shortcut-notification note and capture-delay choices were checked against the original frames. It correctly scoped the recording-audio limitation to the demonstrated version and disclosed sampled coverage. The manifest, transcript and media hashes stayed unchanged.

This is one positive, cached-material Codex CLI comprehension/routing observation. Acquisition was independently verified by the parent conversation; the fresh session did not download or transcribe from scratch. It is not evidence for all links, other hosts, negative routing cases, natural Chinese ASR, Windows interaction, complete adversarial tool isolation or lower cost. The one-round allowance is exhausted; no retry or additional model turn was started. Native events, output and verification are private under `~/.local/state/video-real-zh-TadYyp/`.
