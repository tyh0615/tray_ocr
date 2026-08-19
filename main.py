import threading
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from .capture import CaptureResult, RegionCaptureOverlay
from .config import AppConfig, load_config
from .hotkey import HotkeyListener, normalize_hotkey
from .tencent_ocr import TencentOcrClient, TencentOcrConfig
from .ui import SettingsDialog


class TrayOcrApp(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.cfg: AppConfig = load_config()
        self._ocr_lock = threading.Lock()

        # 保持对象引用，避免被 GC 回收导致菜单/信号失效
        self.tray = QtWidgets.QSystemTrayIcon(self._make_icon())
        self.tray.setToolTip("TrayOCR")

        self.menu = QtWidgets.QMenu()
        self.act_cap = self.menu.addAction(f"截图 OCR ({normalize_hotkey(self.cfg.hotkey)})")
        self.act_set = self.menu.addAction("设置")
        self.menu.addSeparator()
        self.act_quit = self.menu.addAction("退出")

        self.act_cap.triggered.connect(self.capture_and_ocr)
        self.act_set.triggered.connect(self.open_settings)
        self.act_quit.triggered.connect(self.quit)

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip(f"TrayOCR · {normalize_hotkey(self.cfg.hotkey)}")
        self.tray.show()

        self.overlay: Optional[RegionCaptureOverlay] = None

        # 热键在后台线程监听，触发时投递到 Qt 主线程
        self.hotkey = HotkeyListener(on_hotkey=self._on_hotkey_thread, hotkey=self.cfg.hotkey or "shift+c")
        self.hotkey.start()
        # 启动后给出一次提示，方便排查“热键没反应”
        if self.hotkey.register_ok is False:
            if self.hotkey.using_hook_fallback:
                self._notify(f"{normalize_hotkey(self.cfg.hotkey)} 的系统热键注册失败（可能被占用），已启用钩子模式作为兼容。")
            else:
                self._notify(f"{normalize_hotkey(self.cfg.hotkey)} 热键初始化失败，请尝试以管理员运行或更换快捷键。")

    def _make_icon(self) -> QtGui.QIcon:
        # 简单生成一个轻量图标（避免额外资源文件）
        size = 64
        pm = QtGui.QPixmap(size, size)
        pm.fill(QtCore.Qt.GlobalColor.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(0, 160, 0))
        pen.setWidth(4)
        p.setPen(pen)
        p.drawRoundedRect(QtCore.QRect(10, 8, 44, 48), 8, 8)
        f = p.font()
        f.setBold(True)
        f.setPointSize(14)
        p.setFont(f)
        p.drawText(QtCore.QRect(0, 0, size, size), QtCore.Qt.AlignmentFlag.AlignCenter, "OCR")
        p.end()
        return QtGui.QIcon(pm)

    def _notify(self, msg: str, title: str = "TrayOCR"):
        # QSystemTrayIcon.showMessage 在 Windows 会走系统通知中心
        try:
            self.tray.showMessage(title, msg, QtWidgets.QSystemTrayIcon.MessageIcon.Information, 2500)
        except Exception:
            pass

    def _on_hotkey_thread(self):
        QtCore.QMetaObject.invokeMethod(self, "capture_and_ocr", QtCore.Qt.ConnectionType.QueuedConnection)

    @QtCore.Slot()
    def capture_and_ocr(self):
        self._notify("进入截图模式：请拖拽框选区域，按 Esc 取消。")
        if not self._ocr_lock.acquire(blocking=False):
            self._notify("正在识别中，请稍候…")
            return
        try:
            self.overlay = RegionCaptureOverlay()
            self.overlay.captured.connect(self._on_captured)
            self.overlay.start()
        except Exception as e:
            self._ocr_lock.release()
            self._notify(f"启动截图失败：{e}")

    @QtCore.Slot(object)
    def _on_captured(self, result: Optional[CaptureResult]):
        try:
            # 单次使用：尽早断开连接，避免重复触发
            if self.overlay:
                try:
                    self.overlay.captured.disconnect(self._on_captured)
                except Exception:
                    pass
            if not result:
                return
            x1, y1, x2, y2 = result.bbox
            # Qt 的 QRect right/bottom 为包含边界；截图宽高按像素至少 +1
            w = max(1, x2 - x1 + 1)
            h = max(1, y2 - y1 + 1)

            screen = QtGui.QGuiApplication.screenAt(QtCore.QPoint(x1, y1)) or QtGui.QGuiApplication.primaryScreen()
            geo = screen.geometry()
            local_x = x1 - geo.left()
            local_y = y1 - geo.top()

            # Qt grabWindow 接收的是逻辑像素；坐标会由 Qt 内部按 devicePixelRatio 自动转换。
            # 之前先乘 dpr 再传，会把截图位置偏移到屏幕外（高 DPI 屏易触发 ImageNoText）。
            px = int(local_x)
            py = int(local_y)
            pw = int(w)
            ph = int(h)
            pm = screen.grabWindow(0, px, py, pw, ph)
            ba = QtCore.QByteArray()
            buf = QtCore.QBuffer(ba)
            buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
            pm.save(buf, "PNG")
            image_bytes = bytes(ba)

            text = self._do_ocr(image_bytes)
            if not text:
                self._notify("未识别到文字。")
                return
            QtGui.QGuiApplication.clipboard().setText(text)
            self._notify("识别结果已复制到剪贴板。")
        except Exception as e:
            self._notify(f"识别失败：{e}")
        finally:
            try:
                self._ocr_lock.release()
            except Exception:
                pass

    def _do_ocr(self, image_bytes: bytes) -> str:
        cfg = self.cfg
        if not cfg.secret_id or not cfg.secret_key:
            raise RuntimeError("未配置 SecretId/SecretKey，请先在设置中填写。")

        client = TencentOcrClient(
            TencentOcrConfig(
                endpoint=cfg.endpoint,
                region=cfg.region,
                secret_id=cfg.secret_id,
                secret_key=cfg.secret_key,
                multi_language=cfg.multi_language,
                action=cfg.ocr_action,
            )
        )
        return client.recognize(image_bytes)

    @QtCore.Slot()
    def open_settings(self):
        dlg = SettingsDialog(self.cfg, on_saved=self._on_cfg_saved)
        dlg.exec()

    def _on_cfg_saved(self, cfg: AppConfig):
        self.cfg = cfg
        # 快捷键即时生效：热键监听线程动态重注册
        try:
            self.hotkey.update_hotkey(cfg.hotkey or "shift+c")
        except ValueError:
            pass
        self.act_cap.setText(f"截图 OCR ({normalize_hotkey(cfg.hotkey)})")
        self.tray.setToolTip(f"TrayOCR · {normalize_hotkey(cfg.hotkey)}")
        self._notify("设置已更新。")

    @QtCore.Slot()
    def quit(self):
        try:
            self.hotkey.stop()
        except Exception:
            pass
        self.tray.hide()
        QtWidgets.QApplication.quit()


def main():
    app = QtWidgets.QApplication([])
    # 防止 Qt 因无窗口而直接退出
    app.setQuitOnLastWindowClosed(False)
    # 必须保存引用：否则 TrayOcrApp 可能被 GC 回收，表现为“托盘还在但菜单/热键没反应”
    tray_app = TrayOcrApp()
    app.exec()


if __name__ == "__main__":
    main()
