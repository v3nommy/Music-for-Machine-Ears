import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

from test_lyrics_delivery import cli


class GeneratorCliTests(unittest.TestCase):
    def test_lyrics_and_default_core_equal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sr = 22050
            t = np.arange(sr * 8) / sr
            audio = root / 'tone.wav'
            wavfile.write(audio, sr, (.15 * np.sin(2 * np.pi * 440 * t)).astype(np.float32))
            lrc = root / 'supplied.lrc'
            lrc.write_text('[00:00]Lyrics: Example\n[00:02.5]sample\n[offset:500]', encoding='utf-8')
            for name, flags in [('default', []), ('optional', ['--lyrics', lrc])]:
                cli('generate-mme.py', '--audio', audio, '--out_dir', root / name, *flags)
                self.assertEqual(len(list((root / name).glob('*.png'))), 4)
            base = json.loads((root / 'default/tone_sensory_object.json').read_text())
            opt = json.loads((root / 'optional/tone_sensory_object.json').read_text())
            self.assertNotIn('lyrics', base)
            self.assertEqual(opt.pop('lyrics')['lyric_onset_s'], 3)
            # Only generation wall-clock metadata can differ between runs.
            for obj in [base, opt]:
                obj['meta'].pop('created_utc')
            self.assertEqual(base, opt)

    def test_bad_lyrics_fail_before_audio_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / 'invalid.lrc'
            invalid.write_text('[ar:Example]\n[00:99]bad', encoding='utf-8')
            invalid_utf8 = root / 'invalid-encoding.lrc'
            invalid_utf8.write_bytes(b'\xff\xfe')
            for lrc in [root / 'absent.lrc', invalid, invalid_utf8]:
                with self.subTest(lrc=lrc.name):
                    failure = cli('generate-mme.py', '--audio', root / 'absent.wav',
                                  '--out_dir', root / 'output', '--lyrics', lrc, success=False)
                    self.assertNotEqual(failure.returncode, 0)
                    self.assertIn('Cannot load --lyrics', failure.stderr)
                    self.assertIn('UTF-8 LRC', failure.stderr)
                    self.assertNotIn('Traceback', failure.stderr)
                    self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
