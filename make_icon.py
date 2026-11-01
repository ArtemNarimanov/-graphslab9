# -*- coding: utf-8 -*-
"""Генерирует GraphLab.ico — синяя скруглённая плашка с белым графиком."""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Фон: синяя скруглённая плашка
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=56, fill=(37, 99, 235, 255))

# Оси (белые, полупрозрачные)
axis = (255, 255, 255, 200)
d.line([56, 48, 56, 196], fill=(255, 255, 255, 255), width=10)   # Y
d.line([56, 196, 208, 196], fill=(255, 255, 255, 255), width=10)  # X

# Линия графика
pts = [(72, 168), (108, 120), (140, 140), (172, 84), (196, 96)]
d.line(pts, fill=(255, 255, 255, 255), width=14, joint="curve")

# Точки на линии
for x, y in pts:
    r = 10
    d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))

img.save("GraphLab.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("GraphLab.ico written")
