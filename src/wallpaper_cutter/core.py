#!/usr/bin/env python3
"""Local, cross-platform image processing and composition persistence."""
import json
import shutil
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from . import platform_runtime
from .bundle_runtime import image_executable

CONFIG, STATE = platform_runtime.directories()

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(value, f)
        temporary = f.name
    os.replace(temporary, path)


def parse_monitors(state):
    _, physical, logical, properties = state
    by_name = {monitor[0][0]: monitor for monitor in physical}
    result = []
    logical_coordinates = properties.get('layout-mode', 1) == 1
    for x, y, scale, transform, primary, specs, _ in logical:
        if not specs:
            continue
        # A mirrored group is one independent desktop region.
        spec = specs[0]
        monitor = by_name[spec[0]]
        modes = monitor[1]
        mode = next((mode for mode in modes if mode[6].get('is-current')), None)
        if mode is None:
            continue
        width, height = mode[1:3]
        if transform % 2:
            width, height = height, width
        coordinate_scale = scale if logical_coordinates else 1
        result.append(dict(name=spec[0], description=monitor[2].get('display-name', spec[0]),
                           x=x, y=y, width=width/coordinate_scale, height=height/coordinate_scale,
                           pixelWidth=width, pixelHeight=height, scale=coordinate_scale,
                           transform=transform, primary=primary))
    if not result:
        raise ValueError('GNOME üzerinde etkin ekran bulunamadı.')
    return sorted(result, key=lambda monitor: (monitor['x'], monitor['y'], monitor['name']))


def monitors():
    if sys.platform == 'win32':
        from .backends.windows import WindowsDesktop
        try:
            with WindowsDesktop() as native:
                return native.monitors()
        except (OSError, ValueError):
            return gdk_monitors()
    if sys.platform == 'darwin':
        try:
            from .backends.macos import MacDesktop
            return MacDesktop().monitors()
        except ImportError:
            return gdk_monitors()
    import gi
    from gi.repository import Gio
    desktop_name = os.environ.get('XDG_CURRENT_DESKTOP', '').upper()
    if desktop_name and not any(value in desktop_name for value in ('GNOME', 'UNITY', 'BUDGIE', 'PANTHEON')):
        return gdk_monitors()
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        state = bus.call_sync('org.gnome.Mutter.DisplayConfig',
                          '/org/gnome/Mutter/DisplayConfig',
                          'org.gnome.Mutter.DisplayConfig', 'GetCurrentState',
                          None, None, Gio.DBusCallFlags.NONE, 1000, None).unpack()
        return parse_monitors(state)
    except Exception:
        return gdk_monitors()


def gdk_monitors():
    import gi
    gi.require_version('Gdk', '4.0')
    from gi.repository import Gdk
    display = Gdk.Display.get_default()
    if display is None:
        raise ValueError('No graphical display is available.')
    model = display.get_monitors()
    result = []
    for index in range(model.get_n_items()):
        monitor = model.get_item(index)
        geometry = monitor.get_geometry()
        connector = monitor.get_connector() if hasattr(monitor, 'get_connector') else None
        scale = monitor.get_scale() if hasattr(monitor, 'get_scale') else monitor.get_scale_factor()
        result.append(dict(name=connector or f'Display {index+1}', nativeId=str(index),
                           x=geometry.x, y=geometry.y, width=geometry.width, height=geometry.height,
                           pixelWidth=round(geometry.width*scale), pixelHeight=round(geometry.height*scale),
                           scale=scale))
    if not result:
        raise ValueError('No active displays found.')
    return sorted(result, key=lambda m: (m['x'], m['y'], m['name']))


def magick(arguments, stdin=None):
    arguments = list(map(str, arguments))
    command = image_executable('magick')
    if command:
        invocation = [command, *arguments]
    elif sys.platform != 'win32' and image_executable('convert') and image_executable('identify'):
        # ImageMagick 6 is still packaged by several Linux distributions.
        invocation = [image_executable('identify'), *arguments[1:]] if arguments and arguments[0] == 'identify' else [image_executable('convert'), *arguments]
    else:
        raise RuntimeError('ImageMagick is missing. Install ImageMagick and add it to PATH.')
    try:
        result = subprocess.run(invocation, stdin=stdin,
                                capture_output=True, timeout=120, check=True)
    except FileNotFoundError as error:
        raise RuntimeError('ImageMagick is missing. Install ImageMagick and add it to PATH.') from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Image processing timed out after 120 seconds.') from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.stderr.decode(errors='replace').strip() or 'ImageMagick could not process this image.') from error
    return result.stdout.decode().strip()


@contextmanager
def normalized_image(path):
    # Read an actual local file through stdin, so brackets/colons in filenames
    # cannot be interpreted as ImageMagick selectors or pseudo-image operators.
    with tempfile.TemporaryDirectory(prefix='wallpaper-cutter-') as temporary:
        normalized = Path(temporary) / 'source.miff'
        with Path(path).expanduser().open('rb') as source:
            dimensions = magick(['-[0]', '-auto-orient', '-colorspace', 'sRGB',
                                 '-background', 'black', '-alpha', 'remove', '-alpha', 'off',
                                 '+repage', '-strip', '-write', normalized,
                                 '-format', '%w %h', 'info:'], stdin=source)
        width, height = map(int, dimensions.split())
        yield normalized, width, height


def inspect(path):
    STATE.mkdir(parents=True, exist_ok=True)
    preview = STATE / ('preview-' + uuid.uuid4().hex + '.jpg')
    try:
        with normalized_image(path) as (normalized, width, height):
            magick([normalized, '-filter', 'Lanczos', '-resize', '3840x3840>',
                    '-quality', '93', preview])
    except Exception:
        preview.unlink(missing_ok=True)
        raise
    return dict(path=str(Path(path).expanduser().resolve()), preview=preview.as_uri(),
                width=width, height=height, name=Path(path).name)


def number(value, minimum=-1000000, maximum=1000000):
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('An adjustment is outside the supported range.')
    return value


def validate_settings(data):
    if not isinstance(data, dict) or not isinstance(data.get('adjustments', {}), dict):
        raise ValueError('Settings must contain a monitor adjustment object.')
    adjustments = {}
    for name, value in data.get('adjustments', {}).items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ValueError('Invalid monitor adjustment.')
        adjustments[name] = dict(x=number(value.get('x', 0), -5000, 5000),
                                 y=number(value.get('y', 0), -5000, 5000))
    return dict(version=1, gap=number(data.get('gap', 0), 0, 500), adjustments=adjustments)


def save_settings(data):
    settings = validate_settings(data)
    atomic_json(CONFIG / 'settings.json', settings)
    return settings


def load_settings():
    path = CONFIG / 'settings.json'
    if path.exists():
        return validate_settings(json.loads(path.read_text(encoding='utf-8')))
    # Migrate old export-dependent settings even if the source image is gone.
    session = STATE / 'session.json'
    if session.exists():
        return save_settings(json.loads(session.read_text(encoding='utf-8')))
    return validate_settings({})


def validate_preferences(data):
    if not isinstance(data, dict) or data.get('language', 'tr') not in ('tr', 'en'):
        raise ValueError('Invalid application language.')
    if not isinstance(data.get('showControls', True), bool):
        raise ValueError('Invalid panel visibility setting.')
    return dict(version=1, language=data.get('language', 'tr'),
                previewZoom=number(data.get('previewZoom', .7), .01, 1),
                showControls=data.get('showControls', True))


def load_preferences():
    path = CONFIG/'preferences.json'
    try:
        return validate_preferences(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else validate_preferences({})
    except (OSError, ValueError, TypeError):
        return validate_preferences({})


def save_preferences(data):
    preferences = validate_preferences(data)
    atomic_json(CONFIG/'preferences.json', preferences)
    return preferences


@contextmanager
def wallpaper_lock():
    with platform_runtime.file_lock(STATE/'.wallpaper.lock'):
        yield


def theme_generation():
    path = STATE / 'theme-generation.json'
    return path.read_text(encoding='utf-8') if path.exists() else ''


def restore(theme_changed=False):
    with wallpaper_lock():
        if theme_changed:
            atomic_json(STATE / 'theme-generation.json', uuid.uuid4().hex)
        atomic_json(STATE / 'applied.json', {})
    return {'restored': True}


def export_name(request):
    name = request.get('exportName')
    if name is None or name == '':
        image = request['image']
        # A recorded filename is metadata, not a Windows drive-qualified path.
        stem = PurePosixPath(image['name']).stem if image.get('name') else Path(image['path']).stem
        stem = re.sub(r'[<>:"|?*\\/\x00-\x1f\x7f]', '_', stem)
        name = 'cut-' + stem.encode('utf-8')[:140].decode('utf-8', errors='ignore')
    if not isinstance(name, str):
        raise ValueError('Enter a name for the export.')
    name = name.strip()
    if (not name or name.endswith('.') or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?', name, re.I)
            or re.search(r'[<>:"|?*\\/\x00-\x1f\x7f]', name) or len(name.encode('utf-8')) > 180):
        raise ValueError('Use a folder name up to 180 bytes, without slashes or control characters.')
    return name


def export_directory(parent, name):
    parent.mkdir(parents=True, exist_ok=True)
    for index in range(1, 10000):
        path = parent / (name if index == 1 else f'{name}-{index}')
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise ValueError('Too many exports with this name. Choose a different name.')


def validate_views(views):
    if not isinstance(views, dict) or len(views) > 64:
        raise ValueError('Invalid per-monitor composition.')
    result = {}
    for name, view in views.items():
        if not isinstance(name, str) or not isinstance(view, dict):
            raise ValueError('Invalid monitor view.')
        result[name] = dict(zoom=number(view.get('zoom', 1), .01, 8),
                            panX=number(view.get('panX', 0)), panY=number(view.get('panY', 0)))
    return result


def import_layout(path):
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        path /= 'layout.json'
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('This layout file is too large.')
    data = json.loads(path.read_text(encoding='utf-8'))
    settings = validate_settings(data)
    mode = data.get('zoomMode', 'fit')
    if mode not in ('native', 'fit'):
        raise ValueError('Invalid zoom scale mode.')
    zoom = number(data.get('zoom', 1), .01, 8)
    pan_x, pan_y = number(data.get('panX', 0)), number(data.get('panY', 0))
    if data.get('sourceImage'):
        source_name = data['sourceImage']
        if not isinstance(source_name, str) or Path(source_name).name != source_name or source_name in ('.', '..'):
            raise ValueError('Invalid source image in this export.')
        image_path = (path.parent / source_name).resolve()
        if image_path.parent != path.parent:
            raise ValueError('The source image must be inside the exported folder.')
    else:
        image_path = Path(data['image']['path']).expanduser()
    if not image_path.is_file():
        raise ValueError('The original image is missing. Keep the source image with the exported layout.')
    image = inspect(image_path)
    image['name'] = str(data['image'].get('name') or Path(data['image']['path']).name)
    return dict(image=image, gap=settings['gap'], adjustments=settings['adjustments'],
                zoom=zoom, zoomMode=mode, panX=pan_x, panY=pan_y,
                views=validate_views(data['views']) if data.get('views') is not None else None)


def render(request):
    name = export_name(request)
    generation = theme_generation()
    with normalized_image(request['image']['path']) as (image, width, height):
        return render_normalized(request, image, width, height, name, generation)


def render_normalized(request, image, width, height, directory_name, generation):
    scale = number(request['imageScale'], 0.00001, 10000)
    ix, iy = number(request['imageX']), number(request['imageY'])
    frames = request['frames']
    if not frames or len(frames) > 32:
        raise ValueError('Choose between 1 and 32 displays.')
    crops = []
    names = set()
    for m in frames:
        name = m['name']
        if name in names:
            raise ValueError('Duplicate display name.')
        names.add(name)
        x, y = number(m['x']), number(m['y'])
        w, h = number(m['width'], 1), number(m['height'], 1)
        pw, ph = int(number(m['pixelWidth'], 1, 16384)), int(number(m['pixelHeight'], 1, 16384))
        monitor_scale = number(m.get('imageScale', scale), .00001, 10000)
        monitor_x = number(m.get('imageX', ix))
        monitor_y = number(m.get('imageY', iy))
        box = ((x-monitor_x)/monitor_scale, (y-monitor_y)/monitor_scale,
               (x+w-monitor_x)/monitor_scale, (y+h-monitor_y)/monitor_scale)
        if box[0] < -0.01 or box[1] < -0.01 or box[2] > width+0.01 or box[3] > height+0.01:
            raise ValueError('The image must cover every display. Choose Fill layout or move the image back inside the frames.')
        box = (max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3]))
        crops.append((m, box, (pw, ph)))
    # A unique directory avoids overwriting previous exports, even on failure.
    directory = export_directory(Path(request.get('directory') or STATE / 'exports').expanduser(), directory_name)
    outputs = {}
    try:
        for i, (m, box, size) in enumerate(crops):
            name = re.sub(r'[^A-Za-z0-9_.-]', '_', m['name'])
            path = directory / f'{i+1:02d}-{name}-{size[0]}x{size[1]}.png'
            # Affine mapping keeps fractional source edges; integer -crop would
            # round away small alignment/zoom changes. Viewport fixes output size.
            sx, sy = size[0] / (box[2] - box[0]), size[1] / (box[3] - box[1])
            matrix = f'{sx},0,0,{sy},{-box[0]*sx},{-box[1]*sy}'
            magick([image, '-virtual-pixel', 'edge', '-filter', 'Lanczos',
                    '-define', f'distort:viewport={size[0]}x{size[1]}+0+0',
                    '-distort', 'AffineProjection', matrix, '+repage',
                    '-depth', '8', '-strip', 'PNG24:' + str(path)])
            outputs[m['name']] = path.as_uri()
        source = Path(request['image']['path']).expanduser()
        source_name = 'source' + source.suffix
        shutil.copyfile(source, directory / source_name)
        layout = dict(request, sourceImage=source_name, version=1)
        atomic_json(directory / 'layout.json', layout)
        atomic_json(STATE / 'session.json', request)
        applied = False
        if request.get('apply'):
            with wallpaper_lock():
                if theme_generation() == generation:
                    atomic_json(STATE / 'applied.json', outputs)
                    applied = True
    except Exception:
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
        raise
    return dict(directory=str(directory), outputs=outputs, applied=applied, themeChanged=bool(request.get('apply')) and not applied)
