from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from . import autostart
from .config import AppConfig, save_config
from .hotkey import hotkey_available, normalize_hotkey, parse_hotkey
from .tencent_ocr import ACTION_NAME_MAP, OCR_ACTION_CATALOG


class HotkeyEdit(QtWidgets.QLineEdit):
    """热键录制输入框：点击后按键即录入组合键，Esc 恢复原值。"""

    recording_changed = QtCore.Signal(str)

    def __init__(self, current_spec: str, parent=None):
        super().__init__(parent)
        self._original = current_spec
        self._current = current_spec
        self.setReadOnly(True)
        self.setText(normalize_hotkey(current_spec))
        self.setPlaceholderText("点击此处后按下组合键")
        self._update_style(recording=False)

    def mousePressEvent(self, event):
        self._update_style(recording=True)
        self.setPlaceholderText("请按下组合键（Esc 取消）")
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        self._update_style(recording=False)
        self.setPlaceholderText("点击此处后按下组合键")
        super().focusOutEvent(event)

    def _update_style(self, recording: bool):
        if recording:
            self.setStyleSheet("border: 2px solid #1e80ff; color: #1e80ff;")
        else:
            self.setStyleSheet("")

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        key = event.key()
        if key == QtCore.Qt.Key.Key_Escape:
            self._current = self._original
            self.setText(normalize_hotkey(self._original))
            self._update_style(recording=False)
            return
        if key == QtCore.Qt.Key.Key_Backspace or key == QtCore.Qt.Key.Key_Delete:
            # 恢复默认
            self._current = "shift+c"
            self.setText(normalize_hotkey(self._current))
            self.recording_changed.emit(self._current)
            return

        # 忽略纯修饰键按下
        mod_keys = {
            QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Alt,
            QtCore.Qt.Key.Key_Shift, QtCore.Qt.Key.Key_Meta,
        }
        if key in mod_keys:
            return

        # 组合键文本
        parts = []
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if event.modifiers() & QtCore.Qt.KeyboardModifier.MetaModifier:
            parts.append("win")

        text = event.text()
        if key >= QtCore.Qt.Key.Key_F1 and key <= QtCore.Qt.Key.Key_F12:
            parts.append(f"f{key - QtCore.Qt.Key.Key_F1 + 1}")
        elif key == QtCore.Qt.Key.Key_Space:
            parts.append("space")
        elif key == QtCore.Qt.Key.Key_Print:
            parts.append("printscreen")
        elif text and text.isalnum() and len(text) == 1:
            parts.append(text.lower())
        else:
            # 未收录的键：提示不支持
            self.setPlaceholderText("不支持的按键，请换一个（Esc 取消）")
            return

        spec = "+".join(parts)
        try:
            parse_hotkey(spec)
        except ValueError:
            self.setPlaceholderText("无效组合，请重按（Esc 取消）")
            return
        self._current = spec
        self.setText(normalize_hotkey(spec))
        self._update_style(recording=False)
        self.recording_changed.emit(spec)

    def spec(self) -> str:
        return self._current


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, cfg: AppConfig, on_saved: Optional[Callable[[AppConfig], None]] = None):
        super().__init__()
        self.setWindowTitle("TrayOCR 设置")
        self.setModal(True)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
        self._cfg = cfg
        self._on_saved = on_saved

        self.ed_endpoint = QtWidgets.QLineEdit(cfg.endpoint)
        self.ed_region = QtWidgets.QLineEdit(cfg.region)
        self.ed_secret_id = QtWidgets.QLineEdit(cfg.secret_id)
        self.ed_secret_key = QtWidgets.QLineEdit(cfg.secret_key)
        self.ed_secret_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.chk_multi_lang = QtWidgets.QCheckBox("启用多语言识别（MulOCR，自动检测中/英/日/韩等）")
        self.chk_multi_lang.setChecked(cfg.multi_language)
        self.chk_multi_lang.setToolTip(
            "未勾选时使用 ConfigID=OCR（中英混合，精度最高）；勾选后使用 ConfigID=MulOCR（自动检测几十种语言）"
        )

        # 开机自启动：以注册表实际状态为准（勾选=写入 HKCU Run）
        self.chk_autostart = QtWidgets.QCheckBox("开机自动启动")
        self.chk_autostart.setChecked(cfg.autostart or autostart.is_autostart_enabled())
        self.chk_autostart.setToolTip("通过当前用户的注册表 Run 项实现，无需管理员权限。")

        # 快捷键录制框
        self.ed_hotkey = HotkeyEdit(cfg.hotkey or "shift+c")
        self.ed_hotkey.setMinimumWidth(180)
        self._hk_status = QtWidgets.QLabel("")
        self._hk_status.setStyleSheet("color: #555;")
        self.ed_hotkey.recording_changed.connect(self._check_hotkey_conflict)

        btn_reset_hk = QtWidgets.QPushButton("恢复默认")
        btn_reset_hk.clicked.connect(self._reset_hotkey)

        # 接口下拉框：按腾讯云官方分类分组展示（Action + 中文名）
        from PySide6 import QtGui as _QtGui
        self.cmb_action = QtWidgets.QComboBox()
        for category, items in OCR_ACTION_CATALOG:
            # 分类标题项（不可选）
            self.cmb_action.addItem(f"—— {category} ——")
            mi = self.cmb_action.model().item(self.cmb_action.count() - 1)
            mi.setFlags(mi.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            mi.setForeground(_QtGui.QBrush(_QtGui.QColor("#888888")))
            for action, name in items:
                self.cmb_action.addItem(f"{action}  {name}", userData=action)
        # 旧配置里的 Action 不在目录时附加一项，避免下拉显示空白
        if cfg.ocr_action and cfg.ocr_action not in ACTION_NAME_MAP:
            self.cmb_action.addItem(f"{cfg.ocr_action}  (自定义)", userData=cfg.ocr_action)
        # 选中当前配置
        idx = self.cmb_action.findData(cfg.ocr_action)
        if idx < 0:
            idx = self.cmb_action.findData("GeneralAccurateOCR")
        if idx >= 0:
            self.cmb_action.setCurrentIndex(idx)
        self.cmb_action.setToolTip(
            "选择要调用的腾讯云 OCR 接口，按官方分类分组。\n"
            "注意：鉴伪核验类 / Submit·Describe 开头的异步 Agent 类接口，"
            "用截图直接调用可能报参数错误——它们需要额外入参或走异步任务流程。"
        )

        hk_row = QtWidgets.QHBoxLayout()
        hk_row.addWidget(self.ed_hotkey, 1)
        hk_row.addWidget(btn_reset_hk)
        hk_box = QtWidgets.QVBoxLayout()
        hk_box.addLayout(hk_row)
        hk_box.addWidget(self._hk_status)

        form = QtWidgets.QFormLayout()
        form.addRow("API Endpoint", self.ed_endpoint)
        form.addRow("Region", self.ed_region)
        form.addRow("SecretId", self.ed_secret_id)
        form.addRow("SecretKey", self.ed_secret_key)
        form.addRow("识别接口", self.cmb_action)
        form.addRow("识别模式", self.chk_multi_lang)
        form.addRow("截图快捷键", hk_box)
        form.addRow("开机自启动", self.chk_autostart)

        tip = QtWidgets.QLabel(
            "提示：SecretKey 使用 Windows DPAPI 在本机加密保存。"
            "快捷键点击输入框后直接按键录入；需至少一个修饰键，保存时自动检测冲突。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #555;")

        btn_save = QtWidgets.QPushButton("保存")
        btn_cancel = QtWidgets.QPushButton("取消")
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(tip)
        root.addLayout(btns)

        self.resize(520, 0)

    def _reset_hotkey(self):
        self.ed_hotkey._current = "shift+c"
        self.ed_hotkey.setText(normalize_hotkey("shift+c"))
        self._check_hotkey_conflict("shift+c")

    def _check_hotkey_conflict(self, spec: str):
        """录入新键后立即做冲突探测（跳过未变更的当前键）。"""
        if spec == (self._cfg.hotkey or "shift+c"):
            self._hk_status.setText("当前快捷键，未变更")
            self._hk_status.setStyleSheet("color: #555;")
            return
        ok, reason = hotkey_available(spec)
        if ok:
            self._hk_status.setText("可用 ✓")
            self._hk_status.setStyleSheet("color: #1a7f37;")
        else:
            self._hk_status.setText(f"冲突：{reason}")
            self._hk_status.setStyleSheet("color: #d03a3a;")

    def _save(self):
        endpoint = (self.ed_endpoint.text() or "").strip()
        region = (self.ed_region.text() or "").strip()
        secret_id = (self.ed_secret_id.text() or "").strip()
        secret_key = (self.ed_secret_key.text() or "").strip()
        multi_language = self.chk_multi_lang.isChecked()
        ocr_action = (self.cmb_action.currentData() or "GeneralAccurateOCR").strip()
        autostart_on = self.chk_autostart.isChecked()
        new_hotkey = self.ed_hotkey.spec()

        if not endpoint.startswith("http"):
            QtWidgets.QMessageBox.critical(self, "设置错误", "Endpoint 需要以 http/https 开头。")
            return
        if not region:
            QtWidgets.QMessageBox.critical(self, "设置错误", "Region 不能为空。")
            return
        if not secret_id or not secret_key:
            ok = QtWidgets.QMessageBox.question(
                self, "确认", "SecretId/SecretKey 为空，OCR 将无法调用。仍要保存吗？"
            )
            if ok != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        # 热键校验 + 冲突检测（与当前一致时跳过探测，避免探测到自己）
        old_hotkey = self._cfg.hotkey or "shift+c"
        if new_hotkey != old_hotkey:
            try:
                parse_hotkey(new_hotkey)
            except ValueError as e:
                QtWidgets.QMessageBox.critical(self, "快捷键无效", str(e))
                return
            ok, reason = hotkey_available(new_hotkey)
            if not ok:
                QtWidgets.QMessageBox.critical(
                    self, "快捷键冲突",
                    f"快捷键 {normalize_hotkey(new_hotkey)} 无法使用：{reason}\n请换一个组合键。"
                )
                return

        self._cfg.endpoint = endpoint
        self._cfg.region = region
        self._cfg.secret_id = secret_id
        self._cfg.language_type = ""  # 已废弃字段，清空即可
        self._cfg.multi_language = multi_language
        self._cfg.ocr_action = ocr_action or "GeneralAccurateOCR"
        self._cfg.hotkey = new_hotkey
        self._cfg.autostart = autostart_on
        self._cfg.set_secret_key(secret_key)
        save_config(self._cfg)

        # 自启动：写/删注册表，失败时明确反馈
        if autostart_on:
            if not autostart.enable_autostart():
                QtWidgets.QMessageBox.warning(self, "开机自启动", "注册表写入失败，开机自启动未生效。")
        else:
            autostart.disable_autostart()

        if self._on_saved:
            self._on_saved(self._cfg)

        QtWidgets.QMessageBox.information(
            self, "已保存",
            "设置已保存并生效。\n"
            f"截图快捷键：{normalize_hotkey(new_hotkey)}\n"
            f"开机自启动：{'已开启' if autostart_on else '已关闭'}"
        )
        self.accept()

