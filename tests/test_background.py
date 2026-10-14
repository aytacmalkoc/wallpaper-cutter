"""GNOME transactions against memory-backed settings, never the real desktop."""
import json
from unittest.mock import Mock, patch
from helpers import IsolatedTest, memory_background, monitor
from wallpaper_cutter import core
from wallpaper_cutter import desktop


class BackgroundTests(IsolatedTest):
    def test_nonwritable_and_failed_transactions_never_commit_partial_values(self):
        store = Mock()
        data = dict(zip(desktop.BACKGROUND_KEYS, ['file:///a', 'file:///b', 'zoom']))
        store.is_writable.side_effect = [True, False]
        with self.assertRaises(ValueError):
            desktop.write_values(store, data)
        store.delay.assert_not_called()
        store.reset_mock(side_effect=True)
        store.is_writable.return_value = True
        store.set_string.side_effect = [True, False]
        with self.assertRaises(ValueError):
            desktop.write_values(store, data)
        store.revert.assert_called_once()
        store.apply.assert_not_called()

    def test_restore_write_failure_preserves_retry_and_backup(self):
        store = memory_background()
        original = desktop.values(store)
        desktop.apply_wallpaper(self.source(), store)
        backup = (core.STATE/'background-original.json').read_bytes()
        with patch.object(desktop, 'write_values', side_effect=OSError('denied')):
            with self.assertRaises(OSError):
                desktop.restore_wallpaper(store)
        self.assertEqual((core.STATE/'background-original.json').read_bytes(), backup)
        self.assertTrue(desktop.can_restore(store))
        desktop.restore_wallpaper(store)
        self.assertEqual(desktop.values(store), original)

    def test_corrupt_or_incomplete_records_never_allow_restore(self):
        store = memory_background()
        current = desktop.values(store)
        for original, applied in [('broken', current), ([], current), ({'picture-uri': 1}, current),
                                  (current, {'picture-uri': 'x'}), (current, None)]:
            with self.subTest(original=original, applied=applied):
                core.atomic_json(core.STATE/'background-original.json', original)
                core.atomic_json(core.STATE/'background-applied.json', applied)
                self.assertFalse(desktop.can_restore(store))
                with self.assertRaises(ValueError):
                    desktop.restore_wallpaper(store)
                self.assertEqual(desktop.values(store), current)
        (core.STATE/'background-original.json').write_text('{bad')
        self.assertIsNone(desktop.read_background(core.STATE/'background-original.json'))

    def test_unavailable_settings_fail_closed_and_default_store_is_used(self):
        store = memory_background()
        with patch.object(desktop, 'settings', return_value=store):
            desktop.apply_wallpaper(self.source())
            self.assertTrue(desktop.can_restore())
            desktop.restore_wallpaper()
        core.atomic_json(core.STATE/'background-original.json', desktop.values(store))
        core.atomic_json(core.STATE/'background-applied.json', desktop.values(store))
        with patch.object(desktop, 'settings', side_effect=RuntimeError('unavailable')):
            self.assertFalse(desktop.can_restore())

    def test_vertical_bezel_chain_and_non_touching_displays(self):
        layout = [monitor('top', 0, -80), monitor('middle', 0), monitor('bottom', 0, 80),
                  monitor('disconnected', 500, 500)]
        frames = desktop.frames(layout, 7, {'middle': {'y': 2}})
        self.assertEqual([f['y'] for f in frames], [-80, 9, 94, 500])
        self.assertEqual(layout[1]['y'], 0)
        self.assertEqual(desktop.bounds([]), dict(x=0, y=0, width=1920, height=1080))
        self.assertEqual(desktop.preview_bounds([], None), desktop.bounds([]))

    def test_restored_view_rejects_unknown_modes_and_nonfinite_pan(self):
        for data in [dict(zoomMode='invalid'), dict(zoomMode='native', panY=float('inf')),
                     dict(zoomMode='native', zoom=9)]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                desktop.restored_view(data)
