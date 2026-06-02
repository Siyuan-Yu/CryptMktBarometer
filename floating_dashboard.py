"""
桌面悬浮晴雨球 — 纯圆形 Q 版萤火虫仪表盘（tkinter Canvas）

分区交互（严格）：
  · 上半圆：拖动
  · 下半圆：单击 → 打开网页
  · 任意处双击：展开/收起（展开时在圆下方显示迷你价格条）
  · 右键：菜单（打开网页 / 隐藏 / 退出悬浮球）
"""

from __future__ import annotations

import logging
import math
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

logger = logging.getLogger("floating_dashboard")

_base_url = "http://127.0.0.1:5000"
_root: Any = None
_thread: threading.Thread | None = None
_running = False
_hidden = False
_expanded = False
_diameter = 168
_canvas: Any = None
_price_job: str | None = None
_dash_job: str | None = None

_FONT = ("Microsoft YaHei UI",)

# 评级 → 外圈色
_RING: dict[str, tuple[str, str, str]] = {
    "强利多": ("#b8f5d4", "#5ecf9a", "#2d7a5a"),
    "利多": ("#c8f5f0", "#6dd4c8", "#3a7a8a"),
    "偏利多": ("#c8f5f0", "#6dd4c8", "#3a7a8a"),
    "中性": ("#ece8f8", "#c4b8e8", "#6a6288"),
    "利空": ("#fff0e0", "#ffc896", "#9a7048"),
    "偏利空": ("#fff0e0", "#ffc896", "#9a7048"),
    "强利空": ("#ffe8ec", "#ffabab", "#a85a62"),
    "待计算": ("#eef4fc", "#a8c8e8", "#6a8098"),
}


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


def _theme(rating_key: str) -> tuple[str, str, str]:
    show = _display_rating(rating_key)
    return _RING.get(show, _RING.get(rating_key, _RING["待计算"]))


def _run_ui() -> None:
    global _root, _running, _hidden, _expanded, _canvas, _price_job, _dash_job

    import tkinter as tk
    from tkinter import Menu

    _running = True
    _hidden = False
    _expanded = False

    d = _diameter
    pad = 8
    win_h = d + pad * 2
    win_w = d + pad * 2

    state = {
        "score": None,
        "rating": "连接中",
        "theme": _theme("待计算"),
        "prices": {},
        "drag": False,
        "press_y": 0,
        "press_x": 0,
        "moved": False,
        "last_click": 0.0,
    }

    _root = tk.Tk()
    _root.title("晴雨球")
    _root.overrideredirect(True)
    _root.attributes("-topmost", True)
    try:
        _root.attributes("-alpha", 0.94)
        _root.attributes("-transparentcolor", "#010101")
    except tk.TclError:
        pass
    _root.configure(bg="#010101")
    _root.geometry(f"{win_w}x{win_h}+120+120")

    _canvas = tk.Canvas(
        _root,
        width=win_w,
        height=win_h,
        bg="#010101",
        highlightthickness=0,
        bd=0,
    )
    _canvas.pack()

    cx = win_w // 2
    cy = pad + d // 2
    r_outer = d // 2 - 4
    r_ring = r_outer - 10
    r_inner = r_outer - 22

    def _resize_window() -> None:
        nonlocal win_h, win_w
        extra = 72 if _expanded else 0
        win_h = d + pad * 2 + extra
        win_w = d + pad * 2
        _root.geometry(f"{win_w}x{win_h}+{_root.winfo_x()}+{_root.winfo_y()}")
        _canvas.config(width=win_w, height=win_h)

    def _local_y(ev: tk.Event) -> float:
        return ev.y - pad

    def _in_upper_half(ev: tk.Event) -> bool:
        ly = _local_y(ev)
        return ly < d / 2 and math.hypot(ev.x - cx, ly - (d / 2)) <= r_outer + 6

    def _in_lower_half(ev: tk.Event) -> bool:
        ly = _local_y(ev)
        return ly >= d / 2 and math.hypot(ev.x - cx, ly - (d / 2)) <= r_outer + 6

    def _draw() -> None:
        if not _canvas or not _running:
            return
        _canvas.delete("all")
        bg_outer, ring_c, fg = state["theme"]
        score = state["score"]
        rating = _display_rating(state["rating"])

        # 透明底
        _canvas.create_rectangle(0, 0, win_w, win_h, fill="#010101", outline="")

        # 外发光
        for i in range(3, 0, -1):
            _canvas.create_oval(
                cx - r_outer - i * 3,
                cy - r_outer - i * 3,
                cx + r_outer + i * 3,
                cy + r_outer + i * 3,
                fill="",
                outline=ring_c,
                width=1,
            )

        # 五色状态环（静态装饰弧）
        seg_colors = ["#5ecf9a", "#6dd4c8", "#c4b8e8", "#ffc896", "#ffabab"]
        for i, col in enumerate(seg_colors):
            start = -90 + i * 72
            _canvas.create_arc(
                cx - r_outer,
                cy - r_outer,
                cx + r_outer,
                cy + r_outer,
                start=start,
                extent=50,
                style=tk.ARC,
                outline=col,
                width=6,
            )

        # 分数进度环
        pct = (float(score) / 100.0) if score is not None else 0
        extent = max(4, min(360, pct * 3.6))
        _canvas.create_arc(
            cx - r_ring,
            cy - r_ring,
            cx + r_ring,
            cy + r_ring,
            start=-90,
            extent=extent,
            style=tk.ARC,
            outline=ring_c,
            width=8,
        )

        # 磨砂内圆
        _canvas.create_oval(
            cx - r_inner,
            cy - r_inner,
            cx + r_inner,
            cy + r_inner,
            fill=bg_outer,
            outline="#ffffff",
            width=2,
        )

        # 中心分数
        sc = "—" if score is None else f"{int(round(float(score)))}"
        _canvas.create_text(cx, cy - 10, text=sc, fill=fg, font=(_FONT[0], 26, "bold"))
        _canvas.create_text(cx, cy + 18, text=rating, fill=ring_c, font=(_FONT[0], 10, "bold"))

        # 下半区提示（小字）
        _canvas.create_text(
            cx,
            cy + r_inner - 8,
            text="↓ 点开网页",
            fill="#9ab0c8",
            font=(_FONT[0], 7),
        )

        # 展开：圆下方迷你价格
        if _expanded and state["prices"]:
            y0 = pad + d + 6
            _canvas.create_rectangle(
                12,
                y0,
                win_w - 12,
                win_h - 8,
                fill="#f8fbff",
                outline="#dce8f8",
                width=1,
            )
            line = " · ".join(
                f"{k} {_short_price(v)}" for k, v in state["prices"].items()
            )
            _canvas.create_text(
                win_w // 2,
                y0 + 28,
                text=line[:42],
                fill="#6a8098",
                font=(_FONT[0], 8),
            )

    def _short_price(t: dict) -> str:
        p = t.get("price")
        if p is None:
            return "—"
        if p >= 1000:
            return f"${p:,.0f}"
        return f"${p:.1f}"

    def _on_press(ev: tk.Event) -> None:
        state["drag"] = _in_upper_half(ev)
        state["press_x"] = ev.x_root
        state["press_y"] = ev.y_root
        state["moved"] = False
        state["ox"] = ev.x_root - _root.winfo_x()
        state["oy"] = ev.y_root - _root.winfo_y()

    def _on_motion(ev: tk.Event) -> None:
        if state["drag"]:
            if abs(ev.x_root - state["press_x"]) > 3 or abs(ev.y_root - state["press_y"]) > 3:
                state["moved"] = True
            _root.geometry(
                f"{win_w}x{win_h}+{ev.x_root - state['ox']}+{ev.y_root - state['oy']}"
            )

    def _on_release(ev: tk.Event) -> None:
        if state["drag"]:
            state["drag"] = False
            return
        if _in_lower_half(ev) and not state["moved"]:
            now = time.time()
            if now - state["last_click"] < 0.35:
                return
            state["last_click"] = now
            _open_web_panel()

    def _on_double(_ev: tk.Event) -> None:
        global _expanded
        _expanded = not _expanded
        state["last_click"] = time.time() + 0.5
        _resize_window()
        _draw()

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

    menu = Menu(_root, tearoff=0)
    menu.add_command(label="打开网页", command=_open_web_panel)
    menu.add_command(label="隐藏悬浮球", command=_hide_ball)
    menu.add_separator()
    menu.add_command(label="退出悬浮球", command=_close_floating_only)

    def _on_right(ev: tk.Event) -> None:
        menu.tk_popup(ev.x_root, ev.y_root)

    _canvas.bind("<Button-1>", _on_press)
    _canvas.bind("<B1-Motion>", _on_motion)
    _canvas.bind("<ButtonRelease-1>", _on_release)
    _canvas.bind("<Double-Button-1>", _on_double)
    _canvas.bind("<Button-3>", _on_right)

    def _refresh_prices() -> None:
        global _price_job
        if not _running or not _root:
            return
        data = _http_get("/api/prices")
        if data and data.get("tickers"):
            state["prices"] = {
                s: data["tickers"].get(s, {}) for s in ("BTC", "ETH", "SOL")
            }
            if _expanded:
                _draw()
        _price_job = _root.after(5000, _refresh_prices)

    def _refresh_dashboard() -> None:
        global _dash_job
        if not _running or not _root:
            return
        data = _http_get("/api/dashboard")
        if data:
            state["score"] = data.get("total_score")
            state["rating"] = data.get("rating_label") or "待计算"
            state["theme"] = _theme(state["rating"])
        else:
            state["score"] = None
            state["rating"] = "等待"
            state["theme"] = _theme("待计算")
        _draw()
        _dash_job = _root.after(30000, _refresh_dashboard)

    _draw()
    _refresh_prices()
    _refresh_dashboard()

    try:
        _root.mainloop()
    finally:
        _running = False
        _root = None
        _canvas = None


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
    _thread = threading.Thread(target=_run_ui, name="FloatingBall", daemon=True)
    _thread.start()
    logger.info("悬浮晴雨球已启动 %s", _base_url)


def show_floating_window() -> None:
    global _hidden
    if _root is not None:
        try:
            _root.deiconify()
            _root.lift()
            _hidden = False
        except Exception:
            pass


def hide_floating_window() -> None:
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
                except Exception:
                    pass

            r.after(0, _destroy)
        except Exception:
            pass
    _thread = None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    base = _resolve_base_url()
    print("悬浮球:", base)
    print("上半圆拖动 · 下半圆点开网页 · 双击展开价格")

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
