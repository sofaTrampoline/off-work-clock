# 下班提醒弹窗改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Tkinter 自绘的深色卡片替换 WinForms 气泡提醒，到点必须点「知道了」才消失。

**Architecture:** `off_work.py` 继续负责计算与排程，但计划任务改为直接拉起 `pythonw.exe off_work.py --fire <kind>`；`popup.py` 是纯 Tk 的 UI 模块，`run_popup()` 返回 `"ack"` 或 `"snooze"`，排程逻辑仍留在 `off_work.py`。不引入任何第三方依赖，也不留常驻进程。

**Tech Stack:** Python 3.9+ 标准库：`tkinter`、`subprocess`、`json`、`argparse`、`unittest`；Windows 计划任务 `schtasks`。

## Global Constraints

- 仅 Windows（用到 `schtasks`、`SystemParametersInfoW`、`-transparentcolor`）。
- 仅标准库，不新增 `requirements.txt` 依赖；测试用 `unittest`，不用 pytest。
- 不抢焦点：只用 `-topmost`，禁止 `focus_force`。
- 无声音、无任务栏闪烁、无动画。
- 提前提醒为下班前 **10 分钟**（原 5 分钟）。
- 提前提醒卡 **30 秒**后自动关闭；下班卡不自动关闭。
- 计划任务名前缀统一 `OffWorkReminder_`。
- 卡片固定主屏右下角，边距 24px（按 DPI 缩放）。

---

### Task 1: 抽出可测试的时间计算，提前提醒改为 10 分钟

**Files:**
- Modify: `off_work.py`（在 `parse_time()` 之后新增两个函数；重写 `schedule_notification()` 的时间计算部分）
- Test: `tests/__init__.py`（新建，空文件）、`tests/test_off_work.py`（新建）

**Interfaces:**
- Produces:
  - `ceil_minute(dt: datetime) -> datetime`
  - `reminder_times(clock_out: datetime, now: datetime) -> tuple[datetime | None, datetime]`
  - `schedule_notification(clock_out: datetime) -> bool`（保持原签名）

- [ ] **Step 1: 写失败的测试**

创建空文件 `tests/__init__.py`，再创建 `tests/test_off_work.py`：

```python
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import off_work


class CeilMinuteTest(unittest.TestCase):
    def test_exact_minute_unchanged(self):
        dt = datetime(2026, 11, 17, 18, 30, 0)
        self.assertEqual(off_work.ceil_minute(dt), dt)

    def test_seconds_round_up(self):
        dt = datetime(2026, 11, 17, 18, 30, 1)
        self.assertEqual(off_work.ceil_minute(dt), datetime(2026, 11, 17, 18, 31))


class ReminderTimesTest(unittest.TestCase):
    def test_warn_is_ten_minutes_before(self):
        now = datetime(2026, 11, 17, 9, 0)
        clock_out = datetime(2026, 11, 17, 18, 30)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 30))
        self.assertEqual(warn, datetime(2026, 11, 17, 18, 20))

    def test_warn_skipped_when_passed(self):
        now = datetime(2026, 11, 17, 18, 25)
        clock_out = datetime(2026, 11, 17, 18, 30)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertIsNone(warn)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 30))

    def test_rounds_up_to_next_minute(self):
        now = datetime(2026, 11, 17, 9, 0)
        clock_out = datetime(2026, 11, 17, 18, 30, 45)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 31))
        self.assertEqual(warn, datetime(2026, 11, 17, 18, 21))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_off_work -v`

Expected: FAIL，`AttributeError: module 'off_work' has no attribute 'ceil_minute'`

- [ ] **Step 3: 实现两个函数并改 10 分钟**

在 `off_work.py` 的 `parse_time()` 之后插入：

```python
def ceil_minute(dt: datetime) -> datetime:
    """schtasks 只支持分钟精度，把带秒的时间向上取整到下一分钟。"""
    if dt.second or dt.microsecond:
        dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return dt.replace(second=0, microsecond=0)


def reminder_times(
    clock_out: datetime, now: datetime
) -> tuple[datetime | None, datetime]:
    """返回 (提前提醒时间或 None, 下班提醒时间)。提前提醒 = 下班前 10 分钟。"""
    main_time = ceil_minute(clock_out)
    warn_time = main_time - timedelta(minutes=10)
    return (warn_time if warn_time > now else None), main_time
```

然后重写 `schedule_notification()` 的开头部分（原第 159-175 行）为：

```python
def schedule_notification(clock_out: datetime) -> bool:
    """创建两个 Windows 计划任务：下班前 10 分钟提醒 + 下班提醒。"""
    now = datetime.now()
    warn_time, main_time = reminder_times(clock_out, now)

    if main_time <= now:
        print("⚠️  下班时间已过，不设置提醒。")
        return False
```

并把提前提醒的文案与判断改为：

```python
    if warn_time:
        warn_task_name = f"OffWorkReminder_Warn_{warn_time.strftime('%H%M')}"
        warn_body = (
            f"还有 10 分钟下班！收拾东西准备走啦～`r`n`r`n"
            f"下班打卡: {clock_out.strftime('%H:%M')}"
        )
        if _create_task(warn_task_name, warn_time, "下班提醒", warn_body):
            remaining = warn_time - now
            h, remainder = divmod(int(remaining.total_seconds()), 3600)
            m, _ = divmod(remainder, 60)
            print(f"⏰ 已设置提前 10 分钟提醒 — {h} 小时 {m} 分钟后")
        else:
            ok = False
    else:
        print("⚠️  提前 10 分钟提醒时间已过，跳过。")
```

（本任务暂时保留旧的 `_create_task(title, body)` 气球实现，Task 3 再换掉。）

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_off_work -v`

Expected: 5 个测试全部 `ok`

- [ ] **Step 5: 提交**

```bash
git add off_work.py tests/__init__.py tests/test_off_work.py
git commit -m "refactor: extract minute rounding and 10-minute warning time"
```

---

### Task 2: 新增 popup.py 卡片界面

**Files:**
- Create: `popup.py`
- Test: `tests/test_popup.py`（新建）

**Interfaces:**
- Produces:
  - `run_popup(kind: str = "main", clock_text: str = "") -> str`，返回 `"ack"` 或 `"snooze"`
  - `MAIN_SIZE`, `WARN_SIZE`, `WARN_AUTOCLOSE_MS` 常量
  - CLI：`python popup.py --kind main --clock 18:30`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_popup.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import popup


class PopupContractTest(unittest.TestCase):
    def test_warn_card_is_shorter(self):
        self.assertLess(popup.WARN_SIZE[1], popup.MAIN_SIZE[1])

    def test_warn_autoclose_is_thirty_seconds(self):
        self.assertEqual(popup.WARN_AUTOCLOSE_MS, 30_000)

    def test_accent_colors_defined(self):
        self.assertTrue(popup.ACCENT.startswith("#"))
        self.assertTrue(popup.CARD_BG.startswith("#"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_popup -v`

Expected: FAIL，`ModuleNotFoundError: No module named 'popup'`

- [ ] **Step 3: 创建 popup.py**

完整内容：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_popup -v`

Expected: 3 个测试 `ok`

- [ ] **Step 5: 手工预览**

Run: `python popup.py --kind main --clock 18:30`

Expected: 右下角出现深色圆角卡片；点「知道了」后终端打印 `ack`；再运行一次点「10 分钟后再提醒」打印 `snooze`。

Run: `python popup.py --kind warn --clock 18:30`

Expected: 小卡片出现，30 秒后自动消失；点任意位置可提前关闭。

- [ ] **Step 6: 提交**

```bash
git add popup.py tests/test_popup.py
git commit -m "feat: add tkinter reminder popup"
```

---

### Task 3: 计划任务改为 pythonw + 清理旧任务

**Files:**
- Modify: `off_work.py`（替换 `_create_task` 与 `schedule_notification` 中的调用）
- Modify: `.gitignore`（忽略状态文件）
- Test: `tests/test_off_work.py`（追加测试）

**Interfaces:**
- Consumes: `popup.run_popup()` 将在 Task 4 使用，本任务不直接调用。
- Produces:
  - `_pythonw() -> str`
  - `_task_command(kind: str, clock_text: str) -> str`
  - `_load_task_names(state_path: Path = STATE_PATH) -> list[str]`
  - `_save_task_names(names: list[str], state_path: Path = STATE_PATH) -> None`
  - `_create_task(task_name: str, trigger_time: datetime, command: str) -> bool`
  - `STATE_PATH: Path`、`LOG_PATH: Path`

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_off_work.py` 末尾追加：

```python
class TaskCommandTest(unittest.TestCase):
    def test_command_has_fire_and_clock(self):
        cmd = off_work._task_command("main", "18:30")
        self.assertIn("--fire main", cmd)
        self.assertIn("--clock 18:30", cmd)
        self.assertIn("off_work.py", cmd)

    def test_command_uses_pythonw_when_available(self):
        cmd = off_work._task_command("warn", "18:20")
        self.assertIn(off_work._pythonw(), cmd)


class StateFileTest(unittest.TestCase):
    def test_roundtrip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".state.json"
            off_work._save_task_names(["a", "b"], p)
            self.assertEqual(off_work._load_task_names(p), ["a", "b"])

    def test_missing_file_returns_empty(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(off_work._load_task_names(Path(d) / "nope.json"), [])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_off_work -v`

Expected: FAIL，`AttributeError: module 'off_work' has no attribute '_task_command'`

- [ ] **Step 3: 替换计划任务实现**

在 `off_work.py` 顶部 import 区域补上 `import json`（`tempfile` 已在）。

把原 `_create_task()`（第 127-156 行整段）替换为：

```python
STATE_PATH = Path(__file__).resolve().parent / ".state.json"
LOG_PATH = Path(tempfile.gettempdir()) / "off_work.log"


def _log(msg: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def _pythonw() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def _task_command(kind: str, clock_text: str) -> str:
    script = Path(__file__).resolve()
    return f'"{_pythonw()}" "{script}" --fire {kind} --clock {clock_text}'


def _load_task_names(state_path: Path = STATE_PATH) -> list[str]:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return [str(x) for x in data.get("tasks", [])]
    except (OSError, ValueError):
        return []


def _save_task_names(names: list[str], state_path: Path = STATE_PATH) -> None:
    try:
        state_path.write_text(
            json.dumps({"tasks": names}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        _log(f"save state failed: {e!r}")


def _delete_tasks(names: list[str]) -> None:
    for name in names:
        subprocess.run(
            ["schtasks", "/delete", "/tn", name, "/f"],
            capture_output=True,
            text=True,
        )


def _create_task(task_name: str, trigger_time: datetime, command: str) -> bool:
    cmd = [
        "schtasks", "/create", "/f",
        "/sc", "once",
        "/tn", task_name,
        "/tr", command,
        "/st", trigger_time.strftime("%H:%M"),
        "/it",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _log(f"schtasks failed: {result.returncode} {result.stdout} {result.stderr}")
    return result.returncode == 0
```

把 `schedule_notification()` 整段替换为：

```python
def schedule_notification(clock_out: datetime) -> bool:
    """创建两个 Windows 计划任务：下班前 10 分钟提醒 + 下班提醒。"""
    now = datetime.now()
    warn_time, main_time = reminder_times(clock_out, now)

    if main_time <= now:
        print("⚠️  下班时间已过，不设置提醒。")
        return False

    _delete_tasks(_load_task_names())
    names: list[str] = []
    ok = True

    if warn_time:
        warn_task_name = f"OffWorkReminder_Warn_{warn_time.strftime('%H%M')}"
        if _create_task(warn_task_name, warn_time, _task_command("warn", clock_out.strftime("%H:%M"))):
            names.append(warn_task_name)
            remaining = warn_time - now
            h, remainder = divmod(int(remaining.total_seconds()), 3600)
            m, _ = divmod(remainder, 60)
            print(f"⏰ 已设置提前 10 分钟提醒 — {h} 小时 {m} 分钟后")
        else:
            ok = False
    else:
        print("⚠️  提前 10 分钟提醒时间已过，跳过。")

    main_task_name = f"OffWorkReminder_{main_time.strftime('%H%M')}"
    if _create_task(main_task_name, main_time, _task_command("main", clock_out.strftime("%H:%M"))):
        names.append(main_task_name)
        remaining = main_time - now
        h, remainder = divmod(int(remaining.total_seconds()), 3600)
        m, _ = divmod(remainder, 60)
        print(f"✅ 已设置下班提醒 — {h} 小时 {m} 分钟后")
    else:
        ok = False
        print("❌ 设置下班提醒失败")

    _save_task_names(names)
    return ok
```

在 `.gitignore` 追加一行：

```gitignore
.state.json
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 `ok`

- [ ] **Step 5: 手工验证计划任务**

先取一个"3 小时后"的打卡时间，保证下班时间在未来：

```bash
python -c "from datetime import datetime,timedelta; print((datetime.now()+timedelta(hours=3)).strftime('%H%M'))"
```

用它作为打卡时间运行（把 `<HHMM>` 换成上一步输出）：

```bash
python off_work.py <HHMM>
```

Expected: 终端打印「已设置提前 10 分钟提醒」和「已设置下班提醒」。

Run: `schtasks /query /fo list | findstr OffWorkReminder`

Expected: 出现两条 `OffWorkReminder_*` 任务。

Run: `schtasks /query /fo csv /v | findstr OffWorkReminder`

Expected: 任务动作里能看到 `pythonw.exe`、`off_work.py`、`--fire warn` / `--fire main`、`--clock`。

再运行一次同样的 `python off_work.py <HHMM>`：

Expected: 上一次的两个任务被删除后重建，`OffWorkReminder_*` 数量不增加。

- [ ] **Step 6: 提交**

```bash
git add off_work.py tests/test_off_work.py .gitignore
git commit -m "feat: schedule popup via pythonw and clean stale tasks"
```

---

### Task 4: 实现 --fire 入口、日志与气球兜底

**Files:**
- Modify: `off_work.py`（新增 `_fire`、`parse_fire_args`、`_balloon_ps`、`_show_balloon_now`；`main()` 开头增加分发）
- Test: `tests/test_off_work.py`（追加测试）

**Interfaces:**
- Consumes: `popup.run_popup(kind, clock_text) -> str`（Task 2）、`_create_task`/`_save_task_names`/`_load_task_names`（Task 3）
- Produces: `parse_fire_args(argv: list[str]) -> tuple[str, str]`

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_off_work.py` 末尾追加：

```python
class FireArgsTest(unittest.TestCase):
    def test_parse_kind_and_clock(self):
        kind, clock = off_work.parse_fire_args(
            ["--fire", "main", "--clock", "18:30"]
        )
        self.assertEqual(kind, "main")
        self.assertEqual(clock, "18:30")

    def test_warn_kind(self):
        kind, _ = off_work.parse_fire_args(["--fire", "warn", "--clock", "18:20"])
        self.assertEqual(kind, "warn")

    def test_defaults(self):
        kind, clock = off_work.parse_fire_args(["--fire"])
        self.assertEqual(kind, "main")
        self.assertEqual(clock, "")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_off_work -v`

Expected: FAIL，`AttributeError: no attribute 'parse_fire_args'`

- [ ] **Step 3: 实现 --fire 与兜底**

在 `off_work.py` 的 `schedule_notification()` 之后插入：

```python
def parse_fire_args(argv: list[str]) -> tuple[str, str]:
    args = list(argv)
    kind = "warn" if "warn" in args else "main"
    clock_text = ""
    if "--clock" in args:
        i = args.index("--clock")
        if i + 1 < len(args):
            clock_text = args[i + 1]
    return kind, clock_text


def _balloon_ps(title: str, body: str) -> str:
    return (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$b = New-Object System.Windows.Forms.NotifyIcon; "
        "$b.Icon = [System.Drawing.SystemIcons]::Information; "
        "$b.BalloonTipIcon = 'Info'; "
        f'$b.BalloonTipTitle = "{title}"; '
        f'$b.BalloonTipText = "{body}"; '
        "$b.Visible = $true; "
        "$b.ShowBalloonTip(0); "
        "Start-Sleep -Seconds 10; "
        "$b.Dispose()"
    )


def _show_balloon_now(title: str, body: str) -> None:
    subprocess.Popen(
        [
            "powershell", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-Command", _balloon_ps(title, body),
        ],
        creationflags=0x08000000 if sys.platform == "win32" else 0,
    )


def _fire(kind: str, clock_text: str) -> None:
    try:
        import popup

        result = popup.run_popup(kind, clock_text)
    except Exception as e:
        _log(f"popup failed: {e!r}")
        _show_balloon_now(
            "下班提醒",
            "还有 10 分钟下班" if kind == "warn" else "到下班时间啦！辛苦一天，该走了！",
        )
        result = "ack"

    if result == "snooze":
        when = ceil_minute(datetime.now() + timedelta(minutes=10))
        name = f"OffWorkReminder_Snooze_{when.strftime('%H%M')}"
        if _create_task(name, when, _task_command("main", clock_text)):
            _save_task_names(_load_task_names() + [name])
            _log(f"snooze scheduled at {when:%H:%M}")
        else:
            _log("snooze schedule failed")
```

在 `main()` 里，`sys.stdout.reconfigure(...)` 之后、参数解析之前插入：

```python
    if "--fire" in sys.argv:
        kind, clock_text = parse_fire_args(sys.argv)
        _fire(kind, clock_text)
        return
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 `ok`

- [ ] **Step 5: 手工验证 fire 模式**

Run: `pythonw off_work.py --fire warn --clock 18:30`

Expected: 无终端窗口，右下角出现小卡，30 秒自动消失。

Run: `python off_work.py --fire main --clock 18:30`

Expected: 出现大卡；点「10 分钟后再提醒」后，`schtasks /query /fo list | findstr Snooze` 能看到新任务，且 `%TEMP%\off_work.log` 有 `snooze scheduled at …`。

- [ ] **Step 6: 提交**

```bash
git add off_work.py tests/test_off_work.py
git commit -m "feat: add --fire entry with popup and balloon fallback"
```

---

### Task 5: 更新 README 并做端到端验收

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README**

把「功能」和「依赖」两节替换为：

```markdown
## 功能

- 超大 ASCII 艺术字在终端显示下班时间
- 到点弹深色圆角卡片，**必须点「知道了」才消失**；可点「10 分钟后再提醒」
- 下班前 10 分钟弹小卡提醒，30 秒自动消失
- `--watch` 实时全屏倒计时
- `--no-notify` 只计算不提醒

## 依赖

仅 Python 标准库（含 `tkinter`），无需安装第三方包。Windows 10/11 系统即可。
```

- [ ] **Step 2: 端到端验收**

用 Task 3 Step 5 里的方式生成一个未来打卡时间，并运行：

```bash
python off_work.py <HHMM>
```

Expected：

1. 终端显示下班时间和剩余时长，并提示已设置两条提醒
2. `schtasks /query /fo list | findstr OffWorkReminder` 出现 Warn 与主提醒两条任务
3. 用 Task 4 的 `--fire` 命令模拟到点：`python off_work.py --fire main --clock 18:30` —— 出现卡片、无黑窗、无声音
4. 点「知道了」后卡片消失；再跑一次 `python off_work.py <HHMM>`，旧任务被清理、数量不变
5. `%TEMP%\off_work.log` 没有 `popup failed` / `schtasks failed`

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: document popup reminder behavior"
```

---

## Self-Review

**Spec coverage**

| 规格 | 对应任务 |
|---|---|
| 深色圆角卡片、右下角、无边框 | Task 2 |
| 到点必须点确认 | Task 2（`_build_main` 不设自动关闭） |
| 提前 10 分钟、30 秒自动关 | Task 1 / Task 2 |
| pythonw 绝对路径、`/it` | Task 3 |
| 旧任务清理（`.state.json`） | Task 3 |
| `--fire` 入口与 snooze | Task 4 |
| 日志与 tkinter 兜底 | Task 4 |
| README 与验收 | Task 5 |
| 无声音/闪烁/动画 | 全部任务均未引入 |

**Placeholder scan:** 无 TBD/TODO；每个代码步骤都是完整可粘贴内容。

**Type consistency:** `run_popup(kind, clock_text) -> str` 在 Task 2 定义、Task 4 调用一致；`_task_command(kind, clock_text: str)` 在 Task 3 定义、Task 4 传 `clock_text` 一致；`_create_task(name, trigger_time, command)` 三处调用一致。
