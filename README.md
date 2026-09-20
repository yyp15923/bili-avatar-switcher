# B站头像白天/夜晚自动切换

利用 B站官方的头像更新接口 `x/member/web/face/update`，配合 GitHub Actions 定时任务，
每天固定时间自动更换 B站头像：早上切白天图，下午切夜晚图。

## 原理

- B站允许通过 API 直接上传更换头像，需要登录态（Cookie）+ CSRF 校验。
- GitHub Actions 提供免费的定时执行环境，无需自己的服务器。
- 本仓库放两张头像图（白天 / 夜晚），到点自动调用接口上传对应那张。
- 每天 14:30 自动体检 cookie；失效时任务跑红，**GitHub 自动发邮件提醒你**。

## 定时（北京时间）

| 时间 | 动作 |
|---|---|
| 08:35 | 切换为白天图 `images/day.jpg` |
| 17:30 | 切换为夜晚图 `images/night.jpg` |
| 14:30 | 体检 cookie；失效则任务失败 → 发邮件提醒 |

（GitHub Actions 时区是 UTC，cron 已换算好，无需改。）

## 首次部署

1. 在 GitHub 建仓库，把本项目文件推上去。
2. 仓库 **Settings → Secrets and variables → Actions** 新建 secret：
   - `BILI_COOKIE` = 你的 B站整段 cookie（登录 bilibili 后 F12 → Network → 复制任一请求的 `cookie:` 整段）。
3. 进 **Actions** 面板手动跑一次 `check`，确认 cookie 有效（绿）。

## cookie 过期怎么办（关键）

cookie 一般几天到几周过期。过期后：

1. 14:30 的体检会跑红，**GitHub 自动给你（仓库 owner）发一封失败邮件**。
2. 你在任意电脑（本仓库克隆目录）运行：
   ```bash
   pip install qrcode pillow
   python login.py relogin
   ```
   终端会生成二维码 `qr.png`（也打印出扫码链接）→ 用 **B站 App** 扫 →
   成功后终端打印**新 cookie** 一整行。
3. 把那行新 cookie 粘贴回仓库 **Settings → Secrets → BILI_COOKIE**（覆盖旧值）。

> 为什么不在 GitHub 上自动扫码：B站登录二维码 180 秒就过期，且 Actions 下载/扫码来回不及时，
> 所以采用「邮件提醒 + 本地一条命令扫码续期」，全程你只花 1 分钟、几个月一次。

## 换图 / 改时间

- **换头像**：直接替换 `images/day.jpg`、`images/night.jpg` 后提交。
- **改时间**：编辑 `.github/workflows/switch-avatar.yml` 的 cron（UTC，北京时间 -8），
  并同步 `run.py` 里 `pick_image` 的 UTC 小时判断。

## 本地测试

```bash
pip install -r requirements.txt
# 用你的 cookie 直接试上传（会真正换你当前头像）
python main.py "<你的cookie>" "images/day.jpg"
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `main.py` | 调 B站接口上传头像，含错误码翻译 |
| `run.py` | Actions 编排：`check` 体检 / `switch` 切换 |
| `login.py` | 扫码登录：`relogin` 一条命令拿新 cookie |
| `.github/workflows/switch-avatar.yml` | 定时 + 手动触发 |
| `images/day.jpg` / `night.jpg` | 白天 / 夜晚头像 |
