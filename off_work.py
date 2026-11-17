"""下班时间计算器 — 打卡时间 + 8h45m = 下班时间，大字体显示 + 下班提醒通知"""

import csv
import json
import re
import sys
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── 数字字体 ──
# FONT_COMPACT: 4列 × 5行（默认，上下半格压缩后 3 行）
# FONT:         5列 × 7行（--mid / --big，压缩后 4 行）
PIXEL_NARROW = "█"
PIXEL_WIDE = "██"
FONT = {
    "0": [0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    "1": [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    "2": [0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b01000, 0b11111],
    "3": [0b01110, 0b10001, 0b00001, 0b00110, 0b00001, 0b10001, 0b01110],
    "4": [0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010],
    "5": [0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110],
    "6": [0b01110, 0b10001, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110],
    "7": [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000],
    "8": [0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110],
    "9": [0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b10001, 0b01110],
}
FONT_COMPACT = {
    "0": [0b0110, 0b1001, 0b1001, 0b1001, 0b0110],
    "1": [0b0010, 0b0110, 0b0010, 0b0010, 0b0111],
    "2": [0b0110, 0b1001, 0b0010, 0b0100, 0b1111],
    "3": [0b1111, 0b0001, 0b0111, 0b0001, 0b1111],
    "4": [0b0010, 0b0110, 0b1010, 0b1111, 0b0010],
    "5": [0b1111, 0b1000, 0b1110, 0b0001, 0b1110],
    "6": [0b0110, 0b1000, 0b1110, 0b1001, 0b0110],
    "7": [0b1111, 0b0001, 0b0010, 0b0100, 0b0100],
    "8": [0b0110, 0b1001, 0b0110, 0b1001, 0b0110],
    "9": [0b0110, 0b1001, 0b0111, 0b0001, 0b0110],
}


def glyph_bits(ch: str, compact: bool = True) -> list[list[bool]]:
    """返回一个字符的点阵（compact: 5 行 × 4 列；否则 7 行 × 5 列）"""
    font, rows_n, cols_n = (
        (FONT_COMPACT, 5, 4) if compact else (FONT, 7, 5)
    )
    if ch == ":":
        rows = [[False] * cols_n for _ in range(rows_n)]
        rows[1][cols_n // 2] = True
        rows[rows_n - 2][cols_n // 2] = True
        return rows
    pattern = font.get(ch)
    if pattern is None:
        return [[False] * cols_n for _ in range(rows_n)]
    return [
        [bool((row_bits >> (cols_n - 1 - col)) & 1) for col in range(cols_n)]
        for row_bits in pattern
    ]


def render_big(
    text: str,
    pixel: str = PIXEL_NARROW,
    compress: bool = True,
    compact: bool = True,
) -> str:
    """把时间字符串渲染成大数字；compress 时用上下半格把两行压成一行"""
    glyphs = [glyph_bits(ch, compact) for ch in text]
    rows_n = 5 if compact else 7
    width = len(pixel)
    gap = 1 if width > 1 else 2  # 字符间距，宽像素时用 1 格保持总宽不变
    grid = []
    for i in range(rows_n):
        row: list[bool] = []
        for gi, g in enumerate(glyphs):
            if gi:
                row.extend([False] * gap)
            row.extend(g[i])
        grid.append(row)

    if compress:
        blank = [False] * len(grid[0])
        lines = []
        for i in range(0, rows_n, 2):
            top = grid[i]
            bottom = grid[i + 1] if i + 1 < rows_n else blank
            line = []
            for a, b in zip(top, bottom):
                if a and b:
                    line.append("█" * width)
                elif a:
                    line.append("▀" * width)
                elif b:
                    line.append("▄" * width)
                else:
                    line.append(" " * width)
            lines.append("".join(line))
        return "\n".join(lines)

    lines = []
    for row in grid:
        line = ""
        for bit in row:
            line += pixel if bit else " " * width
        lines.append(line)
    return "\n".join(lines)


def parse_time(s: str) -> datetime:
    """解析 HHMM 或 HHMMSS 格式"""
    s = s.strip()
    if not s.isdigit():
        print(f"❌ 格式错误：请输入数字，例如 0845 或 082523，收到: {s}")
        sys.exit(1)
    if len(s) == 4:
        fmt = "%H%M"
    elif len(s) == 6:
        fmt = "%H%M%S"
    else:
        print(f"❌ 长度不对：需要 4 位 (HHMM) 或 6 位 (HHMMSS)，收到 {len(s)} 位: {s}")
        sys.exit(1)
    try:
        return datetime.strptime(s, fmt)
    except ValueError as e:
        print(f"❌ 时间不合法: {e}")
        sys.exit(1)


def ceil_minute(dt: datetime) -> datetime:
    """schtasks 只支持分钟精度，把带秒的时间向上取整到下一分钟。"""
    if dt.second or dt.microsecond:
        dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return dt.replace(second=0, microsecond=0)


def _trigger_time(target: datetime, now: datetime) -> datetime | None:
    """任务触发时刻：取目标的整分钟（向下），已错过则退化为向上取整。"""
    t = target.replace(second=0, microsecond=0)
    if t <= now:
        t = ceil_minute(target)
    return t if t > now else None


def reminder_times(
    clock_out: datetime, now: datetime
) -> tuple[datetime | None, datetime | None]:
    """返回 (提前提醒触发时间或 None, 下班提醒触发时间)。提前提醒 = 下班前 10 分钟。

    触发只能到整分钟；精确到秒的显示由 _fire 里的等待补足。
    """
    warn_target = clock_out - timedelta(minutes=10)
    return _trigger_time(warn_target, now), _trigger_time(clock_out, now)


STATE_PATH = Path(__file__).resolve().parent / ".state.json"
LOG_PATH = Path(tempfile.gettempdir()) / "off_work.log"
TASK_PREFIX = "OffWorkReminder"


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
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [str(x) for x in tasks]


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


def _parse_task_rows(csv_text: str) -> list[tuple[str, str]]:
    """从 schtasks /query /fo csv 的输出里挑出本程序的任务名和下次运行时间。"""
    rows: list[tuple[str, str]] = []
    for line in csv_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            fields = next(csv.reader([line]))
        except (StopIteration, csv.Error):
            continue
        if len(fields) < 2:
            continue
        name = fields[0].lstrip("\\")
        if name.startswith(TASK_PREFIX):
            rows.append((name, fields[1].strip()))
    return rows


def _parse_task_names(csv_text: str) -> list[str]:
    """从 schtasks /query /fo csv 的输出里挑出本程序创建的任务名。"""
    return [name for name, _ in _parse_task_rows(csv_text)]


def _run_task_query() -> list[tuple[str, str]]:
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )
    except OSError as e:
        _log(f"schtasks query failed: {e!r}")
        return []
    if result.returncode != 0:
        _log(f"schtasks query failed: {result.returncode}")
        return []
    return _parse_task_rows(result.stdout)


def _query_task_names() -> list[str]:
    """列出当前所有本程序创建的计划任务，防止历史残留越积越多。"""
    return [name for name, _ in _run_task_query()]


def _query_task_command(task_name: str) -> str:
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/fo", "list", "/v"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )
    except OSError:
        return ""
    return result.stdout if result.returncode == 0 else ""


def _scheduled_clock_text() -> str | None:
    """还有没触发的排程时，返回它记录的下班时间，用于跳过重复输入。"""
    for name, next_run in _run_task_query():
        if not next_run or next_run.upper() == "N/A":
            continue
        match = re.search(
            r"--clock\s+(\d{1,2}:\d{2}(?::\d{2})?)", _query_task_command(name)
        )
        if match:
            return match.group(1)
    return None


def _short_date(dt: datetime) -> str:
    """按系统区域设置返回短日期，供 schtasks /sd 使用。"""
    if sys.platform != "win32":
        return dt.strftime("%Y-%m-%d")
    import ctypes

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [
            ("wYear", ctypes.c_ushort),
            ("wMonth", ctypes.c_ushort),
            ("wDayOfWeek", ctypes.c_ushort),
            ("wDay", ctypes.c_ushort),
            ("wHour", ctypes.c_ushort),
            ("wMinute", ctypes.c_ushort),
            ("wSecond", ctypes.c_ushort),
            ("wMilliseconds", ctypes.c_ushort),
        ]

    st = SYSTEMTIME(dt.year, dt.month, 0, dt.day, 0, 0, 0, 0)
    buf = ctypes.create_unicode_buffer(128)
    kernel32 = ctypes.windll.kernel32
    kernel32.GetDateFormatW.restype = ctypes.c_int
    kernel32.GetDateFormatW.argtypes = [
        ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
    ]
    got = kernel32.GetDateFormatW(
        0x0400, 0x00000001, ctypes.byref(st), None, buf, len(buf)
    )
    return buf.value if got else dt.strftime("%Y-%m-%d")


def _create_task(task_name: str, trigger_time: datetime, command: str) -> bool:
    cmd = [
        "schtasks", "/create", "/f",
        "/sc", "once",
        "/tn", task_name,
        "/tr", command,
        "/st", trigger_time.strftime("%H:%M"),
        "/sd", _short_date(trigger_time),
        "/it",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _log(f"schtasks failed: {result.returncode} {result.stdout} {result.stderr}")
    return result.returncode == 0


def schedule_notification(clock_out: datetime) -> bool:
    """创建两个 Windows 计划任务：下班前 10 分钟提醒 + 下班提醒。"""
    now = datetime.now()
    warn_time, main_time = reminder_times(clock_out, now)

    if main_time is None:
        print("⚠️  下班时间已过，不设置提醒。")
        return False

    # state.json 只记得最后一次排程，重跑会覆盖记录、漏删旧任务；
    # 直接扫一遍计划任务，避免残留堆积导致同一时段重复弹窗。
    stale = set(_load_task_names()) | set(_query_task_names())
    _delete_tasks(sorted(stale))
    names: list[str] = []
    ok = True

    if warn_time:
        warn_task_name = f"OffWorkReminder_Warn_{warn_time.strftime('%H%M')}"
        if _create_task(warn_task_name, warn_time, _task_command("warn", clock_out.strftime("%H:%M:%S"))):
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
    if _create_task(main_task_name, main_time, _task_command("main", clock_out.strftime("%H:%M:%S"))):
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


def parse_fire_args(argv: list[str]) -> tuple[str, str]:
    args = list(argv)
    kind = "warn" if "warn" in args else "main"
    clock_text = ""
    if "--clock" in args:
        i = args.index("--clock")
        if i + 1 < len(args):
            clock_text = args[i + 1]
    return kind, clock_text


def _parse_clock_text(text: str) -> tuple[int, int, int] | None:
    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        nums.append(0)
    h, m, s = nums
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        return None
    return h, m, s


def _popup_target(kind: str, clock_text: str, now: datetime) -> datetime | None:
    """卡片出现的精确时刻：下班时间本身；提前提醒再往前 10 分钟。"""
    parsed = _parse_clock_text(clock_text)
    if parsed is None:
        return None
    h, m, s = parsed
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if kind == "warn":
        target -= timedelta(minutes=10)
    return target


def _wait_until(target: datetime) -> None:
    """计划任务只能按整分钟触发，这里补足到精确的秒。"""
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 1.0))


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
    try:
        subprocess.Popen(
            [
                "powershell", "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass", "-Command", _balloon_ps(title, body),
            ],
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
    except Exception as e:
        _log(f"balloon failed: {e!r}")


def _fire(kind: str, clock_text: str) -> None:
    target = _popup_target(kind, clock_text, datetime.now())
    if target is not None:
        _wait_until(target)

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


def live_countdown(
    clock_out: datetime,
    pixel: str = PIXEL_NARROW,
    compress: bool = True,
    compact: bool = True,
):
    """全屏倒计时，大数字每秒刷新，Ctrl+C 退出。"""
    import time

    # 确保 Windows 终端支持 ANSI 转义序列
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    try:
        while True:
            now = datetime.now()
            remaining = clock_out - now

            if remaining.total_seconds() <= 0:
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()
                print()
                print(render_big("00:00:00", pixel, compress, compact))
                print()
                print("===== 下班时间到！！！=====")
                print()
                sys.stdout.flush()
                time.sleep(5)
                break

            total_sec = int(remaining.total_seconds())
            h, rem = divmod(total_sec, 3600)
            m, s = divmod(rem, 60)
            countdown_str = f"{h:02d}:{m:02d}:{s:02d}"

            # 清屏重绘
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            print(f"下班打卡: {clock_out.strftime('%H:%M:%S')}")
            print(f"距下班还有 {h}h{m:02d}m{s:02d}s")
            print()
            print(render_big(countdown_str, pixel, compress, compact))
            print()
            print("按 Ctrl+C 退出")
            sys.stdout.flush()

            time.sleep(1)

    except KeyboardInterrupt:
        pass


def main():
    # ── 确保终端能输出 emoji / 中文（Git Bash 默认 GBK 会炸）──
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if "--fire" in sys.argv:
        kind, clock_text = parse_fire_args(sys.argv)
        _fire(kind, clock_text)
        return

    # ── 解析参数 ──
    no_notify = "--no-notify" in sys.argv or "-n" in sys.argv
    watch_mode = "--watch" in sys.argv or "-w" in sys.argv
    mid_mode = "--mid" in sys.argv or "-m" in sys.argv
    big_mode = "--big" in sys.argv or "-b" in sys.argv
    tall_mode = "--tall" in sys.argv or "-t" in sys.argv
    compact = not (mid_mode or big_mode)
    pixel = PIXEL_WIDE if big_mode else PIXEL_NARROW
    compress = not tall_mode
    args = [a for a in sys.argv[1:] if not a.startswith("-")]

    if args:
        raw = args[0]
        clock_in = parse_time(raw)
    else:
        saved = _parse_clock_text(_scheduled_clock_text() or "")
        if saved is not None:
            h, m, s = saved
            clock_in = datetime.now().replace(
                hour=h, minute=m, second=s, microsecond=0
            ) - timedelta(hours=8, minutes=45)
            print(f"沿用已有排程：{h:02d}:{m:02d}:{s:02d} 下班（无需重新输入打卡时间）")
        else:
            print("输入打卡时间：")
            raw = input("> ").strip()
            clock_in = parse_time(raw)
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    clock_in = today + timedelta(
        hours=clock_in.hour, minutes=clock_in.minute, seconds=clock_in.second
    )
    clock_out = clock_in + timedelta(hours=8, minutes=45)

    in_str = clock_in.strftime("%H:%M:%S")
    out_str = clock_out.strftime("%H:%M:%S")

    # ── 计算剩余时间 ──
    remaining = clock_out - now
    if remaining.total_seconds() > 0:
        h, remainder = divmod(int(remaining.total_seconds()), 3600)
        m, s = divmod(remainder, 60)
        remain_text = f"距下班还有 {h}h{m:02d}m{s:02d}s"
    else:
        remain_text = "🎉 已经下班啦！"

    # ── 输出 ──
    print()
    print(f"上班打卡: {in_str}")
    print(f"下班打卡: {out_str}  ← {remain_text}")
    print()
    print(render_big(out_str, pixel, compress, compact))
    print()

    # ── 设置通知 ──
    if not no_notify:
        schedule_notification(clock_out)
    else:
        print("🔕 跳过通知设置（--no-notify）")

    # ── 实时倒计时 ──
    if watch_mode:
        print()
        input("按 Enter 开始倒计时...")
        live_countdown(clock_out, pixel, compress, compact)


if __name__ == "__main__":
    main()
