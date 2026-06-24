# Copyright (C) 2026 [EastFt/小心二次元]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""卡牌游戏日常任务自动化 — GUI 控制面板。"""

from __future__ import annotations

import re
import sys
import time
import queue
import threading
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox
import yaml

from utils.paths import base_dir, exe_dir

PROJECT_DIR = base_dir()
EXE_DIR = exe_dir()
CONFIG_PATH = EXE_DIR / "config.yaml"
BG = "#eeeeee"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


class TaskRunner(threading.Thread):

    def __init__(self, log_queue: queue.Queue):
        super().__init__(daemon=True)
        self._log_queue = log_queue
        self._stop_flag = threading.Event()

    def stop(self):
        self._stop_flag.set()

    def run(self):
        """内联运行调度器，捕获 loguru 输出。"""
        from loguru import logger

        class QueueSink:
            def write(self, msg):
                if self._stop.is_set():
                    return
                # loguru 的格式化消息
                record = msg.strip()
                if not record:
                    return
                # 去掉 ANSI
                clean = strip_ansi(record)
                if not clean:
                    return
                # 检测任务开始/结束
                if '开始执行' in clean and '[' in clean:
                    m = re.search(r'\[(\w+)\]', clean)
                    if m:
                        self._q.put(("task_start", m.group(1)))
                elif ('执行成功' in clean or '执行失败' in clean) and '[' in clean:
                    m = re.search(r'\[(\w+)\]', clean)
                    if m:
                        self._q.put(("task_end", m.group(1)))
                self._q.put(("log", clean))

        sink = QueueSink()
        sink._stop = self._stop_flag
        sink._q = self._log_queue

        handler_id = logger.add(sink, format="{time:HH:mm:ss} | {level: <7} | {message}",
                                level="INFO", colorize=False)

        self._log_queue.put(("info", "Starting tasks..."))
        try:
            from core.adb_controller import ADBFatalError
            from config.settings import AppConfig
            from core.adb_controller import ADBController
            from core.device import Device
            from core.vision import VisionEngine
            from core.action import Action
            from scheduler.engine import Scheduler

            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            config = AppConfig(**data)

            # ADB
            adb_path = config.adb.adb_path
            if adb_path == "auto":
                adb_path = str(EXE_DIR / "platform-tools" / "adb.exe")
                if not Path(adb_path).exists():
                    # 尝试源码目录
                    alt = PROJECT_DIR / "platform-tools" / "adb.exe"
                    if alt.exists():
                        adb_path = str(alt)

            from utils.mumu_detector import get_adb_path, detect_mumu_device

            device_addr = config.adb.device_addr
            if device_addr == "auto":
                detected = detect_mumu_device(adb_path)
                if detected:
                    device_addr = detected

            adb = ADBController(device_addr=device_addr, adb_path=adb_path,
                                connect_timeout=config.adb.connect_timeout)
            if not adb.connect():
                self._log_queue.put(("error", f"Cannot connect to {device_addr}"))
                self._log_queue.put(("done", ""))
                logger.remove(handler_id)
                return

            if self._stop_flag.is_set():
                logger.remove(handler_id)
                self._log_queue.put(("done", ""))
                return

            device = Device(adb)
            assets_dir = str(PROJECT_DIR / "assets")  # 始终用项目内置资源
            vision = VisionEngine(assets_dir=assets_dir)
            action = Action(device, vision)

            scheduler = Scheduler(config=config, adb=adb, device=device,
                                  vision=vision, action=action)

            if self._stop_flag.is_set():
                logger.remove(handler_id)
                self._log_queue.put(("done", ""))
                return

            scheduler.run_once()
            adb.disconnect()

        except ADBFatalError as e:
            self._log_queue.put(("error", f"FATAL: {e}"))
        except Exception as e:
            import traceback
            self._log_queue.put(("error", f"Error: {e}"))
            self._log_queue.put(("log", traceback.format_exc()))
        finally:
            try:
                logger.remove(handler_id)
            except Exception:
                pass
        self._log_queue.put(("done", ""))



class App(tk.Tk):

    NAME_MAP = {
        "daily_signin": "福利", "daily_quest": "每日任务",
        "collect_mail": "邮件", "friends": "好友",
        "guild": "联盟", "events": "活动",
        "treasure_hunt": "夺宝奇兵",
        "arena": "竞技场", "auto_battle": "出战",
        "divine_arena": "神域",
    }

    # 导航项: (内部 key, 显示名)
    NAV_ITEMS = [
        ("overview",     "总览"),
        ("daily_signin", "福利"),
        ("daily_quest",  "每日任务"),
        ("collect_mail", "邮件"),
        ("friends",      "好友"),
        ("guild",        "联盟"),
        ("events",       "活动"),
        ("treasure_hunt","夺宝奇兵"),
        ("arena",        "竞技场"),
        ("auto_battle",  "出战"),
        ("divine_arena", "神域"),
    ]

    GOLD = "#F2A7A7"

    DEFAULT_PRIORITIES = {
        "daily_signin": 1, "daily_quest": 2, "collect_mail": 3, "friends": 5,
        "events": 8, "treasure_hunt": 12, "guild": 15, "arena": 20, "auto_battle": 25,
        "divine_arena": 30,
    }

    def __init__(self):
        super().__init__()
        self.title("I'm Yours")
        self.geometry("1280x880")
        self.minsize(960, 660)
        self.configure(bg=BG)
        self.overrideredirect(True)
        self._maximized = False
        self._normal_geom = ""

        icon_path = PROJECT_DIR / "assets" / "icon.png"
        if icon_path.exists():
            try:
                img = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, img)
                self._icon_ref = img
            except Exception:
                pass

        # 自定义选择框图片
        cb_off = PROJECT_DIR / "assets" / "checkbox_unchecked.png"
        cb_on = PROJECT_DIR / "assets" / "checkbox_checked.png"
        self._cb_img_off = tk.PhotoImage(file=str(cb_off)) if cb_off.exists() else None
        self._cb_img_on = tk.PhotoImage(file=str(cb_on)) if cb_on.exists() else None

        self._config = load_config()
        self._runner: TaskRunner | None = None
        self._log_queue = queue.Queue()
        self._running = False
        self._pending_tasks = []

        # 导航+视图状态
        self._nav_indicators: dict[str, tk.Frame] = {}
        self._nav_labels: dict[str, tk.Label] = {}
        self._views: dict[str, tk.Frame] = {}
        self._current_nav = "overview"

        self._build_layout()
        self._update_queue_display()
        self._poll_log_queue()
        self.bind("<Escape>", self._on_close)
        self.after(100, self._fix_taskbar)
        self.after(200, self._apply_round)

    # ── 任务栏 ────────────────────────────────────

    def _fix_taskbar(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00040000)
            self.withdraw()
            self.after(50, self.deiconify)
        except Exception:
            pass

    # ── 标题栏拖动 ────────────────────────────────

    def _drag_start(self, event):
        if self._maximized:
            return
        self._dx = event.x_root - self.winfo_x()
        self._dy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        if self._maximized:
            return
        self.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def _on_minimize(self):
        self.overrideredirect(False)
        self.iconify()
        self.after(200, lambda: self.overrideredirect(True))

    def _on_maximize(self):
        if self._maximized:
            self.geometry(self._normal_geom)
            self._maximized = False
        else:
            self._normal_geom = self.geometry()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight() - 40
            self.geometry(f"{sw}x{sh}+0+0")
            self._maximized = True
        self.after(100, self._apply_round)

    # ── 卡片组件 ──────────────────────────────────

    def _card(self, parent, fill=tk.X, expand=False, **kw):
        outer = tk.Frame(parent, bg="#cccccc")
        outer.pack(fill=fill, expand=expand, **kw)
        inner_fill = tk.BOTH if fill == tk.BOTH else tk.X
        inner = tk.Frame(outer, bg="white")
        inner.pack(fill=inner_fill, expand=expand, padx=1, pady=1)
        return inner

    # ── 圆角 ──────────────────────────────────────

    def _apply_round(self):
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            w, h = self.winfo_width(), self.winfo_height()
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, 12, 12)
            ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
        except Exception:
            pass

    # ── 自定义复选框 ──────────────────────────────────

    def _create_checkbox(self, parent, variable, command):
        """创建一个使用自定义图片的 Checkbutton（无文字指示器）。

        使用 assets/checkbox_unchecked.png（未选中）
        和 assets/checkbox_checked.png（选中）替代默认方框。
        图片引用保存在 self._cb_img_off / self._cb_img_on 防止 GC。
        """
        return tk.Checkbutton(
            parent,
            variable=variable,
            command=command,
            image=self._cb_img_off,
            selectimage=self._cb_img_on,
            indicatoron=False,
            bg="white",
            activebackground="white",
            relief=tk.FLAT,
            borderwidth=0,
            cursor="hand2",
        )

    # ═══════════════════════════════════════════════
    #  整体布局
    # ═══════════════════════════════════════════════

    def _build_layout(self):
        # 窗口边框色 (灰色细线)
        self.configure(bg="#cccccc")

        # 内容容器
        content = tk.Frame(self, bg=BG)
        content.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # === 自定义标题栏 ===
        self._title_bar = tk.Frame(content, bg="white", height=50, cursor="arrow")
        self._title_bar.pack(fill=tk.X)
        self._title_bar.pack_propagate(False)

        # 底部阴影
        tk.Frame(content, bg="#dddddd", height=1).pack(fill=tk.X)
        tk.Frame(content, bg="#eeeeee", height=1).pack(fill=tk.X)

        # 图标
        icon_path = PROJECT_DIR / "assets" / "icon.png"
        if icon_path.exists():
            try:
                from PIL import Image, ImageDraw, ImageTk
                img = Image.open(icon_path).convert("RGBA")
                img = img.resize((40, 40), Image.LANCZOS)
                mask = Image.new("L", (40, 40), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, 40, 40), fill=255)
                img.putalpha(mask)
                self._title_icon = ImageTk.PhotoImage(img)
                tk.Label(self._title_bar, image=self._title_icon, bg="white").pack(
                    side=tk.LEFT, padx=(12, 6), pady=5)
            except Exception:
                pass

        # 标题
        tk.Label(
            self._title_bar, text="I'm Yours", anchor=tk.W,
            font=("Microsoft YaHei", 14, "normal"), bg="white", fg="#333333",
        ).pack(side=tk.LEFT)

        # 窗口按钮
        btn_frame = tk.Frame(self._title_bar, bg="white")
        btn_frame.pack(side=tk.RIGHT, padx=4)
        for sym, cmd in [("─", self._on_minimize), ("□", self._on_maximize), ("✕", self._on_close)]:
            btn = tk.Button(
                btn_frame, text=sym, command=cmd,
                font=("", 12), bg="white", fg="#333333",
                activebackground="#eeeeee", activeforeground="#333333",
                relief=tk.FLAT, borderwidth=0, padx=14, pady=2, cursor="hand2",
            )
            btn.pack(side=tk.LEFT)
            if sym == "✕":
                btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#e81123", fg="white"))
                btn.bind("<Leave>", lambda e, b=btn: b.configure(bg="white", fg="#333333"))

        # 拖动绑定
        for w in [self._title_bar] + list(self._title_bar.winfo_children()):
            if not isinstance(w, tk.Button):
                w.bind("<Button-1>", self._drag_start)
                w.bind("<B1-Motion>", self._drag_move)
        self._title_bar.bind("<Double-Button-1>", lambda e: self._on_maximize())

        # === 主体行：侧栏 + 内容栈 ===
        main_row = tk.Frame(content, bg=BG)
        main_row.pack(fill=tk.BOTH, expand=True)

        # ── 最左侧栏（主页 / IY） ──
        top_sidebar = tk.Frame(main_row, bg="white", width=55)
        top_sidebar.pack(side=tk.LEFT, fill=tk.Y)
        top_sidebar.pack_propagate(False)

        # 主页 行（指示器 + 标签）
        home_row = tk.Frame(top_sidebar, bg="white", cursor="hand2")
        home_row.pack(fill=tk.X, pady=(20, 8))
        self._sidebar_home_indicator = tk.Frame(home_row, bg="white", width=3)
        self._sidebar_home_indicator.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar_home_indicator.pack_propagate(False)
        self._sidebar_home_lbl = tk.Label(
            home_row, text="主页", anchor=tk.CENTER,
            font=("Microsoft YaHei", 12, "bold"), bg="white", fg="#555555",
            cursor="hand2",
        )
        self._sidebar_home_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        for w in (home_row, self._sidebar_home_indicator, self._sidebar_home_lbl):
            w.bind("<Button-1>", lambda e: self._show_home())

        tk.Frame(top_sidebar, bg="#dddddd", height=1).pack(fill=tk.X, padx=8)

        # IY 行（指示器 + 标签，默认选中）
        iy_row = tk.Frame(top_sidebar, bg="white", cursor="hand2")
        iy_row.pack(fill=tk.X, pady=(8, 20))
        self._sidebar_iy_indicator = tk.Frame(iy_row, bg="#F2A7A7", width=3)
        self._sidebar_iy_indicator.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar_iy_indicator.pack_propagate(False)
        self._sidebar_iy_lbl = tk.Label(
            iy_row, text="IY", anchor=tk.CENTER,
            font=("Microsoft YaHei", 12, "bold"), bg="white", fg="#F2A7A7",
            cursor="hand2",
        )
        self._sidebar_iy_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        for w in (iy_row, self._sidebar_iy_indicator, self._sidebar_iy_lbl):
            w.bind("<Button-1>", lambda e: self._show_overview())

        # 侧栏右边框线
        tk.Frame(main_row, bg="#dddddd", width=1).pack(side=tk.LEFT, fill=tk.Y)

        # ── 内容栈（IY 主界面 / 主页子页面 切换） ──
        main_stack = tk.Frame(main_row, bg=BG)
        main_stack.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        main_stack.grid_rowconfigure(0, weight=1)
        main_stack.grid_columnconfigure(0, weight=1)

        # 层 1：IY 主界面（左侧导航 + 右侧内容）
        iy_frame = tk.Frame(main_stack, bg=BG)
        iy_frame.grid(row=0, column=0, sticky="nsew")

        cols = tk.Frame(iy_frame, bg=BG)
        cols.pack(fill=tk.BOTH, expand=True)

        # 左列导航
        left_outer = tk.Frame(cols, bg="#cccccc", width=192)
        left_outer.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))
        left_outer.pack_propagate(False)

        nav_inner = tk.Frame(left_outer, bg="white")
        nav_inner.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self._build_nav(nav_inner)

        # 右列内容区
        right_outer = tk.Frame(cols, bg="#cccccc")
        right_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 8))

        right_inner = tk.Frame(right_outer, bg="white")
        right_inner.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self._build_content(right_inner)

        # 层 2：主页子页面
        home_frame = self._build_home_page(main_stack)
        home_frame.grid(row=0, column=0, sticky="nsew")

        # 默认显示 IY 主界面
        iy_frame.tkraise()

        self._iy_frame = iy_frame
        self._home_frame = home_frame

        # 默认选中总览
        self._switch_view("overview")

    # ═══════════════════════════════════════════════
    #  左侧导航
    # ═══════════════════════════════════════════════

    NAV_STRUCTURE = [
        ("item",   "overview",      "总览"),
        ("group",  "每日", [
            ("daily_signin", "福利"),
            ("collect_mail", "邮件"),
            ("friends",      "好友"),
            ("guild",        "联盟"),
            ("daily_quest",  "每日任务"),
        ]),
        ("group",  "出击", [
            ("events",       "活动"),
            ("auto_battle",  "出战"),
            ("arena",        "竞技场"),
        ]),
        ("item",   "divine_arena",  "神域"),
        ("group",  "限时活动", [
            ("treasure_hunt", "夺宝奇兵"),
        ]),
    ]

    def _build_nav(self, parent: tk.Frame):
        """构建左侧导航：可折叠分组。"""
        for w in parent.winfo_children():
            w.destroy()

        spacer = tk.Frame(parent, bg="white", height=12)
        spacer.pack(fill=tk.X)

        self._nav_group_frames: dict[str, tk.Frame] = {}
        self._nav_group_arrows: dict[str, tk.Label] = {}
        self._nav_group_headers: dict[str, tk.Frame] = {}
        _COLLAPSED_DEFAULT = {"出击", "限时活动"}

        for item in self.NAV_STRUCTURE:
            kind = item[0]
            if kind == "item":
                key, display = item[1], item[2]
                self._add_nav_row(parent, key, display)

            elif kind == "group":
                group_name = item[1]
                children = item[2]

                # 组标题行
                header_row = tk.Frame(parent, bg="white", height=44, cursor="hand2")
                header_row.pack(fill=tk.X)
                header_row.pack_propagate(False)

                start_expanded = group_name not in _COLLAPSED_DEFAULT
                arrow_text = "▼" if start_expanded else "▶"

                arrow_lbl = tk.Label(
                    header_row, text=arrow_text, anchor=tk.W,
                    font=("Microsoft YaHei", 12, "normal"),
                    bg="white", fg="#888888", cursor="hand2",
                    width=2,
                )
                arrow_lbl.pack(side=tk.LEFT, padx=(6, 0))

                name_lbl = tk.Label(
                    header_row, text=group_name, anchor=tk.W,
                    font=("Microsoft YaHei", 14, "normal"),
                    bg="white", fg="black", cursor="hand2",
                )
                name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 8))

                # 子项容器
                children_frame = tk.Frame(parent, bg="white")
                if start_expanded:
                    children_frame.pack(fill=tk.X)

                for child_key, child_display in children:
                    self._add_nav_row(children_frame, child_key, child_display, indent=True)

                self._nav_group_frames[group_name] = children_frame
                self._nav_group_arrows[group_name] = arrow_lbl
                self._nav_group_headers[group_name] = header_row

                # 点击切换展开/折叠
                def make_toggle(hrow=header_row, arrow=arrow_lbl, cframe=children_frame):
                    def toggle(e):
                        if cframe.winfo_ismapped():
                            cframe.pack_forget()
                            arrow.configure(text="▶")
                        else:
                            cframe.pack(fill=tk.X, after=hrow)
                            arrow.configure(text="▼")
                    return toggle

                for w in (header_row, arrow_lbl, name_lbl):
                    w.bind("<Button-1>", make_toggle())

    def _add_nav_row(self, parent: tk.Frame, key: str, display: str, indent: bool = False):
        """添加单个导航行。"""
        row = tk.Frame(parent, bg="white", height=44, cursor="hand2")
        row.pack(fill=tk.X)
        row.pack_propagate(False)

        # 缩进
        if indent:
            tk.Frame(row, bg="white", width=20).pack(side=tk.LEFT)

        # 金色指示条
        indicator = tk.Frame(row, bg="white", width=4)
        indicator.pack(side=tk.LEFT, fill=tk.Y)
        indicator.pack_propagate(False)

        # 文字标签
        font_size = 13 if indent else 14
        label = tk.Label(
            row, text=display, anchor=tk.W,
            font=("Microsoft YaHei", font_size, "normal"),
            bg="white", fg="black", cursor="hand2",
        )
        label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 8))

        for w in (row, indicator, label):
            w.bind("<Button-1>", lambda e, k=key: self._switch_view(k))

        self._nav_indicators[key] = indicator
        self._nav_labels[key] = label

    def _highlight_nav(self, name: str):
        """重置所有导航项样式，然后高亮指定项。"""
        # 重置所有
        for key, indicator in self._nav_indicators.items():
            indicator.configure(bg="white")
        for key, label in self._nav_labels.items():
            label.configure(font=("Microsoft YaHei", 14, "normal"), fg="black")

        # 高亮选中
        if name in self._nav_indicators:
            self._nav_indicators[name].configure(bg=self.GOLD)
        if name in self._nav_labels:
            self._nav_labels[name].configure(
                font=("Microsoft YaHei", 14, "bold"), fg=self.GOLD)
        self._current_nav = name

    # ═══════════════════════════════════════════════
    #  右侧内容区 + 子视图
    # ═══════════════════════════════════════════════

    def _build_content(self, parent: tk.Frame):
        """构建右侧内容区，使用 grid 堆叠所有子视图。"""
        # 内容容器 — 使用 grid 实现子视图堆叠
        container = tk.Frame(parent, bg=BG)
        container.pack(fill=tk.BOTH, expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # ── 总览视图（状态 + 日志） ──
        self._views["overview"] = self._build_overview_view(container)

        # ── 7 个任务配置视图 ──
        for key, display in self.NAV_ITEMS:
            if key == "overview":
                continue
            self._views[key] = self._build_task_config_view(container, key, display)

        # 所有子视图 grid 到同一 cell
        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

    def _switch_view(self, name: str):
        """切换到指定子视图并更新导航高亮。"""
        if name in self._views:
            self._views[name].tkraise()
        self._highlight_nav(name)
        # 若目标在折叠分组中，自动展开
        self._auto_expand_for(name)

    def _auto_expand_for(self, key: str):
        """如果 key 在某折叠分组中，自动展开该分组。"""
        for item in self.NAV_STRUCTURE:
            if item[0] == "group":
                group_name = item[1]
                children_keys = [c[0] for c in item[2]]
                if key in children_keys:
                    frame = self._nav_group_frames.get(group_name)
                    arrow = self._nav_group_arrows.get(group_name)
                    header = self._nav_group_headers.get(group_name)
                    if frame is not None and arrow is not None and header is not None:
                        if not frame.winfo_ismapped():
                            frame.pack(fill=tk.X, after=header)
                            arrow.configure(text="▼")
                    return

    # ── 总览视图 ──────────────────────────────────

    def _build_overview_view(self, container: tk.Frame) -> tk.Frame:
        """构建总览视图：状态卡片 + 日志（日志宽度缩减）。"""
        view = tk.Frame(container, bg=BG)
        view.grid_columnconfigure(0, weight=40)   # 状态列
        view.grid_columnconfigure(1, weight=0)    # 分隔线
        view.grid_columnconfigure(2, weight=35)   # 日志列（缩减）
        view.grid_rowconfigure(0, weight=1)

        # === 左侧：状态卡片列 ===
        status_col = tk.Frame(view, bg=BG)
        status_col.grid(row=0, column=0, sticky="nsew")

        # 启动按钮
        card1 = self._card(status_col, pady=(8, 5), padx=(16, 4))
        self._btn_action = tk.Button(
            card1, text="启动", command=self._on_action,
            font=("Microsoft YaHei", 16, "normal"),
            bg="#F2A7A7", fg="white",
            activebackground="#e09090", activeforeground="white",
            relief=tk.FLAT, cursor="hand2", borderwidth=0,
            width=4, height=1,
        )
        self._btn_action.pack(anchor=tk.W, padx=16, pady=12)

        # 运行中
        card2 = self._card(status_col, pady=5, padx=(16, 4))
        tk.Label(
            card2, text="运行中：", anchor=tk.W,
            font=("Microsoft YaHei", 16, "normal"), bg="white", fg="black",
        ).pack(fill=tk.X, padx=16, pady=(12, 4))
        tk.Frame(card2, bg="#dddddd", height=1).pack(fill=tk.X, padx=16)
        self._lbl_running = tk.Label(
            card2, text="  -", anchor=tk.W,
            font=("Microsoft YaHei", 16), bg="white", fg="#555555",
        )
        self._lbl_running.pack(fill=tk.X, padx=24, pady=(4, 12))

        # 队列中
        card3 = self._card(status_col, pady=5, padx=(16, 4))
        tk.Label(
            card3, text="队列中：", anchor=tk.W,
            font=("Microsoft YaHei", 16, "normal"), bg="white", fg="black",
        ).pack(fill=tk.X, padx=16, pady=(12, 4))
        tk.Frame(card3, bg="#dddddd", height=1).pack(fill=tk.X, padx=16)
        self._queue_frame = tk.Frame(card3, bg="white")
        self._queue_frame.pack(fill=tk.X, padx=24, pady=(4, 12))

        # 已完成
        card4 = self._card(status_col, pady=(5, 8), padx=(16, 4), fill=tk.BOTH, expand=True)
        tk.Label(
            card4, text="已完成：", anchor=tk.W,
            font=("Microsoft YaHei", 16, "normal"), bg="white", fg="black",
        ).pack(fill=tk.X, padx=16, pady=(12, 4))
        tk.Frame(card4, bg="#dddddd", height=1).pack(fill=tk.X, padx=16)
        self._done_frame = tk.Frame(card4, bg="white")
        self._done_frame.pack(fill=tk.X, padx=24, pady=(4, 12))

        # 左右分隔
        tk.Frame(view, bg=BG, width=10).grid(row=0, column=1, sticky="ns")

        # 日志列（无白色背景，间隔为页面背景色）
        log_col = tk.Frame(view, bg=BG)
        log_col.grid(row=0, column=2, sticky="nsew")

        # 日志标题框（卡片，与启动按钮同高）
        log_hdr_card = self._card(log_col, pady=(8, 0), padx=(0, 10))
        tk.Label(
            log_hdr_card, text="日志", anchor=tk.W,
            font=("Microsoft YaHei", 16, "normal"), bg="white", fg="black",
        ).pack(side=tk.LEFT, padx=16, pady=16)
        tk.Button(
            log_hdr_card, text="清空", command=self._clear_log,
            font=("Microsoft YaHei", 12), bg="#f0f0f0", fg="#555555",
            relief=tk.FLAT, padx=12, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=16, pady=16)

        # 10px 间隔（页面背景色）
        tk.Frame(log_col, bg=BG, height=10).pack(fill=tk.X, padx=(0, 10))

        # 日志内容框（卡片，填充剩余空间）
        log_content_card = self._card(log_col, fill=tk.BOTH, expand=True, pady=(0, 8), padx=(0, 10))

        self._log_text = tk.Text(
            log_content_card,
            font=("Consolas", 10), bg="white", fg="#333333",
            relief=tk.FLAT, borderwidth=0, wrap=tk.WORD,
            state=tk.DISABLED, padx=8, pady=8,
        )
        scrollbar = ttk.Scrollbar(log_content_card, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)

        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        return view

    # ── 主页子页面 ──────────────────────────────

    def _build_home_page(self, container: tk.Frame) -> tk.Frame:
        """构建主页子页面：左侧标签栏 + 右侧内容区（通用设置 / 说明）。"""
        page = tk.Frame(container, bg="white")
        page.grid_columnconfigure(0, weight=0)    # 标签栏
        page.grid_columnconfigure(1, weight=0)    # 分隔线
        page.grid_columnconfigure(2, weight=1)    # 内容区
        page.grid_rowconfigure(0, weight=1)

        # ── 标签栏 ──
        tab_bar = tk.Frame(page, bg="white", width=120)
        tab_bar.grid(row=0, column=0, sticky="ns")
        tab_bar.grid_propagate(False)

        self._home_tab_settings_lbl = tk.Label(
            tab_bar, text="通用设置", anchor=tk.W,
            font=("Microsoft YaHei", 14, "bold"), bg="white", fg="#F2A7A7",
            cursor="hand2", padx=16, pady=10,
        )
        self._home_tab_settings_lbl.pack(fill=tk.X)
        self._home_tab_settings_lbl.bind("<Button-1>", lambda e: self._show_home_tab("settings"))

        self._home_tab_about_lbl = tk.Label(
            tab_bar, text="说明", anchor=tk.W,
            font=("Microsoft YaHei", 14, "normal"), bg="white", fg="black",
            cursor="hand2", padx=16, pady=10,
        )
        self._home_tab_about_lbl.pack(fill=tk.X)
        self._home_tab_about_lbl.bind("<Button-1>", lambda e: self._show_home_tab("about"))

        # ── 分隔线 ──
        tk.Frame(page, bg="#dddddd", width=1).grid(row=0, column=1, sticky="ns")

        # ── 内容栈 ──
        tab_content = tk.Frame(page, bg="white")
        tab_content.grid(row=0, column=2, sticky="nsew")
        tab_content.grid_rowconfigure(0, weight=1)
        tab_content.grid_columnconfigure(0, weight=1)

        # === 通用设置页 ===
        settings_page = tk.Frame(tab_content, bg="white")
        settings_page.grid(row=0, column=0, sticky="nsew")

        tk.Label(
            settings_page, text="通用设置", font=("Microsoft YaHei", 22, "bold"),
            bg="white", fg="#333333",
        ).pack(anchor=tk.W, padx=24, pady=(20, 12))

        tk.Frame(settings_page, bg="#dddddd", height=1).pack(fill=tk.X, padx=24)

        # 设备地址区
        dev_frame = tk.Frame(settings_page, bg="white")
        dev_frame.pack(fill=tk.X, padx=24, pady=(16, 8))

        tk.Label(
            dev_frame, text="设备地址：", font=("Microsoft YaHei", 14),
            bg="white", fg="black",
        ).pack(anchor=tk.W)

        entry_row = tk.Frame(dev_frame, bg="white")
        entry_row.pack(fill=tk.X, pady=(8, 8))

        adb_config = self._config.get("adb", {})
        current_device = adb_config.get("device_addr", "auto")
        self._device_var = tk.StringVar(value=current_device)
        self._device_var.trace_add(
            "write",
            lambda *_, v=self._device_var: self._save_device_addr(v.get()),
        )
        self._device_entry = tk.Entry(
            entry_row, textvariable=self._device_var,
            font=("Microsoft YaHei", 12), width=24,
            relief=tk.SOLID, borderwidth=1,
        )
        self._device_entry.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_detect_device = tk.Button(
            entry_row, text="检测设备", command=self._on_detect_device,
            font=("Microsoft YaHei", 11), bg="#e8e8e8", fg="#333333",
            activebackground="#d0d0d0", activeforeground="#333333",
            relief=tk.FLAT, padx=12, pady=2, cursor="hand2",
        )
        self._btn_detect_device.pack(side=tk.LEFT)

        # 说明文字
        help_text = (
            "默认使用 auto 模式，自动匹配地址\n"
            "如果失败（说明启动了多个模拟器，或未启动模拟器），请手动输入地址\n"
            "在模拟器内查询 WIFI 的 IP 地址，附上 :7555 或 :16384，"
            "用 WIFI 地址替换前面的 IP\n"
            "常用地址为 127.0.0.1:7555 或 127.0.0.1:16384"
        )
        tk.Label(
            dev_frame, text=help_text,
            font=("Microsoft YaHei", 11), bg="white", fg="#888888",
            justify=tk.LEFT, wraplength=520,
        ).pack(anchor=tk.W, pady=(12, 0))

        # === 说明页 ===
        about_page = tk.Frame(tab_content, bg="white")
        about_page.grid(row=0, column=0, sticky="nsew")
        about_page.grid_rowconfigure(0, weight=0)  # 标题
        about_page.grid_rowconfigure(1, weight=0)  # 分隔线
        about_page.grid_rowconfigure(2, weight=1)  # 文本区
        about_page.grid_columnconfigure(0, weight=1)

        tk.Label(
            about_page, text="使用说明", font=("Microsoft YaHei", 22, "bold"),
            bg="white", fg="#333333",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 12))

        tk.Frame(about_page, bg="#dddddd", height=1).grid(row=1, column=0, sticky="ew", padx=24)

        # 文本区域（从外部 txt 读取）
        text_frame = tk.Frame(about_page, bg="white")
        text_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(12, 16))
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self._about_text = tk.Text(
            text_frame,
            font=("Microsoft YaHei", 12), bg="white", fg="#333333",
            relief=tk.FLAT, borderwidth=0, wrap=tk.WORD,
            padx=8, pady=8, state=tk.DISABLED,
        )
        about_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self._about_text.yview)
        self._about_text.configure(yscrollcommand=about_scroll.set)
        self._about_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        about_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 默认显示通用设置
        settings_page.tkraise()

        self._home_settings_page = settings_page
        self._home_about_page = about_page

        return page

    def _show_home(self):
        """切换到主页子页面。"""
        self._home_frame.tkraise()
        self._sidebar_home_indicator.configure(bg="#F2A7A7")
        self._sidebar_home_lbl.configure(fg="#F2A7A7", font=("Microsoft YaHei", 12, "bold"))
        self._sidebar_iy_indicator.configure(bg="white")
        self._sidebar_iy_lbl.configure(fg="#555555", font=("Microsoft YaHei", 12, "bold"))
        # 默认显示通用设置
        self._show_home_tab("settings")

    def _show_overview(self):
        """切换回 IY 主界面。"""
        self._iy_frame.tkraise()
        self._sidebar_iy_indicator.configure(bg="#F2A7A7")
        self._sidebar_iy_lbl.configure(fg="#F2A7A7", font=("Microsoft YaHei", 12, "bold"))
        self._sidebar_home_indicator.configure(bg="white")
        self._sidebar_home_lbl.configure(fg="#555555", font=("Microsoft YaHei", 12, "bold"))

    def _show_home_tab(self, tab: str):
        """切换主页子页面的标签页。"""
        if tab == "settings":
            self._home_settings_page.tkraise()
            self._home_tab_settings_lbl.configure(fg="#F2A7A7", font=("Microsoft YaHei", 14, "bold"))
            self._home_tab_about_lbl.configure(fg="black", font=("Microsoft YaHei", 14, "normal"))
        else:
            self._home_about_page.tkraise()
            self._home_tab_about_lbl.configure(fg="#F2A7A7", font=("Microsoft YaHei", 14, "bold"))
            self._home_tab_settings_lbl.configure(fg="black", font=("Microsoft YaHei", 14, "normal"))
            # 从外部 txt 文件刷新内容
            self._refresh_about_text()

    def _refresh_about_text(self):
        """从外部 txt 文件读取使用说明并显示。"""
        guide_path = PROJECT_DIR / "assets" / "使用说明.txt"
        try:
            if guide_path.exists():
                text = guide_path.read_text(encoding="utf-8")
            else:
                text = "（使用说明文件不存在，请在 assets/使用说明.txt 中编写内容）"
        except Exception as e:
            text = f"（读取使用说明失败: {e}）"

        self._about_text.configure(state=tk.NORMAL)
        self._about_text.delete("1.0", tk.END)
        self._about_text.insert("1.0", text)
        self._about_text.configure(state=tk.DISABLED)

    # ── 通用任务配置视图 ───────────────────────────

    def _build_task_config_view(
        self, container: tk.Frame, task_key: str, display_name: str
    ) -> tk.Frame:
        """构建通用任务配置子页面。"""
        view = tk.Frame(container, bg="white")

        task_config = self._get_task_config(task_key)

        # ── 标题 ──
        hdr = tk.Frame(view, bg="white")
        hdr.pack(fill=tk.X, padx=24, pady=(20, 12))
        tk.Label(
            hdr, text=display_name, font=("Microsoft YaHei", 22, "bold"),
            bg="white", fg="#333333",
        ).pack(side=tk.LEFT)

        tk.Frame(view, bg="#dddddd", height=1).pack(fill=tk.X, padx=24)

        # ── 内容区 ──
        content = tk.Frame(view, bg="white")
        content.pack(fill=tk.BOTH, expand=True, padx=24, pady=16)

        # 启用开关
        enabled_var = tk.BooleanVar(value=task_config.get("enabled", False))
        enable_row = tk.Frame(content, bg="white")
        enable_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            enable_row, text="启用此任务",
            font=("Microsoft YaHei", 14), bg="white", fg="black",
        ).pack(side=tk.LEFT)
        self._create_checkbox(
            enable_row, variable=enabled_var,
            command=lambda k=task_key, v=enabled_var: self._save_task_setting(k, "enabled", v.get()),
        ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # 优先级
        prio_frame = tk.Frame(content, bg="white")
        prio_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            prio_frame, text="优先级：", font=("Microsoft YaHei", 14),
            bg="white", fg="#555555",
        ).pack(side=tk.LEFT)

        default_prio = self.DEFAULT_PRIORITIES.get(task_key, 10)
        prio_var = tk.IntVar(value=task_config.get("priority", default_prio))
        prio_var.trace_add(
            "write",
            lambda *_, k=task_key, v=prio_var: self._save_task_setting(k, "priority", v.get()),
        )
        tk.Spinbox(
            prio_frame, from_=1, to=100, textvariable=prio_var, width=6,
            font=("Microsoft YaHei", 14),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # ── 任务专属设置区 ──
        extra_frame = tk.Frame(content, bg="white")
        extra_frame.pack(fill=tk.X, pady=(8, 16))

        extra_label = tk.Label(
            extra_frame, text="专属设置：", font=("Microsoft YaHei", 14, "bold"),
            bg="white", fg="#333333",
        )
        extra_label.pack(anchor=tk.W, pady=(0, 8))

        opts_frame = tk.Frame(extra_frame, bg="white")
        opts_frame.pack(fill=tk.X, padx=(16, 0))

        if task_key == "events":
            self._build_events_opts(opts_frame, task_config)
        elif task_key == "arena":
            self._build_arena_opts(opts_frame, task_config)
        elif task_key == "auto_battle":
            self._build_battle_opts(opts_frame, task_config)
        elif task_key == "divine_arena":
            self._build_divine_arena_opts(opts_frame, task_config)
        elif task_key == "treasure_hunt":
            self._build_treasure_hunt_opts(opts_frame, task_config)
        else:
            tk.Label(
                opts_frame, text="（暂无专属设置）",
                font=("Microsoft YaHei", 12), bg="white", fg="#aaaaaa",
            ).pack(anchor=tk.W)

        # ── 任务说明 ──
        tk.Frame(content, bg="#eeeeee", height=1).pack(fill=tk.X)

        desc_frame = tk.Frame(content, bg="white")
        desc_frame.pack(fill=tk.X, pady=(12, 0))

        descriptions = {
            "daily_signin": "在福利页面完成签到，领取VIP专属礼包。",
            "daily_quest": "从主页进入每日任务，自动领取每日奖励和宝箱。",
            "collect_mail": "一键领取所有邮件附件。",
            "friends":    "向所有好友赠送体力。",
            "guild":      "联盟捐献（MAX）+ 联盟商店兑换。",
            "events":     "资源争夺战、活动1、活动2、马上有红卡、生存大冒险、神恩、元素挑战。",
            "treasure_hunt": "限时活动：刷新夺宝→匹配钻石→立即夺宝→购买十次，循环执行。",
            "arena":      "自动挑战竞技场，可配置战斗次数。",
            "auto_battle": "精英关卡自动战斗、英雄之路扫荡、冒险扫荡与转生石。",
            "divine_arena": "星域竞技场三大战场循环挑战（皮尔米特、乌尔伦、哈托莫），可配置挑战轮数。",
        }
        desc_text = descriptions.get(task_key, "")
        if desc_text:
            tk.Label(
                desc_frame, text=desc_text,
                font=("Microsoft YaHei", 12), bg="white", fg="#888888",
                wraplength=620, justify=tk.LEFT,
            ).pack(anchor=tk.W)

        return view

    # ── 活动：阶段复选框 ─────────────────────

    def _build_events_opts(self, parent: tk.Frame, task_config: dict):
        """构建活动的 7 个阶段复选框。"""
        params = task_config.get("params", {})
        current_phases: list[int] = list(params.get("phases", [1, 2, 3, 4, 5, 6, 7]))

        phase_info = [
            (1, "资源争夺战"),
            (2, "活动1"),
            (3, "活动2"),
            (4, "马上有红卡"),
            (5, "生存大冒险"),
            (6, "神恩"),
            (7, "元素挑战"),
        ]

        self._events_phase_vars: dict[int, tk.BooleanVar] = {}

        for phase_num, label_text in phase_info:
            var = tk.BooleanVar(value=phase_num in current_phases)
            self._events_phase_vars[phase_num] = var

            row = tk.Frame(parent, bg="white")
            row.pack(fill=tk.X, pady=2)

            tk.Label(
                row, text=label_text,
                font=("Microsoft YaHei", 13), bg="white", fg="black",
            ).pack(side=tk.LEFT)
            self._create_checkbox(
                row, variable=var,
                command=lambda p=phase_num, v=var: self._toggle_phase(p, v),
            ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _toggle_phase(self, phase_num: int, var: tk.BooleanVar):
        """保存阶段复选框变更到 config。"""
        task_config = self._get_task_config("events")
        params = task_config.setdefault("params", {})
        phases: list[int] = list(params.get("phases", [1, 2, 3, 4, 5, 6, 7]))

        if var.get():
            if phase_num not in phases:
                phases.append(phase_num)
                phases.sort()
        else:
            if phase_num in phases:
                phases.remove(phase_num)

        params["phases"] = phases
        save_config(self._config)

    # ── 竞技场：战斗次数 ─────────────────────────

    def _build_arena_opts(self, parent: tk.Frame, task_config: dict):
        """构建竞技场战斗次数设置。"""
        params = task_config.get("params", {})
        default_count = params.get("battle_count", 2)

        row = tk.Frame(parent, bg="white")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row, text="战斗次数：", font=("Microsoft YaHei", 14),
            bg="white", fg="#555555",
        ).pack(side=tk.LEFT)

        count_var = tk.IntVar(value=default_count)
        count_var.trace_add(
            "write",
            lambda *_, v=count_var: self._save_task_param("arena", "battle_count", v.get()),
        )

        tk.Spinbox(
            row, from_=1, to=10, textvariable=count_var, width=6,
            font=("Microsoft YaHei", 14),
        ).pack(side=tk.LEFT, padx=(8, 0))

    # ── 出战：子任务勾选 ─────────────────────────

    def _build_battle_opts(self, parent: tk.Frame, task_config: dict):
        """构建出战子任务勾选 + 扫荡次数 / 等待时间。"""
        params = task_config.get("params", {})

        # ── 精英关卡 ──
        row1 = tk.Frame(parent, bg="white")
        row1.pack(fill=tk.X, pady=2)

        elite_var = tk.BooleanVar(value=params.get("elite", True))
        tk.Label(
            row1, text="精英关卡",
            font=("Microsoft YaHei", 13), bg="white", fg="black",
        ).pack(side=tk.LEFT)

        tk.Label(row1, text="  扫荡次数：", font=("Microsoft YaHei", 13),
                 bg="white", fg="#555555").pack(side=tk.LEFT)

        elite_count_var = tk.IntVar(value=params.get("elite_count", 1))
        elite_count_var.trace_add(
            "write",
            lambda *_, v=elite_count_var: self._save_task_param("auto_battle", "elite_count", v.get()),
        )
        tk.Spinbox(row1, from_=1, to=3, textvariable=elite_count_var, width=4,
                   font=("Microsoft YaHei", 13)).pack(side=tk.LEFT)

        self._create_checkbox(
            row1, variable=elite_var,
            command=lambda: self._save_task_param("auto_battle", "elite", elite_var.get()),
        ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # ── 英雄之路 ──
        row2 = tk.Frame(parent, bg="white")
        row2.pack(fill=tk.X, pady=2)

        hero_var = tk.BooleanVar(value=params.get("hero_path", True))
        tk.Label(
            row2, text="英雄之路",
            font=("Microsoft YaHei", 13), bg="white", fg="black",
        ).pack(side=tk.LEFT)

        tk.Label(row2, text="  扫荡次数：", font=("Microsoft YaHei", 13),
                 bg="white", fg="#555555").pack(side=tk.LEFT)

        hero_count_var = tk.IntVar(value=params.get("hero_count", 1))
        hero_count_var.trace_add(
            "write",
            lambda *_, v=hero_count_var: self._save_task_param("auto_battle", "hero_count", v.get()),
        )
        tk.Spinbox(row2, from_=1, to=10, textvariable=hero_count_var, width=4,
                   font=("Microsoft YaHei", 13)).pack(side=tk.LEFT)

        self._create_checkbox(
            row2, variable=hero_var,
            command=lambda: self._save_task_param("auto_battle", "hero_path", hero_var.get()),
        ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # ── 冒险 ──
        row3 = tk.Frame(parent, bg="white")
        row3.pack(fill=tk.X, pady=2)

        adv_var = tk.BooleanVar(value=params.get("adventure", True))
        tk.Label(
            row3, text="冒险",
            font=("Microsoft YaHei", 13), bg="white", fg="black",
        ).pack(side=tk.LEFT)

        self._create_checkbox(
            row3, variable=adv_var,
            command=lambda: self._save_task_param("auto_battle", "adventure", adv_var.get()),
        ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        row3b = tk.Frame(parent, bg="white")
        row3b.pack(fill=tk.X, pady=2, padx=(20, 0))

        tk.Label(row3b, text="等待时间：", font=("Microsoft YaHei", 13),
                 bg="white", fg="#555555").pack(side=tk.LEFT)

        wait_var = tk.IntVar(value=params.get("adventure_wait", 30))
        wait_var.trace_add(
            "write",
            lambda *_, v=wait_var: self._save_task_param("auto_battle", "adventure_wait", v.get()),
        )
        tk.Spinbox(row3b, from_=30, to=600, increment=30, textvariable=wait_var, width=5,
                   font=("Microsoft YaHei", 13)).pack(side=tk.LEFT)

        tk.Label(row3b, text=" 秒", font=("Microsoft YaHei", 13),
                 bg="white", fg="#555555").pack(side=tk.LEFT)

        tk.Label(
            row3b, text="  （30s为默认时间，可保证至少完成5次出击；10分钟为上限，大概可扫荡完所有次数）",
            font=("Microsoft YaHei", 10), bg="white", fg="#aaaaaa",
        ).pack(side=tk.LEFT)

    # ── 神域：挑战轮数 ─────────────────────────

    def _build_divine_arena_opts(self, parent: tk.Frame, task_config: dict):
        """构建神域竞技场三战场独立设置。"""
        params = task_config.get("params", {})

        fields = [
            ("pirmin", "皮尔米特"),
            ("wulun", "乌尔伦"),
            ("hatomo", "哈托莫"),
        ]

        for key, label_text in fields:
            row = tk.Frame(parent, bg="white")
            row.pack(fill=tk.X, pady=2)

            enabled_var = tk.BooleanVar(value=params.get(f"{key}_enabled", True))
            tk.Label(
                row, text=label_text,
                font=("Microsoft YaHei", 13), bg="white", fg="black",
            ).pack(side=tk.LEFT)

            tk.Label(row, text="  轮数：", font=("Microsoft YaHei", 13),
                     bg="white", fg="#555555").pack(side=tk.LEFT)

            rounds_var = tk.IntVar(value=params.get(f"{key}_rounds", 10))
            rounds_var.trace_add(
                "write",
                lambda *_, k=key, v=rounds_var: self._save_task_param(
                    "divine_arena", f"{k}_rounds", v.get()),
            )
            tk.Spinbox(row, from_=1, to=100, textvariable=rounds_var, width=4,
                       font=("Microsoft YaHei", 13)).pack(side=tk.LEFT)

            self._create_checkbox(
                row, variable=enabled_var,
                command=lambda k=key, v=enabled_var: self._save_task_param(
                    "divine_arena", f"{k}_enabled", v.get()),
            ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    # ── 夺宝奇兵：购买次数 ─────────────────────────

    def _build_treasure_hunt_opts(self, parent: tk.Frame, task_config: dict):
        """构建夺宝奇兵购买次数设置。"""
        params = task_config.get("params", {})
        default_count = params.get("buy_count", 10)

        row = tk.Frame(parent, bg="white")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row, text="购买次数：", font=("Microsoft YaHei", 14),
            bg="white", fg="#555555",
        ).pack(side=tk.LEFT)

        count_var = tk.IntVar(value=default_count)
        count_var.trace_add(
            "write",
            lambda *_, v=count_var: self._save_task_param("treasure_hunt", "buy_count", v.get()),
        )

        tk.Spinbox(
            row, from_=1, to=50, textvariable=count_var, width=6,
            font=("Microsoft YaHei", 14),
        ).pack(side=tk.LEFT, padx=(8, 0))

    # ═══════════════════════════════════════════════
    #  配置读写
    # ═══════════════════════════════════════════════

    def _get_task_config(self, task_name: str) -> dict:
        """查找或创建任务配置条目。"""
        tasks: list = self._config.setdefault("tasks", [])
        for t in tasks:
            if t.get("name") == task_name:
                return t
        # 不存在则创建
        default_prio = self.DEFAULT_PRIORITIES.get(task_name, 10)
        new_task = {
            "name": task_name,
            "enabled": False,
            "priority": default_prio,
            "retry_count": 3,
            "retry_delay": 2.0,
            "timeout": 120.0,
            "params": {},
        }
        tasks.append(new_task)
        return new_task

    def _save_task_setting(self, task_name: str, key: str, value):
        """保存单个配置项并刷新 UI。"""
        t = self._get_task_config(task_name)
        t[key] = value
        save_config(self._config)
        if key == "enabled":
            self._update_queue_display()

    def _save_task_param(self, task_name: str, param_key: str, value):
        """保存 params 下的单个键。"""
        t = self._get_task_config(task_name)
        t.setdefault("params", {})[param_key] = value
        save_config(self._config)

    def _save_device_addr(self, value: str):
        """保存设备地址到 config。"""
        self._config.setdefault("adb", {})["device_addr"] = value
        save_config(self._config)

    def _get_adb_path(self) -> str:
        """获取 ADB 可执行文件路径（与 TaskRunner 逻辑一致）。"""
        adb_path = str(EXE_DIR / "platform-tools" / "adb.exe")
        if not Path(adb_path).exists():
            alt = PROJECT_DIR / "platform-tools" / "adb.exe"
            if alt.exists():
                adb_path = str(alt)
        return adb_path

    def _on_detect_device(self):
        """检测设备按钮回调：执行 adb devices 并将第一个设备 ID 填入输入框。"""
        adb_path = self._get_adb_path()
        try:
            from utils.mumu_detector import list_all_devices
            devices = list_all_devices(adb_path)
            self._device_var.set(devices[0])
            messagebox.showinfo("检测成功", f"已找到设备:\n{devices[0]}")
        except RuntimeError as e:
            messagebox.showerror("检测失败", str(e))
        except Exception as e:
            messagebox.showerror("检测失败", f"执行 adb devices 时出错:\n{e}")

    # ═══════════════════════════════════════════════
    #  启动 / 停止
    # ═══════════════════════════════════════════════

    def _on_action(self):
        if self._running:
            self._running = False
            if self._runner:
                self._runner.stop()
            self._cleanup_adb()
            self._update_button_state()
        else:
            enabled = [t["name"] for t in self._config.get("tasks", []) if t.get("enabled", False)]
            if not enabled:
                messagebox.showinfo("提示", "没有启用的任务")
                return
            self._running = True
            self._update_button_state()
            self._update_queue_display()
            for w in self._done_frame.winfo_children():
                w.destroy()
            tk.Label(
                self._done_frame, text="  -", anchor=tk.W,
                font=("Microsoft YaHei", 16), bg="white", fg="#555555",
            ).pack(fill=tk.X)
            self._runner = TaskRunner(self._log_queue)
            self._runner.start()

    def _update_button_state(self):
        if self._running:
            self._btn_action.configure(
                text="停止", bg="white", fg="black",
                activebackground="#f0f0f0", activeforeground="black",
                relief=tk.SOLID, borderwidth=1,
                highlightbackground="#dddddd", highlightcolor="#dddddd",
            )
        else:
            self._btn_action.configure(
                text="启动", bg="#F2A7A7", fg="white",
                activebackground="#e09090", activeforeground="white",
                relief=tk.FLAT, borderwidth=0,
            )

    # ═══════════════════════════════════════════════
    #  队列显示
    # ═══════════════════════════════════════════════

    def _update_queue_display(self):
        self._pending_tasks = [t for t in self._config.get("tasks", []) if t.get("enabled", False)]
        self._pending_tasks.sort(key=lambda t: t.get("priority", 0))
        self._redraw_queue()

    def _remove_from_queue(self, task_name):
        self._pending_tasks = [t for t in self._pending_tasks if t["name"] != task_name]
        self._redraw_queue()

    def _redraw_queue(self):
        for w in self._queue_frame.winfo_children():
            w.destroy()
        if self._pending_tasks:
            for t in self._pending_tasks:
                row = tk.Frame(self._queue_frame, bg="white")
                row.pack(fill=tk.X, pady=2)
                task_key = t["name"]
                tk.Label(
                    row, text=f"  {self.NAME_MAP.get(task_key, task_key)}",
                    anchor=tk.W, font=("Microsoft YaHei", 16), bg="white", fg="#555555",
                ).pack(side=tk.LEFT, fill=tk.X, expand=True)
                # 设置标签（靠右对齐，灰色细边框）
                settings_lbl = tk.Label(
                    row, text="设置", anchor=tk.CENTER,
                    font=("Microsoft YaHei", 11), bg="white", fg="#555555",
                    highlightbackground="#cccccc", highlightthickness=1,
                    padx=10, cursor="hand2",
                )
                settings_lbl.pack(side=tk.RIGHT, padx=(0, 8))
                settings_lbl.bind("<Button-1>", lambda e, k=task_key: self._switch_view(k))
        else:
            tk.Label(
                self._queue_frame, text="  -", anchor=tk.W,
                font=("Microsoft YaHei", 16), bg="white", fg="#555555",
            ).pack(fill=tk.X)

    # ═══════════════════════════════════════════════
    #  日志
    # ═══════════════════════════════════════════════

    def _clear_log(self):
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _poll_log_queue(self):
        while True:
            try:
                mt, text = self._log_queue.get_nowait()
                if mt == "task_start":
                    d = self.NAME_MAP.get(text, text)
                    self._lbl_running.configure(text=f"  {d}")
                    self._remove_from_queue(text)
                    self._append_log(f"[{d}] started")
                elif mt == "task_end":
                    d = self.NAME_MAP.get(text, text)
                    self._append_log(f"[{d}] finished")
                    self._lbl_running.configure(text="  -")
                    for w in self._done_frame.winfo_children():
                        if isinstance(w, tk.Label) and w.cget("text") == "  -":
                            w.destroy()
                    tk.Label(
                        self._done_frame, text=f"  {d}", anchor=tk.W,
                        font=("Microsoft YaHei", 16), bg="white", fg="#555555",
                    ).pack(fill=tk.X, pady=2)
                elif mt == "done":
                    self._running = False
                    self._cleanup_adb()
                    self._update_button_state()
                    self._runner = None
                    self._lbl_running.configure(text="  -")
                    self._redraw_queue()
                    self._append_log(">>> All tasks completed <<<")
                elif mt == "log":
                    self._append_log(text)
                elif mt in ("info", "warning", "error"):
                    self._append_log(text, mt)
            except queue.Empty:
                break
        self.after(200, self._poll_log_queue)

    def _append_log(self, text: str, tag: str = ""):
        self._log_text.configure(state=tk.NORMAL)
        line = f"{time.strftime('%H:%M:%S')}  {text}\n"
        self._log_text.insert(tk.END, line, tag)
        self._log_text.see(tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _cleanup_adb(self):
        """终止所有残留 ADB 进程。"""
        try:
            adb_path = str(EXE_DIR / "platform-tools" / "adb.exe")
            if not Path(adb_path).exists():
                adb_path = str(PROJECT_DIR / "platform-tools" / "adb.exe")
            if Path(adb_path).exists():
                subprocess.run(
                    [adb_path, "kill-server"],
                    capture_output=True, timeout=5,
                    creationflags=0x08000000,
                )
        except Exception:
            pass

    def _on_close(self, event=None):
        if self._runner and self._runner.is_alive():
            if messagebox.askyesno("Confirm", "Task is running. Exit?"):
                self._runner.stop()
                self._runner.join(timeout=2)
                self._cleanup_adb()
            else:
                return
        else:
            self._cleanup_adb()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
