# -*- coding: utf-8 -*-
"""GraphLab Plotter — портативное GUI-приложение.

Выбор .dat файлов (X и Y) из проводника, настройка имён осей, цветов
линий, подписей легенды и строк начала чтения Y для каждой линии,
построение графиков (отдельные или все на одном), сохранение PNG и
готовых строк для Markdown. Предпросмотр — с прокруткой ползунками.

Запуск: GraphLab.exe (или python graphlab_app.py с matplotlib+Pillow).
"""

import os
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

PALETTE = ["#4682b4", "#e07b39", "#2e8b57", "#c0392b",
           "#8e44ad", "#16a085", "#d4ac0d", "#7f8c8d"]


def app_dir() -> str:
    """Папка приложения (для exe — папка с exe, для скрипта — папка скрипта)."""
    if getattr(sys, "frozen", False):  # собран PyInstaller'ом
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def read_numbers(path: str, start_line: int = 1):
    """Читает числа из .dat, начиная с `start_line` (нумерация с 1).

    Разделители: пробелы, табы, точки с запятой. Понимает запись вида
    3.9211E+02 и CRLF. Нечисловые токены игнорируются.
    """
    values = []
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            if lineno < start_line:
                continue
            for tok in re.split(r"[;\s]+", line.strip()):
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    values.append(float(tok))
                except ValueError:
                    pass
    return values


def safe_name(name: str) -> str:
    """Делает строку безопасной для имени файла."""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "graph"


class YLine:
    """Одна линия графика: файл .dat, цвет, подпись легенды, строка начала Y."""

    def __init__(self, master, app, index):
        self.app = app
        self.path_var = tk.StringVar()
        self.legend_var = tk.StringVar(value=f"линия {index + 1}")
        self.start_var = tk.IntVar(value=4)
        self.color = PALETTE[index % len(PALETTE)]

        self.frame = tk.Frame(master)
        self.frame.pack(fill=tk.X, pady=2)

        self.file_entry = tk.Entry(self.frame, textvariable=self.path_var, width=30)
        self.file_entry.pack(side=tk.LEFT)
        tk.Button(self.frame, text="...", width=3, command=self._pick_file).pack(
            side=tk.LEFT, padx=3)

        self.color_btn = tk.Button(self.frame, text="■", width=3, bg=self.color,
                                   fg=self.color, relief=tk.FLAT,
                                   command=self._pick_color)
        self.color_btn.pack(side=tk.LEFT, padx=3)

        self.legend_entry = tk.Entry(self.frame, textvariable=self.legend_var, width=14)
        self.legend_entry.pack(side=tk.LEFT, padx=3)

        # строка начала чтения Y для этой линии
        tk.Label(self.frame, text="Y с:").pack(side=tk.LEFT, padx=(8, 2))
        self.start_entry = tk.Entry(self.frame, textvariable=self.start_var, width=4)
        self.start_entry.pack(side=tk.LEFT, padx=(0, 3))

        tk.Button(self.frame, text="✕", width=3, command=self._remove).pack(side=tk.RIGHT)

    # --- действия ---
    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Выберите .dat файл для линии",
            filetypes=[("DAT-файлы", "*.dat"), ("Все файлы", "*.*")])
        if not path:
            return
        self.path_var.set(path)
        # автоподпись легенды из имени файла, если пользователь её не менял
        cur = self.legend_var.get().strip()
        if not cur or re.fullmatch(r"линия \d+", cur):
            self.legend_var.set(Path(path).stem.replace("result_", "").upper())

    def _pick_color(self):
        result = colorchooser.askcolor(initialcolor=self.color, title="Цвет линии")
        if result and result[1]:
            self.color = result[1]
            self.color_btn.configure(bg=self.color, fg=self.color)

    def _remove(self):
        self.app.lines.remove(self)
        self.frame.destroy()

    # --- доступ к данным ---
    @property
    def path(self):
        return self.path_var.get().strip()

    @property
    def legend(self):
        label = self.legend_var.get().strip()
        return label if label else Path(self.path).stem

    @property
    def start_line(self):
        try:
            return max(1, int(self.start_var.get()))
        except (tk.TclError, ValueError):
            return 4


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GraphLab Plotter")
        self.root.minsize(860, 720)

        self.x_file = tk.StringVar()
        self.title_var = tk.StringVar(value="График")
        self.xlabel_var = tk.StringVar(value="X")
        self.ylabel_var = tk.StringVar(value="Y")
        self.out_dir = tk.StringVar(value=app_dir())
        self.combined = tk.BooleanVar(value=False)
        self.combined_name = tk.StringVar(value="combined")
        self.fit_preview = tk.BooleanVar(value=False)
        self.lines = []
        self._photo = None       # текущий PhotoImage (удерживаем ссылку)
        self._orig_image = None  # исходный PIL-изображение для предпросмотра

        self._build_ui()
        self.add_line()

    # ---------- интерфейс ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # X файл
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, **pad)
        tk.Label(top, text="Файл X:").grid(row=0, column=0, sticky="e", padx=(0, 6))
        tk.Entry(top, textvariable=self.x_file, width=52).grid(row=0, column=1, sticky="ew")
        tk.Button(top, text="Выбрать...", command=self._pick_x).grid(row=0, column=2, padx=(6, 0))
        top.columnconfigure(1, weight=1)

        # линии Y
        lines_box = tk.Frame(self.root)
        lines_box.pack(fill=tk.X, **pad)
        head = tk.Frame(lines_box)
        head.pack(fill=tk.X)
        tk.Label(head, text="Линии Y (файл / цвет / подпись легенды / строка начала Y):").pack(side=tk.LEFT)
        self.lines_frame = tk.Frame(lines_box)
        self.lines_frame.pack(fill=tk.X)

        ctrl = tk.Frame(lines_box)
        ctrl.pack(fill=tk.X, pady=(4, 0))
        tk.Button(ctrl, text="+ Добавить линию", command=self.add_line).pack(side=tk.LEFT)
        tk.Checkbutton(ctrl, text="Все линии на одном графике",
                       variable=self.combined).pack(side=tk.LEFT, padx=16)
        self.combined_lbl = tk.Label(ctrl, text="Имя объединённого графика:", state=tk.DISABLED)
        self.combined_lbl.pack(side=tk.LEFT)
        self.combined_entry = tk.Entry(ctrl, textvariable=self.combined_name, width=14,
                                       state=tk.DISABLED)
        self.combined_entry.pack(side=tk.LEFT, padx=(4, 0))

        # параметры
        opts = tk.Frame(self.root)
        opts.pack(fill=tk.X, **pad)
        tk.Label(opts, text="Название графика:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        tk.Entry(opts, textvariable=self.title_var, width=30).grid(row=0, column=1, sticky="ew", pady=4)
        tk.Label(opts, text="Ось X:").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        tk.Entry(opts, textvariable=self.xlabel_var, width=30).grid(row=1, column=1, sticky="ew", pady=4)
        tk.Label(opts, text="Ось Y:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=4)
        tk.Entry(opts, textvariable=self.ylabel_var, width=30).grid(row=2, column=1, sticky="ew", pady=4)
        opts.columnconfigure(1, weight=1)

        # папка вывода
        out = tk.Frame(self.root)
        out.pack(fill=tk.X, **pad)
        tk.Label(out, text="Папка для PNG:").grid(row=0, column=0, sticky="e", padx=(0, 6))
        tk.Entry(out, textvariable=self.out_dir, width=52).grid(row=0, column=1, sticky="ew")
        tk.Button(out, text="Выбрать...", command=self._pick_dir).grid(row=0, column=2, padx=(6, 0))
        out.columnconfigure(1, weight=1)

        # кнопки
        btns = tk.Frame(self.root)
        btns.pack(fill=tk.X, **pad)
        tk.Button(btns, text="Построить графики", command=self.generate).pack(side=tk.LEFT, padx=8)
        self.status = tk.Label(btns, text="", foreground="gray")
        self.status.pack(side=tk.LEFT, padx=12)

        # предпросмотр с ползунками
        prev = tk.Frame(self.root)
        prev.pack(fill=tk.BOTH, expand=True, **pad)
        prev.grid_columnconfigure(0, weight=1)
        prev.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(prev, bg="#f5f5f5", highlightthickness=0)
        self.vbar = tk.Scrollbar(prev, orient="vertical", command=self.canvas.yview)
        self.hbar = tk.Scrollbar(prev, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<Configure>", lambda e: self._update_preview())

        prev_ctrl = tk.Frame(self.root)
        prev_ctrl.pack(fill=tk.X, padx=8)
        tk.Checkbutton(prev_ctrl, text="Вписывать в окно (без прокрутки)",
                       variable=self.fit_preview,
                       command=self._update_preview).pack(side=tk.LEFT)

        # markdown
        md = tk.Frame(self.root)
        md.pack(fill=tk.X, **pad)
        self.md_text = tk.Text(md, height=4, wrap="none")
        self.md_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        side = tk.Frame(md)
        side.pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(side, text="Копировать в буфер", command=self._copy_md).pack(pady=2)
        tk.Button(side, text="Открыть папку", command=self._open_outdir).pack(pady=2)

    def add_line(self):
        self.lines.append(YLine(self.lines_frame, self, len(self.lines)))

    # ---------- выбор файлов ----------
    def _pick_x(self):
        path = filedialog.askopenfilename(
            title="Выберите .dat файл оси X",
            filetypes=[("DAT-файлы", "*.dat"), ("Все файлы", "*.*")])
        if path:
            self.x_file.set(path)

    def _pick_dir(self):
        d = filedialog.askdirectory(title="Папка для PNG",
                                    initialdir=self.out_dir.get() or app_dir())
        if d:
            self.out_dir.set(d)

    # ---------- построение ----------
    def generate(self):
        x_file = self.x_file.get().strip()
        if not x_file or not os.path.isfile(x_file):
            messagebox.showerror("Ошибка", "Выберите существующий файл X.")
            return
        rows = [ln for ln in self.lines if ln.path and os.path.isfile(ln.path)]
        if not rows:
            messagebox.showerror("Ошибка", "Добавьте хотя бы одну линию с .dat файлом Y.")
            return

        out_dir = self.out_dir.get().strip() or app_dir()
        os.makedirs(out_dir, exist_ok=True)

        try:
            x = read_numbers(x_file)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось читать {x_file}:\n{e}")
            return
        if not x:
            messagebox.showerror("Ошибка", f"В {x_file} не найдено ни одного числа.")
            return

        title = self.title_var.get().strip() or "График"
        md_lines = []
        last_png = None

        if self.combined.get():
            # все линии на одном графике
            png_name = safe_name(self.combined_name.get()) + ".png"
            png_path = os.path.join(out_dir, png_name)
            fig = plt.figure(figsize=(10, 6))
            ax = fig.add_subplot(111)
            plotted = 0
            for ln in rows:
                y = read_numbers(ln.path, start_line=ln.start_line)
                n = min(len(x), len(y))
                if n == 0:
                    self.status.configure(text=f"Нет точек в {ln.path}", foreground="red")
                    continue
                ax.plot(x[:n], y[:n], marker="o", linewidth=1.5, markersize=4,
                        color=ln.color, label=ln.legend)
                plotted += 1
            if plotted == 0:
                plt.close(fig)
                messagebox.showerror("Ошибка", "Не удалось построить ни одной линии.")
                return
            ax.set_xlabel(self.xlabel_var.get().strip() or "X")
            ax.set_ylabel(self.ylabel_var.get().strip() or "Y")
            ax.set_title(title)
            ax.grid(True, linestyle="--", alpha=0.4)
            ax.legend()
            fig.tight_layout()
            fig.savefig(png_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            md_lines.append(f"![{title}]({png_name})")
            last_png = png_path
            self.status.configure(text=f"{png_name}: {plotted} линий", foreground="green")
        else:
            # отдельный график на каждый файл
            for ln in rows:
                stem = Path(ln.path).stem
                png_name = f"{stem}.png"
                png_path = os.path.join(out_dir, png_name)

                y = read_numbers(ln.path, start_line=ln.start_line)
                n = min(len(x), len(y))
                if n == 0:
                    self.status.configure(text=f"Нет точек в {ln.path}", foreground="red")
                    continue

                fig = plt.figure(figsize=(10, 6))
                ax = fig.add_subplot(111)
                ax.plot(x[:n], y[:n], marker="o", linewidth=1.5, markersize=4,
                        color=ln.color, label=ln.legend)
                ax.set_xlabel(self.xlabel_var.get().strip() or "X")
                ax.set_ylabel(self.ylabel_var.get().strip() or "Y")
                ax.set_title(title)
                ax.grid(True, linestyle="--", alpha=0.4)
                ax.legend()
                fig.tight_layout()
                fig.savefig(png_path, dpi=150, bbox_inches="tight")
                plt.close(fig)

                md_lines.append(f"![{title}]({png_name})")
                last_png = png_path
                self.status.configure(text=f"{png_name}: {n} точек", foreground="green")

        if not md_lines:
            messagebox.showerror("Ошибка", "Не получилось построить ни один график.")
            return

        self.md_text.delete("1.0", tk.END)
        self.md_text.insert("1.0", "\n".join(md_lines))
        if last_png:
            self._show_preview(last_png)
        messagebox.showinfo(
            "Готово",
            f"Создано графиков: {len(md_lines)}\nПапка: {out_dir}\n\n"
            "Строки для Markdown в поле ниже.")

    # ---------- предпросмотр ----------
    def _show_preview(self, png_path: str):
        self._orig_image = Image.open(png_path)
        self._update_preview()

    def _update_preview(self):
        if self._orig_image is None:
            return
        img = self._orig_image
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if self.fit_preview.get() and w > 50 and h > 50:
            scale = min(w / img.width, h / img.height)
            if scale < 1.0:
                img = img.resize((max(1, int(img.width * scale)),
                                  max(1, int(img.height * scale))))
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(10, 10, anchor="nw", image=self._photo)
        if not self.fit_preview.get():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _copy_md(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.md_text.get("1.0", "end-1c"))
        self.status.configure(text="Markdown скопирован в буфер обмена", foreground="green")

    def _open_outdir(self):
        d = self.out_dir.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)  # только Windows


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
