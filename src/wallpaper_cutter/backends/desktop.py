"""Desktop-specific wallpaper adapters; unsupported desktops still allow export."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


class UnsupportedBackend:
    supported = False
    name = 'Export only'
    reason = 'Automatic wallpaper setting is unavailable on this desktop. Export the crops and apply them with your wallpaper tool.'

    def capture(self):
        raise RuntimeError(self.reason)


class NativeBackend:
    supported = True

    def __init__(self, name, factory):
        self.name, self.factory = name, factory

    def capture(self):
        with self.factory() as native:
            return native.capture()

    def prepare(self, panorama, outputs):
        with self.factory() as native:
            return native.prepare(outputs)

    def write(self, state):
        with self.factory() as native:
            native.write(state)


class PlasmaBackend:
    supported = True
    name = 'KDE Plasma'

    def __init__(self, evaluate=None):
        self.evaluate = evaluate or self._evaluate

    @staticmethod
    def _evaluate(script):
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return bus.call_sync('org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell',
                             'evaluateScript', GLib.Variant('(s)', (script,)), None,
                             Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]

    def capture(self):
        script = '''var result = []; var list = desktops();
for (var i=0; i<list.length; i++) {
  var d=list[i]; if (d.activity != currentActivity() || d.screen < 0) continue;
  if (d.wallpaperPlugin != "org.kde.image") throw new Error("Only static image wallpapers can be backed up safely");
  d.currentConfigGroup=["Wallpaper", "org.kde.image", "General"];
  var g=screenGeometry(d.screen);
  result.push({id:String(d.id), screen:d.screen, x:g.x, y:g.y, width:g.width, height:g.height,
    image:d.readConfig("Image", ""), fill:d.readConfig("FillMode", 2)});
}
print(JSON.stringify(result));'''
        entries = json.loads(self.evaluate(script).strip())
        if not entries:
            raise ValueError('No active Plasma desktops found.')
        return dict(backend='plasma', desktops=sorted(entries, key=lambda d: d['id']))

    def prepare(self, panorama, outputs):
        from .. import core
        state = copy.deepcopy(self.capture())
        monitors = core.monitors()
        for desktop in state['desktops']:
            match = [m for m in monitors if all(abs(m[k]-desktop[k]) < 1 for k in ('x', 'y', 'width', 'height'))]
            if len(match) != 1 or not outputs or match[0]['name'] not in outputs:
                raise ValueError('Plasma display geometry does not match the exported crops.')
            desktop.update(image=outputs[match[0]['name']], fill=0)
        return state

    def write(self, state):
        # Values are JSON literals, never shell interpolation or executable input.
        payload = json.dumps(state['desktops'], ensure_ascii=True)
        script = f'''var values={payload};
for (var i=0; i<values.length; i++) {{
  var value=values[i]; var d=desktopById(Number(value.id));
  if (!d) throw new Error("The display layout changed");
  d.wallpaperPlugin="org.kde.image"; d.currentConfigGroup=["Wallpaper","org.kde.image","General"];
  d.writeConfig("Image", value.image); d.writeConfig("FillMode", value.fill); d.reloadConfig();
}}'''
        self.evaluate(script)


class XfceBackend:
    supported = True
    name = 'Xfce'

    @staticmethod
    def query(*arguments):
        return subprocess.run(['xfconf-query', '-c', 'xfce4-desktop', *arguments],
                              check=True, capture_output=True, text=True, timeout=5).stdout.rstrip('\r\n')

    def capture(self):
        properties = self.query('-l').splitlines()
        keys = [k for k in properties if k.endswith('/last-image')]
        if not keys:
            raise ValueError('No Xfce wallpaper properties found.')
        values = {key: self.query('-p', key) for key in keys}
        for key in keys:
            style = key.removesuffix('last-image')+'image-style'
            if style not in properties:
                raise ValueError('Xfce image style could not be backed up.')
            values[style] = self.query('-p', style)
        for key in properties:
            if key.endswith('/backdrop-cycle-enable'):
                values[key] = self.query('-p', key)
        return dict(backend='xfce', values=values)

    def prepare(self, panorama, outputs):
        from ..platform_runtime import file_uri_path
        state = copy.deepcopy(self.capture())
        for key in state['values']:
            if key.endswith('/last-image'):
                # Xfce's monitor group uses the output connector name.
                names = [name for name in outputs or {} if f'/monitor{name}/' in key]
                if len(names) != 1:
                    raise ValueError('Xfce display identifiers do not match the exported crops.')
                state['values'][key] = file_uri_path(outputs[names[0]])
            elif key.endswith('/image-style'):
                state['values'][key] = '3'  # stretched; crops already have the native aspect ratio
            else:
                state['values'][key] = 'false'
        return state

    def write(self, state):
        for key, value in state['values'].items():
            self.query('-p', key, '-s', str(value))


def select_backend():
    if sys.platform == 'win32':
        from .windows import WindowsDesktop
        try:
            with WindowsDesktop() as native:
                native.monitors()
            return NativeBackend('Windows', WindowsDesktop)
        except (OSError, ValueError):
            backend = UnsupportedBackend()
            backend.reason = 'Windows wallpaper integration is unavailable in this session. Editing and export are available.'
            return backend
    if sys.platform == 'darwin':
        try:
            import AppKit
            from .macos import MacDesktop
            return NativeBackend('macOS', MacDesktop)
        except ImportError:
            backend = UnsupportedBackend()
            backend.reason = 'Install pyobjc-framework-Cocoa to enable macOS wallpaper application. Editing and export are available.'
            return backend
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').upper()
    if 'KDE' in desktop:
        return PlasmaBackend()
    if 'XFCE' in desktop and shutil.which('xfconf-query'):
        return XfceBackend()
    from gi.repository import Gio
    if 'CINNAMON' in desktop:
        schema_id = 'org.cinnamon.desktop.background'
    elif 'MATE' in desktop:
        schema_id = 'org.mate.background'
    elif any(name in desktop for name in ('GNOME', 'UNITY', 'BUDGIE', 'PANTHEON')):
        schema_id = 'org.gnome.desktop.background'
    elif not desktop:
        # A blank environment may still be a GNOME session; never guess on other shells.
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            from gi.repository import GLib
            present = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                                   'NameHasOwner', GLib.Variant('(s)', ('org.gnome.Shell',)), None,
                                   Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
        except Exception:
            present = False
        if not present:
            return UnsupportedBackend()
        schema_id = 'org.gnome.desktop.background'
    else:
        return UnsupportedBackend()
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup(schema_id, True) if source else None
    if schema is None:
        return UnsupportedBackend()
    keys = set(schema.list_keys())
    if schema_id == 'org.gnome.desktop.background' and {'picture-uri', 'picture-uri-dark', 'picture-options'} <= keys:
        return Gio.Settings.new_full(schema, None, None)
    if {'picture-filename', 'picture-options'} <= keys:
        return MateBackend(Gio.Settings.new_full(schema, None, None))
    if {'picture-uri', 'picture-options'} <= keys:
        return GSettingsBackend(Gio.Settings.new_full(schema, None, None), 'picture-uri')
    return UnsupportedBackend()


class GSettingsBackend:
    supported = True
    name = 'GSettings desktop'

    def __init__(self, store, key, filename=False):
        self.store, self.key, self.filename = store, key, filename

    def capture(self):
        return dict(backend=self.store.props.schema_id,
                    image=self.store.get_string(self.key), options=self.store.get_string('picture-options'))

    def prepare(self, panorama, outputs):
        state = self.capture()
        # Verify spanned is accepted before making any persistent changes.
        from gi.repository import GLib
        if not self.store.range_check('picture-options', GLib.Variant('s', 'spanned')):
            raise ValueError('This desktop does not support spanning. Export and apply the individual crops instead.')
        return dict(state, image=str(Path(panorama).resolve()) if self.filename else Path(panorama).resolve().as_uri(), options='spanned')

    def write(self, state):
        if not self.store.is_writable(self.key) or not self.store.is_writable('picture-options'):
            raise ValueError('Wallpaper settings are not writable.')
        self.store.delay()
        try:
            if not self.store.set_string(self.key, state['image']) or not self.store.set_string('picture-options', state['options']):
                raise ValueError('Could not save wallpaper settings.')
            self.store.apply()
        except Exception:
            self.store.revert()
            raise
        from gi.repository import Gio
        Gio.Settings.sync()


class MateBackend(GSettingsBackend):
    def __init__(self, store):
        super().__init__(store, 'picture-filename', filename=True)
