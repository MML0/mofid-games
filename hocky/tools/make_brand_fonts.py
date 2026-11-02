"""Build the game's brand fonts in assets/fonts from the source files in Fonts/.

SDL_ttf can only draw a variable font at its default (Light) instance, so Pinar's weights are baked into static
files here. Run this once after changing the fonts. It needs fontTools: pip install fonttools

    python3 tools/make_brand_fonts.py
"""

import shutil
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "Fonts", ROOT / "assets" / "fonts"
PINAR = SRC / "Pinar-VF[DSTY,KSHD,wght].ttf"  # the variant with Latin digits; Pinar-VF-FD has Persian ones
WEIGHTS = {"Regular": 400, "Medium": 500, "Bold": 700, "Black": 900}
COPIES = ("SF-Compact-Display-Bold.ttf", "SF-Compact-Display-Heavy.ttf")


def main() -> None:
    for name, wght in WEIGHTS.items():
        font = TTFont(PINAR)
        static = instantiateVariableFont(font, {"wght": wght, "DSTY": 0, "KSHD": 100})
        for rec in static["name"].names:
            if rec.nameID in (2, 17):
                rec.string = name
            elif rec.nameID == 4:
                rec.string = f"Pinar {name}"
            elif rec.nameID == 6:
                rec.string = f"Pinar-{name}"
        static.save(OUT / f"Pinar-{name}.ttf")
        print("wrote", OUT / f"Pinar-{name}.ttf")
    for name in COPIES:
        shutil.copy(SRC / name, OUT / name)
        print("copied", name)


if __name__ == "__main__":
    main()
