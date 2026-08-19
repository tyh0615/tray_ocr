from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass
class CaptureResult:
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in global coords


class RegionCaptureOverlay(QtWidgets.QWidget):
    """
    Qt 全屏半透明遮罩 + QRubberBand 框选区域。
    """

    captured = QtCore.Signal(object)  # CaptureResult | None

    def __init__(self):
        super().__init__(
            None,
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool,
        )
        self.setWindowTitle("TrayOCR Capture")
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        # 由 paintEvent 自己绘制半透明背景；这样在某些系统/主题下也能稳定可见
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        self._start_pos: Optional[QtCore.QPoint] = None
        self._rubber = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, self)

        # 覆盖所有屏幕的虚拟桌面区域
        desktop = QtGui.QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(desktop)

    def start(self):
        self._start_pos = None
        self._rubber.hide()
        # 不使用 showFullScreen()，直接覆盖虚拟桌面区域并置顶显示
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        try:
            self.grabMouse()
            self.grabKeyboard()
        except Exception:
            pass

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 80))
        p.end()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self._finish(None)
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        self._start_pos = event.globalPosition().toPoint()
        self._rubber.setGeometry(QtCore.QRect(self.mapFromGlobal(self._start_pos), QtCore.QSize()))
        self._rubber.show()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self._start_pos:
            return
        cur = event.globalPosition().toPoint()
        rect = QtCore.QRect(self._start_pos, cur).normalized()
        self._rubber.setGeometry(QtCore.QRect(self.mapFromGlobal(rect.topLeft()), rect.size()))

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton or not self._start_pos:
            return
        end = event.globalPosition().toPoint()
        rect = QtCore.QRect(self._start_pos, end).normalized()
        if rect.width() < 5 or rect.height() < 5:
            self._finish(None)
            return
        self._finish(CaptureResult(bbox=(rect.left(), rect.top(), rect.right(), rect.bottom())))

    def _finish(self, result: Optional[CaptureResult]):
        self._rubber.hide()
        try:
            self.releaseMouse()
            self.releaseKeyboard()
        except Exception:
            pass
        self.hide()
        self.captured.emit(result)
