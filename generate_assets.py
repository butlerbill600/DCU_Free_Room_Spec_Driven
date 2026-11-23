import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def generate_icon():
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)

    # Create a 512x512 rounded rectangle app icon
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient-like background circle/rounded square
    padding = 32
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=96,
        fill=(37, 99, 235, 255),  # DCU Blue #2563eb
        outline=(29, 78, 216, 255),
        width=8,
    )

    # Inner decorative accent circle
    center = size // 2
    draw.ellipse(
        [center - 140, center - 140, center + 140, center + 140],
        fill=(255, 255, 255, 40),
    )

    # Pin & building symbol shapes
    # Draw pin head
    draw.ellipse(
        [center - 70, center - 110, center + 70, center + 30],
        fill=(255, 255, 255, 240),
    )
    # Inner pin dot
    draw.ellipse(
        [center - 30, center - 70, center + 30, center - 10],
        fill=(37, 99, 235, 255),
    )
    # Pin needle
    draw.polygon(
        [
            (center - 45, center - 10),
            (center + 45, center - 10),
            (center, center + 110),
        ],
        fill=(255, 255, 255, 240),
    )

    png_path = assets_dir / "icon.png"
    img.save(png_path)
    print(f"Generated {png_path}")

    # Generate ICNS if iconutil is available on macOS
    icns_path = assets_dir / "dcu_rooms.icns"
    try:
        # Convert PNG to ICNS using Pillow's save or iconutil
        img.save(icns_path, format="ICNS")
        print(f"Generated {icns_path}")
    except Exception as e:
        print(f"Pillow ICNS save notice: {e}. Fallback to png icon.")
        # If Pillow icns fails, write png directly to icns path or iconset
        img.save(icns_path, format="PNG")


if __name__ == "__main__":
    generate_icon()
