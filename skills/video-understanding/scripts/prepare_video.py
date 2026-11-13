#!/usr/bin/env python3
"""Build local, timestamped video evidence. No paid inference or shell execution."""
import argparse
import concurrent.futures
import hashlib
import os
import tempfile
import threading
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
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.checkpoint-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


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
    run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '2', '-ss', at, '-i', media, '-frames:v', '1',
         '-vf', "scale=w='min(1280,iw)':h=-2", '-pix_fmt', 'yuvj420p', '-threads', '2', '-q:v', '3', destination])
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ValueError('No frame at requested timestamp')


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def progress(stage, message):
    print(f'[{stage}] {message}', file=sys.stderr, flush=True)


class Checkpoints:
    def __init__(self, output, signature, resume):
        self.output, self.path = output, output / 'run.json'
        self.lock = threading.Lock()
        if resume:
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            if self.state.get('schema') != 2 or self.state.get('signature') != signature:
                raise ValueError('Resume input/options differ from run.json; use the original options or a new output directory')
        else:
            self.state = dict(schema=2, signature=signature, stages={})
            write_json(self.path, self.state)

    def read(self, stage):
        with self.lock:
            saved = self.state['stages'].get(stage)
            if saved is None:
                return None
            for name, digest in saved['files'].items():
                path = self.output / name
                if not path.is_file() or path.is_symlink() or file_hash(path) != digest:
                    raise ValueError(f'Checkpoint artifact missing or changed: {name}; use a new output directory')
            if not stage.startswith('frame-'):
                progress(stage, 'Reusing verified checkpoint')
            return saved['value']

    def save(self, stage, value, files=()):
        hashes = {str(Path(p).relative_to(self.output)): file_hash(p) for p in files}
        with self.lock:
            self.state['stages'][stage] = dict(value=value, files=hashes)
            write_json(self.path, self.state)


class DownloadLog:
    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):
        # Extractor logs can contain signed URLs; expose only a useful category.
        progress('download', 'Upstream warning; access or runtime support may be limited')

    def error(self, message):
        progress('download', 'Upstream request failed; no credentials or signed URLs are logged')


def download_options():
    # Apply format selection BEFORE extract_info resolves requested_formats.
    return dict(quiet=True, noprogress=True, noplaylist=True, socket_timeout=30,
                retries=2, cachedir=False, skip_download=True, ignoreerrors=False,
                logger=DownloadLog(), js_runtimes={'deno': {}, 'node': {}},
                format='bv*[height<=720]+ba/b[height<=?720]', max_filesize=2 * 1024 ** 3)


def validate_duration(duration, maximum, remote=False):
    if not duration or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Video duration is unknown; no media download started' if remote else 'Media duration is invalid')
    if duration > maximum:
        raise ValueError(f'Video duration {stamp(duration)} exceeds limit {stamp(maximum)}; '
                         f'use --max-duration {math.ceil(duration) + 1} to include this video')


def inspect_remote(url, maximum):
    from yt_dlp import YoutubeDL
    parsed = urlsplit(url)
    if parsed.username or parsed.password:
        raise ValueError('Credential-bearing URLs are not accepted')
    with YoutubeDL(download_options()) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get('_type') in ('playlist', 'multi_video'):
        raise ValueError('Supply a single video URL, not a playlist')
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming'):
        raise ValueError('Live/upcoming streams are not supported')
    # Generic MP4 extractors often omit dimensions. Probe before downloading;
    # allowing unknown metadata must never relax the actual 720p boundary.
    for selected in info.get('requested_formats') or [info]:
        if selected.get('vcodec') == 'none' or selected.get('height'):
            continue
        if not re.match(r'^https?://', selected.get('url', '')):
            raise ValueError('Selected video resolution is unknown; no media download started')
        details = probe(selected['url'])
        streams = [s for s in details.get('streams', []) if s.get('codec_type') == 'video']
        height = max((s.get('height', 0) for s in streams), default=0)
        if not height or height > 720:
            raise ValueError('Selected video resolution is unknown or exceeds 720p; no media download started')
        selected['height'] = height
        if selected is info and not info.get('duration'):
            info['duration'] = float(details.get('format', {}).get('duration', 0))
    duration = info.get('duration')
    if not duration and re.match(r'^https?://', info.get('url', '')):
        duration = float(probe(info['url']).get('format', {}).get('duration', 0))
        info['duration'] = duration
    validate_duration(duration, maximum, remote=True)
    return info


def public_metadata(info):
    result = {k: info.get(k) for k in ('title', 'uploader', 'duration', 'language')}
    result['selected_video_height'] = max((f.get('height') or 0 for f in info.get('requested_formats') or [info]), default=0)
    result['chapters'] = [{k: c.get(k) for k in ('start_time', 'end_time', 'title')}
                          for c in info.get('chapters') or []]
    return result


def acquire(url, output, args):
    from yt_dlp import YoutubeDL
    progress('inspect', 'Checking duration, available captions and 720p formats')
    info = inspect_remote(url, args.max_duration)
    progress('download', f'Downloading {stamp(info["duration"])} video, maximum 720p')
    opts = download_options()
    opts.update(skip_download=False, outtmpl=str(output / 'media.%(ext)s'), merge_output_format='mkv')
    with YoutubeDL(opts) as ydl:
        ydl.process_info(info)
    media = [p for p in output.glob('media.*') if p.suffix in ('.mp4', '.mkv', '.webm', '.mov', '.flv', '.avi')]
    if len(media) != 1:
        raise ValueError('Download did not produce one supported media file')
    streams = probe(media[0])['streams']
    height = max((s.get('height', 0) for s in streams if s['codec_type'] == 'video'), default=0)
    if height > 720:
        raise ValueError(f'Download resolution check failed: {height}p exceeds 720p')
    manual, automatic = info.get('subtitles') or {}, info.get('automatic_captions') or {}
    original = next((k[:-5] for k in automatic if k.endswith('-orig')), None)
    lang = args.language or info.get('language') or original
    choices = []
    for tracks, kind in ((manual, 'manual'), (automatic, 'automatic')):
        for key, formats in tracks.items():
            if key == 'live_chat' or not any(x.get('ext') in ('vtt', 'srt') for x in formats):
                continue
            matches = bool(lang and (key == lang or key.split('-')[0] == lang.split('-')[0]))
            choices.append((0 if matches else 1, 0 if kind == 'manual' else 1, key, kind))
    subtitle, source, warnings = None, None, []
    if choices and not args.subtitle:
        _, _, key, kind = min(choices)
        subopts = dict(opts, skip_download=True, writesubtitles=kind == 'manual',
                       writeautomaticsub=kind == 'automatic', subtitleslangs=[key],
                       subtitlesformat='vtt/srt', outtmpl=str(output / 'caption.%(ext)s'))
        try:
            with YoutubeDL(subopts) as ydl:
                ydl.extract_info(url, download=True)
            files = sorted(list(output.glob('caption.*.vtt')) + list(output.glob('caption.*.srt')))
            if files:
                subtitle, source = str(files[0]), f'platform-{kind}:{key}'
        except Exception:
            warnings.append('Platform captions unavailable (possibly rate-limited); using local ASR if needed.')
            progress('captions', 'Unavailable; switching to local ASR without repeating the download')
    metadata = public_metadata(info)
    metadata['downloaded_height'] = height
    return dict(media=str(media[0]), subtitle=subtitle, source=source, metadata=metadata, warnings=warnings)


def asr_warnings(segments, duration):
    warnings = ['Local ASR words and timestamps are approximate; verify names/actions against frames. Silence/music may produce invented text.']
    if any(not math.isfinite(s['start']) or not math.isfinite(s['end']) or
           s['start'] < 0 or s['end'] <= s['start'] or s['end'] > duration + 0.5 for s in segments):
        warnings.append('ASR timestamps extend outside the video or are invalid; raw output is retained for review and must not be treated as reliable speech.')
    return warnings


def transcribe(media, output, args, subtitle, source, checkpoint):
    cached = checkpoint.read('transcript')
    if cached is not None:
        return cached
    progress('transcript', 'Reading captions or transcribing audio locally')
    segments, warnings = captions(subtitle) if subtitle else [], []
    if subtitle and not segments:
        warnings.append('Caption file has no readable cues; attempting local ASR.')
    if not segments:
        source = None
        if args.skip_asr:
            warnings.append('Speech transcription explicitly skipped.')
        elif any(s['codec_type'] == 'audio' for s in probe(media)['streams']):
            try:
                import whisper
            except ImportError as error:
                raise ValueError('No usable captions: install openai-whisper or supply --subtitle') from error
            audio = output / 'audio.wav'
            run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', media, '-vn', '-ac', '1', '-ar', '16000', audio], timeout=1800)
            model = whisper.load_model(args.model, device='cpu')
            result = model.transcribe(str(audio), fp16=False, verbose=None, language=args.language, task='transcribe')
            segments = [dict(start=float(s['start']), end=float(s['end']), text=s['text'].strip())
                        for s in result['segments'] if s['text'].strip()]
            source = f'local-whisper:{args.model}:{result.get("language", "unknown")}'
            warnings.extend(asr_warnings(segments, float(probe(media)['format']['duration'])))
        else:
            warnings.append('Video has no audio track and no supplied captions.')
    if not segments:
        warnings.append('Transcript unavailable/empty; no speech coverage can be claimed.')
    value = dict(source=source, segments=segments, warnings=warnings)
    path = output / 'transcript.json'
    write_json(path, value)  # Persist BEFORE waiting for frame extraction.
    checkpoint.save('transcript', value, [path])
    progress('transcript', f'Saved {len(segments)} segments; source: {source or "unavailable"}')
    return value


def sample_times(media, duration, metadata, args, checkpoint, output):
    cached = checkpoint.read('sampling')
    if cached is not None:
        return cached
    spacing = max(args.interval, duration / args.max_frames)
    times = {round(i * spacing, 3): 'interval' for i in range(math.ceil(duration / spacing))}
    warnings = []
    # Chapter anchors are independent of scene detection; preserve the full chapter list.
    for chapter in (metadata.get('chapters') or [])[:60]:
        at = chapter.get('start_time')
        if isinstance(at, (int, float)) and math.isfinite(at) and 0 <= at < duration:
            times[round(min(at + 1, max(0, duration - 1)), 3)] = 'chapter'
    if args.max_scenes:
        progress('frames', 'Finding scene changes using 1 fps downscaled analysis')
        scene_run = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-threads', '2', '-i', str(media), '-an',
                                   '-vf', r'fps=1,scale=320:-2,select=gt(scene\,0.2),showinfo',
                                   '-frames:v', str(args.max_scenes), '-f', 'null', '-'],
                                  capture_output=True, text=True, timeout=1800, check=True)
        scenes = re.findall(r'pts_time:([\d.]+)', scene_run.stderr)
        for t in scenes:
            if float(t) < duration:
                times[round(float(t), 3)] = 'scene'
        if len(scenes) >= args.max_scenes:
            warnings.append('Scene sample cap reached; use interval/chapter coverage and inspect important moments.')
    times[round(max(0, duration - 1), 3)] = 'end'
    value = dict(spacing=spacing, times=sorted(times.items()), warnings=warnings)
    path = output / 'sampling.json'
    write_json(path, value)
    checkpoint.save('sampling', value, [path])
    return value


def make_overviews(output, frames):
    from PIL import Image, ImageChops, ImageStat, ImageDraw, ImageOps
    representatives, sheets = [], []
    previous, previous_frame = None, None
    for frame in frames:
        with Image.open(output / frame['path']) as image:
            small = image.convert('RGB').resize((320, 180))
        similar = previous is not None and sum(ImageStat.Stat(ImageChops.difference(previous, small)).mean) / 3 < 1
        if similar:
            frame['similar_to'] = previous_frame['path']
        else:
            representatives.append(frame)
            previous, previous_frame = small, frame
    for batch in range(0, len(representatives), 12):
        path = output / f'overview-{batch // 12:03d}.jpg'
        sheet = Image.new('RGB', (1280, 606), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, frame in enumerate(representatives[batch:batch + 12]):
            x, y = (i % 4) * 320, (i // 4) * 202
            draw.text((x + 4, y + 4), stamp(frame['time']), fill='black')
            with Image.open(output / frame['path']) as image:
                sheet.paste(ImageOps.contain(image.convert('RGB'), (320, 180)), (x, y + 22))
        sheet.save(path)
        sheets.append(path.name)
    return dict(sheets=sheets, representative_count=len(representatives),
                note='Similar is not identical. All original frames/timestamps are retained; inspect originals for text or actions.')


def visual_evidence(media, duration, metadata, output, args, checkpoint):
    cached = checkpoint.read('visuals')
    if cached is not None:
        return cached
    sampling = sample_times(media, duration, metadata, args, checkpoint, output)
    directory = output / 'frames'
    directory.mkdir(exist_ok=True)
    frames, warnings = [], list(sampling['warnings'])
    for i, (at, kind) in enumerate(sampling['times']):
        stage = f'frame-{i:05d}'
        frame = checkpoint.read(stage)
        if frame is None:
            path = directory / f'{i:05d}-{at:010.3f}.jpg'
            # Only clean an uncheckpointed output left by this run's interrupted extraction.
            if path.exists():
                if path.is_symlink():
                    raise ValueError('Unexpected symlink in frame output')
                path.unlink()
            try:
                extract_frame(media, at, path)
                frame = dict(time=at, reason=kind, path=str(path.relative_to(output)))
                checkpoint.save(stage, frame, [path])
            except (subprocess.CalledProcessError, ValueError):
                warnings.append(f'No frame decoded at {at:.3f}s; inspect nearby if relevant.')
                continue
        frames.append(dict(frame))
        if i % 20 == 0:
            progress('frames', f'{i + 1}/{len(sampling["times"])} sample positions processed')
    if not frames:
        raise ValueError('No visual frames decoded; cannot claim visual coverage')
    overview = make_overviews(output, frames)
    value = dict(frames=frames, spacing=sampling['spacing'], warnings=warnings, overview=overview)
    checkpoint.save('visuals', value, [output / f['path'] for f in frames] + [output / s for s in overview['sheets']])
    progress('frames', f'Saved {len(frames)} frames and {len(overview["sheets"])} overview sheets')
    return value


def identity(args):
    if re.match(r'^https?://', args.input, re.I):
        source = dict(url_digest=hashlib.sha256(args.input.encode()).hexdigest())
    else:
        path = Path(args.input).expanduser().resolve(strict=True)
        source = dict(path=str(path), digest=file_hash(path))
    settings = {k: getattr(args, k) for k in ('language', 'model', 'skip_asr', 'interval', 'max_frames', 'max_scenes', 'max_duration')}
    if args.subtitle:
        settings['subtitle_digest'] = file_hash(Path(args.subtitle).expanduser().resolve(strict=True))
    return dict(source=source, settings=settings)


def prepare(args):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Install FFmpeg and ffprobe first; see references/setup.md')
    signature = identity(args)
    output = Path(args.output).expanduser().resolve()
    if args.resume:
        if not output.is_dir() or not (output / 'run.json').is_file():
            raise ValueError('--resume requires an existing checkpointed output directory')
    else:
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
    lock_path = output / '.prepare.lock'
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        checkpoint = Checkpoints(output, signature, args.resume)
        acquired = checkpoint.read('acquire')
        if acquired is None:
            if re.match(r'^https?://', args.input, re.I):
                acquired = acquire(args.input, output, args)
                files = [Path(acquired['media'])]
                if acquired['subtitle']:
                    files.append(Path(acquired['subtitle']))
            else:
                acquired = dict(media=str(Path(args.input).expanduser().resolve()), subtitle=None,
                                source=None, metadata={}, warnings=[])
                files = []
            write_json(output / 'metadata.json', acquired['metadata'])
            checkpoint.save('acquire', acquired, files + [output / 'metadata.json'])
        media = acquired['media']
        details = probe(media)
        duration = float(details.get('format', {}).get('duration', 0))
        validate_duration(duration, args.max_duration)
        if not any(s['codec_type'] == 'video' for s in details['streams']):
            raise ValueError('Input has no video track')
        subtitle = str(Path(args.subtitle).expanduser().resolve()) if args.subtitle else acquired['subtitle']
        source = 'user-subtitle' if args.subtitle else acquired['source']
        results, errors = {}, []
        # Stages checkpoint independently: a visual failure cannot discard a completed transcript.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(transcribe, media, output, args, subtitle, source, checkpoint): 'transcript',
                pool.submit(visual_evidence, media, duration, acquired['metadata'], output, args, checkpoint): 'visuals',
            }
            for future in concurrent.futures.as_completed(futures):
                stage = futures[future]
                try:
                    results[stage] = future.result()
                except Exception as error:
                    errors.append((stage, error))
                    progress(stage, 'Failed; completed checkpoints are retained for --resume')
        if errors:
            raise ValueError(f'{errors[0][0]} stage failed ({type(errors[0][1]).__name__}); '
                             'completed stages are saved. Check dependencies/input and retry with --resume') from errors[0][1]
        transcript, visual = results['transcript'], results['visuals']
        for frame in visual['frames']:
            frame['captions'] = [s for s in transcript['segments'] if s['start'] <= frame['time'] < s['end']]
        manifest = dict(schema_version=2, status='prepared-not-yet-interpreted', media=media,
                        metadata=acquired['metadata'], duration=duration, transcript_source=transcript['source'],
                        transcript_status='available' if transcript['segments'] else 'unavailable',
                        frame_interval_seconds=visual['spacing'], frames=visual['frames'], overview=visual['overview'],
                        warnings=acquired['warnings'] + transcript['warnings'] + visual['warnings'])
        write_json(output / 'manifest.json', manifest)
        lines = ['# Video evidence', '', f'Duration: {stamp(duration)}; overview spacing: {visual["spacing"]:.2f}s.',
                 f'Transcript source: {transcript["source"] or "unavailable"}.',
                 'Preparation is not proof that the AI viewed the images.',
                 'Overview sheets: ' + ', '.join(visual['overview']['sheets']), '']
        for frame in visual['frames']:
            lines += [f'## {stamp(frame["time"])} ({frame["time"]:.3f}s)', f'Frame: {frame["path"]}',
                      *[f'[{stamp(s["start"])}] {s["text"]}' for s in frame['captions']], '']
        (output / 'timeline.md').write_text('\n'.join(lines), encoding='utf-8')
        progress('complete', 'Evidence saved; AI interpretation is still required')
        print(json.dumps(dict(output=str(output), duration=duration, frames=len(visual['frames']),
                              transcript_source=transcript['source'], warnings=manifest['warnings']), ensure_ascii=False))
    finally:
        lock_path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?')
    parser.add_argument('--output')
    parser.add_argument('--resume', action='store_true', help='Reuse verified checkpoints with identical input/options')
    parser.add_argument('--inspect', action='store_true', help='Inspect metadata/duration without downloading media or ASR')
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
            if args.at >= float(probe(media)['format']['duration']):
                raise ValueError('Timestamp is beyond video duration')
            extract_frame(media, args.at, args.save_frame)
        else:
            if not args.input or (not args.inspect and not args.output):
                parser.error('input and --output are required (except --inspect)')
            if (not math.isfinite(args.interval) or args.interval <= 0 or args.max_frames < 1
                    or args.max_scenes < 0 or not math.isfinite(args.max_duration) or args.max_duration <= 0):
                parser.error('Intervals, duration and frame count must be positive; scene count nonnegative')
            if args.inspect:
                if re.match(r'^https?://', args.input, re.I):
                    info = inspect_remote(args.input, float('inf'))
                    metadata = public_metadata(info)
                    metadata['exceeds_limit'] = info['duration'] > args.max_duration
                    metadata['suggested_max_duration'] = math.ceil(info['duration']) + 1
                else:
                    metadata = probe(Path(args.input).expanduser().resolve(strict=True))
                print(json.dumps(metadata, ensure_ascii=False, indent=2))
            else:
                prepare(args)
    except Exception as error:
        print(f'ERROR ({type(error).__name__}): video preparation failed.', file=sys.stderr)
        if isinstance(error, (ValueError, FileExistsError)):
            print(str(error), file=sys.stderr)
        else:
            print('Check dependencies, input access and duration limits. No signed URLs or credentials are printed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
