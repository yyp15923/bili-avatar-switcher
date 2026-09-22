# B站头像白天/夜晚自动切换

利用 B站官方头像更新接口 `x/member/web/face/update`，配合 GitHub Actions，
按北京时间自动在「白天图 / 夜晚图」之间切换。

## 当前运行方式：本机计划任务（主力） + GitHub Actions（兜底）

> **重要背景**：GitHub Actions 的 `schedule` 在本仓库实测**已停止发车**——
> 连续 15 小时 0 次定时运行，另建探测 workflow 定在三个相邻分钟点也全部未触发；
> 同期手动触发（`workflow_dispatch`）却能秒起。
> 排除项：非 fork、未禁用、Actions 全开、公共仓库无额度问题。
> 结论是调度器不可用，不是延迟问题。
>
> 所以主力改为**本机 Windows 计划任务**，直接连 B站换头像，不经过 GitHub。
> GitHub 那套保留着，哪天调度器恢复了就是白送的一层兜底。

### 本机计划任务（已在 DESKTOP-JTF6GG1 上建好）

- 任务名：`BiliAvatarSwitch`
- 频率：每 15 分钟一次；用 `pythonw.exe` 静默执行，不弹黑窗口
- cookie 放在 `cookie.txt`（已在 `.gitignore` 里，不会进仓库）
- 运行日志：`logs/switch.log`

查看 / 手动跑一次：

```bat
schtasks /Query /TN "BiliAvatarSwitch" /FO LIST
schtasks /Run   /TN "BiliAvatarSwitch"
type logs\switch.log
```

重建任务（换电脑或重装后）：

```bat
set PYW=C:\Users\yp\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe
set RUN=C:\Users\yp\WorkBuddy\2026-09-20-10-45-14\bili-avatar-switcher\run.py
schtasks /Create /TN "BiliAvatarSwitch" /TR "\"%PYW%\" \"%RUN%\" auto" /SC MINUTE /MO 15 /F
```

> 局限：电脑关机 / 深度睡眠时不执行。8:35 和 17:30 基本都在用电脑，够用；
> 若某次错过，下一次巡检（15 分钟内）会自动纠正回来。

## 核心设计：为什么是「巡检」而不是「两个闹钟」

GitHub Actions 的 `schedule` **并不准点**。本仓库实测：

| 计划 cron (UTC) | 对应北京时间 | 实际触发时间(北京) | 延迟 |
|---|---|---|---|
| `35 0 * * *` | 08:35 | 21:38 | ~13 小时 |
| `30 6 * * *` | 14:30 | 21:04 | ~6.5 小时 |
| `30 9 * * *` | 17:30 | 23:58 | ~6.5 小时 |

免费账号在高峰期排队，延迟几小时是常态。所以本方案**不押宝某一次准点触发**，而是：

1. **每 30 分钟巡检一次**（`cron: "*/30 * * * *"`）；
2. 按【北京时间】算出当前时段该显示哪张图；
3. 调 `nav` 接口读当前头像 URL —— **B站头像 URL 是图片内容哈希，同一张图永远返回同一个 URL**；
4. 只有「当前头像 ≠ 目标图」时才真正上传，其余时候零操作退出。

效果：无论 GitHub 延迟多久，切换误差 ≤ 30 分钟；稳定态每天只上传 2 次，不触发风控。

## 时段规则（北京时间）

| 时段 | 显示 |
|---|---|
| 08:35 ~ 17:30 | `images/day.jpg` |
| 17:30 ~ 次日 08:35 | `images/night.jpg` |
| 每天 14:30 | 体检 cookie，失效才跑红 → GitHub 发邮件 |

纠偏窗口（仅在「当前头像是陌生图」时才动手，避免覆盖你手动设置的头像）：
day `08:30~10:00`，night `17:30~19:00`。

## 首次部署

1. 在 GitHub 建仓库，把本项目文件推上去。
2. 仓库 **Settings → Secrets and variables → Actions** 新建 secret：
   - `BILI_COOKIE` = 你的 B站整段 cookie（登录 bilibili 后 F12 → Network → 复制任一请求的 `cookie:` 整段）。
3. 进 **Actions** 面板手动跑一次，mode 选 `check`，确认 cookie 有效（绿）。

## cookie 过期怎么办（关键）

cookie 一般几天到几周过期。过期后：

1. 每天 14:30 的体检会跑红，**GitHub 自动给你（仓库 owner）发一封失败邮件**。
2. 你在任意电脑（本仓库克隆目录）运行：
   ```bash
   pip install qrcode pillow
   python login.py relogin
   ```
   终端生成二维码 `qr.png`（并打印扫码链接）→ 用 **B站 App** 扫 →
   成功后终端打印**新 cookie** 一整行。
3. 把新 cookie 写回 secret，二选一：
   - 手动：粘贴到 **Settings → Secrets → Actions → BILI_COOKIE**（覆盖旧值）；
   - 命令行：
     ```bash
     pip install pynacl
     export GITHUB_TOKEN="ghp_xxx"      # 需要 repo 权限
     python set_secret.py "<新cookie>"
     ```

> 为什么不在 GitHub 上自动扫码：B站登录二维码 180 秒就过期，Actions 下载/扫码来回不及时。
> 所以采用「邮件提醒 + 本地一条命令扫码续期」，几个月一次，每次 1 分钟。

## 换图 / 改时间

- **换头像**：替换 `images/day.jpg`、`images/night.jpg` 后提交，
  然后跑一次 `python probe_face.py "<cookie>"` 拿到新的 face URL，
  更新 `run.py` 里 `KNOWN_FACE` 两个常量（否则幂等判断会失效）。
- **改时间**：改 `run.py` 里 `target_of()` 的时段判断 和 `WINDOW` 常量即可，
  workflow 的 `*/30` 巡检不用动。

## 本地测试

```bash
pip install -r requirements.txt
python main.py "<你的cookie>" "images/day.jpg"   # 直接上传（会真换头像）
# 或走编排逻辑：
export BILI_COOKIE="<你的cookie>"
python run.py auto     # 按需切换（幂等）
python run.py check    # 只体检
python run.py force    # 强制按当前时段上传一次
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `run.py` | Actions 编排：`auto` 巡检切换 / `check` 体检 / `force` 强制上传（纯标准库，无需 pip） |
| `main.py` | 调 B站接口上传头像，含错误码翻译 |
| `login.py` | 扫码登录：`relogin` 一条命令拿新 cookie |
| `set_secret.py` | 命令行写回 GitHub Secret（libsodium sealed-box 加密） |
| `probe_face.py` | 探测两张图对应的 face URL，用于更新 `KNOWN_FACE` |
| `.github/workflows/switch-avatar.yml` | 每 30 分钟巡检 + 每日体检 |
| `images/day.jpg` / `night.jpg` | 白天 / 夜晚头像 |

## 额度

每天 48 次巡检 × 约 15 秒 ≈ 12 分钟/天 ≈ 360 分钟/月。
公共仓库 Actions 免费无限；私有仓库免费额度 2000 分钟/月，也够用。
