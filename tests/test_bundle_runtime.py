"""Private runtime paths and package verification failure contracts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import bootstrap
from wallpaper_cutter import bundle_runtime, __version__


class BundleRuntimeTests(unittest.TestCase):
    def test_source_runtime_leaves_environment_unchanged(self):
        env = {'PATH': '/system/tools'}
        with patch.object(sys, 'frozen', False, create=True):
            bundle_runtime.configure(environment=env)
        self.assertEqual(env, {'PATH': '/system/tools'})

    def test_private_im6_never_selects_host_im7_and_missing_tools_fail_closed(self):
        from wallpaper_cutter import core
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root/'imagemagick/bin'
            tools.mkdir(parents=True)
            for name in ('convert', 'identify'):
                (tools/name).touch()
            with patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, '_MEIPASS', str(root), create=True), \
                 patch.object(sys, 'platform', 'linux'), \
                 patch.object(bundle_runtime.shutil, 'which', return_value='/usr/bin/magick') as host, \
                 patch.object(core.subprocess, 'run') as run:
                run.return_value.stdout = b'220 100'
                core.magick(['identify', 'source.png'])
                self.assertEqual(run.call_args.args[0], [str(tools/'identify'), 'source.png'])
                core.magick(['source.png', 'output.png'])
                self.assertEqual(run.call_args.args[0][0], str(tools/'convert'))
                (tools/'convert').unlink()
                with self.assertRaisesRegex(RuntimeError, 'ImageMagick is missing'):
                    core.magick(['source.png'])
                host.assert_not_called()

    def test_frozen_tools_precede_host_tools_and_coders_ignore_host_settings(self):
        env = {'PATH': '/system/tools', 'MAGICK_CODER_MODULE_PATH': '/host/coders'}
        root = Path('/bundle with spaces')
        bundle_runtime.configure(root, env)
        self.assertEqual(env['PATH'].split(bundle_runtime.os.pathsep)[:2],
                         [str(root/'imagemagick/bin'), str(root)])
        self.assertEqual(env['MAGICK_CODER_MODULE_PATH'], str(root/'imagemagick/modules'))
        self.assertEqual(env['MAGICK_CONFIGURE_PATH'], str(root/'imagemagick/config'))

    def test_package_failure_writes_report_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp)/'report.json'
            with patch.dict('sys.modules', {'gi': None}):
                self.assertEqual(bundle_runtime.package_check(report), 1)
            result = json.loads(report.read_text())
            self.assertFalse(result['success'])
            self.assertIn('error', result)

    def test_system_tools_use_host_libraries_without_changing_image_runtime(self):
        from wallpaper_cutter.backends.desktop import XfceBackend
        env = {'LD_LIBRARY_PATH': '/bundle', 'LD_LIBRARY_PATH_ORIG': '/host',
               'DYLD_LIBRARY_PATH': '/bundle', 'GIO_MODULE_DIR': '/bundle/gio',
               'DISPLAY': ':99'}
        with patch.object(sys, 'frozen', True, create=True):
            host = bundle_runtime.host_environment(env)
            self.assertEqual(host['LD_LIBRARY_PATH'], '/host')
            self.assertNotIn('DYLD_LIBRARY_PATH', host)
            self.assertNotIn('GIO_MODULE_DIR', host)
            self.assertEqual(env['LD_LIBRARY_PATH'], '/bundle')
            with patch.dict(bundle_runtime.os.environ, env, clear=True), \
                 patch('wallpaper_cutter.backends.desktop.subprocess.run') as run:
                XfceBackend.query('-l')
                self.assertEqual(run.call_args.kwargs['env'], host)
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(bundle_runtime.host_environment(env), env)

    def test_versions_and_runtime_files_stay_consistent(self):
        import tomllib
        from scripts import install
        root = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((root/'pyproject.toml').read_text())
        self.assertEqual(metadata['project']['version'], __version__)
        self.assertIn('X-Wallpaper-Cutter-Version='+__version__,
                      (root/'packaging/linux/wallpaper-cutter.desktop').read_text())
        self.assertIn('bundle_runtime.py', install.PACKAGE_FILES)
