# -*- coding: utf-8 -*-
"""GraphLab Plotter — портативное GUI-приложение.

Выбор .dat файлов (X и Y) из проводника, настройка имён осей, цветов линий,
подписей легенды и строк начала чтения для каждой линии (у линии может быть
свой X), построение графиков (отдельные или все на одном), сохранение PNG и
готовых строк для Markdown. Числа можно вставить прямо в поле без .dat.
Проекты .gslab с автосохранением, предпросмотр вкладками.

Интерфейс: плоский современный дизайн (карточки, шрифт Segoe UI), светлая тема.
Запуск: GraphLab.exe (или python graphlab_app.py с matplotlib+Pillow).
"""

import json
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

# ---------- цвета интерфейса (плоский светлый дизайн) ----------
T = dict(bg="#f4f6f8", card="#ffffff", text="#1f2937", muted="#6b7280",
         accent="#2563eb", accent_hv="#1d4ed8", border="#e2e8f0",
         ok="#16a34a", err="#dc2626", entry_bg="#ffffff",
         btn_bg="#eef2f7", btn_hover="#dfe6ee")

F_BODY = ("Segoe UI", 9)
F_SMALL = ("Segoe UI", 8)
F_HEAD = ("Segoe UI", 10, "bold")

# цвета линий по умолчанию (данные, не интерфейс)
PALETTE = ["#4682b4", "#e07b39", "#2e8b57", "#c0392b",
           "#8e44ad", "#16a085", "#d4ac0d", "#7f8c8d"]


def app_dir() -> str:
    """Папка приложения (для exe — папка с exe, для скрипта — папка скрипта)."""
    if getattr(sys, "frozen", False):  # собран PyInstaller'ом
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def user_dir() -> str:
    """Папка %APPDATA%/GraphLab для config.json и last.gslab."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "GraphLab")
    os.makedirs(d, exist_ok=True)
    return d


def parse_numbers(text: str):
    """Разбирает числа из строки.

    Разделители: пробелы, табы, точки с запятой, запятые. Понимает запись
    вида 3.9211E+02 и CRLF. Нечисловые токены игнорируются.
    """
    values = []
    for tok in re.split(r"[;\s,]+", text):
        tok = tok.strip()
        if not tok:
            continue
        try:
            values.append(float(tok))
        except ValueError:
            pass
    return values


def read_numbers(path: str, start_line: int = 1):
    """Читает числа из .dat, начиная с `start_line` (нумерация с 1).

    Обёртка над parse_numbers: читает файл и разбирает его текст.
    """
    with open(path, encoding="utf-8-sig") as f:
        text = "\n".join(
            line for i, line in enumerate(f, start=1) if i >= start_line
        )
    return parse_numbers(text)


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
    """Одна линия графика: файл/числа Y, свой X (необязательно), цвет, подпись
    легенды, строки начала чтения Y и X."""

    def __init__(self, master, app, index):
        self.app = app
        self.path_var = tk.StringVar()
        self.legend_var = tk.StringVar(value=f"линия {index + 1}")
        self.start_var = tk.StringVar(value="4")
        self.x_path_var = tk.StringVar()
        self.x_start_var = tk.StringVar(value="1")
        self.color = PALETTE[index % len(PALETTE)]

        T = app.T
        self.frame = tk.Frame(master, bg=T["card"])
        self.frame.pack(fill=tk.X, pady=3)
        self.frame.columnconfigure(0, weight=1)

        # ряд 0: файл Y + «...» + цвет + удалить
        self.file_entry = app._entry(self.frame, self.path_var)
        self.file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        pick_btn = app._btn(self.frame, "...", self._pick_file)
        pick_btn.grid(row=0, column=1)
        self.color_btn = tk.Button(self.frame, text="■", width=3, bg=self.color,
                                   fg=self.color, relief=tk.FLAT, bd=0,
                                   font=("Segoe UI", 10), cursor="hand2",
                                   command=self._pick_color)
        self.color_btn.grid(row=0, column=2, padx=(4, 4))
        self.del_btn = tk.Button(self.frame, text="✕", width=3, fg=T["err"],
                                 relief=tk.FLAT, bd=0, bg=T["btn_bg"],
                                 activebackground=T["btn_hover"],
                                 activeforeground=T["err"], font=F_SMALL,
                                 cursor="hand2", command=self._remove)
        self.del_btn.grid(row=0, column=3)

        # ряд 1: подпись легенды + «Y с:»
        self.legend_entry = app._entry(self.frame, self.legend_var, width=16)
        self.legend_entry.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(2, 0))
        y_lbl = app._muted_label(self.frame, "Y с:")
        y_lbl.grid(row=1, column=1, sticky="w", pady=(2, 0))
        self.start_entry = app._entry(self.frame, self.start_var, width=4)
        self.start_entry.grid(row=1, column=2, padx=(4, 0), pady=(2, 0))

        # ряд 2: подпись «Свой X (необязательно)»
        xcap = app._muted_label(self.frame, "Свой X (необязательно)")
        xcap.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # ряд 3: свой X + «...» + «X с:»
        self.x_entry = app._entry(self.frame, self.x_path_var)
        self.x_entry.grid(row=3, column=0, sticky="ew", padx=(0, 4), pady=(2, 0))
        xpick = app._btn(self.frame, "...", self._pick_x_line)
        xpick.grid(row=3, column=1, pady=(2, 0))
        xs_lbl = app._muted_label(self.frame, "X с:")
        xs_lbl.grid(row=3, column=2, sticky="w", padx=(4, 0), pady=(2, 0))
        self.x_start_entry = app._entry(self.frame, self.x_start_var, width=4)
        self.x_start_entry.grid(row=3, column=3, padx=(4, 0), pady=(2, 0))

    # --- действия ---
    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Выберите .dat файл для линии (или вставьте числа в поле)",
            filetypes=[("DAT-файлы", "*.dat"), ("Все файлы", "*.*")])
        if not path:
            return
        self.path_var.set(path)
        # подпись легенды — из имени файла, если пользователь её не менял
        base = Path(path).stem
        if self.legend_var.get().startswith("линия "):
            self.legend_var.set(base)

    def _pick_x_line(self):
        path = filedialog.askopenfilename(
            title="Выберите свой .dat файл X для линии",
            filetypes=[("DAT-файлы", "*.dat"), ("Все файлы", "*.*")])
        if path:
            self.x_path_var.set(path)

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

        self.T = T
        self._status_kind = "info"
        self._ctx_target = None
        self.ctx_menu = None

        self.x_file = tk.StringVar()
        self.title_var = tk.StringVar(value="График")
        self.xlabel_var = tk.StringVar(value="X")
        self.ylabel_var = tk.StringVar(value="Y")
        self.out_dir = tk.StringVar(value=app_dir())
        self.combined = tk.BooleanVar(value=False)
        self.combined_name = tk.StringVar(value="combined")
        self.fit_preview = tk.BooleanVar(value=False)
        self.lines = []
        self._line_counter = 0       # индекс палитры (не сбрасывается при удалении)
        self._preview_tabs = []

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_menu()
        self._build_ui()
        self.add_line()
        self._restore_state()

    # ---------- вспомогательное создание виджетов ----------
    def _reg(self, w, role="field"):
        """Поля (role="field") получают контекстное меню по ПКМ."""
        if role == "field" and self.ctx_menu is not None:
            def handler(e, w=w):
                self._ctx_target = w
                self.ctx_menu.post(e.x_root, e.y_root)
            w.bind("<Button-3>", handler)
        return w

    def _entry(self, parent, var, **kw):
        e = tk.Entry(parent, textvariable=var, bg=self.T["entry_bg"], fg=self.T["text"],
                     insertbackground=self.T["text"], highlightthickness=1,
                     highlightbackground=self.T["border"], highlightcolor=self.T["accent"],
                     font=F_BODY, **kw)
        return self._reg(e, "field")

    def _btn(self, parent, text, command, **kw):
        b = tk.Button(parent, text=text, command=command, relief=tk.FLAT, bd=0,
                      bg=self.T["btn_bg"], fg=self.T["text"],
                      activebackground=self.T["btn_hover"],
                      activeforeground=self.T["text"], font=F_SMALL, cursor="hand2", **kw)
        return self._reg(b, "btn")

    def _muted_label(self, parent, text, **kw):
        lab = tk.Label(parent, text=text, bg=self.T["card"], fg=self.T["muted"],
                       font=F_SMALL, **kw)
        return self._reg(lab, "label_muted")

    # ---------- меню ----------
    def _build_menu(self):
        root = self.root
        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Открыть проект…", command=self._menu_open_project)
        file_menu.add_command(label="Сохранить проект…", command=self._menu_save_project)
        file_menu.add_separator()
        file_menu.add_command(label="Выйти", command=self._on_close)
        menubar.add_cascade(label="Файл", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        for label, ev in [("Вырезать", "<<Cut>>"), ("Копировать", "<<Copy>>"),
                          ("Вставить", "<<Paste>>"), ("Выделить всё", "<<SelectAll>>")]:
            edit_menu.add_command(label=label,
                                  command=lambda e=ev: self._focus_event(e))
        menubar.add_cascade(label="Правка", menu=edit_menu)
        root.config(menu=menubar)

        # ускорители Ctrl+X/C/V/A — генерируют виртуальные события на виджете с фокусом
        for key, ev in [("x", "<<Cut>>"), ("c", "<<Copy>>"),
                        ("v", "<<Paste>>"), ("a", "<<SelectAll>>")]:
            root.bind_all(f"<Control-KeyPress-{key}>",
                          lambda e, ev=ev: self._focus_event(ev))

        # контекстное меню по ПКМ для всех Entry/Text
        self.ctx_menu = tk.Menu(root, tearoff=0)
        for label, ev in [("Вырезать", "<<Cut>>"), ("Копировать", "<<Copy>>"),
                          ("Вставить", "<<Paste>>"), ("Выделить всё", "<<SelectAll>>")]:
            self.ctx_menu.add_command(label=label,
                                      command=lambda e=ev: self._ctx_event(e))

    def _focus_event(self, ev):
        w = self.root.focus_get()
        if w is not None:
            w.event_generate(ev)

    def _ctx_event(self, ev):
        if self._ctx_target is not None:
            self._ctx_target.event_generate(ev)

    # ---------- построение интерфейса ----------
    def _card(self, parent, title: str, row: int, stretch: bool = False):
        """Карточка-секция с заголовком; возвращает её frame."""
        card = tk.Frame(parent, bg=self.T["card"])
        if stretch:
            card.grid(row=row, column=0, sticky="nsew", pady=(0, 10))
            parent.rowconfigure(row, weight=1)
        else:
            card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(0, weight=1)
        self._reg(card, "card")
        self._muted_label(card, title.upper()).grid(
            row=0, column=0, sticky="w", padx=14, pady=(10, 2))
        return card

    def _field_row(self, parent, label: str, var: tk.StringVar, row: int,
                   pick_cmd=None, width: int = None):
        """Строка «подпись + поле ввода (+ кнопка выбора)» внутри карточки."""
        self._muted_label(parent, label).grid(
            row=row, column=0, sticky="w", padx=14, pady=(6, 0))
        rowf = tk.Frame(parent, bg=self.T["card"])
        rowf.grid(row=row + 1, column=0, sticky="ew", padx=14, pady=(2, 0))
        rowf.columnconfigure(0, weight=1)
        self._reg(rowf, "card")
        entry = self._entry(rowf, var)
        entry.grid(row=0, column=0, sticky="ew")
        if width:
            entry.configure(width=width)
        if pick_cmd:
            self._btn(rowf, "Выбрать...", pick_cmd).grid(row=0, column=1, padx=(6, 0))
        return entry

    def _build_ui(self):
        root = self.root
        T = self.T
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # ---------- левая панель: настройки ----------
        left = tk.Frame(root, bg=T["bg"])
        left.grid(row=0, column=0, sticky="ns", padx=(12, 6), pady=12)
        left.columnconfigure(0, weight=1)
        self.left = left

        # карточка «Данные» (растягивается по высоте)
        data = self._card(left, "Данные", row=0, stretch=True)
        self._field_row(data, "Файл X (ось абсцисс)", self.x_file, row=1,
                        pick_cmd=self._pick_x)

        self._muted_label(data, "Линии Y").grid(row=3, column=0, sticky="w", padx=14, pady=(12, 2))
        self.lines_frame = tk.Frame(data, bg=T["card"])
        self.lines_frame.grid(row=4, column=0, sticky="ew", padx=14)
        self._reg(self.lines_frame, "card")
        self._btn(data, "+ Добавить линию", self.add_line).grid(
            row=5, column=0, sticky="w", padx=14, pady=(8, 12))

        # карточка «График»
        graph = self._card(left, "График", row=1)
        self._field_row(graph, "Название графика", self.title_var, row=1)
        self._field_row(graph, "Подпись оси X", self.xlabel_var, row=3)
        self._field_row(graph, "Подпись оси Y", self.ylabel_var, row=5)

        self.combined_check = tk.Checkbutton(
            graph, text="Все линии на одном графике", variable=self.combined,
            command=self._toggle_combined, bg=T["card"], activebackground=T["card"],
            selectcolor=T["entry_bg"], font=F_BODY)
        self.combined_check.grid(row=7, column=0, sticky="w", padx=14, pady=(10, 2))
        self._reg(self.combined_check, "check")
        comb_row = tk.Frame(graph, bg=T["card"])
        comb_row.grid(row=8, column=0, sticky="ew", padx=14, pady=(0, 2))
        comb_row.columnconfigure(1, weight=1)
        self._reg(comb_row, "card")
        self.combined_lbl = self._muted_label(comb_row, "Имя объединённого:",
                                              state=tk.DISABLED)
        self.combined_lbl.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.combined_entry = self._entry(comb_row, self.combined_name, width=12,
                                          state=tk.DISABLED)
        self.combined_entry.grid(row=0, column=1, sticky="ew")

        # карточка «Вывод»
        out = self._card(left, "Вывод", row=2)
        self._field_row(out, "Папка для PNG", self.out_dir, row=1,
                        pick_cmd=self._pick_dir)
        self._muted_label(
            out, "PNG создаются рядом с выбранными .dat файлами, "
                 "если папка не указана явно.", justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=14, pady=(6, 12))

        # ---------- правая панель: результат ----------
        right = tk.Frame(root, bg=T["bg"])
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.right = right

        # верхняя панель: кнопка + тема + статус
        topbar = tk.Frame(right, bg=T["bg"])
        topbar.grid(row=0, column=0, sticky="ew")
        self.topbar = topbar
        self.gen_btn = tk.Button(topbar, text="  Построить графики  ",
                                 bg=T["accent"], fg="white",
                                 activebackground=T["accent_hv"],
                                 activeforeground="white", relief=tk.FLAT, bd=0,
                                 font=F_HEAD, cursor="hand2", command=self.generate)
        self.gen_btn.pack(side=tk.LEFT, padx=(2, 10), pady=6)
        self._reg(self.gen_btn, "accent_btn")
        self.status = tk.Label(topbar, text="", bg=T["bg"], fg=T["muted"], font=F_BODY)
        self.status.pack(side=tk.RIGHT, padx=4)

        # карточка предпросмотра (вкладки на каждый PNG)
        prev = tk.Frame(right, bg=T["card"])
        prev.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        prev.columnconfigure(0, weight=1)
        prev.rowconfigure(0, weight=1)
        self._reg(prev, "card")
        self.nb = ttk.Notebook(prev)
        self.nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        footer = tk.Frame(prev, bg=T["card"])
        footer.grid(row=1, column=0, sticky="ew")
        self._reg(footer, "card")
        self.fit_check = tk.Checkbutton(
            footer, text="Вписывать в окно (без прокрутки)",
            variable=self.fit_preview, command=self._update_all_previews,
            bg=T["card"], activebackground=T["card"], selectcolor=T["entry_bg"],
            font=F_SMALL)
        self.fit_check.grid(row=0, column=0, sticky="w", padx=(6, 0), pady=(2, 8))
        self._reg(self.fit_check, "check")

        # карточка Markdown
        md = tk.Frame(right, bg=T["card"])
        md.grid(row=2, column=0, sticky="ew")
        md.columnconfigure(0, weight=1)
        self._reg(md, "card")
        self.md_text = tk.Text(md, height=4, wrap="none", bd=0, bg=T["entry_bg"],
                              fg=T["text"], insertbackground=T["text"],
                              font=("Consolas", 9), highlightthickness=1,
                              highlightbackground=T["border"])
        self.md_text.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=(12, 12))
        self._reg(self.md_text, "field")
        side = tk.Frame(md, bg=T["card"])
        side.grid(row=0, column=1, sticky="ns", padx=(0, 10))
        self._reg(side, "card")
        self._btn(side, "Копировать в буфер", self._copy_md).pack(pady=3)
        self._btn(side, "Открыть папку", self._open_outdir).pack(pady=3)

    # ---------- действия ----------
    def add_line(self):
        self._line_counter += 1
        self.lines.append(YLine(self.lines_frame, self, self._line_counter))

    def _toggle_combined(self):
        """Включает/выключает поле имени объединённого графика."""
        state = tk.NORMAL if self.combined.get() else tk.DISABLED
        self.combined_entry.configure(state=state)
        self.combined_lbl.configure(
            state=state, fg=self.T["text"] if state == tk.NORMAL else self.T["muted"])

    def _pick_x(self):
        path = filedialog.askopenfilename(
            title="Выберите .dat файл оси X (или вставьте числа в поле)",
            filetypes=[("DAT-файлы", "*.dat"), ("Все файлы", "*.*")])
        if path:
            self.x_file.set(path)

    def _pick_dir(self):
        d = filedialog.askdirectory(title="Папка для PNG файлов")
        if d:
            self.out_dir.set(d)

    @staticmethod
    def _to_int(v, default):
        try:
            return int(v)
        except (ValueError, TypeError, tk.TclError):
            return default

    # ---------- построение графиков ----------
    def generate(self):
        """Строит графики, сохраняет PNG и строки Markdown."""
        warnings = []
        prepared = []
        for ln in self.lines:
            legend = ln.legend_var.get()
            start = self._to_int(ln.start_var.get(), None)
            if start is None:
                messagebox.showerror("Ошибка", "В поле «Y с:» нужно целое число")
                return
            start = max(1, start)
            x_start = self._to_int(ln.x_start_var.get(), None)
            if x_start is None:
                messagebox.showerror("Ошибка", "В поле «X с:» нужно целое число")
                return
            x_start = max(1, x_start)

            # X для линии: свой (если задан), иначе общий
            x_text = ln.x_path_var.get().strip() or self.x_file.get().strip()
            if not x_text:
                warnings.append(f"«{legend}»: не указан X — пропущена")
                continue
            xs = read_numbers(x_text, start_line=x_start) if os.path.isfile(x_text) \
                else parse_numbers(x_text)

            y_text = ln.path_var.get().strip()
            if not y_text:
                warnings.append(f"«{legend}»: не указан Y — пропущена")
                continue
            ys = read_numbers(y_text, start_line=start) if os.path.isfile(y_text) \
                else parse_numbers(y_text)

            n = min(len(xs), len(ys))
            if n == 0:
                warnings.append(f"«{legend}»: нет данных — пропущена")
                continue
            if len(xs) != len(ys):
                warnings.append(f"«{legend}»: X={len(xs)}, Y={len(ys)} — беру {n}")
            prepared.append((xs[:n], ys[:n], ln.color, legend))

        if not prepared:
            messagebox.showerror("Ошибка", "Нет данных: укажите файлы или числа X и Y.")
            return

        main_x = self.x_file.get().strip()
        out_dir = self.out_dir.get().strip()
        if not out_dir:
            out_dir = os.path.dirname(main_x) if os.path.isfile(main_x) else app_dir()
        os.makedirs(out_dir, exist_ok=True)

        md_lines = []
        png_paths = []
        title = self.title_var.get().strip() or "График"
        xlabel = self.xlabel_var.get().strip()
        ylabel = self.ylabel_var.get().strip()

        if self.combined.get():
            fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
            for xs, ys, color, label in prepared:
                ax.plot(xs, ys, color=color, linewidth=2, label=label)
            ax.set_title(title)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            _style_ax(ax)
            fig.tight_layout(pad=0.4)
            name = safe_name(self.combined_name.get()) + ".png"
            path = os.path.join(out_dir, name)
            fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            md_lines.append(f"![{title}]({name})")
            png_paths.append(path)
        else:
            for xs, ys, color, label in prepared:
                fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
                ax.plot(xs, ys, color=color, linewidth=2, label=label)
                ax.set_title(f"{title} — {label}")
                ax.set_xlabel(xlabel)
                ax.set_ylabel(ylabel)
                _style_ax(ax)
                fig.tight_layout(pad=0.4)
                fname = safe_name(label) + ".png"
                path = os.path.join(out_dir, fname)
                fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
                plt.close(fig)
                md_lines.append(f"![{label}]({fname})")
                png_paths.append(path)

        self.md_text.delete("1.0", "end")
        self.md_text.insert("1.0", "\n".join(md_lines))
        self._show_preview(png_paths)
        if warnings:
            self._set_status(
                "⚠ " + "; ".join(warnings) + f"  ·  сохранено {len(md_lines)} PNG в {out_dir}",
                "err")
        else:
            self._set_status(f"Сохранено: {len(md_lines)} PNG в {out_dir}", "ok")

    # ---------- предпросмотр (вкладки) ----------
    def _show_preview(self, png_paths):
        """Вкладка на каждый сохранённый PNG; свой скролл у каждой."""
        for t in self._preview_tabs:
            try:
                t["frame"].destroy()
            except tk.TclError:
                pass
        self._preview_tabs = []
        for path in png_paths:
            if not os.path.isfile(path):
                continue
            img = Image.open(path)
            orig = img.copy()
            frame = tk.Frame(self.nb, bg=self.T["card"])
            self.nb.add(frame, text=os.path.basename(path))
            canvas = tk.Canvas(frame, bg=self.T["card"], highlightthickness=0)
            vbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            hbar = ttk.Scrollbar(frame, orient="horizontal", command=canvas.xview)
            canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            canvas.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=(8, 4))
            vbar.grid(row=0, column=1, sticky="ns", pady=(8, 4), padx=(0, 6))
            hbar.grid(row=1, column=0, sticky="ew", padx=(8, 4), pady=(0, 6))
            entry = {"frame": frame, "canvas": canvas, "orig": orig, "photo": None}
            canvas.bind("<Configure>", lambda e, t=entry: self._update_preview_for(t))
            self._preview_tabs.append(entry)
        if self._preview_tabs:
            self.nb.select(0)
            for t in self._preview_tabs:
                self._update_preview_for(t)

    def _update_preview_for(self, entry):
        """Перерисовывает одну вкладку с учётом «вписать в окно»."""
        img = entry["orig"]
        canvas = entry["canvas"]
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if self.fit_preview.get() and w > 40 and h > 40:
            scale = min((w - 20) / img.width, (h - 20) / img.height, 1.0)
        else:
            scale = 1.0
        resized = img.resize((max(1, int(img.width * scale)),
                              max(1, int(img.height * scale))))
        entry["photo"] = ImageTk.PhotoImage(resized)
        canvas.delete("all")
        canvas.create_image(10, 10, anchor="nw", image=entry["photo"])
        if not self.fit_preview.get():
            canvas.configure(scrollregion=canvas.bbox("all"))

    def _update_all_previews(self):
        for t in self._preview_tabs:
            self._update_preview_for(t)

    # ---------- Markdown / папка ----------
    def _copy_md(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.md_text.get("1.0", "end-1c"))
        self._set_status("Markdown скопирован в буфер обмена", "ok")

    def _open_outdir(self):
        d = self.out_dir.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)  # только Windows

    def _set_status(self, text, kind="info"):
        self._status_kind = kind
        color = {"info": self.T["muted"], "ok": self.T["ok"], "err": self.T["err"]}[kind]
        self.status.configure(text=text, fg=color)

    # ---------- проекты .gslab ----------
    def save_project(self, path):
        """Сохраняет все настройки в JSON-проект; пути внутри папки проекта —
        относительными, остальные — абсолютными."""
        proj_dir = os.path.dirname(os.path.abspath(path))

        def rel(p):
            if not p:
                return ""
            ap = os.path.abspath(p)
            try:
                common = os.path.commonpath([ap, proj_dir])
            except ValueError:
                return p
            if common == proj_dir:
                return os.path.relpath(ap, proj_dir)
            return p

        data = {
            "version": 1,
            "x_file": rel(self.x_file.get().strip()),
            "lines": [
                {"path": rel(ln.path_var.get().strip()),
                 "legend": ln.legend_var.get(),
                 "start": self._to_int(ln.start_var.get(), 4),
                 "color": ln.color,
                 "x_path": rel(ln.x_path_var.get().strip()),
                 "x_start": self._to_int(ln.x_start_var.get(), 1)}
                for ln in self.lines
            ],
            "title": self.title_var.get(),
            "xlabel": self.xlabel_var.get(),
            "ylabel": self.ylabel_var.get(),
            "combined": bool(self.combined.get()),
            "combined_name": self.combined_name.get(),
            "out_dir": rel(self.out_dir.get().strip()),
            "fit_preview": bool(self.fit_preview.get()),
            "geometry": self.root.geometry(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_project(self, path):
        """Открывает проект из файла; ошибки — в showerror."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть проект:\n{e}")
            return False
        base_dir = os.path.dirname(os.path.abspath(path))
        self.load_project_from_dict(data, base_dir)
        self._set_status(f"Проект открыт: {os.path.basename(path)}", "ok")
        return True

    def load_project_from_dict(self, data, base_dir):
        """Восстанавливает состояние из словаря проекта (папка — base_dir)."""
        def resolve(p):
            if not p:
                return ""
            if os.path.isabs(p):
                return p
            return os.path.normpath(os.path.join(base_dir, p))

        # убрать текущие линии
        for ln in list(self.lines):
            try:
                ln.frame.destroy()
            except tk.TclError:
                pass
        self.lines.clear()
        self._line_counter = 0

        for item in data.get("lines", []):
            self._line_counter += 1
            ln = YLine(self.lines_frame, self, self._line_counter)
            ln.path_var.set(resolve(item.get("path", "")))
            ln.legend_var.set(item.get("legend", f"линия {self._line_counter}"))
            ln.start_var.set(self._to_int(item.get("start", 4), 4))
            ln.color = item.get("color") or PALETTE[self._line_counter % len(PALETTE)]
            ln.color_btn.configure(bg=ln.color, fg=ln.color)
            ln.x_path_var.set(resolve(item.get("x_path", "")))
            ln.x_start_var.set(self._to_int(item.get("x_start", 1), 1))
            self.lines.append(ln)

        self.x_file.set(resolve(data.get("x_file", "")))
        self.title_var.set(data.get("title", "График"))
        self.xlabel_var.set(data.get("xlabel", "X"))
        self.ylabel_var.set(data.get("ylabel", "Y"))
        self.combined.set(bool(data.get("combined", False)))
        self.combined_name.set(data.get("combined_name", "combined"))
        od = resolve(data.get("out_dir", ""))
        self.out_dir.set(od or app_dir())
        self.fit_preview.set(bool(data.get("fit_preview", False)))
        geom = data.get("geometry")
        if geom:
            try:
                self.root.geometry(geom)
            except tk.TclError:
                pass
        self._toggle_combined()

    def _project_resolves(self, data, base_dir):
        """True, если файлы проекта существуют (или поля — сырые числа)."""
        def resolve(p):
            if not p:
                return ""
            if os.path.isabs(p):
                return p
            return os.path.normpath(os.path.join(base_dir, p))

        def ok_field(p):
            if not p:
                return True
            return os.path.isfile(p) or len(parse_numbers(p)) > 0

        if not ok_field(resolve(data.get("x_file", ""))):
            return False
        for item in data.get("lines", []):
            if not ok_field(resolve(item.get("path", ""))):
                return False
            if not ok_field(resolve(item.get("x_path", ""))):
                return False
        return True

    # ---------- автосохранение / восстановление ----------
    def _autosave(self):
        try:
            d = user_dir()
            with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"geometry": self.root.geometry()},
                          f, ensure_ascii=False, indent=2)
            self.save_project(os.path.join(d, "last.gslab"))
        except Exception:
            pass

    def _restore_state(self):
        """При запуске: геометрия из config.json; last.gslab — молча,
        если пути резолвятся."""
        d = user_dir()
        geom = None
        cfg_path = os.path.join(d, "config.json")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                geom = cfg.get("geometry")
            except Exception:
                pass

        last = os.path.join(d, "last.gslab")
        loaded = False
        if os.path.isfile(last):
            try:
                with open(last, encoding="utf-8") as f:
                    data = json.load(f)
                base_dir = os.path.dirname(os.path.abspath(last))
                if self._project_resolves(data, base_dir):
                    self.load_project_from_dict(data, base_dir)
                    loaded = True
            except Exception:
                pass
        if not loaded and geom:
            try:
                self.root.geometry(geom)
            except tk.TclError:
                pass

    def _on_close(self):
        self._autosave()
        self.root.destroy()

    # ---------- меню: проекты ----------
    def _menu_save_project(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить проект", defaultextension=".gslab",
            filetypes=[("Проекты GraphLab", "*.gslab")])
        if not path:
            return
        try:
            self.save_project(path)
            self._set_status(f"Проект сохранён: {path}", "ok")
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить проект:\n{e}")

    def _menu_open_project(self):
        path = filedialog.askopenfilename(
            title="Открыть проект",
            filetypes=[("Проекты GraphLab", "*.gslab"), ("Все файлы", "*.*")])
        if not path:
            return
        self.load_project(path)


def main():
    # чёткость на HiDPI-экранах (Windows)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
