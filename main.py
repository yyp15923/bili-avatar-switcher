#!/usr/bin/env python3
"""
B站头像定时切换脚本
通过 Bilibili 的 face/update API 上传指定头像图片
"""

import os
import sys
import time
import mimetypes
import requests

# B站头像更新 API
FACE_UPDATE_API = "https://api.bilibili.com/x/member/web/face/update"


def parse_cookie(cookie_str: str) -> dict:
    """解析 cookie 字符串为字典"""
    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            key, value = item.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def get_csrf_token(cookies: dict) -> str:
    """从 cookie 中提取 bili_jct 作为 CSRF token"""
    token = cookies.get("bili_jct")
    if not token:
        raise ValueError(
            "Cookie 中未找到 bili_jct 参数。"
            "请确保 Cookie 完整，包含 SESSDATA 和 bili_jct。"
        )
    return token


def upload_face(image_path: str, cookie_str: str, csrf: str) -> dict:
    """上传头像到 B站"""
    url = f"{FACE_UPDATE_API}?csrf={csrf}"

    cookies = parse_cookie(cookie_str)

    with open(image_path, "rb") as f:
        file_data = f.read()

    # 构建 multipart 表单（自动识别真实 MIME 类型）
    mime = mimetypes.guess_type(image_path)[0] or "image/png"
    files = {
        "face": (os.path.basename(image_path), file_data, mime),
    }
    data = {
        "dopost": "save",
        "Displayrank": "10000",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://account.bilibili.com/account/face/upload",
        "Origin": "https://account.bilibili.com",
    }

    resp = requests.post(
        url,
        cookies=cookies,
        data=data,
        files=files,
        headers=headers,
        timeout=30,
    )

    try:
        result = resp.json()
    except Exception:
        result = {"code": resp.status_code, "message": resp.text[:200]}

    return result


def main():
    if len(sys.argv) < 3:
        print("用法: python main.py <cookie> <image_path>")
        print("  cookie: B站完整 cookie 字符串")
        print("  image_path: 头像图片路径 (PNG/JPG, 不超过 2MB)")
        sys.exit(1)

    cookie_str = sys.argv[1]
    image_path = sys.argv[2]

    # 检查文件
    if not os.path.exists(image_path):
        print(f"[错误] 图片文件不存在: {image_path}")
        sys.exit(1)

    file_size = os.path.getsize(image_path)
    if file_size > 2 * 1024 * 1024:
        print(f"[警告] 图片大小 {file_size} 字节，超过 2MB 限制，可能被拒绝")

    print(f"[信息] 准备上传头像: {image_path} ({file_size} bytes)")

    # 获取 CSRF
    cookies = parse_cookie(cookie_str)
    csrf = get_csrf_token(cookies)
    print("[信息] CSRF Token 获取成功")

    # 上传
    result = upload_face(image_path, cookie_str, csrf)

    if result.get("code") == 0:
        print("[成功] 头像更新成功！(B站可能有缓存延迟，约半小时后生效)")
    else:
        code = result.get("code", "unknown")
        message = result.get("message", "未知错误")
        print(f"[失败] code={code}, message={message}")

        if code == 40012:
            print("  → 头像格式错误，请使用 PNG 或 JPG 格式")
        elif code == 40013:
            print("  → 头像大小超过 2MB 限制")
        elif code == -400:
            print("  → 请求参数错误，请检查 cookie 是否完整")
        elif code == -101:
            print("  → 登录状态失效，请更新 Cookie (SESSDATA 可能过期)")
        elif code == -403:
            print("  → 权限不足，可能需要重新登录获取新 Cookie")

        sys.exit(1)


if __name__ == "__main__":
    main()
