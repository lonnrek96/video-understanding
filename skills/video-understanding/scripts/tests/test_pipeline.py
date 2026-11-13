"""Local integration checks; no network or inference downloads."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'prepare_video.py'
spec = importlib.util.spec_from_file_location('video', SCRIPT)
video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video)


class PipelineTests(unittest.TestCase):
    def test_caption_markup_and_duplicate_cues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.vtt'
            path.write_text('WEBVTT\n\n00:00.000 --> 00:01.000\n<c>Hello &amp; welcome</c>\n\n00:00.500 --> 00:02.000\nHello &amp; welcome\n')
            self.assertEqual(video.captions(path), [dict(start=0, end=2, text='Hello & welcome')])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_visual_and_transcript_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media, sub, out = root / 'test.mp4', root / 'test.srt', root / 'run'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=red:s=160x120:d=2', '-f', 'lavfi', '-i',
                            'color=c=blue:s=160x120:d=2', '-filter_complex',
                            '[0:v][1:v]concat=n=2:v=1:a=0', '-c:v', 'libx264', str(media)], check=True)
            sub.write_text('1\n00:00:00,000 --> 00:00:02,000\nRed\n\n2\n00:00:02,000 --> 00:00:04,000\nBlue\n')
            subprocess.run([sys.executable, str(SCRIPT), str(media), '--subtitle', str(sub),
                            '--interval', '1', '--output', str(out)], check=True, capture_output=True)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['transcript_status'], 'available')
            self.assertEqual(manifest['status'], 'prepared-not-yet-interpreted')
            self.assertEqual(manifest['frames'][0]['captions'][0]['text'], 'Red')
            blue = next(f for f in manifest['frames'] if f['time'] == 2)
            self.assertEqual(blue['captions'][0]['text'], 'Blue')
            self.assertIn('scene', [f['reason'] for f in manifest['frames']])
            for frame in manifest['frames']:
                self.assertGreater((out / frame['path']).stat().st_size, 100)
            retry = subprocess.run([sys.executable, str(SCRIPT), str(media), '--output', str(out)], capture_output=True)
            self.assertNotEqual(retry.returncode, 0)
            # No-audio media must never fabricate a transcript.
            silent = root / 'silent'
            subprocess.run([sys.executable, str(SCRIPT), str(media), '--output', str(silent)], check=True, capture_output=True)
            self.assertEqual(json.loads((silent / 'manifest.json').read_text())['transcript_status'], 'unavailable')
            failure = subprocess.run([sys.executable, str(SCRIPT), '--frame-source', str(media),
                                      '--at', '99', '--save-frame', str(root / 'invalid.jpg')], capture_output=True)
            self.assertNotEqual(failure.returncode, 0)
            self.assertFalse((root / 'invalid.jpg').exists())



class RecoveryTests(unittest.TestCase):
    def test_out_of_range_asr_is_flagged_without_rewriting_evidence(self):
        segments = [{'start': 9.76, 'end': 23.86, 'text': 'fortress'}]
        self.assertTrue(any('outside the video' in w for w in video.asr_warnings(segments, 10.03)))
        self.assertEqual(segments[0]['end'], 23.86)
        self.assertFalse(any('outside the video' in w for w in video.asr_warnings(
            [{'start': 0, 'end': 5, 'text': 'speech'}], 10)))

    def test_download_selects_format_before_metadata_and_checks_real_resolution(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        options = []
        class FakeDownloader:
            def __init__(self, opts):
                options.append(opts)
                self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, *args, **kwargs):
                assert 'height<=720' in self.opts['format']
                return {'duration': 10, 'height': 720, 'title': 'fixture', 'chapters': []}
            def process_info(self, info):
                Path(self.opts['outtmpl'].replace('%(ext)s', 'mp4')).write_bytes(b'fixture')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {'yt_dlp': SimpleNamespace(YoutubeDL=FakeDownloader)}):
            args = SimpleNamespace(max_duration=20, language=None, subtitle=None)
            with patch.object(video, 'probe', return_value={'streams': [{'codec_type': 'video', 'height': 1080}]}):
                with self.assertRaisesRegex(ValueError, '1080p exceeds 720p'):
                    video.acquire('https://example.invalid/video', Path(tmp), args)
            self.assertTrue(all('height<=720' in opts['format'] for opts in options))

    def test_unknown_remote_resolution_is_probed_before_download(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        class DirectDownloader:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, *args, **kwargs):
                return {'url': 'https://example.invalid/movie.mp4'}
        with patch.dict(sys.modules, {'yt_dlp': SimpleNamespace(YoutubeDL=DirectDownloader)}):
            for height in (480, 1080, 0):
                with self.subTest(height=height), patch.object(video, 'probe', return_value={
                        'streams': [{'codec_type': 'video', 'height': height}], 'format': {'duration': '52'}}):
                    if height == 480:
                        info = video.inspect_remote('https://example.invalid/movie.mp4', 60)
                        self.assertEqual((info['height'], info['duration']), (480, 52))
                    else:
                        with self.assertRaisesRegex(ValueError, 'no media download started'):
                            video.inspect_remote('https://example.invalid/movie.mp4', 60)

    def test_duration_diagnostics_distinguish_unknown_from_too_long(self):
        with self.assertRaisesRegex(ValueError, '01:04:02.*01:00:00.*--max-duration 3843'):
            video.validate_duration(3842, 3600, remote=True)
        with self.assertRaisesRegex(ValueError, 'duration is unknown'):
            video.validate_duration(None, 3600, remote=True)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_completed_transcript_survives_visual_failure_and_resume_refuses_tampering(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media, sub = root / 'video.mp4', root / 'captions.srt'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=blue:s=160x120:d=3', '-c:v', 'libx264', str(media)], check=True)
            sub.write_text('1\n00:00:00,000 --> 00:00:03,000\nCheckpoint speech\n')
            args = SimpleNamespace(input=str(media), output=str(root/'run'), subtitle=str(sub),
                                   language=None, model='base', skip_asr=False, interval=1,
                                   max_frames=10, max_scenes=0, max_duration=60, resume=False)
            with patch.object(video, 'make_overviews', side_effect=RuntimeError('simulated visual failure')):
                with self.assertRaisesRegex(ValueError, 'visuals stage failed'):
                    video.prepare(args)
            transcript = root/'run/transcript.json'
            before, mtime = transcript.read_bytes(), transcript.stat().st_mtime_ns
            self.assertIn('Checkpoint speech', before.decode())
            self.assertFalse((root/'run/.prepare.lock').exists())
            args.resume = True
            with patch.object(video, 'captions', side_effect=AssertionError('Must not retranscribe')):
                video.prepare(args)
            self.assertEqual(before, transcript.read_bytes())
            self.assertEqual(mtime, transcript.stat().st_mtime_ns)
            manifest = json.loads((root/'run/manifest.json').read_text())
            self.assertTrue(manifest['overview']['sheets'])
            self.assertLess(manifest['overview']['representative_count'], len(manifest['frames']))
            self.assertTrue(any('similar_to' in f for f in manifest['frames']))
            self.assertEqual(manifest['transcript_source'], 'user-subtitle')
            transcript.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'transcript stage failed'):
                video.prepare(args)
            self.assertEqual(transcript.read_text(), 'changed')
            args.interval = 2
            with self.assertRaisesRegex(ValueError, 'Resume input/options differ'):
                video.prepare(args)


class SamplingTests(unittest.TestCase):
    def test_chapter_anchor_remains_when_scene_scan_is_disabled(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            checkpoint = video.Checkpoints(output, {'fixture': True}, False)
            args = SimpleNamespace(interval=5, max_frames=10, max_scenes=0)
            value = video.sample_times('unused-for-no-scene-scan', 10, {'chapters': [
                {'start_time': 2, 'title': 'Meaningful slide'}, {'start_time': 99, 'title': 'Out of range'}]}, args, checkpoint, output)
            self.assertIn((3, 'chapter'), value['times'])
            self.assertTrue(all(at < 10 for at, _ in value['times']))
            self.assertEqual(value['spacing'], 5)

if __name__ == '__main__':
    unittest.main()
