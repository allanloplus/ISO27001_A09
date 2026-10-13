# -*- coding: utf-8 -*-
"""從角色設定圖裁切講師與助教的半身像，並去除白色背景（輸出透明 PNG）。

用法：python3 src/make_sprites.py
輸入：assets/characters/allan_sheet.jpg、arale_sheet.jpg（使用者提供的角色設定圖）
輸出：presentation/sprites/{allan,arale}.png（閉嘴待機）、{allan,arale}_open.png（說話張嘴）
"""
import os
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "characters")
OUT = os.path.join(ROOT, "presentation", "sprites")

HEIGHT = 500  # 輸出高度（舞台顯示約 250px，影片 1.5 倍仍清晰）
INK = (38, 22, 22)


def allan_open(im):
    """原圖為閉嘴微笑；畫出張嘴的說話嘴型。"""
    d = ImageDraw.Draw(im)
    d.pieslice((254, 270, 334, 322), 0, 180, fill=(122, 36, 42), outline=INK, width=4)
    d.pieslice((274, 302, 314, 324), 180, 360, fill=(236, 122, 128))
    d.rectangle((266, 295, 322, 299), fill=(255, 255, 255))
    d.line((256, 295, 332, 295), fill=INK, width=4)
    return im


def arale_closed(im):
    """原圖為張嘴笑；以周圍膚色（柔邊）蓋住嘴巴並畫上閉嘴微笑。"""
    px = im.convert("RGB")
    ring = [px.getpixel((x, y)) for x, y in ((160, 188), (222, 188), (190, 208), (170, 204), (212, 204))]
    skin = tuple(sum(c[i] for c in ring) // len(ring) for i in range(3))
    patch = Image.new("L", im.size, 0)
    ImageDraw.Draw(patch).ellipse((162, 170, 220, 206), fill=255)
    patch = patch.filter(ImageFilter.GaussianBlur(3))
    im = Image.composite(Image.new("RGBA", im.size, skin + (255,)), im, patch)
    # 以 4 倍解析度畫弧線再縮小，邊緣較平滑
    big = Image.new("RGBA", (im.width * 4, im.height * 4), (0, 0, 0, 0))
    ImageDraw.Draw(big).arc((172 * 4, 164 * 4, 210 * 4, 192 * 4), 22, 158, fill=INK + (255,), width=13)
    return Image.alpha_composite(im, big.resize(im.size, Image.LANCZOS))


# (來源檔, 裁切框 left, top, right, bottom, 名稱, 原圖嘴型, 產生另一嘴型的函式)
SPRITES = [
    ("allan_sheet.jpg", (60, 80, 770, 840), "allan", "closed", allan_open),   # 正面單張：上半身、手勢指向右側
    ("arale_sheet.jpg", (60, 790, 420, 1190), "arale", "open", arale_closed),  # 揮手姿勢：上半身
]


def cut_background(img, thresh=232):
    """從邊緣做洪水填充，把與外框相連的近白色區域變透明（衣服、名牌內的白色保留）。"""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    h, w, _ = a.shape
    white = (a.min(axis=2) >= thresh) & ((a.max(axis=2) - a.min(axis=2)) < 22)
    bg = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True; q.append((ny, nx))
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))  # 收邊去白邊
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    for src, box, name, base_mouth, paint in SPRITES:
        img = cut_background(Image.open(os.path.join(SRC, src)).crop(box))
        if name == "allan":  # 去掉右下角混入的「表情包」標題字
            img.paste((0, 0, 0, 0), (690, 630, img.width, img.height))
        alt = paint(img.copy())
        frames = {base_mouth: img, ("open" if base_mouth == "closed" else "closed"): alt}
        for mouth, im in frames.items():
            w = round(im.width * HEIGHT / im.height)
            im = im.resize((w, HEIGHT), Image.LANCZOS)
            fn = f"{name}.png" if mouth == "closed" else f"{name}_open.png"
            im.save(os.path.join(OUT, fn), optimize=True)
            print(fn, im.size)


if __name__ == "__main__":
    main()
