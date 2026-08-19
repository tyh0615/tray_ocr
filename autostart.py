"""开机自启动：通过 HKCU\\...\\Run 注册表实现（无需管理员权限）。

打包成 exe 后用 sys.executable；源码运行时用 "python -m tray_ocr.main"。
"""
import os
import sys

RUN_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"
APP_NAME = "TrayOCR"


def _exe_path() -> str:
    """返回用于启动本程序的可执行命令行。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后的 exe 路径（含空格时加引号）
        return f'"{sys.executable}"'
    # 源码运行：pythonw 优先（无控制台黑窗）
    py = os.path.join(sys.base_prefix, "pythonw.exe") if hasattr(sys, "base_prefix") else sys.executable
    if not os.path.exists(py):
        py = sys.executable
    import tray_ocr
    pkg_dir = os.path.dirname(os.path.abspath(tray_ocr.__file__))
    return f'"{py}" -m tray_ocr.main'


def _open_run_key():
    import winreg
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)


def is_autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def enable_autostart() -> bool:
    try:
        with _open_run_key() as k:
            import winreg
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _exe_path())
        return True
    except OSError:
        return False


def disable_autostart() -> bool:
    try:
        with _open_run_key() as k:
            import winreg
            winreg.DeleteValue(k, APP_NAME)
        return True
    except FileNotFoundError:
        return True  # 本来就没有，视为成功
    except OSError:
        return False
