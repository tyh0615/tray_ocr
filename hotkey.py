import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional, Tuple


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

# 修饰键名 -> RegisterHotKey 的 MOD 位
MODIFIER_BITS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
    "meta": MOD_WIN,
}

# 非字母数字键名 -> VK 码
SPECIAL_KEYS = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "backspace": 0x08, "esc": 0x1B, "escape": 0x1B,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "printscr": 0x2C, "snapshot": 0x2C,
    "capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91,
}
for _i in range(1, 13):  # F1-F12
    SPECIAL_KEYS[f"f{_i}"] = 0x70 + _i - 1

# 供显示用的规范化修饰键顺序
_MOD_ORDER = ["ctrl", "alt", "shift", "win"]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


def parse_hotkey(spec: str) -> Tuple[int, int]:
    """把 "ctrl+alt+o" 解析成 (modifiers, vk)。非法时抛 ValueError。

    规则：必须恰好一个普通键（放最后），0-3 个修饰键。
    """
    if not spec or not spec.strip():
        raise ValueError("快捷键不能为空")
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("快捷键不能为空")

    mods = 0
    key_vk: Optional[int] = None
    seen_mods = set()
    for p in parts:
        if p in MODIFIER_BITS:
            if p in seen_mods:
                raise ValueError(f"修饰键重复：{p}")
            seen_mods.add(p)
            mods |= MODIFIER_BITS[p]
        else:
            if key_vk is not None:
                raise ValueError("只能包含一个非修饰键")
            if len(p) == 1 and p.isalnum():
                # 单字符：字母或数字
                key_vk = ord(p.upper())
            elif p in SPECIAL_KEYS:
                key_vk = SPECIAL_KEYS[p]
            else:
                raise ValueError(f"无法识别的按键：{p}")

    if key_vk is None:
        raise ValueError("缺少主键（如 ctrl+alt+o 中的 o）")
    return mods, key_vk


def normalize_hotkey(spec: str) -> str:
    """规范化显示：ctrl+alt+o -> Ctrl+Alt+O"""
    mods, vk = parse_hotkey(spec)
    names = []
    for m in _MOD_ORDER:
        if mods & MODIFIER_BITS[m]:
            names.append(m.capitalize())
    # 主键名
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        names.append(chr(vk))
    else:
        rev = {v: k for k, v in SPECIAL_KEYS.items()}
        names.append(rev.get(vk, f"VK{vk:02X}").capitalize())
    return "+".join(names)


def hotkey_available(spec: str) -> Tuple[bool, str]:
    """探测组合键当前是否可注册（冲突检测）。

    返回 (是否可用, 失败原因)。探测方式：临时 RegisterHotKey 再立刻注销。
    注意：本应用自己已注册的键会被探测为"占用"，调用方需先排除自身当前热键。
    """
    try:
        mods, vk = parse_hotkey(spec)
    except ValueError as e:
        return False, str(e)
    # 纯单键（无修饰）且是字母/数字：容易吞掉正常打字，直接拒绝
    if mods == 0 and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
        return False, "请至少加一个修饰键（Ctrl/Alt/Shift/Win），避免影响正常打字"
    ok = bool(user32.RegisterHotKey(None, 0xBEEF, mods | MOD_NOREPEAT, vk))
    if ok:
        user32.UnregisterHotKey(None, 0xBEEF)
        return True, ""
    err = ctypes.get_last_error()
    if err == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
        return False, "该快捷键已被其它程序占用"
    return False, f"注册失败（系统错误码 {err}）"


class HotkeyListener:
    """全局热键监听：RegisterHotKey 优先，失败时退回低级键盘钩子。

    支持 update_hotkey(spec) 动态更换热键（设置界面保存后调用，即时生效）。
    """

    def __init__(self, on_hotkey: Callable[[], None], hotkey: str = "shift+c"):
        self._on_hotkey = on_hotkey
        self._spec = hotkey
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._thread_id: Optional[int] = None
        self._hotkey_id = 1
        self._ready_event = threading.Event()
        self._register_ok: Optional[bool] = None
        self._use_hook: bool = False
        self._hook_handle = None
        self._hook_proc = None  # 保持引用，避免被GC回收
        # 由监听线程写、主线程读的组合键当前值（update_hotkey 修改它）
        self._current: Tuple[int, int] = parse_hotkey(hotkey)
        self._pending_spec: Optional[str] = None  # 待应用的新热键
        self._pending_event = threading.Event()

    @property
    def spec(self) -> str:
        return self._spec

    @property
    def register_ok(self) -> Optional[bool]:
        return self._register_ok

    @property
    def using_hook_fallback(self) -> bool:
        return self._use_hook

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._ready_event.clear()
        self._thread = threading.Thread(target=self._run, name="HotkeyListener", daemon=True)
        self._thread.start()
        # 等待初始化完成（注册热键或安装Hook）
        self._ready_event.wait(timeout=1.0)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None

    def update_hotkey(self, spec: str) -> bool:
        """动态更换热键。成功返回 True；解析失败返回 False。"""
        parse_hotkey(spec)  # 校验，失败抛 ValueError
        self._spec = spec
        self._current = parse_hotkey(spec)
        # 通知监听线程重新注册（通过投递消息唤醒 GetMessage）
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0400 + 1, 0, 0)  # WM_APP+1
        return True

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._apply_registration()
        self._ready_event.set()

        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0:  # WM_QUIT
                break
            if ret == -1:
                break
            if msg.message == WM_APP_RELOAD:
                # 热键变更：注销旧的，注册新的
                self._teardown_registration()
                self._apply_registration()
            elif msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                try:
                    self._on_hotkey()
                except Exception:
                    pass
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self._teardown_registration()

    def _apply_registration(self) -> None:
        mods, vk = self._current
        ok = bool(user32.RegisterHotKey(None, self._hotkey_id, mods | MOD_NOREPEAT, vk))
        self._register_ok = ok
        if not ok:
            # 注册失败（被占用），退回低级键盘钩子模式
            self._install_hook_fallback()
        else:
            self._uninstall_hook_fallback()

    def _teardown_registration(self) -> None:
        try:
            user32.UnregisterHotKey(None, self._hotkey_id)
        except Exception:
            pass
        self._uninstall_hook_fallback()

    def _install_hook_fallback(self) -> None:
        # 安装全局低级键盘钩子：捕获当前组合键
        PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        mods, vk = self._current

        def _proc(nCode, wParam, lParam):
            try:
                if nCode == HC_ACTION and (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN):
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if kb.vkCode == vk:
                        mods_ok = True
                        if mods & MOD_SHIFT:
                            mods_ok = mods_ok and bool(user32.GetAsyncKeyState(0x10) & 0x8000)
                        if mods & MOD_CONTROL:
                            mods_ok = mods_ok and bool(user32.GetAsyncKeyState(0x11) & 0x8000)
                        if mods & MOD_ALT:
                            mods_ok = mods_ok and bool(user32.GetAsyncKeyState(0x12) & 0x8000)
                        if mods & MOD_WIN:
                            mods_ok = mods_ok and bool(user32.GetAsyncKeyState(0x5B) & 0x8000) \
                                      or bool(user32.GetAsyncKeyState(0x5C) & 0x8000)
                        # 反向校验：没按的修饰键必须确实没按，避免 ctrl+c 命中 ctrl+alt+c
                        if mods_ok and not (mods & MOD_SHIFT) and bool(user32.GetAsyncKeyState(0x10) & 0x8000):
                            mods_ok = False
                        if mods_ok and not (mods & MOD_CONTROL) and bool(user32.GetAsyncKeyState(0x11) & 0x8000):
                            mods_ok = False
                        if mods_ok and not (mods & MOD_ALT) and bool(user32.GetAsyncKeyState(0x12) & 0x8000):
                            mods_ok = False
                        if mods_ok:
                            try:
                                self._on_hotkey()
                            except Exception:
                                pass
                            return 1  # 吞掉按键
            except Exception:
                pass
            return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

        self._hook_proc = PROC(_proc)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc, hmod, 0)
        self._use_hook = bool(self._hook_handle)

    def _uninstall_hook_fallback(self) -> None:
        if self._hook_handle:
            try:
                user32.UnhookWindowsHookEx(self._hook_handle)
            except Exception:
                pass
        self._hook_handle = None
        self._hook_proc = None
        self._use_hook = False


WM_APP_RELOAD = 0x0400 + 1
