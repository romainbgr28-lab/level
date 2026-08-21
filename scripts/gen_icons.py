import struct
import zlib
import os

def make_png(path, size, bg, fg, mark_ratio=0.5):
    w = h = size
    pixels = bytearray()
    cx, cy = w / 2, h / 2
    r = size * mark_ratio / 2
    for y in range(h):
        row = bytearray()
        for x in range(w):
            dx, dy = x - cx, y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            # simple rounded-square "L" mark: a vertical bar + base, violet on dark bg
            in_mark = False
            bar_w = size * 0.09
            if (cx - size * 0.14) - bar_w / 2 <= x <= (cx - size * 0.14) + bar_w / 2 and cy - r * 0.9 <= y <= cy + r * 0.9:
                in_mark = True
            if cx - size * 0.14 <= x <= cx + size * 0.22 and cy + r * 0.9 - bar_w <= y <= cy + r * 0.9:
                in_mark = True
            row += bytes(fg if in_mark else bg)
        pixels += row

    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += pixels[y * w * 3:(y + 1) * w * 3]

    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('!IIBBBBB', w, h, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    png = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)

bg = (8, 8, 11)
fg = (124, 92, 255)

make_png('public/icons/icon-192.png', 192, bg, fg)
make_png('public/icons/icon-512.png', 512, bg, fg)
make_png('public/icons/icon-512-maskable.png', 512, bg, fg, mark_ratio=0.34)
print('done')
