"""Build HouRM_icon.ico with all standard Windows shell sizes from HouRM_icon.png."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PIL.IcoImagePlugin import IcoFile

ROOT = Path(__file__).resolve().parents[1]
PNG_PATH = ROOT / "HouRM_icon.png"
ICO_PATH = ROOT / "HouRM_icon.ico"

# Explorer: small/medium/large/extra-large; 512 for high-DPI scaling.
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256, 512)


def square_crop(im: Image.Image) -> Image.Image:
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def build_ico(png_path: Path = PNG_PATH, ico_path: Path = ICO_PATH) -> Path:
    if not png_path.is_file():
        raise FileNotFoundError(png_path)

    master = square_crop(Image.open(png_path).convert("RGBA"))
    max_side = max(master.size)
    sizes = tuple((s, s) for s in ICO_SIZES if s <= max_side)
    if not sizes:
        raise ValueError(f"Source image too small: {master.size}")

    master.save(ico_path, format="ICO", sizes=sizes)
    return ico_path


def ico_embedded_sizes(ico_path: Path) -> list[int]:
    with open(ico_path, "rb") as f:
        entries = IcoFile(f).entry
    out = []
    for e in entries:
        w, h = e.dim
        out.append(256 if w == 0 else w)
    return sorted(set(out))


def main() -> int:
    ico = build_ico()
    sizes = ico_embedded_sizes(ico)
    print(f"Wrote {ico}")
    print(f"  Embedded sizes: {', '.join(f'{s}x{s}' for s in sizes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
