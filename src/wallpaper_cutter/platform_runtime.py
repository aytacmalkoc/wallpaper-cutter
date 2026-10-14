"""Portable paths, locking and file URI handling (no GUI dependencies)."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse


def directories(system=None, environment=None, home=None):
    system = sys.platform if system is None else system
    env = os.environ if environment is None else environment
    home = Path.home() if home is None else Path(home)
    if system == 'win32':
        config = Path(env.get('APPDATA') or home/'AppData/Roaming')/'WallpaperCutter'
        state = Path(env.get('LOCALAPPDATA') or home/'AppData/Local')/'WallpaperCutter/state'
    elif system == 'darwin':
        config = home/'Library/Application Support/WallpaperCutter'
        state = config/'state'
    else:
        # Preserve the existing Linux installation and all saved compositions.
        config = Path(env.get('XDG_CONFIG_HOME') or home/'.config')/'wallpaper-cutter-linux'
        state = Path(env.get('XDG_STATE_HOME') or home/'.local/state')/'wallpaper-cutter-linux'
    return (Path(env.get('WALLPAPER_CUTTER_CONFIG_HOME') or config),
            Path(env.get('WALLPAPER_CUTTER_STATE_HOME') or state))


def file_uri_path(uri, system=None):
    parsed = urlparse(uri)
    if parsed.scheme != 'file':
        raise ValueError('Only local file URLs are supported.')
    system = sys.platform if system is None else system
    if system == 'win32':
        import nturl2path
        value = ('//'+parsed.netloc if parsed.netloc and parsed.netloc != 'localhost' else '')+parsed.path
        return nturl2path.url2pathname(value)
    if parsed.netloc not in ('', 'localhost'):
        raise ValueError('Remote file URLs are not supported.')
    return unquote(parsed.path)


@contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if sys.platform == 'win32':
            import msvcrt
            if handle.seek(0, 2) == 0:
                handle.write(b'\0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
