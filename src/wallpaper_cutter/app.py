#!/usr/bin/env python3
"""Wallpaper Cutter — cross-platform GTK desktop editor."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import sys
import os
if sys.platform == 'win32':
    os.environ.setdefault('PYGI_DLL_PATH', str(Path(sys.executable).parent))
    _gtk_dll_directory = os.add_dll_directory(str(Path(sys.executable).parent))
import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib
from . import core
from . import desktop
from . import platform_runtime
from . import file_picker
from .i18n import Translator

LOG = logging.getLogger('wallpaper-cutter')
APP_ICON = 'io.github.local.WallpaperCutter'


class PercentControl(Gtk.Box):
    """A bounded percentage entry with one step button on each side."""
    def __init__(self, translator):
        super().__init__(spacing=0, css_classes=['linked', 'wc-percent-control'])
        self.value = 70
        self.minus = Gtk.Button(label='−')
        self.plus = Gtk.Button(label='+')
        translator.bind(self.minus, 'tooltip_text', 'Önizleme ölçeğini azalt')
        translator.bind(self.plus, 'tooltip_text', 'Önizleme ölçeğini artır')
        self.entry = Gtk.Entry(text='70%', width_chars=4, max_width_chars=4,
                               input_purpose=Gtk.InputPurpose.DIGITS)
        self.entry.set_alignment(.5)
        translator.bind(self.entry, 'tooltip_text', 'Başlangıç önizleme ölçeği')
        self.append(self.minus)
        self.append(self.entry)
        self.append(self.plus)
        self.minus.connect('clicked', lambda *_: self.step(-1))
        self.plus.connect('clicked', lambda *_: self.step(1))
        self.entry.connect('activate', lambda *_: self.normalize())
        self.entry.connect('changed', self.input_changed)
        focus = Gtk.EventControllerFocus()
        focus.connect('leave', lambda *_: self.normalize())
        self.entry.add_controller(focus)

    def set_value(self, value):
        self.value = max(1, min(100, round(value)))
        self.entry.set_text(f'{self.value}%')
        self.entry.remove_css_class('error')
        self.minus.set_sensitive(self.value > 1)
        self.plus.set_sensitive(self.value < 100)

    def get_value(self):
        try:
            value = int(self.entry.get_text().strip().removesuffix('%').strip())
            if not 1 <= value <= 100:
                raise ValueError
        except ValueError:
            self.entry.add_css_class('error')
            raise ValueError('Önizleme ölçeği 1 ile 100 arasında bir tam sayı olmalı.') from None
        return value

    def normalize(self):
        try:
            self.set_value(self.get_value())
        except ValueError:
            pass

    def input_changed(self, *_):
        try:
            self.value = self.get_value()
        except ValueError:
            self.minus.set_sensitive(True)
            self.plus.set_sensitive(True)
            return
        self.entry.remove_css_class('error')
        self.minus.set_sensitive(self.value > 1)
        self.plus.set_sensitive(self.value < 100)

    def step(self, delta):
        try:
            value = self.get_value()
        except ValueError:
            value = self.value
        self.set_value(value+delta)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app, initial_image=None, smoke=False):
        super().__init__(application=app, title='Wallpaper Cutter')
        Gtk.IconTheme.get_for_display(self.get_display()).add_search_path(str(Path(__file__).parent/'assets'))
        self.set_icon_name(APP_ICON)
        self.set_default_size(1320, 840)
        self.set_size_request(940, 620)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.monitors = []
        self.picture = None
        self.pixbuf = None
        self.view = dict(zoom=1, panX=0, panY=0)
        self.preferences = core.load_preferences()
        self.translator = Translator(self.preferences['language'])
        self.preview_zoom = self.preferences['previewZoom']
        self.preferences_window = None
        self.background_store = desktop.settings()
        self.stop_background_watch = desktop.watch_changes(self.background_store, self.update_restore_button)
        self.busy = False
        self.applying = False
        self.updating = True
        self.saved = core.load_settings()
        self.adjustments = self.saved['adjustments']
        self.gap = self.saved['gap']
        self.selected = 0
        self.view_scale = 1
        self.smoke = smoke
        style = Gtk.CssProvider()
        style.load_from_data(b"""
            .wc-root { background: @theme_bg_color; }
            .wc-card { background: alpha(@theme_fg_color, 0.035); border: 1px solid alpha(@theme_fg_color, 0.10); border-radius: 16px; padding: 18px; }
            .wc-canvas { border: 1px solid alpha(@theme_fg_color, 0.12); border-radius: 16px; }
            .wc-preview-tools { background: alpha(#202328, 0.94); color: #e8eaed; border: 1px solid alpha(#ffffff, 0.12); border-radius: 12px; padding: 8px 4px; }
            .wc-preview-tools label { font-size: 11px; }
            .wc-preview-tools button { color: #e8eaed; padding: 5px; min-width: 22px; min-height: 22px; }
            .wc-section-title { font-weight: bold; font-size: 15px; }
            .wc-number { font-weight: bold; font-feature-settings: "tnum"; }
            .wc-status { font-size: 12px; }
            .wc-feedback { border-radius: 12px; padding: 14px; border: 1px solid alpha(@theme_fg_color, 0.12); }
            .wc-feedback-success { background: alpha(#2ec27e, 0.13); border-color: alpha(#2ec27e, 0.45); }
            .wc-feedback-error { background: alpha(#e01b24, 0.10); border-color: alpha(#e01b24, 0.4); }
            .wc-toolbar button { padding: 8px 14px; }
            .wc-center-vertical image { transform: rotate(90deg); }
            .wc-percent-control entry { padding-left: 4px; padding-right: 4px; }
        """)
        Gtk.StyleContext.add_provider_for_display(self.get_display(), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.header = Gtk.HeaderBar()
        title = Gtk.Box(spacing=8)
        title.append(Gtk.Image(icon_name=APP_ICON, pixel_size=24))
        title.append(Gtk.Label(label='Wallpaper Cutter', css_classes=['title']))
        self.header.set_title_widget(title)
        self.set_titlebar(self.header)
        self.open_button = self.button('Görsel aç', self.open_image, 'document-open-symbolic')
        self.header.pack_start(self.open_button)
        self.import_button = self.button('İçe aktar', self.import_cut, 'document-open-symbolic')
        self.header.pack_start(self.import_button)
        self.refresh_button = self.button('Ekranları yenile', self.refresh, 'view-refresh-symbolic')
        self.header.pack_end(self.refresh_button)
        self.settings_button = self.button('Ayarlar', self.open_preferences, 'preferences-system-symbolic')
        self.header.pack_end(self.settings_button)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, css_classes=['wc-root'])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, 'set_margin_'+side)(20)
        self.set_child(root)
        self.feedback = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                     transition_duration=150)
        self.feedback_box = Gtk.Box(spacing=12, css_classes=['wc-feedback'])
        self.feedback_icon = Gtk.Image(icon_name='object-select-symbolic', pixel_size=24)
        self.feedback_box.append(self.feedback_icon)
        feedback_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        self.feedback_title = self.label(xalign=0, wrap=True, css_classes=['wc-section-title'])
        self.feedback_detail = self.label(xalign=0, wrap=True)
        feedback_text.append(self.feedback_title)
        feedback_text.append(self.feedback_detail)
        self.feedback_box.append(feedback_text)
        dismiss = Gtk.Button(icon_name='window-close-symbolic', valign=Gtk.Align.START,
                             css_classes=['flat'], tooltip_text='Bildirimi kapat')
        dismiss.connect('clicked', lambda *_: self.feedback.set_reveal_child(False))
        self.translator.bind(dismiss, 'tooltip_text', 'Bildirimi kapat')
        self.feedback_box.append(dismiss)
        self.feedback.set_child(self.feedback_box)
        root.append(self.feedback)
        body = Gtk.Box(spacing=20, vexpand=True)
        root.append(body)
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, hexpand=True)
        body.append(preview)
        heading = Gtk.Box(spacing=12)
        heading.append(self.icon_label('Önizleme', 'view-grid-symbolic', css_classes=['wc-section-title']))
        self.summary = self.label(xalign=1, hexpand=True, css_classes=['dim-label'])
        heading.append(self.summary)
        preview.append(heading)
        self.canvas = Gtk.DrawingArea(hexpand=True, vexpand=True, focusable=True, css_classes=['wc-canvas'])
        self.canvas.set_content_height(330)
        self.canvas.set_draw_func(self.draw)
        self.preview_overlay = Gtk.Overlay(hexpand=True, vexpand=True)
        self.preview_overlay.set_child(self.canvas)
        preview.append(self.preview_overlay)
        self.preview_tools = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                                     halign=Gtk.Align.END, valign=Gtk.Align.START,
                                     margin_top=12, margin_end=12, css_classes=['wc-preview-tools'])
        self.preview_label = Gtk.Label(label=self.percent(self.preview_zoom), width_chars=4, xalign=.5,
                                       css_classes=['wc-number'], tooltip_text='Önizleme ölçeği')
        self.translator.bind(self.preview_label, 'tooltip_text', 'Önizleme ölçeği')
        self.preview_tools.append(self.preview_label)
        self.preview_slider = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, .01, 1, .01)
        self.preview_slider.set_value(self.preview_zoom)
        self.preview_slider.set_draw_value(False)
        self.preview_slider.set_inverted(True)
        self.preview_slider.set_size_request(-1, 130)
        self.translator.bind(self.preview_slider, 'tooltip_text', 'Yalnızca çalışma alanının görünümünü değiştirir; görsel zoom’u ve kesimler korunur')
        self.preview_slider.connect('value-changed', self.preview_zoom_changed)
        self.preview_tools.append(self.preview_slider)
        self.overview_button = Gtk.Button(icon_name='zoom-fit-best-symbolic',
                                         tooltip_text='Görselin tamamını göster', css_classes=['flat'])
        self.overview_button.connect('clicked', self.fit_preview)
        self.translator.bind(self.overview_button, 'tooltip_text', 'Görselin tamamını göster')
        self.overview_button.update_property([Gtk.AccessibleProperty.LABEL], ['Görselin tamamını göster'])
        self.preview_tools.append(self.overview_button)
        self.preview_overlay.add_overlay(self.preview_tools)
        self.hint = self.label(label='Görseli sürükle · Tekerlekle yakınlaştır · Ok tuşlarıyla ince ayar',
                              xalign=0, wrap=True, css_classes=['dim-label'])
        preview.append(self.hint)
        self.image_info = self.label(label='Başlamak için bir görsel aç.', xalign=0,
                                    ellipsize=3, css_classes=['dim-label'])
        preview.append(self.image_info)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, width_request=300)
        sidebar.set_hexpand(False)
        self.sidebar_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                                vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                                min_content_width=300)
        self.sidebar_scroll.set_child(sidebar)
        body.append(self.sidebar_scroll)
        self.sidebar_scroll.set_visible(self.preferences['showControls'])
        self.controls = sidebar
        image_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=['wc-card'])
        image_card.append(self.icon_label('Görsel', 'image-x-generic-symbolic', css_classes=['wc-section-title']))
        image_card.append(self.label(label='%100 = orijinal boyut (1:1)', xalign=0, css_classes=['dim-label']))
        zoom_row = Gtk.Box(spacing=12)
        zoom_row.append(self.icon_label('Yakınlaştırma', 'zoom-in-symbolic', hexpand=True))
        self.zoom_label = Gtk.Label(label=self.percent(1), width_chars=6, xalign=1, css_classes=['wc-number'])
        zoom_row.append(self.zoom_label)
        image_card.append(zoom_row)
        self.zoom_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, .01, 8, .01)
        self.zoom_slider.set_value(1)
        self.zoom_slider.set_draw_value(False)
        self.zoom_slider.set_hexpand(True)
        self.zoom_slider.connect('value-changed', self.zoom_changed)
        image_card.append(self.zoom_slider)
        center_row = Gtk.Box(spacing=8, homogeneous=True)
        self.center_x_button = self.button('Yatay ortala', lambda *_: self.center_image('x'), 'format-justify-center-symbolic')
        self.center_y_button = self.button('Dikey ortala', lambda *_: self.center_image('y'), 'format-justify-center-symbolic')
        self.center_y_button.add_css_class('wc-center-vertical')
        for button in (self.center_x_button, self.center_y_button):
            self.translator.bind(button, 'tooltip_text', 'Görseli mevcut zoom ile tüm ekran düzenine göre ortalar; diğer eksen korunur')
            center_row.append(button)
        image_card.append(center_row)
        self.fill_button = self.button('Orijinal boyutta ortala', self.fill, 'zoom-fit-best-symbolic')
        image_card.append(self.fill_button)
        sidebar.append(image_card)

        screen_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=['wc-card'])
        screen_card.append(self.icon_label('Ekran hizalama', 'preferences-desktop-display-symbolic', css_classes=['wc-section-title']))
        self.monitor_selector = Gtk.DropDown(hexpand=True)
        self.monitor_selector.connect('notify::selected', self.selected_changed)
        screen_card.append(self.monitor_selector)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.offset_x = Gtk.SpinButton.new_with_range(-5000, 5000, 1)
        self.offset_y = Gtk.SpinButton.new_with_range(-5000, 5000, 1)
        for index, (label, spin) in enumerate([('Yatay', self.offset_x), ('Dikey', self.offset_y)]):
            grid.attach(self.icon_label(label, 'pan-end-symbolic' if index == 0 else 'pan-down-symbolic', hexpand=True), 0, index, 1, 1)
            spin.set_width_chars(6)
            spin.connect('value-changed', self.adjusted)
            grid.attach(spin, 1, index, 1, 1)
        screen_card.append(grid)
        screen_card.append(self.button('Seçili ekranın hizasını sıfırla', self.reset, 'edit-undo-symbolic'))
        screen_card.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        gap_row = Gtk.Box(spacing=12)
        gap_row.append(self.icon_label('Çerçeve boşluğu', 'view-dual-symbolic', hexpand=True))
        self.gap_spin = Gtk.SpinButton.new_with_range(0, 500, 1)
        self.gap_spin.set_width_chars(4)
        self.gap_spin.set_value(self.gap)
        self.gap_spin.connect('value-changed', self.adjusted)
        gap_row.append(self.gap_spin)
        screen_card.append(gap_row)
        screen_card.append(self.label(label='Hiza seçili ekrana, boşluk tüm düzene\nuygulanır. Değerler piksel cinsindedir.',
                                     xalign=0, wrap=True, max_width_chars=32, css_classes=['dim-label', 'wc-status']))
        sidebar.append(screen_card)

        root.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        footer = Gtk.Box(spacing=12, css_classes=['wc-toolbar'])
        self.restore_button = self.button('Önceki duvar kâğıdına dön', self.restore, 'edit-undo-symbolic')
        footer.append(self.restore_button)
        footer.append(Gtk.Box(hexpand=True))
        self.export_button = self.button('Dışa aktar', lambda *_: self.export(False), 'document-save-symbolic')
        footer.append(self.export_button)
        self.apply_button = self.button('Duvar kâğıdı yap', lambda *_: self.export(True),
                                        'preferences-desktop-wallpaper-symbolic')
        self.apply_button.add_css_class('suggested-action')
        footer.append(self.apply_button)
        root.append(footer)
        self.status = self.label(label='Bir görsel seçerek başla.', xalign=0, wrap=True,
                                css_classes=['wc-status', 'dim-label'])
        root.append(self.status)
        self.updating = False

        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self.drag_begin)
        drag.connect('drag-update', self.drag_update)
        self.canvas.add_controller(drag)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', self.scroll)
        self.canvas.add_controller(scroll)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.key)
        self.canvas.add_controller(keys)
        action = Gio.SimpleAction.new('open', None)
        action.connect('activate', self.open_image)
        app.add_action(action)
        app.set_accels_for_action('app.open', ['<Control>o'])
        self.connect('close-request', self.closing)
        self.refresh()
        if initial_image:
            self.submit(lambda: core.inspect(initial_image), self.loaded)
        else:
            session = core.STATE/'session.json'
            if session.exists():
                try:
                    saved = json.loads(session.read_text(encoding='utf-8'))
                    if Path(saved['image']['path']).is_file():
                        self.submit(lambda: core.inspect(saved['image']['path']),
                                    lambda image: self.loaded(image, saved))
                except (ValueError, KeyError, OSError):
                    self.message('Önceki görsel bulunamadı. Yeni bir görsel açabilirsin.')

    def label(self, label='', **kwargs):
        widget = Gtk.Label(**kwargs)
        return self.translator.bind(widget, 'text', label)

    def icon_label(self, label, icon, **kwargs):
        box = Gtk.Box(spacing=8, hexpand=kwargs.pop('hexpand', False))
        box.append(Gtk.Image(icon_name=icon, pixel_size=16))
        box.append(self.label(label=label, xalign=0, **kwargs))
        return box

    def percent(self, value):
        return self.translator.text('%{percent}', percent=round(value*100))

    def button(self, label, callback, icon=None):
        button = Gtk.Button()
        if icon:
            content = Gtk.Box(spacing=6)
            content.append(Gtk.Image.new_from_icon_name(icon))
            content.append(self.label(label=label))
            button.set_child(content)
        else:
            self.translator.bind(button, 'label', label)
        button.connect('clicked', callback)
        return button

    def message(self, message, error=False, **parameters):
        self.translator.bind(self.status, 'text', message, **parameters)
        if error:
            self.status.add_css_class('error')
        else:
            self.status.remove_css_class('error')

    def open_preferences(self, *_):
        if self.busy:
            return
        if self.preferences_window is None:
            dialog = Gtk.Window(transient_for=self, modal=True, resizable=False, default_width=480)
            dialog.set_icon_name(APP_ICON)
            self.translator.bind(dialog, 'title', 'Ayarlar')
            header = Gtk.HeaderBar()
            header.set_title_widget(self.icon_label('Ayarlar', 'preferences-system-symbolic',
                                                     css_classes=['title']))
            dialog.set_titlebar(header)
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
            for side in ('top', 'bottom', 'start', 'end'):
                getattr(root, 'set_margin_'+side)(24)
            dialog.set_child(root)
            language_row = Gtk.Box(spacing=16)
            language_row.append(self.icon_label('Dil', 'preferences-desktop-locale-symbolic', hexpand=True))
            self.language_selector = Gtk.DropDown.new_from_strings(['Türkçe', 'English'])
            language_row.append(self.language_selector)
            root.append(language_row)
            preview_row = Gtk.Box(spacing=16)
            preview_row.append(self.icon_label('Başlangıç önizleme ölçeği', 'zoom-out-symbolic', hexpand=True))
            self.default_preview_spin = PercentControl(self.translator)
            preview_row.append(self.default_preview_spin)
            root.append(preview_row)
            root.append(self.label(label='Önizleme görünümünü değiştirir; görselin zoom’u ve kesimler korunur.',
                                   wrap=True, xalign=0, max_width_chars=45, css_classes=['dim-label']))
            panel_row = Gtk.Box(spacing=16)
            panel_row.append(self.icon_label('Düzenleme panelini göster', 'view-dual-symbolic', hexpand=True))
            self.show_controls_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            panel_row.append(self.show_controls_switch)
            root.append(panel_row)
            root.append(self.label(label='Görsel ve ekran hizalama kontrollerini gösterir.',
                                   wrap=True, xalign=0, css_classes=['dim-label']))
            root.append(Gtk.Separator())
            root.append(self.label(label='Değişiklikler kaydedildiğinde hemen uygulanır.',
                                   wrap=True, xalign=0, css_classes=['dim-label']))
            self.preferences_error = self.label(wrap=True, xalign=0, max_width_chars=45,
                                                css_classes=['error'], visible=False)
            root.append(self.preferences_error)
            actions = Gtk.Box(spacing=12, halign=Gtk.Align.END)
            actions.append(self.button('İptal', lambda *_: dialog.hide()))
            self.preferences_save_button = self.button('Kaydet', self.save_preferences)
            self.preferences_save_button.add_css_class('suggested-action')
            actions.append(self.preferences_save_button)
            root.append(actions)
            dialog.connect('close-request', lambda *_: (dialog.hide(), True)[1])
            self.preferences_window = dialog
        self.language_selector.set_selected(0 if self.preferences['language'] == 'tr' else 1)
        self.default_preview_spin.set_value(self.preferences['previewZoom']*100)
        self.show_controls_switch.set_active(self.preferences['showControls'])
        self.preferences_error.set_visible(False)
        self.preferences_window.present()

    def save_preferences(self, *_):
        try:
            desired = dict(language='tr' if self.language_selector.get_selected() == 0 else 'en',
                           previewZoom=self.default_preview_spin.get_value()/100,
                           showControls=self.show_controls_switch.get_active())
            saved = core.save_preferences(desired)
        except Exception as error:
            self.translator.bind(self.preferences_error, 'text', str(error))
            self.preferences_error.set_visible(True)
            return
        self.preferences = saved
        self.translator.set_language(saved['language'])
        self.zoom_label.set_text(self.percent(self.view['zoom']))
        self.preview_slider.set_value(saved['previewZoom'])
        self.preview_label.set_text(self.percent(self.preview_zoom))
        self.overview_button.update_property([Gtk.AccessibleProperty.LABEL],
                                            [self.translator.text('Görselin tamamını göster')])
        self.sidebar_scroll.set_visible(saved['showControls'])
        self.update_buttons()
        self.message('Ayarlar kaydedildi.')
        self.preferences_window.hide()
        self.canvas.queue_draw()

    def show_feedback(self, title, detail='', error=False, **parameters):
        self.translator.bind(self.feedback_title, 'text', title)
        self.translator.bind(self.feedback_detail, 'text', detail, **parameters)
        self.feedback_detail.set_visible(bool(detail))
        self.feedback_icon.set_from_icon_name('dialog-error-symbolic' if error else 'object-select-symbolic')
        self.feedback_box.remove_css_class('wc-feedback-success')
        self.feedback_box.remove_css_class('wc-feedback-error')
        self.feedback_box.add_css_class('wc-feedback-error' if error else 'wc-feedback-success')
        self.feedback.set_reveal_child(True)

    def submit(self, work, done, failure_title=None):
        if self.busy:
            return
        self.busy = True
        self.message('İşleniyor…')
        self.update_buttons()
        def worker():
            try:
                result = work()
                GLib.idle_add(complete, result, None)
            except Exception as error:
                LOG.exception('İşlem başarısız')
                GLib.idle_add(complete, None, str(error))
        def complete(result, error):
            self.busy = False
            if error:
                self.message(error, True)
                if failure_title:
                    self.show_feedback(failure_title, error, error=True)
            else:
                try:
                    done(result)
                except Exception as failure:
                    LOG.exception('İşlem sonucu yüklenemedi')
                    self.message(str(failure), True)
                    if failure_title:
                        self.show_feedback(failure_title, str(failure), error=True)
            self.applying = False
            self.update_buttons()
            return GLib.SOURCE_REMOVE
        self.pool.submit(worker)

    def refresh(self, *_):
        try:
            self.monitors = core.monitors()
            self.monitor_selector.set_model(Gtk.StringList.new([
                f"{m['name']} · {m['pixelWidth']} × {m['pixelHeight']}" for m in self.monitors]))
            self.monitor_selector.set_selected(0)
            self.translator.bind(self.summary, 'text', '{count} ekran · {names}',
                                 count=len(self.monitors), names='  ·  '.join(m['name'] for m in self.monitors))
            LOG.info('Ekranlar algılandı: %s', ', '.join(m['name'] for m in self.monitors))
            self.selected_changed()
            self.canvas.queue_draw()
        except Exception as error:
            self.monitors = []
            self.translator.bind(self.summary, 'text', 'Ekran düzeni alınamadı')
            self.message(str(error), True)
            LOG.exception('Ekran algılama başarısız')
        self.update_buttons()

    def open_image(self, *_):
        if self.busy:
            return
        dialog = file_picker.create(title=self.translator.text('Duvar kâğıdı görseli seç'))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        image_filter = Gtk.FileFilter(name=self.translator.text('Görseller'))
        for mime in ('image/png', 'image/jpeg', 'image/webp', 'image/bmp', 'image/tiff'):
            image_filter.add_mime_type(mime)
        filters.append(image_filter)
        dialog.set_filters(filters)
        def response(dialog, result):
            try:
                path = dialog.open_finish(result).get_path()
                if path:
                    self.submit(lambda: core.inspect(path), self.loaded)
            except GLib.Error:
                pass
        dialog.open(self, None, response)

    def loaded(self, image, composition=None, preserve_legacy=False):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(platform_runtime.file_uri_path(image['preview']))
        self.picture, self.pixbuf = image, pixbuf
        self.view = desktop.restored_view(composition or {}, self.monitors, image,
                                          self.gap, self.adjustments, preserve_legacy)
        self.preview_slider.set_value(self.preferences['previewZoom'])
        self.zoom_slider.set_value(self.view['zoom'])
        self.selected_changed()
        self.translator.bind(self.image_info, 'text', '{name} · {width} × {height}',
                             name=image['name'], width=image['width'], height=image['height'])
        self.image_info.set_tooltip_text(image['path'])
        self.message('Önceki ekran bazlı kesim orijinal boyutta ortalandı. Zoom ve konumu yeniden ayarlayabilirsin.'
                     if composition and composition.get('views') is not None else 'Görsel hazır. Kadrajı ayarlayıp uygula.')
        self.canvas.queue_draw()
        LOG.info('Görsel yüklendi: %dx%d', image['width'], image['height'])
        if self.smoke:
            GLib.timeout_add(800, self.smoke_check)

    def composition(self):
        if not self.picture:
            frames = desktop.frames(self.monitors, self.gap, self.adjustments)
            return frames, desktop.bounds(frames)
        return desktop.composition(self.monitors, self.picture, self.gap, self.adjustments, self.view)

    def covered(self):
        if not self.picture or not self.monitors:
            return False
        frames, _ = self.composition()
        return all(m['x'] >= m['imageX']-.001 and m['y'] >= m['imageY']-.001 and
                   m['x']+m['width'] <= m['imageX']+self.picture['width']*m['imageScale']+.001 and
                   m['y']+m['height'] <= m['imageY']+self.picture['height']*m['imageScale']+.001
                   for m in frames)

    def update_buttons(self):
        valid = self.covered() and not self.busy
        self.export_button.set_sensitive(valid)
        self.apply_button.set_sensitive(valid and desktop.supports_apply(self.background_store))
        reason = getattr(self.background_store, 'reason', '')
        self.translator.bind(self.apply_button, 'tooltip_text', reason)
        self.translator.bind(self.apply_button.get_child().get_last_child(), 'text',
                             'Uygulanıyor…' if self.busy and self.applying else 'Duvar kâğıdı yap')
        self.open_button.set_sensitive(not self.busy)
        self.refresh_button.set_sensitive(not self.busy)
        self.import_button.set_sensitive(not self.busy)
        self.settings_button.set_sensitive(not self.busy)
        self.controls.set_sensitive(not self.busy)
        self.zoom_slider.set_sensitive(not self.busy and self.picture is not None)
        self.fill_button.set_sensitive(not self.busy and self.picture is not None)
        for button in (self.center_x_button, self.center_y_button, self.overview_button, self.preview_slider):
            button.set_sensitive(not self.busy and self.picture is not None and bool(self.monitors))
        self.update_restore_button()
        self.translator.bind(self.hint, 'text', 'Görseli sürükle · Tekerlekle yakınlaştır · Ok tuşlarıyla ince ayar'
                           if not self.picture or self.covered() else
                           'Görsel tüm ekranları kaplamıyor. Yakınlaştır veya daha büyük bir görsel seç.')

    def update_restore_button(self):
        if hasattr(self, 'restore_button'):
            self.restore_button.set_sensitive(not self.busy and desktop.can_restore(self.background_store))

    def draw(self, _, context, width, height):
        frames, _ = self.composition()
        area = desktop.preview_bounds(frames, self.picture)
        context.save()
        context.set_source_rgb(.075, .085, .10)
        radius = 16
        context.new_sub_path()
        from math import pi
        for cx, cy, start in [(width-radius, radius, -pi/2), (width-radius, height-radius, 0),
                              (radius, height-radius, pi/2), (radius, radius, pi)]:
            context.arc(cx, cy, radius, start, start+pi/2)
        context.close_path()
        context.clip_preserve()
        context.fill()
        self.view_scale = max(1e-12, min((width-70)/area['width'], (height-70)/area['height']))*self.preview_zoom
        ox = (width-area['width']*self.view_scale)/2-area['x']*self.view_scale
        oy = (height-area['height']*self.view_scale)/2-area['y']*self.view_scale
        self.view_origin = (ox, oy)
        if self.pixbuf and frames:
            first = frames[0]
            context.save()
            context.translate(ox+first['imageX']*self.view_scale, oy+first['imageY']*self.view_scale)
            factor = first['imageScale']*self.view_scale*self.picture['width']/self.pixbuf.get_width()
            context.scale(factor, factor)
            Gdk.cairo_set_source_pixbuf(context, self.pixbuf, 0, 0)
            context.paint_with_alpha(.38)
            context.restore()
        for index, monitor in enumerate(frames):
            x, y = ox+monitor['x']*self.view_scale, oy+monitor['y']*self.view_scale
            w, h = monitor['width']*self.view_scale, monitor['height']*self.view_scale
            context.save()
            context.rectangle(x, y, w, h)
            context.clip()
            context.set_source_rgb(.13, .15, .18)
            context.paint()
            if self.pixbuf:
                context.translate(ox+monitor['imageX']*self.view_scale, oy+monitor['imageY']*self.view_scale)
                factor = monitor['imageScale']*self.view_scale*self.picture['width']/self.pixbuf.get_width()
                context.scale(factor, factor)
                Gdk.cairo_set_source_pixbuf(context, self.pixbuf, 0, 0)
                context.paint()
            context.restore()
            context.set_source_rgb(*((.28, .76, .95) if index == self.selected else (.43, .47, .52)))
            context.set_line_width(3 if index == self.selected else 1.5)
            context.rectangle(x, y, w, h)
            context.stroke()
            context.set_source_rgb(.94, .96, .98)
            context.select_font_face('Sans')
            context.set_font_size(12)
            label = f"{monitor['name']} · {monitor['pixelWidth']}×{monitor['pixelHeight']}"
            if context.text_extents(label).width > w-16:
                label = monitor['name']
            if context.text_extents(label).width > w-16:
                label = str(index+1)
            if context.text_extents(label).width <= w-16:
                context.move_to(x+8, y+h+21)
                context.show_text(label)
        if not frames:
            context.set_source_rgb(.7, .75, .8)
            context.set_font_size(18)
            context.move_to(30, height/2)
            context.show_text(self.translator.text('Ekranlar algılanamadı'))
        context.restore()

    def drag_begin(self, _, x, y):
        self.canvas.grab_focus()
        if hasattr(self, 'view_origin'):
            ox, oy = self.view_origin
            for i, monitor in enumerate(self.composition()[0]):
                if monitor['x'] <= (x-ox)/self.view_scale <= monitor['x']+monitor['width'] and \
                   monitor['y'] <= (y-oy)/self.view_scale <= monitor['y']+monitor['height']:
                    self.monitor_selector.set_selected(i)
                    break
        self.drag_origin = (self.view['panX'], self.view['panY'])
        self.drag_scale = self.view_scale

    def drag_update(self, _, x, y):
        if self.picture and not self.busy:
            self.view['panX'] = self.drag_origin[0]+x/self.drag_scale
            self.view['panY'] = self.drag_origin[1]+y/self.drag_scale
            self.canvas.queue_draw()
            self.update_buttons()

    def scroll(self, _, dx, dy):
        if not self.busy and self.picture:
            self.zoom_slider.set_value(max(.01, min(8, self.view['zoom']-dy*.05)))
        return True

    def zoom_changed(self, slider):
        value = slider.get_value()
        if not self.updating:
            self.view['zoom'] = value
        self.zoom_label.set_text(self.percent(value))
        self.canvas.queue_draw()
        if not self.updating:
            self.update_buttons()

    def key(self, _, key, code, modifiers):
        if self.busy or not self.picture:
            return False
        step = 10 if modifiers & Gdk.ModifierType.SHIFT_MASK else 1
        view = self.view
        if key == Gdk.KEY_Left: view['panX'] -= step
        elif key == Gdk.KEY_Right: view['panX'] += step
        elif key == Gdk.KEY_Up: view['panY'] -= step
        elif key == Gdk.KEY_Down: view['panY'] += step
        else: return False
        self.canvas.queue_draw()
        self.update_buttons()
        return True

    def fill(self, *_):
        if not self.picture or not self.monitors:
            return
        self.view = dict(zoom=1, panX=0, panY=0)
        self.zoom_slider.set_value(1)
        self.canvas.queue_draw()
        self.update_buttons()

    def center_image(self, axis):
        if self.busy or not self.picture or not self.monitors:
            return
        self.view['panX' if axis == 'x' else 'panY'] = 0
        self.canvas.queue_draw()
        self.update_buttons()

    def preview_zoom_changed(self, slider):
        self.preview_zoom = slider.get_value()
        self.preview_label.set_text(self.percent(self.preview_zoom))
        self.canvas.queue_draw()

    def fit_preview(self, *_):
        if self.busy or not self.picture or not self.monitors:
            return
        frames, _ = self.composition()
        area = desktop.preview_bounds(frames, self.picture)
        first = frames[0]
        cx, cy = area['x']+area['width']/2, area['y']+area['height']/2
        # Keep the layout's center fixed; only the preview camera pulls back.
        extent_width = max(area['width'], 2*abs(first['imageX']-cx),
                           2*abs(first['imageX']+self.picture['width']*first['imageScale']-cx))
        extent_height = max(area['height'], 2*abs(first['imageY']-cy),
                            2*abs(first['imageY']+self.picture['height']*first['imageScale']-cy))
        width, height = self.canvas.get_width()-70, self.canvas.get_height()-70
        base = max(1e-12, min(width/area['width'], height/area['height']))
        fitted = min(width/extent_width, height/extent_height)
        self.preview_slider.set_value(min(1, max(.01, fitted/base)))

    def selected_changed(self, *_):
        if not self.monitors:
            return
        self.selected = min(self.monitor_selector.get_selected(), len(self.monitors)-1)
        self.updating = True
        offset = self.adjustments.get(self.monitors[self.selected]['name'], {})
        self.offset_x.set_value(offset.get('x', 0))
        self.offset_y.set_value(offset.get('y', 0))
        self.updating = False
        self.canvas.queue_draw()

    def adjusted(self, *_):
        if self.updating or not self.monitors:
            return
        self.gap = self.gap_spin.get_value()
        name = self.monitors[self.selected]['name']
        self.adjustments[name] = dict(x=self.offset_x.get_value(), y=self.offset_y.get_value())
        try:
            core.save_settings(dict(gap=self.gap, adjustments=self.adjustments))
        except Exception as error:
            self.message(str(error), True)
        self.canvas.queue_draw()
        self.update_buttons()

    def reset(self, *_):
        if not self.monitors:
            return
        self.updating = True
        self.offset_x.set_value(0)
        self.offset_y.set_value(0)
        self.updating = False
        self.adjusted()

    def request(self, directory, name):
        frames, _ = self.composition()
        first = frames[0]
        return dict(image=self.picture, monitors=self.monitors, frames=frames,
                    gap=self.gap, adjustments=self.adjustments, zoomMode='native', **self.view,
                    imageScale=first['imageScale'], imageX=first['imageX'], imageY=first['imageY'],
                    directory=str(directory), exportName=name)

    def export(self, apply):
        if not self.covered() or self.busy or (apply and not desktop.supports_apply(self.background_store)):
            return
        if apply:
            self.run_export(core.STATE/'exports', core.export_name({'image': self.picture}), True)
            return
        dialog = file_picker.create(title=self.translator.text('Kesim klasörünün adını ve konumunu seç'),
                                initial_name=core.export_name({'image': self.picture}))
        def response(dialog, result):
            try:
                chosen = dialog.save_finish(result).get_path()
                if chosen:
                    path = Path(chosen)
                    self.run_export(path.parent, path.name, False)
            except GLib.Error:
                pass
        dialog.save(self, None, response)

    def run_export(self, directory, name, apply):
        if self.busy:
            return
        self.feedback.set_reveal_child(False)
        self.applying = apply
        request = self.request(directory, name)
        def done(result):
            if apply:
                if core.monitors() != request['monitors']:
                    raise ValueError('Ekran düzeni değişti. Ekranları yenileyip tekrar uygula. Kesimler kaydedildi.')
                if hasattr(self.background_store, 'capture'):
                    desktop.apply_wallpaper(result['panorama'], self.background_store, result.get('outputs'))
                else:
                    desktop.apply_wallpaper(result['panorama'], self.background_store)
                self.message('Duvar kâğıdı uygulandı.')
                self.show_feedback('Duvar kâğıdı başarıyla uygulandı',
                    '{count} ekran için ayarlandı. Önceki duvar kâğıdına dön düğmesiyle geri alabilirsin.', count=len(request['monitors']))
            else:
                self.message('Kaydedildi: {directory}', directory=result['directory'])
                self.show_feedback('Kesimler kaydedildi', result['directory'])
        self.submit(lambda: desktop.export(request), done,
                    'Duvar kâğıdı uygulanamadı' if apply else 'Kesimler kaydedilemedi')

    def restore(self, *_):
        if self.busy or not desktop.can_restore(self.background_store):
            self.update_restore_button()
            return
        self.feedback.set_reveal_child(False)
        try:
            desktop.restore_wallpaper(self.background_store)
            self.message('Önceki duvar kâğıdı geri yüklendi.')
            self.show_feedback('Önceki duvar kâğıdı geri yüklendi')
        except Exception as error:
            self.message(str(error), True)
            self.show_feedback('Duvar kâğıdı geri yüklenemedi', str(error), error=True)
        self.update_buttons()

    def import_cut(self, *_):
        dialog = file_picker.create(title=self.translator.text('Kaydedilmiş kesimin layout.json dosyasını seç'))
        def response(dialog, result):
            try:
                chosen = dialog.open_finish(result).get_path()
                if chosen:
                    def done(layout):
                        self.updating = True
                        self.adjustments = layout['adjustments']
                        self.gap = layout['gap']
                        self.gap_spin.set_value(self.gap)
                        self.updating = False
                        self.selected_changed()
                        core.save_settings(dict(gap=self.gap, adjustments=self.adjustments))
                        self.loaded(layout['image'], layout, preserve_legacy=True)
                    self.submit(lambda: core.import_layout(chosen), done)
            except GLib.Error:
                pass
        dialog.open(self, None, response)

    def smoke_check(self):
        try:
            assert self.monitors and self.pixbuf
            assert self.canvas.get_width() > 100 and self.canvas.get_height() > 100
            self.zoom_slider.set_value(1.75)
            assert self.view['zoom'] == 1.75
            frames = self.composition()[0]
            assert len({(f['imageScale'], f['imageX'], f['imageY']) for f in frames}) == 1
            if len(self.monitors) > 1:
                before = self.composition()[0]
                self.monitor_selector.set_selected(1)
                assert self.zoom_slider.get_value() == 1.75
                assert self.composition()[0] == before
                second = self.composition()[0][1]
                ox, oy = self.view_origin
                self.drag_begin(None, ox+(second['x']+second['width']/2)*self.view_scale,
                                oy+(second['y']+second['height']/2)*self.view_scale)
                self.drag_update(None, 18, 8)
                after = self.composition()[0]
                assert all(a['imageX'] != b['imageX'] for a, b in zip(before, after))
                assert len({(f['imageScale'], f['imageX'], f['imageY']) for f in after}) == 1
                self.monitor_selector.set_selected(0)
            self.gap_spin.set_value(24)
            assert self.gap == 24
            self.offset_x.set_value(8)
            assert self.adjustments[self.monitors[self.selected]['name']]['x'] == 8
            previous_view = dict(self.view)
            self.reset()
            assert self.view == previous_view
            self.fill()
            assert self.view == dict(zoom=1, panX=0, panY=0)
            assert all(f['imageScale'] == 1 for f in self.composition()[0])
            assert self.apply_button.get_sensitive() == self.covered()
            core.STATE.mkdir(parents=True, exist_ok=True)
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.canvas.get_width(), self.canvas.get_height())
            self.draw(self.canvas, cairo.Context(surface), self.canvas.get_width(), self.canvas.get_height())
            surface.write_to_png(str(core.STATE/'preview.png'))
            LOG.info('GTK smoke PASS: %d ekran, %dx%d tuval, ortak zoom/konum ve ekran seçimi PASS',
                     len(self.monitors), self.canvas.get_width(), self.canvas.get_height())
            GLib.timeout_add(200, self.capture_smoke)
        except Exception:
            LOG.exception('GTK smoke FAIL')
            self.get_application().exit_code = 1
            self.get_application().quit()
        return GLib.SOURCE_REMOVE

    def capture_smoke(self):
        try:
            widget = self
            snapshot = Gtk.Snapshot.new()
            Gtk.WidgetPaintable.new(widget).snapshot(snapshot, widget.get_width(), widget.get_height())
            node = snapshot.to_node()
            texture = self.get_renderer().render_texture(node, None)
            texture.save_to_png(str(core.STATE/'window.png'))
        except Exception:
            LOG.exception('GTK arayüz görüntüsü alınamadı')
            self.get_application().exit_code = 1
        self.get_application().quit()
        return GLib.SOURCE_REMOVE

    def closing(self, *_):
        if self.stop_background_watch:
            self.stop_background_watch()
            self.stop_background_watch = None
        self.pool.shutdown(wait=False, cancel_futures=True)
        return False


class Application(Gtk.Application):
    def __init__(self, options):
        super().__init__(application_id='io.github.local.WallpaperCutter',
                         flags=Gio.ApplicationFlags.NON_UNIQUE if options.smoke else Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.options = options
        self.exit_code = 0

    def do_activate(self):
        window = self.get_active_window()
        if not window:
            window = Window(self, self.options.image, self.options.smoke)
        window.present()


def main():
    translator = Translator(core.load_preferences()['language'])
    parser = argparse.ArgumentParser(description=translator.text('Çoklu ekran duvar kâğıdı düzenleyici'))
    parser.add_argument('--version', action='version', version='Wallpaper Cutter 1.0.0')
    parser.add_argument('--image', help=translator.text('Başlangıçta açılacak yerel görsel'))
    parser.add_argument('--smoke', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    app = Application(options)
    result = app.run([sys.argv[0]])
    return app.exit_code or result


if __name__ == '__main__':
    sys.exit(main())
