#!/usr/bin/env python3
"""GitHub Actions 编排脚本：cookie 体检 → 失效则扫码自动续期并写回 secret → 切换头像。

模式:
  python run.py switch <day|night>   确保持 cookie 有效后上传对应头像
  python run.py check                只体检+续期（不改头像）

依赖 env:
  BILI_COOKIE       当前 cookie
  WECOM_WEBHOOK     企业微信机器人 webhook 完整 URL (可空: 没有就只在日志里提示)
  GITHUB_TOKEN      用于把新 cookie 写回 secret (Actions 自动注入)
  GITHUB_REPOSITORY 仓库 full_name
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as bili_main  # 复用头像上传逻辑 (改名避免与本地 main() 函数冲突)

NAVTAG = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


def _post_json(url, payload, extra_headers=None):
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or b"{}")


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


def wecom_notify(text: str, image_path: str = None):
    url = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not url:
        print("(未配置 WECOM_WEBHOOK，跳过企业微信通知)")
        return
    try:
        _post_json(url, {"msgtype": "text", "text": {"content": text}})
        if image_path and os.path.exists(image_path):
            raw = open(image_path, "rb").read()
            _post_json(url, {
                "msgtype": "image",
                "image": {"base64": base64.b64encode(raw).decode(), "md5": hashlib.md5(raw).hexdigest()},
            })
            print("二维码已推送企业微信")
    except Exception as e:
        print(f"企业微信推送失败: {e}")


def relogin_cookie() -> str:
    """生成二维码→推送→等待扫码，最多 3 轮。成功返回新 cookie，失败返回空串。"""
    for round_no in (1, 2, 3):
        print(f"--- 扫码续期 第 {round_no} 轮 ---")
        try:
            out = subprocess.run(
                [sys.executable, "login.py", "qr"],
                capture_output=True, text=True, timeout=60,
            )
            if out.returncode != 0:
                print("生成二维码失败:", out.stderr.strip()[:200])
                continue
            key = out.stdout.strip()
            wecom_notify(
                f"【B站头像任务】登录 cookie 已过期，请在下方二维码上打开 B站 App 扫码，"
                f"扫码后自动续期（第 {round_no}/3 轮，每轮约 60 秒）",
                "qr.png",
            )
            r = subprocess.run(
                [sys.executable, "login.py", "wait", key, "--out", "cookie_new.txt", "--timeout", "45"],
                capture_output=True, text=True, timeout=60,
            )
            print(r.stdout.strip() or r.stderr.strip()[:200])
            if r.returncode == 0 and os.path.exists("cookie_new.txt"):
                cookie = open("cookie_new.txt").read().strip()
                if cookie_valid(cookie):
                    print("新 cookie 体检通过 ✓")
                    return cookie
                print("新 cookie 体检未通过，重试")
        except Exception as e:
            print(f"扫码流程异常: {e}")
    return ""


def write_back_secret(cookie: str):
    """把新 cookie 写回 GitHub 仓库 secret BILI_COOKIE（openssl 加密）。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("(缺少 GITHUB_TOKEN/GITHUB_REPOSITORY，跳过 secret 回写)")
        return
    base = f"https://api.github.com/repos/{repo}/actions/secrets"
    H = {"Authorization": f"token {token}", "Accept": "application/json", "User-Agent": "run.py"}
    try:
        pk = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/public-key", headers=H), timeout=30).read().decode())
        key_id = pk["key_id"]
        der = base64.b64decode(pk["key"])
        # 包一层 PEM 头，openssl 才能读
        open("pub.pem", "w").write(
            "-----BEGIN PUBLIC KEY-----\n"
            + base64.b64encode(der).decode()
            + "\n-----END PUBLIC KEY-----\n"
        )
        p = subprocess.run(
            ["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", "pub.pem",
             "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_md_algorithm:sha256",
             "-in", "cookie_new.txt"],
            capture_output=True, timeout=60,
        )
        if p.returncode != 0:
            raise RuntimeError(f"openssl 加密失败: {p.stderr.decode()[:200]}")
        enc = base64.b64encode(p.stdout).decode()
        req = urllib.request.Request(
            f"{base}/BILI_COOKIE",
            data=json.dumps({"name": "BILI_COOKIE", "encrypted_value": enc, "key_id": key_id}).encode(),
            method="PUT", headers=H,
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"新 cookie 已写回 secret BILI_COOKIE (HTTP {r.status})")
    except Exception as e:
        print(f"secret 回写失败: {e}")


def ensure_cookie(cookie: str) -> str:
    if cookie_valid(cookie):
        print("当前 cookie 有效 ✓")
        return cookie
    print("当前 cookie 已失效，尝试扫码续期…")
    new = relogin_cookie()
    if new:
        write_back_secret(new)
        return new.strip()
    print("扫码续期失败（本轮放弃）")
    return ""


def pick_image(mode: str) -> str:
    # UTC: 0:35(北京8:35)=day, 9:30(北京17:30)=night
    if mode in ("day", "night"):
        return f"images/{mode}.jpg"
    utc_hour = int(subprocess.run(["date", "-u", "+%H"], capture_output=True, text=True).stdout.strip() or "0")
    return "images/day.jpg" if utc_hour < 6 else "images/night.jpg"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    cookie = os.environ.get("BILI_COOKIE", "").strip()

    if mode == "check":
        ensure_cookie(cookie)
        return

    if mode not in ("switch",):
        print("用法: run.py check | run.py switch [day|night|auto]")
        sys.exit(2)
    img_arg = sys.argv[2] if len(sys.argv) > 2 else "auto"
    img = pick_image(img_arg)

    cookie = ensure_cookie(cookie)
    if not cookie:
        print("[失败] 没有可用 cookie，本次切换取消")
        sys.exit(1)

    # 扫码续期拿到的是原始 cookie 串，直接可用
    csrf = bili_main.get_csrf_token(bili_main.parse_cookie(cookie))
    result = bili_main.upload_face(img, cookie, csrf)
    if result.get("code") == 0:
        print(f"[成功] 头像已切换为 {img}")
    else:
        print(f"[失败] code={result.get('code')} msg={result.get('message')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
