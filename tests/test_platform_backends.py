"""Desktop routing, native rollback and Linux adapter contracts."""
import copy
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from helpers import IsolatedTest, memory_background, monitor
from wallpaper_cutter import core
from wallpaper_cutter import desktop
from wallpaper_cutter.backends import desktop as backends


class FakeBackend:
    supported = True

    def __init__(self):
        self.state = dict(backend='fake-native', images={'left': 'before.png'}, mode=4)
        self.fail_once = False
        self.ignore = False

    def capture(self):
        return copy.deepcopy(self.state)

    def prepare(self, path, outputs):
        return dict(self.state, images={'left': str(path)}, mode=2)

    def write(self, state):
        if self.ignore:
            return
        self.state = copy.deepcopy(state)
        if self.fail_once:
            self.fail_once = False
            raise OSError('second display failed')


class NativeTransactionTests(IsolatedTest):
    def test_native_apply_and_restore_preserve_original_after_multiple_applications(self):
        backend = FakeBackend()
        before = backend.capture()
        desktop.apply_wallpaper(self.source(), backend)
        self.assertTrue(desktop.can_restore(backend))
        desktop.apply_wallpaper(self.source('next.png'), backend)
        desktop.restore_wallpaper(backend)
        self.assertEqual(backend.capture(), before)
        self.assertFalse(desktop.can_restore(backend))

    def test_partial_native_failure_rolls_back_without_enabling_restore(self):
        backend = FakeBackend()
        before = backend.capture()
        backend.fail_once = True
        with self.assertRaises(OSError):
            desktop.apply_wallpaper(self.source(), backend)
        self.assertEqual(backend.capture(), before)
        self.assertFalse(desktop.can_restore(backend))
        self.assertTrue((core.STATE/'wallpaper-original.json').exists())

    def test_native_write_ignored_by_desktop_is_not_reported_as_success(self):
        backend = FakeBackend()
        backend.ignore = True
        with self.assertRaisesRegex(RuntimeError, 'did not accept'):
            desktop.apply_wallpaper(self.source(), backend)
        self.assertFalse(desktop.can_restore(backend))

    def test_failed_restore_retains_applied_state_and_allows_retry(self):
        backend = FakeBackend()
        desktop.apply_wallpaper(self.source(), backend)
        applied = backend.capture()
        backend.fail_once = True
        with self.assertRaises(OSError):
            desktop.restore_wallpaper(backend)
        self.assertEqual(backend.capture(), applied)
        self.assertTrue(desktop.can_restore(backend))
        backend.ignore = True
        with self.assertRaisesRegex(RuntimeError, 'did not restore'):
            desktop.restore_wallpaper(backend)
        self.assertTrue(desktop.can_restore(backend))

    def test_external_changes_corrupt_backup_and_backend_mismatch_fail_closed(self):
        backend = FakeBackend()
        desktop.apply_wallpaper(self.source(), backend)
        applied = backend.capture()
        backend.state['mode'] = 9
        self.assertFalse(desktop.can_restore(backend))
        backend.state = applied
        core.atomic_json(core.STATE/'wallpaper-original.json', {'backend': 'fake-native', 'images': 'bad'})
        self.assertFalse(desktop.can_restore(backend))
        core.atomic_json(core.STATE/'wallpaper-original.json', dict(applied, backend='different'))
        self.assertFalse(desktop.can_restore(backend))
        self.assertFalse(desktop.can_restore(backends.UnsupportedBackend()))

    def test_rollback_failure_is_explicit_and_preserves_recovery_record(self):
        backend = FakeBackend()
        with patch.object(backend, 'write', side_effect=OSError('permission denied')):
            with self.assertRaisesRegex(RuntimeError, 'rollback failed'):
                desktop.apply_wallpaper(self.source(), backend)
        self.assertTrue((core.STATE/'wallpaper-original.json').exists())

    def test_silent_rollback_failure_is_detected_by_reading_actual_state(self):
        backend = FakeBackend()
        def write(state):
            if state['mode'] == 2:
                backend.state = copy.deepcopy(state)
                raise OSError('partial native write')
            # The desktop silently ignores the requested rollback.
        with patch.object(backend, 'write', side_effect=write):
            with self.assertRaisesRegex(RuntimeError, 'rollback failed'):
                desktop.apply_wallpaper(self.source(), backend)
        self.assertTrue((core.STATE/'wallpaper-original.json').exists())
        self.assertFalse(desktop.can_restore(backend))


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux desktop adapters require Linux GTK schemas')
class LinuxBackendTests(IsolatedTest):
    def test_desktop_routing_does_not_assume_gnome_on_unknown_shells(self):
        with patch.dict(os.environ, XDG_CURRENT_DESKTOP='sway'):
            self.assertFalse(backends.select_backend().supported)
        with patch.dict(os.environ, XDG_CURRENT_DESKTOP='KDE'):
            self.assertIsInstance(backends.select_backend(), backends.PlasmaBackend)
        with patch.dict(os.environ, XDG_CURRENT_DESKTOP='XFCE'), patch.object(backends.shutil, 'which', return_value='xfconf-query'):
            self.assertIsInstance(backends.select_backend(), backends.XfceBackend)
        with patch.dict(os.environ, XDG_CURRENT_DESKTOP='GNOME'):
            from gi.repository import Gio
            self.assertIsInstance(backends.select_backend(), Gio.Settings)

    def test_plasma_matches_geometry_and_encodes_paths_as_json_not_shell_code(self):
        entries = [dict(id='4', screen=0, x=0, y=0, width=100, height=80, image='file:///before.png', fill=2)]
        evaluate = Mock(return_value=json.dumps(entries))
        backend = backends.PlasmaBackend(evaluate)
        with patch.object(core, 'monitors', return_value=[monitor()]):
            desired = backend.prepare('unused', {'left': 'file:///a%20b%22.png'})
        self.assertEqual(desired['desktops'][0]['fill'], 0)
        self.assertEqual(desired['desktops'][0]['image'], 'file:///a%20b%22.png')
        backend.write(desired)
        script = evaluate.call_args.args[0]
        self.assertIn(json.dumps(desired['desktops']), script)
        self.assertIn('desktopById', script)
        with patch.object(core, 'monitors', return_value=[]), self.assertRaises(ValueError):
            backend.prepare('unused', {})

    def test_xfce_connector_properties_cycles_and_stretch_mode_roundtrip(self):
        image = '/backdrop/screen0/monitorDP-1/workspace0/last-image'
        style = image.replace('last-image', 'image-style')
        cycle = image.replace('last-image', 'backdrop-cycle-enable')
        values = {image: '/before.png', style: '5', cycle: 'true'}
        def query(*args):
            if args == ('-l',):
                return '\n'.join(values)
            if len(args) == 4:
                values[args[1]] = args[3]
                return ''
            return values[args[1]]
        backend = backends.XfceBackend()
        with patch.object(backend, 'query', side_effect=query):
            before = backend.capture()
            desired = backend.prepare('unused', {'DP-1': 'file:///cut.png'})
            backend.write(desired)
            self.assertEqual(values, {image: '/cut.png', style: '3', cycle: 'false'})
            backend.write(before)
            self.assertEqual(values, before['values'])
            with self.assertRaises(ValueError):
                backend.prepare('unused', {'wrong': 'file:///cut.png'})

    def test_gdk_geometry_fallback_when_mutter_is_unavailable(self):
        from gi.repository import Gio, Gdk
        native = Mock()
        native.get_geometry.return_value = SimpleNamespace(x=-100, y=0, width=100, height=80)
        native.get_connector.return_value = 'DP-1'
        native.get_scale.return_value = 1.5
        model = Mock()
        model.get_n_items.return_value = 1
        model.get_item.return_value = native
        display = Mock()
        display.get_monitors.return_value = model
        with patch.object(Gdk.Display, 'get_default', return_value=display), \
             patch.object(Gio, 'bus_get_sync', side_effect=RuntimeError('no Mutter')):
            result = core.monitors()
        self.assertEqual((result[0]['x'], result[0]['pixelWidth'], result[0]['scale']), (-100, 150, 1.5))

    def test_generic_gsettings_backend_keeps_mode_and_uses_proper_image_key(self):
        store = memory_background()
        backend = backends.GSettingsBackend(store, 'picture-uri')
        before = backend.capture()
        image = self.source()
        desired = backend.prepare(image, None)
        backend.write(desired)
        self.assertEqual(store.get_string('picture-uri'), image.as_uri())
        self.assertEqual(store.get_string('picture-options'), 'spanned')
        backend.write(before)
        self.assertEqual(backend.capture(), before)

    def test_native_backend_factory_is_scoped_to_each_api_call(self):
        native = Mock()
        native.__enter__ = Mock(return_value=native)
        native.__exit__ = Mock()
        factory = Mock(return_value=native)
        backend = backends.NativeBackend('test', factory)
        backend.capture()
        backend.prepare('image', {'left': 'file:///cut.png'})
        backend.write({'state': 'value'})
        self.assertEqual(factory.call_count, 3)
        self.assertEqual(native.__exit__.call_count, 3)
