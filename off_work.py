"""下班时间计算器 — 打卡时间 + 8h45m = 下班时间，大字体显示 + 下班提醒通知"""

import sys
import subprocess
import tempfile
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


def _create_task(task_name: str, trigger_time: datetime, title: str, body: str) -> bool:
    """创建单次计划任务，触发时弹气泡通知。"""

    # PowerShell 气泡通知脚本
    ps_code = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$b = New-Object System.Windows.Forms.NotifyIcon; "
        "$b.Icon = [System.Drawing.SystemIcons]::Information; "
        "$b.BalloonTipIcon = 'Info'; "
        f'$b.BalloonTipTitle = "{title}"; '
        f'$b.BalloonTipText = "{body}"; '
        "$b.Visible = $true; "
        "$b.ShowBalloonTip(0); "
        "Start-Sleep -Seconds 5; "
        "$b.Dispose()"
    )
    script_path = Path(tempfile.gettempdir()) / f"_offwork_{trigger_time.strftime('%H%M%S')}.ps1"
    script_path.write_text(ps_code, encoding="utf-8-sig")
    script_path_str = str(script_path).replace("\\", "\\\\")

    cmd = [
        "schtasks", "/create", "/f",
        "/sc", "once",
        "/tn", task_name,
        "/tr", f'powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File "{script_path_str}"',
        "/st", trigger_time.strftime("%H:%M"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def schedule_notification(clock_out: datetime) -> bool:
    """创建两个 Windows 计划任务：下班前 5 分钟提醒 + 下班提醒。"""
    now = datetime.now()

    # schtasks 只支持分钟精度，秒数向上取整
    if clock_out.second > 0 or clock_out.microsecond > 0:
        main_time = clock_out.replace(second=0, microsecond=0) + timedelta(minutes=1)
    else:
        main_time = clock_out

    warn_time = main_time - timedelta(minutes=5)

    if main_time <= now:
        print("⚠️  下班时间已过，不设置提醒。")
        return False

    ok = True

    # ── 提前 5 分钟提醒 ──
    if warn_time > now:
        warn_task_name = f"OffWorkReminder_Warn_{warn_time.strftime('%H%M')}"
        warn_body = (
            f"还有 5 分钟下班！收拾东西准备走啦～`r`n`r`n"
            f"下班打卡: {clock_out.strftime('%H:%M')}"
        )
        if _create_task(warn_task_name, warn_time, "下班提醒", warn_body):
            remaining = warn_time - now
            h, remainder = divmod(int(remaining.total_seconds()), 3600)
            m, _ = divmod(remainder, 60)
            print(f"⏰ 已设置提前提醒 — {h} 小时 {m} 分钟后")
        else:
            ok = False
    else:
        print("⚠️  提前 5 分钟提醒时间已过，跳过。")

    # ── 下班准时提醒 ──
    main_task_name = f"OffWorkReminder_{main_time.strftime('%H%M')}"
    main_body = (
        f"到下班时间啦！辛苦一天，该走了！`r`n`r`n"
        f"打卡: {clock_out.strftime('%H:%M')}"
    )
    if _create_task(main_task_name, main_time, "下班提醒", main_body):
        remaining = main_time - now
        h, remainder = divmod(int(remaining.total_seconds()), 3600)
        m, _ = divmod(remainder, 60)
        print(f"✅ 已设置下班提醒 — {h} 小时 {m} 分钟后")
    else:
        ok = False
        print("❌ 设置下班提醒失败")

    return ok


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
