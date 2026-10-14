#!/usr/bin/env python3
"""Build a native desktop bundle and its installer on the target OS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT/'src/wallpaper_cutter/assets/io.github.local.WallpaperCutter.png'
TOOL_URL = 'https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage'
TOOL_SHA256 = '95cbe7cce9717fce90c484e34052ee7c7f1d7635b33c12525b4776826a7d29b6'


def run(*command, **options):
    print('Running:', ' '.join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, **options)


def version():
    value = tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('A stable semantic version is required for desktop packages.')
    return value


def image_inventory(executable):
    """Collect codecs as binaries so PyInstaller also resolves their libraries."""
    executable = Path(executable).resolve()
    prefix = executable.parent.parent
    configured = subprocess.check_output([str(executable), '-list', 'configure'], text=True)
    paths = {}
    for line in configured.splitlines():
        fields = line.split(None, 1)
        if len(fields) == 2:
            paths[fields[0]] = fields[1].strip()
    binaries = [(str(executable), 'imagemagick/bin')]
    if not executable.name.lower().startswith('magick'):
        identify = shutil.which('identify')
        if not identify:
            raise RuntimeError('ImageMagick 6 also requires identify.')
        binaries.append((str(Path(identify).resolve()), 'imagemagick/bin'))
    datas = []
    config_dirs = set(prefix.glob('etc/ImageMagick*')) | set(prefix.glob('share/ImageMagick*'))
    for key in ['CONFIGURE_PATH', 'SHARE_PATH']:
        for value in paths.get(key, '').split(os.pathsep):
            if Path(value).is_dir():
                config_dirs.add(Path(value))
    for directory in sorted(config_dirs):
        for path in directory.glob('*.xml'):
            datas.append((str(path), 'imagemagick/config'))
    module_dirs = set(prefix.glob('lib/ImageMagick*/modules*/coders'))
    module_dirs |= set(prefix.glob('lib/*/ImageMagick*/modules*/coders'))
    configured_coders = paths.get('CODER_PATH')
    if configured_coders and Path(configured_coders).is_dir():
        module_dirs.add(Path(configured_coders))
    for directory in sorted(module_dirs):
        for path in directory.iterdir():
            if path.suffix in ('.so', '.dll', '.dylib'):
                binaries.append((str(path), 'imagemagick/modules'))
            elif path.suffix == '.la':
                # ImageMagick's libltdl loader looks up these descriptors first.
                # Do not fall back to the build machine's absolute library path.
                target = ROOT/'build/module-descriptors'/path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                text = re.sub(r"(?m)^libdir=.*$", "libdir=''", path.read_text())
                target.write_text(text)
                datas.append((str(target), 'imagemagick/modules'))
    # IM6 executables are symlinks on Debian; retain the names core.magick uses.
    stage = ROOT/'build/image-bin'
    stage.mkdir(parents=True, exist_ok=True)
    named = []
    for source, destination in binaries:
        if destination == 'imagemagick/bin':
            name = 'magick.exe' if sys.platform == 'win32' else 'magick'
            if not executable.name.lower().startswith('magick'):
                name = 'identify' if Path(source).name.startswith('identify') else 'convert'
            target = stage/name
            shutil.copy2(source, target)
            named.append((str(target), destination))
        else:
            named.append((source, destination))
    return list(dict.fromkeys(named)), list(dict.fromkeys(datas))


def inventory():
    executable = shutil.which('magick') or (shutil.which('convert') if sys.platform != 'win32' else None)
    if not executable:
        raise RuntimeError('Install ImageMagick in the build environment.')
    binaries, datas = image_inventory(executable)
    datas.extend([(str(ROOT/'src/wallpaper_cutter/assets'), 'wallpaper_cutter/assets'),
                  (str(ROOT/'LICENSE'), 'licenses/application'),
                  (str(ROOT/'LICENSE.upstream'), 'licenses/application'),
                  (str(ROOT/'packaging/THIRD_PARTY.md'), 'licenses')])
    # Include package-supplied notices for the runtime libraries.
    if sys.platform == 'linux':
        datas.extend((str(path), 'licenses/system/'+path.parent.name)
                     for path in Path('/usr/share/doc').glob('*/copyright'))
    else:
        prefixes = {Path(sys.executable).parent.parent, Path(executable).resolve().parent.parent}
        if sys.platform == 'darwin':
            prefixes.add(Path(subprocess.check_output(['brew', '--prefix'], text=True).strip()))
        for prefix in sorted(prefixes):
            for path in (prefix/'share/licenses').glob('*'):
                datas.append((str(path), 'licenses/dependencies/'+path.name))
            for path in (prefix/'share/doc').glob('*/COPYING*'):
                datas.append((str(path), 'licenses/dependencies/'+path.parent.name))
    return dict(version=version(), binaries=binaries, datas=datas)


def build_bundle():
    (ROOT/'build').mkdir(exist_ok=True)
    data = inventory()
    (ROOT/'build/bundle-inventory.json').write_text(json.dumps(data, indent=2))
    if sys.platform in ('win32', 'darwin'):
        from PIL import Image
        image = Image.open(ICON)
        image.save(ROOT/'build'/('app.ico' if sys.platform == 'win32' else 'app.icns'))
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', ROOT/'packaging/bundle.spec', cwd=ROOT)


def appimage():
    if platform.machine() != 'x86_64':
        raise RuntimeError('The current AppImage build targets x86_64.')
    directory = ROOT/'build/WallpaperCutter.AppDir'
    if directory.exists():
        shutil.rmtree(directory)
    (directory/'usr').mkdir(parents=True)
    shutil.copytree(ROOT/'dist/wallpaper-cutter', directory/'usr/bin')
    shutil.copy2(ROOT/'packaging/linux/AppRun', directory/'AppRun')
    (directory/'AppRun').chmod(0o755)
    shutil.copy2(ICON, directory/'io.github.local.WallpaperCutter.png')
    (directory/'.DirIcon').symlink_to('io.github.local.WallpaperCutter.png')
    text = (ROOT/'packaging/linux/wallpaper-cutter.desktop').read_text()
    text = text.replace('@LAUNCHER@', 'wallpaper-cutter')
    (directory/'wallpaper-cutter.desktop').write_text(text)
    run('desktop-file-validate', directory/'wallpaper-cutter.desktop')
    tool = ROOT/'build/appimagetool.AppImage'
    if not tool.exists():
        with urllib.request.urlopen(TOOL_URL) as response, tool.open('wb') as output:
            shutil.copyfileobj(response, output)
    if hashlib.sha256(tool.read_bytes()).hexdigest() != TOOL_SHA256:
        raise RuntimeError('appimagetool checksum mismatch; review and update the pinned tool.')
    tool.chmod(0o755)
    output = ROOT/f'dist/release/WallpaperCutter-{version()}-linux-x86_64.AppImage'
    env = dict(os.environ, ARCH='x86_64', APPIMAGE_EXTRACT_AND_RUN='1', VERSION=version())
    run(tool, '--no-appstream', directory, output, env=env)


def deb():
    directory = ROOT/'build/deb'
    if directory.exists():
        shutil.rmtree(directory)
    (directory/'DEBIAN').mkdir(parents=True)
    shutil.copytree(ROOT/'dist/wallpaper-cutter', directory/'opt/wallpaper-cutter')
    (directory/'usr/bin').mkdir(parents=True)
    (directory/'usr/bin/wallpaper-cutter').symlink_to('/opt/wallpaper-cutter/wallpaper-cutter')
    desktop = directory/'usr/share/applications/wallpaper-cutter.desktop'
    desktop.parent.mkdir(parents=True)
    desktop.write_text((ROOT/'packaging/linux/wallpaper-cutter.desktop').read_text().replace('@LAUNCHER@', '/opt/wallpaper-cutter/wallpaper-cutter'))
    icon = directory/'usr/share/icons/hicolor/256x256/apps/io.github.local.WallpaperCutter.png'
    icon.parent.mkdir(parents=True)
    shutil.copy2(ICON, icon)
    copyright_file = directory/'usr/share/doc/wallpaper-cutter/copyright'
    copyright_file.parent.mkdir(parents=True)
    copyright_file.write_text((ROOT/'LICENSE').read_text()+'\n'+(ROOT/'LICENSE.upstream').read_text())
    size = sum(path.stat().st_size for path in directory.rglob('*')
               if path.is_file() and not path.is_symlink()) // 1024
    (directory/'DEBIAN/control').write_text(
        f'Package: wallpaper-cutter\nVersion: {version()}\nArchitecture: amd64\n'
        f'Installed-Size: {size}\n'
        'Maintainer: Wallpaper Cutter contributors\nSection: graphics\nPriority: optional\n'
        'Depends: libc6 (>= 2.36), libgl1, libegl1, libx11-6, libxcb1, libxext6, libxrender1, libwayland-client0, libwayland-egl1, libwayland-cursor0, fontconfig\n'
        'Homepage: https://github.com/aytacmalkoc/wallpaper-cutter\n'
        'Description: Compose one wallpaper across multiple displays\n'
        ' Includes its private Python, GTK and ImageMagick runtime.\n')
    run('dpkg-deb', '--root-owner-group', '--build', directory,
        ROOT/f'dist/release/WallpaperCutter-{version()}-linux-amd64.deb')


def disk_image(staging, output):
    # DiskImages can briefly return EBUSY on hosted macOS runners after signing.
    for attempt in range(3):
        try:
            result = run('hdiutil', 'create', '-volname', 'Wallpaper Cutter',
                         '-srcfolder', staging, '-ov', '-fs', 'HFS+', '-format', 'UDZO',
                         output, capture_output=True, text=True)
            print(result.stdout, flush=True)
            return
        except subprocess.CalledProcessError as error:
            if attempt == 2 or 'Resource busy' not in (error.stderr or ''):
                print(error.stderr, file=sys.stderr)
                raise
            time.sleep(2)


def installer():
    (ROOT/'dist/release').mkdir(exist_ok=True)
    if sys.platform == 'win32':
        compiler = shutil.which('ISCC') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
        run(compiler, '/DAppVersion='+version(), ROOT/'packaging/windows/setup.iss')
    elif sys.platform == 'darwin':
        staging = ROOT/'build/dmg'
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        shutil.copytree(ROOT/'dist/Wallpaper Cutter.app', staging/'Wallpaper Cutter.app', symlinks=True)
        (staging/'Applications').symlink_to('/Applications')
        disk_image(staging, ROOT/f'dist/release/WallpaperCutter-{version()}-macos-{platform.machine()}.dmg')
    else:
        appimage()
        deb()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer-only', action='store_true')
    args = parser.parse_args()
    if not args.installer_only:
        build_bundle()
    installer()
