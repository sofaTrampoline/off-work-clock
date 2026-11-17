"""下班提醒卡片 —— 纯 Tkinter 实现，无第三方依赖。"""

from __future__ import annotations

import argparse
import sys

CARD_BG = "#26263A"
CARD_BORDER = "#3A3A55"
TEXT_FG = "#E8E8F0"
TEXT_MUTED = "#9A9AB0"
ACCENT = "#5FD3C4"
ACCENT_HOVER = "#7FE3D6"
ACCENT_FG = "#101018"
BTN_BG = "#33334D"
BTN_HOVER = "#40405F"
CHROMA = "#FF00FF"

WARN_AUTOCLOSE_MS = 30_000
MARGIN = 24
MAIN_SIZE = (380, 200)
WARN_SIZE = (320, 96)


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _work_area(root) -> tuple[int, int, int, int]:
    """主屏工作区 (left, top, right, bottom)，已避开任务栏。"""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
        ):
            return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def _apply_no_activate(root) -> None:
    """给窗口加 WS_EX_NOACTIVATE，避免出现时抢走前台焦点。"""
    if sys.platform != "win32":
        return
    import ctypes

    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080

    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]

    inner = ctypes.c_void_p(root.winfo_id())
    hwnd = user32.GetParent(inner) or inner
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def _round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    pts = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kwargs)


class _Button:
    def __init__(self, canvas, x, y, w, h, text, command, primary=True, scale=1.0):
        self.canvas = canvas
        self.command = command
        bg = ACCENT if primary else BTN_BG
        hover = ACCENT_HOVER if primary else BTN_HOVER
        fg = ACCENT_FG if primary else TEXT_FG
        self.rect = _round_rect(canvas, x, y, x + w, y + h, h // 2, fill=bg, outline="")
        self.text = canvas.create_text(
            x + w / 2,
            y + h / 2,
            text=text,
            fill=fg,
            font=("Microsoft YaHei UI", -int(12 * scale)),
        )
        for item in (self.rect, self.text):
            canvas.tag_bind(item, "<Button-1>", self._click)
            canvas.tag_bind(
                item, "<Enter>", lambda e, c=hover: canvas.itemconfigure(self.rect, fill=c)
            )
            canvas.tag_bind(
                item, "<Leave>", lambda e, c=bg: canvas.itemconfigure(self.rect, fill=c)
            )

    def _click(self, _event):
        self.command()
        return "break"


def _make_window(kind: str):
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    if sys.platform == "win32":
        root.attributes("-transparentcolor", CHROMA)
    root.configure(bg=CHROMA)

    scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    base_w, base_h = MAIN_SIZE if kind == "main" else WARN_SIZE
    w, h = int(base_w * scale), int(base_h * scale)
    left, top, right, bottom = _work_area(root)
    x = right - w - int(MARGIN * scale)
    y = bottom - h - int(MARGIN * scale)
    root.geometry(f"{w}x{h}+{x}+{y}")

    canvas = tk.Canvas(root, width=w, height=h, bg=CHROMA, highlightthickness=0)
    canvas.pack()
    _round_rect(
        canvas, 1, 1, w - 1, h - 1, int(18 * scale),
        fill=CARD_BG, outline=CARD_BORDER, width=1,
    )
    root.update_idletasks()
    _apply_no_activate(root)
    root.deiconify()
    root.lift()
    return root, canvas, scale, w, h


def _build_main(root, canvas, scale, w, h, clock_text):
    pad = int(24 * scale)
    canvas.create_text(
        pad, pad, text=clock_text, anchor="nw",
        fill=ACCENT, font=("Microsoft YaHei UI", -int(44 * scale)),
    )
    canvas.create_text(
        pad + int(2 * scale), int(76 * scale),
        text="辛苦一天，该走啦", anchor="nw",
        fill=TEXT_MUTED, font=("Microsoft YaHei UI", -int(12 * scale)),
    )

    def ack():
        root.result = "ack"
        root.destroy()

    def snooze():
        root.result = "snooze"
        root.destroy()

    _Button(canvas, pad, int(136 * scale), int(104 * scale), int(38 * scale),
            "知道了", ack, primary=True, scale=scale)
    _Button(canvas, pad + int(116 * scale), int(136 * scale), int(206 * scale),
            int(38 * scale), "10 分钟后再提醒", snooze, primary=False, scale=scale)

    root.bind("<Alt-F4>", lambda e: ack())
    root.protocol("WM_DELETE_WINDOW", ack)


def _build_warn(root, canvas, scale, w, h, clock_text):
    pad = int(20 * scale)
    canvas.create_text(
        pad, int(18 * scale), text="还有 10 分钟下班", anchor="nw",
        fill=TEXT_FG, font=("Microsoft YaHei UI", -int(14 * scale)),
    )
    canvas.create_text(
        pad, int(52 * scale), text=f"打卡时间 {clock_text}", anchor="nw",
        fill=TEXT_MUTED, font=("Microsoft YaHei UI", -int(11 * scale)),
    )

    def close(_event=None):
        root.result = "ack"
        root.destroy()

    canvas.bind("<Button-1>", close)
    root.bind("<Alt-F4>", close)
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(WARN_AUTOCLOSE_MS, close)


def run_popup(kind: str = "main", clock_text: str = "") -> str:
    """显示卡片并阻塞，返回 "ack"（确认）或 "snooze"（10 分钟后再提醒）。"""
    _enable_dpi_awareness()

    root, canvas, scale, w, h = _make_window(kind)
    root.result = "ack"
    if kind == "warn":
        _build_warn(root, canvas, scale, w, h, clock_text)
    else:
        _build_main(root, canvas, scale, w, h, clock_text)
    root.mainloop()
    return root.result


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["main", "warn"], default="main")
    parser.add_argument("--clock", default="")
    ns = parser.parse_args(argv)
    result = run_popup(ns.kind, ns.clock)
    print(result)
    return 0 if result == "ack" else 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
