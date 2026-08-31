#!/usr/bin/env python3
"""Genere og-image.png — la vignette de partage (Open Graph / Twitter card).

C'est l'image qui represente la station partout ou son lien est colle :
annuaires type TuneIn, WhatsApp, Discord, X, Facebook, Slack. Elle etait
jusqu'ici un PNG sans source, impossible a modifier sans le refaire a la main :
d'ou ce script.

Format impose par Open Graph : 1200x630 (ratio 1.91:1). Les plateformes
recadrent souvent les bords, donc rien d'important ne touche la marge.

Le texte est integralement en anglais, comme le player et les annuaires ou la
station est referencee. Aucune mention d'origine geographique ni de drapeau :
la station se presente uniquement par sa musique.

Polices : Space Grotesk / Space Mono sont celles du player, mais elles ne sont
pas installees par defaut sous Windows. On les utilise si elles sont presentes
(depose les .ttf dans tools/fonts/ ou installe-les), sinon on retombe sur
Arial Bold + Consolas, qui tiennent le meme role : une grotesque grasse pour le
logo, une monospace pour le reste.

Usage : python tools/make_og_image.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "og-image.png"
FONT_DIR = Path(__file__).resolve().parent / "fonts"
WIN_FONTS = Path("C:/Windows/Fonts")

W, H = 1200, 630

BG = (13, 13, 13)
FG = (255, 255, 255)
ACCENT = (245, 230, 66)
RED = (255, 59, 59)

# Marge exterieure : les plateformes recadrent parfois jusqu'a ~5 % des bords.
MARGIN = 44
SHADOW = 14  # decalage du bloc jaune, comme les box-shadow du player
BORDER = 5


def load_font(candidates, size):
    """Premiere police trouvee parmi les candidates, sinon la police par defaut.

    Les candidates sont donnees de la plus fidele (celle du player) a la plus
    disponible (celle de Windows) — la valeur de repli n'est jamais un echec.
    """
    for name in candidates:
        for folder in (FONT_DIR, WIN_FONTS):
            path = folder / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def text_width(draw, s, font):
    return draw.textbbox((0, 0), s, font=font)[2]


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    bold = lambda s: load_font(["SpaceGrotesk-Bold.ttf", "arialbd.ttf"], s)
    mono = lambda s: load_font(["SpaceMono-Regular.ttf", "consola.ttf"], s)
    mono_b = lambda s: load_font(["SpaceMono-Bold.ttf", "consolab.ttf"], s)

    # ---- Cadre : bloc jaune decale + cadre blanc par-dessus ----
    box = (MARGIN, MARGIN, W - MARGIN - SHADOW, H - MARGIN - SHADOW)
    d.rectangle((box[0] + SHADOW, box[1] + SHADOW, box[2] + SHADOW, box[3] + SHADOW), fill=ACCENT)
    d.rectangle(box, fill=BG, outline=FG, width=BORDER)

    pad = 56
    x = box[0] + pad
    y = box[1] + pad

    # ---- Pastille "on air" ----
    d.rectangle((x, y, x + 22, y + 22), fill=RED)
    y += 22 + 42

    # ---- Logo ----
    f_logo = bold(122)
    d.text((x, y), "KALBASSFM", font=f_logo, fill=FG)
    y += d.textbbox((0, 0), "KALBASSFM", font=f_logo)[3] + 26

    # ---- Barre d'accent sous le logo ----
    d.rectangle((x, y, x + 500, y + 9), fill=ACCENT)
    y += 9 + 54

    # ---- Accroche ----
    f_tag = mono(41)
    tagline = "THE 100% ELECTRONIC WEBRADIO"
    d.text((x, y), tagline, font=f_tag, fill=FG)
    y += d.textbbox((0, 0), tagline, font=f_tag)[3] + 44

    # ---- Genres ----
    f_gen = mono_b(34)
    d.text((x, y), "HOUSE  -  DISCO  -  TECH HOUSE  -  TECHNO", font=f_gen, fill=ACCENT)

    # ---- Bandeau defilant, colle au bord interieur bas du cadre ----
    # Dessine dans une image separee aux dimensions exactes du bandeau, puis
    # collee : le motif est volontairement plus long que la barre pour donner
    # l'impression d'un defilement sans fin, et c'est le collage qui coupe
    # proprement. Ecrire directement sur l'image finale ferait deborder le texte
    # par-dessus la bordure blanche du cadre.
    bar_h = 54
    bar_w = (box[2] - BORDER) - (box[0] + BORDER)
    bar_top = box[3] - BORDER - bar_h
    bar = Image.new("RGB", (bar_w, bar_h), ACCENT)
    bd = ImageDraw.Draw(bar)
    f_bar = mono_b(27)
    unit = "*  24/7  *  KALBASS FM  "
    repeats = max(1, bar_w // max(1, text_width(bd, unit, f_bar)) + 2)
    bd.text((14, bar_h // 2), unit * repeats, font=f_bar, fill=BG, anchor="lm")
    img.paste(bar, (box[0] + BORDER, bar_top))

    img.save(OUT, "PNG", optimize=True)
    print(f"ecrit : {OUT}  ({OUT.stat().st_size // 1024} Ko)")
    print(f"logo  : {f_logo.path if hasattr(f_logo, 'path') else 'defaut'}")
    print(f"mono  : {f_tag.path if hasattr(f_tag, 'path') else 'defaut'}")


if __name__ == "__main__":
    main()
