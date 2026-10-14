"""Modern chooser dispatch and GTK 4.0 native-chooser callback contracts."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from helpers import IsolatedTest
from wallpaper_cutter import file_picker
from gi.repository import Gtk, Gio, GLib


class FilePickerTests(IsolatedTest):
    def test_factory_selects_modern_or_legacy_chooser_by_available_api(self):
        modern = Mock()
        constructor = Mock(return_value=modern)
        with patch.object(file_picker, 'Gtk', SimpleNamespace(FileDialog=constructor)):
            self.assertIs(file_picker.create(title='Open'), modern)
            constructor.assert_called_once_with(title='Open')
        with patch.object(file_picker, 'Gtk', SimpleNamespace()):
            legacy = file_picker.create(title='Open')
            self.assertIsInstance(legacy, file_picker.LegacyDialog)
            self.assertEqual(legacy.title, 'Open')

    def test_legacy_open_preserves_filters_and_returns_selected_local_file(self):
        chooser, callback = Mock(), Mock()
        selected = Gio.File.new_for_path(str(self.root/'image.png'))
        chooser.get_file.return_value = selected
        filters = Gio.ListStore.new(Gtk.FileFilter)
        image_filter = Gtk.FileFilter()
        image_filter.add_pattern('*.png')
        filters.append(image_filter)
        dialog = file_picker.LegacyDialog(title='Open image')
        dialog.set_filters(filters)
        with patch.object(Gtk.FileChooserNative, 'new', return_value=chooser) as constructor:
            dialog.open(None, None, callback)
        self.assertEqual(constructor.call_args.args[2], Gtk.FileChooserAction.OPEN)
        chooser.add_filter.assert_called_once_with(image_filter)
        chooser.set_current_name.assert_not_called()
        chooser.show.assert_called_once()
        chooser.connect.call_args.args[1](chooser, Gtk.ResponseType.ACCEPT)
        result = callback.call_args.args[1]
        self.assertIs(dialog.open_finish(result), selected)
        chooser.destroy.assert_called_once()

    def test_legacy_save_keeps_initial_name_and_reports_cancel_as_error(self):
        chooser, callback = Mock(), Mock()
        dialog = file_picker.LegacyDialog(title='Export', initial_name='cut')
        with patch.object(Gtk.FileChooserNative, 'new', return_value=chooser) as constructor:
            dialog.save(None, None, callback)
        self.assertEqual(constructor.call_args.args[2], Gtk.FileChooserAction.SAVE)
        chooser.set_current_name.assert_called_once_with('cut')
        chooser.connect.call_args.args[1](chooser, Gtk.ResponseType.CANCEL)
        with self.assertRaises(GLib.Error):
            dialog.save_finish(callback.call_args.args[1])
        chooser.get_file.assert_not_called()
        chooser.destroy.assert_called_once()

    def test_legacy_chooser_is_destroyed_even_when_completion_callback_fails(self):
        chooser = Mock()
        callback = Mock(side_effect=RuntimeError('completion failed'))
        dialog = file_picker.LegacyDialog()
        with patch.object(Gtk.FileChooserNative, 'new', return_value=chooser):
            dialog.open(None, None, callback)
        with self.assertRaisesRegex(RuntimeError, 'completion failed'):
            chooser.connect.call_args.args[1](chooser, Gtk.ResponseType.ACCEPT)
        chooser.destroy.assert_called_once()
