import argparse
import struct
import sys
from pathlib import Path
from PIL import Image

IWF_MAGIC = b'iwf\0'
DIR_ENTRY = struct.Struct('<30s2xII')   # 40 bytes
RAW_MAGIC = b'RAW\0'
RAW_HEADER = struct.Struct('<4sHHHHI')  # magic, w, h, fmt, reserved, rgb_size = 16 bytes


def parse_iwf(path):
    data = Path(path).read_bytes()
    if data[:4] != IWF_MAGIC:
        raise ValueError(f"Invalid watch face: bad magic {data[:4]!r}")
    version, count = struct.unpack_from('<HH', data, 4)
    entries = []
    for i in range(count):
        off = 8 + i * DIR_ENTRY.size
        raw_name, doff, dsize = DIR_ENTRY.unpack_from(data, off)
        name = raw_name.rstrip(b'\0').decode('utf-8', 'replace')
        entries.append((name, doff, dsize))
    return version, count, entries, data


def decode_raw_image(blob):
    """Decode a RAW-wrapped RGB565(+alpha) blob into a PIL image."""
    if blob[:4] != RAW_MAGIC:
        raise ValueError(f"Bad RAW magic: {blob[:4]!r}")
    _, w, h, fmt, _reserved, rgb_size = RAW_HEADER.unpack_from(blob, 0)

    has_alpha = (fmt & 0xFF00) != 0     # 0x6685 -> alpha, 0x0085 -> no alpha
    rgb_bytes = w * h * 2
    if rgb_size not in (0, rgb_bytes):
        raise ValueError(f"rgb_size {rgb_size} != {rgb_bytes}")

    off = RAW_HEADER.size
    rgb = blob[off:off + rgb_bytes]
    off += rgb_bytes

    if has_alpha:
        alpha_bytes = (w * h + 1) // 2
        alpha = blob[off:off + alpha_bytes]
    else:
        alpha = None

    mode = 'RGBA' if alpha else 'RGB'
    img = Image.new(mode, (w, h))
    px = img.load()

    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 2
            v = (rgb[i] << 8) | rgb[i + 1]              # Big-endian
            r = ((v >> 11) & 0x1F) << 3
            g = ((v >> 5) & 0x3F) << 2
            b = (v & 0x1F) << 3
            if alpha is not None:
                a_idx = y * w + x
                byte = alpha[a_idx >> 1]
                nib = (byte >> 4) if (a_idx & 1) == 0 else (byte & 0x0F)
                a = nib * 17  # 0..15 -> 0..255
                px[x, y] = (r, g, b, a)
            else:
                px[x, y] = (r, g, b)
    return img


def unpack(input_file, output_dir):
    version, count, entries, data = parse_iwf(input_file)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Version={version}, entries={count}")

    for name, off, size in entries:
        blob = data[off:off + size]

        if name.endswith('.json'):
            (out / name).write_bytes(blob)
            print(f"  [json] {name}  ({size} bytes)")
            continue

        if blob[:4] != RAW_MAGIC:
            # Unknown non-RAW entry: write as-is
            (out / name).write_bytes(blob)
            print(f"  [raw?] {name}  ({size} bytes)  magic={blob[:4]!r}")
            continue

        img = decode_raw_image(blob)
        # Always save as .png (real PNG, replacing the fake one)
        png_name = name if name.endswith('.png') else f"{name}.png"
        img.save(out / png_name)
        print(f"  [img ] {name}  {img.size} {img.mode}  ->  {png_name}")


def main():
    ap = argparse.ArgumentParser(description="Unpack an .iwf file")
    ap.add_argument("input_file")
    ap.add_argument("output_dir")
    args = ap.parse_args()

    if not Path(args.input_file).exists():
        print(f"Input file {args.input_file} does not exist.")
        sys.exit(1)

    try:
        unpack(args.input_file, args.output_dir)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()