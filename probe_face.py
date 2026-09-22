#!/usr/bin/env python3
"""探测：B站对同一张头像是否返回稳定的 face URL。

用法: python probe_face.py "<cookie>"
会依次上传 day -> day -> night -> night -> day，每次记录 nav 返回的 face URL。
目的：确认"同一张图的 face URL 是否稳定"，从而支持无状态的幂等判断。
"""
import sys
import time
import requests

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from main import parse_cookie, get_csrf_token, upload_face

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


def nav_face(cookie):
    r = requests.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Cookie": cookie},
        timeout=20,
    )
    j = r.json()
    return j.get("data", {}).get("face"), j.get("data", {}).get("uname")


def main():
    cookie = sys.argv[1].strip()
    csrf = get_csrf_token(parse_cookie(cookie))
    base = __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0]

    print("初始 face:", nav_face(cookie))
    seq = ["day", "day", "night", "night", "day"]
    for name in seq:
        img = f"{base}/images/{name}.jpg"
        res = upload_face(img, cookie, csrf)
        time.sleep(3)
        face, uname = nav_face(cookie)
        print(f"上传 {name:6} -> code={res.get('code')} msg={res.get('message')} | face={face}")
        time.sleep(3)
    print("结束 face:", nav_face(cookie))


if __name__ == "__main__":
    main()
