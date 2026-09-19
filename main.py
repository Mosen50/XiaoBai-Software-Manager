# -*- coding: utf-8 -*-
"""
小白软件管家 —— 面向电脑小白的 Windows 软件一键安装工具

核心特性：
  1. 纯图形界面，全程不弹出任何黑色命令行窗口；
  2. 按分类展示常用软件，大字体、大按钮，可滚动；
  3. 每个软件按“有没有”动态显示最多三个操作按钮：
       · 一键安装（有 winget 包 ID 时，静默后台安装，含实时详细进度）
       · 直接下载（有直接下载地址时直接下载；有 winget 时用 winget 下载）
       · 官网    （有官网地址时，用默认浏览器打开官网）
  4. Windows Defender 提供“禁用”按钮，二次确认后以管理员权限禁用实时保护；
  5. 启动时自动检测 winget，不可用时顶部红色警告并提供“一键安装 winget”；
  6. 底部固定“一键安装所有必装软件”大按钮；
  7. 交互与动画：卡片悬停高亮、按钮悬停变色、平滑滚动、下载/安装进度条与实时详情；
  8. 系统工具：Geek Uninstaller 卸载工具、电脑驱动检测（检测驱动 / Windows 更新 / 驱动工具官网）。

依赖说明：
  本程序只使用 Python 标准库自带的 tkinter，【不需要安装任何第三方库】。

运行：pythonw main.py（推荐，无控制台窗口），或 python main.py。
"""

import base64
import ctypes
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from tempfile import gettempdir

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk


# ==================== 全局基础设置 ====================
APP_NAME = "小白软件管家"
APP_VERSION = "1.0.0"

# 适配高分屏，避免界面发虚
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# 隐藏控制台窗口所需的 Windows 常量
CREATE_NO_WINDOW = 0x08000000
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0

# 单个软件“一键安装”的超时时间（秒）。超过该时间未完成会强制结束并提示“超时”。
INSTALL_TIMEOUT_SECONDS = 1800

# winget（App Installer）下载地址，仅用于代码内部下载，不会显示给用户
WINGET_BUNDLE_URL = (
    "https://github.com/microsoft/winget-cli/releases/latest/download/"
    "Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle"
)
WINGET_BUNDLE_URL_FALLBACK = "https://aka.ms/getwinget"

# ==================== 配色与字体 ====================
BG = "#f2f3f5"            # 窗口背景
CARD_BG = "#ffffff"       # 卡片背景
CARD_HOVER = "#f3f8ff"    # 卡片悬停背景
TEXT = "#1f2329"          # 主文字
MUTED = "#6b7280"         # 次要文字
BORDER = "#e3e5e8"        # 卡片边框

C_PRIMARY = "#2f7fd6"     # 一键安装按钮（蓝）
C_DOWNLOAD = "#d68a2f"    # 直接下载按钮（橙）
C_SUCCESS = "#2f9e6e"     # 官网按钮（绿）
C_DANGER = "#d64545"      # 禁用 / 一键必装按钮（红）
C_WARN = "#d68a2f"        # 警告（橙）

TAG_COLORS = {
    "必装": "#d64545",
    "推荐": "#2f9e6e",
    "按需": "#6b7a8f",
}

STATUS_COLORS = {
    "wait": "#8a9199",
    "ok": "#2f9e6e",
    "busy": "#2f7fd6",
    "warn": "#d68a2f",
    "err": "#d64545",
}

# 字体统一使用微软雅黑（Windows 自带），尺寸偏大方便新手
F_TITLE = ("Microsoft YaHei UI", 20, "bold")
F_SUBTITLE = ("Microsoft YaHei UI", 11)
F_SECTION = ("Microsoft YaHei UI", 15, "bold")
F_NAME = ("Microsoft YaHei UI", 15, "bold")
F_DESC = ("Microsoft YaHei UI", 11)
F_TAG = ("Microsoft YaHei UI", 10, "bold")
F_STATUS = ("Microsoft YaHei UI", 10)
F_DETAIL = ("Microsoft YaHei UI", 10)
F_BUTTON = ("Microsoft YaHei UI", 12, "bold")
F_BIG_BUTTON = ("Microsoft YaHei UI", 14, "bold")


def _darken(hex_color, factor=0.14):
    """把十六进制颜色变暗，用于按钮悬停效果。"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


# ==================== 底层工具函数 ====================
def _startupinfo_hidden():
    """构造一个“隐藏窗口”的 STARTUPINFO，确保子进程不弹黑框。"""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= STARTF_USESHOWWINDOW
    si.wShowWindow = SW_HIDE
    return si


def run_hidden(args, timeout=None):
    """以完全隐藏的方式运行命令并捕获输出，绝不弹出黑色控制台窗口。"""
    try:
        return subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            startupinfo=_startupinfo_hidden(),
            timeout=timeout,
        )
    except Exception:
        return None


def run_hidden_to_log(args, log_path, timeout=None):
    """以完全隐藏的方式运行命令，把输出写入日志文件（避免长任务卡管道缓冲）。"""
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as f:
            return subprocess.run(
                list(args),
                stdout=f,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
                startupinfo=_startupinfo_hidden(),
                timeout=timeout,
            )
    except Exception:
        return None


def run_powershell(script, timeout=None):
    """以隐藏方式运行一段 PowerShell 脚本。"""
    return run_hidden(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=timeout,
    )


def run_as_admin(script):
    """通过 ShellExecute 的 runas 动词，以管理员权限运行 PowerShell 脚本。

    会弹出 Windows 的 UAC 提权窗口（这是系统安全弹窗，不是命令行窗口）。
    返回 True 表示已成功发起提权请求（用户点击“是”后命令才会真正执行）。
    """
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "powershell.exe",
            "-NoProfile -ExecutionPolicy Bypass -EncodedCommand " + encoded,
            None,
            SW_HIDE,
        )
        return rc > 32  # ShellExecuteW 返回值大于 32 表示成功
    except Exception:
        return False


def get_winget_path():
    """优先从 PATH 查找 winget；找不到时检查 App Installer 的默认安装位置。"""
    p = shutil.which("winget")
    if p:
        return p
    local = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe")
    if os.path.exists(local):
        return local
    return None


def winget_is_available():
    """判断 winget 是否真正可用（能执行 --version 并返回版本号）。"""
    path = get_winget_path()
    if not path:
        return False
    r = run_hidden([path, "--version"], timeout=15)
    return bool(r and r.returncode == 0 and (r.stdout or "").strip())


def download_app_installer(dest_dir=None):
    """下载 App Installer（winget）安装包到临时目录，返回文件路径；失败返回 None。"""
    dest_dir = dest_dir or gettempdir()
    dest = os.path.join(dest_dir, "Microsoft.DesktopAppInstaller.msixbundle")
    for url in (WINGET_BUNDLE_URL, WINGET_BUNDLE_URL_FALLBACK):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            if os.path.getsize(dest) > 1024 * 1024:
                return dest
        except Exception:
            continue
    return None


def downloads_dir():
    """返回当前用户的下载文件夹。"""
    return os.path.join(os.path.expanduser("~"), "Downloads")


# ==================== 软件数据（方便后续增删改） ====================
# 每个条目字段说明：
#   name         软件名称
#   desc         一句话说明
#   tag          标签：必装 / 推荐 / 按需
#   category     所属分类（必须与 CATEGORIES 一致）
#   winget       winget 包 ID（没有就填 None）—— 用于“一键安装”与“直接下载”
#   url          官网地址（没有就填 None）—— 用于“官网”按钮，仅内部跳转不显示文字
#   download_url 直接下载地址（没有就填 None）—— 用于“直接下载”按钮
#                （部分“最新版直链”可能随时间变化，程序下载失败时会自动兜底转官网）
#   kind         可选特殊类型：defender 表示 Defender 禁用；driver 表示驱动检测
CATEGORIES = [
    "安全防护", "文件处理", "办公套件", "浏览器", "影音播放",
    "社交通讯", "效率工具", "系统工具", "游戏平台", "游戏加速器",
]

SOFTWARE = [
    # ---------- 安全防护 ----------
    {"name": "火绒安全", "desc": "轻量安静的国产杀毒软件，防捆绑、防弹窗",
     "tag": "推荐", "category": "安全防护", "winget": None,
     "url": "https://www.huorong.cn/",
     "download_url": "https://www.huorong.cn/downloadv5.html"},
    {"name": "Windows Defender", "desc": "Windows 自带杀毒防护，本页可一键临时禁用",
     "tag": "按需", "category": "安全防护", "winget": None,
     "url": None, "download_url": None, "kind": "defender"},

    # ---------- 文件处理 ----------
    {"name": "7-Zip", "desc": "免费开源的压缩解压工具，装机必备",
     "tag": "必装", "category": "文件处理", "winget": "7zip.7zip",
     "url": "https://www.7-zip.org/", "download_url": None},
    {"name": "Everything", "desc": "秒级搜索本地文件，比系统搜索快得多",
     "tag": "推荐", "category": "文件处理", "winget": "voidtools.Everything",
     "url": "https://www.voidtools.com/", "download_url": None},
    {"name": "Dism++", "desc": "Windows 系统清理与优化工具",
     "tag": "按需", "category": "文件处理", "winget": None,
     "url": "https://www.chuyu.me/",
     "download_url": "https://github.com/Chuyu-Team/Dism-Multi-language/releases/latest"},

    # ---------- 办公套件 ----------
    {"name": "WPS Office", "desc": "国产免费办公套件，兼容 Word/Excel/PPT",
     "tag": "推荐", "category": "办公套件", "winget": "Kingsoft.WPSOffice",
     "url": "https://www.wps.cn/", "download_url": None},
    {"name": "LibreOffice", "desc": "免费开源办公套件，文档处理全能",
     "tag": "按需", "category": "办公套件", "winget": "TheDocumentFoundation.LibreOffice",
     "url": "https://www.libreoffice.org/", "download_url": None},

    # ---------- 浏览器 ----------
    {"name": "Microsoft Edge", "desc": "微软官方浏览器，系统自带可更新",
     "tag": "推荐", "category": "浏览器", "winget": "Microsoft.Edge",
     "url": "https://www.microsoft.com/zh-cn/edge",
     "download_url": "https://go.microsoft.com/fwlink/?linkid=2093504"},
    {"name": "Google Chrome", "desc": "全球流行的浏览器，速度快、扩展多",
     "tag": "必装", "category": "浏览器", "winget": "Google.Chrome",
     "url": "https://www.google.com/chrome/",
     "download_url": "https://dl.google.com/chrome/install/latest/chrome_installer.exe"},

    # ---------- 影音播放 ----------
    {"name": "PotPlayer", "desc": "强大的本地视频播放器，格式通吃",
     "tag": "推荐", "category": "影音播放", "winget": "Daum.PotPlayer",
     "url": "https://potplayer.daum.net/", "download_url": None},

    # ---------- 社交通讯 ----------
    {"name": "微信", "desc": "国民级聊天软件，电脑办公必备",
     "tag": "必装", "category": "社交通讯", "winget": "Tencent.WeChat",
     "url": "https://weixin.qq.com/",
     "download_url": "https://dldir1.qq.com/weixin/Windows/WeChatSetup.exe"},
    {"name": "QQ", "desc": "经典聊天软件，聊天传文件两不误",
     "tag": "推荐", "category": "社交通讯", "winget": "Tencent.QQ",
     "url": "https://im.qq.com/", "download_url": None},

    # ---------- 效率工具 ----------
    {"name": "Snipaste", "desc": "贴图截图工具，效率神器",
     "tag": "推荐", "category": "效率工具", "winget": "Snipaste.Snipaste",
     "url": "https://www.snipaste.com/", "download_url": None},
    {"name": "QuickLook", "desc": "按空格键快速预览文件内容",
     "tag": "推荐", "category": "效率工具", "winget": "QL-Win.QuickLook",
     "url": "https://github.com/QL-Win/QuickLook", "download_url": None},

    # ---------- 系统工具 ----------
    {"name": "Geek Uninstaller", "desc": "小巧免费的卸载工具，强制卸载并清理残留",
     "tag": "推荐", "category": "系统工具", "winget": "GeekUninstaller.GeekUninstaller",
     "url": "https://geekuninstaller.com/",
     "download_url": "https://geekuninstaller.com/geek.zip"},
    {"name": "驱动检测", "desc": "检测电脑驱动是否缺失或异常，并提供更新方式",
     "tag": "推荐", "category": "系统工具", "winget": None,
     "url": "https://www.snappy-driver-installer.org/",
     "download_url": None, "kind": "driver"},

    # ---------- 游戏平台 ----------
    {"name": "Steam", "desc": "全球最大的 PC 游戏平台",
     "tag": "按需", "category": "游戏平台", "winget": "Valve.Steam",
     "url": "https://store.steampowered.com/",
     "download_url": "https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe"},
    {"name": "Epic Games", "desc": "每周免费送游戏的游戏平台",
     "tag": "按需", "category": "游戏平台", "winget": "EpicGames.EpicGamesLauncher",
     "url": "https://store.epicgames.com/",
     "download_url": "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi"},
    {"name": "WeGame", "desc": "腾讯游戏平台",
     "tag": "按需", "category": "游戏平台", "winget": None,
     "url": "https://www.wegame.com.cn/",
     "download_url": "https://www.wegame.com.cn/"},
    {"name": "暴雪战网", "desc": "暴雪游戏启动器",
     "tag": "按需", "category": "游戏平台", "winget": None,
     "url": "https://www.blizzard.com/zh-cn/",
     "download_url": "https://www.battle.net/download/getInstallerForGame?os=win&locale=zhCN&version=LIVE&gameProgram=BATTLENET_APP"},
    {"name": "EA App", "desc": "EA 游戏平台",
     "tag": "按需", "category": "游戏平台", "winget": "ElectronicArts.EADesktop",
     "url": "https://www.ea.com/zh-cn/ea-app",
     "download_url": "https://origin-a.akamaihd.net/EA-Desktop-Client-Download/installer-releases/EAappInstaller.exe"},
    {"name": "Ubisoft Connect", "desc": "育碧游戏平台",
     "tag": "按需", "category": "游戏平台", "winget": "Ubisoft.Connect",
     "url": "https://ubisoftconnect.com/",
     "download_url": "https://ubistatic3-a.akamaihd.net/orbit/launcher_installer/UbisoftConnectInstaller.exe"},

    # ---------- 游戏加速器 ----------
    {"name": "网易UU", "desc": "网易游戏加速器",
     "tag": "按需", "category": "游戏加速器", "winget": None,
     "url": "https://uu.163.com/",
     "download_url": "https://uu.163.com/download/"},
    {"name": "迅游", "desc": "迅游网游加速器",
     "tag": "按需", "category": "游戏加速器", "winget": None,
     "url": "https://www.xunyou.com/",
     "download_url": "https://www.xunyou.com/"},
    {"name": "奇游", "desc": "奇游联机宝加速器",
     "tag": "按需", "category": "游戏加速器", "winget": None,
     "url": "https://www.qiyou.cn/",
     "download_url": "https://www.qiyou.cn/download/"},
]


def item_kind(item):
    """判断某个软件条目的特殊类型。"""
    kind = item.get("kind")
    if kind in ("defender", "driver"):
        return kind
    return None


# ==================== 主界面 ====================
class App(tk.Tk):
    """小白软件管家主窗口。"""

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("960x780")
        self.minsize(860, 640)
        self.configure(bg=BG)

        # 运行状态
        self.winget_ok = False
        self.winget_path = None
        self._winget_lock = threading.Lock()  # winget 相关操作互斥（winget 不支持并发）
        self._scroll_anim_id = None           # 平滑滚动动画句柄

        # 记录每个条目的控件，key 为软件名称
        self.cards = {}
        # 依赖 winget 的按钮（一键安装 + winget 直接下载），供统一启停
        self.winget_buttons = []

        self._build_layout()

        # 启动后立即在后台检测 winget，不阻塞界面
        threading.Thread(target=self._detect_winget_async, daemon=True).start()

    # ---------- 通用控件构造 ----------
    def _mk_button(self, parent, text, bg, command, width=None, height=1,
                   font=F_BUTTON, fg="#ffffff"):
        """构造一个扁平化彩色大按钮，带悬停变色动画。"""
        hover = _darken(bg, 0.14)
        b = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg,
            disabledforeground="#c7ccd1", relief="flat", bd=0,
            highlightthickness=0, cursor="hand2", font=font,
            width=width, height=height, padx=10, pady=3)

        def on_enter(_e):
            if b.cget("state") == "normal":
                b.configure(bg=hover)

        def on_leave(_e):
            if b.cget("state") == "normal":
                b.configure(bg=bg)

        b.bind("<Enter>", on_enter)
        b.bind("<Leave>", on_leave)
        return b

    # ---------- 界面构建 ----------
    def _build_layout(self):
        # 顶部容器：标题 + winget 警告横幅
        self.top = tk.Frame(self, bg=BG)
        self.top.pack(side="top", fill="x")

        header = tk.Frame(self.top, bg=BG)
        header.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(header, text="小白软件管家", font=F_TITLE,
                 bg=BG, fg=TEXT, anchor="w").pack(anchor="w")
        tk.Label(header, text="一键安装 · 直接下载 · 官网，远离捆绑软件",
                 font=F_SUBTITLE, bg=BG, fg=MUTED, anchor="w").pack(anchor="w")

        # winget 警告横幅（默认隐藏，检测到不可用时再显示）
        self.banner = tk.Frame(self.top, bg="#5c1f1f")
        self.banner_inner = tk.Frame(self.banner, bg="#5c1f1f")
        self.banner_inner.pack(fill="x", padx=16, pady=10)
        self.banner_text = tk.Label(
            self.banner_inner,
            text="⚠ 未检测到 winget（Windows 包管理器），部分“一键安装”功能不可用。",
            font=F_DESC, bg="#5c1f1f", fg="#ffd7d7", justify="left",
            wraplength=620, anchor="w")
        self.banner_text.pack(side="left", expand=True, fill="x", padx=(0, 12))
        self.banner_button = self._mk_button(
            self.banner_inner, "一键安装 winget", C_PRIMARY,
            self._on_install_winget_clicked, width=14, height=2)
        self.banner_button.pack(side="right")

        # 底部固定栏：一键安装所有必装软件
        self.bottom = tk.Frame(self, bg=BG)
        self.bottom.pack(side="bottom", fill="x")
        bottom_inner = tk.Frame(self.bottom, bg=BG)
        bottom_inner.pack(fill="x", padx=20, pady=12)
        self.progress_label = tk.Label(bottom_inner, text="", font=F_STATUS,
                                       bg=BG, fg=MUTED, anchor="w")
        self.progress_label.pack(anchor="w")
        self.install_all_button = self._mk_button(
            bottom_inner, "一键安装所有必装软件", C_DANGER,
            self._on_install_all_clicked, height=3, font=F_BIG_BUTTON)
        self.install_all_button.pack(fill="x", pady=(6, 2))
        tk.Label(bottom_inner, text="仅安装标记为“必装”且支持 winget 的软件",
                 font=F_STATUS, bg=BG, fg=MUTED, anchor="w").pack(anchor="w")

        # 可滚动内容区
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(side="top", fill="both", expand=True)

        self.canvas = tk.Canvas(self.body, bg=BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.body, orient="vertical",
                                       command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg=BG)
        self._content_window = self.canvas.create_window(
            (0, 0), window=self.content, anchor="nw")

        self.content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 鼠标滚轮：全局绑定，鼠标停在任意卡片/按钮上都能滚动
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)

        self._build_cards()

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._content_window, width=event.width)

    # ---------- 平滑滚动 ----------
    def _on_mousewheel(self, event):
        direction = 0
        num = getattr(event, "num", None)
        if num == 4:
            direction = -1
        elif num == 5:
            direction = 1
        else:
            delta = getattr(event, "delta", 0)
            if delta > 0:
                direction = -1
            elif delta < 0:
                direction = 1
        if direction == 0:
            return

        top, bottom = self.canvas.yview()
        if direction < 0 and top <= 0:
            return
        if direction > 0 and bottom >= 1:
            return

        step = 0.05
        target = max(0.0, min(1.0 - (bottom - top), top + direction * step))
        self._animate_scroll(target)
        return "break"

    def _animate_scroll(self, target):
        """把画布平滑滚动到目标位置（ease-out），连续滚动自动合并动画。"""
        top, _ = self.canvas.yview()
        start = top
        if abs(target - start) < 0.001:
            return
        if self._scroll_anim_id is not None:
            try:
                self.after_cancel(self._scroll_anim_id)
            except Exception:
                pass
            self._scroll_anim_id = None

        steps = 8
        duration = 110

        def step(i):
            if i > steps:
                self._scroll_anim_id = None
                self.canvas.yview_moveto(target)
                return
            frac = i / steps
            eased = 1 - (1 - frac) ** 2
            self.canvas.yview_moveto(start + (target - start) * eased)
            self._scroll_anim_id = self.after(int(duration / steps),
                                              lambda: step(i + 1))

        step(1)

    # ---------- 卡片悬停特效 ----------
    def _bind_all_children(self, widget, seq, func):
        """给控件及其所有子孙控件追加绑定（不影响已有绑定）。"""
        widget.bind(seq, func, add="+")
        for child in widget.winfo_children():
            self._bind_all_children(child, seq, func)

    def _add_card_hover(self, card):
        """卡片悬停时边框高亮 + 底色轻微变蓝。"""
        def on_enter(_e):
            card.configure(highlightbackground=C_PRIMARY, highlightcolor=C_PRIMARY,
                           bg=CARD_HOVER)
            for w in card.winfo_children():
                try:
                    if isinstance(w, tk.Label) and w.cget("bg") == CARD_BG:
                        w.configure(bg=CARD_HOVER)
                except Exception:
                    pass

        def on_leave(_e):
            card.configure(highlightbackground=BORDER, highlightcolor=BORDER,
                           bg=CARD_BG)
            for w in card.winfo_children():
                try:
                    if isinstance(w, tk.Label) and w.cget("bg") == CARD_HOVER:
                        w.configure(bg=CARD_BG)
                except Exception:
                    pass

        self._bind_all_children(card, "<Enter>", on_enter)
        self._bind_all_children(card, "<Leave>", on_leave)

    # ---------- 卡片渲染 ----------
    def _build_cards(self):
        """按分类渲染所有软件卡片。"""
        for cat in CATEGORIES:
            items = [it for it in SOFTWARE if it["category"] == cat]
            if not items:
                continue

            tk.Label(self.content, text=cat, font=F_SECTION, bg=BG, fg=TEXT,
                     anchor="w").pack(fill="x", padx=22, pady=(18, 6))

            for item in items:
                self._build_card(item)

    def _build_card(self, item):
        """创建单个软件卡片，按“有没有”动态显示按钮。"""
        card = tk.Frame(self.content, bg=CARD_BG,
                        highlightbackground=BORDER, highlightcolor=BORDER,
                        highlightthickness=1)
        card.pack(fill="x", padx=20, pady=6)
        card.grid_columnconfigure(0, weight=1)

        # 左列：名称 + 说明 + 标签
        tk.Label(card, text=item["name"], font=F_NAME, bg=CARD_BG,
                 fg=TEXT, anchor="w", justify="left").grid(
                     row=0, column=0, sticky="w", padx=(16, 8), pady=(12, 0))
        tk.Label(card, text=item["desc"], font=F_DESC, bg=CARD_BG,
                 fg=MUTED, anchor="w", justify="left").grid(
                     row=1, column=0, sticky="w", padx=(16, 8), pady=(2, 0))
        tag_color = TAG_COLORS.get(item["tag"], "#6b7a8f")
        tk.Label(card, text=item["tag"], font=F_TAG, bg=tag_color,
                 fg="#ffffff", padx=8, pady=1).grid(
                     row=2, column=0, sticky="w", padx=(16, 8), pady=(6, 12))

        # 右列：按需动态生成按钮（一键安装 / 直接下载 / 官网 / 禁用）
        buttons = {}
        row = 0

        kind = item_kind(item)
        if kind == "defender":
            b = self._mk_button(card, "禁用", C_DANGER,
                                lambda it=item: self._confirm_disable_defender(it),
                                width=11)
            b.grid(row=row, column=1, sticky="e", padx=(8, 16), pady=(10, 2))
            buttons["defender"] = b
            row += 1
        elif kind == "driver":
            b = self._mk_button(card, "检测驱动", C_PRIMARY,
                                lambda it=item: self._detect_drivers(it),
                                width=11)
            b.grid(row=row, column=1, sticky="e", padx=(8, 16), pady=(10, 2))
            buttons["detect"] = b
            row += 1

            b = self._mk_button(card, "Windows 更新", C_DOWNLOAD,
                                lambda it=item: self._open_windows_update(it),
                                width=11)
            b.grid(row=row, column=1, sticky="e", padx=(8, 16), pady=(2, 2))
            buttons["update"] = b
            row += 1

            if item.get("url"):
                b = self._mk_button(card, "驱动工具官网", C_SUCCESS,
                                    lambda it=item: self._open_website(it),
                                    width=11)
                b.grid(row=row, column=1, sticky="e", padx=(8, 16), pady=(2, 2))
                buttons["website"] = b
                row += 1
        else:
            if item.get("winget"):
                b = self._mk_button(card, "一键安装", C_PRIMARY,
                                    lambda it=item: self._on_install(it),
                                    width=11)
                b.grid(row=row, column=1, sticky="e",
                       padx=(8, 16), pady=(10 if row == 0 else 2, 2))
                buttons["winget"] = b
                self.winget_buttons.append(b)
                row += 1

            if item.get("winget") or item.get("download_url"):
                b = self._mk_button(card, "直接下载", C_DOWNLOAD,
                                    lambda it=item: self._on_download(it),
                                    width=11)
                b.grid(row=row, column=1, sticky="e",
                       padx=(8, 16), pady=(10 if row == 0 else 2, 2))
                buttons["download"] = b
                if not item.get("download_url"):
                    self.winget_buttons.append(b)
                row += 1

            if item.get("url"):
                b = self._mk_button(card, "官网", C_SUCCESS,
                                    lambda it=item: self._open_website(it),
                                    width=11)
                b.grid(row=row, column=1, sticky="e",
                       padx=(8, 16), pady=(10 if row == 0 else 2, 2))
                buttons["website"] = b
                row += 1

        # 底部通栏：状态文字 + 详情 + 进度条
        status_row = max(row, 3)
        status = tk.Label(card, text="等待操作", font=F_STATUS, bg=CARD_BG,
                          fg=STATUS_COLORS["wait"], anchor="w")
        status.grid(row=status_row, column=0, columnspan=2, sticky="w",
                    padx=16, pady=(6, 2))

        detail = tk.Label(card, text="", font=F_DETAIL, bg=CARD_BG,
                          fg=C_PRIMARY, anchor="w", justify="left",
                          wraplength=620)
        detail.grid(row=status_row + 1, column=0, columnspan=2, sticky="w",
                    padx=16, pady=(0, 2))
        detail.grid_remove()

        progress = ttk.Progressbar(card, mode="indeterminate",
                                   maximum=100, value=0)
        progress.grid(row=status_row + 2, column=0, columnspan=2, sticky="ew",
                      padx=16, pady=(0, 12))
        progress.grid_remove()

        self.cards[item["name"]] = {
            "buttons": buttons, "status": status, "detail": detail,
            "progress": progress, "item": item}

        self._add_card_hover(card)

    # ---------- 线程安全的 UI 更新 ----------
    def set_status(self, item_name, text, color=None):
        """更新某个软件条目的状态文字（可从任意线程调用）。"""
        card = self.cards.get(item_name)
        if not card:
            return
        color = color or STATUS_COLORS["wait"]

        def _apply():
            card["status"].configure(text=text, fg=color)
        self.after(0, _apply)

    def set_progress(self, text):
        """更新底部进度提示文字。"""
        def _apply():
            self.progress_label.configure(text=text)
        self.after(0, _apply)

    # ---------- 卡片进度条 / 详情 ----------
    def _card_show_progress(self, name, mode="indeterminate"):
        """显示某个卡片的进度条与详情行（可从任意线程调用）。"""
        card = self.cards.get(name)
        if not card:
            return

        def _apply():
            p = card["progress"]
            d = card["detail"]
            p.configure(mode=mode, maximum=100, value=0)
            if mode == "indeterminate":
                p.start(14)
            d.configure(text="", fg=C_PRIMARY)
            p.grid()
            d.grid()
        self.after(0, _apply)

    def _card_update_progress(self, name, value=None, detail=None):
        """更新卡片进度条数值与详情文字（可从任意线程调用）。"""
        card = self.cards.get(name)
        if not card:
            return

        def _apply():
            p = card["progress"]
            if value is not None:
                if str(p.cget("mode")) != "determinate":
                    try:
                        p.stop()
                    except Exception:
                        pass
                    p.configure(mode="determinate", maximum=100)
                p.configure(value=value)
            if detail is not None:
                card["detail"].configure(text=str(detail)[-120:])
        self.after(0, _apply)

    def _card_hide_progress(self, name):
        """隐藏卡片进度条与详情行（可从任意线程调用）。"""
        card = self.cards.get(name)
        if not card:
            return

        def _apply():
            p = card["progress"]
            d = card["detail"]
            try:
                p.stop()
            except Exception:
                pass
            p.grid_remove()
            d.grid_remove()
        self.after(0, _apply)

    def _card_show_final_detail(self, name, text):
        """安装失败时，停止进度条并保留最后一条详情用于排查。"""
        card = self.cards.get(name)
        if not card:
            return

        def _apply():
            p = card["progress"]
            d = card["detail"]
            try:
                p.stop()
            except Exception:
                pass
            p.grid_remove()
            d.configure(text=str(text)[-120:], fg=STATUS_COLORS["err"])
            d.grid()
        self.after(0, _apply)

    # ---------- winget 检测与安装 ----------
    def _detect_winget_async(self):
        ok = winget_is_available()
        path = get_winget_path()
        self.after(0, lambda: self._on_winget_checked(ok, path))

    def _on_winget_checked(self, ok, path):
        self.winget_ok = ok
        self.winget_path = path
        if ok:
            self.banner.pack_forget()
            self._set_winget_buttons_enabled(True)
            self.install_all_button.configure(state="normal")
            threading.Thread(target=self._refresh_installed, daemon=True).start()
        else:
            self.banner_text.configure(
                text="⚠ 未检测到 winget（Windows 包管理器），部分“一键安装”功能不可用。")
            self.banner_button.configure(state="normal", text="一键安装 winget")
            self.banner.pack(fill="x", padx=20, pady=(0, 8))
            self._set_winget_buttons_enabled(False)
            self.install_all_button.configure(state="disabled")

    def _set_winget_buttons_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for b in self.winget_buttons:
            try:
                b.configure(state=state)
            except Exception:
                pass

    def _on_install_winget_clicked(self):
        self.banner_button.configure(state="disabled", text="正在安装 winget…")
        threading.Thread(target=self._install_winget_async, daemon=True).start()

    def _install_winget_async(self):
        self._banner_text("正在下载 winget（App Installer），请稍候…")
        bundle = download_app_installer()
        if not bundle:
            self.after(0, self._winget_install_failed)
            return

        self._banner_text("正在安装 winget，请稍候…")
        run_powershell(
            f"$ErrorActionPreference='Stop'; Add-AppxPackage -Path '{bundle}'",
            timeout=300)
        ok = winget_is_available()

        if not ok:
            run_as_admin(
                f"$ErrorActionPreference='Stop'; Add-AppxPackage -Path '{bundle}'")
            time.sleep(5)
            ok = winget_is_available()

        if ok:
            self.after(0, self._winget_install_done)
        else:
            self.after(0, self._winget_install_failed)

    def _banner_text(self, text):
        def _apply():
            self.banner_text.configure(text=text)
        self.after(0, _apply)

    def _winget_install_done(self):
        self._on_winget_checked(True, get_winget_path())
        messagebox.showinfo("安装成功", "winget 已安装成功，现在可以使用“一键安装”功能啦！")

    def _winget_install_failed(self):
        self.banner_text.configure(
            text="⚠ winget 安装失败。请尝试联网后重试，或在“设置 → Windows 更新”中检查更新后再次尝试。")
        self.banner_button.configure(state="normal", text="重试安装 winget")
        messagebox.showwarning(
            "安装失败",
            "winget 安装未成功。\n\n"
            "建议先联网，然后点击横幅上的“重试安装 winget”。\n"
            "若仍失败，请更新系统到较新的 Windows 版本后再试。")

    # ---------- 已安装状态刷新 ----------
    def _refresh_installed(self):
        path = get_winget_path()
        if not path:
            return
        r = run_hidden([path, "list", "--accept-source-agreements"], timeout=120)
        if not r:
            return
        out = (r.stdout or "").lower()
        for item in SOFTWARE:
            wid = item.get("winget")
            if wid and wid.lower() in out:
                self.set_status(item["name"], "已安装 ✓", STATUS_COLORS["ok"])

    # ---------- 一键安装 ----------
    def _on_install(self, item):
        if not self.winget_ok:
            messagebox.showwarning("winget 不可用",
                                   "请先点击顶部横幅上的“一键安装 winget”。")
            return
        threading.Thread(target=self._install_item_async, args=(item,),
                         daemon=True).start()

    def _install_item_async(self, item):
        if not self._winget_lock.acquire(blocking=False):
            self.set_status(item["name"], "已有任务进行中…", STATUS_COLORS["warn"])
            return
        try:
            ok = self._install_one(item)
            if not ok:
                self.after(0, lambda: messagebox.showwarning(
                    "安装未成功", f"“{item['name']}”安装未成功。\n\n"
                    "可能原因：网络问题、软件源暂无该版本，或该软件需要手动确认。\n"
                    "可以稍后重试，或改用“直接下载 / 官网”。"))
        finally:
            self._winget_lock.release()

    def _install_one(self, item):
        """执行一次 winget 静默安装：实时进度 + 超时保护，返回是否成功。"""
        wid = item.get("winget")
        path = get_winget_path()
        if not path or not wid:
            self.set_status(item["name"], "winget 不可用", STATUS_COLORS["err"])
            return False

        self.set_status(item["name"], "准备安装…", STATUS_COLORS["warn"])
        self._card_show_progress(item["name"], "indeterminate")
        self._card_update_progress(item["name"], detail="正在启动 winget…")

        cmd = [path, "install", "--id", wid, "--silent",
               "--accept-package-agreements", "--accept-source-agreements",
               "--disable-interactivity"]

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW, startupinfo=_startupinfo_hidden())
        except Exception:
            self._card_hide_progress(item["name"])
            self.set_status(item["name"], "安装失败 ✗", STATUS_COLORS["err"])
            return False

        log = os.path.join(gettempdir(),
                           f"xiaobai_winget_{wid.replace('.', '_')}.log")

        # 读取线程与主线程共享的进度状态
        state = {"pct": None, "detail": "", "last_t": 0.0}

        def parse(text):
            for seg in re.split(r"[\r\n]+", text):
                seg = seg.strip()
                if not seg:
                    continue
                m = re.search(r"(\d{1,3})\s*%", seg)
                if m:
                    state["pct"] = int(m.group(1))
                # 去掉进度条方块/制表符，只留可读文字
                readable = re.sub(r"[\u2580-\u259f\u2500-\u257f]+", " ", seg)
                readable = re.sub(r"\s+", " ", readable).strip()
                if readable:
                    state["detail"] = readable

        def emit(force=False):
            now = time.time()
            if force or now - state["last_t"] >= 0.12:  # 节流，避免刷爆 UI 队列
                state["last_t"] = now
                self._card_update_progress(item["name"], value=state["pct"],
                                           detail=state["detail"])

        def reader():
            try:
                with open(log, "wb") as lf:
                    while True:
                        chunk = proc.stdout.read(4096)
                        if not chunk:
                            break
                        lf.write(chunk)
                        parse(chunk.decode("utf-8", "replace"))
                        emit()
            except Exception:
                pass

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        # 带超时等待：超过设定时间就强制结束，避免无限挂起
        timed_out = False
        try:
            rc = proc.wait(timeout=INSTALL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                proc.kill()
            except Exception:
                pass
            rc = proc.wait()

        t.join(timeout=5)  # 等读取线程收尾

        if timed_out:
            self._card_show_final_detail(
                item["name"],
                f"安装超时（超过 {INSTALL_TIMEOUT_SECONDS // 60} 分钟），已强制结束")
            self.set_status(item["name"], "安装超时 ✗", STATUS_COLORS["err"])
            return False

        ok = (rc == 0)
        if ok:
            self._card_hide_progress(item["name"])
            self.set_status(item["name"], "安装完成 ✓", STATUS_COLORS["ok"])
        else:
            self._card_show_final_detail(
                item["name"], state["detail"] or "winget 未返回有效信息")
            self.set_status(item["name"], "安装失败 ✗", STATUS_COLORS["err"])
        return ok

    # ---------- 直接下载 ----------
    def _on_download(self, item):
        if item.get("download_url"):
            threading.Thread(target=self._http_download_async, args=(item,),
                             daemon=True).start()
        elif item.get("winget"):
            if not self.winget_ok:
                messagebox.showwarning("winget 不可用",
                                       "“直接下载”需要 winget，请先安装。")
                return
            threading.Thread(target=self._winget_download_async, args=(item,),
                             daemon=True).start()

    def _http_download_async(self, item):
        """用直接下载地址下载安装包到“下载”文件夹，带进度条与百分比。"""
        url = item.get("download_url")
        self.set_status(item["name"], "连接中…", STATUS_COLORS["warn"])
        self._card_show_progress(item["name"], "determinate")
        dest_dir = downloads_dir()
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception:
            dest_dir = gettempdir()

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=120)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            fname = self._guess_filename(item, url, resp)
            dest = os.path.join(dest_dir, fname)

            total = 0
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except Exception:
                total = 0

            done = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = int(done * 100 / total)
                        self._card_update_progress(
                            item["name"], value=pct,
                            detail=f"正在下载 {fname}：{pct}%")
                    else:
                        self._card_update_progress(
                            item["name"],
                            detail=f"正在下载 {fname}：{done // 1024} KB")

            # 若返回的是网页而非安装包，则回退为打开浏览器
            if "text/html" in ctype:
                try:
                    os.remove(dest)
                except Exception:
                    pass
                self._card_hide_progress(item["name"])
                self._open_website(item)
                return

            self._card_hide_progress(item["name"])
            self.set_status(item["name"], "已下载 ✓", STATUS_COLORS["ok"])
            self._offer_open(item, dest)
        except Exception:
            self._card_hide_progress(item["name"])
            self.set_status(item["name"], "下载失败 ✗", STATUS_COLORS["err"])
            self.after(0, lambda: messagebox.showwarning(
                "下载失败",
                f"“{item['name']}”直接下载失败，可改用“官网”按钮下载。"))

    def _guess_filename(self, item, url, resp):
        """根据响应头/URL 推断一个合理的文件名。"""
        cd = resp.headers.get("Content-Disposition") or ""
        m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", cd, re.I)
        if m:
            name = m.group(1).strip().strip('"')
            if name:
                return os.path.basename(urllib.parse.unquote(name))
        base = os.path.basename(urllib.parse.urlparse(url).path)
        if base and "." in base:
            return base
        return f"{item['name']}安装包.exe"

    def _winget_download_async(self, item):
        """用 winget 下载安装包（适用于没有稳定直链的 winget 软件）。"""
        wid = item.get("winget")
        if not self._winget_lock.acquire(blocking=False):
            self.set_status(item["name"], "已有任务进行中…", STATUS_COLORS["warn"])
            return
        try:
            self.set_status(item["name"], "下载中…", STATUS_COLORS["warn"])
            self._card_show_progress(item["name"], "indeterminate")
            self._card_update_progress(item["name"],
                                       detail="正在用 winget 下载安装包…")
            dest = os.path.join(downloads_dir(), "小白软件管家", wid)
            try:
                os.makedirs(dest, exist_ok=True)
            except Exception:
                dest = os.path.join(gettempdir(), "xiaobai", wid)
                os.makedirs(dest, exist_ok=True)

            path = get_winget_path()
            log = os.path.join(gettempdir(),
                               f"xiaobai_wingetdl_{wid.replace('.', '_')}.log")
            cmd = [path, "download", "--id", wid, "--download-directory", dest,
                   "--accept-package-agreements", "--accept-source-agreements"]
            r = run_hidden_to_log(cmd, log, timeout=1800)

            newest = self._newest_file(dest)
            if r and r.returncode == 0 and newest:
                self._card_hide_progress(item["name"])
                self.set_status(item["name"], "已下载 ✓", STATUS_COLORS["ok"])
                self._offer_open(item, newest)
            else:
                self._card_hide_progress(item["name"])
                self.set_status(item["name"], "下载失败，转官网", STATUS_COLORS["err"])
                self._open_website(item)
        finally:
            self._winget_lock.release()

    def _newest_file(self, directory):
        """返回目录下最新的文件；没有则返回 None。"""
        newest = None
        newest_mtime = 0
        for root, _dirs, files in os.walk(directory):
            for name in files:
                fp = os.path.join(root, name)
                try:
                    mt = os.path.getmtime(fp)
                except OSError:
                    continue
                if mt > newest_mtime:
                    newest_mtime = mt
                    newest = fp
        return newest

    def _offer_open(self, item, filepath):
        """下载完成后询问是否立即打开安装程序。"""
        def _ask():
            if messagebox.askyesno(
                    "下载完成",
                    f"“{item['name']}”已下载到：\n{filepath}\n\n"
                    "是否立即打开安装程序？\n（选“否”则打开所在文件夹）"):
                try:
                    os.startfile(filepath)
                except Exception:
                    self._open_folder(filepath)
            else:
                self._open_folder(filepath)
        self.after(0, _ask)

    def _open_folder(self, filepath):
        try:
            subprocess.run(
                ["explorer.exe", "/select,", os.path.normpath(filepath)],
                creationflags=CREATE_NO_WINDOW,
                startupinfo=_startupinfo_hidden())
        except Exception:
            pass

    # ---------- 官网 ----------
    def _open_website(self, item):
        """用默认浏览器打开官网（网址仅内部使用，不显示文字）。"""
        url = item.get("url")
        if not url:
            return
        self.set_status(item["name"], "正在打开官网…", STATUS_COLORS["busy"])
        try:
            webbrowser.open(url)
            self.set_status(item["name"], "已打开官网 ✓", STATUS_COLORS["ok"])
        except Exception:
            self.set_status(item["name"], "打开失败 ✗", STATUS_COLORS["err"])

    # ---------- 驱动检测 ----------
    def _detect_drivers(self, item):
        """触发一次驱动检测（后台线程）。"""
        self.set_status(item["name"], "正在检测驱动…", STATUS_COLORS["busy"])
        threading.Thread(target=self._detect_drivers_async, args=(item,),
                         daemon=True).start()

    def _detect_drivers_async(self, item):
        """扫描缺失/异常的驱动（ConfigManagerErrorCode != 0），并汇报结果。"""
        script = (
            "Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | "
            "Where-Object { $_.ConfigManagerErrorCode -ne $null -and "
            "$_.ConfigManagerErrorCode -ne 0 } | "
            "ForEach-Object { '{0}（代码 {1}）' -f $_.Name, $_.ConfigManagerErrorCode }"
        )
        r = run_powershell(script, timeout=90)
        problems = []
        if r and r.returncode == 0 and r.stdout:
            problems = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]

        if not problems:
            self.set_status(item["name"], "驱动正常 ✓", STATUS_COLORS["ok"])
            self.after(0, lambda: messagebox.showinfo(
                "驱动检测", "未发现缺失或异常的驱动，电脑驱动状态良好。"))
            return

        sample = "\n".join("· " + p for p in problems[:10])
        more = "" if len(problems) <= 10 else f"\n… 等共 {len(problems)} 个设备"
        self.set_status(item["name"], f"发现 {len(problems)} 个异常驱动",
                        STATUS_COLORS["err"])
        self.after(0, lambda: messagebox.showwarning(
            "驱动检测",
            f"发现 {len(problems)} 个设备驱动异常：\n\n{sample}{more}\n\n"
            "建议先点“Windows 更新”自动安装驱动；\n"
            "若仍缺失，可用“驱动工具官网”里的工具补充。"))

    def _open_windows_update(self, item):
        """打开系统自带的 Windows 更新（最安全、无捆绑的驱动更新方式）。"""
        self.set_status(item["name"], "正在打开 Windows 更新…",
                        STATUS_COLORS["busy"])
        try:
            os.startfile("ms-settings:windowsupdate")
            self.set_status(item["name"], "已打开 Windows 更新 ✓",
                            STATUS_COLORS["ok"])
        except Exception:
            try:
                subprocess.run(
                    ["cmd", "/c", "start", "", "ms-settings:windowsupdate"],
                    creationflags=CREATE_NO_WINDOW,
                    startupinfo=_startupinfo_hidden())
                self.set_status(item["name"], "已打开 Windows 更新 ✓",
                                STATUS_COLORS["ok"])
            except Exception:
                self.set_status(item["name"], "打开失败 ✗", STATUS_COLORS["err"])

    # ---------- 一键安装所有必装软件 ----------
    def _on_install_all_clicked(self):
        if not self.winget_ok:
            messagebox.showwarning("winget 不可用", "请先安装 winget。")
            return
        items = [it for it in SOFTWARE if it["tag"] == "必装" and it.get("winget")]
        names = "、".join(it["name"] for it in items)
        if not messagebox.askokcancel(
                "开始安装",
                f"将依次静默安装以下必装软件：\n\n{names}\n\n"
                "安装过程中请保持网络畅通，不要关闭本窗口。是否开始？"):
            return
        threading.Thread(target=self._install_all_async, args=(items,),
                         daemon=True).start()

    def _install_all_async(self, items):
        if not self._winget_lock.acquire(blocking=False):
            self.after(0, lambda: messagebox.showwarning(
                "正在安装", "当前已有安装任务在进行，请稍候。"))
            return
        try:
            self._set_big_button_enabled(False)
            total = len(items)
            ok_count = 0
            for i, item in enumerate(items, 1):
                self.set_progress(f"正在安装必装软件：{i}/{total}  {item['name']} …")
                if self._install_one(item):
                    ok_count += 1
            self.set_progress("")
            self.after(0, lambda: messagebox.showinfo(
                "全部完成", f"必装软件安装完成：成功 {ok_count} / {total}。\n"
                "失败的项目可单独重试，或改用“直接下载 / 官网”。"))
        finally:
            self._set_big_button_enabled(True)
            self._winget_lock.release()

    def _set_big_button_enabled(self, enabled):
        def _apply():
            self.install_all_button.configure(
                state="normal" if enabled else "disabled")
        self.after(0, _apply)

    # ---------- Windows Defender 禁用 ----------
    def _confirm_disable_defender(self, item):
        """二次确认后，以管理员权限禁用 Windows Defender 实时保护。"""
        if not messagebox.askokcancel(
                "风险提示",
                "即将以管理员身份临时禁用 Windows Defender 实时保护。\n\n"
                "⚠ 风险提示：\n"
                "· 禁用后电脑将失去实时杀毒防护，可能感染病毒；\n"
                "· 建议仅在确有必要时临时禁用，用完请尽快恢复；\n"
                "· 若系统开启了“篡改防护”，此操作可能无法生效。\n\n"
                "是否继续？"):
            self.set_status(item["name"], "已取消", STATUS_COLORS["wait"])
            return

        if not messagebox.askyesno(
                "再次确认",
                "确定要禁用实时保护吗？此操作会降低系统安全性，请谨慎选择。"):
            self.set_status(item["name"], "已取消", STATUS_COLORS["wait"])
            return

        success = run_as_admin("Set-MpPreference -DisableRealtimeMonitoring $true")
        if success:
            self.set_status(item["name"], "已请求禁用，请在弹窗点“是”",
                            STATUS_COLORS["warn"])
            threading.Thread(target=self._check_defender_state, args=(item,),
                             daemon=True).start()
        else:
            self.set_status(item["name"], "提权失败或已取消", STATUS_COLORS["err"])

    def _check_defender_state(self, item):
        time.sleep(8)
        r = run_powershell("(Get-MpPreference).DisableRealtimeMonitoring", timeout=30)
        disabled = bool(r and r.returncode == 0 and
                        (r.stdout or "").strip().lower() == "true")
        if disabled:
            self.set_status(item["name"], "已禁用实时保护", STATUS_COLORS["ok"])
        else:
            self.set_status(item["name"], "未生效（可能被篡改防护拦截）",
                            STATUS_COLORS["err"])


# ==================== 程序入口 ====================
def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
