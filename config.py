import base64
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import ctypes
from ctypes import wintypes


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_DATA_BLOB),
]
_crypt32.CryptProtectData.restype = wintypes.BOOL

_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_DATA_BLOB),
]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL

_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _raise_last_win_error(prefix: str) -> None:
    err = ctypes.get_last_error()
    raise OSError(f"{prefix}. WinError={err}")


def dpapi_encrypt(plaintext: str) -> str:
    if plaintext is None:
        return ""
    data = plaintext.encode("utf-8")
    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    in_blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DATA_BLOB()
    if not _crypt32.CryptProtectData(ctypes.byref(in_blob), "TrayOCR", None, None, None, 0, ctypes.byref(out_blob)):
        _raise_last_win_error("CryptProtectData failed")
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        _kernel32.LocalFree(out_blob.pbData)


def dpapi_decrypt(ciphertext_b64: str) -> str:
    if not ciphertext_b64:
        return ""
    encrypted = base64.b64decode(ciphertext_b64)
    buf = (ctypes.c_byte * len(encrypted)).from_buffer_copy(encrypted)
    in_blob = _DATA_BLOB(len(encrypted), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DATA_BLOB()
    ppsz_desc = wintypes.LPWSTR()
    if not _crypt32.CryptUnprotectData(ctypes.byref(in_blob), ctypes.byref(ppsz_desc), None, None, None, 0, ctypes.byref(out_blob)):
        _raise_last_win_error("CryptUnprotectData failed")
    try:
        decrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return decrypted.decode("utf-8", errors="replace")
    finally:
        _kernel32.LocalFree(out_blob.pbData)
        if ppsz_desc:
            _kernel32.LocalFree(ppsz_desc)


def _app_config_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    d = Path(appdata) / "TrayOCR"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return _app_config_dir() / "config.json"


@dataclass
class AppConfig:
    endpoint: str = "https://ocr.tencentcloudapi.com/"
    region: str = "ap-guangzhou"
    secret_id: str = ""
    secret_key_encrypted: str = ""
    language_type: str = ""  # 已废弃，保留兼容旧配置；新逻辑请用 multi_language
    multi_language: bool = False  # True=ConfigID=MulOCR 多语言自动识别；False=ConfigID=OCR 中英混合默认
    ocr_action: str = "GeneralAccurateOCR"  # 腾讯云 OCR 接口 Action 名
    autostart: bool = False  # 开机自启动（HKCU Run 注册表）
    hotkey: str = "shift+c"  # 全局截图热键，格式如 "ctrl+alt+o"

    @property
    def secret_key(self) -> str:
        try:
            return dpapi_decrypt(self.secret_key_encrypted)
        except Exception:
            return ""

    def set_secret_key(self, secret_key: str) -> None:
        self.secret_key_encrypted = dpapi_encrypt(secret_key or "")


def load_config() -> AppConfig:
    p = config_path()
    if not p.exists():
        return AppConfig()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cfg = AppConfig(**{k: v for k, v in data.items() if k in asdict(AppConfig()).keys()})
        # 旧版迁移：language_type 非空视为"启用多语言"
        if getattr(cfg, "language_type", ""):
            cfg.multi_language = True
            cfg.language_type = ""
        return cfg
    except Exception:
        # 配置损坏则回退默认
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    p = config_path()
    data = asdict(cfg)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

