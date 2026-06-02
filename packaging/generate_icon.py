"""
生成 Windows 托盘与 exe 图标 packaging/icon.ico
运行：python packaging/generate_icon.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "icon.ico"


def main() -> None:
    from PIL import Image, ImageDraw

    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (30, 58, 95, 255))
        draw = ImageDraw.Draw(img)
        margin = max(2, size // 8)
        draw.ellipse(
            (margin, margin, size - margin, size - margin),
            fill=(37, 99, 235, 255),
            outline=(255, 255, 255, 200),
        )
        if size >= 32:
            font_size = size // 3
            try:
                from PIL import ImageFont

                font = ImageFont.truetype("msyh.ttc", font_size)
            except OSError:
                font = ImageFont.load_default()
            draw.text((size * 0.28, size * 0.22), "晴", fill=(255, 255, 255, 255), font=font)
        images.append(img)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        OUT,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"已生成: {OUT}")


if __name__ == "__main__":
    main()
