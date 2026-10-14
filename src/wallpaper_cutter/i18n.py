"""Small Turkish/English catalogue with live GTK text bindings."""

STRINGS = {
    'Görsel aç': 'Open image', 'İçe aktar': 'Import', 'Ekranları yenile': 'Refresh displays',
    'Ayarlar': 'Settings', 'Önizleme': 'Preview', 'Görsel': 'Image',
    '%100 = orijinal boyut (1:1)': '100% = original size (1:1)',
    'Yakınlaştırma': 'Zoom', 'Yatay ortala': 'Center horizontally',
    'Dikey ortala': 'Center vertically', 'Orijinal boyutta ortala': 'Center at original size',
    'Ekran hizalama': 'Display alignment', 'Yatay': 'Horizontal', 'Dikey': 'Vertical',
    'Seçili ekranın hizasını sıfırla': 'Reset selected display alignment',
    'Çerçeve boşluğu': 'Bezel gap',
    'Hiza seçili ekrana, boşluk tüm düzene\nuygulanır. Değerler piksel cinsindedir.':
        'Alignment affects the selected display; the gap affects the whole layout. Values are in pixels.',
    'Önceki duvar kâğıdına dön': 'Restore previous wallpaper', 'Dışa aktar': 'Export',
    'Duvar kâğıdı yap': 'Apply wallpaper', 'Uygulanıyor…': 'Applying…',
    'Bir görsel seçerek başla.': 'Choose an image to get started.',
    'Başlamak için bir görsel aç.': 'Open an image to get started.',
    'Önceki görsel bulunamadı. Yeni bir görsel açabilirsin.': 'Previous image not found. You can open a new image.',
    'İşleniyor…': 'Processing…', 'Bildirimi kapat': 'Dismiss notification',
    'Önizleme ölçeği': 'Preview scale', 'Görselin tamamını göster': 'Show entire image',
    'Yalnızca çalışma alanının görünümünü değiştirir; görsel zoom’u ve kesimler korunur':
        'Changes only the workspace view; image zoom and exported crops stay unchanged.',
    'Görseli mevcut zoom ile tüm ekran düzenine göre ortalar; diğer eksen korunur':
        'Centers the image on the display layout at the current zoom; the other axis stays unchanged.',
    'Görseli sürükle · Tekerlekle yakınlaştır · Ok tuşlarıyla ince ayar':
        'Drag the image · Scroll to zoom · Use arrow keys for fine adjustments',
    'Görsel tüm ekranları kaplamıyor. Yakınlaştır veya daha büyük bir görsel seç.':
        'The image does not cover all displays. Zoom in or choose a larger image.',
    '{count} ekran · {names}': '{count} displays · {names}',
    'Ekran düzeni alınamadı': 'Could not read the display layout',
    'Ekranlar algılanamadı': 'No displays detected', 'Duvar kâğıdı görseli seç': 'Choose a wallpaper image',
    'Görseller': 'Images',
    'Önceki ekran bazlı kesim orijinal boyutta ortalandı. Zoom ve konumu yeniden ayarlayabilirsin.':
        'The previous per-display crop was centered at original size. You can adjust zoom and position again.',
    'Görsel hazır. Kadrajı ayarlayıp uygula.': 'Image ready. Adjust the composition and apply it.',
    'Kesim klasörünün adını ve konumunu seç': 'Choose a name and location for the crop folder',
    'Ekran düzeni değişti. Ekranları yenileyip tekrar uygula. Kesimler kaydedildi.':
        'The display layout changed. Refresh displays and apply again. Your crops were saved.',
    'Duvar kâğıdı uygulandı.': 'Wallpaper applied.',
    'Duvar kâğıdı başarıyla uygulandı': 'Wallpaper applied successfully',
    '{count} ekran için ayarlandı. Önceki duvar kâğıdına dön düğmesiyle geri alabilirsin.':
        'Applied to {count} displays. Use Restore previous wallpaper to undo it.',
    'Kaydedildi: {directory}': 'Saved: {directory}', 'Kesimler kaydedildi': 'Crops saved',
    'Duvar kâğıdı uygulanamadı': 'Could not apply wallpaper', 'Kesimler kaydedilemedi': 'Could not save crops',
    'Önceki duvar kâğıdı geri yüklendi.': 'Previous wallpaper restored.',
    'Önceki duvar kâğıdı geri yüklendi': 'Previous wallpaper restored',
    'Duvar kâğıdı geri yüklenemedi': 'Could not restore wallpaper',
    'Kaydedilmiş kesimin layout.json dosyasını seç': 'Choose the saved crop’s layout.json file',
    'Dil': 'Language', 'Başlangıç önizleme ölçeği': 'Default preview scale',
    'Düzenleme panelini göster': 'Show editing panel',
    'Görsel ve ekran hizalama kontrollerini gösterir.': 'Shows the image and display alignment controls.',
    'Önizleme görünümünü değiştirir; görselin zoom’u ve kesimler korunur.':
        'Changes the preview view; image zoom and crops stay unchanged.',
    'Değişiklikler kaydedildiğinde hemen uygulanır.': 'Changes take effect as soon as you save them.',
    'Kaydet': 'Save', 'İptal': 'Cancel', 'Ayarlar kaydedildi.': 'Settings saved.',
    'Ayarlar kaydedilemedi': 'Could not save settings',
    '%{percent}': '{percent}%',
    'GNOME üzerinde etkin ekran bulunamadı.': 'No active displays found on GNOME.',
    'Geçersiz yakınlaştırma ölçeği.': 'Invalid zoom scale.',
    'Bu ekran düzeni ilk sürümün panorama boyutu sınırını aşıyor.': 'This display layout exceeds the supported panorama size.',
    'GNOME duvar kâğıdı ayarlarına yazma izni yok.': 'GNOME wallpaper settings are not writable.',
    'GNOME duvar kâğıdı ayarı kaydedilemedi.': 'Could not save the GNOME wallpaper setting.',
    'Henüz uygulama üzerinden bir duvar kâğıdı uygulanmadı.':
        'No wallpaper applied by this app is currently available to restore.',
    'Bir ayar desteklenen aralığın dışında.': 'An adjustment is outside the supported range.',
    'Ayarlar ekran hizalama verisi içermelidir.': 'Settings must contain a monitor adjustment object.',
    'Geçersiz ekran hizalaması.': 'Invalid monitor adjustment.',
    'Dışa aktarılacak klasör için bir ad gir.': 'Enter a name for the export.',
    'Klasör adı en fazla 180 bayt olmalı; bölü veya kontrol karakteri içermemeli.':
        'Use a folder name up to 180 bytes, without slashes or control characters.',
    'Bu adla çok fazla kesim var. Farklı bir ad seç.': 'Too many exports with this name. Choose a different name.',
    'Geçersiz ekran bazlı kadraj.': 'Invalid per-monitor composition.',
    'Geçersiz ekran görünümü.': 'Invalid monitor view.',
    'Bu yerleşim dosyası çok büyük.': 'This layout file is too large.',
    'Geçersiz zoom ölçeği modu.': 'Invalid zoom scale mode.',
    'Bu kesimde geçersiz kaynak görseli var.': 'Invalid source image in this export.',
    'Kaynak görsel kesim klasörünün içinde olmalıdır.': 'The source image must be inside the exported folder.',
    'Orijinal görsel bulunamadı. Kaynak görseli yerleşim dosyasıyla birlikte sakla.':
        'The original image is missing. Keep the source image with the exported layout.',
    '1 ile 32 arasında ekran seç.': 'Choose between 1 and 32 displays.',
    'Aynı ekran adı birden fazla kez kullanılmış.': 'Duplicate display name.',
    'Görsel tüm ekranları kaplamalı. Yakınlaştır veya görseli çerçevelerin içine taşı.':
        'The image must cover every display. Choose Fill layout or move the image back inside the frames.',
    'Geçersiz uygulama dili.': 'Invalid application language.',
    'Geçersiz panel görünürlüğü ayarı.': 'Invalid panel visibility setting.',
    'GNOME için çoklu ekran duvar kâğıdı düzenleyici': 'Multi-display wallpaper editor for GNOME',
    'Çoklu ekran duvar kâğıdı düzenleyici': 'Cross-platform multi-display wallpaper editor',
    'Bu masaüstünde otomatik duvar kâğıdı uygulaması yok. Kesimleri dışa aktarıp duvar kâğıdı aracınla uygula.':
        'Automatic wallpaper setting is unavailable on this desktop. Export the crops and apply them with your wallpaper tool.',
    'Başlangıçta açılacak yerel görsel': 'Local image to open at startup',
    'Önizleme ölçeğini azalt': 'Decrease preview scale',
    'Önizleme ölçeğini artır': 'Increase preview scale',
    'Önizleme ölçeği 1 ile 100 arasında bir tam sayı olmalı.': 'Preview scale must be a whole number between 1 and 100.',
}
REVERSE = {english: turkish for turkish, english in STRINGS.items()}


class Translator:
    def __init__(self, language='tr'):
        self.language = language
        self.bindings = {}

    def text(self, source, **parameters):
        canonical = REVERSE.get(source, source)
        translated = STRINGS.get(canonical, canonical) if self.language == 'en' else canonical
        return translated.format(**parameters) if parameters else translated

    def bind(self, widget, property_name, source, **parameters):
        self.bindings[(widget, property_name)] = (source, parameters)
        getattr(widget, 'set_'+property_name)(self.text(source, **parameters))
        return widget

    def set_language(self, language):
        self.language = language
        for (widget, property_name), (source, parameters) in self.bindings.items():
            getattr(widget, 'set_'+property_name)(self.text(source, **parameters))
