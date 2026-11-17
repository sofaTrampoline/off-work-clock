# Off Work Clock ⏰

下班时间计算器 + Windows 通知提醒。输入打卡时间，自动计算 8h45m 后的下班时间，并设好 Windows 计划任务到点弹通知。

## 功能

- 超大 ASCII 艺术字在终端显示下班时间
- 到点弹深色圆角卡片，**必须点「知道了」才消失**；可点「10 分钟后再提醒」
- 下班前 10 分钟弹小卡提醒，30 秒自动消失
- `--watch` 实时全屏倒计时
- `--no-notify` 只计算不提醒

## 用法

```bash
# 正常：计算 + 设通知
python off_work.py 0845

# 交互式输入
python off_work.py

# 实时倒计时
python off_work.py 0845 --watch

# 只要计算
python off_work.py 0845 --no-notify
```

## 依赖

仅 Python 标准库（含 `tkinter`），无需安装第三方包。Windows 10/11 系统即可。
