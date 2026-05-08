"""
Norm Konteyner Sayım Portalı — Kullanıcı Kılavuzu PDF/DOCX üretici.

Çalıştır:
    python scripts/generate_user_guide.py

Çıktı: docs/Norm_Konteyner_Kullanici_Kilavuzu.docx
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Cm, Inches


PRIMARY = RGBColor(0x1F, 0x3A, 0x8A)   # Lacivert mavi (kurumsal)
ACCENT = RGBColor(0x25, 0x63, 0xEB)    # Açık mavi
SUCCESS = RGBColor(0x16, 0xA3, 0x4A)
DANGER = RGBColor(0xDC, 0x26, 0x26)
MUTED = RGBColor(0x47, 0x55, 0x69)
TEXT = RGBColor(0x0F, 0x17, 0x2A)


def add_title(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(24)
    run.font.color.rgb = PRIMARY
    p.paragraph_format.space_after = Pt(8)


def add_subtitle(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.size = Pt(11)
    run.font.color.rgb = MUTED
    run.italic = True
    p.paragraph_format.space_after = Pt(24)


def add_h1(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(18)
    run.font.color.rgb = PRIMARY
    p.paragraph_format.space_before = Pt(20)
    p.paragraph_format.space_after = Pt(8)
    # alt çizgi efekti
    p.paragraph_format.keep_with_next = True
    return p


def add_h2(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = ACCENT
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    return p


def add_para(doc, text, *, bold_words=None, color=None, size=11):
    p = doc.add_paragraph()
    bold_words = set(bold_words or [])
    if bold_words:
        # naive — split by spaces
        for word in text.split(" "):
            run = p.add_run(word + " ")
            run.font.size = Pt(size)
            run.font.color.rgb = color or TEXT
            if any(w in word for w in bold_words):
                run.bold = True
    else:
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.font.color.rgb = color or TEXT
    p.paragraph_format.space_after = Pt(6)
    return p


def add_bullet(doc, text, *, indent=0.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Inches(indent)
    p.paragraph_format.space_after = Pt(3)
    run = p.runs[0] if p.runs else p.add_run("")
    p.runs[0].text = ""  # clear
    new_run = p.add_run(text)
    new_run.font.size = Pt(11)
    new_run.font.color.rgb = TEXT
    return p


def add_numbered(doc, text):
    p = doc.add_paragraph(style="List Number")
    p.paragraph_format.space_after = Pt(3)
    if p.runs:
        p.runs[0].text = ""
    run = p.add_run(text)
    run.font.size = Pt(11)
    run.font.color.rgb = TEXT
    return p


def add_callout(doc, label, body, color=ACCENT):
    """Renkli kutu — vurgu için."""
    p = doc.add_paragraph()
    label_run = p.add_run(f"  ▸  {label}: ")
    label_run.bold = True
    label_run.font.size = Pt(11)
    label_run.font.color.rgb = color
    body_run = p.add_run(body)
    body_run.font.size = Pt(11)
    body_run.font.color.rgb = TEXT
    p.paragraph_format.left_indent = Inches(0.2)
    p.paragraph_format.space_after = Pt(8)
    return p


def add_divider(doc):
    p = doc.add_paragraph()
    run = p.add_run("─" * 70)
    run.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)
    run.font.size = Pt(8)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(12)


def main():
    doc = Document()

    # Sayfa düzeni
    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

    # Default font
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ----- Kapak -----
    add_title(doc, "Norm Fasteners")
    add_subtitle(doc, "Konteyner Sayım Portalı — Kullanıcı Kılavuzu")
    add_para(
        doc,
        "Bu kılavuz, haftalık konteyner sayım girişlerinizi portal üzerinden "
        "nasıl yapacağınızı adım adım anlatır. Sistem hakkında temel bilgiler, "
        "form doldurma kuralları ve sık karşılaşılan sorunlar dahildir.",
        color=MUTED, size=10,
    )
    add_divider(doc)

    # ----- 1. Giriş ve Şifre -----
    add_h1(doc, "1.  Giriş ve Şifre")
    add_para(doc, "Portala bilgisayarınızdaki tarayıcıdan (Chrome, Edge vb.) erişiyorsunuz.")
    add_h2(doc, "Adım adım giriş")
    add_numbered(doc, "Tarayıcıyı açın, yönetici tarafından size iletilen portal adresini girin.")
    add_numbered(doc, "Açılan ekranda kullanıcı adınızı ve şifrenizi yazın.")
    add_numbered(doc, "“Giriş Yap” butonuna basın.")
    add_callout(doc, "Yanlış şifre", "Sağ üst köşede kırmızı bir uyarı çıkar. Doğru bilgilerle tekrar deneyin.", DANGER)
    add_callout(doc, "Şifrenizi unuttuysanız", "Yöneticinizle iletişime geçin, sıfırlatabilir.", MUTED)

    # ----- 2. Ana Sayfa -----
    add_h1(doc, "2.  Ana Sayfa")
    add_para(
        doc,
        "Login sonrası ilk açılan sayfa. Üst kısımda “Hoş geldin, [adınız]” yazısı, "
        "altında bu haftanın tarihi ve sayım giriş penceresinin durumu görünür."
    )
    add_h2(doc, "Pencere durumu")
    add_bullet(doc, "Yeşil “Sayım Açık”: o anda sayım giriyor olabilirsiniz.")
    add_bullet(doc, "Gri “Sayım Kapalı”: pencere açık değil. Açılma zamanı yine ekranda yazılı (örn. “Pazartesi 09:00 – 12:00 arasında açılır”).")
    add_callout(doc, "Pencere zamanı", "Her hafta Pazartesi 09:00 – 12:00 arası açıktır. Yöneticiyle paylaşılan farklı bir saat varsa, sistem ona göre çalışır.", ACCENT)
    add_h2(doc, "Hızlı erişim kartları")
    add_para(doc, "Ana sayfada doğrudan tıklayabileceğiniz kısayollar var:")
    add_bullet(doc, "Sayım Girişi — haftalık sayımı buradan girersiniz.")
    add_bullet(doc, "Haftalık Durum — bu hafta hangi bölümler girdi, hangileri eksik?")

    # ----- 3. Sayım Girişi (en kritik) -----
    add_h1(doc, "3.  Sayım Girişi (En Önemli Bölüm)")
    add_para(
        doc,
        "Sol menüden “Sayım Girişi”ne tıklayın. Form yüklenir. "
        "Pencere kapalıyken form pasif olur, yalnızca pencere açıkken doldurulabilir.",
    )

    add_h2(doc, "Üst kısım — Hafta ve Bölüm")
    add_bullet(doc, "Hafta otomatik gelir, değiştiremezsiniz. Sistem o anki haftayı seçer.")
    add_bullet(doc, "“Bölüm” açılır listesinden kendi sorumlu olduğunuz bölümü seçin.")
    add_bullet(doc, "Birden fazla bölümden sorumluysanız hepsi listede çıkar; her birine ayrı ayrı sayım girersiniz.")

    add_h2(doc, "Tarih ve saat")
    add_para(doc, "Otomatik olarak işlenir, manuel girilmez. Sistem kayıt anının zamanını damgalar.")

    add_h2(doc, "Yarı mamül tonajı (toplam)")
    add_callout(doc, "Zorunlu", "Bu alan boş bırakılırsa kaydedemezsiniz. Sistem uyarı verir, kutu kırmızıya döner.", DANGER)
    add_para(doc, "O hafta için bölümünüzdeki yarı mamül tonajını yazın. Ondalık girebilirsiniz (örn. 1234 veya 12.5).")

    add_h2(doc, "Renk × Sayım tablosu")
    add_para(doc, "Her renk için 4 sayı girersiniz. Açıklamalar:")
    add_bullet(doc, "Boş — o renkten kaç adet boş konteyner var?")
    add_bullet(doc, "Dolu (toplam) — o renkten kaç adet dolu konteyner var?")
    add_bullet(doc, "Kanban — dolu konteynerlerin kaç tanesi kanban olarak kullanılıyor? (Kanban dolu’nun ALT KÜMESİ’dir; doludan büyük olamaz.)")
    add_bullet(doc, "Hurdaya Ayrılacak — artık kullanılmayacak konteynerler (ayağı kırık, çatlak vb.). Boş ve dolu sayılarına DAHİL DEĞİLDİR; ayrı sayılır.")

    add_callout(doc, "Örnek", "Mavi renkte: 100 boş, 500 dolu, doluların 100’ü kanban, 5 tane de hurdaya ayrılacak.", SUCCESS)
    add_callout(doc, "Önemli kural", "Kanban miktarı, dolu miktarından büyük olamaz. Sistem buna izin vermez.", DANGER)

    add_h2(doc, "Kaydetme")
    add_numbered(doc, "Tüm değerleri girdikten sonra altta “Kaydet” butonuna basın.")
    add_numbered(doc, "Sağ üst köşede yeşil “Sayım kaydedildi” bildirimi görünür.")

    add_h2(doc, "Yanlış girdiyseniz — Güncelleme")
    add_para(doc, "Aynı bölüm için aynı hafta içinde tekrar form açabilirsiniz:")
    add_bullet(doc, "Mevcut değerleriniz formda dolu gelir.")
    add_bullet(doc, "Düzeltmek istediğiniz alanı değiştirin.")
    add_bullet(doc, "Buton bu kez “Güncelle” yazar. Basın.")
    add_bullet(doc, "Sağ üstte “Sayım güncellendi” bildirimi görünür.")
    add_callout(doc, "Hiç değişiklik yapmadan tekrar bastığınızda", "“Değişiklik yapılmadı” uyarısı çıkar. Veriniz olduğu gibi kalır, herhangi bir kayıp olmaz.", MUTED)

    # ----- 4. Haftalık Durum -----
    add_h1(doc, "4.  Haftalık Durum")
    add_para(doc, "Sol menüden “Haftalık Durum”a girin. Bu sayfa o haftanın tüm bölüm bilgilerini özetler.")
    add_h2(doc, "Üstteki özet")
    add_bullet(doc, "Toplam bölüm sayısı içinde kaç tanesi sayım girdi.")
    add_bullet(doc, "Eksik kalan bölümlerin listesi (sorumlu kullanıcı adıyla).")

    add_h2(doc, "Bölüm × Renk Matrisi")
    add_para(
        doc,
        "Aşağıdaki tablo her bölüm için her rengin sayım değerlerini tek bakışta gösterir. "
        "Hücre formatı: Boş / Dolu / Kanban / Hurdaya Ayrılacak.",
    )
    add_callout(doc, "Örnek hücre", "100/500/100/5 → 100 boş, 500 dolu, 100 kanban, 5 hurdaya ayrılacak.", ACCENT)
    add_para(doc, "En sağda Tonaj sütunu bulunur — bölümün o haftaki toplam tonajı.")

    # ----- 5. Yetkililer -----
    add_h1(doc, "5.  Yetkililer")
    add_para(
        doc,
        "Sol menüden “Yetkililer” sayfasına ulaşılır. Hangi bölüme kimin yetkili olduğunu, "
        "her birinin sayım girip girmediğini gösterir. Kontrol amaçlıdır."
    )

    # ----- 6. Çıkış -----
    add_h1(doc, "6.  Çıkış Yapma")
    add_para(doc, "Sol menünün en altındaki “Çıkış Yap” butonuna basın. Login ekranına döner.")
    add_callout(doc, "Bilgisayardan kalkıyorsanız", "Mutlaka çıkış yapın. Aksi halde başka biri sizin oturumunuzla işlem yapabilir.", DANGER)

    # ----- 7. SSS -----
    add_h1(doc, "7.  Sık Karşılaşılan Sorunlar")

    add_h2(doc, "“Sayım Girişi yapamıyorum, form pasif.”")
    add_bullet(doc, "Pencere kapalı — Pazartesi 09:00 – 12:00 dışındasınız. Pencere açıldığında tekrar deneyin.")
    add_bullet(doc, "Bölüm yetkisi atanmamış — “Yetkili bölüm bulunamadı” uyarısı görüyorsanız, yöneticinizle iletişime geçin.")

    add_h2(doc, "“Şifremi unuttum.”")
    add_para(doc, "Yöneticinize haber verin. Şifrenizi sıfırlayıp size yeni şifrenizi iletecektir.")

    add_h2(doc, "“Yanlış değer girdim, düzeltebilir miyim?”")
    add_para(
        doc,
        "Pencere hâlâ açıksa: aynı bölüm + aynı hafta için Sayım Girişi sayfasını "
        "tekrar açıp değerleri düzeltin, “Güncelle”ye basın. Pencere kapandıysa "
        "yöneticinize bildirin; o gerektiğinde sizin için geç giriş açabilir.",
    )

    add_h2(doc, "“Saat geçti, sayımı giremedim.”")
    add_para(
        doc,
        "Yöneticinize haber verin. Yönetici geç giriş penceresi açabilir. "
        "Açıldığında siz ekranda “Sayım Açık” durumunu yine görür, normal şekilde sayım girersiniz.",
    )

    add_h2(doc, "“Kanban miktarını dolu’dan büyük yazınca uyarı veriyor.”")
    add_para(
        doc,
        "Doğru çalışıyor. Kanban konteynerler dolu konteynerlerin alt kümesidir; "
        "doludan büyük olamaz. Önce dolu sayısını gözden geçirin.",
    )

    add_h2(doc, "“Tonaj alanı kırmızı yanıp sönüyor.”")
    add_para(
        doc,
        "Tonaj zorunlu alandır, boş bırakılamaz. Değer girip “Kaydet”e tekrar basın.",
    )

    # ----- Footer -----
    add_divider(doc)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Norm Fasteners — Konteyner Operasyon Merkezi")
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    run.italic = True

    # Kaydet
    out_dir = Path(__file__).resolve().parent.parent / "docs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "Norm_Konteyner_Kullanici_Kilavuzu.docx"
    doc.save(out_path)
    print(f"OK -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
