"""固定定位模式面板：對應原本 gps_app.py 的 pin_frame。"""

from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from .. import theme

PIN_PRESETS = [
    ("台中火車站", 24.1368, 120.6862),
    ("台北101", 25.0338, 121.5645),
    ("高雄85大樓", 22.6155, 120.3025),
    ("台南孔廟", 22.9969, 120.2008),
]


class PinPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)

        layout.addWidget(theme.style_section_title(QLabel("固定座標")))

        form = QFormLayout()
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setDecimals(6)
        self.lat_spin.setRange(-90.0, 90.0)
        self.lat_spin.setValue(24.1368)
        form.addRow("緯度：", self.lat_spin)

        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setDecimals(6)
        self.lon_spin.setRange(-180.0, 180.0)
        self.lon_spin.setValue(120.6862)
        form.addRow("經度：", self.lon_spin)
        layout.addLayout(form)

        layout.addWidget(QLabel("快速選擇："))
        presets_row = QHBoxLayout()
        for name, lat, lon in PIN_PRESETS:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked=False, la=lat, lo=lon: self._apply_preset(la, lo))
            presets_row.addWidget(btn)
        presets_row.addStretch(1)
        layout.addLayout(presets_row)

        # 沒有這個 stretch 項目時，QVBoxLayout 會把面板多出來的垂直空間平均分給
        # 上面每一列（包含兩個標題 QLabel），導致文字被撐在一個過高的空白區塊
        # 正中央，看起來像「標題列高度太大」。加在最後把多餘空間全部吸收掉，
        # 其餘內容維持貼齊頂端的自然高度。
        layout.addStretch(1)

    def _apply_preset(self, lat, lon):
        self.lat_spin.setValue(lat)
        self.lon_spin.setValue(lon)

    def coordinates(self):
        return self.lat_spin.value(), self.lon_spin.value()
