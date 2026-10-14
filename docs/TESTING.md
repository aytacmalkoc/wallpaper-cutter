# Testing Wallpaper Cutter

Run the complete suite from the repository root:

```sh
bash tests/run.sh
```

The suite uses Python's standard `unittest` module. No Python test framework
needs to be installed. Runtime requirements are Python 3.11+, PyGObject,
pycairo, GTK 4 and ImageMagick. The complete Linux suite currently requires
GTK 4.10+, ImageMagick 7, GNOME desktop GSettings schemas and the
Adwaita icon theme and a font such as DejaVu Sans. Test-only requirements are Xvfb, xauth, D-Bus and
desktop-file-utils. On Arch Linux:

```sh
sudo pacman -S --needed python python-gobject python-cairo gtk4 imagemagick \
  gsettings-desktop-schemas adwaita-icon-theme ttf-dejavu xorg-server-xvfb xorg-xauth \
  dbus desktop-file-utils
```

The runner starts a private D-Bus session and an X11 virtual display. Display
layouts are synthetic, so tests work without a GNOME session, real monitors,
NVIDIA acceleration or a particular display count. XDG configuration, state,
data, cache and runtime paths are disposable. GSettings writes use an in-memory
backend; installation tests use disposable child-process homes. The runner
does not install or modify the user's app or change the user's wallpaper.

GTK initialization failure is an error in the complete runner. Running plain
`python -m unittest discover -s tests -v` without a display explicitly skips the
GTK tests and is **not** equivalent to running the complete suite.

## Feature-to-test map

| Feature / boundary | Automated proof |
| --- | --- |
| Open PNG, JPEG, WebP, BMP and TIFF; preview resizing, alpha flattening and orientation | `test_core.CoreTests.test_all_supported_image_formats_can_be_inspected`, `test_inspect_literal_special_filename_and_preview_limit`, `test_normalization_removes_alpha_and_cleans_temporary_file`, `test_orientation_metadata_is_applied_before_preview_and_crops` |
| Image picker selection, cancellation and invalid-image errors | `test_app.AppTests.test_open_image_file_selection_loads_and_cancel_preserves_current_image`, `test_open_invalid_image_reports_error_and_keeps_loaded_image` |
| Shared pan, drag hit testing and fixed display rectangles | `test_app.AppTests.test_drag_hit_testing_and_shared_transform_leave_display_rectangles_fixed`; desktop shared-output and fixed-camera regression tests |
| Image zoom slider, wheel zoom and limits | `test_app.AppTests.test_scroll_zoom_limits_and_zoom_label`; desktop native scale and shared PNG change tests |
| Arrow keys and Shift nudging | `test_app.AppTests.test_arrow_keys_and_shift_nudge_without_changing_zoom` |
| Horizontal/vertical centering and original-size reset | `test_app.AppTests.test_center_axes_and_original_size_reset` |
| Display selection, independent alignment, bezel gap, reset and persistence | `test_app.AppTests.test_selection_alignment_gap_and_reset_preserve_global_image_view`, `test_alignment_save_failure_reports_error_without_altering_saved_file`; desktop horizontal and vertical bezel tests |
| Negative origins, portrait rotation, fractional density, mirrored outputs and Mutter transport | desktop rotation/mirror test; `test_core.CoreTests.test_physical_coordinate_mutter_layout_and_missing_modes`, `test_monitor_dbus_boundary_unpacks_mutter_result`, `test_fractional_sampling_and_monitor_density_are_preserved_in_pngs` |
| Preview scale, full-image overview, dimmed crop exterior and no changes to export geometry | `test_app.AppTests.test_preview_scale_changes_camera_only_and_overview_contains_offset_source`, `test_draw_dims_exterior_and_keeps_crop_pixels_bright`; fixed-camera regression tests |
| Refresh displays and unavailable/empty layouts | `test_app.AppTests.test_refresh_uses_updated_display_layout_and_resets_selection`, `test_empty_layout_draws_and_disables_export` |
| Separate settings window, saved language/scale/panel preferences and reopening | `test_app.AppTests.test_preferences_separate_window_live_language_and_persisted_defaults` |
| Cancel settings and save failure | `test_app.AppTests.test_preferences_cancel_and_save_failure_preserve_existing_preferences`; preferences round-trip and invalid-file tests |
| Percentage entry, minus/plus steps, range validation and text-only Save | `test_app.AppTests.test_percentage_control_typing_buttons_limits_and_invalid_save` |
| Turkish/English UI, formatting, tooltips, live updates, error translation and CLI language | `test_i18n.TranslationTests`; GTK preferences test; `test_install.InstallTests.test_cli_help_english_and_unknown_arguments`; live GNOME script also checks translated banners |
| Export native PNGs, panorama pixels, copied source, layout/session metadata, unique output folders | desktop native-cuts/panorama and shared-transform round-trip tests; `test_core.CoreTests.test_export_copies_original_source_bytes_and_sanitizes_output_filenames`; GTK selected-folder export test |
| Export cancellation, incomplete coverage and empty editor | `test_app.AppTests.test_export_selected_folder_and_cancel_do_not_apply_wallpaper`, `test_empty_editor_guards_and_uncovered_image_do_not_export`; core pre-write validation tests |
| Export failure cleanup, source integrity and panorama size limits | `test_core.CoreTests.test_render_failure_cleans_partial_export_and_preserves_session`, `test_panorama_limits_reject_before_rendering` |
| Import saved crops and restore zoom, pan, alignment, gap and source | `test_app.AppTests.test_import_saved_crop_restores_source_view_bezel_and_alignment`; desktop export/import round-trip test |
| Import cancellation, malformed/oversized layout, path traversal, source symlink escape and missing source | `test_app.AppTests.test_import_cancel_and_bad_layout_leave_current_composition`; core import rejection tests |
| Legacy shared/independent views and settings migration | desktop legacy-view tests; `test_app.AppTests.test_legacy_independent_layout_opens_at_native_center_and_reports_migration`; core session/settings migration test |
| Apply wallpaper, both light/dark URIs and previous mode; one-time restore eligibility | `test_app.AppTests.test_apply_then_restore_real_export_with_memory_gsettings`; desktop apply/restore tests |
| Failed apply, changed monitor layout, external wallpaper changes, corrupt backup and restore failure | GTK apply/restore failure tests; `test_background.BackgroundTests`; desktop failed-apply/external-change test |
| GSettings write restrictions and rollback of partial transactions | `test_background.BackgroundTests.test_nonwritable_and_failed_transactions_never_commit_partial_values` |
| Busy controls, duplicate-job guards, asynchronous worker/completion failures, retries and shutdown | `test_app.AppTests.test_busy_state_blocks_duplicate_work_editing_and_file_dialogs`, `test_worker_and_completion_errors_report_and_allow_retry`, `test_smoke_option_uses_nonunique_app_and_close_stops_worker_pool` |
| Success/error/dismissible feedback and cleared status errors | `test_app.AppTests.test_feedback_success_error_dismiss_and_error_status_clear` |
| Initial image, restored session and malformed/missing session | `test_app.AppTests.test_initial_image_and_saved_session_load_with_native_view`, `test_malformed_or_missing_session_does_not_crash_or_change_background` |
| Ctrl+O, reuse of the active application window and app icon | `test_app.AppTests.test_icon_open_shortcut_and_application_reuse` |
| Preview/window smoke capture | `test_app.AppTests.test_smoke_produces_preview_and_window_capture_without_background_writes` |
| User installation, reinstall, paths with spaces, launcher version, desktop entry and icon bytes | `test_install.InstallTests.test_install_reinstall_launcher_icon_and_preferences_preservation` |
| Protection of unmanaged app directories and unrelated launchers | remaining installation guard tests |
| Upgrade from the previous flat layout, launcher migration and preservation of unrelated files/caches | `test_install.InstallTests.test_upgrade_from_flat_layout_updates_launcher_and_preserves_unrelated_files` |
| Numeric/file validation and legacy generation/restore utility | core validation and stale-generation tests |
| Linux/Windows/macOS configuration paths, local URI decoding, lock release and portable export names | `test_platform_runtime.RuntimeTests` |
| ImageMagick 6 dispatch and avoiding Windows system `convert.exe` | `test_platform_runtime.RuntimeTests.test_imagemagick_six_dispatch_and_windows_never_uses_system_convert` |
| Windows COM ABI, GUIDs, native monitor geometry, per-display paths, slideshow rejection and apartment cleanup | `test_platform_native.WindowsTests` |
| macOS Retina geometry, image/options restore, native errors and main-thread requirement | `test_platform_native.MacTests` |
| Native transactional apply/restore, read-back verification, failed rollback and malformed/external state | `test_platform_backends.NativeTransactionTests` |
| Desktop routing, Mutter-to-GDK fallback, Plasma scripting, Xfce properties/cycles and desktop-specific GSettings | `test_platform_backends.LinuxBackendTests` |
| Missing platform API, unsupported desktops, usable editing/export and disabled automatic apply | runtime native-routing test and `test_app.AppTests.test_unsupported_desktop_still_edits_and_exports_without_gnome_settings` |
| Modern chooser selection and GTK 4.0 fallback selection/save/cancel/error cleanup | `test_file_picker.FilePickerTests` |
| macOS/Windows installer paths, copied modules and launcher generation | runtime installer tests |

## Desktop distribution checks

`test_bundle_runtime.BundleRuntimeTests` verifies private runtime paths, unchanged
source environments, failure reports and version consistency. Native artifact
checks exercise GTK/icons, all supported image formats, multi-display export and
layout import from the installed package; see [PACKAGING.md](PACKAGING.md).
They do not apply wallpapers to CI desktops.

## Source layout

Production code is imported from `src/wallpaper_cutter`, including the `backends`
subpackage. Test bootstrap resolves the checkout package explicitly. Installation
and CLI tests invoke `scripts/install.sh` and `scripts/run.py`; they also check that
GNOME accepts the generated menu entry and that packaged assets survive installation.
`pyproject.toml` includes the assets in wheels and exposes the same CLI through
`python -m wallpaper_cutter` and the `wallpaper-cutter` console entry point.

## Coverage and focused runs

```sh
# Statement execution report using the standard library; no extra dependency.
bash tests/run.sh --coverage

# Focus on a particular feature while keeping the same isolation.
bash tests/run.sh -k preferences

# Standard-library-only native API/path/installer contracts on any platform.
# These tests inject the native API; they do not need GTK or ImageMagick.
python -m unittest discover -s tests -p 'test_platform_[nr]*.py' -v
```

Coverage reports are written under `.test-coverage/` and ignored by Git. Python
`trace` measures line execution, not branch coverage or visual correctness.
Child-process CLI/install executions are validated by their tests but do not
contribute to the parent process's line report. A high percentage is not a
substitute for the feature assertions above.

## Platform boundaries and optional GNOME check

The headless suite executes real GTK widgets, Cairo drawing, ImageMagick,
filesystem exports/imports and installation. Native file-picker responses and
Mutter's D-Bus response are injected. Actual desktop settings are replaced with
GSettings' memory backend. File-picker/portal appearance and permission prompts,
physical-monitor presentation and compositor-specific behavior still require
manual platform verification; the suite does not claim to test those UI services.

Windows contracts exercise callable ctypes COM vtables, native error codes,
monitor rectangles and memory-release behavior through an injected DLL. macOS
contracts inject NSScreen/NSWorkspace, including display density, wallpaper options,
errors and thread restrictions. Linux adapter contracts inject Plasma scripting and
Xfce properties; generic GSettings tests use memory storage. These prove the adapter
contracts and transaction behavior, not real Windows/macOS/KDE/Xfce sessions.
Only GNOME has additionally been checked in the development desktop session.
Manual checks on other desktops should include mixed-density displays, apply,
restore, picker behavior and wallpaper changes made outside the app.

`tests/check_ui.py` remains an optional live-session rendering check. It assumes
two horizontal 1920×1080 displays; it is intentionally outside test discovery.
Run it only in that matching GNOME environment, with disposable XDG paths:

```sh
XDG_STATE_HOME=/tmp/wallpaper-cutter-live-check/state \
XDG_CONFIG_HOME=/tmp/wallpaper-cutter-live-check/config \
PYTHONDONTWRITEBYTECODE=1 python tests/check_ui.py
```

Its wallpaper writes also use the memory backend.

## GitHub Actions

`.github/workflows/tests.yml` runs `bash tests/run.sh` on pushes, pull requests
and manual dispatch. An Arch Linux container supplies ImageMagick 7 and current
GTK, with read-only repository permissions and no persisted checkout credentials.
Separate Windows and macOS jobs run the standard-library-only portable contracts
with Python 3.13. They do not open GTK windows or change native wallpaper.
The workflow uses the [official checkout action](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python)
and [GitHub's job-container configuration](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container).
The same test command is verified locally. See the repository's
[Actions page](https://github.com/aytacmalkoc/wallpaper-cutter/actions) for CI results
for each pushed commit.
