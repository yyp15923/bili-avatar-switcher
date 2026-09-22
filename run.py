#!/usr/bin/env python3
"""B站头像自动切换 —— 巡检式编排脚本（纯标准库，无需 pip install）。

设计要点
--------
GitHub Actions 的 schedule cron 并不准点，实测会延迟 3~13 小时（免费账号在高峰期排队）。
所以本方案不再"押宝某一次准点触发"，而是：

  * 每 30 分钟巡检一次；
  * 按【北京时间】算出当前时段该显示哪张图；
  * 调 nav 接口读取当前头像 URL —— B站头像 URL 是图片内容哈希，同一张图永远返回同一个 URL；
  * 只有当"当前头像 != 目标图"时才真正上传，其余时候零操作直接退出。

这样无论 GitHub 延迟多久，只要 30 分钟内能跑起来一次，切换误差就 <= 30 分钟，
且稳定状态下每天只上传 2 次，不会触发 B站风控。

模式:
  python run.py auto    巡检（默认）：按需切换，cookie 失效则静默跳过(exit 0)
  python run.py check   只体检 cookie：有效 exit 0，失效 exit 1 → workflow 跑红 → GitHub 发邮件
  python run.py force   无视时段判断，强制按当前时段上传一次

时段规则（北京时间）:
  08:35 ~ 17:30  -> images/day.jpg
  17:30 ~ 次日08:35 -> images/night.jpg

纠偏窗口（仅当当前头像是"陌生图"时生效，避免覆盖你手动设的头像）:
  day   : 08:30 ~ 10:00
  night : 17:30 ~ 19:00

依赖 env:
  BILI_COOKIE   当前 cookie
"""
import os
import sys
import json
import uuid
import mimetypes
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
BJ = timezone(timedelta(hours=8))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
NAV_API = "https://api.bilibili.com/x/web-interface/nav"
FACE_API = "https://api.bilibili.com/x/member/web/face/update"

# B站头像 URL 是图片内容哈希，同一张图上传后返回的 URL 固定。
# 探测命令: python probe_face.py "<cookie>"
KNOWN_FACE = {
    "day": "https://i2.hdslb.com/bfs/face/3dba4bf6d4d72b5459512b772b1c6b9a09c6cd6f.jpg",
    "night": "https://i2.hdslb.com/bfs/face/22059c511f757d722d70f4bdf915df65360a2822.jpg",
}

# 北京时间纠偏窗口 (起始小时, 起始分钟, 结束小时, 结束分钟)
WINDOW = {
    "day": (8, 30, 10, 0),
    "night": (17, 30, 19, 0),
}


def http_get(url, cookie):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Cookie": cookie}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def get_state(cookie):
    """返回 (是否登录, 当前头像URL, 昵称)。异常时 is_login=False。"""
    try:
        d = http_get(NAV_API, cookie)
    except Exception as e:
        print(f"[异常] nav 请求失败: {e}")
        return False, None, None
    data = d.get("data", {}) or {}
    login = d.get("code") == 0 and data.get("isLogin") in (True, 1)
    return login, data.get("face"), data.get("uname")


def bj_now():
    return datetime.now(BJ)


def target_of(now):
    """按北京时间返回该显示的图: day / night"""
    hm = (now.hour, now.minute)
    if hm >= (8, 35) and hm < (17, 30):
        return "day"
    return "night"


def in_window(name, now):
    sh, sm, eh, em = WINDOW[name]
    return (now.hour, now.minute) >= (sh, sm) and (now.hour, now.minute) < (eh, em)


def upload_face(img_name, cookie, csrf):
    """用标准库构造 multipart/form-data 上传头像"""
    path = os.path.join(BASE, "images", f"{img_name}.jpg")
    with open(path, "rb") as f:
        payload = f.read()
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    boundary = "----bili" + uuid.uuid4().hex

    def field(name, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    def file_part():
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="face"; filename="{img_name}.jpg"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        return head + payload + b"\r\n"

    body = (
        field("dopost", "save")
        + field("Displayrank", "10000")
        + file_part()
        + f"--{boundary}--\r\n".encode()
    )

    req = urllib.request.Request(
        f"{FACE_API}?csrf={csrf}",
        data=body,
        method="POST",
        headers={
            "User-Agent": UA,
            "Referer": "https://account.bilibili.com/account/face/upload",
            "Origin": "https://account.bilibili.com",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Cookie": cookie,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"code": e.code, "message": e.read()[:200].decode("utf-8", "replace")}
    except Exception as e:
        return {"code": -1, "message": str(e)}


def cookie_of():
    return os.environ.get("BILI_COOKIE", "").strip()


def csrf_of(cookie):
    for item in cookie.split(";"):
        item = item.strip()
        if item.startswith("bili_jct="):
            return item.split("=", 1)[1].strip()
    return ""


def cmd_check():
    cookie = cookie_of()
    login, _face, uname = get_state(cookie)
    if login:
        print(f"当前 cookie 有效 ✓ (用户: {uname})")
        sys.exit(0)
    print("当前 cookie 已失效！", file=sys.stderr)
    print("GitHub 会给你发一封失败邮件。收到后，在你的电脑上运行:", file=sys.stderr)
    print("  pip install qrcode pillow && python login.py relogin", file=sys.stderr)
    print("扫码后把打印出来的 cookie 粘贴到仓库 Settings → Secrets → Actions → BILI_COOKIE", file=sys.stderr)
    sys.exit(1)


def cmd_auto(force=False):
    cookie = cookie_of()
    if not cookie:
        print("[错误] 环境变量 BILI_COOKIE 为空", file=sys.stderr)
        sys.exit(1)

    login, face, uname = get_state(cookie)
    if not login:
        # 巡检不报警（否则一天 48 封邮件）；报警交给每天一次的 check
        print("cookie 已失效，静默跳过本次巡检（等待每日体检邮件提醒）")
        sys.exit(0)

    now = bj_now()
    target = target_of(now)
    want = KNOWN_FACE[target]
    other = "night" if target == "day" else "day"

    print(f"北京时间 {now:%Y-%m-%d %H:%M} | 用户 {uname} | 目标 {target}.jpg")
    print(f"当前头像 {face}")

    if not force:
        if face == want:
            print(f"当前头像已是目标图 {target}.jpg，无需操作 ✓")
            sys.exit(0)
        if face == KNOWN_FACE[other]:
            print(f"当前还是 {other}.jpg，立即纠正为 {target}.jpg")
        elif not in_window(target, now):
            print(
                f"当前头像既不是 day 也不是 night（你可能手动换过），"
                f"且不在 {target} 的纠偏窗口内 → 保持不动，尊重你的手动设置"
            )
            sys.exit(0)
        else:
            print(f"当前头像是陌生图，处于 {target} 纠偏窗口内 → 切换")

    csrf = csrf_of(cookie)
    if not csrf:
        print("[错误] cookie 中缺少 bili_jct", file=sys.stderr)
        sys.exit(1)

    res = upload_face(target, cookie, csrf)
    if res.get("code") == 0:
        print(f"[成功] 头像已切换为 images/{target}.jpg")
        sys.exit(0)
    print(f"[失败] code={res.get('code')} msg={res.get('message')}", file=sys.stderr)
    sys.exit(1)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode == "check":
        cmd_check()
    elif mode == "auto":
        cmd_auto(force=False)
    elif mode == "force":
        cmd_auto(force=True)
    else:
        print("用法: run.py [auto|check|force]")
        sys.exit(2)


if __name__ == "__main__":
    main()
