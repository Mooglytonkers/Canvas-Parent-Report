#!/usr/bin/env python3
"""Draw an original report-and-checkmark icon. No third-party logos."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    margin = max(1, int(size * 0.06))
    radius = int(size * 0.22)
    pen.rounded_rectangle(
        [margin, margin, size - margin - 1, size - margin - 1],
        radius=radius,
        fill=(31, 78, 121, 255),
    )
    left = int(size * 0.28)
    top = int(size * 0.22)
    right = int(size * 0.72)
    bottom = int(size * 0.78)
    pen.rounded_rectangle([left, top, right, bottom], radius=max(2, size // 28), fill=(255, 255, 255, 255))
    fold = int(size * 0.12)
    pen.polygon(
        [(right - fold, top), (right, top + fold), (right - fold, top + fold)],
        fill=(214, 226, 236, 255),
    )
    line_left = int(size * 0.36)
    line_right = int(size * 0.62)
    thickness = max(2, size // 28)
    for index in range(3):
        y = int(size * (0.38 + index * 0.12))
        pen.rounded_rectangle(
            [line_left, y, line_right, y + thickness],
            radius=thickness // 2,
            fill=(31, 78, 121, 255),
        )
    badge_r = int(size * 0.16)
    center = (int(size * 0.70), int(size * 0.70))
    pen.ellipse(
        [center[0] - badge_r, center[1] - badge_r, center[0] + badge_r, center[1] + badge_r],
        fill=(47, 133, 90, 255),
    )
    check = [
        (center[0] - int(badge_r * 0.45), center[1] + int(badge_r * 0.05)),
        (center[0] - int(badge_r * 0.05), center[1] + int(badge_r * 0.40)),
        (center[0] + int(badge_r * 0.50), center[1] - int(badge_r * 0.35)),
    ]
    pen.line(check, fill=(255, 255, 255, 255), width=max(2, size // 18), joint="curve")
    return image


def main() -> None:
    folder = Path(__file__).resolve().parent
    large = draw(256)
    large.save(folder / "icon.png")
    sizes = [draw(size) for size in (16, 24, 32, 48, 64, 128, 256)]
    sizes[-1].save(
        folder / "icon.ico",
        format="ICO",
        sizes=[(image.width, image.height) for image in sizes],
        append_images=sizes[:-1],
    )


if __name__ == "__main__":
    main()
