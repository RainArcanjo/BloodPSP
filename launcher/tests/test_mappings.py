import tempfile
from pathlib import Path
import unittest

from bloodpsp_launcher.config import ConfigError, ConfigDocument
from bloodpsp_launcher.mappings import ChordCapture, Mapping, chord, read_mappings, write_mappings
from bloodpsp_launcher.profiles import ProfileStore
from bloodpsp_launcher.resources import default_document


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.capture = ChordCapture()
        self.capture.update(set(), 0)

    def test_single_waits_until_release_plus_200ms(self):
        c = self.capture
        self.assertIsNone(c.update({'cross'}, 10))
        self.assertIsNone(c.update({'cross'}, 1000))
        self.assertIsNone(c.update(set(), 1100))
        self.assertIsNone(c.update(set(), 1299))
        self.assertEqual(c.update(set(), 1300), ('cross',))

    def test_combination_waits_for_every_button_to_be_up(self):
        c = self.capture
        c.update({'cross'}, 10)
        c.update({'cross', 'r'}, 50)
        self.assertIsNone(c.update({'r'}, 200))
        self.assertIsNone(c.update({'r'}, 1000))
        c.update(set(), 1050)
        self.assertIsNone(c.update(set(), 1249))
        self.assertEqual(c.update(set(), 1250), ('cross', 'r'))

    def test_sequential_buttons_are_not_a_combination(self):
        c = self.capture
        c.update({'cross'}, 10)
        c.update(set(), 50)
        c.update({'r'}, 100)
        c.update(set(), 150)
        self.assertEqual(c.update(set(), 350), ('r',))

    def test_does_not_union_buttons_that_never_overlap(self):
        c = self.capture
        c.update({'cross', 'r'}, 10)
        c.update({'r'}, 50)
        c.update({'r', 'l'}, 80)
        c.update(set(), 100)
        self.assertEqual(c.update(set(), 300), ('l', 'r'))

    def test_held_opening_buttons_and_reserved_buttons_are_ignored(self):
        c = ChordCapture()
        c.update({'cross'}, 0)
        c.update(set(), 50)
        self.assertIsNone(c.update(set(), 300))
        c.update({'start'}, 400)
        self.assertIsNone(c.update(set(), 700))


class MappingTests(unittest.TestCase):
    def test_native_mapping_roundtrip_and_delete_preserve_other_settings(self):
        doc = default_document()
        doc.set('Custom', 'Keep', '"unknown; value"')
        values = [Mapping(chord(('r', 'cross')), 'Jump'), Mapping(('square',), 'Open')]
        write_mappings(doc, values)
        parsed = ConfigDocument(doc.to_bytes())
        self.assertEqual(read_mappings(parsed), values)
        write_mappings(parsed, values[:1])
        self.assertEqual(parsed.get('PSP Controls', 'Mapping1'), '')
        self.assertEqual(parsed.get('Custom', 'Keep'), '"unknown; value"')
        self.assertEqual(parsed.number('Screen Setup', 'ScreenWidth'), 480)

    def test_duplicate_combo_and_unknown_actions_rejected(self):
        doc = default_document()
        with self.assertRaises(ConfigError):
            write_mappings(doc, [Mapping(('r', 'cross'), 'Jump'), Mapping(('cross', 'r'), 'Open')])
        with self.assertRaises(ConfigError):
            write_mappings(doc, [Mapping(('cross',), 'not an action')])
        with self.assertRaises(ConfigError):
            write_mappings(doc, [Mapping(('start',), 'Jump')])

    def test_empty_table_means_all_buttons_unbound(self):
        doc = default_document()
        write_mappings(doc, [])
        self.assertEqual(read_mappings(doc), [])
        self.assertEqual(doc.number('PSP Controls', 'Version'), 1)

    def test_profile_survives_restart_without_replacing_video(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'profiles.json'
            doc = default_document()
            write_mappings(doc, [Mapping(('cross', 'r'), 'Jump')])
            doc.set('Controls', 'JoystickAnalogScale0', -65536)
            ProfileStore(path).save('My controls', doc, 'current')
            target = default_document()
            target.set('Screen Setup', 'ScreenWidth', 320)
            store = ProfileStore(path)
            store.apply('My controls', target)
            self.assertEqual(read_mappings(target), [Mapping(('cross', 'r'), 'Jump')])
            self.assertEqual(target.number('Controls', 'JoystickAnalogScale0'), -65536)
            self.assertEqual(target.number('Screen Setup', 'ScreenWidth'), 320)
            store.remove('My controls')
            self.assertEqual(ProfileStore(path).load(), {})
