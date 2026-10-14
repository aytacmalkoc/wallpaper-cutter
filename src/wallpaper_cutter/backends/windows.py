"""Windows IDesktopWallpaper adapter. COM objects stay on the calling thread."""
import ctypes
from pathlib import Path
import uuid


class GUID(ctypes.Structure):
    _fields_ = [('data', ctypes.c_ubyte*16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class RECT(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int32) for name in ('left', 'top', 'right', 'bottom')]


class WindowsDesktop:
    def __init__(self):
        self.ole = ctypes.WinDLL('ole32')
        self.ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.ole.CoInitializeEx.restype = ctypes.c_int32
        initialized = self.ole.CoInitializeEx(None, 2)
        self.uninitialize = initialized in (0, 1)
        if initialized < 0 and initialized != -2147417850:  # RPC_E_CHANGED_MODE
            raise OSError(f'COM initialization failed: {initialized:#x}')
        self.pointer = ctypes.c_void_p()
        clsid = GUID.parse('C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD')
        iid = GUID.parse('B92B56A9-8B55-4E14-9A89-0199BBB6F93B')
        self.ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint32,
                                             ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        self.ole.CoCreateInstance.restype = ctypes.c_int32
        self.ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        self.ole.CoTaskMemFree.restype = None
        result = self.ole.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(self.pointer))
        if result < 0:
            if self.uninitialize:
                self.ole.CoUninitialize()
            raise OSError(f'IDesktopWallpaper is unavailable: {result:#x}')

    def _call(self, index, types, *arguments):
        table = ctypes.cast(self.pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        function = ctypes.WINFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *types)(table[index])
        result = function(self.pointer, *arguments)
        if result < 0:
            raise OSError(f'Windows wallpaper operation failed: {result:#x}')
        return result

    def _string(self, index, types, *arguments):
        output = ctypes.c_void_p()
        self._call(index, [*types, ctypes.POINTER(ctypes.c_void_p)], *arguments, ctypes.byref(output))
        try:
            return ctypes.wstring_at(output) if output.value else ''
        finally:
            if output.value:
                self.ole.CoTaskMemFree(output)

    def _number(self, index):
        output = ctypes.c_uint32()
        self._call(index, [ctypes.POINTER(ctypes.c_uint32)], ctypes.byref(output))
        return output.value

    def monitors(self):
        result = []
        for index in range(self._number(6)):
            identifier = self._string(5, [ctypes.c_uint32], index)
            rect = RECT()
            status = self._call(7, [ctypes.c_wchar_p, ctypes.POINTER(RECT)], identifier, ctypes.byref(rect))
            if status != 0 or rect.right <= rect.left or rect.bottom <= rect.top:
                continue
            width, height = rect.right-rect.left, rect.bottom-rect.top
            result.append(dict(name=f'Display {index+1}', nativeId=identifier, x=rect.left, y=rect.top,
                               width=width, height=height, pixelWidth=width, pixelHeight=height, scale=1))
        if not result:
            raise ValueError('No active Windows displays found.')
        return sorted(result, key=lambda m: (m['x'], m['y'], m['name']))

    def capture(self):
        status = self._number(17)
        if status & 2:
            raise ValueError('Windows slideshow wallpapers cannot be restored safely. Export the cuts or switch to a static wallpaper first.')
        state = dict(backend='windows', enabled=bool(status & 1), position=self._number(11), color=self._number(9),
                    images={m['nativeId']: self._string(4, [ctypes.c_wchar_p], m['nativeId']) for m in self.monitors()})
        if any(not image for image in state['images'].values()):
            raise ValueError('The previous Windows desktop image is unavailable. Export the cuts or choose a static wallpaper first.')
        return state

    def prepare(self, outputs):
        current = self.capture()
        monitors = self.monitors()
        if not outputs or any(m['name'] not in outputs for m in monitors):
            raise ValueError('A native crop is required for every display.')
        from ..platform_runtime import file_uri_path
        return dict(current, enabled=True, position=2, images={m['nativeId']: file_uri_path(outputs[m['name']], 'win32') for m in monitors})

    def write(self, state):
        if set(state['images']) != {m['nativeId'] for m in self.monitors()}:
            raise ValueError('The display layout changed. Refresh displays before applying.')
        self._call(10, [ctypes.c_uint32], state['position'])
        self._call(8, [ctypes.c_uint32], state['color'])
        for identifier, path in state['images'].items():
            self._call(3, [ctypes.c_wchar_p, ctypes.c_wchar_p], identifier, path)
        # SetWallpaper enables the background; restore its previous enabled state last.
        self._call(18, [ctypes.c_int32], int(state['enabled']))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.pointer.value:
            self._call(2, [])
            self.pointer = ctypes.c_void_p()
        if self.uninitialize:
            self.ole.CoUninitialize()
