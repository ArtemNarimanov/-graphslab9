# -*- coding: utf-8 -*-
"""GraphLab Plotter — портативное GUI-приложение.

Выбор .dat файлов (X и Y) из проводника, настройка имён осей, цветов линий,
подписей легенды и строк начала чтения для каждой линии (у линии может быть
свой X), построение графиков (отдельные или все на одном), сохранение PNG и
готовых строк для Markdown. Числа можно вставить прямо в поле без .dat.
Предпросмотр строится в памяти — файлы на диск не пишутся; экспорт в PNG —
отдельная кнопка. Проекты .gslab: «Новый проект / Открыть / Сохранить /
Сохранить как…», заголовок со звёздочкой при несохранённых изменениях,
автосохранение при выходе, предпросмотр вкладками.

Интерфейс: плоский современный дизайн (карточки, шрифт Segoe UI), светлая тема.
Запуск: GraphLab.exe (или python graphlab_app.py с matplotlib+Pillow).
"""

import ctypes
import io
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

        # любое пользовательское изменение поля — проект «испорчен»
        for var in (self.path_var, self.legend_var, self.start_var,
                    self.x_path_var, self.x_start_var):
            var.trace_add("write", lambda *a: app._mark_dirty())

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
            self.app._mark_dirty()

    def _remove(self):
        self.frame.destroy()
        self.app.lines.remove(self)
        self.app._mark_dirty()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.geometry("1280x720")   # по умолчанию 16:9 (TZ fix 3)
        root.minsize(1024, 576)

        self.T = T
        self._status_kind = "info"
        self._ctx_target = None
        self.ctx_menu = None

        # состояние проекта: None — «Новый проект», _dirty — есть несохранённые
        self.project_path = None
        self._dirty = False
        self._loading = False

        self.x_file = tk.StringVar()
        self.title_var = tk.StringVar(value="График")
        self.xlabel_var = tk.StringVar(value="X")
        self.ylabel_var = tk.StringVar(value="Y")
        self.out_dir = tk.StringVar(value=app_dir())
        self.combined = tk.BooleanVar(value=False)
        self.combined_name = tk.StringVar(value="combined")
        self.fit_preview = tk.BooleanVar(value=False)
        # любое пользовательское изменение поля — проект «испорчен»
        for var in (self.x_file, self.title_var, self.xlabel_var, self.ylabel_var,
                    self.out_dir, self.combined_name):
            var.trace_add("write", lambda *a: self._mark_dirty())
        self.combined.trace_add("write", lambda *a: self._mark_dirty())
        self.fit_preview.trace_add("write", lambda *a: self._mark_dirty())
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
        file_menu.add_command(label="Новый проект", accelerator="Ctrl+N",
                              command=self._menu_new_project)
        file_menu.add_command(label="Открыть проект…", accelerator="Ctrl+O",
                              command=self._menu_open_project)
        file_menu.add_command(label="Сохранить", accelerator="Ctrl+S",
                              command=self._menu_save_project)
        file_menu.add_command(label="Сохранить как…", accelerator="Ctrl+Shift+S",
                              command=self._menu_save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Выйти", command=self._on_close)
        menubar.add_cascade(label="Файл", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        for label, ev, acc in [("Вырезать", "<<Cut>>", "Ctrl+X"),
                               ("Копировать", "<<Copy>>", "Ctrl+C"),
                               ("Вставить", "<<Paste>>", "Ctrl+V"),
                               ("Выделить всё", "<<SelectAll>>", "Ctrl+A")]:
            edit_menu.add_command(label=label, accelerator=acc,
                                  command=lambda e=ev: self._focus_event(e))
        menubar.add_cascade(label="Правка", menu=edit_menu)
        root.config(menu=menubar)

        # ускорители Ctrl+X/C/V/A и меню «Файл».
        # Раскладка-независимо: одна привязка <Control-KeyPress>,
        # диспетчеризация по keysym внутри _ctrl_key (англ. + ЙЦУКЕН).
        root.bind_all("<Control-KeyPress>", self._ctrl_key)

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

    # keysym → действие. Команды меню — callable; редактор — виртуальные
    # события, генерируемые на виджете с фокусом. Англ. + ЙЦУКЕН.
    _HOTKEYS = {
        "n": "new", "т": "new",
        "o": "open", "щ": "open",
        "s": "save", "ы": "save",
        "x": "<<Cut>>", "ч": "<<Cut>>",
        "c": "<<Copy>>", "с": "<<Copy>>",
        "v": "<<Paste>>", "м": "<<Paste>>",
        "a": "<<SelectAll>>", "ф": "<<SelectAll>>",
    }
    _HOTKEYS_SHIFT = {"S": "saveas", "Ы": "saveas"}

    # Fallback по физическим кодам клавиш (VK) — раскладка-независим: одна и
    # та же физическая клавиша в любой раскладке. Используется, когда Tk не
    # перевёл символ в keysym (keysym == "??", например русская раскладка
    # внутри замороженного exe).
    _VK_HOTKEYS = {
        0x4E: "new",             # N / Т
        0x4F: "open",            # O / Щ
        0x53: "save",            # S / Ы (с Shift -> saveas)
        0x58: "<<Cut>>",         # X / Ч
        0x43: "<<Copy>>",        # C / С
        0x56: "<<Paste>>",       # V / М
        0x41: "<<SelectAll>>",   # A / Ф
    }

    def _vk_action(self, shift):
        """Действие по нажатой Ctrl+букве через физический код клавиши (VK)."""
        try:
            user32 = ctypes.windll.user32
        except (AttributeError, OSError):
            return None
        for vk, action in self._VK_HOTKEYS.items():
            if user32.GetAsyncKeyState(vk) & 0x8000:
                if shift and action == "save":
                    return "saveas"
                return action
        return None

    def _ctrl_key(self, e):
        """Ctrl-ускорители (раскладка-независимо): диспетчеризация по keysym
        с fallback на физические коды клавиш (VK)."""
        ks = e.keysym
        if not (e.state & 4):          # бит Control
            return
        shift = bool(e.state & 1)
        action = None
        if isinstance(ks, str) and len(ks) == 1:
            table = self._HOTKEYS_SHIFT if shift else self._HOTKEYS
            action = table.get(ks)
        elif isinstance(ks, str) and ks.startswith("U") and len(ks) == 5:
            # Tk может сообщать Unicode-символ как "U0442" (нет keysym'а)
            try:
                ch = chr(int(ks[1:], 16))
            except ValueError:
                ch = None
            if ch is not None:
                table = self._HOTKEYS_SHIFT if shift else self._HOTKEYS
                action = table.get(ch)
        if action is None:
            # keysym == "??": Tk не смог перевести символ (русская раскладка
            # внутри exe). Fallback на физические коды — они одинаковы в
            # любой раскладке.
            action = self._vk_action(shift)
        if action is None:
            return
        if action == "new":
            self._menu_new_project()
        elif action == "open":
            self._menu_open_project()
        elif action == "save":
            self._menu_save_project()
        elif action == "saveas":
            self._menu_save_project_as()
        else:                          # виртуальное событие на фокусе
            self._focus_event(action)

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
        self.left = left
        # прокручивается только «Данные»; «График» и «Вывод» статичны (TZ fix 1)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        # canvas + вертикальный бегунок вокруг карточки «Данные» (R6)
        data_box = tk.Frame(left, bg=T["bg"])
        data_box.grid(row=0, column=0, sticky="nsew")
        data_box.columnconfigure(0, weight=1)
        left_canvas = tk.Canvas(data_box, bg=T["bg"], highlightthickness=0)
        left_vbar = ttk.Scrollbar(data_box, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_vbar.set)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_vbar.grid(row=0, column=1, sticky="ns")
        self.left_canvas = left_canvas

        inner = tk.Frame(left_canvas, bg=T["bg"])
        win_id = left_canvas.create_window(0, 0, anchor="nw", window=inner)

        # автоизмерение: scrollregion, ширина карточек, автоскрытие бегунка
        def _left_scroll_state(e):
            if e.widget is inner:
                left_canvas.configure(scrollregion=left_canvas.bbox("all"))
            else:  # canvas — карточки на всю ширину панели (R6.2)
                left_canvas.itemconfigure(win_id, width=e.widget.winfo_width())
            bbox = left_canvas.bbox("all")
            content_h = bbox[3] if bbox else 0
            if content_h <= left_canvas.winfo_height():
                left_vbar.grid_remove()
            else:
                left_vbar.grid(row=0, column=1, sticky="ns")

        inner.bind("<Configure>", _left_scroll_state)
        left_canvas.bind("<Configure>", _left_scroll_state)

        # карточка «Данные» (естественная высота — R6.3)
        data = self._card(inner, "Данные", row=0)
        self._field_row(data, "Файл X (ось абсцисс)", self.x_file, row=1,
                        pick_cmd=self._pick_x)

        self._muted_label(data, "Линии Y").grid(row=3, column=0, sticky="w", padx=14, pady=(12, 2))
        self.lines_frame = tk.Frame(data, bg=T["card"])
        self.lines_frame.grid(row=4, column=0, sticky="ew", padx=14)
        self._reg(self.lines_frame, "card")
        self._btn(data, "+ Добавить линию", self.add_line).grid(
            row=5, column=0, sticky="w", padx=14, pady=(8, 12))

        # карточка «График» (статична, вне прокрутки — TZ fix 1)
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

        # карточка «Вывод» (статична, вне прокрутки — TZ fix 1)
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
        self.gen_btn = tk.Button(topbar, text="  Построить график  ",
                                 bg=T["accent"], fg="white",
                                 activebackground=T["accent_hv"],
                                 activeforeground="white", relief=tk.FLAT, bd=0,
                                 font=F_HEAD, cursor="hand2",
                                  command=self.preview_graph)
        self.gen_btn.pack(side=tk.LEFT, padx=(2, 10), pady=6)
        self._reg(self.gen_btn, "accent_btn")
        self.export_btn = tk.Button(topbar, text="  Экспорт в PNG  ",
                                    bg=T["btn_bg"], fg=T["text"],
                                    activebackground=T["btn_hover"],
                                    activeforeground=T["text"], relief=tk.FLAT, bd=0,
                                    font=F_HEAD, cursor="hand2",
                                    command=self.export_png)
        self.export_btn.pack(side=tk.LEFT, padx=(0, 10), pady=6)
        self._reg(self.export_btn, "btn")
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

        # карточка «Python-код» (R8: самодостаточный сниппет для Jupyter)
        code = tk.Frame(right, bg=T["card"])
        code.grid(row=2, column=0, sticky="ew")
        code.columnconfigure(0, weight=1)
        self._reg(code, "card")
        self.code_text = tk.Text(code, height=9, wrap="none", bd=0, bg=T["entry_bg"],
                                fg=T["text"], insertbackground=T["text"],
                                font=("Consolas", 9), highlightthickness=1,
                                highlightbackground=T["border"], state=tk.DISABLED)
        self.code_text.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=(12, 12))
        self._reg(self.code_text, "field")
        code_vbar = ttk.Scrollbar(code, orient="vertical", command=self.code_text.yview)
        self.code_text.configure(yscrollcommand=code_vbar.set)
        code_vbar.grid(row=0, column=1, sticky="ns", padx=(2, 4), pady=(12, 12))
        side = tk.Frame(code, bg=T["card"])
        side.grid(row=0, column=2, sticky="ns", padx=(0, 10))
        self._reg(side, "card")
        self._btn(side, "Скопировать код", self._copy_code).pack(pady=3)
        self._btn(side, "Открыть папку", self._open_outdir).pack(pady=3)

        # колесико мыши: единый центральный обработчик для всех областей (R7.1)
        root.bind_all("<MouseWheel>", self._on_mousewheel)

    # ---------- действия ----------
    def add_line(self):
        idx = self._line_counter
        self._line_counter += 1
        self.lines.append(YLine(self.lines_frame, self, idx))
        self._mark_dirty()

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
    @staticmethod
    def _plural(n, one, few, many):
        """Русские формы множественного: 1 график, 2 графика, 5 графиков."""
        n %= 100
        if 11 <= n <= 14:
            return many
        n %= 10
        if n == 1:
            return one
        if 2 <= n <= 4:
            return few
        return many

    def _prepare(self):
        """Валидация и сборка данных (xs, ys, цвет, легенда) + warnings.

        Возвращает (prepared, warnings); None — была ошибка (уже показана).
        """
        warnings = []
        prepared = []
        read_errors = []
        for ln in self.lines:
            legend = ln.legend_var.get()
            start = self._to_int(ln.start_var.get(), None)
            if start is None:
                messagebox.showerror("Ошибка", "В поле «Y с:» нужно целое число")
                return None
            start = max(1, start)
            x_start = self._to_int(ln.x_start_var.get(), None)
            if x_start is None:
                messagebox.showerror("Ошибка", "В поле «X с:» нужно целое число")
                return None
            x_start = max(1, x_start)

            # X для линии: свой (если задан), иначе общий
            x_text = ln.x_path_var.get().strip() or self.x_file.get().strip()
            if not x_text:
                warnings.append(f"«{legend}»: не указан X — пропущена")
                continue
            try:
                xs = read_numbers(x_text, start_line=x_start) if os.path.isfile(x_text) \
                    else parse_numbers(x_text)
            except (OSError, UnicodeDecodeError) as e:
                read_errors.append(f"{x_text}: {e}")
                continue

            y_text = ln.path_var.get().strip()
            if not y_text:
                warnings.append(f"«{legend}»: не указан Y — пропущена")
                continue
            try:
                ys = read_numbers(y_text, start_line=start) if os.path.isfile(y_text) \
                    else parse_numbers(y_text)
            except (OSError, UnicodeDecodeError) as e:
                read_errors.append(f"{y_text}: {e}")
                continue

            n = min(len(xs), len(ys))
            if n == 0:
                warnings.append(f"«{legend}»: нет данных — пропущена")
                continue
            if len(xs) != len(ys):
                warnings.append(f"«{legend}»: X={len(xs)}, Y={len(ys)} — беру {n}")
            prepared.append((xs[:n], ys[:n], ln.color, legend))

        if read_errors:
            messagebox.showerror(
                "Ошибка чтения",
                "Не удалось прочитать файлы:\n" + "\n".join(read_errors))
        if not prepared:
            messagebox.showerror("Ошибка", "Нет данных: укажите файлы или числа X и Y.")
            return None
        return prepared, warnings

    def _build_figs(self, prepared):
        """Общее построение фигур (объединённый или по линиям).

        Возвращает список (fig, name, caption); name — имя PNG/Markdown.
        """
        title = self.title_var.get().strip() or "График"
        xlabel = self.xlabel_var.get().strip()
        ylabel = self.ylabel_var.get().strip()
        figs = []
        if self.combined.get():
            fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
            for xs, ys, color, label in prepared:
                ax.plot(xs, ys, color=color, linewidth=2, label=label)
            ax.set_title(title)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            _style_ax(ax)
            fig.tight_layout(pad=0.4)
            figs.append((fig, safe_name(self.combined_name.get()) + ".png", title))
        else:
            for xs, ys, color, label in prepared:
                fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
                ax.plot(xs, ys, color=color, linewidth=2, label=label)
                ax.set_title(f"{title} — {label}")
                ax.set_xlabel(xlabel)
                ax.set_ylabel(ylabel)
                _style_ax(ax)
                fig.tight_layout(pad=0.4)
                figs.append((fig, safe_name(label) + ".png", label))
        return figs

    # ---------- Python-код (R8) ----------
    @staticmethod
    def _py_str(s):
        """Строковый литерал для сниппета: двойные кавычки с экранированием."""
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _build_snippet(self, prepared):
        """Самодостаточный matplotlib-код, воспроизводящий график.

        Вставляется в Jupyter и выполняется без GraphLab: массивы данных,
        стиль, сохранение в plots/, plt.show().
        """
        title = self.title_var.get().strip() or "График"
        xlabel = self.xlabel_var.get().strip()
        ylabel = self.ylabel_var.get().strip()
        lines = ["import os", "import matplotlib.pyplot as plt", ""]
        for i, (xs, ys, color, label) in enumerate(prepared, start=1):
            x_lit = ", ".join(repr(float(v)) for v in xs)
            y_lit = ", ".join(repr(float(v)) for v in ys)
            lines.append(f"x{i} = [{x_lit}]")
            lines.append(f"y{i} = [{y_lit}]")
        lines.append("")

        def _style():
            return [
                'ax.spines["top"].set_visible(False)',
                'ax.spines["right"].set_visible(False)',
                'ax.grid(True, linestyle="--", alpha=0.4)',
                "ax.legend(framealpha=0.9)",
            ]

        if self.combined.get():
            lines.append("fig, ax = plt.subplots(figsize=(9, 5), dpi=150)")
            for i, (_, _, color, label) in enumerate(prepared, start=1):
                lines.append(f"ax.plot(x{i}, y{i}, color={self._py_str(color)}, "
                             f"linewidth=2, label={self._py_str(label)})")
            lines.append(f"ax.set_title({self._py_str(title)})")
            lines.append(f"ax.set_xlabel({self._py_str(xlabel)})")
            lines.append(f"ax.set_ylabel({self._py_str(ylabel)})")
            lines.extend(_style())
            lines.append("fig.tight_layout(pad=0.4)")
            lines.append("")
            lines.append('os.makedirs("plots", exist_ok=True)')
            name = safe_name(self.combined_name.get()) + ".png"
            lines.append(f'fig.savefig(os.path.join("plots", {self._py_str(name)}), '
                         f'dpi=150, bbox_inches="tight")')
        else:
            lines.append('os.makedirs("plots", exist_ok=True)')
            for i, (_, _, color, label) in enumerate(prepared, start=1):
                sub_title = f"{title} — {label}"
                lines.append(f"fig{i}, ax = plt.subplots(figsize=(9, 5), dpi=150)")
                lines.append(f"ax.plot(x{i}, y{i}, color={self._py_str(color)}, "
                             f"linewidth=2, label={self._py_str(label)})")
                lines.append(f"ax.set_title({self._py_str(sub_title)})")
                lines.append(f"ax.set_xlabel({self._py_str(xlabel)})")
                lines.append(f"ax.set_ylabel({self._py_str(ylabel)})")
                lines.extend(_style())
                lines.append(f"fig{i}.tight_layout(pad=0.4)")
                name = safe_name(label) + ".png"
                lines.append(f'fig{i}.savefig(os.path.join("plots", {self._py_str(name)}), '
                             f'dpi=150, bbox_inches="tight")')
        lines.append("")
        lines.append("plt.show()")
        return "\n".join(lines)

    def _update_code(self, text):
        """Обновляет поле Python-кода (оно только для чтения)."""
        self.code_text.configure(state=tk.NORMAL)
        self.code_text.delete("1.0", "end")
        self.code_text.insert("1.0", text)
        self.code_text.configure(state=tk.DISABLED)

    def preview_graph(self):
        """«Построить график»: предпросмотр в памяти — на диск ничего не пишет."""
        res = self._prepare()
        if res is None:
            return
        prepared, warnings = res
        figs = self._build_figs(prepared)
        images = []
        for fig, name, _ in figs:
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            buf.seek(0)
            img = Image.open(buf)
            images.append((name, img))
        self._update_code(self._build_snippet(prepared))
        self._show_preview(images)
        n = len(images)
        status = (f"Предпросмотр: {n} "
                  f"{self._plural(n, 'график', 'графика', 'графиков')}, "
                  f"файлы не записаны")
        if warnings:
            self._set_status("⚠ " + "; ".join(warnings) + f"  ·  {status}", "err")
        else:
            self._set_status(status, "ok")

    def export_png(self):
        """«Экспорт в PNG»: записывает файлы в out_dir + тот же предпросмотр."""
        res = self._prepare()
        if res is None:
            return
        prepared, warnings = res
        main_x = self.x_file.get().strip()
        out_dir = self.out_dir.get().strip()
        if not out_dir:
            out_dir = os.path.dirname(main_x) if os.path.isfile(main_x) else app_dir()
        os.makedirs(out_dir, exist_ok=True)

        figs = self._build_figs(prepared)
        images = []
        for fig, name, _ in figs:
            path = os.path.join(out_dir, name)
            fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            img = Image.open(path)
            images.append((name, img))
        self._show_preview(images)
        status = f"Экспорт: {len(images)} PNG в {out_dir}"
        if warnings:
            self._set_status("⚠ " + "; ".join(warnings) + f"  ·  {status}", "err")
        else:
            self._set_status(status, "ok")

    # ---------- предпросмотр (вкладки) ----------
    def _clear_preview_tabs(self):
        for t in self._preview_tabs:
            try:
                t["frame"].destroy()
            except tk.TclError:
                pass
        self._preview_tabs = []

    def _show_preview(self, images):
        """Вкладка на каждое изображение (name, PIL Image); свой скролл у каждой."""
        self._clear_preview_tabs()
        for name, img in images:
            orig = img.copy()
            frame = tk.Frame(self.nb, bg=self.T["card"])
            self.nb.add(frame, text=name)
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

    # ---------- колесико мыши (R7) ----------
    def _on_mousewheel(self, e):
        """Колесико над панелью данных, вкладками графика и полем Python-кода.

        Область определяется по цепочке master виджета под указателем;
        обработанное событие возвращает "break". Направление: колесо вниз →
        вниз/вправо, вверх → вверх/влево (TZ fix 2); Shift+колесо — горизонтально
        только над вкладкой графика (R7.5).
        """
        w = self.root.winfo_containing(e.x_root, e.y_root)
        if w is None:
            return
        chain = []
        cur = w
        while cur is not None:
            chain.append(cur)
            cur = cur.master
        shift = bool(e.state & 1)
        target = None
        if self.left_canvas in chain:
            if not shift:
                target = (self.left_canvas, "y")
        else:
            for t in self._preview_tabs:
                if t["canvas"] in chain:
                    target = (t["canvas"], "x" if shift else "y")
                    break
            if target is None and self.code_text in chain:
                target = (self.code_text, "y")
        if target is None:
            return
        # «вниз» на Windows даёт delta < 0, поэтому знак инвертируется:
        # колесо вниз → +1 (вниз/вправо), вверх → -1 (вверх/влево) — TZ fix 2
        delta = e.delta
        if delta == 0:
            return "break"
        steps = -delta // 120 if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        canvas, axis = target
        if axis == "y":
            canvas.yview_scroll(steps, "units")
        else:
            canvas.xview_scroll(steps, "units")
        return "break"

    # ---------- код / папка ----------
    def _copy_code(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.code_text.get("1.0", "end-1c"))
        self._set_status("Код скопирован в буфер обмена", "ok")

    def _open_outdir(self):
        d = self.out_dir.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)  # только Windows

    def _set_status(self, text, kind="info"):
        self._status_kind = kind
        color = {"info": self.T["muted"], "ok": self.T["ok"], "err": self.T["err"]}[kind]
        self.status.configure(text=text, fg=color)

    # ---------- состояние проекта: dirty / заголовок / подтверждение ----------
    def _mark_dirty(self):
        if self._loading:
            return
        if not self._dirty:
            self._dirty = True
            self._update_title()

    def _clear_dirty(self):
        if self._dirty:
            self._dirty = False
            self._update_title()

    def _update_title(self):
        """«Новый проект» / «имя файла*» — GraphLab; * — есть несохранённое."""
        if self.project_path:
            name = os.path.splitext(os.path.basename(self.project_path))[0]
        else:
            name = "Новый проект"
        if self._dirty:
            name += "*"
        self.root.title(f"{name} — GraphLab")

    def _confirm_discard(self):
        """Да/Нет/Отмена перед потерей несохранённых изменений."""
        if not self._dirty:
            return True
        ans = messagebox.askyesnocancel(
            "Несохранённые изменения",
            "В проекте есть несохранённые изменения.\n\n"
            "Сохранить их перед продолжением?")
        if ans is None:
            return False
        if ans:
            return self._save_current()
        return True

    def _save_current(self):
        """Сохраняет в текущий файл (или через «Сохранить как…»). True — успех."""
        if not self.project_path:
            return self._menu_save_project_as()
        try:
            self.save_project(self.project_path)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить проект:\n{e}")
            return False
        self._clear_dirty()
        self._set_status(f"Проект сохранён: {self.project_path}", "ok")
        return True

    def _menu_new_project(self):
        """«Новый проект»: сброс к значениям по умолчанию, без файла."""
        if not self._confirm_discard():
            return
        self._loading = True
        try:
            for ln in list(self.lines):
                try:
                    ln.frame.destroy()
                except tk.TclError:
                    pass
            self.lines.clear()
            self._line_counter = 0
            self.x_file.set("")
            self.title_var.set("График")
            self.xlabel_var.set("X")
            self.ylabel_var.set("Y")
            self.out_dir.set(app_dir())
            self.combined.set(False)
            self.combined_name.set("combined")
            self.fit_preview.set(False)
            self._toggle_combined()
            self._update_code("")
            self._clear_preview_tabs()
            self.add_line()
        finally:
            self._loading = False
        self.project_path = None
        self._dirty = False
        self._update_title()
        self._set_status("Новый проект", "info")

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
        """Восстанавливает состояние из словаря проекта (папка — base_dir).

        Изменения полей во время загрузки не помечают проект «испорченным».
        """
        self._loading = True
        try:
            self._load_project_data(data, base_dir)
        finally:
            self._loading = False

    def _load_project_data(self, data, base_dir):
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
            idx = self._line_counter
            self._line_counter += 1
            ln = YLine(self.lines_frame, self, idx)
            ln.path_var.set(resolve(item.get("path", "")))
            ln.legend_var.set(item.get("legend", f"линия {idx + 1}"))
            ln.start_var.set(self._to_int(item.get("start", 4), 4))
            ln.color = item.get("color") or PALETTE[idx % len(PALETTE)]
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

        # после восстановления — «Новый проект» с данными (без привязки к файлу)
        self.project_path = None
        self._dirty = False
        self._update_title()

    def _on_close(self):
        if not self._confirm_discard():
            return
        self._autosave()
        self.root.destroy()

    # ---------- меню: проекты ----------
    def _menu_save_project(self):
        """«Сохранить»: в текущий файл, а если его нет — через «Сохранить как…»."""
        self._save_current()

    def _menu_save_project_as(self):
        """«Сохранить как…»: выбор .gslab файла и запись туда. True — успех."""
        path = filedialog.asksaveasfilename(
            title="Сохранить проект", defaultextension=".gslab",
            filetypes=[("Проекты GraphLab", "*.gslab")])
        if not path:
            return False
        try:
            self.save_project(path)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить проект:\n{e}")
            return False
        self.project_path = os.path.abspath(path)
        self._clear_dirty()
        self._update_title()
        self._set_status(f"Проект сохранён: {path}", "ok")
        return True

    def _menu_open_project(self):
        path = filedialog.askopenfilename(
            title="Открыть проект",
            filetypes=[("Проекты GraphLab", "*.gslab"), ("Все файлы", "*.*")])
        if not path:
            return
        if not self._confirm_discard():
            return
        if self.load_project(path):
            self.project_path = os.path.abspath(path)
            self._clear_dirty()
            self._update_title()


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
