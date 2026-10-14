# Wallpaper Cutter

A local, cross-platform Python/GTK application for composing one image across
multiple displays. Arrange the image once, preview the individual crops, and
export native-resolution wallpapers or apply them through a supported desktop
backend. Images stay on your computer.

## Features

- One shared image zoom and position across every display.
- Fixed display frames while dragging or zooming the image.
- Horizontal and vertical centering without changing image zoom.
- Original-size centering: 100% means one source pixel per layout unit.
- Per-display crop alignment and bezel compensation without changing system layout.
- A separate preview scale, starting at 70%, and a full-image overview.
- PNG, JPEG, WebP, BMP and TIFF input; orientation correction and local previews.
- Native-resolution PNG crops, a combined panorama, the original source and a
  reusable `layout.json` file. Existing exports are never overwritten.
- Turkish and English, with live language switching and saved preferences.
- Success/error notifications, safe restore eligibility and rollback for native
  multi-display wallpaper operations.

## Platforms and desktop integration

The editor and export pipeline are independent of GNOME. Download packages
include the runtime; source installs require GTK/PyGObject and ImageMagick.

| Environment | Displays / editor / export | Automatic wallpaper application |
| --- | --- | --- |
| Windows 10/11 | Native display rectangles; GTK Win32 | `IDesktopWallpaper`, one crop per display |
| macOS | AppKit display frames with Retina density; GTK macOS | `NSWorkspace`, one crop per display; requires PyObjC Cocoa |
| GNOME / compatible Budgie sessions | Mutter geometry, with GDK fallback | GSettings, combined `spanned` panorama; light/dark settings preserved |
| Cinnamon / MATE | GDK monitor geometry | Their own GSettings schemas, when spanning is supported |
| KDE Plasma | GDK monitor geometry | Plasma's desktop scripting API, per-display crops on the current activity |
| Xfce | GDK monitor geometry | `xfconf-query`, matching connector/workspace wallpaper properties |
| Other Linux desktops and compositors | GDK monitor geometry | Editing/export remains available; automatic apply is disabled with an explanation when no supported backend exists |

A distribution does not need a special integration. Its desktop session and
available APIs determine wallpaper support. Arbitrary shells have no universal
wallpaper-setting API; export the individual crops for their wallpaper tool.
The program does not guess GNOME settings merely because GNOME schemas happen
to be installed.

Windows slideshow backgrounds and non-image Plasma wallpaper plugins are
rejected before applying because their full previous state cannot currently be
restored safely. macOS images are applied to the currently exposed screens and
Spaces; changing every inactive Space is outside the public AppKit API used here.
Windows and macOS adapters require a retrievable previous desktop image.

**Verification:** the complete automated suite and a live GNOME check have been
run on Linux. Windows/macOS and non-GNOME Linux adapters have injected API contract
tests. Their interactive desktop sessions have not been verified in the current
development environment.
See [TESTING.md](docs/TESTING.md). Release packages include their runtime;
Windows/macOS packages are currently unsigned.

## Install

Download the package for your computer from
[GitHub Releases](https://github.com/aytacmalkoc/wallpaper-cutter/releases/latest).
The packages include Python, GTK and ImageMagick.

| System | Download | Install |
| --- | --- | --- |
| Windows 10/11, x64 | `windows-x64-Setup.exe` | Open the installer, then launch Wallpaper Cutter from Start. |
| macOS, Apple Silicon | `macos-arm64.dmg` | Open the disk image and drag Wallpaper Cutter into Applications. |
| macOS, Intel | `macos-x86_64.dmg` | Open the disk image and drag Wallpaper Cutter into Applications. |
| Linux, x86_64 | `linux-x86_64.AppImage` | Allow the file to run as a program, then open it. |
| Debian 12+ / Ubuntu 24.04+, amd64 | `linux-amd64.deb` | Install with your software manager or `sudo apt install ./WallpaperCutter-*.deb`. |

Linux AppImage requires glibc 2.36 or newer (including current Arch/CachyOS).
If FUSE is unavailable, run it with `--appimage-extract-and-run`.
Windows/macOS packages are currently unsigned; signing/notarization is not
included in this release. macOS packages target macOS 15 or newer.

For source setup, see [INSTALLATION.md](docs/INSTALLATION.md). For package builds
and the release process, see [PACKAGING.md](docs/PACKAGING.md).

## Use

1. **Open image**, or press **Ctrl+O**.
2. Drag to compose, scroll to change image zoom, or use arrow keys to nudge.
   Hold **Shift** for ten layout units per keypress.
3. **Center horizontally/vertically** adjusts only that axis. **Center at
   original size** also restores image zoom to 100%.
4. Select a display to adjust its crop alignment. **Bezel gap** omits pixels
   behind touching screen bezels; neither control moves physical displays.
5. Use the small vertical preview control to pull the camera back. It affects
   only the preview. **Show entire image** includes the current zoomed/offset
   source; the actual export geometry stays unchanged.
6. **Export** chooses a new output folder. **Apply wallpaper** exports to the
   app's state directory and uses the detected desktop backend.

The image must cover every display before export/apply is enabled. Source
pixels outside display frames are dimmed. The app does not measure physical
monitor sizes; bezel and alignment adjustments are manual. Output is 8-bit
sRGB PNG. Panoramas are limited to 48 million pixels and 32768 pixels per side.

**Settings** opens a separate window for language, default preview scale and
editing-panel visibility. The percentage field is `− 70% +`; it also accepts
keyboard input. **Save** applies preferences immediately; closing/cancelling
leaves them unchanged. Existing image zoom and position are preserved.

**Import** opens an exported `layout.json` and restores its source, shared zoom,
position, gap and alignment. Legacy shared crops are converted to native scale;
old independent per-display crops open centered at 100% with an explanation.

**Restore previous wallpaper** is available only when the app has a successful
application record, its previous-state backup is valid, and that wallpaper is
still active. External wallpaper changes disable restore. A successful restore
consumes the backup. Native multi-display writes attempt rollback on failure;
rollback failures are reported with the retained backup location.

## Repository layout

```text
src/wallpaper_cutter/       Application package, UI, image processing and state
  backends/                Windows, macOS and Linux desktop integrations
  assets/                  Application icon and demo image
scripts/                   Source launcher and per-user installation tools
packaging/linux/           Linux desktop-entry template
tests/                     Isolated unit, integration and platform contract tests
docs/                      Testing guide, reference source and validation evidence
.github/                   CI workflows, contribution guide and issue/PR templates
pyproject.toml             Python package metadata and console entry point
```

`python scripts/run.py` launches a checkout directly on every supported platform.
For Python packaging workflows, `pyproject.toml` uses the standard `src` layout;
install into a suitable environment with `python -m pip install --no-deps -e .`.
The GTK and ImageMagick runtime requirements still apply. An installed Python
package can also run with `python -m wallpaper_cutter` or `wallpaper-cutter`.
The upstream reference implementation lives in `docs/reference/Geometry.upstream.js`;
it is not a runtime dependency.

## Data locations

| Platform | Configuration | Exports, previews and wallpaper backups |
| --- | --- | --- |
| Linux | `$XDG_CONFIG_HOME/wallpaper-cutter-linux` or `~/.config/wallpaper-cutter-linux` | `$XDG_STATE_HOME/wallpaper-cutter-linux` or `~/.local/state/wallpaper-cutter-linux` |
| Windows | `%APPDATA%\WallpaperCutter` | `%LOCALAPPDATA%\WallpaperCutter\state` |
| macOS | `~/Library/Application Support/WallpaperCutter` | Its `state` subdirectory |

`settings.json` contains alignment/gap; `preferences.json` contains app
preferences; `session.json` restores the last exported composition. Linux paths
are intentionally retained for compatibility. `WALLPAPER_CUTTER_CONFIG_HOME` and
`WALLPAPER_CUTTER_STATE_HOME` can explicitly override directories on any platform.
Closing the app does not remove applied wallpapers or exported files.

## Tests

```sh
bash tests/run.sh
bash tests/run.sh --coverage
```

The complete Linux suite uses a private D-Bus, Xvfb and in-memory desktop
settings. Native platform adapters are tested with injected APIs, never by
changing the test runner's real wallpaper. [TESTING.md](docs/TESTING.md) maps features
to tests and states the limits of platform verification.

## Version history

The first public version is **1.0.0**. See [CHANGELOG.md](CHANGELOG.md) for version
history; changes for the next version are collected under **Unreleased**.

## Contributing and reporting issues

See the [contribution guide](.github/CONTRIBUTING.md) for setup, code organization,
tests and pull requests. For a problem, follow the
[bug-reporting guide](docs/REPORTING_BUGS.md) and choose **Bug report** from
[Issues → New issue](https://github.com/aytacmalkoc/wallpaper-cutter/issues/new/choose).
The **Feature request** form is available
for suggested improvements and additional desktop integrations.

Issue forms and the pull request template are stored in `.github/`. They become
available on GitHub after the files are on the repository's default branch;
Issues must be enabled for the issue forms. No separate template service is needed.

## License and attribution

MIT. The reference project is
[Omarchy Wallpaper Cutter by Renan Tonheiro](https://github.com/renanmt/omarchy-wallpaper-cutter).
The cropping/geometry foundation and demo image were adapted from that project;
its copyright/license notice is retained in `LICENSE.upstream`. The standalone
Python/GTK application, platform integrations and tests are maintained here.
