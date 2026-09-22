#!/usr/bin/env python3
"""把 BILI_COOKIE 写入 GitHub Actions Secrets。

GitHub 用的是 libsodium sealed-box（X25519，32 字节公钥），不是 RSA-OAEP。
用法:
    export GITHUB_TOKEN="ghp_xxx"        # 需要 repo 权限
    python set_secret.py "<新的 cookie 字符串>"
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error

from nacl import encoding, public

TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPO", "yyp15923/bili-avatar-switcher")
SECRET_NAME = "BILI_COOKIE"


def api(path, method="GET", data=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "set-secret")
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, body, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return {"__err__": e.code, "msg": e.read().decode()[:400]}


def main():
    if not TOKEN:
        print("请先设置环境变量 GITHUB_TOKEN（需要 repo 权限的 Personal Access Token）")
        sys.exit(1)
    if len(sys.argv) < 2:
        print('用法: python set_secret.py "<cookie>"')
        sys.exit(1)
    value = sys.argv[1].strip()

    pk = api("actions/secrets/public-key")
    if "key" not in pk:
        print("拿不到公钥:", pk)
        sys.exit(1)

    pub = public.PublicKey(pk["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pub).encrypt(value.encode())
    encrypted = base64.b64encode(sealed).decode()

    res = api(f"actions/secrets/{SECRET_NAME}", "PUT",
              {"encrypted_value": encrypted, "key_id": pk["key_id"]})
    if "__err__" in res:
        print("写入失败:", res)
        sys.exit(1)
    print(f"[OK] {SECRET_NAME} 已更新 (len={len(value)})")


if __name__ == "__main__":
    main()
