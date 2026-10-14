"""GTK 4.0+ asynchronous chooser compatibility without requiring GTK 4.10."""
from types import SimpleNamespace
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib


def create(**kwargs):
    if hasattr(Gtk, 'FileDialog'):
        return Gtk.FileDialog(**kwargs)
    return LegacyDialog(**kwargs)


class LegacyDialog:
    def __init__(self, title='', initial_name=None):
        self.title, self.initial_name = title, initial_name
        self.filters = None
        self.chooser = None

    def set_filters(self, filters):
        self.filters = filters

    def open(self, parent, cancellable, callback):
        self._show(parent, Gtk.FileChooserAction.OPEN, callback)

    def save(self, parent, cancellable, callback):
        self._show(parent, Gtk.FileChooserAction.SAVE, callback)

    def _show(self, parent, action, callback):
        self.chooser = Gtk.FileChooserNative.new(self.title, parent, action, None, None)
        if self.initial_name and action == Gtk.FileChooserAction.SAVE:
            self.chooser.set_current_name(self.initial_name)
        if self.filters:
            for index in range(self.filters.get_n_items()):
                self.chooser.add_filter(self.filters.get_item(index))
        def complete(chooser, response):
            result = SimpleNamespace(file=chooser.get_file() if response == Gtk.ResponseType.ACCEPT else None)
            try:
                callback(self, result)
            finally:
                chooser.destroy()
        self.chooser.connect('response', complete)
        self.chooser.show()

    def open_finish(self, result):
        if result.file is None:
            raise GLib.Error('File selection was cancelled.')
        return result.file

    save_finish = open_finish
