# -*- coding: utf-8 -*-
"""Читает .dat файлы (X и Y) и рисует графики, готовые к вставке в Markdown.

Использование:
    python graph.py [x_file] [y_file ...]

По умолчанию:
    X  = x.dat                (числа через ; или пробелы)
    Y  = result_tav.dat, result_tw1.dat, result_tw2.dat
       (читаются с 4-й строки; первые 3 строки — заголовок и начальные значения)

Результат для каждого Y-файла:
    <имя>.png — картинка (result_tav.png, result_tw1.png, result_tw2.png)
    на stdout — строка ![...](<имя>.png) для вставки в Markdown
"""

import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # рендер без окна (работает и на сервере, и в CI)
import matplotlib.pyplot as plt

# --- Настройки по умолчанию ---
X_FILE = "x.dat"
Y_FILES = [
    "result_tav.dat",
    "result_tw1.dat",
    "result_tw2.dat",
]

# С какой строки (нумерация с 1) читать значения Y.
# Строки 1-3 в наших .dat: заголовок и начальные значения — пропускаем.
Y_START_LINE = 4


def read_numbers(path, start_line=1):
    """Читает числа из файла, начиная с `start_line` (нумерация с 1).

    Понимает разделители: пробелы, табы, точки с запятой.
    Поддерживает экспоненциальную запись вида 3.9211E+02 и CRLF.
    """
    values = []
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            if lineno < start_line:
                continue  # пропускаем заголовок и начальные строки
            tokens = re.split(r"[;\s]+", line.strip())
            for tok in tokens:
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    values.append(float(tok))
                except ValueError:
                    pass  # нечисловой токен — игнорируем
    return values


def make_graph(x, y, png_file, title):
    """Рисует один график и сохраняет его в PNG."""
    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111)
    ax.plot(x, y, marker="o", linewidth=1.5, markersize=4,
            color="steelblue", label=title)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_file, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    args = sys.argv[1:]
    x_file = args[0] if len(args) > 0 else X_FILE
    y_files = args[1:] if len(args) > 1 else Y_FILES

    x = read_numbers(x_file)
    if not x:
        sys.exit(f"Не удалось прочитать ни одной точки из '{x_file}'.")

    for y_file in y_files:
        stem = Path(y_file).stem                        # result_tw1 -> result_tw1
        title = stem.replace("result_", "").upper()     # TAV, TW1, TW2
        png_file = f"{stem}.png"

        y = read_numbers(y_file, start_line=Y_START_LINE)
        n = min(len(x), len(y))
        if n == 0:
            print(f"Внимание: в '{y_file}' нет точек — пропускаю.", file=sys.stderr)
            continue
        if len(x) != len(y):
            print(f"Внимание: {y_file}: X={len(x)}, Y={len(y)} — беру {n} точек.",
                  file=sys.stderr)

        make_graph(x[:n], y[:n], png_file, title)
        print(f"{y_file}: {n} точек -> {png_file}")
        print(f"![{title}]({png_file})")


if __name__ == "__main__":
    main()
