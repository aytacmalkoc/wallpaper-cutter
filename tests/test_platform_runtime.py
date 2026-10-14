"""Portable paths, URI contracts, lock branches and source installation."""
import json
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock, patch
from helpers import IsolatedTest
from wallpaper_cutter import core
from scripts import install
from wallpaper_cutter import platform_runtime as runtime
from wallpaper_cutter.backends import desktop as backends


class RuntimeTests(IsolatedTest):
    def test_paths_preserve_linux_data_and_follow_windows_and_macos_conventions(self):
        home = self.root/'home'
        linux = runtime.directories('linux', {}, home)
        self.assertEqual(linux, (home/'.config/wallpaper-cutter-linux', home/'.local/state/wallpaper-cutter-linux'))
        windows = runtime.directories('win32', {'APPDATA': str(self.root/'roaming'), 'LOCALAPPDATA': str(self.root/'local')}, home)
        self.assertEqual(windows, (self.root/'roaming/WallpaperCutter', self.root/'local/WallpaperCutter/state'))
        mac = runtime.directories('darwin', {}, home)
        self.assertEqual(mac[0], home/'Library/Application Support/WallpaperCutter')
        self.assertEqual(mac[1], mac[0]/'state')
        overridden = runtime.directories('darwin', {'WALLPAPER_CUTTER_CONFIG_HOME': str(self.root/'config'),
                                                   'WALLPAPER_CUTTER_STATE_HOME': str(self.root/'state')}, home)
        self.assertEqual(overridden, (self.root/'config', self.root/'state'))

    def test_file_uris_handle_windows_drives_unc_spaces_and_unicode(self):
        self.assertEqual(runtime.file_uri_path('file:///C:/pictures/a%20b.png', 'win32'), 'C:\\pictures\\a b.png')
        self.assertEqual(runtime.file_uri_path('file://server/share/a.png', 'win32'), '\\\\server\\share\\a.png')
        self.assertEqual(runtime.file_uri_path('file:///tmp/%C3%BC.png', 'linux'), '/tmp/ü.png')
        self.assertEqual(runtime.file_uri_path('file://localhost/tmp/a.png', 'darwin'), '/tmp/a.png')
        for uri in ['https://example.com/image.png', 'file://remote/path']:
            with self.assertRaises(ValueError):
                runtime.file_uri_path(uri, 'linux')

    def test_posix_and_windows_lock_release_even_on_exception(self):
        path = self.root/'lock'
        with runtime.file_lock(path):
            self.assertTrue(path.exists())
        fake = SimpleNamespace(LK_LOCK=1, LK_UNLCK=2, locking=Mock())
        with patch.object(runtime.sys, 'platform', 'win32'), patch.dict('sys.modules', msvcrt=fake):
            with self.assertRaises(RuntimeError):
                with runtime.file_lock(self.root/'windows-lock'):
                    raise RuntimeError('intentional')
        self.assertEqual([call.args[1:] for call in fake.locking.call_args_list], [(1, 1), (2, 1)])

    def test_imagemagick_six_dispatch_and_windows_never_uses_system_convert(self):
        which = lambda name: '/tools/'+name if name in ('convert', 'identify') else None
        with patch.object(core.sys, 'platform', 'linux'), patch.object(core.shutil, 'which', side_effect=which), patch.object(core.subprocess, 'run') as run:
            run.return_value.stdout = b'12x8'
            self.assertEqual(core.magick(['identify', 'image.png']), '12x8')
            self.assertEqual(run.call_args.args[0], ['/tools/identify', 'image.png'])
            core.magick(['-size', '12x8', 'xc:red', 'out.png'])
            self.assertEqual(run.call_args.args[0][0], '/tools/convert')
            with patch.object(core.sys, 'platform', 'win32'), self.assertRaisesRegex(RuntimeError, 'Install ImageMagick'):
                core.magick(['input.png', 'output.png'])

    def test_portable_export_names_reject_reserved_windows_and_invalid_characters(self):
        for name in ['CON', 'nul.txt', 'COM1', 'LPT9.png', 'name.', 'a:b', 'a?b', 'a*b', 'a|b', 'a<b']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.export_name({'exportName': name})
        self.assertEqual(core.export_name({'image': {'path': 'x', 'name': 'a:b?.png'}}), 'cut-a_b_')
        with patch.object(core, 'Path', PureWindowsPath):
            self.assertEqual(core.export_name({'image': {'path': 'x', 'name': 'a:b?.png'}}), 'cut-a_b_')

    def test_windows_and_macos_installers_copy_all_modules_and_generate_safe_launchers(self):
        for system in ['win32', 'darwin']:
            home = self.root/system/'home with spaces ü'
            env = {'LOCALAPPDATA': str(self.root/system/'local ü')}
            launcher = install.install(system, env, home)
            target, _, desktop = install.targets(system, env, home)
            self.assertIsNone(desktop)
            for name in install.FILES:
                self.assertTrue((target/name).is_file(), name)
            text = launcher.read_text(encoding='utf-8')
            self.assertIn('Wallpaper Cutter managed launcher', text)
            if system == 'win32':
                self.assertIn('PYGI_DLL_PATH=', text)
                self.assertIn('chcp 65001', text)
                self.assertIn('%*', text)
            else:
                self.assertIn('"$@"', text)
            self.assertEqual(install.install(system, env, home), launcher)

    def test_missing_source_and_unrelated_desktop_entry_are_not_overwritten(self):
        with self.assertRaises(FileNotFoundError):
            install.install('linux', {}, self.root/'new-home', self.root/'missing-source')
        self.assertFalse((self.root/'new-home').exists())
        home = self.root/'home'
        target, launcher, desktop = install.targets('linux', {}, home)
        desktop.parent.mkdir(parents=True)
        desktop.write_text('[Desktop Entry]\nName=Other app\n')
        with self.assertRaises(RuntimeError):
            install.install('linux', {}, home)
        self.assertEqual(desktop.read_text(), '[Desktop Entry]\nName=Other app\n')
        self.assertFalse(target.exists())

    def test_installer_preserves_virtual_environment_python_without_resolving_symlinks(self):
        executable = self.root/'venv/bin/python'
        source = Path(install.__file__).parent.parent
        with patch.object(install.sys, 'executable', str(executable)), \
             patch.object(type(executable), 'resolve', side_effect=AssertionError('Do not resolve venv Python')):
            launcher = install.install('darwin', {}, self.root/'home', source)
        self.assertIn(str(executable), launcher.read_text(encoding='utf-8'))

    def test_desktop_exec_quoting_preserves_literal_metacharacters(self):
        quoted = install.desktop_quote('/tmp/a b%$`"\\file')
        self.assertTrue(quoted.startswith('"') and quoted.endswith('"'))
        self.assertIn('%%', quoted)
        self.assertIn('\\$', quoted)
        self.assertIn('\\`', quoted)

    def test_native_routing_and_missing_api_fallback_do_not_require_gnome(self):
        from wallpaper_cutter.backends import windows as native_windows
        from wallpaper_cutter.backends import macos as native_macos
        native = Mock()
        native.__enter__ = Mock(return_value=native)
        native.__exit__ = Mock()
        native.monitors.return_value = [{'name': 'native display'}]
        with patch.object(core.sys, 'platform', 'win32'), patch.object(native_windows, 'WindowsDesktop', return_value=native):
            self.assertEqual(core.monitors(), native.monitors.return_value)
            self.assertIsInstance(backends.select_backend(), backends.NativeBackend)
        with patch.object(core.sys, 'platform', 'win32'), patch.object(native_windows, 'WindowsDesktop', side_effect=OSError('API unavailable')), \
             patch.object(core, 'gdk_monitors', return_value=[{'name': 'fallback display'}]):
            self.assertFalse(backends.select_backend().supported)
            self.assertEqual(core.monitors(), [{'name': 'fallback display'}])
        with patch.object(core.sys, 'platform', 'darwin'), patch.dict('sys.modules', AppKit=SimpleNamespace()), \
             patch.object(native_macos, 'MacDesktop', return_value=native):
            self.assertIsInstance(backends.select_backend(), backends.NativeBackend)
            self.assertEqual(core.monitors(), native.monitors.return_value)
        with patch.object(core.sys, 'platform', 'darwin'), patch.dict('sys.modules', AppKit=None), \
             patch.object(native_macos, 'MacDesktop', side_effect=ImportError('Cocoa unavailable')), \
             patch.object(core, 'gdk_monitors', return_value=[{'name': 'fallback display'}]):
            self.assertFalse(backends.select_backend().supported)
            self.assertEqual(core.monitors(), [{'name': 'fallback display'}])
