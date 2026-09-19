# 小白软件管家

为电脑小白打造的**一体化软件安装平台**——一个窗口搞定「装软件、驱动检测、卸载」，全程无命令行黑窗口，远离捆绑软件。

![小白软件管家 主界面](screenshot.png)

## 下载

到 [Releases](https://github.com/Mosen50/XiaoBai-Software-Manager/releases) 下载 `小白软件管家.exe`，双击即用（无需安装 Python）。

## 功能

- **一键装软件**：10 大类 25 款常用软件，一键安装 / 直接下载 / 官网
- **驱动检测**：扫描缺失/异常驱动，一键修复
- **卸载工具**：Geek Uninstaller，强制卸载、清理残留
- **一键必装**：底部按钮一次装齐所有必装软件
- **零捆绑**：只走 winget / 官方直链 / 官网，无广告、无捆绑

## 特点

- 纯图形界面，大字体、大按钮，全程无黑窗口
- 零第三方依赖（仅用 Python 自带 tkinter）
- winget 静默安装，实时进度 + 超时保护
- 卡片/按钮悬停特效、平滑滚动

## 使用

1. 双击运行
2. 找软件 → 点「一键安装 / 直接下载 / 官网」
3. 装齐常用软件 → 点底部「一键安装所有必装软件」

## 从源码运行 / 打包

```bash
# 运行
pythonw main.py

# 打包成 exe
pip install pyinstaller
pyinstaller --onefile --windowed --name "小白软件管家" main.py
```

## 开源协议

[MIT License](LICENSE)
