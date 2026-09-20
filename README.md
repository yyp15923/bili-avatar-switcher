# B站头像白天/夜晚自动切换

利用 B站官方的头像更新接口 `x/member/web/face/update`，配合 GitHub Actions 定时任务，
每天固定时间自动更换 B站头像：早上切白天图，晚上切夜晚图。

## 原理

- B站允许通过 API 直接上传更换头像，需要登录态（Cookie）+ CSRF 校验。
- GitHub Actions 提供免费的定时执行环境，无需自己的服务器。
- 本仓库放两张头像图（白天 / 夜晚），到点自动调用接口上传对应那张。

## 使用步骤

### 1. Fork 本仓库
点右上角 **Fork**，复制到自己 GitHub 账号下。

### 2. 放入自己的头像
把两张 180×180（或更大）的 PNG 图片替换到 `images/` 目录：
- `images/day.png`   — 白天头像
- `images/night.png` — 夜晚头像

> 头像大小不超过 2MB，PNG 或 JPG 均可。

### 3. 获取 B站 Cookie
1. 用 Chrome 登录 [bilibili.com](https://www.bilibili.com)。
2. 按 `F12` 打开开发者工具，切到 **Application / 存储** 标签。
3. 在 Cookies 里找到 `bilibili.com` 域下的这些项，复制它们的值：
   - `SESSDATA`
   - `bili_jct`
   - `DedeUserID`（可选）
4. 把它们拼成一整段标准 cookie 字符串，形如：
   ```
   SESSDATA=xxxx; bili_jct=yyyy; DedeUserID=12345; ...
   ```
   最简单的做法：打开 B站任意页面，F12 → Network → 随便点一个请求 →
   复制 Request Headers 里的 `cookie:` 后面整段内容即可。

### 4. 配置 Secrets
在 Fork 的仓库里：**Settings → Secrets and variables → Actions → New repository secret**
新建一个名为 `BILI_COOKIE` 的 secret，值填上面那整段 cookie 字符串。

> ⚠️ Cookie 会过期（一般几天到几周）。过期后自动任务会失败，
> 需重新登录 B站并更新 `BILI_COOKIE`。

### 5. 开启定时 / 手动测试
- 定时：本仓库工作流已写好，每天
  - **北京时间 08:00** 切到白天图
  - **北京时间 20:00** 切到夜晚图

  （GitHub Actions 时区是 UTC，已换算好，无需改。）
- 手动测试：进 **Actions** 面板 → 选 `Bili Avatar Switcher` →
  Run workflow，勾选是否用夜晚图，立即跑一次验证 cookie 是否有效。

## 常见问题

- **返回 -101 / 登录失效**：cookie 过期，重新获取更新 secret。
- **头像没立刻变**：B站有 CDN 缓存，约半小时到一小时后生效，属正常。
- **想改切换时间**：编辑 `.github/workflows/switch-avatar.yml` 里的
  两条 `cron`（注意是 UTC，比北京时间早 8 小时），并同步改 `main.py` 的判定逻辑。
- **想加第三张图**：在 `images/` 加文件，并在 workflow 里增加一个 cron + 分支判断。

## 本地测试
```bash
pip install -r requirements.txt
python main.py "<你的cookie>" "images/day.png"
```