"""Install into disposable homes; never touch the calling user's installation."""
import os
from pathlib import Path
import subprocess
from helpers import IsolatedTest

SOURCE = Path(__file__).resolve().parents[1]


class InstallTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.home = self.root/'home with spaces'
        self.data = self.root/'data with spaces'
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.data),
                        XDG_CONFIG_HOME=str(self.root/'config'), XDG_STATE_HOME=str(self.root/'state'),
                        WALLPAPER_CUTTER_CONFIG_HOME=str(self.root/'config/wallpaper-cutter-linux'),
                        WALLPAPER_CUTTER_STATE_HOME=str(self.root/'state/wallpaper-cutter-linux'),
                        PYTHONDONTWRITEBYTECODE='1')
        self.target = self.data/'wallpaper-cutter-linux'

    def install(self):
        return subprocess.run(['bash', str(SOURCE/'scripts/install.sh')], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_install_reinstall_launcher_icon_and_preferences_preservation(self):
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        for name in ['src/wallpaper_cutter/app.py', 'src/wallpaper_cutter/core.py', 'src/wallpaper_cutter/desktop.py', 'src/wallpaper_cutter/i18n.py', 'src/wallpaper_cutter/assets/io.github.local.WallpaperCutter.png']:
            self.assertEqual((self.target/name).read_bytes(), (SOURCE/name).read_bytes())
        self.assertTrue((self.target/'.managed-install').is_file())
        launcher = self.home/'.local/bin/wallpaper-cutter'
        self.assertTrue(os.access(launcher, os.X_OK))
        version = subprocess.run([str(launcher), '--version'], env=self.env, capture_output=True, text=True)
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertIn('Wallpaper Cutter ', version.stdout)
        desktop_file = self.data/'applications/wallpaper-cutter.desktop'
        text = desktop_file.read_text()
        self.assertIn(f'Icon={self.target}/src/wallpaper_cutter/assets/io.github.local.WallpaperCutter.png', text)
        self.assertIn(f'TryExec={launcher}\n', text)
        from gi.repository import Gio
        entry = Gio.DesktopAppInfo.new_from_filename(str(desktop_file))
        self.assertTrue(entry.should_show(), 'GNOME must accept and display the generated menu entry')
        # Reinstallation must preserve configuration and exported data.
        preferences = self.root/'config/wallpaper-cutter-linux/preferences.json'
        preferences.parent.mkdir(parents=True, exist_ok=True)
        preferences.write_text('{"language":"en"}')
        cut = self.root/'state/wallpaper-cutter-linux/exports/keep.png'
        cut.parent.mkdir(parents=True)
        cut.write_bytes(b'keep')
        again = self.install()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(preferences.read_text(), '{"language":"en"}')
        self.assertEqual(cut.read_bytes(), b'keep')

    def test_unmanaged_app_directory_is_not_overwritten(self):
        self.target.mkdir(parents=True)
        sentinel = self.target/'app.py'
        sentinel.write_text('unrelated application')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), 'unrelated application')
        self.assertFalse((self.target/'.managed-install').exists())

    def test_upgrade_from_flat_layout_updates_launcher_and_preserves_unrelated_files(self):
        self.target.mkdir(parents=True)
        (self.target/'.managed-install').touch()
        (self.target/'app.py').write_text('legacy code')
        (self.target/'core.py').write_text('legacy code')
        (self.target/'notes.txt').write_text('keep this file')
        cache = self.target/'__pycache__'
        cache.mkdir()
        (cache/'core.cpython-313.pyc').write_bytes(b'old bytecode')
        (cache/'custom.cpython-313.pyc').write_bytes(b'keep unrelated bytecode')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.target/'app.py').exists())
        self.assertFalse((self.target/'core.py').exists())
        self.assertFalse((cache/'core.cpython-313.pyc').exists())
        self.assertEqual((cache/'custom.cpython-313.pyc').read_bytes(), b'keep unrelated bytecode')
        self.assertEqual((self.target/'notes.txt').read_text(), 'keep this file')
        launcher = self.home/'.local/bin/wallpaper-cutter'
        self.assertIn('scripts/run.py', launcher.read_text())
        version = subprocess.run([str(launcher), '--version'], env=self.env, capture_output=True, text=True)
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertIn('Wallpaper Cutter 1.0.0', version.stdout)

    def test_unrelated_launcher_is_not_overwritten(self):
        launcher = self.home/'.local/bin/wallpaper-cutter'
        launcher.parent.mkdir(parents=True)
        launcher.write_text('#!/bin/sh\nexit 42\n')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(launcher.read_text(), '#!/bin/sh\nexit 42\n')
        self.assertFalse(self.target.exists())

    def test_cli_help_english_and_unknown_arguments(self):
        config = self.root/'config/wallpaper-cutter-linux'
        config.mkdir(parents=True)
        (config/'preferences.json').write_text('{"language":"en"}')
        result = subprocess.run(['python', str(SOURCE/'scripts/run.py'), '--help'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Cross-platform multi-display wallpaper editor', result.stdout)
        bad = subprocess.run(['python', str(SOURCE/'scripts/run.py'), '--unknown'], env=self.env,
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
