#!/usr/bin/env python3
"""B站扫码登录（passport.bilibili.com 官方接口，纯 API 无需浏览器）。

接口:
  generate: GET https://passport.bilibili.com/x/passport-login/web/qrcode/generate
            ?source=main-fe-header&go_url=https%3A%2F%2Fwww.bilibili.com%2F
            -> data.qrcode_key (32位), data.url (登录链接, 需渲染成二维码图)
  poll:     GET https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key=xxx
            -> data.code: 86101 未扫码 / 86090 已扫码待确认 / 0 成功 / 86038 已过期
            -> 成功时新 cookie 在响应的 Set-Cookie 头里 (SESSDATA, bili_jct, DedeUserID...)

用法:
  python login.py qr                     # 生成二维码存 qr.png，key 打到 stdout
  python login.py wait KEY --out FILE [--timeout 120]
                                         # 轮询等待扫码，成功把新 cookie 写入 FILE，退出码 0
依赖: pip install qrcode[pil]
"""
import sys
import time
import json
import urllib.request

GENERATE = ("https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            "?source=main-fe-header&go_url=https%3A%2F%2Fwww.bilibili.com%2F&web_location=333.1007")
POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}

# 需要保留的登录相关 cookie 字段
WANTED = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "b_nut", "sid")


def get_json(url):
    """GET 并解析 JSON，同时返回原始响应用以提取 Set-Cookie"""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw_headers = r.headers
        body = json.loads(r.read().decode())
    return body, raw_headers


def collect_cookie(raw_headers):
    """从 Set-Cookie 头拼出 cookie 字符串（只保留登录相关字段）"""
    got = {}
    for v in raw_headers.get_all("Set-Cookie") or []:
        pair = v.split(";", 1)[0]
        if "=" in pair:
            k, val = pair.split("=", 1)
            got[k.strip()] = val.strip()
    parts = [f"{k}={v}" for k, v in got.items() if k in WANTED]
    if "SESSDATA" not in got:
        # 部分场景 Set-Cookie 不全，退回保留全部
        parts = [f"{k}={v}" for k, v in got.items()]
    return "; ".join(parts)


def cmd_qr():
    d, _ = get_json(GENERATE)
    if d.get("code") != 0:
        print(f"generate 失败: {d}", file=sys.stderr)
        sys.exit(1)
    key = d["data"]["qrcode_key"]
    url = d["data"]["url"]
    import qrcode
    qrcode.make(url).save("qr.png")
    sys.stdout.write(key)


def cmd_wait(key, out, timeout):
    t0 = time.time()
    url = f"{POLL}?qrcode_key={key}"
    while time.time() - t0 < timeout:
        try:
            d, raw = get_json(url)
        except Exception:
            time.sleep(3)
            continue
        code = d.get("data", {}).get("code")
        if code == 0:
            cookie = collect_cookie(raw)
            if "SESSDATA" not in cookie:
                print("登录成功但未能提取 SESSDATA，Set-Cookie 可能被中间层吃掉", file=sys.stderr)
                sys.exit(1)
            with open(out, "w") as f:
                f.write(cookie + "\n")
            print(f"扫码成功，新 cookie 已写入 {out}")
            return 0
        if code == 86038:
            print("二维码已过期")
            return 1
        # 86101 未扫码 / 86090 待确认
        time.sleep(3)
    print("等待超时（二维码已过期）")
    return 1


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "qr":
        cmd_qr()
    elif cmd == "wait":
        args = sys.argv[2:]
        k = args[0]
        out = "cookie.txt"
        timeout = 120
        if "--out" in args:
            out = args[args.index("--out") + 1]
        if "--timeout" in args:
            timeout = int(args[args.index("--timeout") + 1])
        sys.exit(cmd_wait(k, out, timeout))
    else:
        print(__doc__)
        sys.exit(2)
