# Source installation

For contributors and users who prefer running from source. Ready-made packages
are available from [GitHub Releases](https://github.com/aytacmalkoc/wallpaper-cutter/releases/latest).

## Install dependencies

Python 3.11+, GTK 4, PyGObject and pycairo are required. GTK 4.10+ uses the modern
file picker; older GTK 4 uses `FileChooserNative`. ImageMagick 7 is recommended;
ImageMagick 6's `convert`/`identify` commands are also supported on Unix systems.
Windows requires `magick` on PATH so the system's unrelated `convert.exe` is
never used for image processing.

### Linux

Arch Linux and derivatives:

```sh
sudo pacman -S --needed python python-gobject python-cairo gtk4 imagemagick
```

Debian / Ubuntu:

```sh
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 imagemagick
```

Fedora:

```sh
sudo dnf install python3 python3-gobject python3-cairo gtk4 ImageMagick
```

Xfce automatic application also needs `xfconf-query` (usually installed with
Xfce). GNOME-family wallpaper backends use the schemas supplied by the desktop.
KDE integration uses the running `plasmashell` D-Bus service.

### Windows

Use an [MSYS2 UCRT64](https://pygobject.gnome.org/getting_started.html#windows)
environment so GTK, Python and their DLLs come from the same runtime:

```sh
pacman -Syu
pacman -S --needed mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-python-gobject mingw-w64-ucrt-x86_64-python-cairo \
  mingw-w64-ucrt-x86_64-gtk4 mingw-w64-ucrt-x86_64-imagemagick
python scripts/run.py
```

Run these commands in the **UCRT64** terminal. Do not mix the MSYS2 Python
packages with a separate python.org installation. The generated launcher
preserves the runtime binary directory and DLL search path.

### macOS

Follow the [PyGObject macOS setup](https://pygobject.gnome.org/getting_started.html#macos):

```sh
brew install pygobject3 gtk4 imagemagick
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install pyobjc-framework-Cocoa
python scripts/run.py
```

Use the Homebrew Python associated with `pygobject3` when creating the virtual
environment. Cocoa is only required for native display/wallpaper integration;
without it, GDK-based editing/export remains available and automatic apply is
disabled with an explanation.

## Run or install for your user

From the source directory:

```sh
python scripts/run.py
python scripts/run.py --image /path/to/picture.png
python scripts/install.py
```

On Linux/macOS, `python3` may be the appropriate executable. Installation uses
the same Python runtime that ran the installer; it does not install dependencies
or require administrator privileges. It refuses to overwrite unrelated apps or
launchers.

- **Linux:** preserves `~/.local/share/wallpaper-cutter-linux`, creates
  `~/.local/bin/wallpaper-cutter` and a desktop entry. XDG data paths are honored.
  `bash scripts/install.sh` remains a compatibility entry point.
- **Windows:** installs below `%LOCALAPPDATA%\WallpaperCutter\app` and creates
  `%LOCALAPPDATA%\WallpaperCutter\wallpaper-cutter.cmd`.
- **macOS:** installs below `~/Library/Application Support/WallpaperCutter/app`
  and creates `~/Applications/Wallpaper Cutter.command`.

The launcher points at the installing Python/virtual environment. Keep that
runtime available; rerun the installer if you move or remove it.

