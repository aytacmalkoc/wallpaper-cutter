# Changelog

Notable changes to Wallpaper Cutter are recorded here, newest first. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

## 1.0.0 - 2026-10-14

### Added

- Initial public version of the Python/GTK multi-display wallpaper editor.
- One shared image zoom and position, fixed display frames, horizontal/vertical
  centering, per-display crop alignment and bezel compensation.
- Original-size image centering, an independent preview camera starting at 70%,
  full-image overview and dimmed pixels outside display frames.
- PNG, JPEG, WebP, BMP and TIFF input with orientation correction and local
  ImageMagick processing; Unix supports ImageMagick 6 and 7.
- Native-resolution PNG crops, a combined panorama, preserved source image and
  reusable exported layouts, with unique export folders and input validation.
- Turkish/English interface, a separate preferences window, percentage controls,
  saved preferences, application icon and success/error notifications.
- GNOME wallpaper integration, including light/dark settings and previous-image
  restore eligibility.
- Windows, macOS, KDE Plasma, Xfce, Cinnamon and MATE integration adapters, plus
  GDK display discovery and editing/export on other desktops. Platform support
  and prerequisites are described in the README.
- Verified state capture, native apply/restore transactions, rollback and
  protection against restoring over external wallpaper changes.
- Portable configuration directories, local URI handling, file locks and
  per-user launch/install tools with safe menu entries and UTF-8 paths.
- A `src` package layout, bundled assets, Python package metadata, console entry
  point and `python -m wallpaper_cutter` support.
- Isolated image-processing, geometry, GTK, installation, translation and native
  API contract tests; Linux/Windows/macOS GitHub Actions jobs.
- English documentation, contribution and bug-reporting guides, issue forms,
  a pull request template and version tracking.

Native Windows/macOS and non-GNOME Linux integrations have injected API contract
tests. Interactive desktop verification has been performed on GNOME; see
[TESTING.md](docs/TESTING.md) for verification boundaries.
