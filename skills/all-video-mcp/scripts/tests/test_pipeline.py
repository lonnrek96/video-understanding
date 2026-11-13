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


if __name__ == '__main__':
    unittest.main()
