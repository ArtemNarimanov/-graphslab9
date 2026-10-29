# -*- coding: utf-8 -*-
"""GraphLab Plotter — портативное GUI-приложение.

Выбор .dat файлов (X и Y) из проводника, настройка имён осей, цветов
линий, подписей легенды и строк начала чтения Y для каждой линии,
построение графиков (отдельные или все на одном), сохранение PNG и
готовых строк для Markdown. Предпросмотр — с прокруткой ползунками.

Интерфейс: плоский современный дизайн (единая палитра, карточки,
шрифт Segoe UI). Запуск: GraphLab.exe (или python graphlab_app.py
с matplotlib+Pillow).
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
from tkinter import ttk
from tkinter import colorchooser, filedialog, messagebox

# ---------- палитра и шрифты (плоский дизайн) ----------
C_BG = "#f4f6f8"        # фон окна
C_CARD = "#ffffff"      # карточки
C_TEXT = "#1f2937"      # основной текст
C_MUTED = "#6b7280"     # приглушённый текст
C_ACCENT = "#2563eb"    # акцент (кнопки)
C_ACCENT_HV = "#1d4ed8" # акцент при наведении
C_BORDER = "#e2e8f0"    # границы полей
C_OK = "#16a34a"        # статус успеха
C_ERR = "#dc2626"       # статус ошибки

F_BODY = ("Segoe UI", 9)
F_SMALL = ("Segoe UI", 8)
F_HEAD = ("Segoe UI", 10, "bold")

# цвета линий по умолчанию (данные, не интерфейс)
PALETTE = ["#4682b4", "#e07b39", "#2e8b57", "#c0392b",
           "#8e44ad", "#16a085", "#d4ac0d", "#7f8c8d"]

# общие опции виджетов
E_OPT = dict(bd=0, highlightthickness=1, highlightbackground=C_BORDER,
             highlightcolor=C_ACCENT, bg="white", insertbackground=C_TEXT,
             font=F_BODY)
B_OPT = dict(relief=tk.FLAT, bd=0, bg="#eef2f7", fg=C_TEXT,
             activebackground="#dfe6ee", activeforeground=C_TEXT,
             font=F_SMALL, cursor="hand2")


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


def _style_ax(ax):
    """Единый аккуратный вид оси: без верхних/правых рамок, лёгкая сетка."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(framealpha=0.9)


class YLine:
    """Одна линия графика: файл .dat, цвет, подпись легенды, строка начала Y."""

    def __init__(self, master, app, index):
        self.app = app
        self.path_var = tk.StringVar()
        self.legend_var = tk.StringVar(value=f"линия {index + 1}")
        self.start_var = tk.IntVar(value=4)
        self.color = PALETTE[index % len(PALETTE)]

        self.frame = tk.Frame(master, bg=C_CARD)
        self.frame.pack(fill=tk.X, pady=3)
        self.frame.columnconfigure(0, weight=1)

        self.file_entry = tk.Entry(self.frame, textvariable=self.path_var, **E_OPT)
        self.file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        tk.Button(self.frame, text="...", width=3, command=self._pick_file,
                  **B_OPT).grid(row=0, column=1)
        self.color_btn = tk.Button(self.frame, text="■", width=3, bg=self.color,
                                   fg=self.color, relief=tk.FLAT, bd=0,
                                   font=("Segoe UI", 10), cursor="hand2",
                                   command=self._pick_color)
        self.color_btn.grid(row=0, column=2, padx=(4, 4))
        del_opt = dict(B_OPT)
        del_opt["fg"] = C_ERR
        tk.Button(self.frame, text="✕", width=3, command=self._remove,
                  **del_opt).grid(row=0, column=3)

        self.legend_entry = tk.Entry(self.frame, textvariable=self.legend_var,
                                     width=16, **E_OPT)
        self.legend_entry.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(2, 0))
        tk.Label(self.frame, text="Y с:", bg=C_CARD, fg=C_MUTED, font=F_SMALL).grid(
            row=1, column=1, sticky="w", pady=(2, 0))
        self.start_entry = tk.Entry(self.frame, textvariable=self.start_var,
                                    width=4, **E_OPT)
        self.start_entry.grid(row=1, column=2, padx=(4, 0), pady=(2, 0))

    # --- действия ---
    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Выберите .dat файл для линии",
            filetypes=[("DAT-файлы", "*.dat"), ("Все файлы", "*.*")])
        if not path:
            return
        self.path_var.set(path)
        # подпись легенды — из имени файла, если пользователь её не менял
        base = Path(path).stem
        if self.legend_var.get().startswith("линия "):
            self.legend_var.set(base)

    def _pick_color(self):
        color = colorchooser.askcolor(initialcolor=self.color,
                                      title="Цвет линии")[1]
        if color:
            self.color = color
            self.color_btn.configure(bg=color, fg=color)

    def _remove(self):
        self.frame.destroy()
        self.app.lines.remove(self)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("GraphLab Plotter")
        root.geometry("1160x760")
        root.minsize(1024, 680)
        root.configure(bg=C_BG)

        self.x_file = tk.StringVar()
        self.title_var = tk.StringVar(value="График")
        self.xlabel_var = tk.StringVar(value="X")
        self.ylabel_var = tk.StringVar(value="Y")
        self.out_dir = tk.StringVar(value=app_dir())
        self.combined = tk.BooleanVar(value=False)
        self.combined_name = tk.StringVar(value="combined")
        self.fit_preview = tk.BooleanVar(value=False)
        self.lines = []
        self._photo = None
        self._orig_image = None

        self._build_ui()
        self.add_line()

    # ---------- построение интерфейса ----------
    def _card(self, parent, title: str, row: int, stretch: bool = False):
        """Белая карточка-секция с заголовком; возвращает её frame."""
        card = tk.Frame(parent, bg=C_CARD)
        if stretch:
            card.grid(row=row, column=0, sticky="nsew", pady=(0, 10))
            parent.rowconfigure(row, weight=1)
        else:
            card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(0, weight=1)
        tk.Label(card, text=title.upper(), bg=C_CARD, fg=C_MUTED, font=F_SMALL).grid(
            row=0, column=0, sticky="w", padx=14, pady=(10, 2))
        return card

    def _field_row(self, parent, label: str, var: tk.StringVar, row: int,
                   pick_cmd=None, width: int = None):
        """Строка «подпись + поле ввода (+ кнопка выбора)» внутри карточки."""
        tk.Label(parent, text=label, bg=C_CARD, fg=C_MUTED, font=F_SMALL).grid(
            row=row, column=0, sticky="w", padx=14, pady=(6, 0))
        rowf = tk.Frame(parent, bg=C_CARD)
        rowf.grid(row=row + 1, column=0, sticky="ew", padx=14, pady=(2, 0))
        rowf.columnconfigure(0, weight=1)
        entry = tk.Entry(rowf, textvariable=var, **E_OPT)
        entry.grid(row=0, column=0, sticky="ew")
        if width:
            entry.configure(width=width)
        if pick_cmd:
            tk.Button(rowf, text="Выбрать...", command=pick_cmd, **B_OPT).grid(
                row=0, column=1, padx=(6, 0))
        return entry

    def _build_ui(self):
        root = self.root
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # ---------- левая панель: настройки ----------
        left = tk.Frame(root, bg=C_BG)
        left.grid(row=0, column=0, sticky="ns", padx=(12, 6), pady=12)
        left.columnconfigure(0, weight=1)

        # карточка «Данные» (растягивается по высоте)
        data = self._card(left, "Данные", row=0, stretch=True)
        self._field_row(data, "Файл X (ось абсцисс)", self.x_file, row=1,
                        pick_cmd=self._pick_x)

        tk.Label(data, text="Линии Y", bg=C_CARD, fg=C_MUTED, font=F_SMALL).grid(
            row=3, column=0, sticky="w", padx=14, pady=(12, 2))
        self.lines_frame = tk.Frame(data, bg=C_CARD)
        self.lines_frame.grid(row=4, column=0, sticky="ew", padx=14)
        tk.Button(data, text="+ Добавить линию", command=self.add_line, **B_OPT).grid(
            row=5, column=0, sticky="w", padx=14, pady=(8, 12))

        # карточка «График»
        graph = self._card(left, "График", row=1)
        self._field_row(graph, "Название графика", self.title_var, row=1)
        self._field_row(graph, "Подпись оси X", self.xlabel_var, row=3)
        self._field_row(graph, "Подпись оси Y", self.ylabel_var, row=5)

        tk.Checkbutton(graph, text="Все линии на одном графике",
                       variable=self.combined, command=self._toggle_combined,
                       bg=C_CARD, activebackground=C_CARD, selectcolor="white",
                       font=F_BODY).grid(row=7, column=0, sticky="w", padx=14, pady=(10, 2))
        comb_row = tk.Frame(graph, bg=C_CARD)
        comb_row.grid(row=8, column=0, sticky="ew", padx=14, pady=(0, 12))
        comb_row.columnconfigure(1, weight=1)
        self.combined_lbl = tk.Label(comb_row, text="Имя объединённого:",
                                     bg=C_CARD, fg=C_MUTED, font=F_SMALL,
                                     state=tk.DISABLED)
        self.combined_lbl.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.combined_entry = tk.Entry(comb_row, textvariable=self.combined_name,
                                       width=12, state=tk.DISABLED, **E_OPT)
        self.combined_entry.grid(row=0, column=1, sticky="ew")

        # карточка «Вывод»
        out = self._card(left, "Вывод", row=2)
        self._field_row(out, "Папка для PNG", self.out_dir, row=1,
                        pick_cmd=self._pick_dir)
        tk.Label(out, text="PNG создаются рядом с выбранными .dat файлами, "
                           "если папка не указана явно.",
                 bg=C_CARD, fg=C_MUTED, font=F_SMALL, justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=14, pady=(6, 12))

        # ---------- правая панель: результат ----------
        right = tk.Frame(root, bg=C_BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # верхняя панель: кнопка + статус
        topbar = tk.Frame(right, bg=C_BG)
        topbar.grid(row=0, column=0, sticky="ew")
        self.gen_btn = tk.Button(topbar, text="  Построить графики  ",
                                 bg=C_ACCENT, fg="white",
                                 activebackground=C_ACCENT_HV,
                                 activeforeground="white", relief=tk.FLAT, bd=0,
                                 font=F_HEAD, cursor="hand2", command=self.generate)
        self.gen_btn.pack(side=tk.LEFT, padx=(2, 10), pady=6)
        self.status = tk.Label(topbar, text="", bg=C_BG, fg=C_MUTED, font=F_BODY)
        self.status.pack(side=tk.RIGHT, padx=4)

        # карточка предпросмотра
        prev = tk.Frame(right, bg=C_CARD)
        prev.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        prev.columnconfigure(0, weight=1)
        prev.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(prev, bg="#fbfcfe", highlightthickness=0)
        self.vbar = ttk.Scrollbar(prev, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(prev, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set,
                              xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=(10, 4))
        self.vbar.grid(row=0, column=1, sticky="ns", pady=(10, 4), padx=(0, 8))
        self.hbar.grid(row=1, column=0, sticky="ew", padx=(10, 4), pady=(0, 6))
        self.canvas.bind("<Configure>", lambda e: self._update_preview())
        footer = tk.Frame(prev, bg=C_CARD)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        tk.Checkbutton(footer, text="Вписывать в окно (без прокрутки)",
                       variable=self.fit_preview, command=self._update_preview,
                       bg=C_CARD, activebackground=C_CARD, selectcolor="white",
                       font=F_SMALL).grid(row=0, column=0, sticky="w", padx=(14, 0), pady=(2, 8))

        # карточка Markdown
        md = tk.Frame(right, bg=C_CARD)
        md.grid(row=2, column=0, sticky="ew")
        md.columnconfigure(0, weight=1)
        self.md_text = tk.Text(md, height=4, wrap="none", bd=0, bg="white",
                               fg=C_TEXT, insertbackground=C_TEXT,
                               font=("Consolas", 9), highlightthickness=1,
                               highlightbackground=C_BORDER)
        self.md_text.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=(12, 12))
        side = tk.Frame(md, bg=C_CARD)
        side.grid(row=0, column=1, sticky="ns", padx=(0, 10))
        tk.Button(side, text="Копировать в буфер", command=self._copy_md, **B_OPT).pack(pady=3)
        tk.Button(side, text="Открыть папку", command=self._open_outdir, **B_OPT).pack(pady=3)

    # ---------- действия ----------
    def add_line(self):
        self.lines.append(YLine(self.lines_frame, self, len(self.lines)))

    def _toggle_combined(self):
        """Включает/выключает поле имени объединённого графика."""
        state = tk.NORMAL if self.combined.get() else tk.DISABLED
        self.combined_entry.configure(state=state)
        self.combined_lbl.configure(state=state,
                                    fg=C_TEXT if state == tk.NORMAL else C_MUTED)

    def _pick_x(self):
        path = filedialog.askopenfilename(
            title="Выберите .dat файл оси X",
            filetypes=[("DAT-файлы", "*.dat"), ("Все файлы", "*.*")])
        if path:
            self.x_file.set(path)

    def _pick_dir(self):
        d = filedialog.askdirectory(title="Папка для PNG файлов")
        if d:
            self.out_dir.set(d)

    def generate(self):
        """Строит графики, сохраняет PNG и строки Markdown."""
        x_path = self.x_file.get().strip()
        if not x_path or not os.path.isfile(x_path):
            messagebox.showerror("Ошибка", "Выберите существующий .dat файл X.")
            return
        prepared = []
        for ln in self.lines:
            p = ln.path_var.get().strip()
            if not p or not os.path.isfile(p):
                continue
            start = max(1, int(ln.start_var.get()))
            xs = read_numbers(x_path)
            ys = read_numbers(p, start_line=start)
            n = min(len(xs), len(ys))
            if n == 0:
                continue
            prepared.append((xs[:n], ys[:n], ln.color, ln.legend_var.get()))
        if not prepared:
            messagebox.showerror("Ошибка", "Нет данных: укажите файлы X и Y.")
            return

        out_dir = self.out_dir.get().strip() or os.path.dirname(x_path)
        os.makedirs(out_dir, exist_ok=True)
        md_lines = []
        title = self.title_var.get().strip() or "График"
        xlabel = self.xlabel_var.get().strip()
        ylabel = self.ylabel_var.get().strip()

        if self.combined.get():
            fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
            for xs, ys, color, label in prepared:
                ax.plot(xs, ys, color=color, linewidth=2, label=label)
            ax.set_title(title)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            _style_ax(ax)
            name = safe_name(self.combined_name.get()) + ".png"
            path = os.path.join(out_dir, name)
            fig.savefig(path)
            plt.close(fig)
            md_lines.append(f"![{title}]({name})")
        else:
            for xs, ys, color, label in prepared:
                fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
                ax.plot(xs, ys, color=color, linewidth=2, label=label)
                ax.set_title(f"{title} — {label}")
                ax.set_xlabel(xlabel)
                ax.set_ylabel(ylabel)
                _style_ax(ax)
                fname = safe_name(label) + ".png"
                path = os.path.join(out_dir, fname)
                fig.savefig(path)
                plt.close(fig)
                md_lines.append(f"![{label}]({fname})")

        self.md_text.delete("1.0", "end")
        self.md_text.insert("1.0", "\n".join(md_lines))
        self._show_preview(out_dir, prepared, title, xlabel, ylabel)
        self.status.configure(text=f"Сохранено: {len(md_lines)} PNG в {out_dir}",
                              foreground=C_OK)
        messagebox.showinfo("GraphLab", f"Готово. PNG сохранены в:\n{out_dir}")

    # ---------- предпросмотр ----------
    def _show_preview(self, out_dir, prepared, title, xlabel, ylabel):
        """Сохраняет картинку для предпросмотра (последний построенный график)."""
        if self.combined.get():
            name = safe_name(self.combined_name.get()) + ".png"
        else:
            name = safe_name(prepared[-1][3]) + ".png"
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            return
        img = Image.open(path)
        self._orig_image = img.copy()
        self._update_preview()

    def _update_preview(self):
        """Перерисовывает предпросмотр с учётом галочки «вписать в окно»."""
        if self._orig_image is None:
            return
        img = self._orig_image
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if self.fit_preview.get() and w > 40 and h > 40:
            scale = min((w - 20) / img.width, (h - 20) / img.height, 1.0)
        else:
            scale = 1.0
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
        self.status.configure(text="Markdown скопирован в буфер обмена",
                              foreground=C_OK)

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
