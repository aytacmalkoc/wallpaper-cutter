# Reporting bugs

Open the repository's **Issues → New issue → Bug report** form. Search existing
issues first; if the same problem is already reported, add your environment and
reproduction details there instead of opening a duplicate.

Check the [platform support table](../README.md#platforms-and-desktop-integration)
and installation requirements. On desktops without a supported wallpaper backend,
the editor and export pipeline remain usable while automatic application is
disabled. Suggestions for additional integration belong in the feature-request
form.

## What to include

- The application version, or the source commit if running a checkout.
- Operating system/version; Linux distribution, desktop/compositor/version and
  Wayland or X11 where applicable.
- How you installed and launched the app, and the Python/GTK/ImageMagick versions
  if available.
- Number and arrangement of displays, their resolution, scaling and rotation
  when relevant to the problem.
- Short reproduction steps, expected behavior and actual behavior. If the issue
  is intermittent, describe its frequency and the last action before it happened.
- For crop/preview problems, image dimensions, format, image zoom and preview
  scale. These are separate controls.
- Exact error text, relevant terminal output and a screenshot if useful.

Public issues and attachments are visible to everyone. Remove private paths,
credentials and personal information from logs, screenshots and exported layout
files. A synthetic image or the bundled demo image is sufficient when the bug
does not depend on a particular source; sharing the original is optional.

## Collect version and terminal output

Run these commands from a source checkout using the same Python environment that
runs the app:

```sh
python scripts/run.py --version
python --version
magick --version
```

If a missing dependency prevents the first command from working, include its
traceback and write `unknown` for the application version. On Linux/macOS with
ImageMagick 6, use `convert --version` instead of `magick --version`.

For the GTK runtime version:

```sh
python -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print('GTK', Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()); print('PyGObject', gi.__version__)"
```

To capture a problem, close the existing application window first, then launch
from a terminal and reproduce it:

```sh
python scripts/run.py
```

Copy the relevant output into the form's **Logs** field. On a per-user Linux
installation, `~/.local/bin/wallpaper-cutter` can be launched from a terminal
instead. On Windows/macOS, use the launcher described in the
[installation guide](../README.md#run-or-install-for-your-user) from a terminal.

An exported `layout.json` can help diagnose composition problems, but may contain
source paths and desktop details. Attach only the relevant, redacted information;
do not delete your settings or wallpaper backups to prepare a report.

## Enabling the forms on GitHub

The definitions live in `.github/ISSUE_TEMPLATE/`. After publishing the project,
enable **Issues** in repository settings and put the definitions on the default
branch. GitHub then displays the bug and feature-request forms when opening an
issue. The chooser configuration directs contributors to those forms; maintainers
can still create a blank issue.

The forms use the `bug` and `enhancement` labels. Ensure those labels exist if you
want GitHub to apply them automatically. No repository URL, owner, project board
or assignee is hard-coded, so the templates also work in forks.

See GitHub's [issue-template configuration guide](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository).
