#!/usr/bin/env python3
"""GitHub Actions 编排脚本：cookie 体检 + 头像切换。

模式:
  python run.py switch <day|night|auto>   cookie 有效 → 上传对应头像；失效 → 记录日志、跳过(不报错)
  python run.py check                     体检 cookie；有效=exit 0，失效=exit 1
                                          (失效时 workflow 跑红 → GitHub 自动邮件提醒你)

为什么不用 GitHub 自动扫描码：B站二维码 180 s 就过期，Actions 上下下来回不及时。
续期是半自动: cookie 失效 → GitHub 给你发失败邮件 → 你在本机跑 `python login.py relogin`
扫码 → 把打印出来的新 cookie 粘贴到仓库 Secrets 的 BILI_COOKIE 即可。

依赖 env:
  BILI_COOKIE   当前 cookie
"""
import os
import sys
import subprocess
import urllib.request
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as bili_main  # 复用头像上传逻辑 (改名避免与本地 main() 冲突)

NAVTAG = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


def cookie_valid(cookie: str) -> bool:
    req = urllib.request.Request(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"User-Agent": NAVTAG, "Referer": "https://www.bilibili.com/", "Cookie": cookie},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
        return d.get("code") == 0 and d.get("data", {}).get("isLogin") in (True, 1)
    except Exception as e:
        print(f"cookie 体检请求异常: {e}")
        return False


def pick_image(mode: str) -> str:
    # UTC: 0:35(北京8:35)=day ; 9:30(北京17:30)=night
    if mode in ("day", "night"):
        return f"images/{mode}.jpg"
    utc_hour = int(subprocess.run(["date", "-u", "+%H"], capture_output=True, text=True).stdout.strip() or "0")
    return "images/day.jpg" if utc_hour < 6 else "images/night.jpg"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    cookie = os.environ.get("BILI_COOKIE", "").strip()

    if mode == "check":
        # 【测试模式】强制失败，验证 GitHub 邮件提醒是否正常
        print("[测试] 模拟 cookie 失效，验证 GitHub 邮件提醒", file=sys.stderr)
        sys.exit(1)
        print("GitHub 会给你发一封失败邮件。收到后，在你的电脑上运行:", file=sys.stderr)
        print("  pip install qrcode pillow && python login.py relogin", file=sys.stderr)
        print("扫码后把打印出来的 cookie 粘贴到仓库 Settings → Secrets → Actions → BILI_COOKIE", file=sys.stderr)
        sys.exit(1)

    if mode == "switch":
        img_arg = sys.argv[2] if len(sys.argv) > 2 else "auto"
        img = pick_image(img_arg)
        if not cookie_valid(cookie):
            print(f"cookie 失效，跳过本次切换 ({img}) —— 等待 14:30 的体检提醒你")
            sys.exit(0)  # 故意不失败，避免 8:35/17:30 重复邮件骚扰
        csrf = bili_main.get_csrf_token(bili_main.parse_cookie(cookie))
        result = bili_main.upload_face(img, cookie, csrf)
        if result.get("code") == 0:
            print(f"[成功] 头像已切换为 {img}")
            sys.exit(0)
        print(f"[失败] code={result.get('code')} msg={result.get('message')}", file=sys.stderr)
        sys.exit(1)

    print("用法: run.py check  |  run.py switch [day|night|auto]")
    sys.exit(2)


if __name__ == "__main__":
    main()
