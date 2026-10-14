"""Real file/image operations and failure boundaries."""
import copy
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock, patch
from helpers import IsolatedTest, monitor
from wallpaper_cutter import core
from wallpaper_cutter import desktop


class CoreTests(IsolatedTest):
    def test_atomic_json_replaces_existing_document_and_keeps_unicode(self):
        path = self.root/'nested'/'settings.json'
        core.atomic_json(path, {'old': True})
        core.atomic_json(path, {'name': 'Görsel', 'value': [1, 2]})
        self.assertEqual(json.loads(path.read_text()), {'name': 'Görsel', 'value': [1, 2]})
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_settings_defaults_and_session_migration_without_source_image(self):
        self.assertEqual(core.load_settings()['adjustments'], {})
        self.assertFalse((core.CONFIG/'settings.json').exists())
        core.atomic_json(core.STATE/'session.json', dict(gap=9, adjustments={'left': {'x': 4}},
                                                        image={'path': '/missing-source.png'}))
        migrated = core.load_settings()
        self.assertEqual(migrated, dict(version=1, gap=9, adjustments={'left': {'x': 4, 'y': 0}}))
        self.assertEqual(json.loads((core.CONFIG/'settings.json').read_text()), migrated)
        core.atomic_json(core.STATE/'session.json', dict(gap=33))
        self.assertEqual(core.load_settings(), migrated)

    def test_numeric_and_monitor_adjustment_validation(self):
        for value in [float('nan'), float('inf'), -5001, 5001]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                core.validate_settings(dict(adjustments={'left': {'x': value}}))
        for data in [[], dict(adjustments=[]), dict(adjustments={1: {}}),
                     dict(adjustments={'left': 3}), dict(gap=-1), dict(gap=501)]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                core.validate_settings(data)
        self.assertEqual(core.number('1.5'), 1.5)

    def test_preferences_invalid_or_unreadable_files_use_safe_defaults(self):
        for content in ['null', '[]', '{bad', '{"language":"invalid"}', '{"previewZoom":0}']:
            core.CONFIG.mkdir(exist_ok=True)
            (core.CONFIG/'preferences.json').write_text(content)
            self.assertEqual(core.load_preferences(), core.validate_preferences({}))
        with patch.object(Path, 'read_text', side_effect=PermissionError('denied')):
            self.assertEqual(core.load_preferences()['language'], 'tr')

    def test_magick_reports_missing_timeout_and_process_errors(self):
        failures = [(FileNotFoundError(), 'missing'),
                    (subprocess.TimeoutExpired('magick', 120), 'timed out'),
                    (subprocess.CalledProcessError(1, 'magick', stderr=b'bad image'), 'bad image'),
                    (subprocess.CalledProcessError(1, 'magick', stderr=b''), 'could not process')]
        for error, message in failures:
            with self.subTest(error=error), patch.object(core.subprocess, 'run', side_effect=error):
                with self.assertRaisesRegex(RuntimeError, message):
                    core.magick(['identify', 'x'])

    def test_inspect_literal_special_filename_and_preview_limit(self):
        path = self.source('picture[0]: test.png', '4000x20')
        info = core.inspect(path)
        self.assertEqual((info['width'], info['height'], info['name']), (4000, 20, path.name))
        preview = Path(info['preview'].removeprefix('file://'))
        self.assertEqual(core.magick(['identify', '-format', '%w', preview]), '3840')
        self.assertEqual(Path(info['path']), path)

    def test_invalid_image_leaves_no_preview(self):
        path = self.root/'broken.png'
        path.write_bytes(b'not an image')
        with self.assertRaises(RuntimeError):
            core.inspect(path)
        self.assertEqual(list(core.STATE.iterdir()), [])

    def test_all_supported_image_formats_can_be_inspected(self):
        for suffix in ['png', 'jpg', 'webp', 'bmp', 'tiff']:
            with self.subTest(format=suffix):
                path = self.root/f'image.{suffix}'
                core.magick(['-size', '13x7', 'xc:#33aa55', str(path)])
                info = core.inspect(path)
                self.assertEqual((info['width'], info['height']), (13, 7))
                self.assertTrue(info['preview'].startswith('file://'))
                self.assertEqual(Path(info['path']), path)

    def test_orientation_metadata_is_applied_before_preview_and_crops(self):
        path = self.root/'rotated.tiff'
        core.magick(['-size', '12x8', 'xc:red', '-orient', 'RightTop', str(path)])
        info = core.inspect(path)
        self.assertEqual((info['width'], info['height']), (8, 12))

    def test_export_copies_original_source_bytes_and_sanitizes_output_filenames(self):
        request = self.request()
        request['frames'][0]['name'] = 'DP/1'
        original = Path(request['image']['path']).read_bytes()
        result = core.render(request)
        directory = Path(result['directory'])
        self.assertEqual((directory/'source.png').read_bytes(), original)
        self.assertTrue((directory/'01-DP_1-100x80.png').is_file())
        self.assertIn('DP/1', result['outputs'])
        self.assertEqual(json.loads((core.STATE/'session.json').read_text()), request)

    def test_normalization_removes_alpha_and_cleans_temporary_file(self):
        path = self.root/'alpha.png'
        core.magick(['-size', '8x6', 'xc:none', str(path)])
        with core.normalized_image(path) as (normalized, width, height):
            self.assertEqual((width, height), (8, 6))
            self.assertEqual(core.magick([normalized, '-format', '%[pixel:p{0,0}]', 'info:']), 'srgb(0,0,0)')
        self.assertFalse(normalized.exists())

    def test_export_names_and_collisions_preserve_existing_files(self):
        for name in ['..', '.', 'x/y', 'x\\y', 'x\nx', 'ü'*91, 12]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.export_name({'exportName': name})
        generated = core.export_name({'image': {'path': 'x', 'name': 'ü'*120+'.png'}})
        self.assertLessEqual(len(generated.encode()), 144)
        self.assertEqual(core.export_name({'exportName': '  trimmed  '}), 'trimmed')
        first = core.export_directory(self.root/'exports', 'same')
        (first/'keep').write_text('important')
        second = core.export_directory(self.root/'exports', 'same')
        self.assertEqual(second.name, 'same-2')
        self.assertEqual((first/'keep').read_text(), 'important')
        with patch.object(Path, 'mkdir', side_effect=[None]+[FileExistsError()]*9999):
            with self.assertRaisesRegex(ValueError, 'Too many'):
                core.export_directory(self.root/'full', 'same')

    def test_import_rejects_oversized_malformed_and_traversal_layouts(self):
        path = self.root/'layout.json'
        path.write_text(' '* (1024*1024+1))
        with self.assertRaisesRegex(ValueError, 'too large'):
            core.import_layout(path)
        path.write_text('{broken')
        with self.assertRaises(ValueError):
            core.import_layout(path)
        base = dict(image={'path': 'missing.png'}, zoomMode='native')
        for source in ['../outside.png', '.', '..', ['source.png']]:
            core.atomic_json(path, dict(base, sourceImage=source))
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'Invalid source'):
                core.import_layout(path)
        outside = self.source()
        folder = self.root/'cut'
        folder.mkdir()
        (folder/'source.png').symlink_to(outside)
        core.atomic_json(folder/'layout.json', dict(base, sourceImage='source.png'))
        with self.assertRaisesRegex(ValueError, 'inside'):
            core.import_layout(folder)

    def test_import_legacy_missing_source_invalid_mode_and_views(self):
        source = self.source()
        layout = self.root/'layout.json'
        data = dict(image={'path': str(source), 'name': 'original.png'}, zoom=1.4,
                    views={'left': {'zoom': 2, 'panX': 3}}, gap=10)
        core.atomic_json(layout, data)
        result = core.import_layout(self.root)
        self.assertEqual(result['image']['name'], 'original.png')
        self.assertEqual(result['zoomMode'], 'fit')
        self.assertEqual(result['views']['left'], dict(zoom=2, panX=3, panY=0))
        for extra in [dict(zoomMode='bad'), dict(views=[]), dict(views={'left': 1}),
                      dict(views={1: {}}), dict(views={'left': {'zoom': 0}})]:
            # Integer JSON object keys become strings, so validate that case directly below.
            if extra == dict(views={1: {}}):
                with self.assertRaises(ValueError):
                    core.validate_views({1: {}})
                continue
            core.atomic_json(layout, dict(data, **extra))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                core.import_layout(layout)
        source.unlink()
        core.atomic_json(layout, data)
        with self.assertRaisesRegex(ValueError, 'missing'):
            core.import_layout(layout)
        with self.assertRaises(ValueError):
            core.validate_views({str(i): {} for i in range(65)})

    def test_export_validates_display_count_duplicates_and_crop_bounds_before_writing(self):
        request = self.request()
        for frames in [[], [monitor(str(i), i*100) for i in range(33)],
                       [monitor(), monitor()], [monitor(width=1000)], [monitor(width=0)]]:
            with self.subTest(frames=len(frames)), self.assertRaises(ValueError):
                core.render(dict(request, frames=frames))
            self.assertFalse((self.root/'exports').exists())

    def test_render_failure_cleans_partial_export_and_preserves_session(self):
        request = self.request()
        core.atomic_json(core.STATE/'session.json', {'keep': True})
        original = core.magick
        def fail_second(arguments, **kwargs):
            if any('02-right-' in str(value) for value in arguments):
                raise RuntimeError('disk full')
            return original(arguments, **kwargs)
        with patch.object(core, 'magick', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, 'disk full'):
                core.render(request)
        self.assertEqual(list((self.root/'exports').iterdir()), [])
        self.assertEqual(json.loads((core.STATE/'session.json').read_text()), {'keep': True})

    def test_fractional_sampling_and_monitor_density_are_preserved_in_pngs(self):
        request = self.request()
        request['monitors'] = [monitor('left', -100, scale=1.5), monitor('right', 0, scale=2)]
        request['frames'], _ = desktop.composition(request['monitors'], request['image'], 0, {},
                                                  dict(zoom=1.3, panX=.4, panY=-.2))
        first = request['frames'][0]
        request.update(imageScale=first['imageScale'], imageX=first['imageX'], imageY=first['imageY'])
        result = desktop.export(request)
        folder = Path(result['directory'])
        self.assertEqual(core.magick(['identify', '-format', '%wx%h', folder/'01-left-150x120.png']), '150x120')
        self.assertEqual(core.magick(['identify', '-format', '%wx%h', result['panorama']]), '400x160')
        self.assertEqual(json.loads((folder/'layout.json').read_text())['frames'], request['frames'])

    def test_legacy_apply_generation_blocks_stale_result_after_restore(self):
        request = self.request(apply=True)
        result = core.render(request)
        self.assertTrue(result['applied'])
        self.assertEqual(json.loads((core.STATE/'applied.json').read_text()), result['outputs'])
        before = core.theme_generation()
        core.restore(theme_changed=True)
        self.assertNotEqual(core.theme_generation(), before)
        normalized = self.root/'normalized.miff'
        core.magick([request['image']['path'], str(normalized)])
        stale = core.render_normalized(request, normalized, 220, 100, 'stale', before)
        self.assertFalse(stale['applied'])
        self.assertTrue(stale['themeChanged'])
        self.assertEqual(json.loads((core.STATE/'applied.json').read_text()), {})

    def test_physical_coordinate_mutter_layout_and_missing_modes(self):
        spec = ('DP-1', '', '', '')
        physical = [(spec, [('current', 1920, 1080, 60, 1, [2], {'is-current': True})], {})]
        state = (1, physical, [(0, 0, 2, 0, True, [spec], {})], {'layout-mode': 2})
        self.assertEqual(core.parse_monitors(state)[0]['width'], 1920)
        self.assertEqual(core.parse_monitors(state)[0]['scale'], 1)
        for logical, modes in [([], physical), ([(0, 0, 1, 0, True, [], {})], physical),
                               (state[2], [(spec, [], {})])]:
            with self.assertRaises(ValueError):
                core.parse_monitors((1, modes, logical, {}))

    def test_monitor_dbus_boundary_unpacks_mutter_result(self):
        from gi.repository import Gio
        bus = Mock()
        bus.call_sync.return_value.unpack.return_value = ('state',)
        with patch.object(Gio, 'bus_get_sync', return_value=bus), patch.object(core, 'parse_monitors', return_value=['screen']) as parse:
            self.assertEqual(core.monitors(), ['screen'])
        parse.assert_called_once_with(('state',))
        self.assertEqual(bus.call_sync.call_args.args[0], 'org.gnome.Mutter.DisplayConfig')

    def test_panorama_limits_reject_before_rendering(self):
        for dimensions in [(32769, 1), (8000, 8000)]:
            request = dict(monitors=[monitor(width=dimensions[0], height=dimensions[1])])
            with self.subTest(dimensions=dimensions), patch.object(core, 'render') as render:
                with self.assertRaises(ValueError):
                    desktop.export(request)
                render.assert_not_called()
