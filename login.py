#!/usr/bin/env python3
"""B站扫码登录（官方接口，纯 API 无需浏览器）。

用法:
  python login.py qr                      生成二维码 qr.png，key 打到 stdout（供 run.py 内部用）
  python login.py wait KEY --out F --timeout N   轮询 KEY，成功把 cookie 写 F
  python login.py relogin                 【推荐】一条命令：生成二维码 → 等待 → 打印新 cookie
"""
import sys
import time
import json
import urllib.request

BASE = "https://passport.bilibili.com/x/passport-login/web/qrcode"
GENERATE = (BASE + "/generate?source=main-fe-header&go_url=https%3A%2F%2Fwww.bilibili.com%2F&web_location=333.1007")
POLL = BASE + "/poll"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}

# 只保留登录相关字段，其它无关 cookie 丢弃
WANTED = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "b_nut", "sid")


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.headers
        body = json.loads(r.read().decode())
    return body, raw


def collect_cookie(raw_headers):
    got = {}
    for v in raw_headers.get_all("Set-Cookie") or []:
        pair = v.split(";", 1)[0]
        if "=" in pair:
            k, val = pair.split("=", 1)
            got[k.strip()] = val.strip()
    if not got:
        return ""
    parts = [f"{k}={got[k]}" for k in WANTED if k in got]
    return "; ".join(parts) if parts else "; ".join(f"{k}={v}" for k, v in got.items())


def generate():
    """返回 (key, qrcode_url)"""
    d, _ = get_json(GENERATE)
    if d.get("code") != 0:
        print(f"generate 失败: {d}", file=sys.stderr)
        sys.exit(1)
    key = d["data"]["qrcode_key"]
    url = d["data"]["url"]
    try:
        import qrcode
        qrcode.make(url).save("qr.png")
    except Exception:
        print("(未安装 qrcode，跳过保存 qr.png；你可直接在浏览器打开下方链接扫码)", file=sys.stderr)
    return key, url


def wait(key, out=None, timeout=90):
    """轮询 key 直到登录成功，返回新 cookie；过期/超时返回 None。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            d, raw = get_json(f"{POLL}?qrcode_key={key}")
        except Exception:
            time.sleep(3)
            continue
        code = d.get("data", {}).get("code")
        if code == 0:
            cookie = collect_cookie(raw)
            if not cookie:
                print("登录成功但未拿到 Set-Cookie (可能被中间层吃掉)", file=sys.stderr)
                return None
            if out:
                with open(out, "w") as f:
                    f.write(cookie + "\n")
            return cookie
        if code in (86038, 86040):
            print("二维码已过期")
            return None
        # 86101 未扫码 / 86090 待确认
        time.sleep(3)
    print("等待超时")
    return None


def cmd_qr():
    key, url = generate()
    sys.stdout.write(key)


def cmd_wait():
    args = sys.argv[2:]
    key = args[0]
    out = "cookie.txt"
    timeout = 90
    if "--out" in args:
        out = args[args.index("--out") + 1]
    if "--timeout" in args:
        timeout = int(args[args.index("--timeout") + 1])
    cookie = wait(key, out=out, timeout=timeout)
    if cookie:
        print(f"扫码成功，新 cookie 已写入 {out}")
        sys.exit(0)
    sys.exit(1)


def cmd_relogin():
    """一条命令本地续期：生成二维码 → 等扫 → 打印新 cookie 到 stdout"""
    key, url = generate()
    print("已生成二维码: qr.png (也可在浏览器直接打开以下链接扫码):")
    print(f"  {url}")
    print("请用 B站 App 扫码 (最多 3 轮，每轮 60 s)…")
    cookie = None
    for round_no in range(1, 4):
        print(f"\n[第 {round_no} 轮，等待扫码…]")
        cookie = wait(key, timeout=60)
        if cookie:
            break
        print("本轮没扫到，60 s 后重新生成二维码…")
        key, url = generate()
    if not cookie:
        print("\n[失败] 三轮都没扫码成功，请再运行一次 `python login.py relogin`")
        sys.exit(1)
    print("\n" + "=" * 60)
    print("扫码成功！复制下面整行 → 粘贴到仓库 Settings → Secrets → Actions → BILI_COOKIE ：")
    print("=" * 60)
    print(cookie)
    sys.exit(0)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "relogin"
    if cmd == "qr":
        cmd_qr()
    elif cmd == "wait":
        cmd_wait()
    elif cmd == "relogin":
        cmd_relogin()
    else:
        print(__doc__)
        sys.exit(2)
