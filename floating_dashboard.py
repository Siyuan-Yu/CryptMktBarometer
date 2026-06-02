"""
桌面悬浮晴雨表小球（tkinter · 萤火虫可爱风）

分区交互：
  - 上半区：仅拖动
  - 中间文字区：无点击动作；双击展开/收起
  - 右下角「↗」按钮：打开网页
  - 右键：打开网页 / 隐藏悬浮球 / 退出悬浮球
"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

logger = logging.getLogger("floating_dashboard")

_base_url = "http://127.0.0.1:5000"
_root: Any = None
_thread: threading.Thread | None = None
_running = False
_hidden = False
_expanded = True
_price_job: str | None = None
_dash_job: str | None = None

_FONT = ("Microsoft YaHei UI",)
_FONT_BOLD = ("Microsoft YaHei UI",)

# 评级主题（背景 / 主色 / 文字）
_RATING_THEMES: dict[str, dict[str, str]] = {
    "强利多": {"bg": "#e8faf3", "accent": "#5ecf9a", "fg": "#2d7a5a", "sub": "#6bb896"},
    "利多": {"bg": "#e8f8fc", "accent": "#6dd4e8", "fg": "#3a7a8a", "sub": "#7ab0bc"},
    "偏利多": {"bg": "#e8f8fc", "accent": "#6dd4e8", "fg": "#3a7a8a", "sub": "#7ab0bc"},
    "中性": {"bg": "#f6f2fc", "accent": "#c4b8e8", "fg": "#6a6288", "sub": "#9a94b0"},
    "利空": {"bg": "#fff6ee", "accent": "#ffc896", "fg": "#9a7048", "sub": "#b8a080"},
    "偏利空": {"bg": "#fff6ee", "accent": "#ffc896", "fg": "#9a7048", "sub": "#b8a080"},
    "强利空": {"bg": "#fff0f2", "accent": "#ffb0b8", "fg": "#a85a62", "sub": "#c09098"},
    "待计算": {"bg": "#f4f7fc", "accent": "#a8c8e8", "fg": "#6a8098", "sub": "#9ab0c8"},
    "连接中…": {"bg": "#f4f7fc", "accent": "#a8c8e8", "fg": "#6a8098", "sub": "#9ab0c8"},
    "等待服务…": {"bg": "#f4f7fc", "accent": "#a8c8e8", "fg": "#6a8098", "sub": "#9ab0c8"},
}

_CHG_UP = "#4ecf9a"
_CHG_DOWN = "#ff9b9b"
_CHG_FLAT = "#a8b4c8"

_GEO_EXPANDED = "228x300"
_GEO_COLLAPSED = "200x132"


def _display_rating(label: str) -> str:
    return {"偏利多": "利多", "偏利空": "利空"}.get(label, label)


def _resolve_base_url(url: str | None = None) -> str:
    if url:
        return url.rstrip("/")
    try:
        root = Path(__file__).resolve().parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from core.config_loader import load_config

        cfg = load_config()
        host = cfg.get("web", {}).get("host", "127.0.0.1")
        port = int(cfg.get("web", {}).get("port", 5000))
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        return f"http://{host}:{port}"
    except Exception:
        return _base_url


def _open_web_panel() -> None:
    webbrowser.open(f"{_base_url}/")


def _http_get(path: str, timeout: float = 4.0) -> dict[str, Any] | None:
    try:
        import requests

        r = requests.get(f"{_base_url}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.debug("请求失败 %s: %s", path, exc)
        return None


def _fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:,.2f}"
    return f"${v:.3f}"


def _fmt_chg(pct: float | None) -> tuple[str, str]:
    if pct is None:
        return "—", _CHG_FLAT
    sign = "+" if pct >= 0 else ""
    text = f"{sign}{pct:.1f}%"
    if pct > 0.05:
        return text, _CHG_UP
    if pct < -0.05:
        return text, _CHG_DOWN
    return text, _CHG_FLAT


def _run_ui() -> None:
    global _root, _running, _price_job, _dash_job, _expanded, _hidden

    import tkinter as tk
    from tkinter import Menu

    _running = True
    _hidden = False
    _expanded = True

    theme = _RATING_THEMES["待计算"]
    bg = theme["bg"]

    _root = tk.Tk()
    _root.title("晴雨小球")
    _root.overrideredirect(True)
    _root.attributes("-topmost", True)
    try:
        _root.attributes("-alpha", 0.92)
    except tk.TclError:
        pass
    _root.configure(bg=bg)
    _root.geometry(f"{_GEO_EXPANDED}+100+100")

    # 拖动状态（仅上半区启动）
    _drag = {"active": False, "ox": 0, "oy": 0, "sx": 0, "sy": 0}

    def _in_top_half(ev: tk.Event) -> bool:
        wy = ev.y_root - _root.winfo_rooty()
        h = max(_root.winfo_height(), 1)
        return wy < h * 0.52

    def _start_drag(ev: tk.Event) -> None:
        if not _in_top_half(ev):
            return
        _drag["active"] = True
        _drag["sx"] = ev.x_root
        _drag["sy"] = ev.y_root
        _drag["ox"] = ev.x_root - _root.winfo_x()
        _drag["oy"] = ev.y_root - _root.winfo_y()

    def _window_size() -> tuple[int, int]:
        return (228, 300) if _expanded else (200, 132)

    def _do_drag(ev: tk.Event) -> None:
        if not _drag["active"]:
            return
        x = ev.x_root - _drag["ox"]
        y = ev.y_root - _drag["oy"]
        w, h = _window_size()
        _root.geometry(f"{w}x{h}+{x}+{y}")

    def _end_drag(_ev: tk.Event) -> None:
        _drag["active"] = False

    # --- 外层椭圆卡片容器 ---
    outer = tk.Frame(_root, bg=bg, padx=14, pady=12)
    outer.pack(fill=tk.BOTH, expand=True)

    # 顶部拖动条（上半区）
    drag_strip = tk.Frame(outer, bg=bg, height=36, cursor="fleur")
    drag_strip.pack(fill=tk.X)
    drag_strip.pack_propagate(False)
    drag_hint = tk.Label(
        drag_strip,
        text="☁  拖动我",
        font=(_FONT[0], 8),
        fg=theme["sub"],
        bg=bg,
        cursor="fleur",
    )
    drag_hint.place(relx=0.5, rely=0.5, anchor="center")

    # 中间：分数 + 评级
    content = tk.Frame(outer, bg=bg)
    content.pack(fill=tk.X, pady=(2, 4))

    score_lbl = tk.Label(
        content,
        text="—",
        font=(_FONT[0], 32, "bold"),
        fg=theme["fg"],
        bg=bg,
        cursor="arrow",
    )
    score_lbl.pack()

    rating_lbl = tk.Label(
        content,
        text="连接中",
        font=(_FONT[0], 12, "bold"),
        fg=theme["accent"],
        bg=bg,
        cursor="arrow",
    )
    rating_lbl.pack(pady=(0, 2))

    collapse_hint = tk.Label(
        content,
        text="双击收起",
        font=(_FONT[0], 7),
        fg=theme["sub"],
        bg=bg,
    )
    collapse_hint.pack()

    # 底部价格区
    price_zone = tk.Frame(outer, bg=bg)
    price_zone.pack(fill=tk.X, pady=(6, 0))

    price_labels: dict[str, tuple[tk.Label, tk.Label]] = {}
    for sym in ("BTC", "ETH", "SOL"):
        row = tk.Frame(price_zone, bg=bg)
        row.pack(fill=tk.X, pady=2)
        tk.Label(
            row,
            text=sym,
            font=(_FONT[0], 8, "bold"),
            fg=theme["accent"],
            bg=bg,
            width=4,
            anchor="w",
        ).pack(side=tk.LEFT)
        px = tk.Label(row, text="—", font=(_FONT[0], 8), fg=theme["fg"], bg=bg, anchor="w")
        px.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ch = tk.Label(row, text="", font=(_FONT[0], 8), fg=_CHG_FLAT, bg=bg, width=7, anchor="e")
        ch.pack(side=tk.RIGHT)
        price_labels[sym] = (px, ch)

    status_lbl = tk.Label(
        price_zone,
        text="",
        font=(_FONT[0], 7),
        fg=theme["sub"],
        bg=bg,
    )
    status_lbl.pack(pady=(4, 0))

    # 右下角打开网页按钮
    btn_frame = tk.Frame(outer, bg=bg)
    btn_frame.pack(fill=tk.X, pady=(8, 0))

    open_canvas = tk.Canvas(
        btn_frame,
        width=44,
        height=44,
        bg=bg,
        highlightthickness=0,
        cursor="hand2",
    )
    open_canvas.pack(side=tk.RIGHT)

    def _draw_open_btn(accent: str) -> None:
        open_canvas.delete("all")
        open_canvas.create_oval(2, 2, 42, 42, fill=accent, outline="#ffffff", width=2)
        open_canvas.create_text(22, 22, text="↗", fill="#ffffff", font=(_FONT[0], 14, "bold"))

    _draw_open_btn(theme["accent"])
    open_canvas.bind("<Button-1>", lambda _e: _open_web_panel())

    _widgets_all: list[tk.Widget] = [
        outer,
        drag_strip,
        drag_hint,
        content,
        score_lbl,
        rating_lbl,
        collapse_hint,
        price_zone,
        status_lbl,
        btn_frame,
    ]

    def _apply_theme(rating_key: str) -> None:
        t = _RATING_THEMES.get(rating_key, _RATING_THEMES["中性"])
        nb = t["bg"]
        _root.configure(bg=nb)
        for w in _widgets_all:
            try:
                w.configure(bg=nb)
            except tk.TclError:
                pass
        for sym_row in price_zone.winfo_children():
            if isinstance(sym_row, tk.Frame):
                sym_row.configure(bg=nb)
                for c in sym_row.winfo_children():
                    c.configure(bg=nb)
        score_lbl.configure(fg=t["fg"])
        rating_lbl.configure(fg=t["accent"])
        drag_hint.configure(fg=t["sub"])
        collapse_hint.configure(fg=t["sub"])
        status_lbl.configure(fg=t["sub"])
        _draw_open_btn(t["accent"])

    def _bind_drag_only(widget: tk.Widget) -> None:
        widget.bind("<Button-1>", _start_drag)
        widget.bind("<B1-Motion>", _do_drag)
        widget.bind("<ButtonRelease-1>", _end_drag)

    _bind_drag_only(drag_strip)
    _bind_drag_only(drag_hint)

    def _toggle_expand(_ev: tk.Event | None = None) -> None:
        global _expanded
        _expanded = not _expanded
        x, y = _root.winfo_x(), _root.winfo_y()
        if _expanded:
            price_zone.pack(fill=tk.X, pady=(6, 0))
            btn_frame.pack(fill=tk.X, pady=(8, 0))
            collapse_hint.config(text="双击收起")
            _root.geometry(f"{_GEO_EXPANDED}+{x}+{y}")
        else:
            price_zone.pack_forget()
            btn_frame.pack_forget()
            collapse_hint.config(text="双击展开")
            _root.geometry(f"{_GEO_COLLAPSED}+{x}+{y}")

    content.bind("<Double-Button-1>", _toggle_expand)
    score_lbl.bind("<Double-Button-1>", _toggle_expand)
    rating_lbl.bind("<Double-Button-1>", _toggle_expand)

    # 根窗口：仅上半区可拖动
    def _root_press(ev: tk.Event) -> None:
        w = ev.widget
        if w == open_canvas or str(w).endswith("canvas"):
            return
        # 右下角按钮区域不触发拖动
        wx = ev.x_root - _root.winfo_rootx()
        wy = ev.y_root - _root.winfo_rooty()
        rw, rh = _root.winfo_width(), _root.winfo_height()
        if wx > rw - 52 and wy > rh - 52:
            return
        _start_drag(ev)

    def _root_drag(ev: tk.Event) -> None:
        _do_drag(ev)

    def _root_release(ev: tk.Event) -> None:
        _end_drag(ev)

    _root.bind("<Button-1>", _root_press)
    _root.bind("<B1-Motion>", _root_drag)
    _root.bind("<ButtonRelease-1>", _root_release)

    def _hide_ball() -> None:
        global _hidden
        if _root:
            _root.withdraw()
            _hidden = True

    def _close_floating_only() -> None:
        global _running
        _running = False
        if _root:
            _root.destroy()

    menu = Menu(_root, tearoff=0, font=(_FONT[0], 9))
    menu.add_command(label="打开网页", command=_open_web_panel)
    menu.add_command(label="隐藏悬浮球", command=_hide_ball)
    menu.add_separator()
    menu.add_command(label="退出悬浮球", command=_close_floating_only)

    def _on_right_click(ev: tk.Event) -> None:
        menu.tk_popup(ev.x_root, ev.y_root)

    _root.bind("<Button-3>", _on_right_click)
    outer.bind("<Button-3>", _on_right_click)

    def _refresh_prices() -> None:
        global _price_job
        if not _running or not _root:
            return
        if not _expanded:
            _price_job = _root.after(5000, _refresh_prices)
            return
        data = _http_get("/api/prices")
        if data and data.get("tickers"):
            for sym, (px_lbl, chg_lbl) in price_labels.items():
                t = data["tickers"].get(sym) or {}
                px_lbl.config(text=_fmt_price(t.get("price")))
                chg_text, chg_color = _fmt_chg(t.get("change_24h_pct"))
                chg_lbl.config(text=chg_text, fg=chg_color)
        _price_job = _root.after(5000, _refresh_prices)

    def _refresh_dashboard() -> None:
        global _dash_job
        if not _running or not _root:
            return
        data = _http_get("/api/dashboard")
        if data:
            total = data.get("total_score")
            rating = data.get("rating_label") or "待计算"
            show = _display_rating(rating)
            if total is not None:
                score_lbl.config(text=f"{float(total):.0f}")
            else:
                score_lbl.config(text="—")
            rating_lbl.config(text=show)
            _apply_theme(show if show in _RATING_THEMES else rating)
        else:
            score_lbl.config(text="—")
            rating_lbl.config(text="等待")
            _apply_theme("等待服务…")
        _dash_job = _root.after(30000, _refresh_dashboard)

    _refresh_prices()
    _refresh_dashboard()

    def _on_destroy() -> None:
        global _running, _root
        _running = False
        _root = None

    _root.protocol("WM_DELETE_WINDOW", _close_floating_only)
    _root.bind("<Destroy>", lambda _e: _on_destroy())

    try:
        _root.mainloop()
    finally:
        _running = False
        _root = None


def start_floating_window(base_url: str | None = None) -> None:
    global _thread, _base_url, _hidden
    if _root is not None and _hidden:
        try:
            _root.deiconify()
            _hidden = False
            return
        except Exception:
            pass
    stop_floating_window()
    _base_url = _resolve_base_url(base_url)
    _thread = threading.Thread(target=_run_ui, name="FloatingDashboard", daemon=True)
    _thread.start()
    logger.info("悬浮晴雨球已启动，API=%s", _base_url)


def show_floating_window() -> None:
    """显示已隐藏的悬浮球。"""
    global _hidden
    if _root is not None:
        try:
            _root.deiconify()
            _root.lift()
            _hidden = False
        except Exception:
            pass


def hide_floating_window() -> None:
    """隐藏悬浮球（不停止 Flask）。"""
    global _hidden
    if _root is not None:
        try:
            _root.withdraw()
            _hidden = True
        except Exception:
            pass


def stop_floating_window() -> None:
    global _root, _running, _thread, _hidden
    _running = False
    _hidden = False
    if _root is not None:
        try:
            r = _root

            def _destroy() -> None:
                try:
                    r.destroy()
                except tk.TclError:
                    pass

            r.after(0, _destroy)
        except Exception:
            pass
    _thread = None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    import time

    base = _resolve_base_url()
    print(f"悬浮球连接: {base}")
    print("上半区拖动 · 中间双击展开/收起 · 右下角↗打开网页 · 右键菜单")

    for _ in range(30):
        if _http_get("/health"):
            break
        time.sleep(0.5)

    start_floating_window(base)
    try:
        while True:
            if _thread and not _thread.is_alive():
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_floating_window()


if __name__ == "__main__":
    main()
