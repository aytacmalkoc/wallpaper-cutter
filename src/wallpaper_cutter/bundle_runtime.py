"""Locate the private image runtime in a frozen desktop distribution."""
import os
from pathlib import Path
import sys


def configure(root=None, environment=None):
    """Source installs retain their environment; frozen builds use bundled tools."""
    if root is None:
        if not getattr(sys, 'frozen', False):
            return
        root = sys._MEIPASS
    root = Path(root)
    env = os.environ if environment is None else environment
    image = root/'imagemagick'
    env['PATH'] = os.pathsep.join([str(image/'bin'), str(root), env.get('PATH', '')])
    env['MAGICK_CONFIGURE_PATH'] = str(image/'config')
    env['MAGICK_CODER_MODULE_PATH'] = str(image/'modules')
    env['MAGICK_FILTER_MODULE_PATH'] = str(image/'filters')


def package_check(report):
    """Exercise bundled GTK, codecs and real export in disposable directories."""
    import json
    import tempfile
    import traceback
    result = {'version': None, 'checks': [], 'success': False}
    try:
        os.environ['MAGICK_DEBUG'] = 'Module'
        import gi
        import cairo
        gi.require_version('Gtk', '4.0')
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import Gtk, GdkPixbuf, Gio
        from . import __version__, core, desktop
        result['version'] = __version__
        Gtk.init()
        window = Gtk.Window()
        window.set_child(Gtk.Button(icon_name='document-open-symbolic'))
        assert Gtk.IconTheme.get_for_display(window.get_display()).has_icon('document-open-symbolic')
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
        cairo.Context(surface).paint()
        result['checks'].append('gtk-window-icons-cairo')
        with tempfile.TemporaryDirectory(prefix='wallpaper-cutter-package-') as temporary:
            root = Path(temporary)
            core.CONFIG, core.STATE = root/'config', root/'state'
            source = root/'source with spaces ü.png'
            core.magick(['-size', '220x100', 'gradient:red-blue', 'PNG24:'+str(source)])
            image = core.inspect(source)
            GdkPixbuf.Pixbuf.new_from_file(str(core.platform_runtime.file_uri_path(image['preview'])))
            for suffix in ['jpg', 'webp', 'bmp', 'tiff']:
                converted = root/f'codec.{suffix}'
                core.magick([source, str(converted)])
                assert core.inspect(converted)['width'] == 220
                result['checks'].append(suffix+'-decode')
            from .app import Window
            application = Gtk.Application(application_id='io.github.aytacmalkoc.WallpaperCutter.PackageCheck',
                                          flags=Gio.ApplicationFlags.NON_UNIQUE)
            application.register(None)
            editor = Window(application)
            try:
                editor.loaded(image)
                preview = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 500)
                editor.draw(editor.canvas, cairo.Context(preview), 800, 500)
                assert editor.monitors
                result['checks'].append('application-window-image-preview')
            finally:
                editor.closing()
                editor.pool.shutdown(wait=True, cancel_futures=True)
                editor.destroy()
            monitors = [dict(name=name, x=x, y=0, width=100, height=80,
                             pixelWidth=100, pixelHeight=80, scale=1)
                        for name, x in [('left', 0), ('right', 100)]]
            view = dict(zoom=1, panX=0, panY=0)
            frames, _ = desktop.composition(monitors, image, 0, {}, view)
            frame = frames[0]
            request = dict(image=image, monitors=monitors, frames=frames, **view,
                           zoomMode='native', gap=0, adjustments={},
                           imageScale=frame['imageScale'], imageX=frame['imageX'],
                           imageY=frame['imageY'], directory=str(root/'exports'), exportName='check')
            exported = desktop.export(request)
            assert len(exported['outputs']) == 2
            for uri in exported['outputs'].values():
                crop = core.inspect(core.platform_runtime.file_uri_path(uri))
                assert (crop['width'], crop['height']) == (100, 80)
            imported = core.import_layout(Path(exported['directory'])/'layout.json')
            assert imported['image']['width'] == 220
            result['checks'].append('png-preview-two-display-export-layout-import')
        window.destroy()
        result['success'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        modules = Path(os.environ.get('MAGICK_CODER_MODULE_PATH', '/nonexistent'))
        result['runtime'] = {'module_path': str(modules),
                             'modules': sorted(path.name for path in modules.glob('*'))}
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['success'] else 1
