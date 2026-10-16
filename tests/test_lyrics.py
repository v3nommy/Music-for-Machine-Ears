import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "music-for-machine-ears" / "scripts" / "lyrics.py"
SPEC = importlib.util.spec_from_file_location("mme_lyrics", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LyricsParserTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-title.lrc'
            path.write_text(text, encoding='utf-8-sig')
            return MODULE.parse_lrc(path)

    def test_parses_offsets_multiple_timestamps_and_metadata(self):
        result = self.parse('[ar:Example]\n[offset:500]\n[00:01.50][00:03.00]First line\n[01:02.250]Second line\n')
        self.assertEqual(result['offset_s'], 0.5)
        self.assertEqual(result['lines'], [
            {'time_s': 2.0, 'text': 'First line'},
            {'time_s': 3.5, 'text': 'First line'},
            {'time_s': 62.75, 'text': 'Second line'},
        ])

    def test_global_offset_and_fraction_scales(self):
        data = self.parse('[offset:200]\n[00:01.5]a\n[00:02.50]b\n[00:03.500]c\n[offset:1000]\n[offset:invalid]')
        self.assertEqual([e['time_s'] for e in data['lines']], [2.5, 3.5, 4.5])
        self.assertEqual(data['lyric_onset_s'], 2.5)
        self.assertIsNone(data['first_timed_text_is_sung'])

    def test_invalid_and_multiple_times(self):
        data = self.parse('[00:60]bad\n[01:60:00]bad\n[00:01.1234]bad\n'
                          '[00:02][00:03]ok\n[00:02]ok\n[100:00]long\n[1:02:03,5]hour')
        self.assertEqual([e['time_s'] for e in data['lines']], [2, 3, 3723.5, 6000])

    def test_credits_and_annotations_are_not_sung(self):
        data = self.parse('[00:00]Song\n[00:01]Lyrics by Example\n[00:02][Instrumental]\n'
                          '[00:03]sample verse\n[ti:Song]')
        self.assertEqual(data['first_timed_text_kind'], 'credit')
        self.assertEqual(data['lyric_onset_s'], 3)
        self.assertEqual(len(data['lines']), 1)
        self.assertEqual(len(data['timed_text']), 4)

    def test_credit_only_unknown_and_negative_offset(self):
        data = self.parse('[00:01]Music: Example\n[offset:-2000]')
        self.assertEqual(data['first_timed_text_s'], 0)
        self.assertIsNone(data['lyric_onset_s'])
        self.assertEqual(data['lines'], [])
        annotation = self.parse('[00:01](Instrumental)')
        self.assertIsNone(annotation['lyric_onset_s'])
        self.assertEqual(annotation['first_timed_text_kind'], 'unknown')

    def test_unmarked_credits_cannot_be_verified(self):
        data = self.parse('[00:01]Unlabelled name')
        self.assertEqual(data['first_timed_text_kind'], 'lyric_candidate')
        self.assertIsNone(data['first_timed_text_is_sung'])
        self.assertIn('unverified', data['onset_basis'])

    def test_same_timestamp_preserves_distinct_lines_and_deduplicates(self):
        data = self.parse('[00:02]second\n[00:01]first\n[00:01]translation\n[00:01]first')
        self.assertEqual([e['text'] for e in data['lines']], ['first', 'translation', 'second'])

    def test_missing_and_empty(self):
        with self.assertRaises(FileNotFoundError):
            MODULE.parse_lrc(SCRIPT.parent / 'nonexistent-file.lrc')
        for text in ['[ar:Example]\n[00:99]bad', '', '[00:01]']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.parse(text)


if __name__ == '__main__':
    unittest.main()
