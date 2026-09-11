# iPhone GPS 路線模擬器 - 圖形介面版
# 執行前請確認：
#   1. 系統管理員視窗執行：pymobiledevice3 remote tunneld
#   2. 執行此 App：python gps_app.py

import asyncio
import math
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, filedialog
import customtkinter as ctk
import sys
import json
import os
import re
import ctypes
import xml.etree.ElementTree as ET

FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gps_favorites.json")
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gps_settings.json")

def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_favorites(favs):
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favs, f, ensure_ascii=False, indent=2)

def _kml_tag(elem):
    """去掉 XML namespace，取得元素的原始標籤名稱"""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

def parse_kml_route(path):
    """解析 KML 檔案，取出第一條 LineString 路線座標，
    並用最接近起訖點的 Point 名稱標記備註。
    回傳 (route, doc_name)，route 為 [[緯度, 經度, 備註], ...]，找不到路線時 route 為 None。"""
    tree = ET.parse(path)
    root = tree.getroot()

    doc_name = ""
    for elem in root.iter():
        if _kml_tag(elem) == "name":
            doc_name = (elem.text or "").strip()
            break

    line_points = []
    marker_points = []
    for placemark in root.iter():
        if _kml_tag(placemark) != "Placemark":
            continue
        pname = ""
        for child in placemark.iter():
            if _kml_tag(child) == "name":
                pname = (child.text or "").strip()
                break
        line_string = point_el = None
        for child in placemark.iter():
            ctag = _kml_tag(child)
            if ctag == "LineString" and line_string is None:
                line_string = child
            elif ctag == "Point" and point_el is None:
                point_el = child

        if line_string is not None and not line_points:
            coords_text = ""
            for child in line_string.iter():
                if _kml_tag(child) == "coordinates":
                    coords_text = child.text or ""
                    break
            for token in coords_text.split():
                parts = token.split(",")
                if len(parts) >= 2:
                    lon, lat = float(parts[0]), float(parts[1])
                    line_points.append([lat, lon, ""])
        elif point_el is not None:
            coords_text = ""
            for child in point_el.iter():
                if _kml_tag(child) == "coordinates":
                    coords_text = child.text or ""
                    break
            tokens = coords_text.split()
            if tokens:
                parts = tokens[0].split(",")
                if len(parts) >= 2:
                    lon, lat = float(parts[0]), float(parts[1])
                    marker_points.append((lat, lon, pname))

    if not line_points:
        return None, doc_name

    def nearest_marker_name(lat, lon):
        best_name, best_d = None, 0.0005  # 約 50 公尺內才採用
        for mlat, mlon, mname in marker_points:
            if not mname:
                continue
            d = ((lat - mlat) ** 2 + (lon - mlon) ** 2) ** 0.5
            if d < best_d:
                best_d, best_name = d, mname
        return best_name

    start_name = nearest_marker_name(*line_points[0][:2])
    end_name = nearest_marker_name(*line_points[-1][:2])
    if start_name:
        line_points[0][2] = start_name
    if end_name:
        line_points[-1][2] = end_name

    return line_points, doc_name

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

# ── 視窗位置記憶 ────────────────────
# 視窗幾何（大小 + 座標 + 是否最大化）存在 gps_settings.json 的 "window" 欄位，
# 下次啟動時先把視窗移回上次的座標，再決定要不要最大化——Windows 的「最大化」
# 是相對於視窗當下所在的螢幕，所以只要先把座標擺對，多螢幕環境就會回到上次那一台。
DEFAULT_WINDOW_W = 1500
DEFAULT_WINDOW_H = 820
MIN_WINDOW_W = 560
MIN_WINDOW_H = 360

MONITOR_DEFAULTTONULL = 0

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def point_on_any_monitor(x, y):
    """(x, y)（實體像素）是否落在目前接上的任何一台螢幕內。

    tkinter 的 winfo_screenwidth()/winfo_screenheight() 只回報主螢幕大小，無法判斷
    副螢幕上（甚至是負座標）的位置，所以改用 Win32 的 MonitorFromPoint：帶
    MONITOR_DEFAULTTONULL 時，座標不在任何螢幕上就會回傳 NULL，代表上次那台螢幕
    已經拔掉或解析度變了，還原下去視窗會跑到看不見的地方。
    非 Windows 平台或呼叫失敗時一律當作有效，不因為檢查不了就丟掉使用者的位置。

    注意：CustomTkinter 會呼叫 SetProcessDpiAwareness()，之後 CTk.geometry() 回報的是
    「邏輯像素」，而這個 Win32 API 吃的是實體像素，呼叫端必須先換算（見
    GPSApp._logical_to_physical()）。
    """
    if sys.platform != "win32":
        return True
    try:
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.MonitorFromPoint.argtypes = [_POINT, ctypes.c_ulong]
        return bool(user32.MonitorFromPoint(_POINT(int(x), int(y)), MONITOR_DEFAULTTONULL))
    except Exception:
        return True

# ── 顏色主題（深色 / 淺色）────────────────────
# BG / BG2 / BG3 是三層堆疊背景（主底 → 卡片 → 輸入框／次要按鈕），
# 相鄰兩層的對比度刻意拉到 1.2 以上，否則深色下看不出層級。
# HOVER 是按鈕的滑入色（比 BG3 更亮，深色介面的 hover 應該變亮而非變暗）。
# ACCENT 是主要動作色，DANGER 刻意換成橙色系，避免與 ACCENT 同色而分不出
# 「主要動作」與「破壞性動作」。TEXT_ON_ACCENT 用在亮底色（ACCENT / DANGER）上，
# TEXT_ON_ACCENT2 用在暗底色（ACCENT2 / HOVER）上，兩者不可互換。
# DISABLED_BG / DISABLED_TEXT 是按鈕停用狀態：亮度刻意壓在 BG3（可按的次要按鈕）
# 之下，因為 CTkButton 的 state="disabled" 只會換文字色、不會換背景色。
THEMES = {
    "dark": {
        "BG": "#1D1616", "BG2": "#302323", "BG3": "#4E2F2F",
        "HOVER": "#7E3535",
        "ACCENT": "#D84040", "ACCENT2": "#8E1616",
        "DANGER": "#F0883E",
        "TEXT": "#EEEEEE", "TEXT2": "#B3A5A5",
        "TEXT_ON_ACCENT": "#0A0707", "TEXT_ON_ACCENT2": "#EEEEEE",
        "DISABLED_BG": "#2A2020", "DISABLED_TEXT": "#7A6B6B",
    },
    "light": {
        # BG 比純白的 BG2 深一階，白色卡片才浮得起來；BG3 又比 BG 更深，
        # 讓次要按鈕/表格底在淺色底上仍看得出輪廓。
        "BG": "#E3F5EF", "BG2": "#ffffff", "BG3": "#C9E2D9",
        "HOVER": "#99C0C9",
        # ACCENT / ACCENT2 / DANGER 都刻意壓深：中亮度色配近白字必然低對比，
        # 壓深後白字才過 AA，同時在白色卡片上也有足夠輪廓。
        "ACCENT": "#2A72A3", "ACCENT2": "#27A55F",
        "DANGER": "#B8242A",
        "TEXT": "#272727", "TEXT2": "#5c5c5c",
        "TEXT_ON_ACCENT": "#EFFFFB", "TEXT_ON_ACCENT2": "#272727",
        "DISABLED_BG": "#D2D2D2", "DISABLED_TEXT": "#858585",
    },
}

def _pair(key):
    """把 THEMES 的同名色票組成 CustomTkinter 的 (淺色, 深色) tuple。

    CTk 的每個顏色參數都接受這種 tuple，並在 set_appearance_mode() 時自己挑對應
    的那一個重畫——這是整份 UI 不需要銷毀重建就能換主題的關鍵。順序固定為
    (light, dark)，不可對調。
    """
    return (THEMES["light"][key], THEMES["dark"][key])

BG, BG2, BG3 = _pair("BG"), _pair("BG2"), _pair("BG3")
HOVER = _pair("HOVER")
ACCENT, ACCENT2 = _pair("ACCENT"), _pair("ACCENT2")
DANGER = _pair("DANGER")
TEXT, TEXT2 = _pair("TEXT"), _pair("TEXT2")
TEXT_ON_ACCENT, TEXT_ON_ACCENT2 = _pair("TEXT_ON_ACCENT"), _pair("TEXT_ON_ACCENT2")
DISABLED_BG, DISABLED_TEXT = _pair("DISABLED_BG"), _pair("DISABLED_TEXT")

# ── 外觀常數 ────────────────────
CARD_RADIUS = 10
BTN_RADIUS = 8
FONT = "Segoe UI"
FONT_MONO = "Consolas"
FONT_EMOJI = "Segoe UI Emoji"

# 字級。全部集中在這裡，不要在 widget 裡直接寫數字。
# 下限刻意訂在 FS_XS=10pt：中文字在 11px 以下筆畫會糊在一起，
# 舊版用到的 8pt/9pt 對拉丁字母還能看，中文則完全不行。
FS_XS = 10        # 表格列、列內小按鈕
FS_SM = 11        # 次要說明文字、預設值按鈕
FS_MD = 12        # 一般標籤
FS_LG = 13        # 面板標題
FS_XL = 15        # 主要控制按鈕
FS_TITLE = 22     # App 標題
FS_EMOJI = 12     # 列內圖示
FS_EMOJI_LG = 30  # 標題列圖示

# 整體介面放大倍率。CustomTkinter 的 widget scaling 會同時放大字級與 widget 尺寸，
# 所以調這一個值就能整體再微調大小，不必逐一改上面的字級。
# 只影響 widget，不影響視窗幾何（那是 window scaling，兩者獨立）。
UI_SCALE = 1.15

# 按鈕配色組合。hover_color 一定要明確給值：CTkButton 在沒指定時會套用
# CustomTkinter 預設主題（藍色系）的 hover 色，與本 App 的色票完全不搭。
BTN_PRIMARY = {"fg_color": ACCENT, "text_color": TEXT_ON_ACCENT, "hover_color": HOVER}
BTN_SECONDARY = {"fg_color": BG3, "text_color": TEXT2, "hover_color": HOVER}
BTN_SUCCESS = {"fg_color": ACCENT2, "text_color": TEXT_ON_ACCENT2, "hover_color": HOVER}
BTN_STOP = {"fg_color": DANGER, "text_color": TEXT_ON_ACCENT, "hover_color": HOVER}

def make_card(parent, padx=20, pady=14, fg_color=BG2):
    """建立一張卡片，回傳 (外框, 內容框)。

    CTkFrame 沒有 tk.Frame 的 padx/pady 內距參數，所以用一層透明內框把內距做出來。
    外框負責 pack()/pack_forget()（模式切換用），子 widget 一律放進內容框。
    """
    outer = ctk.CTkFrame(parent, fg_color=fg_color, corner_radius=CARD_RADIUS)
    inner = ctk.CTkFrame(outer, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=padx, pady=pady)
    return outer, inner

def icon_for(fav):
    """最愛項目的類型圖示。"""
    return "📌" if fav["type"] == "pin" else "🗺"

_FONT_CACHE = {}

def measure_font(font):
    """取得可量測文字寬度的 tkfont.Font（依 font tuple 快取）。

    用未縮放的字級建立，量出來的寬度就是 widget 單位，可以直接跟
    _physical_to_widget_units() 的結果比較。
    """
    if font not in _FONT_CACHE:
        weight = "bold" if len(font) > 2 and font[2] == "bold" else "normal"
        _FONT_CACHE[font] = tkfont.Font(family=font[0], size=font[1], weight=weight)
    return _FONT_CACHE[font]

def elide_to_width(text, font, max_units):
    """把 text 裁到 max_units（widget 單位）以內，被裁掉時尾端補「…」。

    單純讓文字在容器裡被切掉會斷在字的中間，看起來像顯示錯誤；補上省略號
    才看得出來是「後面還有」。用二分搜尋找最長的可容納前綴。
    """
    f = measure_font(font)
    if max_units <= 0 or f.measure(text) <= max_units:
        return text
    ellipsis_w = f.measure("…")
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if f.measure(text[:mid]) + ellipsis_w <= max_units:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"

def set_scrollbar_visibility(scrollable_frame):
    """內容高度塞得下時隱藏捲軸，塞不下才顯示。

    CTkScrollableFrame 的捲軸是在 _create_grid() 裡無條件 grid() 的，沒有自動隱藏
    機制，只能自己動它。這裡刻意碰了 _scrollbar / _parent_canvas 兩個私有屬性，
    是與 CustomTkinter 內部實作耦合的已知風險點；用 getattr + try 包住，萬一未來
    版本改名也只是退回「捲軸固定顯示」，不會讓整個 UI 壞掉。
    """
    scrollbar = getattr(scrollable_frame, "_scrollbar", None)
    canvas = getattr(scrollable_frame, "_parent_canvas", None)
    if scrollbar is None or canvas is None:
        return
    try:
        if canvas.yview() == (0.0, 1.0):
            scrollbar.grid_remove()
        else:
            scrollbar.grid()
    except Exception:
        pass

# ─────────────────────────────────────────────

WIDE_LAYOUT_BREAKPOINT = 1000
ROUTE_TABLE_MAX_ROWS = 15

# 路線表格是虛擬化清單：不論路線有幾個點，都只建立這麼多個列 widget，
# 捲動時把它們重新綁到不同的資料索引（見 GPSApp._render_route_window）。
# 多備 2 列是為了捲到一半時上下邊緣不會露空。
# 一個 CTk widget 約 3ms，446 個點若每列都建就是 2230 個 widget、8 秒；
# 虛擬化之後固定只建 17 列，載入時間與路線長度無關。
ROUTE_ROW_POOL = ROUTE_TABLE_MAX_ROWS + 2

# 路線表格的欄寬（像素）。CTkLabel / CTkEntry 的 width 是像素而非字元數，
# 表頭與每一列必須共用同一組數值才對得齊。
ROUTE_COL_INDEX_W = 34
ROUTE_COL_COORD_W = 96
ROUTE_COL_DEL_W = 44

# 最愛列表的欄寬（像素）與列高。名稱欄會吃掉剩餘寬度，其餘欄位一律固定，
# 這樣名稱再長也不會把「載入」「✕」擠變形。
FAV_ROW_H = 28
FAV_COL_ICON_W = 26
FAV_COL_NAME_MIN_W = 80
FAV_COL_PREVIEW_W = 120
FAV_COL_DEL_W = 30

# 執行日誌高度 = 視窗高度 40% 再扣掉這麼多行。
LOG_SHRINK_LINES = 3

DEFAULT_ROUTE = [
    (24.1368, 120.6862, "台中火車站"),
    (24.1390, 120.6800, "台灣大道一段"),
    (24.1420, 120.6720, "台灣大道二段"),
    (24.1470, 120.6640, "台灣大道三段"),
    (24.1520, 120.6560, "台灣大道四段"),
    (24.1560, 120.6480, "近市政府"),
    (24.1590, 120.6430, "勤美誠品"),
]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def interpolate_points(route, speed_ms, interval_sec):
    points = []
    for i in range(len(route) - 1):
        lat1, lon1 = route[i][0], route[i][1]
        lat2, lon2 = route[i+1][0], route[i+1][1]
        dist = haversine(lat1, lon1, lat2, lon2)
        steps = max(1, int(dist / (speed_ms * interval_sec)))
        for s in range(steps):
            t = s / steps
            points.append((lat1 + (lat2-lat1)*t, lon1 + (lon2-lon1)*t))
    points.append((route[-1][0], route[-1][1]))
    return points

class GPSApp(ctk.CTk):
    def __init__(self):
        # 外觀模式要在建立視窗前就定案：CTk.__init__() 會依當下的模式決定
        # Windows 標題列要用深色還是淺色。
        settings = load_settings()
        theme_name = settings.get("theme", "dark")
        if theme_name not in THEMES:
            theme_name = "dark"
        ctk.set_appearance_mode(theme_name)
        ctk.set_widget_scaling(UI_SCALE)

        super().__init__(fg_color=BG)
        self.theme_name = theme_name
        self.settings = settings

        self.title("iPhone GPS 路線模擬器")
        self.resizable(True, True)
        self.minsize(MIN_WINDOW_W, MIN_WINDOW_H)

        # 視窗幾何要在建立任何內容前就定案，否則會先閃一下預設位置再跳走。
        self._restore_window_geometry()

        # 定位模擬連線是「長連線」：只要連上裝置，就算按停止／返回也不會斷線，
        # 只有明確按「恢復真實定位」才會真的中斷連線（中斷當下裝置會自動恢復真實 GPS）。
        self.session_thread = None
        self.session_active = False
        self.pending_action = "pause"  # "forward" | "reverse" | "pause" | "disconnect"
        self.point_idx = 0
        self.route = [list(r) for r in DEFAULT_ROUTE]
        self.mode = tk.StringVar(value="route")
        self.favorites = load_favorites()
        self._layout_wide = None
        self._log_line_h = None
        # 路線表格虛擬化用的狀態
        self._route_rows = []           # 可重複使用的列 widget
        self._route_row_h = None        # 單列高度（實體像素），量一次就快取
        self._route_rebinding = False   # 換綁資料時擋掉 Entry 的 write callback
        self._route_rendering = False   # 防止 place() 觸發的捲動事件遞迴

        self._build_scroll_container()
        self._build_ui()
        self._apply_responsive_layout(self._start_width)
        # 一定要 add="+"：CTk.__init__() 自己也綁了 <Configure>（_update_dimensions_event）
        # 來追蹤視窗尺寸，不加就會把它蓋掉。
        self.bind("<Configure>", self._remember_window_geometry, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # 先讓視窗以一般大小完成第一次繪製，再最大化：一方面避免最大化動畫途中
        # 內容尚未畫出而露出空白背景，另一方面在真正變成最大化尺寸後，強制把
        # 捲動位置重新校正到最上方，避免出現「明明沒往下捲，卻可以往上捲出空白」
        # 的殘留捲動位移。
        self.after(10, self._settle_window_and_reset_scroll)

    # ── 視窗幾何：還原 / 記錄 / 存檔 ────────────────────
    def _logical_to_physical(self, value):
        """把 CTk 的邏輯像素換算成 Win32 API 要的實體像素。

        CustomTkinter 開啟了 DPI awareness，CTk.geometry() 取得/設定的都是邏輯像素；
        MonitorFromPoint 吃的是實體像素。螢幕縮放 100% 時係數為 1，兩者相同。
        """
        try:
            return int(value * ctk.ScalingTracker.get_window_scaling(self))
        except Exception:
            return int(value)

    def _restore_window_geometry(self):
        win = self.settings.get("window") or {}
        w, h = win.get("width"), win.get("height")
        x, y = win.get("x"), win.get("y")
        # 找不到設定（第一次啟動）時維持舊行為：主螢幕、最大化。
        self._start_maximized = bool(win.get("maximized", True))
        if not isinstance(w, int) or not isinstance(h, int) or w < MIN_WINDOW_W or h < MIN_WINDOW_H:
            w, h = DEFAULT_WINDOW_W, DEFAULT_WINDOW_H
        # 拿標題列中間的點去問「這個位置還在哪台螢幕上」，比左上角不容易壓在螢幕邊界上。
        on_monitor = (isinstance(x, int) and isinstance(y, int)
                      and point_on_any_monitor(self._logical_to_physical(x + w // 2),
                                               self._logical_to_physical(y + 15)))
        if on_monitor:
            self.geometry(f"{w}x{h}+{x}+{y}")
        else:
            x = y = None
            self.geometry(f"{w}x{h}")
        self._start_width = w
        self._saved_window = {"width": w, "height": h, "x": x, "y": y,
                              "maximized": self._start_maximized}

    def _remember_window_geometry(self, event):
        # 根視窗的 bindtag 在每個子 widget 上都有，子 widget 的 <Configure> 也會打到這裡。
        if event.widget is not self:
            return
        state = self.state()
        self._saved_window["maximized"] = (state == "zoomed")
        if state != "normal":
            # 最大化／最小化時的座標（例如 -8, -8）不能拿來當下次的還原基準。
            return
        # 用 geometry() 字串而不是 winfo_x()/winfo_y()：後者回傳的是客戶區位置，跟
        # geometry() 設定時用的外框座標差一個標題列高度，存還一次就會往下漂移一次。
        m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", self.geometry())
        if not m:
            return
        w, h, x, y = (int(v) for v in m.groups())
        if w < MIN_WINDOW_W or h < MIN_WINDOW_H:
            # 視窗真正畫出來之前的 1x1 過渡狀態，不要記下來。
            return
        self._saved_window.update({"width": w, "height": h, "x": x, "y": y})

    def _save_window_geometry(self):
        win = {"width": self._saved_window["width"],
               "height": self._saved_window["height"],
               "maximized": self._saved_window["maximized"]}
        if isinstance(self._saved_window["x"], int) and isinstance(self._saved_window["y"], int):
            win["x"] = self._saved_window["x"]
            win["y"] = self._saved_window["y"]
        self.settings["window"] = win
        save_settings(self.settings)

    def _on_close(self):
        try:
            self._save_window_geometry()
        except Exception:
            pass
        self.destroy()

    def _settle_window_and_reset_scroll(self):
        if self._start_maximized:
            self.state("zoomed")
        self.update_idletasks()
        canvas = getattr(self.scroll_frame, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0)
        self._update_scrollbar_visibility()
        self._update_log_height()
        self._update_route_table_height()

    def _update_scrollbar_visibility(self):
        set_scrollbar_visibility(self.scroll_frame)

    def _physical_to_widget_units(self, pixels):
        """把實際螢幕像素換算回 CTk 的 width/height 參數單位。

        CTk 的 width/height 會先乘上 widget scaling 才套到底層 widget，但
        winfo_reqheight() 與 <Configure> 的 event.height 拿到的已經是縮放後的
        實際像素。直接把後者餵回 configure(height=...) 會被二次縮放，UI_SCALE
        或螢幕 DPI 不是 1 時就會明顯過高。
        """
        try:
            scaling = ctk.ScalingTracker.get_widget_scaling(self)
        except Exception:
            scaling = 1.0
        return pixels / scaling if scaling else pixels

    def _log_line_height(self):
        """日誌字型一行的高度（widget 單位）。

        用未縮放的字級去問 Tk，拿到的就是 widget 單位的行高，可以直接跟
        configure(height=...) 的數值相加減。量一次就快取，不必每次 resize 重算。
        """
        if self._log_line_h is None:
            self._log_line_h = tkfont.Font(family=FONT_MONO,
                                           size=FS_SM).metrics("linespace")
        return self._log_line_h

    def _update_log_height(self, window_height=None):
        if not hasattr(self, "log"):
            return
        if window_height is None:
            window_height = self.container.winfo_height()
        target = self._physical_to_widget_units(window_height * 0.4)
        target -= LOG_SHRINK_LINES * self._log_line_height()
        self.log.configure(height=max(80, int(target)))

    def _build_scroll_container(self):
        """建立整個視窗的可捲動容器。

        CTkScrollableFrame 已內建 Canvas + 捲軸 + 滾輪事件（含巢狀捲動判定：游標在
        路線表格那層時只捲內層），所以舊版那一整套手刻 Canvas 管線都不需要了。
        """
        self.container = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.container.pack(fill="both", expand=True)
        self.container.bind("<Configure>", self._on_container_configure)

        self.scroll_frame = ctk.CTkScrollableFrame(self.container, fg_color=BG,
                                                   corner_radius=0)
        self.scroll_frame.pack(fill="both", expand=True)

    def _on_container_configure(self, event):
        self._update_log_height(event.height)
        self._apply_responsive_layout(event.width)
        self._update_scrollbar_visibility()

    def _apply_responsive_layout(self, width):
        if not hasattr(self, "left_col"):
            return
        wide = width > WIDE_LAYOUT_BREAKPOINT
        if wide == self._layout_wide:
            return
        self._layout_wide = wide
        self.left_col.grid_forget()
        self.right_col.grid_forget()
        if wide:
            self.left_col.grid(row=0, column=0, sticky="new", padx=(24, 12))
            self.right_col.grid(row=0, column=1, sticky="new", padx=(12, 24))
        else:
            self.left_col.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24)
            self.right_col.grid(row=1, column=0, columnspan=2, sticky="ew", padx=24)

    def _theme_btn_text(self):
        return "☀  切換淺色" if self.theme_name == "dark" else "🌙  切換深色"

    def _toggle_theme(self):
        """切換深色／淺色。

        所有 widget 的顏色都是 (淺色, 深色) tuple，set_appearance_mode() 會讓
        CustomTkinter 自己把每個已建立的 widget 重畫成另一組色，因此不需要像
        舊版那樣銷毀重建整個 UI，也就不必暫存／還原使用者正在輸入的欄位。
        """
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        ctk.set_appearance_mode(self.theme_name)
        self.theme_btn.configure(text=self._theme_btn_text())
        self.settings["theme"] = self.theme_name
        # 不直接 save_settings()：那樣寫回去的 "window" 會是啟動時讀進來的舊值，
        # 改呼叫 _save_window_geometry() 順手把目前的視窗位置一起存下去。
        self._save_window_geometry()

    def _build_ui(self):
        # ── 標題 ──
        title_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        title_frame.pack(fill="x", padx=30, pady=20)

        ctk.CTkLabel(title_frame, text="📍", font=(FONT_EMOJI, FS_EMOJI_LG),
                     text_color=ACCENT, fg_color="transparent").pack(side="left")
        title_col = ctk.CTkFrame(title_frame, fg_color="transparent")
        title_col.pack(side="left", padx=12)
        ctk.CTkLabel(title_col, text="GPS 路線模擬器",
                     font=(FONT, FS_TITLE, "bold"), text_color=TEXT,
                     fg_color="transparent").pack(anchor="w")
        ctk.CTkLabel(title_col, text="iPhone iOS 26  ·  需先執行 tunneld",
                     font=(FONT, FS_MD), text_color=TEXT2,
                     fg_color="transparent").pack(anchor="w")

        self.theme_btn = ctk.CTkButton(title_frame, text=self._theme_btn_text(),
                                       font=(FONT, FS_MD, "bold"),
                                       fg_color=BG3, text_color=TEXT, hover_color=HOVER,
                                       corner_radius=BTN_RADIUS,
                                       width=1, height=34, border_spacing=12,
                                       command=self._toggle_theme)
        self.theme_btn.pack(side="right", padx=(0, 4))

        # ── 內容分欄（>1000px 寬時左右並排且等寬，否則上下堆疊）──
        columns_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        columns_frame.pack(fill="both", expand=True)
        columns_frame.columnconfigure(0, weight=1, uniform="cols")
        columns_frame.columnconfigure(1, weight=1, uniform="cols")

        self.left_col = ctk.CTkFrame(columns_frame, fg_color="transparent")
        self.right_col = ctk.CTkFrame(columns_frame, fg_color="transparent")

        # ── 控制按鈕（左欄，三顆按鈕等寬並填滿整列）──
        btn_frame = ctk.CTkFrame(self.left_col, fg_color="transparent")
        btn_frame.pack(fill="x", pady=8)
        btn_frame.columnconfigure(0, weight=1, uniform="ctrl_btns")
        btn_frame.columnconfigure(1, weight=1, uniform="ctrl_btns")
        btn_frame.columnconfigure(2, weight=1, uniform="ctrl_btns")

        self.start_btn = ctk.CTkButton(btn_frame, text="▶  開始模擬",
                                       font=(FONT, FS_XL, "bold"), **BTN_PRIMARY,
                                       corner_radius=BTN_RADIUS, width=1, height=48,
                                       command=self._start)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.return_btn = ctk.CTkButton(btn_frame, text="↩  返回",
                                        font=(FONT, FS_XL, "bold"),
                                        fg_color=BG3, text_color=TEXT, hover_color=HOVER,
                                        corner_radius=BTN_RADIUS, width=1, height=48,
                                        command=self._reverse)
        self.return_btn.grid(row=0, column=1, sticky="ew", padx=4)

        self.stop_btn = ctk.CTkButton(btn_frame, text="⏹  停止",
                                      font=(FONT, FS_XL, "bold"), **BTN_STOP,
                                      corner_radius=BTN_RADIUS, width=1, height=48,
                                      command=self._stop)
        self.stop_btn.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # ── 恢復真實定位（獨立按鈕，與開始/返回/停止的流程無關）──
        self.restore_btn = ctk.CTkButton(self.left_col, text="🛰  恢復真實定位",
                                         font=(FONT, FS_MD, "bold"), **BTN_SECONDARY,
                                         corner_radius=BTN_RADIUS, width=1, height=36,
                                         command=self._restore_real_location)
        self.restore_btn.pack(fill="x", pady=(0, 4))

        # 登記每顆控制按鈕「啟用時」該用的顏色，_set_btn_enabled() 會據此還原；
        # 停用時的背景／文字色則統一由 DISABLED_BG / DISABLED_TEXT 決定。
        for btn, on_bg, on_fg in (
            (self.start_btn, ACCENT, TEXT_ON_ACCENT),
            (self.return_btn, BG3, TEXT),
            (self.stop_btn, DANGER, TEXT_ON_ACCENT),
            (self.restore_btn, BG3, TEXT2),
        ):
            btn.enabled_bg, btn.enabled_fg = on_bg, on_fg
        self._sync_btn_states()

        # ── 進度條（左欄）──
        # CTkProgressBar 的值域是 0~1（不是百分比），progress_var 一律存小數。
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ctk.CTkProgressBar(self.left_col, variable=self.progress_var,
                                               height=8, corner_radius=4,
                                               fg_color=BG3, progress_color=ACCENT)
        self.progress_bar.pack(fill="x", pady=8)

        self.progress_label = ctk.CTkLabel(self.left_col, text="",
                                           font=(FONT, FS_MD), text_color=TEXT2,
                                           fg_color="transparent")
        self.progress_label.pack()

        # ── 日誌（左欄，高度固定為視窗高度的 40%）──
        ctk.CTkLabel(self.left_col, text="執行日誌", font=(FONT, FS_MD, "bold"),
                     text_color=TEXT2, fg_color="transparent").pack(anchor="w", pady=(12, 2))
        self.log = ctk.CTkTextbox(self.left_col, font=(FONT_MONO, FS_SM),
                                  fg_color=BG2, text_color=TEXT2,
                                  corner_radius=CARD_RADIUS, state="disabled")
        self.log.pack(fill="x", pady=(0, 20))
        self._update_log_height()

        # ── 最愛地點面板（左欄）──
        fav_card, self.fav_frame = make_card(self.left_col, padx=20, pady=14)
        fav_card.pack(fill="x", pady=(0, 8))

        fav_title_row = ctk.CTkFrame(self.fav_frame, fg_color="transparent")
        fav_title_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(fav_title_row, text="⭐ 最愛地點",
                     font=(FONT, FS_LG, "bold"), text_color=TEXT,
                     fg_color="transparent").pack(side="left")

        # 儲存目前定位按鈕
        ctk.CTkButton(fav_title_row, text="＋ 儲存目前座標",
                      font=(FONT, FS_SM), **BTN_SUCCESS,
                      corner_radius=BTN_RADIUS, width=1, height=26, border_spacing=8,
                      command=self._save_current_pin_as_fav).pack(side="right", padx=(4, 0))

        ctk.CTkButton(fav_title_row, text="＋ 儲存目前路線",
                      font=(FONT, FS_SM), **BTN_SECONDARY,
                      corner_radius=BTN_RADIUS, width=1, height=26, border_spacing=8,
                      command=self._save_current_route_as_fav).pack(side="right", padx=4)

        # 匯入 KML 檔案產生路線最愛按鈕
        ctk.CTkButton(fav_title_row, text="＋ 匯入 KML 路線",
                      font=(FONT, FS_SM), **BTN_SECONDARY,
                      corner_radius=BTN_RADIUS, width=1, height=26, border_spacing=8,
                      command=self._import_kml_as_fav).pack(side="right", padx=4)

        # 最愛列表
        self.fav_list_frame = ctk.CTkFrame(self.fav_frame, fg_color="transparent")
        self.fav_list_frame.pack(fill="x")
        self._refresh_fav_list()

        # ── 模式切換（右欄）──
        mode_card, mode_frame = make_card(self.right_col, padx=20, pady=12)
        mode_card.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(mode_frame, text="模式選擇", font=(FONT, FS_LG, "bold"),
                     text_color=TEXT, fg_color="transparent").pack(side="left", padx=(0, 16))

        self.route_mode_btn = ctk.CTkButton(mode_frame, text="🗺  路線移動",
                                            font=(FONT, FS_MD, "bold"), **BTN_PRIMARY,
                                            corner_radius=BTN_RADIUS,
                                            width=1, height=32, border_spacing=14,
                                            command=lambda: self._switch_mode("route"))
        self.route_mode_btn.pack(side="left", padx=4)

        self.pin_mode_btn = ctk.CTkButton(mode_frame, text="📌  固定定位",
                                          font=(FONT, FS_MD, "bold"), **BTN_SECONDARY,
                                          corner_radius=BTN_RADIUS,
                                          width=1, height=32, border_spacing=14,
                                          command=lambda: self._switch_mode("pin"))
        self.pin_mode_btn.pack(side="left", padx=4)

        # ── 固定定位面板（預設隱藏，右欄）──
        self.pin_frame, pin_body = make_card(self.right_col, padx=20, pady=16)

        ctk.CTkLabel(pin_body, text="固定座標",
                     font=(FONT, FS_LG, "bold"), text_color=TEXT,
                     fg_color="transparent").grid(row=0, column=0, columnspan=4,
                                                  sticky="w", pady=(0, 10))

        ctk.CTkLabel(pin_body, text="緯度：", font=(FONT, FS_MD),
                     text_color=TEXT2, fg_color="transparent").grid(row=1, column=0, sticky="w")
        self.pin_lat = tk.StringVar(value="24.1368")
        ctk.CTkEntry(pin_body, textvariable=self.pin_lat, width=140, height=30,
                     font=(FONT, FS_LG), fg_color=BG3, text_color=TEXT,
                     border_width=0, corner_radius=6).grid(row=1, column=1, padx=8)

        ctk.CTkLabel(pin_body, text="經度：", font=(FONT, FS_MD),
                     text_color=TEXT2, fg_color="transparent").grid(row=1, column=2, sticky="w")
        self.pin_lon = tk.StringVar(value="120.6862")
        ctk.CTkEntry(pin_body, textvariable=self.pin_lon, width=140, height=30,
                     font=(FONT, FS_LG), fg_color=BG3, text_color=TEXT,
                     border_width=0, corner_radius=6).grid(row=1, column=3, padx=8)

        # 預設地點快速選擇
        ctk.CTkLabel(pin_body, text="快速選擇：", font=(FONT, FS_SM),
                     text_color=TEXT2, fg_color="transparent").grid(
                     row=2, column=0, columnspan=4, sticky="w", pady=(12, 4))

        pin_presets_btns = ctk.CTkFrame(pin_body, fg_color="transparent")
        pin_presets_btns.grid(row=3, column=0, columnspan=4, sticky="w")
        pin_presets = [
            ("台中火車站", 24.1368, 120.6862),
            ("台北101",   25.0338, 121.5645),
            ("高雄85大樓", 22.6155, 120.3025),
            ("台南孔廟",   22.9969, 120.2008),
        ]
        for name, lat, lon in pin_presets:
            ctk.CTkButton(pin_presets_btns, text=name, font=(FONT, FS_SM),
                          **BTN_SECONDARY, corner_radius=BTN_RADIUS,
                          width=1, height=28, border_spacing=8,
                          command=lambda la=lat, lo=lon: (
                              self.pin_lat.set(str(la)),
                              self.pin_lon.set(str(lo))
                          )).pack(side="left", padx=4)

        # ── 速度設定 ──
        self.speed_frame_ref, speed_frame = make_card(self.right_col, padx=20, pady=16)
        self.speed_frame_ref.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(speed_frame, text="移動速度", font=(FONT, FS_LG, "bold"),
                     text_color=TEXT, fg_color="transparent").grid(row=0, column=0, sticky="w")

        self.speed_var = tk.DoubleVar(value=20.0)
        presets = [("步行 5 km/h", 5), ("慢跑 10 km/h", 10),
                   ("騎車 20 km/h", 20), ("開車 40 km/h", 40)]

        preset_frame = ctk.CTkFrame(speed_frame, fg_color="transparent")
        preset_frame.grid(row=1, column=0, sticky="w", pady=8)
        for label, val in presets:
            ctk.CTkButton(preset_frame, text=label, font=(FONT, FS_SM),
                          **BTN_SECONDARY, corner_radius=BTN_RADIUS,
                          width=1, height=28, border_spacing=8,
                          command=lambda v=val: self._set_speed(v)).pack(side="left", padx=4)

        speed_row = ctk.CTkFrame(speed_frame, fg_color="transparent")
        speed_row.grid(row=2, column=0, sticky="w")
        ctk.CTkLabel(speed_row, text="自訂 km/h：", font=(FONT, FS_MD),
                     text_color=TEXT2, fg_color="transparent").pack(side="left")
        self.speed_entry = ctk.CTkEntry(speed_row, textvariable=self.speed_var,
                                        width=80, height=30, font=(FONT, FS_LG),
                                        fg_color=BG3, text_color=TEXT,
                                        border_width=0, corner_radius=6)
        self.speed_entry.pack(side="left", padx=6)

        self.loop_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(speed_row, text="循環模式（來回）",
                        variable=self.loop_var,
                        font=(FONT, FS_MD), text_color=TEXT2,
                        fg_color=ACCENT, hover_color=HOVER,
                        border_color=BG3, checkmark_color=TEXT_ON_ACCENT,
                        checkbox_width=18, checkbox_height=18,
                        corner_radius=4).pack(side="left", padx=16)

        # ── 路線點 ──
        self.route_section = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.route_section.pack(fill="x")

        route_label_frame = ctk.CTkFrame(self.route_section, fg_color="transparent")
        route_label_frame.pack(fill="x", pady=(4, 4))
        ctk.CTkLabel(route_label_frame, text="路線座標點",
                     font=(FONT, FS_LG, "bold"), text_color=TEXT,
                     fg_color="transparent").pack(side="left")
        ctk.CTkButton(route_label_frame, text="🗑 清空座標點", font=(FONT, FS_SM),
                      **BTN_SECONDARY, corner_radius=BTN_RADIUS,
                      width=1, height=24, border_spacing=8,
                      command=self._clear_route_points).pack(side="right")
        ctk.CTkButton(route_label_frame, text="＋ 新增點", font=(FONT, FS_SM),
                      **BTN_SUCCESS, corner_radius=BTN_RADIUS,
                      width=1, height=24, border_spacing=8,
                      command=self._add_point).pack(side="right", padx=4)
        # 距離/時間資訊：與「＋ 新增點」同一列
        self.info_label = ctk.CTkLabel(route_label_frame, text="",
                                       font=(FONT, FS_MD), text_color=TEXT2,
                                       fg_color="transparent")
        self.info_label.pack(side="left", padx=(16, 0))

        # 路線表格表頭
        cols_frame = ctk.CTkFrame(self.route_section, fg_color=BG3, corner_radius=0)
        cols_frame.pack(fill="x")
        header_cols = [("#", ROUTE_COL_INDEX_W, False), ("緯度", ROUTE_COL_COORD_W, False),
                       ("經度", ROUTE_COL_COORD_W, False), ("備註", ROUTE_COL_COORD_W, True),
                       ("", ROUTE_COL_DEL_W, False)]
        for txt, w, exp in header_cols:
            ctk.CTkLabel(cols_frame, text=txt, font=(FONT, FS_SM),
                         text_color=TEXT2, fg_color="transparent",
                         width=w, height=24, anchor="w").pack(side="left", fill="x",
                                                              expand=exp, padx=(6, 0))

        # 表格內容區：獨立的內層 CTkScrollableFrame，最多顯示 ROUTE_TABLE_MAX_ROWS 列。
        # CustomTkinter 的滾輪處理會自己判斷游標在哪一層（_check_if_valid_scroll 比對
        # _parent_canvas），所以巢狀捲動不需要像舊版那樣手動分派事件。
        self.route_container = ctk.CTkScrollableFrame(self.route_section,
                                                      fg_color=BG2, corner_radius=0)
        self.route_container.pack(fill="x")

        # 列是用 place() 疊上去的，place 不會把容器撐高，所以放一個看不見的
        # 墊片來決定內容總高度（＝捲動範圍），高度由 _refresh_route_rows() 更新。
        self._route_spacer = ctk.CTkFrame(self.route_container,
                                          fg_color="transparent", height=1)
        self._route_spacer.pack(fill="x")
        self._install_route_scroll_hook()

        self._refresh_route_rows()
        self._update_info()
        self._update_return_btn_state()

    def _switch_mode(self, mode):
        self.mode.set(mode)
        if mode == "route":
            self.route_mode_btn.configure(**BTN_PRIMARY)
            self.pin_mode_btn.configure(**BTN_SECONDARY)
            self.pin_frame.pack_forget()
            self.speed_frame_ref.pack(fill="x", pady=(0, 12))
            self.route_section.pack(fill="x")
            self.start_btn.configure(text="▶  開始模擬")
        else:
            self.pin_mode_btn.configure(**BTN_SUCCESS)
            self.route_mode_btn.configure(**BTN_SECONDARY)
            self.speed_frame_ref.pack_forget()
            self.route_section.pack_forget()
            self.pin_frame.pack(fill="x", pady=(0, 8))
            self.start_btn.configure(text="📌  固定定位")
        self._update_return_btn_state()

    def _set_btn_enabled(self, btn, enabled):
        """切換控制按鈕的可用狀態（含背景色）。

        CTkButton 的 state="disabled" 只會把文字換成 text_color_disabled，背景色
        完全不動，所以停用中的「停止」仍是滿版 DANGER 底，看起來比真正可按的
        按鈕更醒目。這裡連背景一起換掉，讓停用狀態退到 BG3 之下，並關掉 hover
        （停用的按鈕不該對滑鼠有反應）。
        """
        if enabled:
            btn.configure(state="normal", fg_color=btn.enabled_bg,
                          text_color=btn.enabled_fg, hover=True)
        else:
            btn.configure(state="disabled", fg_color=DISABLED_BG,
                          text_color=DISABLED_TEXT, text_color_disabled=DISABLED_TEXT,
                          hover=False)

    def _sync_btn_states(self):
        """由 pending_action / mode 推導四顆控制按鈕的可用性。"""
        busy = self.pending_action in ("forward", "reverse", "disconnect")
        self._set_btn_enabled(self.start_btn, not busy)
        self._set_btn_enabled(self.stop_btn,
                              self.pending_action in ("forward", "reverse"))
        self._set_btn_enabled(self.restore_btn, not busy)
        self._update_return_btn_state()

    def _update_return_btn_state(self):
        enabled = (self.mode.get() == "route"
                   and self.pending_action not in ("reverse", "disconnect"))
        self._set_btn_enabled(self.return_btn, enabled)

    def _fixed_cell(self, parent, width):
        """建立寬度不隨內容改變的欄位容器。

        CTkLabel 會依文字長度自動撐寬，直接放進一列裡時，過長的文字會把同一列
        其他欄位擠掉（最愛名稱太長時「載入」「✕」被壓變形就是這樣來的）。
        包一層 pack_propagate(False) 的容器後，內容過長只會在容器內被裁切，
        其他欄位的寬度不受影響。
        """
        cell = ctk.CTkFrame(parent, fg_color="transparent",
                            width=width, height=FAV_ROW_H)
        cell.pack_propagate(False)
        return cell

    def _bind_elide(self, cell, label, full_text, font):
        """讓 label 的文字隨欄位寬度自動截斷加省略號。

        名稱欄的寬度會跟著視窗寬度變，所以不能只在建立時算一次；綁在欄位容器
        自己的 <Configure> 上，只有該欄真的改變寬度時才重算。
        """
        def on_configure(event):
            avail = self._physical_to_widget_units(event.width) - 4  # 留一點右邊界
            label.configure(text=elide_to_width(full_text, font, avail))
        cell.bind("<Configure>", on_configure)

    def _refresh_fav_list(self):
        for w in self.fav_list_frame.winfo_children():
            w.destroy()
        if not self.favorites:
            ctk.CTkLabel(self.fav_list_frame, text="尚無儲存的最愛地點",
                         font=(FONT, FS_SM), text_color=TEXT2,
                         fg_color="transparent", height=24).pack(anchor="w")
            return
        for i, fav in enumerate(self.favorites):
            row_color = BG3 if i % 2 == 0 else BG2
            row = ctk.CTkFrame(self.fav_list_frame, fg_color=row_color,
                               corner_radius=6, height=FAV_ROW_H)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)  # 列高固定，不被內容撐高

            # 右側欄位先 pack：pack 是先到先分配空間，先放的一定拿得到自己的寬度，
            # 名稱再長也只能吃剩下的，不會把「載入」「✕」擠變形。
            ctk.CTkButton(row, text="✕", font=(FONT, FS_XS),
                          fg_color="transparent", text_color=DANGER, hover_color=HOVER,
                          corner_radius=6, width=FAV_COL_DEL_W, height=22,
                          command=lambda i=i: self._del_fav(i)).pack(side="right", padx=(2, 6))

            ctk.CTkButton(row, text="載入", font=(FONT, FS_XS), **BTN_PRIMARY,
                          corner_radius=6, width=1, height=22, border_spacing=6,
                          command=lambda f=fav: self._load_fav(f)).pack(side="right", padx=4)

            # 座標預覽
            if fav["type"] == "pin":
                preview = f"{fav['lat']:.4f}, {fav['lon']:.4f}"
            else:
                preview = f"{len(fav['route'])} 個節點"
            preview_cell = self._fixed_cell(row, FAV_COL_PREVIEW_W)
            preview_cell.pack(side="right", padx=4)
            ctk.CTkLabel(preview_cell, text=preview, font=(FONT, FS_SM),
                         text_color=TEXT2, fg_color="transparent",
                         anchor="w").pack(fill="both", expand=True)

            # 圖示
            ctk.CTkLabel(row, text=icon_for(fav), font=(FONT_EMOJI, FS_EMOJI),
                         text_color=TEXT2, fg_color="transparent",
                         width=FAV_COL_ICON_W).pack(side="left", padx=4)

            # 名稱：吃掉剩餘寬度，過長時在容器內被裁掉而不是往外撐
            name_cell = self._fixed_cell(row, FAV_COL_NAME_MIN_W)
            name_cell.pack(side="left", fill="x", expand=True, padx=(0, 4))
            name_font = (FONT, FS_MD, "bold")
            name_label = ctk.CTkLabel(name_cell, text=fav["name"], font=name_font,
                                      text_color=TEXT, fg_color="transparent",
                                      anchor="w")
            name_label.pack(fill="both", expand=True)
            self._bind_elide(name_cell, name_label, fav["name"], name_font)

    def _save_current_pin_as_fav(self):
        try:
            lat = float(self.pin_lat.get())
            lon = float(self.pin_lon.get())
        except ValueError:
            messagebox.showerror("錯誤", "請先輸入有效座標")
            return
        name = simpledialog.askstring("儲存最愛", "請輸入地點名稱：",
                                       parent=self, initialvalue="我的地點")
        if not name:
            return
        self.favorites.append({"type": "pin", "name": name, "lat": lat, "lon": lon})
        save_favorites(self.favorites)
        self._refresh_fav_list()
        self._log("⭐ 已儲存最愛：" + name)

    def _save_current_route_as_fav(self):
        if len(self.route) < 2:
            messagebox.showerror("錯誤", "請至少設定 2 個路線點")
            return
        name = simpledialog.askstring("儲存最愛", "請輸入路線名稱：",
                                       parent=self, initialvalue="我的路線")
        if not name:
            return
        self.favorites.append({
            "type": "route",
            "name": name,
            "route": [[r[0], r[1], r[2]] for r in self.route]
        })
        save_favorites(self.favorites)
        self._refresh_fav_list()
        self._log("⭐ 已儲存路線：" + name)

    def _import_kml_as_fav(self):
        path = filedialog.askopenfilename(
            title="選擇 KML 檔案",
            filetypes=[("KML 檔案", "*.kml"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            route, doc_name = parse_kml_route(path)
        except Exception as e:
            messagebox.showerror("錯誤", f"KML 檔案解析失敗：\n{e}")
            return
        if not route or len(route) < 2:
            messagebox.showerror("錯誤", "此 KML 檔案內找不到有效的路線（LineString 座標）")
            return

        default_name = doc_name or os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("儲存最愛", "請輸入路線名稱：",
                                       parent=self, initialvalue=default_name)
        if not name:
            return
        self.favorites.append({"type": "route", "name": name, "route": route})
        save_favorites(self.favorites)
        self._refresh_fav_list()
        self._log(f"⭐ 已從 KML 匯入路線：{name}（共 {len(route)} 個路徑點）")

    def _load_fav(self, fav):
        if fav["type"] == "pin":
            self._switch_mode("pin")
            self.pin_lat.set(str(fav["lat"]))
            self.pin_lon.set(str(fav["lon"]))
            self._log("⭐ 載入最愛：" + fav["name"])
        else:
            self._switch_mode("route")
            self.route = [[r[0], r[1], r[2]] for r in fav["route"]]
            self.point_idx = 0
            self._refresh_route_rows()
            self._update_info()
            self._log("⭐ 載入路線：" + fav["name"])

    def _del_fav(self, i):
        name = self.favorites[i]["name"]
        if messagebox.askyesno("確認刪除", f"確定要刪除「{name}」？"):
            self.favorites.pop(i)
            save_favorites(self.favorites)
            self._refresh_fav_list()
            self._log("🗑  已刪除：" + name)

    def _set_speed(self, val):
        self.speed_var.set(round(val, 2))

    def _speed_ms(self):
        """UI 的速度以 km/h 輸入，換算成內部計算用的 m/s。"""
        return self.speed_var.get() / 3.6

    # ── 路線表格（虛擬化清單）────────────────────
    # 表格一次最多只看得到 ROUTE_TABLE_MAX_ROWS 列，所以只建立 ROUTE_ROW_POOL 個
    # 列 widget 重複使用，捲動時把它們重新綁到不同的資料索引並用 place() 移到
    # 對應的高度。載入 446 個點的路線因此從 8 秒降到不到 0.1 秒。
    def _install_route_scroll_hook(self):
        """捲動時重新計算要顯示哪幾列。

        CTkScrollableFrame 沒有對外的捲動事件，只能包住它內部 canvas 的
        yscrollcommand（原本直接接捲軸的 set）。這裡與 set_scrollbar_visibility()
        一樣是與 CustomTkinter 內部實作耦合的點，用 getattr + try 保護。
        """
        canvas = getattr(self.route_container, "_parent_canvas", None)
        scrollbar = getattr(self.route_container, "_scrollbar", None)
        if canvas is None or scrollbar is None:
            return
        try:
            canvas.configure(yscrollcommand=lambda first, last: (
                scrollbar.set(first, last), self._render_route_window()))
        except Exception:
            pass

    def _make_route_row(self):
        """建立一個可重複使用的表格列；內容留白，由 _render_route_window() 填。"""
        row = ctk.CTkFrame(self.route_container, fg_color=BG2, corner_radius=0)
        row.idx_label = ctk.CTkLabel(row, text="", width=ROUTE_COL_INDEX_W, height=26,
                                     font=(FONT, FS_SM), text_color=TEXT2,
                                     fg_color="transparent", anchor="w")
        row.idx_label.pack(side="left", padx=(6, 0))
        row.cell_vars, row.cell_entries = [], []
        for j, exp in enumerate([False, False, True]):
            var = tk.StringVar()
            entry = ctk.CTkEntry(row, textvariable=var, width=ROUTE_COL_COORD_W, height=24,
                                 font=(FONT, FS_SM), fg_color=BG2, text_color=TEXT,
                                 border_width=0, corner_radius=4)
            entry.pack(side="left", padx=2, fill="x", expand=exp)
            var.trace_add("write",
                          lambda *a, r=row, f=j, v=var: self._on_edit(r, f, v))
            row.cell_vars.append(var)
            row.cell_entries.append(entry)
        ctk.CTkButton(row, text="✕", font=(FONT, FS_XS),
                      fg_color="transparent", text_color=DANGER, hover_color=HOVER,
                      corner_radius=4, width=ROUTE_COL_DEL_W, height=22,
                      command=lambda r=row: self._del_point(r.data_index)).pack(side="left")
        row.data_index = None  # 目前綁在哪一筆資料；None 代表這列沒在用
        return row

    def _ensure_route_rows(self):
        if not self._route_rows:
            self._route_rows = [self._make_route_row() for _ in range(ROUTE_ROW_POOL)]

    def _route_row_height(self):
        """單列高度（實體像素）。place() 用的是實體像素，所以這裡不換算單位。"""
        if self._route_row_h is None:
            self._ensure_route_rows()
            probe = self._route_rows[0]
            probe.place(x=0, y=0, relwidth=1)
            self.update_idletasks()
            self._route_row_h = max(20, probe.winfo_reqheight())
        return self._route_row_h

    def _render_route_window(self):
        """依目前捲動位置，把列 widget 綁到對應的資料並擺到正確高度。"""
        if self._route_rendering or not hasattr(self, "route_container"):
            return
        self._route_rendering = True
        try:
            self._ensure_route_rows()
            total = len(self.route)
            row_h = self._route_row_height()
            canvas = getattr(self.route_container, "_parent_canvas", None)
            if total <= ROUTE_ROW_POOL:
                first = 0
            else:
                # canvasy(0) = 視窗頂端對應到內容的哪個 y，也就是捲動位移
                top = canvas.canvasy(0) if canvas is not None else 0
                first = int(max(0, top) // row_h)
                first = max(0, min(first, total - ROUTE_ROW_POOL))

            self._route_rebinding = True  # 擋掉 var.set() 觸發的 _on_edit
            for k, row in enumerate(self._route_rows):
                i = first + k
                if i >= total:
                    if row.data_index is not None:
                        row.place_forget()
                        row.data_index = None
                    continue
                row.data_index = i
                row.idx_label.configure(text=str(i + 1))
                row_color = BG2 if i % 2 == 0 else BG3
                row.configure(fg_color=row_color)
                for j, var in enumerate(row.cell_vars):
                    text = str(self.route[i][j])
                    if var.get() != text:
                        var.set(text)
                    row.cell_entries[j].configure(fg_color=row_color)
                # 不傳 height：CTkBaseClass.place() 禁止 width/height（那是建構子的
                # 參數，CTk 要自己套縮放）。不給的話 place 會用列的自然高度，
                # 而那正好就是 _route_row_height() 量到的值。
                row.place(x=0, y=i * row_h, relwidth=1)
        finally:
            self._route_rebinding = False
            self._route_rendering = False

    def _refresh_route_rows(self):
        """路線資料變動後重畫表格。

        只重畫看得到的那十幾列，耗時與路線長度無關；墊片高度決定捲動範圍。
        """
        if not hasattr(self, "route_container"):
            return
        self._ensure_route_rows()
        row_h = self._route_row_height()
        total_h = self._physical_to_widget_units(len(self.route) * row_h)
        self._route_spacer.configure(height=max(1, int(total_h)))
        canvas = getattr(self.route_container, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0)  # 換一條路線就回到表格最上面
        self._render_route_window()
        self._update_route_table_height()

    def _update_route_table_height(self):
        if not hasattr(self, "route_container"):
            return
        if not self.route:
            self.route_container.configure(height=1)
            return
        row_h = self._route_row_height()
        visible_rows = min(len(self.route), ROUTE_TABLE_MAX_ROWS)
        self.route_container.configure(
            height=self._physical_to_widget_units(row_h * visible_rows))
        self.update_idletasks()
        set_scrollbar_visibility(self.route_container)

    def _on_edit(self, row, field, var):
        # 換綁資料時 var.set() 也會觸發這裡，那不是使用者輸入，必須擋掉，
        # 否則會把上一列的值寫進新綁上來的那一筆資料。
        if self._route_rebinding or row.data_index is None:
            return
        try:
            val = float(var.get()) if field < 2 else var.get()
            self.route[row.data_index][field] = val
            self._update_info()
        except ValueError:
            pass

    def _add_point(self):
        last = self.route[-1] if self.route else [24.0, 121.0, "新增點"]
        self.route.append([last[0]+0.001, last[1]+0.001, "新增點"])
        self._refresh_route_rows()
        self._update_info()

    def _del_point(self, i):
        # 虛擬化清單裡沒綁到資料的列 data_index 是 None（正常情況下它是隱藏的、
        # 點不到，這裡只是不讓意外的呼叫炸掉）。
        if i is None or not (0 <= i < len(self.route)):
            return
        if len(self.route) <= 2:
            messagebox.showwarning("警告", "至少需要 2 個路線點")
            return
        self.route.pop(i)
        self._refresh_route_rows()
        self._update_info()

    def _clear_route_points(self):
        if not self.route:
            return
        if not messagebox.askyesno("確認清空", "確定要清空所有路線座標點嗎？"):
            return
        self.route = []
        self.point_idx = 0
        self.info_label.configure(text="")
        self._refresh_route_rows()
        self._update_info()

    def _update_info(self):
        try:
            if len(self.route) < 2:
                return
            dist = sum(
                haversine(self.route[i][0], self.route[i][1],
                          self.route[i+1][0], self.route[i+1][1])
                for i in range(len(self.route)-1)
            )
            speed = self._speed_ms()
            secs = dist / speed if speed > 0 else 0
            mins = int(secs // 60)
            sec2 = int(secs % 60)
            self.info_label.configure(
                text=f"總距離：{dist/1000:.2f} 公里  ·  預計時間：{mins} 分 {sec2} 秒  ·  共 {len(self.route)} 個節點"
            )
        except Exception:
            pass

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_progress_label(self, text):
        """背景執行緒要更新進度文字時，統一經由這個方法排回主執行緒。

        CTkLabel 沒有 tk.Label 的 config(**dict) 用法，改用具名方法比在
        self.after() 裡塞 dict 清楚。
        """
        self.progress_label.configure(text=text)

    def _start(self):
        if self.mode.get() == "route" and len(self.route) < 2:
            messagebox.showerror("錯誤", "請至少設定 2 個路線點")
            return
        if self.mode.get() == "pin":
            try:
                float(self.pin_lat.get())
                float(self.pin_lon.get())
            except ValueError:
                messagebox.showerror("錯誤", "請輸入有效的緯度/經度數值")
                return
        self.pending_action = "forward"
        self._sync_btn_states()
        if self.mode.get() == "pin":
            self._log("📌 固定定位模式啟動...")
        else:
            self._log("▶  開始模擬...")
        self._ensure_session_thread()

    def _stop(self):
        self.pending_action = "pause"
        self._log("⏹  停止中...")

    def _reverse(self):
        if self.mode.get() != "route":
            return
        if len(self.route) < 2:
            messagebox.showerror("錯誤", "請至少設定 2 個路線點")
            return
        self.pending_action = "reverse"
        self._sync_btn_states()
        self._log("↩  返回：從目前座標往回走...")
        self._ensure_session_thread()

    def _restore_real_location(self):
        if not self.session_active:
            messagebox.showinfo("提示", "目前尚未連線模擬，已經是真實定位")
            return
        if self.pending_action in ("forward", "reverse"):
            messagebox.showwarning("警告", "請先按「停止」，再恢復真實定位")
            return
        self.pending_action = "disconnect"
        self._sync_btn_states()
        self._log("🛰  恢復真實定位中...")

    def _ensure_session_thread(self):
        if self.session_thread and self.session_thread.is_alive():
            return
        self.session_thread = threading.Thread(target=self._run_session, daemon=True)
        self.session_thread.start()

    def _run_session(self):
        try:
            asyncio.run(self._session_main())
        except Exception as e:
            self.after(0, self._log, "❌ 錯誤：" + str(e))
        finally:
            self.after(0, self._on_session_ended)

    def _on_session_ended(self):
        self.session_active = False
        # 連線已結束（正常斷線或中途出錯），把動作歸零再同步按鈕狀態，
        # 否則殘留的 "disconnect"／"forward" 會讓按鈕全部卡在停用。
        self.pending_action = "pause"
        self._sync_btn_states()

    def _on_paused(self):
        self._sync_btn_states()

    async def _session_main(self):
        """維持一條長連線：開始/返回/停止都只是換動作，不會中斷連線；
        只有拿到 "disconnect" 動作（按下「恢復真實定位」）才會真正斷線，
        斷線當下裝置會自動恢復真實 GPS。"""
        try:
            from pymobiledevice3.tunneld.api import get_tunneld_devices
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        except ImportError as e:
            self.after(0, self._log, "❌ 匯入失敗：" + str(e))
            return

        self.after(0, self._log, "🔍 搜尋裝置中...")
        try:
            rsds = await get_tunneld_devices()
        except Exception as e:
            self.after(0, self._log, "❌ tunneld 連線失敗：" + str(e))
            self.after(0, self._log, "   請先以系統管理員執行：python -m pymobiledevice3 remote tunneld")
            return

        if not rsds:
            self.after(0, self._log, "❌ 找不到裝置，請確認 USB 已連接")
            return

        rsd = rsds[0]
        self.after(0, self._log, "✅ 找到裝置：" + str(rsd.udid))

        async with DvtProvider(rsd) as dvt, LocationSimulation(dvt) as sim:
            self.session_active = True
            while True:
                action = self.pending_action
                if action == "disconnect":
                    break
                elif action == "forward" and self.mode.get() == "pin":
                    await self._walk_pin(sim)
                elif action == "forward":
                    await self._walk_route(sim, 1)
                elif action == "reverse":
                    await self._walk_route(sim, -1)
                else:
                    await asyncio.sleep(0.2)
                    continue
                if self.pending_action == "pause":
                    self.after(0, self._on_paused)

            await sim.clear()
            self.point_idx = 0
            self.after(0, self._log, "✅ 已恢復真實定位")
            self.after(0, self.progress_var.set, 0)
            self.after(0, self._set_progress_label, "已恢復真實定位")

    async def _walk_pin(self, sim):
        lat = float(self.pin_lat.get())
        lon = float(self.pin_lon.get())
        self.after(0, self._log, f"📌 固定位置：{lat:.6f}, {lon:.6f}")
        await sim.set(lat, lon)
        self.after(0, self.progress_var.set, 1.0)
        self.after(0, self._set_progress_label, f"📌 固定中  {lat:.6f}, {lon:.6f}")
        self.after(0, self._log, "✅ 定位已固定！按「停止」可保持在目前座標")
        self.pending_action = "pause"

    async def _walk_route(self, sim, direction):
        """direction=1 往路線終點走，direction=-1 往路線起點走回去。
        走到一半若 self.pending_action 被改成別的值（暫停/切換方向/斷線），
        會立刻中斷並把目前位置留在 self.point_idx，交回外層迴圈處理。
        循環模式只由「開始」啟動的 forward 觸發：走到終點後自動折返走回起點，
        再從起點往終點走，如此來回往復，直到 pending_action 被改成別的值。"""
        action_name = "forward" if direction == 1 else "reverse"
        loop_mode = self.loop_var.get() if direction == 1 else False
        if direction == -1:
            self.after(0, self._log, "↩  返回中，沿路線往回走...")

        idx = self.point_idx
        while True:
            suffix = "" if direction == 1 else "（返回中）"
            speed = self._speed_ms()
            points = interpolate_points([(r[0], r[1], "") for r in self.route], speed, 1.0)
            total = len(points)
            idx = max(0, min(idx, total - 1))
            idx_range = range(idx, total) if direction == 1 else range(idx, -1, -1)

            interrupted = False
            for i in idx_range:
                if self.pending_action != action_name:
                    interrupted = True
                    break
                lat, lon = points[i]
                await sim.set(lat, lon)
                idx = i
                self.point_idx = i
                # CTkProgressBar 的值域是 0~1，文字標籤仍顯示百分比。
                frac = (i + 1) / total if direction == 1 else i / total
                self.after(0, self.progress_var.set, frac)
                self.after(0, self._set_progress_label,
                           f"{frac*100:.1f}%  📍 {lat:.6f}, {lon:.6f}{suffix}")
                await asyncio.sleep(1.0)

            if interrupted:
                return

            if loop_mode and self.pending_action == action_name:
                if direction == 1:
                    self.after(0, self._log, "🔁 循環模式：已抵達終點，沿路線折返")
                else:
                    self.after(0, self._log, "🔁 循環模式：已回到起點，再次出發")
                direction = -direction
                idx = max(0, min(idx + direction, total - 1))
                self.point_idx = idx
                continue

            if direction == 1:
                self.after(0, self._log, "✅ 完成！保持於目前座標")
            else:
                self.after(0, self._log, "✅ 已返回起點，保持於目前座標")
            self.after(0, self._set_progress_label, "已完成")
            self.pending_action = "pause"
            return


if __name__ == "__main__":
    app = GPSApp()
    app.mainloop()
