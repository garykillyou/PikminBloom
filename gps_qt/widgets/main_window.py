"""主視窗：整體版面、按鈕狀態機、視窗幾何/主題存讀。

對應原本 gps_app.py 的 GPSApp 類別裡屬於「UI 骨架」的部分；連線狀態機
搬到 gps_qt/session.py 的 GPSSession。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QVBoxLayout, QWidget,
)

from .. import persistence, theme, window_geometry
from ..session import GPSSession
from .favorites_panel import FavoritesPanel
from .pin_panel import PinPanel
from .route_panel import RoutePanel

DEFAULT_ROUTE = [
    [24.1368, 120.6862, "台中火車站"],
    [24.1390, 120.6800, "台灣大道一段"],
    [24.1420, 120.6720, "台灣大道二段"],
    [24.1470, 120.6640, "台灣大道三段"],
    [24.1520, 120.6560, "台灣大道四段"],
    [24.1560, 120.6480, "近市政府"],
    [24.1590, 120.6430, "勤美誠品"],
]

WIDE_LAYOUT_BREAKPOINT = 1000


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = persistence.load_settings()
        self.theme_name = self.settings.get("theme", "dark")
        if self.theme_name not in ("dark", "light"):
            self.theme_name = "dark"
        self.mode = "route"

        route = persistence.load_saved_route(self.settings) or [list(r) for r in DEFAULT_ROUTE]

        self.setWindowTitle("iPhone GPS 路線模擬器")
        self.setMinimumSize(window_geometry.MIN_WINDOW_W, window_geometry.MIN_WINDOW_H)
        maximize = window_geometry.restore_geometry(self, self.settings)
        self._normal_geometry = window_geometry.capture_geometry(self)

        # 樣式表要在建立任何子 widget 之前先套用：子 widget 建構時若呼叫
        # sizeHint()/fontMetrics() 依目前樣式決定固定寬度，套用順序反了會用到
        # 「尚未套用 QSS 前」的尺寸，等真正套用樣式表後（padding 變大）就會被裁切。
        theme.apply(QApplication.instance(), self.theme_name)
        self._build_ui(route)
        self._apply_theme()

        self.session = GPSSession(
            route_provider=lambda: self.route_panel.route,
            speed_provider=lambda: self.route_panel.speed_ms(),
            pin_provider=lambda: self.pin_panel.coordinates(),
            mode_provider=lambda: self.mode,
            loop_provider=lambda: self.route_panel.loop_enabled(),
        )
        self.session.log.connect(self._log)
        self.session.progress_value.connect(lambda v: self.progress_bar.setValue(int(v * 1000)))
        self.session.progress_label.connect(self.progress_label.setText)
        self.session.paused.connect(self._sync_btn_states)
        self.session.session_ended.connect(self._on_session_ended)
        self.session.direction_changed.connect(self._sync_btn_states)
        self._switch_mode("route")
        self._sync_btn_states()

        if maximize:
            self.showMaximized()
        else:
            self.showNormal()

    # ── UI 組裝 ────────────────────
    def _build_ui(self, route):
        central = QWidget()
        outer_layout = QVBoxLayout(central)

        title_row = QHBoxLayout()
        title_label = theme.mark_class(QLabel("GPS 路線模擬器"), "app-title")
        title_row.addWidget(title_label)
        subtitle = QLabel("iPhone iOS 26  ·  需先執行 tunneld")
        title_row.addWidget(subtitle)
        title_row.addStretch(1)
        self.theme_btn = QPushButton()
        self.theme_btn.clicked.connect(self._toggle_theme)
        title_row.addWidget(self.theme_btn)
        outer_layout.addLayout(title_row)

        self.splitter = QSplitter(Qt.Horizontal)
        outer_layout.addWidget(self.splitter, 1)

        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("開始模擬")
        self.start_btn.clicked.connect(self._start)
        btn_row.addWidget(self.start_btn)
        self.return_btn = QPushButton("往起點")
        self.return_btn.clicked.connect(self._reverse)
        btn_row.addWidget(self.return_btn)
        self.stop_btn = QPushButton("停止")
        theme.mark_class(self.stop_btn, "danger")
        self.stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self.stop_btn)
        left_layout.addLayout(btn_row)

        self.restore_btn = QPushButton("恢復真實定位")
        self.restore_btn.clicked.connect(self._restore_real_location)
        left_layout.addWidget(self.restore_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        left_layout.addWidget(self.progress_bar)
        self.progress_label = QLabel("")
        left_layout.addWidget(self.progress_label)

        left_layout.addWidget(theme.style_section_title(QLabel("執行日誌")))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        left_layout.addWidget(self.log_view)

        self.favorites_panel = FavoritesPanel(
            pin_provider=lambda: self.pin_panel.coordinates(),
            route_provider=lambda: self.route_panel.route,
            mode_provider=lambda: self.mode,
        )
        self.favorites_panel.load_requested.connect(self._load_favorite)
        left_layout.addWidget(self.favorites_panel)

        self.splitter.addWidget(left_col)

        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)

        mode_row = QHBoxLayout()
        mode_row.addWidget(theme.style_section_title(QLabel("模式選擇")))
        # 用 checkable 按鈕 + 互斥群組取代原本手動切換 QSS 屬性：qt-material 的
        # QPushButton:checked 樣式本身就會用 primaryColor 標示目前選取的模式。
        self.route_mode_btn = QPushButton("路線移動")
        self.route_mode_btn.setCheckable(True)
        self.route_mode_btn.clicked.connect(lambda: self._switch_mode("route"))
        mode_row.addWidget(self.route_mode_btn)
        self.pin_mode_btn = QPushButton("固定定位")
        self.pin_mode_btn.setCheckable(True)
        self.pin_mode_btn.clicked.connect(lambda: self._switch_mode("pin"))
        mode_row.addWidget(self.pin_mode_btn)
        self.mode_btn_group = QButtonGroup(self)
        self.mode_btn_group.setExclusive(True)
        self.mode_btn_group.addButton(self.route_mode_btn)
        self.mode_btn_group.addButton(self.pin_mode_btn)
        mode_row.addStretch(1)
        right_layout.addLayout(mode_row)

        self.pin_panel = PinPanel()
        right_layout.addWidget(self.pin_panel)
        self.route_panel = RoutePanel(route)
        right_layout.addWidget(self.route_panel)

        self.splitter.addWidget(right_col)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        # setStretchFactor 只影響「resize 時多出來的空間」怎麼分配，初始寬度仍要
        # 靠 setSizes() 指定；給兩個相同的大數字，Qt 會依可用空間等比例換算。
        self.splitter.setSizes([10**6, 10**6])

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

    # ── 主題 ────────────────────
    def _apply_theme(self):
        theme.apply(QApplication.instance(), self.theme_name)
        self.theme_btn.setText("切換淺色" if self.theme_name == "dark" else "切換深色")

    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self._apply_theme()
        self.settings["theme"] = self.theme_name
        persistence.save_settings(self.settings)

    # ── 模式切換 ────────────────────
    def _switch_mode(self, mode):
        self.mode = mode
        if mode == "route":
            self.pin_panel.hide()
            self.route_panel.show()
            self.start_btn.setText("開始模擬")
        else:
            self.route_panel.hide()
            self.pin_panel.show()
            self.start_btn.setText("固定定位")
        self.route_mode_btn.setChecked(mode == "route")
        self.pin_mode_btn.setChecked(mode == "pin")
        self._update_return_btn_state()
        self.favorites_panel.refresh()

    def _load_favorite(self, fav):
        if fav["type"] == "pin":
            self.pin_panel.lat_spin.setValue(fav["lat"])
            self.pin_panel.lon_spin.setValue(fav["lon"])
            self._switch_mode("pin")
        else:
            self.route_panel.set_route([list(r) for r in fav["route"]])
            self._switch_mode("route")
        self._log(f"已載入：{fav['name']}")

    # ── 控制按鈕 ────────────────────
    def _start(self):
        if self.mode == "route" and len(self.route_panel.route) < 2:
            QMessageBox.critical(self, "錯誤", "請至少設定 2 個路線點")
            return
        self._log("固定定位模式啟動..." if self.mode == "pin" else "開始模擬...")
        self.session.start_forward()
        self._sync_btn_states()

    def _stop(self):
        self.session.stop()
        self._log("停止中...")

    def _reverse(self):
        if self.mode != "route":
            return
        if len(self.route_panel.route) < 2:
            QMessageBox.critical(self, "錯誤", "請至少設定 2 個路線點")
            return
        self.session.reverse()
        self._sync_btn_states()
        if self.session.pending_action == "reverse":
            self._log("已切換方向：往起點走...")
        else:
            self._log("已切換方向：往終點走...")

    def _restore_real_location(self):
        if not self.session.session_active:
            QMessageBox.information(self, "提示", "目前尚未連線模擬，已經是真實定位")
            return
        if self.session.pending_action in ("forward", "reverse"):
            QMessageBox.warning(self, "警告", "請先按「停止」，再恢復真實定位")
            return
        self.session.restore_real_location()
        self._sync_btn_states()
        self._log("恢復真實定位中...")

    def _on_session_ended(self):
        # 連線已結束（正常斷線或中途出錯），把動作歸零再同步按鈕狀態，
        # 否則殘留的 "disconnect" 會讓按鈕全部卡在停用。
        self.session.pending_action = "pause"
        self._sync_btn_states()

    def _sync_btn_states(self):
        busy = self.session.pending_action in ("forward", "reverse", "disconnect")
        # 固定定位模式啟動後會立刻回到 "pause"（保持在目前座標），此時連線
        # 仍在，「停止」要維持可按，否則會跟 _walk_pin() 的提示訊息互相矛盾。
        holding = self.session.session_active and self.session.pending_action == "pause"
        self.start_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(self.session.pending_action in ("forward", "reverse") or holding)
        # 從未成功連線（尚未按過「開始模擬」，或已恢復真實定位斷線）時，
        # 「恢復真實定位」沒有意義，初始化時只留「開始模擬」可以點擊。
        self.restore_btn.setEnabled(self.session.session_active and not busy)
        self._update_return_btn_state()

    def _update_return_btn_state(self):
        # 返回鈕現在只是「切換方向」，正在返回中也要能再按一次切回前進，
        # 所以不再因 pending_action == "reverse" 而停用。「已啟動」不能只
        # 看 session_active——那要等背景協程實際連上裝置才會變 True，
        # 沒有訊號通知 UI，會卡到按「停止」觸發 paused 訊號才更新。改用
        # pending_action 是否已經是 forward/reverse：按下「開始模擬」當下
        # 就同步變成 forward，可以立刻切換方向，不用等連線完成。初始化時
        # （尚未按過「開始模擬」）兩者皆為否，只留「開始模擬」可以點擊。
        # 文字顯示「按下去會往哪裡走」：目前正往起點走就顯示「往終點」，
        # 否則顯示「往起點」。
        moving = self.session.pending_action in ("forward", "reverse")
        started = moving or self.session.session_active
        enabled = (
            self.mode == "route"
            and started
            and self.session.pending_action != "disconnect"
        )
        self.return_btn.setEnabled(enabled)
        self.return_btn.setText("往終點" if self.session.pending_action == "reverse" else "往起點")

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    # ── 視窗幾何記憶 + 響應式版面 ────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.isMaximized():
            self._normal_geometry = window_geometry.capture_geometry(self)
        wide = self.width() >= WIDE_LAYOUT_BREAKPOINT
        new_orientation = Qt.Horizontal if wide else Qt.Vertical
        if self.splitter.orientation() != new_orientation:
            self.splitter.setOrientation(new_orientation)
            # 換方向後舊的 sizes（另一軸的像素）沿用會變成不等寬/不等高，重設成等分。
            self.splitter.setSizes([10**6, 10**6])

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self.isMaximized():
            self._normal_geometry = window_geometry.capture_geometry(self)

    def closeEvent(self, event):
        win = dict(self._normal_geometry)
        win["maximized"] = self.isMaximized()
        self.settings["window"] = win
        self.settings["last_route"] = [[r[0], r[1], r[2]] for r in self.route_panel.route]
        persistence.save_settings(self.settings)
        super().closeEvent(event)
