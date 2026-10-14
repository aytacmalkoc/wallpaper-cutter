"""Packaging inventory preserves IM6 command names and module dependencies."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bootstrap

spec = importlib.util.spec_from_file_location('desktop_build', bootstrap.ROOT/'packaging/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class PackagingTests(unittest.TestCase):
    def test_im6_symlink_targets_keep_command_names_and_include_dynamic_codecs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root/'runtime'
            (prefix/'bin').mkdir(parents=True)
            convert = prefix/'bin/convert-im6.q16'
            identify = prefix/'bin/identify-im6.q16'
            convert.write_text('converter')
            identify.write_text('identifier')
            coders = prefix/'lib/x86_64-linux-gnu/ImageMagick-6.9/modules-Q16/coders'
            coders.mkdir(parents=True)
            (coders/'png.so').write_text('shared codec')
            (coders/'png.la').write_text("dlname='png.so'")
            config = prefix/'etc/ImageMagick-6'
            config.mkdir(parents=True)
            (config/'policy.xml').write_text('<policymap/>')
            with patch.object(build, 'ROOT', root), patch.object(build.sys, 'platform', 'linux'), \
                 patch.object(build.subprocess, 'check_output', return_value=f'CODER_PATH {coders}\nCONFIGURE_PATH {config}\n'), \
                 patch.object(build.shutil, 'which', return_value=str(identify)):
                binaries, datas = build.image_inventory(convert)
            names = {Path(source).name for source, _ in binaries}
            self.assertEqual(names, {'convert', 'identify', 'png.so'})
            self.assertIn((str(config/'policy.xml'), 'imagemagick/config'), datas)
            self.assertIn((str(coders/'png.la'), 'imagemagick/modules'), datas)
            self.assertEqual((root/'build/image-bin/convert').read_text(), 'converter')

    def test_stable_versions_required_before_creating_installers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'pyproject.toml').write_text('[project]\nversion="1.0.1-dev"\n')
            with patch.object(build, 'ROOT', root), self.assertRaises(ValueError):
                build.version()

    def test_corrupt_packaging_tool_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'dist/wallpaper-cutter').mkdir(parents=True)
            (root/'packaging/linux').mkdir(parents=True)
            (root/'packaging/linux/AppRun').write_text('#!/bin/sh\n')
            (root/'packaging/linux/wallpaper-cutter.desktop').write_text('Exec=@LAUNCHER@\n')
            (root/'build').mkdir()
            (root/'build/appimagetool.AppImage').write_bytes(b'corrupt executable')
            icon = root/'icon.png'
            icon.write_bytes(b'icon')
            with patch.object(build, 'ROOT', root), patch.object(build, 'ICON', icon), \
                 patch.object(build, 'run') as run, patch.object(build.platform, 'machine', return_value='x86_64'), \
                 self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                build.appimage()
            self.assertEqual(run.call_count, 1)  # desktop-file validation only
