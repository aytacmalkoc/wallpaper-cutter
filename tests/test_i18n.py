"""Translation contracts, formatting and live binding replacement."""
import string
import unittest
from unittest.mock import Mock
from helpers import core
from wallpaper_cutter.i18n import STRINGS, Translator


class TranslationTests(unittest.TestCase):
    def test_every_translation_preserves_format_parameters(self):
        formatter = string.Formatter()
        for turkish, english in STRINGS.items():
            with self.subTest(message=turkish):
                self.assertTrue(english.strip())
                self.assertEqual({key for _, key, _, _ in formatter.parse(turkish) if key},
                                 {key for _, key, _, _ in formatter.parse(english) if key})

    def test_live_language_switch_preserves_latest_dynamic_text(self):
        widget = Mock()
        translator = Translator('tr')
        translator.bind(widget, 'text', '{count} ekran · {names}', count=2, names='DP-1')
        widget.set_text.assert_called_with('2 ekran · DP-1')
        translator.set_language('en')
        widget.set_text.assert_called_with('2 displays · DP-1')
        translator.bind(widget, 'text', 'Kaydedildi: {directory}', directory='/tmp/image{1}')
        translator.set_language('tr')
        widget.set_text.assert_called_with('Kaydedildi: /tmp/image{1}')
        self.assertEqual(len(translator.bindings), 1)

    def test_error_translation_percent_and_unknown_strings(self):
        translator = Translator('en')
        self.assertEqual(translator.text('%{percent}', percent=70), '70%')
        self.assertEqual(translator.text('Invalid application language.'), 'Invalid application language.')
        translator.set_language('tr')
        self.assertEqual(translator.text('Invalid application language.'), 'Geçersiz uygulama dili.')
        self.assertEqual(translator.text('%{percent}', percent=70), '%70')
        self.assertEqual(translator.text('/tmp/photo{1}.png'), '/tmp/photo{1}.png')

    def test_different_properties_on_same_widget_are_both_updated(self):
        widget = Mock()
        translator = Translator('tr')
        translator.bind(widget, 'label', 'Kaydet')
        translator.bind(widget, 'tooltip_text', 'Ayarlar')
        translator.set_language('en')
        widget.set_label.assert_called_with('Save')
        widget.set_tooltip_text.assert_called_with('Settings')
