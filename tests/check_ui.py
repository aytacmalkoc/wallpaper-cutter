"""Real GTK feedback and preview checks; wallpaper writes use a memory backend."""
from pathlib import Path
import logging
import sys
import traceback
from unittest.mock import patch
import bootstrap
from wallpaper_cutter import app
from wallpaper_cutter import core
from wallpaper_cutter import desktop
from gi.repository import Gtk, Gio, GLib, GdkPixbuf
import cairo

logging.basicConfig(level=logging.CRITICAL)
application = Gtk.Application(application_id='io.github.local.WallpaperCutter.Check',
                              flags=Gio.ApplicationFlags.NON_UNIQUE)
exit_code = 0
patches = []
stages = [
    ('export failure', 'Görsel kaydedilemedi: test hatası', None, False),
    ('apply failure', None, 'GNOME ayarına yazılamadı: test hatası', False),
    ('layout changed', None, None, True),
    ('successful retry', None, None, False),
]


def finish(error=None):
    global exit_code
    for item in patches:
        item.stop()
    patches.clear()
    if error:
        print('FAIL:', error)
        traceback.print_exc()
        exit_code = 1
    application.quit()
    return GLib.SOURCE_REMOVE


def capture(window, name):
    snapshot = Gtk.Snapshot.new()
    Gtk.WidgetPaintable.new(window).snapshot(snapshot, window.get_width(), window.get_height())
    texture = window.get_renderer().render_texture(snapshot.to_node(), None)
    texture.save_to_png(str(core.STATE/name))


def check_preview(window):
    width, height = window.canvas.get_width(), window.canvas.get_height()
    assert abs(window.preview_zoom-.7) < 1e-9
    assert window.preview_label.get_text() == '%70'
    assert window.preview_slider.get_orientation() == Gtk.Orientation.VERTICAL
    assert window.preview_slider.get_inverted()
    assert window.preview_overlay.get_child() == window.canvas
    allocation = window.preview_tools.get_allocation()
    assert allocation.width <= 70 and allocation.height <= 240, (allocation.width, allocation.height)
    assert allocation.x >= width-85 and 0 <= allocation.y <= 20, (allocation.x, allocation.y)
    print('PASS: compact vertical control at canvas top right; preview starts at 70%')
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    window.draw(window.canvas, cairo.Context(surface), width, height)
    frames, _ = window.composition()
    first = frames[0]
    assert first['imageScale'] == 1
    assert (first['imageX'], first['imageY']) == ((3840-4000)/2, (1080-3000)/2)
    ox, oy = window.view_origin
    scale = window.view_scale
    # The entire photo must fit even though its top/bottom fall outside all screens.
    photo_width = window.picture['width']*first['imageScale']
    photo_height = window.picture['height']*first['imageScale']
    left, top = ox+first['imageX']*scale, oy+first['imageY']*scale
    assert left >= 34 and top >= 34
    assert left+photo_width*scale <= width-34
    assert top+photo_height*scale <= height-34
    data = surface.get_data()
    def red(x, y):
        i = int(y)*surface.get_stride()+int(x)*4
        return data[i+2]
    inside = red(ox+(first['x']+first['width']/2)*scale,
                 oy+(first['y']+first['height']/2)*scale)
    outside = red(left+photo_width*scale/4, top+photo_height*scale*.05)
    assert inside > 180, inside
    assert 45 < outside < inside*.7, (inside, outside)
    surface.write_to_png(str(core.STATE/'dimmed-source-preview.png'))
    camera = (window.view_origin, window.view_scale)
    selected = window.selected
    original_pixels = bytes(surface.get_data())
    rectangles = [(ox+f['x']*scale, oy+f['y']*scale,
                   f['width']*scale, f['height']*scale) for f in frames]

    def redraw_fixed_frames():
        before = window.composition()[0]
        result = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        window.draw(window.canvas, cairo.Context(result), width, height)
        result.flush()
        assert window.composition()[0] == before, 'Preview changed exported transforms'
        assert (window.view_origin, window.view_scale) == camera, 'Camera moved during pan/zoom'
        x, y = window.view_origin
        current = [(x+f['x']*window.view_scale, y+f['y']*window.view_scale,
                    f['width']*window.view_scale, f['height']*window.view_scale) for f in before]
        assert current == rectangles, 'Monitor rectangles moved during pan/zoom'
        # Check the actual selected outline remains painted at the same pixels.
        bx, by, bw, bh = rectangles[window.selected]
        offset = int(by+bh/2)*result.get_stride()+int(bx)*4
        blue, green, red = result.get_data()[offset:offset+3]
        assert blue > 200 and green > 150 and red < 100, (blue, green, red)
        return result, before[0]

    bx, by, bw, bh = rectangles[0]
    window.drag_begin(None, bx+bw/2, by+bh/2)
    for dx, dy in [(24, -12), (48, -24)]:
        window.drag_update(None, dx, dy)
        moved, current = redraw_fixed_frames()
        assert abs(ox+current['imageX']*scale-left-dx) < 1e-7
        assert abs(oy+current['imageY']*scale-top-dy) < 1e-7
        assert bytes(moved.get_data()) != original_pixels, 'Image pixels did not move'
    moved.write_to_png(str(core.STATE/'panned-source-preview.png'))
    window.zoom_slider.set_value(2)
    _, current = redraw_fixed_frames()
    assert current['imageScale'] == 2
    window.scroll(None, 0, -1)
    zoomed, current = redraw_fixed_frames()
    assert abs(current['imageScale']-2.05) < 1e-7
    assert bytes(zoomed.get_data()) != bytes(moved.get_data()), 'Image pixels did not zoom'
    zoomed.write_to_png(str(core.STATE/'zoomed-source-preview.png'))
    # Hit testing uses the same fixed rectangles after moving and zooming the image.
    bx, by, bw, bh = rectangles[-1]
    window.drag_begin(None, bx+bw/2, by+bh/2)
    assert window.selected == len(frames)-1
    window.fill()
    window.monitor_selector.set_selected(selected)
    window.canvas.queue_draw()
    print('PASS: native source visible; exterior dimmed; exported transforms unchanged')
    print('PASS: drag and wheel zoom move image pixels; monitor outlines and hit targets stay fixed')


def check_editing_tools(window):
    width, height = window.canvas.get_width(), window.canvas.get_height()
    def render():
        result = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        window.draw(window.canvas, cairo.Context(result), width, height)
        return result

    window.preview_slider.set_value(1)
    window.zoom_slider.set_value(1.75)
    window.view.update(panX=86, panY=-55)
    render()
    camera = (window.view_origin, window.view_scale)
    window.center_x_button.emit('clicked')
    assert window.view == dict(zoom=1.75, panX=0, panY=-55)
    frames, layout = window.composition()
    first = frames[0]
    assert first['imageX']+window.picture['width']*first['imageScale']/2 == layout['x']+layout['width']/2
    render()
    assert (window.view_origin, window.view_scale) == camera
    window.view['panX'] = 95
    window.center_y_button.emit('clicked')
    assert window.view == dict(zoom=1.75, panX=95, panY=0)
    frames, layout = window.composition()
    first = frames[0]
    assert first['imageY']+window.picture['height']*first['imageScale']/2 == layout['y']+layout['height']/2
    render()
    assert (window.view_origin, window.view_scale) == camera
    print('PASS: axis centering preserves image zoom, other axis and preview camera')

    window.zoom_slider.set_value(8)
    window.view.update(panX=4200, panY=-2300)
    view = dict(window.view)
    frames = window.composition()[0]
    coverage = window.covered()
    window.preview_slider.set_value(.25)
    render()
    assert abs(window.view_scale-camera[1]*.25) < 1e-9
    assert window.view == view and window.composition()[0] == frames
    window.overview_button.emit('clicked')
    overview = render()
    first = frames[0]
    ox, oy = window.view_origin
    scale = window.view_scale
    left, top = ox+first['imageX']*scale, oy+first['imageY']*scale
    assert left >= 34 and top >= 34, (left, top)
    assert left+window.picture['width']*first['imageScale']*scale <= width-34
    assert top+window.picture['height']*first['imageScale']*scale <= height-34
    assert window.view == view and window.composition()[0] == frames
    assert window.covered() == coverage
    overview.write_to_png(str(core.STATE/'overview-preview.png'))
    camera = (window.view_origin, window.view_scale)
    window.drag_begin(None, width/2, height/2)
    window.drag_update(None, 12, -6)
    render()
    assert (window.view_origin, window.view_scale) == camera
    moved = window.composition()[0][0]
    assert abs(ox+moved['imageX']*scale-left-12) < 1e-7
    assert abs(oy+moved['imageY']*scale-top+6) < 1e-7
    print('PASS: 800% image and offset fit overview; camera controls preserve all export transforms')
    window.fill()
    window.preview_slider.set_value(window.preferences['previewZoom'])
    render()


def activate(application):
    schema = Gio.SettingsSchemaSource.get_default().lookup('org.gnome.desktop.background', True)
    store = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
    desktop.write_values(store, {'picture-uri': 'file:///original-light.png',
                                'picture-uri-dark': 'file:///original-dark.png',
                                'picture-options': 'zoom'})
    with patch.object(desktop, 'settings', return_value=store):
        window = app.Window(application)
    core.STATE.mkdir(parents=True, exist_ok=True)
    source = core.STATE/'test-source.png'
    core.magick(['-size', '4000x3000', 'xc:#cc5522', str(source)])
    window.preview_slider.set_value(.43)
    window.loaded(core.inspect(source))
    window.present()
    apply_original = desktop.apply_wallpaper

    def next_stage():
        try:
            if not stages:
                # Final screenshot uses the real artwork, with the tested success banner.
                return GLib.timeout_add(220, final_capture) and GLib.SOURCE_REMOVE
            name, export_error, apply_error, changed = stages.pop(0)
            result = {'panorama': str(source), 'directory': str(core.STATE)}
            patches.append(patch.object(desktop, 'export', side_effect=OSError(export_error))
                           if export_error else patch.object(desktop, 'export', return_value=result))
            patches.append(patch.object(desktop, 'apply_wallpaper', side_effect=RuntimeError(apply_error))
                           if apply_error else patch.object(desktop, 'apply_wallpaper',
                               side_effect=lambda path, backend=None: apply_original(path, store)))
            if changed:
                patches.append(patch.object(core, 'monitors', return_value=[]))
            for item in patches:
                item.start()
            window.run_export(core.STATE, 'test', True)
            assert window.busy
            assert all(not control.get_sensitive() for control in
                       (window.center_x_button, window.center_y_button, window.overview_button, window.preview_slider))
            assert window.apply_button.get_child().get_last_child().get_text() == 'Uygulanıyor…'
            def complete():
                try:
                    if window.busy:
                        return GLib.SOURCE_CONTINUE
                    assert window.feedback.get_reveal_child()
                    failed = bool(export_error or apply_error or changed)
                    assert window.feedback_title.get_text() == ('Duvar kâğıdı uygulanamadı' if failed else
                                                               'Duvar kâğıdı başarıyla uygulandı')
                    assert window.feedback_box.has_css_class('wc-feedback-error' if failed else 'wc-feedback-success')
                    assert not window.feedback_box.has_css_class('wc-feedback-success' if failed else 'wc-feedback-error')
                    if failed:
                        expected = export_error or apply_error or 'Ekran düzeni değişti'
                        assert expected in window.feedback_detail.get_text()
                    else:
                        assert desktop.values(store)['picture-uri'] == source.as_uri()
                        assert desktop.values(store)['picture-options'] == 'spanned'
                    assert window.restore_button.get_sensitive() == (not failed)
                    assert window.apply_button.get_sensitive()
                    for item in patches:
                        item.stop()
                    patches.clear()
                    print('PASS:', name)
                    if name == 'apply failure':
                        GLib.timeout_add(220, error_capture)
                    else:
                        GLib.timeout_add(220, next_stage)
                    return GLib.SOURCE_REMOVE
                except Exception as error:
                    return finish(repr(error))
            GLib.timeout_add(30, complete)
            return GLib.SOURCE_REMOVE
        except Exception as error:
            return finish(repr(error))

    def error_capture():
        try:
            capture(window, 'feedback-error.png')
            window.feedback.set_reveal_child(False)
            assert not window.feedback.get_reveal_child()
            print('PASS: dismissible failure banner')
            return next_stage()
        except Exception as error:
            return finish(repr(error))

    def final_capture():
        try:
            capture(window, 'feedback-success.png')
            assert window.restore_button.get_sensitive()
            window.restore_button.emit('clicked')
            assert desktop.values(store)['picture-uri'] == 'file:///original-light.png'
            assert desktop.values(store)['picture-uri-dark'] == 'file:///original-dark.png'
            assert not window.restore_button.get_sensitive()
            print('PASS: restore enabled only after successful app apply; one-time restore preserves both modes')
            return finish()
        except Exception as error:
            return finish(repr(error))

    def initial():
        try:
            check_preview(window)
            check_editing_tools(window)
            original_width = window.canvas.get_width()
            original_view = dict(window.view)
            assert not window.restore_button.get_sensitive()
            window.settings_button.emit('clicked')
            assert window.preferences_window.get_visible()
            assert window.preferences_window.get_modal()
            assert window.sidebar_scroll.get_visible(), 'Settings button toggled the editing panel'
            assert window.view == original_view
            assert window.get_icon_name() == app.APP_ICON
            assert Gtk.IconTheme.get_for_display(window.get_display()).has_icon(app.APP_ICON)
            assert isinstance(window.preferences_save_button.get_child(), Gtk.Label)
            control = window.default_preview_spin
            assert control.get_first_child() == control.minus
            assert control.minus.get_next_sibling() == control.entry
            assert control.entry.get_next_sibling() == control.plus
            assert control.entry.get_text() == '70%'
            control.minus.emit('clicked')
            assert control.entry.get_text() == '69%'
            control.plus.emit('clicked')
            assert control.entry.get_text() == '70%'
            control.set_value(1)
            assert not control.minus.get_sensitive()
            control.entry.set_text('42%')
            assert control.minus.get_sensitive()
            control.minus.emit('clicked')
            assert control.entry.get_text() == '41%'
            control.set_value(100)
            assert not control.plus.get_sensitive()
            stored = core.load_preferences()
            control.entry.set_text('0%')
            window.preferences_save_button.emit('clicked')
            assert window.preferences_error.get_visible()
            assert core.load_preferences() == stored
            assert window.view == original_view
            print('PASS: supplied app icon; text-only Save; minus/percentage/plus control with safe input bounds')
            window.language_selector.set_selected(1)
            window.default_preview_spin.set_value(55)
            window.show_controls_switch.set_active(False)
            window.preferences_save_button.emit('clicked')
            assert not window.preferences_window.get_visible()
            assert core.load_preferences()['language'] == 'en'
            assert core.load_preferences()['previewZoom'] == .55
            assert window.preview_label.get_text() == '55%'
            assert window.open_button.get_child().get_last_child().get_text() == 'Open image'
            assert window.center_x_button.get_child().get_last_child().get_text() == 'Center horizontally'
            assert window.hint.get_text().startswith('Drag the image')
            assert window.view == original_view
            assert not window.sidebar_scroll.get_visible()
            def check_expanded():
                try:
                    assert window.canvas.get_width() > original_width+200
                    assert window.view == original_view
                    capture(window, 'expanded-preview.png')
                    window.settings_button.emit('clicked')
                    assert window.preferences_window.get_title() == 'Settings'
                    assert window.preferences_window.get_visible()
                    window.sidebar_scroll.set_visible(True)
                    def english_capture():
                        try:
                            capture(window, 'main-english.png')
                            capture(window.preferences_window, 'settings-english.png')
                            window.show_feedback('Duvar kâğıdı uygulanamadı',
                                                 'GNOME duvar kâğıdı ayarlarına yazma izni yok.', error=True)
                            assert window.feedback_title.get_text() == 'Could not apply wallpaper'
                            assert window.feedback_detail.get_text() == 'GNOME wallpaper settings are not writable.'
                            stored = core.load_preferences()
                            window.language_selector.set_selected(0)
                            window.default_preview_spin.set_value(90)
                            window.preferences_window.close()
                            assert core.load_preferences() == stored
                            window.settings_button.emit('clicked')
                            assert window.language_selector.get_selected() == 1
                            assert abs(window.default_preview_spin.get_value()-55) < 1e-7
                            window.language_selector.set_selected(0)
                            window.default_preview_spin.set_value(70)
                            window.show_controls_switch.set_active(True)
                            # Saving failures keep the previous preferences and image untouched.
                            with patch.object(core, 'save_preferences', side_effect=OSError('cannot save')):
                                window.preferences_save_button.emit('clicked')
                            assert window.preferences_error.get_visible()
                            assert window.preferences['language'] == 'en'
                            assert window.view == original_view
                            window.preferences_save_button.emit('clicked')
                            assert core.load_preferences()['language'] == 'tr'
                            assert window.open_button.get_child().get_last_child().get_text() == 'Görsel aç'
                            assert window.preview_label.get_text() == '%70'
                            assert window.sidebar_scroll.get_visible()
                            assert window.view == original_view
                            assert window.feedback_title.get_text() == 'Duvar kâğıdı uygulanamadı'
                            assert window.feedback_detail.get_text() == 'GNOME duvar kâğıdı ayarlarına yazma izni yok.'
                            window.settings_button.emit('clicked')
                            def turkish_capture():
                                try:
                                    capture(window.preferences_window, 'settings-turkish.png')
                                    window.preferences_window.close()
                                    GLib.timeout_add(150, next_stage)
                                    return GLib.SOURCE_REMOVE
                                except Exception as error:
                                    return finish(repr(error))
                            GLib.timeout_add(150, turkish_capture)
                            print('PASS: live Turkish/English UI and errors; preferences persist; cancel/save failure preserve state')
                            return GLib.SOURCE_REMOVE
                        except Exception as error:
                            return finish(repr(error))
                    GLib.timeout_add(150, english_capture)
                    print('PASS: hiding settings expands canvas without changing image transform')
                    return GLib.SOURCE_REMOVE
                except Exception as error:
                    return finish(repr(error))
            GLib.timeout_add(150, check_expanded)
            return GLib.SOURCE_REMOVE
        except Exception as error:
            return finish(repr(error))
    GLib.timeout_add(500, initial)


application.connect('activate', activate)
GLib.timeout_add_seconds(20, lambda: finish('GTK check timed out'))
application.run([sys.argv[0]])
sys.exit(exit_code)
