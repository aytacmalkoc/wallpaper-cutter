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

    def test_versions_and_runtime_files_stay_consistent(self):
        import tomllib
        from scripts import install
        root = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((root/'pyproject.toml').read_text())
        self.assertEqual(metadata['project']['version'], __version__)
        self.assertIn('X-Wallpaper-Cutter-Version='+__version__,
                      (root/'packaging/linux/wallpaper-cutter.desktop').read_text())
        self.assertIn('bundle_runtime.py', install.PACKAGE_FILES)
