#!/usr/bin/env python3
"""Per-user installation using the active Python runtime on Linux/macOS/Windows."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

PACKAGE_FILES = ('__init__.py', '__main__.py', 'app.py', 'core.py', 'desktop.py', 'i18n.py',
                 'platform_runtime.py', 'file_picker.py', 'bundle_runtime.py', 'backends/__init__.py', 'backends/desktop.py',
                 'backends/windows.py', 'backends/macos.py', 'assets/demo-wallpaper.png',
                 'assets/io.github.local.WallpaperCutter.png')
FILES = ('scripts/run.py', 'LICENSE', 'LICENSE.upstream', 'README.md', 'CHANGELOG.md', 'docs/TESTING.md',
         'docs/INSTALLATION.md', 'docs/PACKAGING.md',
         *(f'src/wallpaper_cutter/{name}' for name in PACKAGE_FILES))
LEGACY_FILES = ('app.py', 'core.py', 'desktop.py', 'i18n.py', 'platform_runtime.py', 'wallpaper_backends.py',
                'native_windows.py', 'native_macos.py', 'file_picker.py', 'demo-wallpaper.png',
                'io.github.local.WallpaperCutter.png')


def targets(system, env, home):
    if system == 'win32':
        root = Path(env.get('LOCALAPPDATA') or home/'AppData/Local')/'WallpaperCutter'
        return root/'app', root/'wallpaper-cutter.cmd', None
    if system == 'darwin':
        return home/'Library/Application Support/WallpaperCutter/app', home/'Applications/Wallpaper Cutter.command', None
    data = Path(env.get('XDG_DATA_HOME') or home/'.local/share')
    return data/'wallpaper-cutter-linux', home/'.local/bin/wallpaper-cutter', data/'applications/wallpaper-cutter.desktop'


def desktop_quote(value):
    return '"'+str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')+'"'


def install(system=None, environment=None, home=None, source=None):
    system = sys.platform if system is None else system
    env = os.environ if environment is None else environment
    home = Path.home() if home is None else Path(home)
    source = Path(__file__).resolve().parent.parent if source is None else Path(source)
    app_dir, launcher, desktop = targets(system, env, home)
    if app_dir.exists() and not (app_dir/'.managed-install').is_file():
        raise RuntimeError(f'Unmanaged application directory was not changed: {app_dir}')
    if launcher.exists():
        text = launcher.read_text(encoding='utf-8')
        if 'wallpaper-cutter-linux/app.py' not in text and '# Wallpaper Cutter managed launcher' not in text:
            raise RuntimeError(f'Unrelated launcher was not changed: {launcher}')
    if desktop and desktop.exists() and 'X-Wallpaper-Cutter-Version=' not in desktop.read_text(encoding='utf-8'):
        raise RuntimeError(f'Unrelated desktop entry was not changed: {desktop}')
    for name in FILES:
        if not (source/name).is_file():
            raise FileNotFoundError(source/name)
    template = source/'packaging/linux/wallpaper-cutter.desktop'
    if desktop and not template.is_file():
        raise FileNotFoundError(template)
    app_dir.mkdir(parents=True, exist_ok=True)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        (app_dir/name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, app_dir/name)
        (app_dir/name).chmod(0o644)
    (app_dir/'.managed-install').touch()
    # Resolving a venv's Python symlink loses its site-packages (notably PyObjC).
    runtime = Path(sys.executable).absolute()
    command = app_dir/'scripts/run.py'
    executable = shutil.which('magick') or shutil.which('convert')
    runtime_paths = list(dict.fromkeys([str(runtime.parent)]+([str(Path(executable).parent)] if executable else [])))
    if system == 'win32':
        escaped = lambda value: str(value).replace('%', '%%')
        path = ';'.join(escaped(p) for p in runtime_paths)
        launcher.write_text('@echo off\r\nsetlocal\r\nchcp 65001 >nul\r\nrem # Wallpaper Cutter managed launcher\r\n'
            f'set "PATH={path};%PATH%"\r\nset "PYGI_DLL_PATH={path};%PYGI_DLL_PATH%"\r\n'
            f'"{escaped(runtime)}" "{escaped(command)}" %*\r\n', encoding='utf-8', newline='')
    else:
        prefix = ':'.join(runtime_paths)
        launcher.write_text('#!/bin/sh\n# Wallpaper Cutter managed launcher\n'
            f'export PATH={shlex.quote(prefix)}:"$PATH"\n'
            f'exec {shlex.quote(str(runtime))} {shlex.quote(str(command))} "$@"\n', encoding='utf-8')
        launcher.chmod(0o755)
    if desktop:
        desktop.parent.mkdir(parents=True, exist_ok=True)
        text = template.read_text(encoding='utf-8')
        # TryExec is a literal path; replace it before Exec (a substring of TryExec).
        text = text.replace('TryExec=@LAUNCHER@', 'TryExec='+str(launcher))
        text = text.replace('Exec=@LAUNCHER@', 'Exec='+desktop_quote(launcher))
        text = text.replace('Icon=io.github.local.WallpaperCutter', 'Icon='+str(app_dir/'src/wallpaper_cutter/assets/io.github.local.WallpaperCutter.png'))
        desktop.write_text(text, encoding='utf-8')
        for executable, arguments in [('desktop-file-validate', [str(desktop)]),
                                      ('update-desktop-database', [str(desktop.parent)])]:
            if shutil.which(executable):
                subprocess.run([executable, *arguments], check=True)
    # Remove only the known obsolete code/assets from installations we own.
    for name in LEGACY_FILES:
        (app_dir/name).unlink(missing_ok=True)
        if name.endswith('.py'):
            for cached in (app_dir/'__pycache__').glob(Path(name).stem+'.*.pyc'):
                cached.unlink()
    try:
        (app_dir/'__pycache__').rmdir()
    except OSError:
        pass  # Do not remove caches or other files we do not own.
    return launcher


if __name__ == '__main__':
    try:
        print('Installed launcher:', install())
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
