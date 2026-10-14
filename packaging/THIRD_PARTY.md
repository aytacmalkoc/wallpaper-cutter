# Bundled runtime

Desktop packages contain Python, GTK/GLib/Pango, PyGObject, Cairo, GdkPixbuf,
ImageMagick and their required native libraries. Their package-supplied notices
are included below `licenses`. These components retain their original licenses;
the application's MIT license does not replace them.

Source code, license texts and upstream releases:

- Python (PSF): https://www.python.org/downloads/source/
- GTK (LGPL): https://download.gnome.org/sources/gtk/
- GLib (LGPL): https://download.gnome.org/sources/glib/
- PyGObject (LGPL): https://download.gnome.org/sources/pygobject/
- Cairo (LGPL/MPL): https://cairographics.org/releases/
- Pango (LGPL): https://download.gnome.org/sources/pango/
- GdkPixbuf (LGPL): https://download.gnome.org/sources/gdk-pixbuf/
- ImageMagick: https://imagemagick.org/script/license.php
- MSYS2 dependency sources: https://github.com/msys2/MINGW-packages
- Homebrew dependency sources: https://github.com/Homebrew/homebrew-core
- Debian dependency sources: https://sources.debian.org/

Libraries remain separate files in the application bundle. Rebuilding packages
with modified libraries is supported by `packaging/build.py` and the documented
build environment. Windows/macOS packages are currently unsigned.
