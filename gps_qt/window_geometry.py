"""視窗位置記憶：大小/座標/是否最大化存在 settings 的 "window" 欄位。

改用 Qt 的 QScreen API 判斷座標是否落在任何一台螢幕內，取代原本
gps_app.py 用 ctypes 呼叫 Win32 MonitorFromPoint 的做法；Qt6 的
QWidget.geometry()/QScreen.availableGeometry() 都是邏輯像素，
不需要再手動做實體/邏輯像素換算。
"""

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication

DEFAULT_WINDOW_W = 1500
DEFAULT_WINDOW_H = 820
MIN_WINDOW_W = 560
MIN_WINDOW_H = 360


def point_on_any_screen(x, y):
    """(x, y)（邏輯像素）是否落在目前接上的任何一台螢幕內。

    找不到設定或螢幕已拔掉/解析度變了時，呼叫端應該放棄還原座標、
    只套用大小，位置交給作業系統決定。
    """
    return QGuiApplication.screenAt(QPoint(int(x), int(y))) is not None


def restore_geometry(window, settings):
    """依 settings["window"] 還原視窗大小/位置/是否最大化。

    回傳 True 代表視窗啟動後應該呼叫 showMaximized()，否則呼叫 showNormal()。
    找不到設定（第一次啟動）時 fallback 回預設大小 + 最大化，與原本行為一致。
    """
    win = settings.get("window") or {}
    w = win.get("width", DEFAULT_WINDOW_W)
    h = win.get("height", DEFAULT_WINDOW_H)
    x, y = win.get("x"), win.get("y")
    maximized = bool(win.get("maximized", True))

    window.resize(max(w, MIN_WINDOW_W), max(h, MIN_WINDOW_H))
    if isinstance(x, int) and isinstance(y, int) and point_on_any_screen(x, y):
        window.move(x, y)
    return maximized


def capture_geometry(window):
    """讀取視窗目前的大小/座標/是否最大化，回傳可直接存進 settings["window"] 的 dict。

    只有在「非最大化」狀態下的座標才有意義（最大化時的幾何是相對於當下螢幕算出來的，
    不能當作下次還原的基準），所以呼叫端應該只在 window.isMaximized() 為 False 時
    記錄 x/y；這裡一律回傳目前狀態，由呼叫端決定何時要更新記錄。
    """
    geo = window.geometry()
    return {
        "width": geo.width(),
        "height": geo.height(),
        "x": geo.x(),
        "y": geo.y(),
        "maximized": window.isMaximized(),
    }
