import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
import bootstrap
from wallpaper_cutter import core
from wallpaper_cutter import desktop


def monitor(name, x, y=0, width=100, height=80, scale=1):
    return dict(name=name, x=x, y=y, width=width, height=height,
                pixelWidth=round(width*scale), pixelHeight=round(height*scale), scale=scale)


class DesktopTests(unittest.TestCase):
    def test_bezel_chain_and_corner_contact(self):
        monitors = [monitor('left', -100), monitor('middle', 0), monitor('right', 100),
                    monitor('corner', 200, 80)]
        frames = desktop.frames(monitors, 12, {'middle': {'x': 3, 'y': -2}})
        self.assertEqual([m['x'] for m in frames], [-100, 15, 124, 200])
        self.assertEqual(frames[1]['y'], -2)
        self.assertEqual(monitors[1]['x'], 0)

    def test_mutter_rotation_fractional_scale_and_mirror_group(self):
        spec = ('DP-1', 'A', 'Screen', '123')
        mirror = ('HDMI-1', 'A', 'Screen', '456')
        physical = [(spec, [('current', 1920, 1080, 60., 1., [1.25], {'is-current': True})],
                     {'display-name': 'Test screen'}),
                    (mirror, [('current', 1920, 1080, 60., 1., [1.25], {'is-current': True})], {})]
        state = (1, physical, [(-100, 0, 1.25, 1, True, [spec, mirror], {})], {'layout-mode': 1})
        result = core.parse_monitors(state)
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]['width'], result[0]['height']), (864, 1536))
        self.assertEqual((result[0]['pixelWidth'], result[0]['pixelHeight']), (1080, 1920))
        self.assertEqual(result[0]['x'], -100)

    def test_settings_reject_nonfinite_and_preserve_saved_alignment(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'CONFIG', Path(directory)):
            value = core.save_settings({'gap': 8, 'adjustments': {'DP-1': {'x': 3, 'y': -5}}})
            with self.assertRaises(ValueError):
                core.save_settings({'gap': float('nan')})
            self.assertEqual(core.load_settings(), value)

    def test_native_cuts_panorama_import_and_unique_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(core, 'STATE', root/'state'):
                image = root/'source.png'
                # Each vertical strip encodes its position, exposing seam/crop errors.
                core.magick(['-size', '220x80', 'gradient:red-blue', '-rotate', '90',
                             '-resize', '220x80!', 'PNG24:'+str(image)])
                layout = [monitor('left', 0), monitor('right', 100)]
                request = dict(image=dict(path=str(image), name='source.png', width=220, height=80),
                               monitors=layout, frames=desktop.frames(layout, 20, {}), gap=20,
                               adjustments={}, zoom=1, panX=0, panY=0,
                               imageScale=1, imageX=0, imageY=0,
                               directory=str(root/'exports'), exportName='named-cut')
                result = desktop.export(request)
                self.assertEqual(core.magick(['identify', '-format', '%wx%h', result['panorama']]), '200x80')
                output = Path(result['directory'])
                self.assertEqual(core.magick(['identify', '-format', '%wx%h', output/'01-left-100x80.png']), '100x80')
                # The bezel discards source pixels 100..119; the right screen begins at 120.
                sample = core.magick([result['panorama'], '-format', '%[pixel:p{100,40}]', 'info:'])
                expected = core.magick([str(image), '-format', '%[pixel:p{120,40}]', 'info:'])
                self.assertEqual(sample, expected)
                imported = core.import_layout(output/'layout.json')
                self.assertEqual(imported['gap'], 20)
                self.assertTrue(Path(imported['image']['path']).is_file())
                second = desktop.export(request)
                self.assertNotEqual(result['directory'], second['directory'])

    def test_uncovered_export_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'STATE', Path(directory)/'state'):
            image = Path(directory)/'image.png'
            core.magick(['-size', '50x50', 'xc:red', str(image)])
            request = dict(image=dict(path=str(image), name='image.png'), monitors=[monitor('screen', 0)],
                           frames=[monitor('screen', 0)], imageScale=1, imageX=0, imageY=0,
                           directory=str(Path(directory)/'exports'), exportName='invalid')
            with self.assertRaises(ValueError): desktop.export(request)
            self.assertFalse((Path(directory)/'exports').exists())

    def test_shared_zoom_and_pan_change_all_monitor_pixels_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'STATE', Path(directory)/'state'):
            root = Path(directory)
            image_path = root/'source.png'
            core.magick(['-size', '220x80', 'gradient:red-blue', '-rotate', '90',
                         '-resize', '220x80!', 'PNG24:'+str(image_path)])
            image = dict(path=str(image_path), name='source.png', width=220, height=80)
            monitors = [monitor('left', 0), monitor('right', 100)]
            def request(view):
                frames, _ = desktop.composition(monitors, image, 0, {}, view)
                return dict(image=image, monitors=monitors, frames=frames, zoomMode='native', **view,
                            gap=0, adjustments={}, imageScale=frames[0]['imageScale'],
                            imageX=frames[0]['imageX'], imageY=frames[0]['imageY'],
                            directory=str(root/'exports'), exportName='shared')
            initial = request(dict(zoom=1, panX=0, panY=0))
            first = desktop.export(initial)
            view = dict(zoom=1.5, panX=3, panY=-2)
            changed = request(view)
            transforms = {(f['imageScale'], f['imageX'], f['imageY']) for f in changed['frames']}
            self.assertEqual(len(transforms), 1)
            second = desktop.export(changed)
            a, b = Path(first['directory']), Path(second['directory'])
            for name in ['01-left-100x80.png', '02-right-100x80.png']:
                self.assertNotEqual((a/name).read_bytes(), (b/name).read_bytes())
            saved = json.loads((b/'layout.json').read_text())
            self.assertNotIn('views', saved)
            imported = core.import_layout(b/'layout.json')
            restored = desktop.restored_view(imported)
            self.assertEqual(restored, view)
            self.assertEqual(desktop.composition(monitors, image, 0, {}, restored)[0], changed['frames'])
            # The extended zoom range must also round-trip through exported files.
            saved['zoom'] = 6
            (b/'layout.json').write_text(json.dumps(saved))
            self.assertEqual(core.import_layout(b/'layout.json')['zoom'], 6)

    def test_legacy_shared_crop_is_preserved(self):
        monitors = [monitor('left', -100), monitor('right', 0)]
        image = {'width': 220, 'height': 100}
        saved = {'zoom': 2, 'panX': 7, 'panY': -3}
        view = desktop.restored_view(saved, monitors, image, preserve_legacy=True)
        frames, area = desktop.composition(monitors, image, 0, {}, view)
        scale = max(area['width']/image['width'], area['height']/image['height'])*2
        expected_x = area['x']+(area['width']-image['width']*scale)/2+7
        expected_y = area['y']+(area['height']-image['height']*scale)/2-3
        for frame in frames:
            self.assertEqual(frame['imageScale'], scale)
            self.assertEqual(frame['imageX'], expected_x)
            self.assertEqual(frame['imageY'], expected_y)

    def test_independent_crops_open_as_native_center_without_mutating_saved_data(self):
        saved = {'views': {'left': {'zoom': 1.5, 'panX': 8, 'panY': 0},
                           'right': {'zoom': 2, 'panX': -2, 'panY': 3}}}
        original = copy.deepcopy(saved)
        self.assertEqual(desktop.restored_view(saved), dict(zoom=1, panX=0, panY=0))
        self.assertEqual(saved, original)
        with self.assertRaises(ValueError):
            desktop.restored_view({'views': {'left': {'zoom': float('nan')}}})

    def test_native_default_centers_without_resizing(self):
        monitors = [monitor('left', 0, width=1920, height=1080),
                    monitor('right', 1920, width=1920, height=1080)]
        image = {'width': 5267, 'height': 3604}
        frames, area = desktop.composition(monitors, image, 0, {}, {})
        self.assertEqual((area['width'], area['height']), (3840, 1080))
        for f in frames:
            self.assertEqual(f['imageScale'], 1)
            self.assertEqual((f['imageX'], f['imageY']), (-713.5, -1262))
        # Smaller images also retain their real size; there is no automatic fill.
        small, _ = desktop.composition(monitors, {'width': 2000, 'height': 800}, 0, {}, {})
        self.assertEqual(small[0]['imageScale'], 1)
        self.assertEqual((small[0]['imageX'], small[0]['imageY']), (920, 140))

    def test_old_session_resets_to_native_default_and_new_zoom_roundtrips(self):
        self.assertEqual(desktop.restored_view({'zoom': 2, 'panX': 30, 'panY': -5}),
                         dict(zoom=1, panX=0, panY=0))
        self.assertEqual(desktop.restored_view({'zoomMode': 'native', 'zoom': 1.5, 'panX': 30, 'panY': -5}),
                         dict(zoom=1.5, panX=30, panY=-5))

    def test_preview_includes_native_centered_image_and_portrait_layouts(self):
        monitors = [monitor('portrait', -80, -30, width=80, height=160),
                    monitor('wide', 0, 10, width=160, height=90)]
        for image in [{'width': 400, 'height': 300}, {'width': 100, 'height': 500}]:
            frames, crop_area = desktop.composition(monitors, image, 12, {}, {})
            before = copy.deepcopy(frames)
            preview = desktop.preview_bounds(frames, image)
            first = frames[0]
            rectangles = [*frames, dict(x=first['imageX'], y=first['imageY'],
                width=image['width'], height=image['height'])]
            for rectangle in rectangles:
                self.assertLessEqual(preview['x'], rectangle['x'])
                self.assertLessEqual(preview['y'], rectangle['y'])
                self.assertGreaterEqual(preview['x']+preview['width'], rectangle['x']+rectangle['width'])
                self.assertGreaterEqual(preview['y']+preview['height'], rectangle['y']+rectangle['height'])
            self.assertEqual(frames, before)
            self.assertEqual(desktop.composition(monitors, image, 12, {}, {})[1], crop_area)

    def test_preview_camera_stays_fixed_while_image_moves_and_zooms(self):
        monitors = [monitor('portrait', -80, -30, width=80, height=160),
                    monitor('wide', 0, 10, width=160, height=90)]
        for image in [{'width': 400, 'height': 300}, {'width': 100, 'height': 500}]:
            initial, _ = desktop.composition(monitors, image, 12, {}, {})
            camera = desktop.preview_bounds(initial, image)
            for view in [dict(zoom=1, panX=120, panY=-55),
                         dict(zoom=2, panX=0, panY=0),
                         dict(zoom=.1, panX=-300, panY=200),
                         dict(zoom=8, panX=500, panY=-600)]:
                with self.subTest(image=image, view=view):
                    frames, _ = desktop.composition(monitors, image, 12, {}, view)
                    before = copy.deepcopy(frames)
                    self.assertEqual(desktop.preview_bounds(frames, image), camera)
                    self.assertEqual(frames, before)
                    for original, changed in zip(initial, frames):
                        self.assertEqual(tuple(changed[k] for k in ('x', 'y', 'width', 'height')),
                                         tuple(original[k] for k in ('x', 'y', 'width', 'height')))
                    self.assertNotEqual((frames[0]['imageX'], frames[0]['imageY'], frames[0]['imageScale']),
                                        (initial[0]['imageX'], initial[0]['imageY'], initial[0]['imageScale']))

    def test_apply_twice_and_restore_both_color_modes(self):
        import gi
        from gi.repository import Gio
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'STATE', Path(directory)/'state'):
            original = {'picture-uri': 'file:///original-light.png',
                        'picture-uri-dark': 'file:///original-dark.png', 'picture-options': 'zoom'}
            schema = Gio.SettingsSchemaSource.get_default().lookup('org.gnome.desktop.background', True)
            store = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
            desktop.write_values(store, original)
            self.assertFalse(desktop.can_restore(store))
            image = Path(directory)/'wallpaper.png'
            image.write_bytes(b'test')
            desktop.apply_wallpaper(image, store)
            self.assertTrue(desktop.can_restore(store))
            desktop.apply_wallpaper(image, store)
            self.assertEqual(desktop.values(store)['picture-options'], 'spanned')
            desktop.restore_wallpaper(store)
            self.assertEqual(desktop.values(store), original)
            self.assertFalse(desktop.can_restore(store))
            with self.assertRaises(ValueError):
                desktop.restore_wallpaper(store)

    def test_failed_apply_and_external_wallpaper_do_not_allow_restore(self):
        from gi.repository import Gio
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'STATE', Path(directory)/'state'):
            schema = Gio.SettingsSchemaSource.get_default().lookup('org.gnome.desktop.background', True)
            store = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
            original = dict(zip(desktop.BACKGROUND_KEYS, ['file:///light.png', 'file:///dark.png', 'zoom']))
            desktop.write_values(store, original)
            image = Path(directory)/'wallpaper.png'
            image.write_bytes(b'test')
            with patch.object(desktop, 'write_values', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    desktop.apply_wallpaper(image, store)
            self.assertTrue((core.STATE/'background-original.json').exists())
            self.assertFalse(desktop.can_restore(store))
            with self.assertRaises(ValueError):
                desktop.restore_wallpaper(store)
            desktop.apply_wallpaper(image, store)
            desktop.write_values(store, original)
            self.assertFalse(desktop.can_restore(store))
            with self.assertRaises(ValueError):
                desktop.restore_wallpaper(store)
            self.assertEqual(desktop.values(store), original)
            # A new successful application after an external change captures that wallpaper.
            external = dict(original, **{'picture-uri': 'file:///external.png'})
            desktop.write_values(store, external)
            desktop.apply_wallpaper(image, store)
            desktop.restore_wallpaper(store)
            self.assertEqual(desktop.values(store), external)

    def test_preferences_roundtrip_preserves_alignment_and_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'CONFIG', Path(directory)):
            settings = core.save_settings(dict(gap=12, adjustments={'DP-1': {'x': 3, 'y': -2}}))
            self.assertEqual(core.load_preferences(), dict(version=1, language='tr', previewZoom=.7, showControls=True))
            saved = core.save_preferences(dict(language='en', previewZoom=.55, showControls=False))
            self.assertEqual(core.load_preferences(), saved)
            self.assertEqual(core.load_settings(), settings)
            for invalid in [dict(language='xx'), dict(previewZoom=float('nan')), dict(previewZoom=2), dict(showControls=1)]:
                with self.subTest(value=invalid), self.assertRaises(ValueError):
                    core.save_preferences(invalid)
                self.assertEqual(core.load_preferences(), saved)
            (core.CONFIG/'preferences.json').write_text('{invalid')
            self.assertEqual(core.load_preferences()['previewZoom'], .7)


if __name__ == '__main__':
    unittest.main()
