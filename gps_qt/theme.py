"""主題套用：改用 qt-material 套件產生樣式表，取代自寫的 QSS。

qt-material 最新版本身沒有版本限制問題（純 Python，任何 Qt binding 皆可）。
色票（含 danger/success 等語意色）全部使用 qt-material 內建主題的預設值，
不覆寫成原本 gps_app.py 的品牌色。
"""

import qt_material
from PySide6.QtWidgets import QApplication

THEME_FILES = {"dark": "dark_red.xml", "light": "light_red.xml"}

FS_TITLE = 22  # App 標題字級（pt），qt-material 本身不管這個，維持原本大小
FS_SECTION_TITLE = 18  # 區塊標題（「移動速度」「我的最愛」這類），比內文大 3 階


# qt-material 的樣式表最上層有一條 `* { font-size: ...px; ... }` 規則，套用在
# QApplication 層級時，會蓋掉個別 widget 用 setFont() 設定的字級（Qt 的樣式表
# 屬性一旦命中該 widget，優先權高於程式設定的 QFont）。所以字級大小的例外一律
# 要用「更明確的 QSS 選擇器」蓋回去，不能只靠 setFont()——這裡沿用 mark_class()
# 同一套「動態屬性 class + 對應 QSS 規則」機制。
EXTRA_QSS_TEMPLATE = """
.app-title {{ font-size: {app_title}pt; font-weight: bold; }}
.section-title {{ font-size: {section_title}pt; font-weight: bold; }}
"""


def apply(app: QApplication, theme_name: str):
    """套用主題。切換主題時重新呼叫這個函式即可，不需要重建視窗。

    淺色主題要加 invert_secondary=True：qt-material 的 secondaryColor 系列
    預設是深色系（給深色主題的卡片/表面用），淺色主題不反轉的話文字對比
    在亮底上會不足。
    """
    qt_material.apply_stylesheet(
        app,
        theme=THEME_FILES[theme_name],
        invert_secondary=(theme_name == "light"),
        extra={
            "density_scale": "-1",
            "font_family": "Noto Sans TC",
        },
    )
    extra_qss = EXTRA_QSS_TEMPLATE.format(app_title=FS_TITLE, section_title=FS_SECTION_TITLE)
    app.setStyleSheet(app.styleSheet() + extra_qss)


def style_section_title(label):
    """把一個 QLabel 標記成區塊標題外觀：比一般內文字級大、加粗。"""
    mark_class(label, "section-title")
    return label


def mark_class(widget, class_name):
    """把 widget 標記成 qt-material 的語意樣式類別（"danger"/"warning"/"success"）。

    對應 qt-material 的 QPushButton.danger / .success 這類 QSS 規則：靠 Qt 的
    動態屬性 "class" 選取，設定後要 unpolish()/polish() 讓樣式重新計算一次。
    """
    widget.setProperty("class", class_name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget
