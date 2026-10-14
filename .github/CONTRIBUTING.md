# Contributing to Wallpaper Cutter

Contributions to code, translations, documentation and platform verification are
welcome. For a bug, start with the [reporting guide](../docs/REPORTING_BUGS.md).
For a proposed feature, explain the problem and desired behavior in a feature
request before spending time on a large implementation.

## Development setup

1. Fork the repository and create a branch for your change.
2. Install the dependencies for your platform from [README.md](../README.md).
   Use the same Python environment for development and the application.
3. From the repository root, run:

   ```sh
   python scripts/run.py
   ```

There is no requirement to install the app into your user profile for development.
If you prefer an editable Python package, use
`python -m pip install --no-deps -e .` after installing the runtime dependencies.
Run `python -m wallpaper_cutter` or `wallpaper-cutter` in that environment.

## Where changes belong

| Area | Location |
| --- | --- |
| GTK interface, preview and input handling | `src/wallpaper_cutter/app.py` |
| Image processing, validation and persistence | `src/wallpaper_cutter/core.py` |
| Composition, exports and wallpaper transactions | `src/wallpaper_cutter/desktop.py` |
| Native and Linux desktop integrations | `src/wallpaper_cutter/backends/` |
| Turkish/English strings | `src/wallpaper_cutter/i18n.py` |
| Shared runtime helpers and chooser compatibility | `platform_runtime.py` and `file_picker.py` in the application package |
| Icon and example image | `src/wallpaper_cutter/assets/` |
| Installation and source launchers | `scripts/` and `packaging/` |
| Tests | `tests/` |
| Documentation | `README.md` and `docs/` |

Keep a change focused on one problem. Follow the surrounding code's style, use
relative imports inside the application package and avoid adding a dependency
when the existing runtime can do the job. Preserve saved layouts, preferences,
exported images and previous-wallpaper restore behavior.

Translation changes must keep formatting placeholders such as `{count}` intact
and update both languages. A UI change should include screenshots of the result
and remain usable with either language.

## Verification

See [TESTING.md](../docs/TESTING.md) for dependencies, isolation and the feature map.
On Linux, run the complete suite:

```sh
bash tests/run.sh
```

For a focused development run, use `bash tests/run.sh -k keyword`. The
standard-library-only platform contracts also run on Windows and macOS:

```sh
python -m unittest discover -s tests -p "test_platform_[nr]*.py" -v
```

Add a regression test for a bug fix and tests for new behavior. Automated tests
must use temporary files, memory settings or injected desktop APIs; they must not
change the runner's real wallpaper or user data. Do not weaken an existing test
to make an unrelated failure disappear.

For platform-specific changes, report the desktop and runtime you actually used.
Injected API tests do not establish that an interactive native session works.
Include a manual apply/restore check on the affected platform when available,
and clearly state any verification you could not perform.

## Changelog and versions

Add notable user-facing changes to [CHANGELOG.md](../CHANGELOG.md) under
**Unreleased**, using the relevant Added, Changed, Deprecated, Removed, Fixed or
Security section. Describe the resulting behavior rather than listing commits.
Routine internal cleanup does not need a separate entry unless it affects
installation, compatibility or contributors.

When preparing a version, choose its number using
[Semantic Versioning](https://semver.org/), move the relevant Unreleased entries
into a new version section and record the actual release/build date as
`YYYY-MM-DD`. Keep these version declarations and their test expectations aligned:

- `pyproject.toml`: `project.version`.
- `src/wallpaper_cutter/app.py`: the CLI `--version` string.
- `packaging/linux/wallpaper-cutter.desktop`: `X-Wallpaper-Cutter-Version`.

Run the verification appropriate to the change and record platform limitations.
Updating the changelog alone does not create a tag, publish a GitHub release or
change the application's version number.

## Pull requests

Use the pull request template to explain the problem, resulting behavior, linked
issue and verification. Include the commands you ran and their results; mention
remaining failures or untested platforms. Update the README or relevant guide
when installation, support boundaries or user-facing behavior changes.

Contributions are licensed under this project's MIT license. Keep the upstream
copyright and license notices when changing adapted reference material.
