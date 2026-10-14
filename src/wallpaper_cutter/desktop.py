"""Composition geometry and transactional desktop wallpaper integration."""
from pathlib import Path
import math
from . import core
from . import platform_runtime


def frames(monitors, gap, adjustments):
    """Port of upstream Geometry.js; compensation changes sampling, not layout."""
    result = [dict(monitor) for monitor in monitors]
    for axis, other, size, other_size in [('x', 'y', 'width', 'height'),
                                         ('y', 'x', 'height', 'width')]:
        ordered = sorted(monitors, key=lambda monitor: monitor[axis])
        shifts = {}
        for monitor in ordered:
            shift = 0
            for previous in ordered:
                if previous[axis] >= monitor[axis]:
                    continue
                overlap = min(previous[other]+previous[other_size],
                              monitor[other]+monitor[other_size])-max(previous[other], monitor[other])
                if overlap > 0 and abs(previous[axis]+previous[size]-monitor[axis]) <= 1:
                    shift = max(shift, shifts.get(previous['name'], 0)+gap)
            shifts[monitor['name']] = shift
        for monitor in result:
            monitor[axis] += shifts[monitor['name']]
    for monitor in result:
        offset = adjustments.get(monitor['name'], {})
        monitor['x'] += offset.get('x', 0)
        monitor['y'] += offset.get('y', 0)
    return result


def bounds(monitors):
    if not monitors:
        return dict(x=0, y=0, width=1920, height=1080)
    x = min(m['x'] for m in monitors)
    y = min(m['y'] for m in monitors)
    return dict(x=x, y=y,
                width=max(m['x']+m['width'] for m in monitors)-x,
                height=max(m['y']+m['height'] for m in monitors)-y)


def composition(monitors, image, gap, adjustments, view):
    """One continuous image transform shared by every output."""
    result = frames(monitors, gap, adjustments)
    area = bounds(result)
    scale = view.get('zoom', 1)
    image_x = area['x']+(area['width']-image['width']*scale)/2+view.get('panX', 0)
    image_y = area['y']+(area['height']-image['height']*scale)/2+view.get('panY', 0)
    for frame in result:
        frame.update(imageScale=scale, imageX=image_x, imageY=image_y)
    return result, area


def preview_bounds(frames_, image):
    """Anchor the camera to the layout and native centered source, independent of pan/zoom."""
    area = bounds(frames_)
    if not image or not frames_:
        return area
    photo = dict(x=area['x']+(area['width']-image['width'])/2,
                 y=area['y']+(area['height']-image['height'])/2,
                 width=image['width'], height=image['height'])
    return bounds([area, photo])


def restored_view(saved, monitors=None, image=None, gap=0, adjustments=None, preserve_legacy=False):
    if saved.get('views') is not None:
        core.validate_views(saved['views'])
        return dict(zoom=1, panX=0, panY=0)
    mode = saved.get('zoomMode', 'fit')
    if mode not in ('native', 'fit'):
        raise ValueError('Geçersiz yakınlaştırma ölçeği.')
    if mode == 'fit' and not preserve_legacy:
        # Startup uses the new native default; old files remain intact.
        return dict(zoom=1, panX=0, panY=0)
    zoom = core.number(saved.get('zoom', 1), .01, 8)
    if mode == 'fit':
        # Explicit imports retain the old crop by converting its actual scale.
        area = bounds(frames(monitors, gap, adjustments or {}))
        zoom *= max(area['width']/image['width'], area['height']/image['height'])
        zoom = core.number(zoom, .01, 8)
    return dict(zoom=zoom, panX=core.number(saved.get('panX', 0)),
                panY=core.number(saved.get('panY', 0)))


def export(request):
    """Export native-resolution cuts plus a panorama for GNOME's spanned mode."""
    physical_layout = request['monitors']
    area = bounds(physical_layout)
    density = max(m['scale'] for m in physical_layout)
    width, height = round(area['width']*density), round(area['height']*density)
    if width*height > 48_000_000 or max(width, height) > 32768:
        raise ValueError('Bu ekran düzeni ilk sürümün panorama boyutu sınırını aşıyor.')
    result = core.render(dict(request, apply=False))
    target = Path(result['directory'])/'panorama.png'
    arguments = ['-size', f'{width}x{height}', 'canvas:black']
    for monitor in physical_layout:
        source = platform_runtime.file_uri_path(result['outputs'][monitor['name']])
        x = round((monitor['x']-area['x'])*density)
        y = round((monitor['y']-area['y'])*density)
        right = round((monitor['x']+monitor['width']-area['x'])*density)
        bottom = round((monitor['y']+monitor['height']-area['y'])*density)
        arguments += ['(', source, '-resize', f'{right-x}x{bottom-y}!', ')',
                      '-geometry', f'+{x}+{y}', '-composite']
    core.magick(arguments+['-depth', '8', str(target)])
    result['panorama'] = str(target)
    return result


BACKGROUND_KEYS = ('picture-uri', 'picture-uri-dark', 'picture-options')


def settings():
    from .backends.desktop import select_backend
    return select_backend()


def supports_apply(store):
    return bool(getattr(store, 'supported', True))


def watch_changes(store, callback):
    if hasattr(store, 'capture'):
        from gi.repository import GLib
        def update():
            callback()
            return GLib.SOURCE_CONTINUE
        identifier = GLib.timeout_add_seconds(3, update)
        return lambda: GLib.source_remove(identifier)
    identifier = store.connect('changed', lambda *_: callback())
    return lambda: store.disconnect(identifier)


def _native_record(path):
    try:
        data = core.json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) and isinstance(data.get('backend'), str) else None
    except (OSError, ValueError):
        return None


def _same_shape(value, reference):
    if isinstance(reference, dict):
        return (isinstance(value, dict) and value.keys() == reference.keys()
                and all(_same_shape(value[key], reference[key]) for key in reference))
    if isinstance(reference, list):
        return (isinstance(value, list) and len(value) == len(reference)
                and all(_same_shape(a, b) for a, b in zip(value, reference)))
    if type(reference) in (int, float):
        return type(value) in (int, float)
    return type(value) is type(reference)


def values(store):
    return {key: store.get_string(key) for key in BACKGROUND_KEYS}


def write_values(store, data):
    if not all(store.is_writable(key) for key in BACKGROUND_KEYS):
        raise ValueError('GNOME duvar kâğıdı ayarlarına yazma izni yok.')
    store.delay()
    try:
        for key in BACKGROUND_KEYS:
            if not store.set_string(key, data[key]):
                raise ValueError('GNOME duvar kâğıdı ayarı kaydedilemedi.')
        store.apply()
    except Exception:
        store.revert()
        raise
    from gi.repository import Gio
    Gio.Settings.sync()


def read_background(path):
    try:
        data = core.json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict) and all(isinstance(data.get(key), str) for key in BACKGROUND_KEYS):
            return {key: data[key] for key in BACKGROUND_KEYS}
    except (OSError, ValueError):
        pass
    return None


def can_restore(store=None):
    """Only restore a successful application whose wallpaper is still active."""
    try:
        store = store if store is not None else settings()
    except Exception:
        return False
    if not supports_apply(store):
        return False
    if hasattr(store, 'capture'):
        original = _native_record(core.STATE/'wallpaper-original.json')
        applied = _native_record(core.STATE/'wallpaper-applied.json')
        if original is None or applied is None or original['backend'] != applied['backend']:
            return False
        try:
            return _same_shape(original, applied) and store.capture() == applied
        except Exception:
            return False
    original = read_background(core.STATE/'background-original.json')
    applied = read_background(core.STATE/'background-applied.json')
    if original is None or applied is None:
        return False
    try:
        return values(store) == applied
    except Exception:
        return False


def apply_wallpaper(path, store=None, outputs=None):
    store = store if store is not None else settings()
    path = Path(path).resolve(strict=True)
    if not supports_apply(store):
        raise ValueError(store.reason)
    if hasattr(store, 'capture'):
        with core.wallpaper_lock():
            current = store.capture()
            desired = store.prepare(path, outputs)
            backup = core.STATE/'wallpaper-original.json'
            last = core.STATE/'wallpaper-applied.json'
            previous = _native_record(last)
            if _native_record(backup) is None or current != previous:
                core.atomic_json(backup, current)
            try:
                store.write(desired)
                applied = store.capture()
                if applied != desired:
                    raise RuntimeError('The desktop did not accept the requested wallpaper settings.')
                core.atomic_json(last, applied)
            except Exception as error:
                try:
                    store.write(current)
                    if store.capture() != current:
                        raise RuntimeError('The desktop did not restore the state during rollback.')
                except Exception as rollback:
                    raise RuntimeError(f'{error}; rollback failed: {rollback}. Backup: {backup}') from error
                raise
        return
    current = values(store)
    backup = core.STATE/'background-original.json'
    last = core.STATE/'background-applied.json'
    previous = read_background(last)
    if not backup.exists() or current != previous:
        core.atomic_json(backup, current)
    desired = {'picture-uri': path.as_uri(), 'picture-uri-dark': path.as_uri(),
               'picture-options': 'spanned'}
    write_values(store, desired)
    core.atomic_json(last, desired)


def restore_wallpaper(store=None):
    store = store if store is not None else settings()
    backup = core.STATE/'background-original.json'
    if not can_restore(store):
        raise ValueError('Henüz uygulama üzerinden bir duvar kâğıdı uygulanmadı.')
    if hasattr(store, 'capture'):
        with core.wallpaper_lock():
            # Recheck after acquiring the lock, before changing any desktop values.
            if not can_restore(store):
                raise ValueError('The wallpaper changed outside this app.')
            current = store.capture()
            original = _native_record(core.STATE/'wallpaper-original.json')
            try:
                store.write(original)
                if store.capture() != original:
                    raise RuntimeError('The desktop did not restore the previous wallpaper settings.')
            except Exception as error:
                try:
                    store.write(current)
                    if store.capture() != current:
                        raise RuntimeError('The desktop did not restore the state during rollback.')
                except Exception as rollback:
                    raise RuntimeError(f'{error}; rollback failed: {rollback}') from error
                raise
            (core.STATE/'wallpaper-original.json').unlink()
            (core.STATE/'wallpaper-applied.json').unlink(missing_ok=True)
        return
    write_values(store, read_background(backup))
    backup.unlink()
    (core.STATE/'background-applied.json').unlink(missing_ok=True)
