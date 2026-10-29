import copy
import unittest

from studio import sentences as s
from studio.subtitles import Cue


class SentenceTests(unittest.TestCase):
    def test_join_sort_and_spans(self):
        cues = [Cue(2, 4, 'world.'), Cue(0, 2, 'Hello')]
        self.assertEqual(s.source_text(cues), 'Hello world.')
        rows = s.build_sentences(cues)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['english'], 'Hello world.')
        self.assertEqual((rows[0]['source_start'], rows[0]['source_end']), (0, 12))
        self.assertFalse(rows[0]['timing_estimated'])
        self.assertTrue(s.validate_sentences(cues, rows))

    def test_split_timing_and_quotes(self):
        cues = [dict(start=0, end=20, text='"Go!" Stay here.')]
        rows = s.build_sentences(cues)
        self.assertEqual([r['english'] for r in rows], ['"Go!"', 'Stay here.'])
        self.assertAlmostEqual(rows[0]['end'], 20 * 5 / 16)
        self.assertTrue(all(r['timing_estimated'] for r in rows))
        self.assertTrue(s.validate_sentences(cues, rows))

    def test_abbreviations_and_finance(self):
        text = 'Dr. Mr. Ms. Prof. Jones paid $27.22 in the U.S. market, e.g. stocks etc. today. Done!'
        rows = s.build_sentences([Cue(0, 10, text)])
        self.assertEqual([r['english'] for r in rows], [text[:-6], 'Done!'])

    def test_unpunctuated_marks_and_clipped_start(self):
        cues = [Cue(0, 10, 'and we left then We returned')]
        rows = s.build_sentences(cues, [(11, '.'), (len(cues[0].text), '.')])
        self.assertEqual([r['english'] for r in rows], ['and we left.', 'then We returned.'])
        self.assertTrue(rows[0]['fragment'])
        self.assertIn('clipped', rows[0]['fragment_reason'])
        self.assertTrue(rows[1]['fragment'])
        self.assertEqual(rows[1]['fragment_reason'], 'restored_tail_uncertain')
        self.assertTrue(all(r['restored'] for r in rows))
        self.assertTrue(s.validate_sentences(cues, rows))

    def test_existing_punctuation_wins(self):
        rows = s.build_sentences([Cue(0, 1, 'Hello!')], [(5, '.'), (6, '?')])
        self.assertEqual(rows[0]['english'], 'Hello!')
        self.assertFalse(rows[0]['restored'])

    def test_no_length_cutoff_and_tail(self):
        text = 'Hello ' + 'very ' * 300 + 'long tail'
        rows = s.build_sentences([Cue(0, 100, text)])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['fragment'])
        self.assertIn('terminal', rows[0]['fragment_reason'])
        self.assertEqual(rows[0]['chinese'], '')
        self.assertEqual(s.build_sentences([]), [])
        self.assertTrue(s.validate_sentences([], []))

    def test_validation_rejects_corruption(self):
        cues = [Cue(0, 2, 'Hello, world. Bye!')]
        rows = s.build_sentences(cues)
        for key, value in [('english', 'hello, world.'), ('english', 'Hello world.'),
                           ('english', 'Hello, new world.'), ('end', float('nan')),
                           ('source_start', 1), ('source_end', True)]:
            bad = copy.deepcopy(rows)
            bad[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                s.validate_sentences(cues, bad)
        with self.assertRaises(ValueError):
            s.validate_sentences(cues, rows[:-1])
        with self.assertRaises(ValueError):
            s.validate_sentences(cues, rows + rows)

    def test_bad_inputs(self):
        for cue in [Cue(2, 1, 'Hi'), Cue(0, float('inf'), 'Hi')]:
            with self.assertRaises(ValueError):
                s.build_sentences([cue])
        for mark in [[(2, 'word')], [(999, '.')], [(1, '.')]]:
            with self.assertRaises(ValueError):
                s.build_sentences([Cue(0, 1, 'Hello')], mark)

    def test_restored_period_after_pronoun_not_an_initial(self):
        cues = [Cue(0, 3, 'So do I Then we leave')]
        rows = s.build_sentences(cues, [(7, '.')])
        self.assertEqual([r['english'] for r in rows], ['So do I.', 'Then we leave'])

    def test_initials_and_empty_cues(self):
        cues = [Cue(0, 1, ''), Cue(1, 2, '  '),
                Cue(2, 8, 'J. R. Smith works. Fine?')]
        rows = s.build_sentences(cues)
        self.assertEqual([r['english'] for r in rows], ['J. R. Smith works.', 'Fine?'])
        self.assertTrue(s.validate_sentences(cues, rows))

    def test_validation_recomputes_timing_and_strict_metadata(self):
        cues = [Cue(10, 20, 'Hello. Goodbye.')]
        rows = s.build_sentences(cues)
        for key, value in [('start', 0), ('end', 999), ('start', 10.1),
                           ('fragment', 0), ('restored', 'false'),
                           ('timing_estimated', 1), ('fragment_reason', '<script>'),
                           ('fragment_reason', None), ('timing_estimated', False),
                           ('restored', True), ('fragment', True)]:
            bad = copy.deepcopy(rows)
            bad[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                s.validate_sentences(cues, bad)
        for key in ['fragment', 'restored', 'timing_estimated', 'fragment_reason']:
            bad = copy.deepcopy(rows)
            del bad[0][key]
            with self.assertRaises(ValueError):
                s.validate_sentences(cues, bad)

    def test_nested_cue_interval_envelope(self):
        cues = [Cue(0, 100, 'Hello. We'), Cue(10, 12, 'leave. Next!')]
        rows = s.build_sentences(cues)
        self.assertEqual([r['english'] for r in rows], ['Hello.', 'We leave.', 'Next!'])
        self.assertEqual(rows[1]['end'], 100)
        self.assertLessEqual(rows[1]['start'], rows[1]['end'])
        self.assertTrue(s.validate_sentences(cues, rows))

    def test_original_pronoun_terminal(self):
        rows = s.build_sentences([Cue(0, 10, 'So do I. Then we leave. J. I. Smith agrees.')])
        self.assertEqual([r['english'] for r in rows],
                         ['So do I.', 'Then we leave.', 'J. I. Smith agrees.'])

    def test_restored_tail_does_not_prove_completeness(self):
        cues = [Cue(0, 3, 'We went to the')]
        rows = s.build_sentences(cues, [(14, '.')])
        self.assertEqual(rows[0]['english'], 'We went to the.')
        self.assertTrue(rows[0]['fragment'])
        self.assertEqual(rows[0]['fragment_reason'], 'restored_tail_uncertain')
        self.assertTrue(s.validate_sentences(cues, rows))
        for reason, fragment in [('', False), ('missing_terminal_punctuation', True)]:
            bad = copy.deepcopy(rows)
            bad[0].update(fragment_reason=reason, fragment=fragment)
            with self.assertRaises(ValueError):
                s.validate_sentences(cues, bad)

    def test_tail_uncertainty_only_final_and_without_original_terminal(self):
        for text, marks, reasons in [
            ('We left Then we stayed.', [(7, '.')], ['', '']),
            ('We left. Then we stayed', [(23, '!')], ['', 'restored_tail_uncertain']),
            ('"We left"  ', [(8, '.')], ['restored_tail_uncertain']),
            ('we left', [(7, '.')], ['clipped_start;restored_tail_uncertain']),
            ('We left', [], ['missing_terminal_punctuation']),
            ('"We left."', [], ['']),
        ]:
            with self.subTest(text=text):
                cues = [Cue(0, 3, text)]
                rows = s.build_sentences(cues, marks)
                self.assertEqual([r['fragment_reason'] for r in rows], reasons)
                self.assertTrue(s.validate_sentences(cues, rows))


if __name__ == '__main__':
    unittest.main()
