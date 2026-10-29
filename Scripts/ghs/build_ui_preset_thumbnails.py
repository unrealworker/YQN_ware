"""Build the four scene-setting preview thumbnails without changing source PNGs.

Run with Python and Pillow. Inputs mirror settings().presets in
Content/GHSTwinUI/web/app.js; full-size images remain available to other views.
"""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, features


REPOSITORY = Path(__file__).resolve().parents[2]
ASSETS = REPOSITORY / "Content" / "GHSTwinUI" / "web" / "assets"
PRESETS = (
    ("overview", "warehouse-overview"),
    ("top", "warehouse-top"),
    ("racks", "warehouse-racks"),
    ("floor", "warehouse-storage"),
)
SIZE = (480, 270)
QUALITY = 92


def main():
    if not features.check("webp"):
        raise RuntimeError("This Pillow installation does not support WebP.")
    results = []
    for preset, basename in PRESETS:
        source = ASSETS / (basename + ".png")
        destination = ASSETS / "presets" / (basename + ".webp")
        original = source.read_bytes()
        source_hash = sha256(original).hexdigest()
        with Image.open(BytesIO(original)) as image:
            if image.width * SIZE[1] != image.height * SIZE[0]:
                raise ValueError(f"{source.name}: expected a 16:9 source; refusing to crop or distort it.")
            # Drop only a fully opaque alpha channel; preserve any transparency.
            mode = "RGBA" if "A" in image.getbands() and image.getchannel("A").getextrema() != (255, 255) else "RGB"
            thumbnail = image.convert(mode).resize(SIZE, Image.Resampling.LANCZOS)
            encoded = BytesIO()
            thumbnail.save(encoded, format="WEBP", quality=QUALITY, method=6, exact=True)
        output = encoded.getvalue()
        with Image.open(BytesIO(output)) as check:
            check.load()
            if check.format != "WEBP" or check.size != SIZE:
                raise RuntimeError(f"Invalid generated thumbnail: {destination.name}")
        if sha256(source.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError(f"Source changed during generation: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_bytes() != output:
            destination.write_bytes(output)
        results.append({
            "preset": preset,
            "source": source.relative_to(REPOSITORY).as_posix(),
            "thumbnail": destination.relative_to(REPOSITORY).as_posix(),
            "size": SIZE,
            "source_bytes": len(original),
            "thumbnail_bytes": len(output),
            "source_sha256": source_hash,
            "thumbnail_sha256": sha256(output).hexdigest(),
            "source_unchanged": True,
        })
    source_bytes = sum(item["source_bytes"] for item in results)
    thumbnail_bytes = sum(item["thumbnail_bytes"] for item in results)
    print(json.dumps({
        "quality": QUALITY,
        "images": results,
        "source_bytes": source_bytes,
        "thumbnail_bytes": thumbnail_bytes,
        "reduction_percent": round((1 - thumbnail_bytes / source_bytes) * 100, 2),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
