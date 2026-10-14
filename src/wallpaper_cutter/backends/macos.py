"""macOS AppKit display/wallpaper adapter, loaded only on macOS."""
import threading


class MacDesktop:
    def __init__(self, api=None):
        if api is None:
            import AppKit
            api = AppKit
        self.api = api
        self.workspace = api.NSWorkspace.sharedWorkspace()

    def _screens(self):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('AppKit desktop operations must run on the main thread.')
        return list(self.api.NSScreen.screens())

    @staticmethod
    def _id(screen):
        return str(screen.deviceDescription()['NSScreenNumber'])

    def monitors(self):
        screens = self._screens()
        if not screens:
            raise ValueError('No active macOS displays found.')
        primary_height = screens[0].frame().size.height
        result = []
        for screen in screens:
            frame = screen.frame()
            scale = screen.backingScaleFactor()
            width, height = frame.size.width, frame.size.height
            identifier = self._id(screen)
            result.append(dict(name=f'Display {identifier}', nativeId=identifier,
                               x=frame.origin.x, y=primary_height-frame.origin.y-height,
                               width=width, height=height, pixelWidth=round(width*scale),
                               pixelHeight=round(height*scale), scale=scale))
        return sorted(result, key=lambda m: (m['x'], m['y'], m['name']))

    def capture(self):
        images = {}
        for screen in self._screens():
            url = self.workspace.desktopImageURLForScreen_(screen)
            if url is None:
                raise ValueError('The previous macOS desktop image is unavailable. Export the cuts instead.')
            options = self.workspace.desktopImageOptionsForScreen_(screen) or {}
            value = dict(url=str(url.absoluteString()), scale=int(options.get(self.api.NSWorkspaceDesktopImageScalingKey, 3)),
                         clip=bool(options.get(self.api.NSWorkspaceDesktopImageAllowClippingKey, True)),
                         color=[0.0, 0.0, 0.0, 1.0])
            color = options.get(self.api.NSWorkspaceDesktopImageFillColorKey)
            if color is not None:
                rgb = color.colorUsingColorSpace_(self.api.NSColorSpace.genericRGBColorSpace())
                if rgb is None:
                    raise ValueError('The desktop fill color cannot be backed up safely.')
                value['color'] = list(rgb.getRed_green_blue_alpha_(None, None, None, None))
            images[self._id(screen)] = value
        return dict(backend='macos', images=images)

    def prepare(self, outputs):
        current = self.capture()
        monitors = self.monitors()
        if not outputs or any(m['name'] not in outputs for m in monitors):
            raise ValueError('A native crop is required for every display.')
        return dict(backend='macos', images={m['nativeId']: dict(current['images'][m['nativeId']],
                    url=outputs[m['name']], scale=1, clip=False) for m in monitors})

    def write(self, state):
        screens = {self._id(s): s for s in self._screens()}
        if set(state['images']) != set(screens):
            raise ValueError('The display layout changed. Refresh displays before applying.')
        for identifier, value in state['images'].items():
            options = {self.api.NSWorkspaceDesktopImageScalingKey: value['scale'],
                       self.api.NSWorkspaceDesktopImageAllowClippingKey: value['clip']}
            if 'color' in value:
                options[self.api.NSWorkspaceDesktopImageFillColorKey] = self.api.NSColor.colorWithCalibratedRed_green_blue_alpha_(*value['color'])
            url = self.api.NSURL.URLWithString_(value['url'])
            ok, error = self.workspace.setDesktopImageURL_forScreen_options_error_(url, screens[identifier], options, None)
            if not ok:
                raise OSError(str(error))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False
