# Build on the target OS; GTK introspection and its native libraries are bundled.
import json
from pathlib import Path
import sys

root = Path(SPECPATH).parent
inventory = json.loads((root/'build/bundle-inventory.json').read_text())
a = Analysis(
    [str(root/'packaging/entry.py')], pathex=[str(root/'src')],
    binaries=inventory['binaries'], datas=inventory['datas'],
    hiddenimports=['gi.repository.Gtk', 'gi.repository.Gdk', 'gi.repository.GdkPixbuf',
                   'gi.repository.Gio', 'gi.repository.GLib', 'cairo'] +
                  (['AppKit', 'Foundation', 'objc'] if sys.platform == 'darwin' else []),
    hooksconfig={'gi': {'module-versions': {'Gtk': '4.0', 'Gdk': '4.0'},
                       'icons': ['Adwaita', 'hicolor'], 'themes': ['Adwaita'],
                       'languages': ['en', 'tr']}},
    excludes=['tkinter', 'pytest', 'unittest'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='wallpaper-cutter',
          console=sys.platform == 'linux', debug=False, strip=False, upx=False,
          icon=str(root/'build/app.ico') if sys.platform == 'win32' else None)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='wallpaper-cutter')
if sys.platform == 'darwin':
    app = BUNDLE(collection, name='Wallpaper Cutter.app',
                 icon=str(root/'build/app.icns'),
                 bundle_identifier='io.github.aytacmalkoc.WallpaperCutter',
                 info_plist={'CFBundleShortVersionString': inventory['version'],
                             'CFBundleVersion': inventory['version'],
                             'NSHighResolutionCapable': True})
