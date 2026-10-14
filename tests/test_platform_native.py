"""Native API contract tests; no operating-system wallpaper writes."""
import ctypes
import bootstrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from wallpaper_cutter.backends import windows as win
from wallpaper_cutter.backends import macos as mac


class FakeWindowsCOM:
    def __init__(self):
        self.images = {'left-id': 'C:\\before-left.png', 'right-id': 'C:\\before-right.png'}
        self.position, self.color, self.status = 4, 123, 1
        self.callbacks, self.buffers = [], []
        self.failed_method = None
        self.ole = Mock()
        self.ole.CoInitializeEx.return_value = 0
        self.ole.CoCreateInstance.side_effect = self.create
        self.table = (ctypes.c_void_p*19)()
        def method(index, types, function):
            def invoke(pointer, *arguments):
                return -2147467259 if self.failed_method == index else function(*arguments)
            callback = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *types)(invoke)
            self.callbacks.append(callback)
            self.table[index] = ctypes.cast(callback, ctypes.c_void_p).value
        string_out = ctypes.POINTER(ctypes.c_void_p)
        number_out = ctypes.POINTER(ctypes.c_uint32)
        method(2, [], lambda: 1)
        method(6, [number_out], lambda out: self.number(out, 2))
        method(5, [ctypes.c_uint32, string_out], lambda i, out: self.string(out, list(self.images)[i]))
        method(7, [ctypes.c_wchar_p, ctypes.POINTER(win.RECT)], self.rect)
        method(4, [ctypes.c_wchar_p, string_out], lambda key, out: self.string(out, self.images[key]))
        method(3, [ctypes.c_wchar_p, ctypes.c_wchar_p], self.wallpaper)
        method(9, [number_out], lambda out: self.number(out, self.color))
        method(11, [number_out], lambda out: self.number(out, self.position))
        method(17, [number_out], lambda out: self.number(out, self.status))
        method(8, [ctypes.c_uint32], lambda value: self.assign('color', value))
        method(10, [ctypes.c_uint32], lambda value: self.assign('position', value))
        method(18, [ctypes.c_int32], lambda value: self.assign('status', 1 if value else 0))
        self.interface = (ctypes.c_void_p*1)(ctypes.cast(self.table, ctypes.c_void_p).value)

    def create(self, clsid, parent, flags, iid, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = ctypes.addressof(self.interface)
        return 0

    @staticmethod
    def number(output, value):
        output[0] = value
        return 0

    def string(self, output, value):
        buffer = ctypes.create_unicode_buffer(value)
        self.buffers.append(buffer)
        output[0] = ctypes.cast(buffer, ctypes.c_void_p).value
        return 0

    def rect(self, key, rect):
        values = (-100, 0, 0, 80) if key == 'left-id' else (0, 0, 200, 120)
        rect.contents.left, rect.contents.top, rect.contents.right, rect.contents.bottom = values
        return 0

    def assign(self, key, value):
        setattr(self, key, value)
        return 0

    def wallpaper(self, key, value):
        self.images[key] = value
        self.status = 1
        return 0


class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWindowsCOM()
        self.enterContext(patch.object(ctypes, 'WinDLL', return_value=self.fake.ole, create=True))
        self.enterContext(patch.object(ctypes, 'WINFUNCTYPE', ctypes.CFUNCTYPE, create=True))

    def test_com_abi_monitors_per_display_apply_capture_and_restore(self):
        self.assertEqual(ctypes.sizeof(win.GUID), 16)
        self.assertEqual(ctypes.sizeof(win.RECT), 16)
        with win.WindowsDesktop() as native:
            monitors = native.monitors()
            self.assertEqual(monitors[0]['x'], -100)
            self.assertEqual(monitors[1]['pixelWidth'], 200)
            before = native.capture()
            target = native.prepare({'Display 1': 'file:///C:/images/left%20cut.png',
                                     'Display 2': 'file:///C:/images/right.png'})
            native.write(target)
            self.assertEqual(native.capture(), target)
            self.assertEqual(self.fake.images['left-id'], 'C:\\images\\left cut.png')
            native.write(before)
            self.assertEqual(native.capture(), before)
        self.fake.ole.CoUninitialize.assert_called_once()
        self.assertTrue(self.fake.ole.CoTaskMemFree.called)

    def test_hresult_failure_slideshow_and_layout_change_are_rejected(self):
        with win.WindowsDesktop() as native:
            self.fake.failed_method = 6
            with self.assertRaises(OSError):
                native.monitors()
            self.fake.failed_method = None
            self.fake.status = 3
            with self.assertRaisesRegex(ValueError, 'slideshow'):
                native.capture()
            self.fake.status = 1
            with self.assertRaises(ValueError):
                native.prepare({})
            state = native.capture()
            state['images'] = {'missing-id': 'x'}
            with self.assertRaises(ValueError):
                native.write(state)

    def test_changed_com_apartment_is_not_uninitialized_by_this_adapter(self):
        self.fake.ole.CoInitializeEx.return_value = -2147417850
        with win.WindowsDesktop():
            pass
        self.fake.ole.CoUninitialize.assert_not_called()

    def test_disabled_background_state_is_restored_and_missing_previous_image_is_rejected(self):
        self.fake.status = 0
        with win.WindowsDesktop() as native:
            before = native.capture()
            self.assertFalse(before['enabled'])
            desired = native.prepare({'Display 1': 'file:///C:/left.png', 'Display 2': 'file:///C:/right.png'})
            native.write(desired)
            self.assertTrue(native.capture()['enabled'])
            native.write(before)
            self.assertEqual(native.capture(), before)
            self.fake.images['left-id'] = ''
            with self.assertRaisesRegex(ValueError, 'previous Windows desktop image'):
                native.capture()

    def test_com_creation_failure_releases_owned_apartment(self):
        self.fake.ole.CoCreateInstance.side_effect = None
        self.fake.ole.CoCreateInstance.return_value = -2147467259
        with self.assertRaises(OSError):
            win.WindowsDesktop()
        self.fake.ole.CoUninitialize.assert_called_once()


class FakeColor:
    def __init__(self, rgba):
        self.rgba = rgba

    def colorUsingColorSpace_(self, space):
        return self

    def getRed_green_blue_alpha_(self, *arguments):
        return self.rgba


class FakeURL:
    def __init__(self, value):
        self.value = value

    def absoluteString(self):
        return self.value


class MacTests(unittest.TestCase):
    def setUp(self):
        def screen(identifier, x, y, width, height, scale):
            frame = SimpleNamespace(origin=SimpleNamespace(x=x, y=y), size=SimpleNamespace(width=width, height=height))
            return SimpleNamespace(deviceDescription=lambda: {'NSScreenNumber': identifier},
                                   frame=lambda: frame, backingScaleFactor=lambda: scale)
        self.screens = [screen(7, 0, 0, 100, 80, 2), screen(9, -100, 0, 100, 100, 1)]
        self.states = {str(i): {'url': f'file:///before-{i}.png', 'scale': 3, 'clip': True,
                               'color': [0.1, 0.2, 0.3, 1.0]} for i in (7, 9)}
        workspace = SimpleNamespace(desktopImageURLForScreen_=lambda s: FakeURL(self.states[mac.MacDesktop._id(s)]['url']),
            desktopImageOptionsForScreen_=lambda s: {'Scaling': self.states[mac.MacDesktop._id(s)]['scale'],
                'Clip': self.states[mac.MacDesktop._id(s)]['clip'], 'Fill': FakeColor(self.states[mac.MacDesktop._id(s)]['color'])},
            setDesktopImageURL_forScreen_options_error_=self.write)
        self.api = SimpleNamespace(NSScreen=SimpleNamespace(screens=lambda: self.screens),
            NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace),
            NSWorkspaceDesktopImageScalingKey='Scaling', NSWorkspaceDesktopImageAllowClippingKey='Clip',
            NSWorkspaceDesktopImageFillColorKey='Fill', NSURL=SimpleNamespace(URLWithString_=FakeURL),
            NSColorSpace=SimpleNamespace(genericRGBColorSpace=lambda: 'rgb'),
            NSColor=SimpleNamespace(colorWithCalibratedRed_green_blue_alpha_=lambda *rgba: FakeColor(rgba)))
        self.native = mac.MacDesktop(self.api)

    def write(self, url, screen, options, error):
        self.states[mac.MacDesktop._id(screen)] = dict(url=url.value, scale=options['Scaling'],
                clip=options['Clip'], color=list(options['Fill'].rgba))
        return True, None

    def test_retina_coordinates_per_display_images_and_all_original_options_restore(self):
        monitors = self.native.monitors()
        self.assertEqual((monitors[0]['x'], monitors[0]['y']), (-100, -20))
        self.assertEqual(monitors[1]['pixelWidth'], 200)
        before = self.native.capture()
        target = self.native.prepare({'Display 7': 'file:///left.png', 'Display 9': 'file:///right.png'})
        self.native.write(target)
        self.assertEqual(self.native.capture(), target)
        self.native.write(before)
        self.assertEqual(self.native.capture(), before)

    def test_missing_crop_changed_layout_and_native_failure_are_reported(self):
        with self.assertRaises(ValueError):
            self.native.prepare({})
        before = self.native.capture()
        self.screens.pop()
        with self.assertRaises(ValueError):
            self.native.write(before)
        self.native.workspace.setDesktopImageURL_forScreen_options_error_ = lambda *args: (False, 'permission denied')
        before = self.native.capture()
        with self.assertRaisesRegex(OSError, 'permission denied'):
            self.native.write(before)

    def test_appkit_is_main_thread_only_and_missing_wallpaper_fails_safely(self):
        with patch.object(mac.threading, 'current_thread', return_value=object()), self.assertRaises(RuntimeError):
            self.native.monitors()
        self.native.workspace.desktopImageURLForScreen_ = lambda screen: None
        with self.assertRaises(ValueError):
            self.native.capture()
