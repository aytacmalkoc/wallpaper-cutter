"""GTK behavior on synthetic displays, runnable with Xvfb and a private D-Bus."""
import copy
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from helpers import IsolatedTest, memory_background, monitor
from wallpaper_cutter import core
from wallpaper_cutter import desktop
from wallpaper_cutter import app
import cairo
from gi.repository import Gtk, Gio, GLib, Gdk


def pump_until(predicate, timeout=5):
    deadline = time.monotonic()+timeout
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        for _ in range(8):
            if not context.pending():
                break
            context.iteration(False)
        if predicate():
            return
        time.sleep(.002)
    raise AssertionError('Timed out waiting for GTK/worker completion')


GTK_AVAILABLE = Gtk.init_check()
if os.environ.get('WALLPAPER_CUTTER_REQUIRE_GTK') == '1' and not GTK_AVAILABLE:
    raise RuntimeError('The complete suite requires a working GTK display; Xvfb did not initialize.')


@unittest.skipUnless(GTK_AVAILABLE, 'GTK display unavailable; use bash tests/run.sh')
class AppTests(IsolatedTest):
    @classmethod
    def setUpClass(cls):
        cls.application = Gtk.Application(application_id='io.github.local.WallpaperCutter.UnitTests',
                                          flags=Gio.ApplicationFlags.NON_UNIQUE)
        cls.application.register(None)

    def setUp(self):
        super().setUp()
        self.layout = [monitor(), monitor('right', 100)]
        self.enterContext(patch.object(core, 'monitors', return_value=copy.deepcopy(self.layout)))
        self.store = memory_background()
        self.before_background = desktop.values(self.store)
        self.enterContext(patch.object(desktop, 'settings', return_value=self.store))
        self.enterContext(patch.object(app, 'LOG'))
        self.window = self.new_window()
        self.image = core.inspect(self.source(size='400x300'))
        self.window.loaded(self.image)
        self.window.update_buttons()
        self.window.present()
        pump_until(lambda: self.window.canvas.get_width() > 100)

    def new_window(self, **kwargs):
        window = app.Window(self.application, **kwargs)
        def cleanup():
            window.closing()
            window.pool.shutdown(wait=True, cancel_futures=True)
            if window.preferences_window:
                window.preferences_window.destroy()
            window.destroy()
        self.addCleanup(cleanup)
        return window

    def settle(self):
        pump_until(lambda: not self.window.busy)

    def draw(self, width=800, height=500):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        self.window.draw(self.window.canvas, cairo.Context(surface), width, height)
        surface.flush()
        return surface

    def dialog(self, operation='open', selected=None, error=None):
        dialog = Mock()
        finish = getattr(dialog, operation+'_finish')
        if error:
            finish.side_effect = error
        else:
            finish.return_value.get_path.return_value = selected
        def respond(parent, cancellable, callback):
            callback(dialog, object())
        getattr(dialog, operation).side_effect = respond
        return dialog

    def test_open_image_file_selection_loads_and_cancel_preserves_current_image(self):
        other = self.source('other.png', '360x240')
        with patch.object(Gtk, 'FileDialog', return_value=self.dialog(selected=str(other))):
            self.window.open_image()
            self.settle()
        self.assertEqual(self.window.picture['path'], str(other))
        for dialog in [self.dialog(selected=None), self.dialog(error=GLib.Error('cancelled'))]:
            with patch.object(Gtk, 'FileDialog', return_value=dialog):
                before = self.window.picture
                self.window.open_image()
                self.assertIs(self.window.picture, before)
                self.assertFalse(self.window.busy)

    def test_open_invalid_image_reports_error_and_keeps_loaded_image(self):
        broken = self.root/'broken.png'
        broken.write_bytes(b'bad image')
        with patch.object(Gtk, 'FileDialog', return_value=self.dialog(selected=str(broken))):
            before = self.window.picture
            self.window.open_image()
            self.settle()
        self.assertIs(self.window.picture, before)
        self.assertTrue(self.window.status.has_css_class('error'))
        self.assertTrue(self.window.open_button.get_sensitive())

    def test_drag_hit_testing_and_shared_transform_leave_display_rectangles_fixed(self):
        original_frames = self.window.composition()[0]
        self.draw()
        camera = (self.window.view_origin, self.window.view_scale)
        ox, oy = self.window.view_origin
        scale = self.window.view_scale
        self.window.drag_begin(None, ox+150*scale, oy+40*scale)
        self.assertEqual(self.window.selected, 1)
        self.window.drag_update(None, 24, -12)
        self.assertAlmostEqual(self.window.view['panX'], 24/scale)
        self.assertAlmostEqual(self.window.view['panY'], -12/scale)
        changed = self.window.composition()[0]
        for a, b in zip(original_frames, changed):
            self.assertEqual([a[k] for k in ['x', 'y', 'width', 'height']],
                             [b[k] for k in ['x', 'y', 'width', 'height']])
        self.assertEqual(len({(f['imageX'], f['imageY'], f['imageScale']) for f in changed}), 1)
        self.draw()
        self.assertEqual((self.window.view_origin, self.window.view_scale), camera)

    def test_scroll_zoom_limits_and_zoom_label(self):
        self.window.zoom_slider.set_value(2)
        self.assertTrue(self.window.scroll(None, 0, -1))
        self.assertAlmostEqual(self.window.view['zoom'], 2.05)
        self.assertEqual(self.window.zoom_label.get_text(), '%205')
        self.window.scroll(None, 0, -1000)
        self.assertEqual(self.window.view['zoom'], 8)
        self.window.scroll(None, 0, 1000)
        self.assertEqual(self.window.view['zoom'], .01)
        self.assertFalse(self.window.apply_button.get_sensitive())

    def test_arrow_keys_and_shift_nudge_without_changing_zoom(self):
        self.window.zoom_slider.set_value(1.5)
        for key, modifiers in [(Gdk.KEY_Right, 0), (Gdk.KEY_Down, Gdk.ModifierType.SHIFT_MASK),
                               (Gdk.KEY_Left, 0), (Gdk.KEY_Up, 0)]:
            self.assertTrue(self.window.key(None, key, 0, modifiers))
        self.assertEqual(self.window.view, dict(zoom=1.5, panX=0, panY=9))
        self.assertFalse(self.window.key(None, Gdk.KEY_a, 0, 0))

    def test_center_axes_and_original_size_reset(self):
        self.window.zoom_slider.set_value(2)
        self.window.view.update(panX=20, panY=-11)
        self.window.center_x_button.emit('clicked')
        self.assertEqual(self.window.view, dict(zoom=2, panX=0, panY=-11))
        self.window.view['panX'] = 9
        self.window.center_y_button.emit('clicked')
        self.assertEqual(self.window.view, dict(zoom=2, panX=9, panY=0))
        self.window.fill_button.emit('clicked')
        self.assertEqual(self.window.view, dict(zoom=1, panX=0, panY=0))

    def test_selection_alignment_gap_and_reset_preserve_global_image_view(self):
        self.window.zoom_slider.set_value(1.8)
        before = copy.deepcopy(self.window.view)
        self.window.monitor_selector.set_selected(1)
        self.assertEqual(self.window.view, before)
        self.window.offset_x.set_value(13)
        self.window.offset_y.set_value(-7)
        self.window.gap_spin.set_value(12)
        frames = self.window.composition()[0]
        self.assertEqual((frames[1]['x'], frames[1]['y']), (125, -7))
        self.assertEqual(core.load_settings()['adjustments']['right'], dict(x=13, y=-7))
        self.window.reset()
        self.assertEqual(self.window.adjustments['right'], dict(x=0, y=0))
        self.assertEqual(self.window.gap, 12)
        self.assertEqual(self.window.view, before)
        self.assertEqual(self.window.monitors, self.layout)

    def test_alignment_save_failure_reports_error_without_altering_saved_file(self):
        core.save_settings(dict(gap=4, adjustments={}))
        saved = (core.CONFIG/'settings.json').read_bytes()
        with patch.object(core, 'save_settings', side_effect=OSError('read only')):
            self.window.offset_x.set_value(5)
        self.assertIn('read only', self.window.status.get_text())
        self.assertEqual((core.CONFIG/'settings.json').read_bytes(), saved)

    def test_preview_scale_changes_camera_only_and_overview_contains_offset_source(self):
        self.window.zoom_slider.set_value(8)
        self.window.view.update(panX=500, panY=-250)
        before = self.window.request(self.root/'output', 'cut')
        self.window.preview_slider.set_value(.4)
        self.draw()
        self.assertEqual(self.window.request(self.root/'output', 'cut'), before)
        self.window.fit_preview()
        width, height = self.window.canvas.get_width(), self.window.canvas.get_height()
        self.draw(width, height)
        first = self.window.composition()[0][0]
        ox, oy = self.window.view_origin
        s = self.window.view_scale
        left, top = ox+first['imageX']*s, oy+first['imageY']*s
        self.assertGreaterEqual(left, 34)
        self.assertGreaterEqual(top, 34)
        self.assertLessEqual(left+self.image['width']*first['imageScale']*s, width-34)
        self.assertLessEqual(top+self.image['height']*first['imageScale']*s, height-34)
        self.assertEqual(self.window.request(self.root/'output', 'cut'), before)

    def test_draw_dims_exterior_and_keeps_crop_pixels_bright(self):
        self.window.loaded(core.inspect(self.source('red.png', '400x300', 'xc:#cc5522')))
        surface = self.draw()
        ox, oy = self.window.view_origin
        s = self.window.view_scale
        data = surface.get_data()
        def red(x, y):
            return data[int(y)*surface.get_stride()+int(x)*4+2]
        inside = red(ox+50*s, oy+40*s)
        outside = red(ox+50*s, oy-80*s)
        self.assertGreater(inside, 180)
        self.assertTrue(45 < outside < inside*.7, (inside, outside))

    def test_empty_layout_draws_and_disables_export(self):
        with patch.object(core, 'monitors', side_effect=ValueError('no screens')):
            self.window.refresh()
        self.draw()
        self.assertEqual(self.window.monitors, [])
        self.assertFalse(self.window.export_button.get_sensitive())
        self.assertIn('no screens', self.window.status.get_text())

    def test_refresh_uses_updated_display_layout_and_resets_selection(self):
        changed = [monitor('portrait', -80, width=80, height=160)]
        with patch.object(core, 'monitors', return_value=changed):
            self.window.refresh()
        self.assertEqual(self.window.monitors, changed)
        self.assertEqual(self.window.selected, 0)
        self.assertIn('portrait', self.window.summary.get_text())

    def test_preferences_separate_window_live_language_and_persisted_defaults(self):
        before = dict(self.window.view)
        self.window.settings_button.emit('clicked')
        dialog = self.window.preferences_window
        self.assertTrue(dialog.get_modal())
        self.assertTrue(self.window.sidebar_scroll.get_visible())
        self.window.language_selector.set_selected(1)
        self.window.default_preview_spin.set_value(55)
        self.window.show_controls_switch.set_active(False)
        self.window.preferences_save_button.emit('clicked')
        self.assertEqual(self.window.view, before)
        self.assertEqual(self.window.open_button.get_child().get_last_child().get_text(), 'Open image')
        self.assertEqual(self.window.preview_label.get_text(), '55%')
        self.assertFalse(self.window.sidebar_scroll.get_visible())
        reopened = self.new_window()
        self.assertEqual(reopened.preferences['language'], 'en')
        self.assertEqual(reopened.preview_zoom, .55)
        self.assertFalse(reopened.sidebar_scroll.get_visible())
        self.window.open_preferences()
        self.assertIs(self.window.preferences_window, dialog)
        self.assertEqual(self.window.default_preview_spin.get_value(), 55)

    def test_preferences_cancel_and_save_failure_preserve_existing_preferences(self):
        original = core.load_preferences()
        self.window.open_preferences()
        self.window.language_selector.set_selected(1)
        self.window.preferences_window.emit('close-request')
        self.assertEqual(core.load_preferences(), original)
        self.window.open_preferences()
        self.assertEqual(self.window.language_selector.get_selected(), 0)
        with patch.object(core, 'save_preferences', side_effect=OSError('denied')):
            self.window.preferences_save_button.emit('clicked')
        self.assertTrue(self.window.preferences_error.get_visible())
        self.assertEqual(core.load_preferences(), original)

    def test_percentage_control_typing_buttons_limits_and_invalid_save(self):
        self.window.open_preferences()
        control = self.window.default_preview_spin
        self.assertEqual(control.entry.get_text(), '70%')
        control.minus.emit('clicked')
        self.assertEqual(control.entry.get_text(), '69%')
        control.plus.emit('clicked')
        self.assertEqual(control.entry.get_text(), '70%')
        control.entry.set_text('42')
        control.entry.emit('activate')
        self.assertEqual(control.entry.get_text(), '42%')
        control.set_value(1)
        self.assertFalse(control.minus.get_sensitive())
        control.set_value(100)
        self.assertFalse(control.plus.get_sensitive())
        for value in ['0%', '101%', '4.2%', 'bad', '']:
            control.entry.set_text(value)
            self.window.preferences_save_button.emit('clicked')
            self.assertTrue(self.window.preferences_error.get_visible())
            self.assertFalse((core.CONFIG/'preferences.json').exists())
        control.plus.emit('clicked')
        self.assertEqual(control.get_value(), 100)
        self.assertIsInstance(self.window.preferences_save_button.get_child(), Gtk.Label)

    def test_feedback_success_error_dismiss_and_error_status_clear(self):
        self.window.show_feedback('Duvar kâğıdı başarıyla uygulandı')
        self.assertTrue(self.window.feedback_box.has_css_class('wc-feedback-success'))
        self.assertFalse(self.window.feedback_detail.get_visible())
        self.window.show_feedback('Duvar kâğıdı uygulanamadı', 'error', error=True)
        self.assertFalse(self.window.feedback_box.has_css_class('wc-feedback-success'))
        self.assertTrue(self.window.feedback_box.has_css_class('wc-feedback-error'))
        self.window.feedback_box.get_last_child().emit('clicked')
        self.assertFalse(self.window.feedback.get_reveal_child())
        self.window.message('failed', True)
        self.window.message('ready')
        self.assertFalse(self.window.status.has_css_class('error'))

    def test_busy_state_blocks_duplicate_work_editing_and_file_dialogs(self):
        release = threading.Event()
        started = threading.Event()
        self.addCleanup(release.set)
        def work():
            started.set()
            release.wait(3)
            return 'complete'
        self.window.submit(work, lambda result: self.window.message(result))
        self.assertTrue(started.wait(1))
        self.assertTrue(self.window.busy)
        before = dict(self.window.view)
        with patch.object(Gtk, 'FileDialog') as dialog, patch.object(desktop, 'export') as export:
            self.window.open_image()
            self.window.export(True)
            self.window.open_preferences()
            self.window.run_export(self.root, 'other', True)
            self.window.scroll(None, 0, 1)
            self.window.drag_update(None, 10, 10)
            self.window.center_image('x')
            self.window.fit_preview()
            self.assertFalse(self.window.key(None, Gdk.KEY_Right, 0, 0))
            dialog.assert_not_called()
            export.assert_not_called()
        self.assertEqual(self.window.view, before)
        self.assertFalse(self.window.open_button.get_sensitive())
        duplicate = Mock()
        self.window.submit(duplicate, Mock())
        release.set()
        self.settle()
        duplicate.assert_not_called()
        self.assertTrue(self.window.open_button.get_sensitive())
        self.assertEqual(self.window.status.get_text(), 'complete')

    def test_worker_and_completion_errors_report_and_allow_retry(self):
        for worker, done in [(Mock(side_effect=OSError('worker failure')), Mock()),
                             (Mock(return_value='ok'), Mock(side_effect=ValueError('completion failure')))]:
            self.window.submit(worker, done, failure_title='Duvar kâğıdı uygulanamadı')
            self.settle()
            self.assertTrue(self.window.feedback_box.has_css_class('wc-feedback-error'))
            self.assertTrue(self.window.open_button.get_sensitive())
        self.window.submit(lambda: 'retry', self.window.message)
        self.settle()
        self.assertEqual(self.window.status.get_text(), 'retry')

    def test_export_selected_folder_and_cancel_do_not_apply_wallpaper(self):
        target = self.root/'chosen'/'my-cut'
        with patch.object(Gtk, 'FileDialog', return_value=self.dialog('save', str(target))), \
             patch.object(desktop, 'apply_wallpaper') as apply:
            self.window.export(False)
            self.settle()
        apply.assert_not_called()
        self.assertTrue((target/'panorama.png').is_file())
        self.assertTrue(self.window.feedback_box.has_css_class('wc-feedback-success'))
        self.assertEqual(desktop.values(self.store), self.before_background)
        for dialog in [self.dialog('save', None), self.dialog('save', error=GLib.Error('cancelled'))]:
            with patch.object(Gtk, 'FileDialog', return_value=dialog), patch.object(desktop, 'export') as export:
                self.window.export(False)
                export.assert_not_called()

    def test_apply_then_restore_real_export_with_memory_gsettings(self):
        self.window.export(True)
        self.assertTrue(self.window.busy)
        self.assertEqual(self.window.apply_button.get_child().get_last_child().get_text(), 'Uygulanıyor…')
        self.settle()
        self.assertEqual(desktop.values(self.store)['picture-options'], 'spanned')
        self.assertTrue(self.window.restore_button.get_sensitive())
        self.assertTrue((core.STATE/'session.json').exists())
        self.window.restore_button.emit('clicked')
        self.assertEqual(desktop.values(self.store), self.before_background)
        self.assertFalse(self.window.restore_button.get_sensitive())

    def test_apply_failure_and_changed_layout_do_not_touch_wallpaper(self):
        for failure in ['export', 'apply', 'layout']:
            with self.subTest(failure=failure):
                with patch.object(desktop, 'export', side_effect=OSError('failed')) if failure == 'export' else patch.object(desktop, 'export', return_value={'panorama': self.image['path']}):
                    with patch.object(desktop, 'apply_wallpaper', side_effect=OSError('failed')) if failure == 'apply' else patch.object(desktop, 'apply_wallpaper') as apply:
                        with patch.object(core, 'monitors', return_value=[] if failure == 'layout' else self.layout):
                            self.window.run_export(self.root, 'test', True)
                            self.settle()
                self.assertTrue(self.window.feedback_box.has_css_class('wc-feedback-error'))
                self.assertFalse(self.window.restore_button.get_sensitive())
                self.assertEqual(desktop.values(self.store), self.before_background)

    def test_external_wallpaper_change_and_restore_failure_leave_safe_state(self):
        desktop.apply_wallpaper(Path(self.image['path']), self.store)
        self.window.update_buttons()
        with patch.object(desktop, 'restore_wallpaper', side_effect=OSError('denied')):
            self.window.restore()
        self.assertTrue(self.window.restore_button.get_sensitive())
        self.assertTrue(self.window.feedback_box.has_css_class('wc-feedback-error'))
        self.store.set_string('picture-uri', 'file:///external.png')
        pump_until(lambda: not self.window.restore_button.get_sensitive())
        before = desktop.values(self.store)
        self.window.restore()
        self.assertEqual(desktop.values(self.store), before)

    def test_import_saved_crop_restores_source_view_bezel_and_alignment(self):
        self.window.zoom_slider.set_value(2)
        self.window.view.update(panX=3, panY=-2)
        self.window.gap_spin.set_value(7)
        self.window.offset_x.set_value(5)
        request = self.window.request(self.root/'exports', 'saved')
        result = desktop.export(request)
        self.window.fill()
        self.window.gap_spin.set_value(0)
        self.window.offset_x.set_value(0)
        layout_file = str(Path(result['directory'])/'layout.json')
        with patch.object(Gtk, 'FileDialog', return_value=self.dialog(selected=layout_file)):
            self.window.import_cut()
            self.settle()
        self.assertEqual(self.window.view, dict(zoom=2, panX=3, panY=-2))
        self.assertEqual(self.window.gap, 7)
        self.assertEqual(self.window.adjustments['left']['x'], 5)
        self.assertEqual(self.window.preview_zoom, .7)
        self.assertIn('source.png', self.window.picture['path'])

    def test_import_cancel_and_bad_layout_leave_current_composition(self):
        before = self.window.request(self.root, 'before')
        for dialog in [self.dialog(selected=None), self.dialog(error=GLib.Error('cancelled'))]:
            with patch.object(Gtk, 'FileDialog', return_value=dialog):
                self.window.import_cut()
        self.assertEqual(self.window.request(self.root, 'before'), before)
        broken = self.root/'layout.json'
        broken.write_text('{bad')
        with patch.object(Gtk, 'FileDialog', return_value=self.dialog(selected=str(broken))):
            self.window.import_cut()
            self.settle()
        self.assertEqual(self.window.request(self.root, 'before'), before)
        self.assertTrue(self.window.status.has_css_class('error'))

    def test_initial_image_and_saved_session_load_with_native_view(self):
        window = self.new_window(initial_image=self.image['path'])
        pump_until(lambda: window.picture is not None and not window.busy)
        self.assertEqual(window.view, dict(zoom=1, panX=0, panY=0))
        core.atomic_json(core.STATE/'session.json', dict(image=self.image, zoomMode='native',
                                                        zoom=1.5, panX=3, panY=-2))
        resumed = self.new_window()
        pump_until(lambda: resumed.picture is not None and not resumed.busy)
        self.assertEqual(resumed.view, dict(zoom=1.5, panX=3, panY=-2))

    def test_malformed_or_missing_session_does_not_crash_or_change_background(self):
        core.atomic_json(core.STATE/'session.json', dict(image={'path': '/missing.png'}))
        window = self.new_window()
        self.assertIsNone(window.picture)
        (core.STATE/'session.json').write_text('{bad')
        invalid = self.new_window()
        self.assertIsNone(invalid.picture)
        self.assertIn('Önceki görsel', invalid.status.get_text())
        self.assertEqual(desktop.values(self.store), self.before_background)

    def test_legacy_independent_layout_opens_at_native_center_and_reports_migration(self):
        self.window.loaded(self.image, dict(views={'left': dict(zoom=2)}))
        self.assertEqual(self.window.view, dict(zoom=1, panX=0, panY=0))
        self.assertIn('Önceki ekran bazlı', self.window.status.get_text())

    def test_icon_open_shortcut_and_application_reuse(self):
        self.assertEqual(self.window.get_icon_name(), app.APP_ICON)
        self.assertTrue(Gtk.IconTheme.get_for_display(self.window.get_display()).has_icon(app.APP_ICON))
        self.assertIn('<Control>o', self.application.get_accels_for_action('app.open'))
        existing = Mock()
        fake = Mock()
        fake.get_active_window.return_value = existing
        app.Application.do_activate(fake)
        existing.present.assert_called_once()
        fake.get_active_window.return_value = None
        fake.options = SimpleNamespace(image=None, smoke=False)
        with patch.object(app, 'Window', return_value=existing) as constructor:
            app.Application.do_activate(fake)
            constructor.assert_called_once_with(fake, None, False)

    def test_smoke_option_uses_nonunique_app_and_close_stops_worker_pool(self):
        application = app.Application(SimpleNamespace(smoke=True, image=None))
        self.assertTrue(application.get_flags() & Gio.ApplicationFlags.NON_UNIQUE)
        self.assertFalse(self.window.closing())
        with self.assertRaises(RuntimeError):
            self.window.pool.submit(lambda: None)

    def test_smoke_produces_preview_and_window_capture_without_background_writes(self):
        self.application.exit_code = 0
        with patch.object(self.application, 'quit') as quit_application:
            self.assertFalse(self.window.smoke_check())
            pump_until(lambda: (core.STATE/'window.png').exists())
        quit_application.assert_called_once()
        self.assertTrue((core.STATE/'preview.png').exists())
        self.assertEqual(self.application.exit_code, 0)
        self.assertEqual(desktop.values(self.store), self.before_background)

    def test_empty_editor_guards_and_uncovered_image_do_not_export(self):
        self.window.picture = None
        self.window.pixbuf = None
        self.window.update_buttons()
        self.draw()
        before = dict(self.window.view)
        self.window.fill()
        self.window.center_image('y')
        self.window.drag_update(None, 10, 10)
        self.window.fit_preview()
        self.assertFalse(self.window.key(None, Gdk.KEY_Left, 0, 0))
        self.assertEqual(self.window.view, before)
        self.assertFalse(self.window.zoom_slider.get_sensitive())
        with patch.object(Gtk, 'FileDialog') as dialog, patch.object(desktop, 'export') as export:
            self.window.export(False)
            dialog.assert_not_called()
            export.assert_not_called()
        self.window.loaded(self.image)
        self.window.zoom_slider.set_value(.01)
        self.assertFalse(self.window.covered())
        with patch.object(desktop, 'export') as export:
            self.window.export(True)
            export.assert_not_called()

    def test_unsupported_desktop_still_edits_and_exports_without_gnome_settings(self):
        from wallpaper_cutter.backends.desktop import UnsupportedBackend
        with patch.object(desktop, 'settings', return_value=UnsupportedBackend()):
            window = self.new_window()
        window.loaded(self.image)
        window.update_buttons()
        self.assertTrue(window.export_button.get_sensitive())
        self.assertFalse(window.apply_button.get_sensitive())
        self.assertFalse(window.restore_button.get_sensitive())
        self.assertIn('dışa', window.apply_button.get_tooltip_text())
        with patch.object(desktop, 'apply_wallpaper') as apply:
            window.export(True)
            apply.assert_not_called()
