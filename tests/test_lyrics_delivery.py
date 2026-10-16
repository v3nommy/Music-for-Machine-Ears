import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'music-for-machine-ears/scripts'
SPEC = importlib.util.spec_from_file_location('mme_next', SCRIPTS / 'mme_next.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
LYRICS_SPEC = importlib.util.spec_from_file_location('mme_lyrics', SCRIPTS / 'lyrics.py')
LYRICS = importlib.util.module_from_spec(LYRICS_SPEC)
LYRICS_SPEC.loader.exec_module(LYRICS)


def cli(script, *args, success=True):
    result = subprocess.run([sys.executable, '-B', str(SCRIPTS / script), *map(str, args)],
                            capture_output=True, text=True, encoding='utf-8',
                            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
    if success and result.returncode:
        raise AssertionError(result.stderr)
    return result


class SequentialCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        lrc = self.root / 'synthetic-title.lrc'
        lrc.write_text('[ti:Example]\n[00:00]Example\n[00:01][Instrumental]\n'
                       '[00:02]early\n[00:20]boundary\n[00:20]translation\n[00:40]at end\n', encoding='utf-8')
        self.obj = {'meta': {'duration_s': 40}, 'time_series_1hz': {},
                    'lyrics': LYRICS.parse_lrc(lrc)}
        self.path = self.root / 'object.json'
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.obj), encoding='utf-8')

    def call(self, *args, success=True):
        result = cli('mme_next.py', self.path, '--state-dir', self.root/'state', *args, success=success)
        return json.loads(result.stdout) if success else result

    def assert_metadata_withheld(self, payload):
        for secret in ['synthetic-title', 'Example', 'Instrumental', 'source_file',
                       'lyric_onset_s', 'first_timed_text', 'timed_text', 'onset_basis', 'offset_s']:
            self.assertNotIn(secret, json.dumps(payload))

    def test_blind_boundary_and_summary(self):
        first = self.call()
        self.assertNotIn('lyrics', first)
        self.assert_metadata_withheld(first)
        replay = self.call('--resume')
        replay.pop('resumed'); replay.pop('resume_message')
        self.assertEqual(first, replay)
        self.assertEqual(self.call(success=False).returncode, 2)
        second = self.call('--note', 'Mechanical boundary check; no listening claim.')
        self.assertNotIn('lyrics', second)
        self.assert_metadata_withheld(second)
        summary = self.call('--note', 'Mechanical final check; no listening claim.')
        self.assertEqual(summary['global']['lyrics'], self.obj['lyrics'])
        self.assertEqual(self.call('--resume'), summary)

    def test_reveal_resume_inherits_mode_and_end_inclusive(self):
        first = self.call('--reveal-lyrics')
        self.assertEqual(first['lyrics']['lines'], [{'time_s': 2, 'text': 'early'}])
        self.assertNotIn('boundary', json.dumps(first))
        self.assertNotIn('at end', json.dumps(first))
        self.assert_metadata_withheld(first)
        replay = self.call('--resume')
        self.assertEqual(first['lyrics'], replay['lyrics'])
        second = self.call('--note', 'Mechanical check.')
        self.assertEqual([v['time_s'] for v in second['lyrics']['lines']], [20, 20, 40])
        self.assertNotIn('early', json.dumps(second))
        self.assert_metadata_withheld(second)

    def test_mid_session_mode_switch_rejected_and_reset_allowed(self):
        self.call()
        failure = self.call('--resume', '--reveal-lyrics', success=False)
        self.assertNotEqual(failure.returncode, 0)
        self.assertIn('--reset', failure.stderr)
        self.assertIn('lyrics', self.call('--reset', '--reveal-lyrics'))

    def test_modified_object_rejected_and_reset_allowed(self):
        self.call()
        self.obj['lyrics']['lyric_onset_s'] = 100
        self.save()
        failure = self.call('--resume', success=False)
        self.assertNotEqual(failure.returncode, 0)
        self.assertIn('--reset', failure.stderr)
        self.assertEqual(self.call('--reset')['slice_index'], 1)

    def test_missing_lyrics_default_backward_compatibility(self):
        del self.obj['lyrics']
        self.save()
        self.assertEqual(self.call(), MODULE.make_slice(self.obj, 0, 20))
        self.call('--note', 'Mechanical check.')
        summary = self.call('--note', 'Mechanical check.')
        self.assertNotIn('lyrics', summary['global'])
        self.assertIsNone(self.call('--reset', '--reveal-lyrics')['lyrics'])

    def test_legacy_cursor_acquires_digest_and_blind_mode(self):
        self.call()
        cursor = self.root / 'state/cursor.json'
        state = json.loads(cursor.read_text())
        del state['input_sha256']
        del state['reveal_lyrics']
        cursor.write_text(json.dumps(state))
        self.assertNotIn('lyrics', self.call('--resume'))
        saved = json.loads(cursor.read_text())
        self.assertEqual(len(saved['input_sha256']), 64)
        self.assertFalse(saved['reveal_lyrics'])


if __name__ == '__main__':
    unittest.main()
