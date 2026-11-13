#!/usr/bin/env python3
"""Build local, timestamped video evidence. No paid inference or shell execution."""
import argparse
import html
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def run(args, timeout=180):
    return subprocess.run([str(x) for x in args], check=True, capture_output=True,
                          text=True, timeout=timeout).stdout


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def stamp(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'


def seconds(value):
    parts = value.replace(',', '.').split(':')
    return sum(float(v) * 60 ** i for i, v in enumerate(reversed(parts)))


def captions(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    result = []
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
        lines = block.splitlines()
        for i, line in enumerate(lines):
            match = re.match(r'(\d[\d:.,]*)\s+-->\s+(\d[\d:.,]*)', line)
            if not match:
                continue
            content = html.unescape(re.sub(r'<[^>]+>', '', ' '.join(lines[i + 1:]))).strip()
            start, end = seconds(match[1]), seconds(match[2])
            if content and end > start:
                # Merge repeated rolling-caption cues while preserving their time coverage.
                if result and result[-1]['text'] == content and start <= result[-1]['end']:
                    result[-1]['end'] = max(end, result[-1]['end'])
                else:
                    result.append(dict(start=start, end=end, text=content))
            break
    return sorted(result, key=lambda x: x['start'])


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                           '-of', 'json', path]))


def extract_frame(media, at, destination):
    if at < 0 or not math.isfinite(at):
        raise ValueError('Frame timestamp must be finite and nonnegative')
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Refusing to overwrite an existing frame')
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', at, '-i', media, '-frames:v', '1',
         '-vf', "scale=w='min(1280,iw)':h=-2", '-pix_fmt', 'yuvj420p', '-q:v', '3', destination])
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ValueError('No frame at requested timestamp')


def acquire(url, output, args):
    from yt_dlp import YoutubeDL
    opts = dict(quiet=True, noplaylist=True, socket_timeout=30, retries=2,
                cachedir=False, skip_download=True, ignoreerrors=False,
                js_runtimes={'deno': {}, 'node': {}})
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get('_type') in ('playlist', 'multi_video'):
        raise ValueError('Supply a single video URL, not a playlist')
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming'):
        raise ValueError('Live/upcoming streams are not supported')
    duration = info.get('duration')
    if not duration and re.match(r'^https?://', info.get('url', '')):
        # Generic direct-file extractors may omit duration; inspect media headers first.
        duration = float(probe(info['url']).get('format', {}).get('duration', 0))
        info['duration'] = duration
    if not duration or not math.isfinite(duration) or duration > args.max_duration:
        raise ValueError('Remote duration unknown or exceeds --max-duration; no media downloaded')
    manual, automatic = info.get('subtitles') or {}, info.get('automatic_captions') or {}
    # Prefer requested language; otherwise prefer original manual before any other caption.
    original = next((k[:-5] for k in automatic if k.endswith('-orig')), None)
    lang = args.language or info.get('language') or original
    choices = []
    for tracks, kind in ((manual, 'manual'), (automatic, 'automatic')):
        for key, formats in tracks.items():
            if key == 'live_chat' or not any(x.get('ext') in ('vtt', 'srt') for x in formats):
                continue
            matches = bool(lang and (key == lang or key.split('-')[0] == lang.split('-')[0]))
            choices.append((0 if matches else 1, 0 if kind == 'manual' else 1, key, kind))
    choice = min(choices) if choices else None
    opts.update(skip_download=False, outtmpl=str(output / 'media.%(ext)s'),
                format='bv*[height<=720]+ba/b[height<=720]', merge_output_format='mkv',
                max_filesize=2 * 1024 ** 3)
    with YoutubeDL(opts) as ydl:
        ydl.process_info(info)
    media = [p for p in output.glob('media.*') if p.suffix in ('.mp4', '.mkv', '.webm', '.mov', '.flv', '.avi')]
    if len(media) != 1:
        raise ValueError('Download did not produce one supported media file')
    subtitle, source, warnings = None, None, []
    if choice:
        _, _, key, kind = choice
        subopts = dict(opts, skip_download=True, writesubtitles=kind == 'manual',
                       writeautomaticsub=kind == 'automatic', subtitleslangs=[key],
                       subtitlesformat='vtt/srt', outtmpl=str(output / 'caption.%(ext)s'))
        try:
            with YoutubeDL(subopts) as ydl:
                ydl.extract_info(url, download=True)
            files = sorted(list(output.glob('caption.*.vtt')) + list(output.glob('caption.*.srt')))
            if files:
                subtitle, source = files[0], f'platform-{kind}:{key}'
        except Exception:
            warnings.append('Platform captions could not be fetched; attempting local ASR.')
    # Do not persist raw extractor metadata, signed stream URLs, headers or cookies.
    metadata = {k: info.get(k) for k in ('title', 'uploader', 'duration', 'language')}
    return media[0], subtitle, source, metadata, warnings


def prepare(args):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Install FFmpeg and ffprobe first; see references/setup.md')
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    warnings = []
    subtitle = Path(args.subtitle).expanduser().resolve() if args.subtitle else None
    source = 'user-subtitle' if subtitle else None
    metadata = {}
    if re.match(r'^https?://', args.input, re.I):
        parsed = urlsplit(args.input)
        if parsed.username or parsed.password:
            raise ValueError('Credential-bearing URLs are not accepted')
        media, downloaded_sub, downloaded_source, metadata, warnings = acquire(args.input, output, args)
        subtitle, source = (subtitle, source) if subtitle else (downloaded_sub, downloaded_source)
    else:
        media = Path(args.input).expanduser().resolve(strict=True)
        if not media.is_file():
            raise ValueError('Input is not a media file')
    details = probe(media)
    duration = float(details.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0 or duration > args.max_duration:
        raise ValueError('Invalid duration or exceeds --max-duration')
    if not any(s['codec_type'] == 'video' for s in details['streams']):
        raise ValueError('Input has no video track')
    segments = captions(subtitle) if subtitle else []
    if subtitle and not segments:
        warnings.append('Provided/platform subtitle contains no readable cues; attempting ASR.')
    if not segments:
        source = None
        if args.skip_asr:
            warnings.append('Speech transcription explicitly skipped.')
        elif any(s['codec_type'] == 'audio' for s in details['streams']):
            try:
                import whisper
            except ImportError as error:
                raise ValueError('No usable captions. Install openai-whisper or provide --subtitle; do not claim transcript coverage.') from error
            audio = output / 'audio.wav'
            run(['ffmpeg', '-nostdin', '-v', 'error', '-i', media, '-vn', '-ac', '1',
                 '-ar', '16000', audio], timeout=1800)
            model = whisper.load_model(args.model, device='cpu')
            result = model.transcribe(str(audio), fp16=False, verbose=False,
                                      language=args.language, task='transcribe')
            segments = [dict(start=float(s['start']), end=float(s['end']), text=s['text'].strip())
                        for s in result['segments'] if s['text'].strip()]
            source = f'local-whisper:{args.model}:{result.get("language", "unknown")}'
        else:
            warnings.append('Video has no audio track and no supplied captions.')
    if not segments:
        warnings.append('Transcript unavailable/empty. Only visual evidence can be analyzed.')
    # Full temporal overview with an explicit batch cap; never silently truncate at the start.
    spacing = max(args.interval, duration / args.max_frames)
    times = [(round(i * spacing, 3), 'interval') for i in range(math.ceil(duration / spacing))]
    # Additional scene samples, bounded independently so long videos cannot explode output.
    # showinfo is stderr, not stdout. Decode the entire stream only when scene samples requested.
    if args.max_scenes:
        scene_run = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(media), '-an',
                                   '-vf', r'select=gt(scene\,0.35),showinfo', '-frames:v', str(args.max_scenes),
                                   '-f', 'null', '-'], capture_output=True, text=True, timeout=1800, check=True)
        scene_times = re.findall(r'pts_time:([\d.]+)', scene_run.stderr)
        times += [(round(float(t), 3), 'scene') for t in scene_times if float(t) < duration]
        if len(scene_times) >= args.max_scenes:
            warnings.append('Scene sample cap reached; later scene changes may not be represented.')
    times.append((round(max(0, duration - 1.0), 3), 'end'))
    times = sorted({t: kind for t, kind in times}.items())
    frame_dir = output / 'frames'
    frame_dir.mkdir()
    frames = []
    for i, (at, kind) in enumerate(times):
        path = frame_dir / f'{i:05d}-{at:010.3f}.jpg'
        try:
            extract_frame(media, at, path)
        except (subprocess.CalledProcessError, ValueError):
            if path.exists():
                path.unlink()
            warnings.append(f'No frame decoded at {at:.3f}s; inspect nearby if relevant.')
            continue
        nearby = [s for s in segments if s['start'] <= at < s['end']]
        frames.append(dict(time=at, reason=kind, path=str(path.relative_to(output)), captions=nearby))
    if not frames:
        raise ValueError('No visual frames decoded; cannot prepare visual evidence')
    write_json(output / 'transcript.json', dict(source=source, segments=segments))
    manifest = dict(schema_version=1, status='prepared-not-yet-interpreted', media=str(media),
                    metadata=metadata, duration=duration, transcript_source=source,
                    transcript_status='available' if segments else 'unavailable',
                    frame_interval_seconds=spacing, frames=frames, warnings=warnings)
    write_json(output / 'manifest.json', manifest)
    lines = ['# Video evidence', '', f'Duration: {stamp(duration)}; frame spacing: {spacing:.2f}s.',
             f'Transcript source: {source or "unavailable"}.', '',
             'Preparation is not proof that the AI viewed the images.', '']
    for frame in frames:
        lines += [f'## {stamp(frame["time"])} ({frame["time"]:.3f}s)',
                  f'Frame: {frame["path"]}',
                  *[f'[{stamp(s["start"])}] {s["text"]}' for s in frame['captions']], '']
    (output / 'timeline.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(output=str(output), duration=duration, frames=len(frames),
                          transcript_source=source, warnings=warnings), ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?')
    parser.add_argument('--output')
    parser.add_argument('--subtitle')
    parser.add_argument('--language', help='Language code, e.g. zh or en')
    parser.add_argument('--model', choices=['tiny', 'base', 'small', 'medium', 'large', 'turbo'], default='base')
    parser.add_argument('--skip-asr', action='store_true')
    parser.add_argument('--interval', type=float, default=15)
    parser.add_argument('--max-frames', type=int, default=240)
    parser.add_argument('--max-scenes', type=int, default=60)
    parser.add_argument('--max-duration', type=float, default=3600)
    parser.add_argument('--frame-source')
    parser.add_argument('--at', type=float)
    parser.add_argument('--save-frame')
    args = parser.parse_args()
    try:
        if args.frame_source:
            if args.at is None or not args.save_frame:
                parser.error('--frame-source requires --at and --save-frame')
            media = Path(args.frame_source).expanduser().resolve(strict=True)
            duration = float(probe(media)['format']['duration'])
            if args.at >= duration:
                raise ValueError('Timestamp is beyond video duration')
            extract_frame(media, args.at, args.save_frame)
        else:
            if not args.input or not args.output:
                parser.error('input and --output are required')
            if (not math.isfinite(args.interval) or args.interval <= 0 or args.max_frames < 1
                    or args.max_scenes < 0 or not math.isfinite(args.max_duration) or args.max_duration <= 0):
                parser.error('Intervals, duration and frame count must be positive; scene count nonnegative')
            prepare(args)
    except Exception as error:
        # Libraries can include signed URLs in exceptions; keep terminal output generic.
        print(f'ERROR ({type(error).__name__}): video preparation failed. '
              'Check dependencies, input access, duration limits and subtitle availability. '
              'Partial output may exist; use a new output directory for a retry.', file=sys.stderr)
        if isinstance(error, (ValueError, FileExistsError, ImportError)):
            print(str(error) if not isinstance(error, ImportError) else 'Missing local Python dependency.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
