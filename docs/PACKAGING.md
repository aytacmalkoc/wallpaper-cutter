# Desktop packages and releases

The application is frozen on each target OS. GTK introspection files, native
libraries, icons, codecs and ImageMagick configuration are included. No user
Python/GTK installation is needed. The source installer remains available.

## Build

Linux x86_64 uses Debian 12 (glibc 2.36) as its minimum build/runtime baseline:

```sh
docker build -t wallpaper-cutter-build -f packaging/linux/Dockerfile .
docker run --rm -v "$PWD:/work" wallpaper-cutter-build python packaging/build.py
```

Windows uses MSYS2 UCRT64 GTK/PyGObject/ImageMagick/PyInstaller/Pillow and Inno
Setup 6. macOS uses the Homebrew Python paired with PyGObject, a virtual
environment with system site packages, PyInstaller, Pillow and PyObjC Cocoa.
Run `python packaging/build.py` in the appropriate native build environment.
The exact build commands are in `.github/workflows/packages.yml`.

Outputs are below `dist/release`. AppImage uses a checksum-pinned official
appimagetool; a changed upstream binary fails the build until its digest is
reviewed. AppImage packaging does not require FUSE. Windows installs per-user;
uninstallation preserves settings and exported wallpapers. The macOS DMG
contains an app bundle and an Applications shortcut. Intel and Apple Silicon
are separate builds, currently targeting macOS 15+.

Runtime libraries retain their own licenses. Package-supplied notices and
upstream source links accompany the bundles; see `packaging/THIRD_PARTY.md`.
Windows signing and Apple signing/notarization require maintainer credentials
and are not configured. These initial binaries are unsigned.

## Verification

Every PR builds the four native targets. Each executable's internal
`--package-check <report.json>` runs in temporary directories and exercises GTK
windows/icons, Cairo, the real editor window and preview drawing, PNG preview,
JPEG/WebP/BMP/TIFF codecs, a two-display
export and layout import. It never applies a wallpaper.

Linux checks use fresh Debian containers with no Python/GTK/ImageMagick installed;
both AppImage extraction and deb install/uninstall are exercised. The Linux tests
also run with a deliberately failing host `magick` sentinel on PATH, verifying
that bundled ImageMagick 6 tools cannot be overridden by an installed version 7.
Windows checks
install the setup executable in a path with spaces, remove MSYS2 from PATH, run
the app and uninstall. macOS checks mount the DMG, copy the app to a separate
location and remove Homebrew from PATH. Native wallpaper integration still
needs interactive verification on real desktops.

## Publish

1. Update the package version, `__version__`, desktop entry and changelog.
2. Open a PR. Require the existing tests and all desktop package jobs to pass.
3. Merge through the protected main branch. Wait for its tests and package builds.
4. Download artifacts from **Desktop packages** for that exact main commit.
5. Generate `SHA256SUMS.txt` for all installers. Create a draft release with a
   `vX.Y.Z` tag targeting the verified commit; attach installers and checksums.
6. Verify the asset list and publish the draft. Never publish failed, missing or
   untested packages. Do not rebuild artifacts on an unrelated commit.

Releases are published explicitly by the maintainer, rather than by untrusted
PR workflows. Build workflows have read-only repository permissions.
