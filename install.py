#!/usr/bin/env python3
"""B站头像白天/夜晚自动切换 —— 一键安装到本机（Windows）

会做四件事：
  1. 把脚本和头像图复制到安装目录（默认 %USERPROFILE%\\bili-avatar-switcher）
  2. 写入 cookie（命令行给 / 粘贴 / 扫码登录三选一）
  3. 创建 Windows 计划任务：每 15 分钟静默巡检一次
  4. 立刻跑一次验证

用法（在本文件所在目录下执行）：
    python install.py                        # 交互式：引导你粘贴或扫码拿 cookie
    python install.py "<整段cookie>"          # 直接给 cookie，全程无交互
    python install.py "<cookie>" --dir D:\\my\\dir      # 指定安装目录
    python install.py --task-name MyTaskName            # 自定义计划任务名（装第二台机器时可选）

卸载：
    schtasks /Delete /TN "BiliAvatarSwitch" /F
"""
import os
import sys
import shutil
import subprocess

PKG = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TASK = "BiliAvatarSwitch"
# 兼容两种布局：
#   扁平布局（项目目录）: run.py / images/ 与 install.py 同级
#   技能布局（WorkBuddy skill）: scripts/*.py 与 install.py 同级，images/ 在上一级
SEARCH_DIRS = [PKG, os.path.dirname(PKG), os.path.join(PKG, "scripts")]
COPY_ITEMS = ["run.py", "main.py", "login.py", "probe_face.py", "set_secret.py",
              "requirements.txt", "README.md", ".gitignore", "images"]


def locate(item):
    for d in SEARCH_DIRS:
        p = os.path.join(d, item)
        if os.path.exists(p):
            return p
    return None


def parse_args():
    cookie, target, task = None, None, DEFAULT_TASK
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dir":
            target = args[i + 1]; i += 2
        elif a == "--task-name":
            task = args[i + 1]; i += 2
        elif not a.startswith("--") and cookie is None:
            cookie = a; i += 1
        else:
            i += 1
    return cookie, target, task


def copy_pkg(target):
    os.makedirs(target, exist_ok=True)
    n = 0
    for item in COPY_ITEMS:
        src = locate(item)
        if not src:
            print(f"      跳过（找不到）: {item}")
            continue
        dst = os.path.join(target, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        n += 1
    os.makedirs(os.path.join(target, "logs"), exist_ok=True)
    print(f"[1/4] 已复制 {n} 项到 {target}")
    return target


def get_cookie(cookie, target):
    cookie_file = os.path.join(target, "cookie.txt")
    if cookie:
        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write(cookie.strip())
        print("[2/4] cookie 已写入 cookie.txt")
        return cookie_file

    if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 50:
        print("[2/4] 复用已有的 cookie.txt")
        return cookie_file

    print("[2/4] 需要你的 B站 cookie。两种方式：")
    print("      A. 浏览器登录 bilibili.com → F12 → Network → 随便点一个请求 →")
    print("         复制 Request Headers 里 cookie: 后面那一整段，粘贴到这里回车")
    print("      B. 直接回车，改用扫码登录（需要 pip install qrcode pillow）")
    v = input("cookie> ").strip()
    if v:
        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write(v)
        print("      cookie 已保存")
        return cookie_file

    print("      启动扫码登录…")
    r = subprocess.run([sys.executable, os.path.join(target, "login.py"), "relogin"],
                       cwd=target)
    if r.returncode != 0 or not os.path.exists(cookie_file):
        print("扫码登录未成功，请把打印出的 cookie 手动粘到 cookie.txt 后重跑本脚本")
        sys.exit(1)
    print("      cookie 已保存")
    return cookie_file


def find_pythonw():
    """优先找 pythonw.exe（无窗口），找不到就退回 python.exe"""
    here = os.path.dirname(sys.executable)
    for name in ("pythonw.exe", "python.exe"):
        p = os.path.join(here, name)
        if os.path.exists(p):
            return p
    which = shutil.which("pythonw") or shutil.which("python")
    if which:
        return which
    print("[错误] 找不到 Python，请先安装 Python 3.8+ 并勾选 Add to PATH")
    sys.exit(1)


def run_cmd(cmd):
    """跑一条命令并拿回文本。中文 Windows 的 schtasks 输出是 GBK，别硬用 utf-8 解码。"""
    r = subprocess.run(cmd, shell=True, capture_output=True)
    raw = (r.stdout or b"") + (r.stderr or b"")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    return r.returncode, text


def create_task(target, py, task):
    run_py = os.path.join(target, "run.py")
    cmd = f'schtasks /Create /TN "{task}" /TR "\\"{py}\\" \\"{run_py}\\" auto" /SC MINUTE /MO 15 /F'
    code, out = run_cmd(cmd)
    if code != 0:
        print(f"[3/4] 创建计划任务失败：{out.strip()}")
        print("      如果你没有管理员权限，可以改用「任务计划程序」手动创建，")
        print(f"      程序填 {py}，参数填 {run_py} auto，触发器选每 15 分钟。")
        return False
    print(f"[3/4] 计划任务 {task} 已创建（每 15 分钟，静默执行）")
    return True


def verify(target, task):
    r = subprocess.run([sys.executable, os.path.join(target, "run.py"), "auto"],
                       cwd=target, capture_output=True)
    out = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", errors="replace").strip()
    print("[4/4] 首次试跑：")
    for line in out.splitlines():
        print("      " + line)
    if r.returncode != 0:
        print("      ⚠ 试跑失败，检查日志 logs/switch.log")
        return
    run_cmd(f'schtasks /Run /TN "{task}"')
    print("\n安装完成 ✓")
    print(f"  安装目录 : {target}")
    print(f"  计划任务 : {task}（每 15 分钟）")
    print(f"  运行日志 : {os.path.join(target, 'logs', 'switch.log')}")
    print("\n常用命令：")
    print(f'  schtasks /Query /TN "{task}" /FO LIST     查看状态')
    print(f'  schtasks /Run    /TN "{task}"             立刻跑一次')
    print(f'  schtasks /Delete /TN "{task}" /F          卸载')
    print("\n换头像图：替换 images/day.jpg 和 images/night.jpg，然后跑")
    print(f"  python {os.path.join(target, 'probe_face.py')} \"$(cat cookie.txt)\"")
    print("拿到新的 face URL，更新 run.py 里的 KNOWN_FACE。")


def main():
    cookie, target, task = parse_args()
    if not sys.platform.startswith("win"):
        print("本安装脚本只支持 Windows；其它系统请用 cron 定时跑 run.py auto：")
        print("  */15 * * * * cd /path/to/dir && /usr/bin/python3 run.py auto")
        sys.exit(1)
    if target is None:
        target = os.path.join(os.path.expanduser("~"), "bili-avatar-switcher")
    copy_pkg(target)
    get_cookie(cookie, target)
    py = find_pythonw()
    create_task(target, py, task)
    verify(target, task)


if __name__ == "__main__":
    main()
