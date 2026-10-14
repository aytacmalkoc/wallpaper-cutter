"""Isolated fixtures; no real displays or persistent GNOME writes."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import bootstrap
from wallpaper_cutter import core
from wallpaper_cutter import desktop


def monitor(name='left', x=0, y=0, width=100, height=80, scale=1):
    return dict(name=name, x=x, y=y, width=width, height=height,
                pixelWidth=round(width*scale), pixelHeight=round(height*scale), scale=scale)


def memory_background():
    from gi.repository import Gio
    schema = Gio.SettingsSchemaSource.get_default().lookup('org.gnome.desktop.background', True)
    store = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
    desktop.write_values(store, {'picture-uri': 'file:///before-light.png',
                                'picture-uri-dark': 'file:///before-dark.png', 'picture-options': 'zoom'})
    return store


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix='wallpaper-cutter-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.object(core, 'CONFIG', self.root/'config'))
        self.enterContext(patch.object(core, 'STATE', self.root/'state'))

    def source(self, name='source.png', size='220x100', color='gradient:red-blue'):
        path = self.root/name
        core.magick(['-size', size, color, 'PNG24:'+str(path)])
        return path

    def request(self, **overrides):
        image = dict(path=str(self.source()), name='source.png', width=220, height=100)
        monitors = [monitor(), monitor('right', 100)]
        view = dict(zoom=1, panX=0, panY=0)
        frames, _ = desktop.composition(monitors, image, 0, {}, view)
        first = frames[0]
        result = dict(image=image, monitors=monitors, frames=frames, **view, zoomMode='native',
                      gap=0, adjustments={}, imageScale=first['imageScale'], imageX=first['imageX'],
                      imageY=first['imageY'], directory=str(self.root/'exports'), exportName='test')
        result.update(overrides)
        return result
