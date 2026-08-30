# iPhone GPS 路線模擬器 - 圖形介面版
# 執行前請確認：
#   1. 系統管理員視窗執行：pymobiledevice3 remote tunneld
#   2. 執行此 App：C:\Python311\python.exe gps_app.py

import asyncio
import math
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
import sys
import json
import os
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

# ── 顏色主題（深色 / 淺色）────────────────────
THEMES = {
    "dark": {
        "BG": "#1D1616", "BG2": "#2A1F1F", "BG3": "#3D2424",
        "ACCENT": "#D84040", "ACCENT2": "#8E1616",
        "SUCCESS": "#00e676", "DANGER": "#D84040",
        "TEXT": "#EEEEEE", "TEXT2": "#A89A9A",
        "TEXT_ON_ACCENT": "#EEEEEE",
    },
    "light": {
        "BG": "#EFFFFB", "BG2": "#ffffff", "BG3": "#DCEEE7",
        "ACCENT": "#4F98CA", "ACCENT2": "#50D890",
        "SUCCESS": "#50D890", "DANGER": "#e5484d",
        "TEXT": "#272727", "TEXT2": "#5c5c5c",
        "TEXT_ON_ACCENT": "#EFFFFB",
    },
}

BG = BG2 = BG3 = ACCENT = ACCENT2 = SUCCESS = DANGER = TEXT = TEXT2 = TEXT_ON_ACCENT = None

def apply_theme(name):
    global BG, BG2, BG3, ACCENT, ACCENT2, SUCCESS, DANGER, TEXT, TEXT2, TEXT_ON_ACCENT
    t = THEMES[name]
    BG, BG2, BG3 = t["BG"], t["BG2"], t["BG3"]
    ACCENT, ACCENT2 = t["ACCENT"], t["ACCENT2"]
    SUCCESS, DANGER = t["SUCCESS"], t["DANGER"]
    TEXT, TEXT2 = t["TEXT"], t["TEXT2"]
    TEXT_ON_ACCENT = t["TEXT_ON_ACCENT"]

apply_theme("dark")
# ─────────────────────────────────────────────

WIDE_LAYOUT_BREAKPOINT = 1000
ROUTE_TABLE_MAX_ROWS = 15

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

class GPSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("iPhone GPS 路線模擬器")
        self.geometry("1500x820")
        self.resizable(True, True)
        self.minsize(560, 360)

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
        self.settings = load_settings()
        self.theme_name = self.settings.get("theme", "dark")
        if self.theme_name not in THEMES:
            self.theme_name = "dark"
        apply_theme(self.theme_name)
        self.configure(bg=BG)

        self._build_scroll_container()
        self._build_ui()
        self._apply_responsive_layout(1500)
        # 先讓視窗以一般大小完成第一次繪製，再最大化：一方面避免最大化動畫途中
        # 內容尚未畫出而露出空白背景，另一方面在真正變成最大化尺寸後，強制把
        # scrollregion 與捲動位置重新校正到最上方，避免出現「明明沒往下捲，
        # 卻可以往上捲出空白」的殘留捲動位移。
        self.after(10, self._maximize_and_reset_scroll)

    def _maximize_and_reset_scroll(self):
        self.state("zoomed")
        self.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(0)
        self._update_scrollbar_visibility()
        self._update_log_height()
        if hasattr(self, "route_container"):
            self._update_route_table_height()

    def _content_fits(self, target_canvas=None):
        target_canvas = target_canvas or self.canvas
        bbox = target_canvas.bbox("all")
        content_h = (bbox[3] - bbox[1]) if bbox else 0
        return content_h <= target_canvas.winfo_height()

    def _update_scrollbar_visibility(self):
        if self._content_fits():
            if self.scrollbar.winfo_ismapped():
                self.scrollbar.pack_forget()
        else:
            if not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(side="right", fill="y")

    def _widget_is_descendant(self, widget, ancestor):
        w = widget
        while w is not None:
            if w == ancestor:
                return True
            w = getattr(w, "master", None)
        return False

    def _scroll_canvas(self, target_canvas, event):
        if self._content_fits(target_canvas):
            return
        target_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        top, bottom = target_canvas.yview()
        if top < 0:
            target_canvas.yview_moveto(0)
        elif bottom > 1:
            target_canvas.yview_moveto(1 - (bottom - top))

    def _update_log_height(self, window_height=None):
        if not hasattr(self, "log_frame"):
            return
        if window_height is None:
            window_height = self.container.winfo_height()
        self.log_frame.configure(height=max(80, int(window_height * 0.4)))

    def _build_scroll_container(self):
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)
        self.container.bind("<Configure>", lambda e: self._update_log_height(e.height))

        canvas = tk.Canvas(self.container, bg=BG, highlightthickness=0)
        self.canvas = canvas
        self.scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=self.scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        # 捲軸是否顯示由 _update_scrollbar_visibility() 依內容高度動態決定，
        # 這裡先不 pack。

        self.scroll_frame = tk.Frame(canvas, bg=BG)
        frame_id = canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            self._update_scrollbar_visibility()
        self.scroll_frame.bind("<Configure>", _on_frame_configure)

        def _on_canvas_configure(event):
            canvas.itemconfig(frame_id, width=event.width)
            self._apply_responsive_layout(event.width)
            self._update_scrollbar_visibility()
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            if hasattr(self, "route_container") and hasattr(self, "route_canvas") and \
                    self._widget_is_descendant(event.widget, self.route_container):
                self._scroll_canvas(self.route_canvas, event)
            else:
                self._scroll_canvas(canvas, event)
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

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
        pin_lat_val = self.pin_lat.get()
        pin_lon_val = self.pin_lon.get()
        speed_val = self.speed_var.get()
        loop_val = self.loop_var.get()
        mode_val = self.mode.get()

        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        apply_theme(self.theme_name)
        self.settings["theme"] = self.theme_name
        save_settings(self.settings)

        self.configure(bg=BG)
        self.container.destroy()
        self._layout_wide = None
        self._build_scroll_container()
        self._build_ui()

        self.pin_lat.set(pin_lat_val)
        self.pin_lon.set(pin_lon_val)
        self.speed_var.set(speed_val)
        self.loop_var.set(loop_val)
        self._switch_mode(mode_val)
        self._update_info()

        self.update_idletasks()
        self._apply_responsive_layout(self.winfo_width())
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(0)
        self._update_scrollbar_visibility()
        self._update_route_table_height()

    def _build_ui(self):
        # ── 標題 ──
        title_frame = tk.Frame(self.scroll_frame, bg=BG, pady=20)
        title_frame.pack(fill="x", padx=30)

        tk.Label(title_frame, text="📍", font=("Segoe UI Emoji", 28),
                 bg=BG, fg=ACCENT).pack(side="left")
        title_col = tk.Frame(title_frame, bg=BG)
        title_col.pack(side="left", padx=12)
        tk.Label(title_col, text="GPS 路線模擬器",
                 font=("Segoe UI", 20, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(title_col, text="iPhone iOS 17/18+  ·  需先執行 tunneld",
                 font=("Segoe UI", 10), bg=BG, fg=TEXT2).pack(anchor="w")

        self.theme_btn = tk.Button(title_frame, text=self._theme_btn_text(),
                                    font=("Segoe UI", 10, "bold"),
                                    bg=BG3, fg=TEXT, relief="flat",
                                    padx=14, pady=8, cursor="hand2",
                                    command=self._toggle_theme)
        self.theme_btn.pack(side="right", padx=(0, 4))

        # ── 內容分欄（>1000px 寬時左右並排且等寬，否則上下堆疊）──
        columns_frame = tk.Frame(self.scroll_frame, bg=BG)
        columns_frame.pack(fill="both", expand=True)
        columns_frame.columnconfigure(0, weight=1, uniform="cols")
        columns_frame.columnconfigure(1, weight=1, uniform="cols")

        self.left_col = tk.Frame(columns_frame, bg=BG)
        self.right_col = tk.Frame(columns_frame, bg=BG)

        # ── 控制按鈕（左欄，兩顆按鈕等寬並填滿整列）──
        btn_frame = tk.Frame(self.left_col, bg=BG, pady=8)
        btn_frame.pack(fill="x")
        btn_frame.columnconfigure(0, weight=1, uniform="ctrl_btns")
        btn_frame.columnconfigure(1, weight=1, uniform="ctrl_btns")
        btn_frame.columnconfigure(2, weight=1, uniform="ctrl_btns")

        self.start_btn = tk.Button(btn_frame, text="▶  開始模擬",
                                   font=("Segoe UI", 13, "bold"),
                                   bg=ACCENT, fg="#000", relief="flat",
                                   padx=30, pady=12, cursor="hand2",
                                   command=self._start)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.return_btn = tk.Button(btn_frame, text="↩  返回",
                                    font=("Segoe UI", 13, "bold"),
                                    bg=BG3, fg=TEXT, relief="flat",
                                    padx=30, pady=12, cursor="hand2",
                                    state="disabled",
                                    command=self._reverse)
        self.return_btn.grid(row=0, column=1, sticky="ew", padx=4)

        self.stop_btn = tk.Button(btn_frame, text="⏹  停止",
                                  font=("Segoe UI", 13, "bold"),
                                  bg=DANGER, fg=TEXT_ON_ACCENT, relief="flat",
                                  padx=30, pady=12, cursor="hand2",
                                  state="disabled",
                                  command=self._stop)
        self.stop_btn.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # ── 恢復真實定位（獨立按鈕，與開始/返回/停止的流程無關）──
        restore_frame = tk.Frame(self.left_col, bg=BG)
        restore_frame.pack(fill="x", pady=(0, 4))
        self.restore_btn = tk.Button(restore_frame, text="🛰  恢復真實定位",
                                     font=("Segoe UI", 10, "bold"),
                                     bg=BG3, fg=TEXT2, relief="flat",
                                     padx=20, pady=8, cursor="hand2",
                                     command=self._restore_real_location)
        self.restore_btn.pack(fill="x")

        # ── 進度條（左欄）──
        self.progress_var = tk.DoubleVar(value=0)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("GPS.Horizontal.TProgressbar",
                        troughcolor=BG3, background=ACCENT,
                        bordercolor=BG3, lightcolor=ACCENT,
                        darkcolor=ACCENT, thickness=8)
        self.progress_bar = ttk.Progressbar(self.left_col, variable=self.progress_var,
                                             maximum=100, length=660,
                                             style="GPS.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=8)

        self.progress_label = tk.Label(self.left_col, text="",
                                       font=("Segoe UI", 10), bg=BG, fg=TEXT2)
        self.progress_label.pack()

        # ── 日誌（左欄，高度固定為視窗高度的 40%）──
        tk.Label(self.left_col, text="執行日誌", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=TEXT2).pack(anchor="w", pady=(12, 2))
        self.log_frame = tk.Frame(self.left_col, bg=BG)
        self.log_frame.pack(fill="x", pady=(0, 20))
        self.log_frame.pack_propagate(False)
        self.log = scrolledtext.ScrolledText(self.log_frame,
                                              font=("Consolas", 9),
                                              bg=BG2, fg=TEXT2,
                                              insertbackground=ACCENT,
                                              relief="flat", bd=0,
                                              state="disabled")
        self.log.pack(fill="both", expand=True)
        self._update_log_height()

        # ── 最愛地點面板（左欄）──
        self.fav_frame = tk.Frame(self.left_col, bg=BG2, padx=20, pady=14)
        self.fav_frame.pack(fill="x", pady=(0, 8))

        fav_title_row = tk.Frame(self.fav_frame, bg=BG2)
        fav_title_row.pack(fill="x", pady=(0, 10))
        tk.Label(fav_title_row, text="⭐ 最愛地點",
                 font=("Segoe UI", 11, "bold"), bg=BG2, fg=TEXT).pack(side="left")

        # 儲存目前定位按鈕
        save_pin_btn = tk.Button(fav_title_row, text="＋ 儲存目前座標",
                                  font=("Segoe UI", 9), bg=ACCENT2, fg=TEXT_ON_ACCENT,
                                  relief="flat", padx=10, pady=4, cursor="hand2",
                                  command=self._save_current_pin_as_fav)
        save_pin_btn.pack(side="right", padx=(4, 0))

        save_route_btn = tk.Button(fav_title_row, text="＋ 儲存目前路線",
                                    font=("Segoe UI", 9), bg=BG3, fg=TEXT2,
                                    relief="flat", padx=10, pady=4, cursor="hand2",
                                    command=self._save_current_route_as_fav)
        save_route_btn.pack(side="right", padx=4)

        # 匯入 KML 檔案產生路線最愛按鈕
        import_kml_btn = tk.Button(fav_title_row, text="＋ 匯入 KML 路線",
                                    font=("Segoe UI", 9), bg=BG3, fg=TEXT2,
                                    relief="flat", padx=10, pady=4, cursor="hand2",
                                    command=self._import_kml_as_fav)
        import_kml_btn.pack(side="right", padx=4)

        # 最愛列表
        self.fav_list_frame = tk.Frame(self.fav_frame, bg=BG2)
        self.fav_list_frame.pack(fill="x")
        self._refresh_fav_list()

        # ── 模式切換（右欄）──
        mode_frame = tk.Frame(self.right_col, bg=BG2, padx=20, pady=12)
        mode_frame.pack(fill="x", pady=(0, 8))

        tk.Label(mode_frame, text="模式選擇", font=("Segoe UI", 11, "bold"),
                 bg=BG2, fg=TEXT).pack(side="left", padx=(0, 16))

        self.route_mode_btn = tk.Button(mode_frame, text="🗺  路線移動",
                                        font=("Segoe UI", 10, "bold"),
                                        bg=ACCENT, fg="#000", relief="flat",
                                        padx=16, pady=6, cursor="hand2",
                                        command=lambda: self._switch_mode("route"))
        self.route_mode_btn.pack(side="left", padx=4)

        self.pin_mode_btn = tk.Button(mode_frame, text="📌  固定定位",
                                      font=("Segoe UI", 10, "bold"),
                                      bg=BG3, fg=TEXT2, relief="flat",
                                      padx=16, pady=6, cursor="hand2",
                                      command=lambda: self._switch_mode("pin"))
        self.pin_mode_btn.pack(side="left", padx=4)

        # ── 固定定位面板（預設隱藏，右欄）──
        self.pin_frame = tk.Frame(self.right_col, bg=BG2, padx=20, pady=16)

        tk.Label(self.pin_frame, text="固定座標",
                 font=("Segoe UI", 11, "bold"), bg=BG2, fg=TEXT).grid(
                 row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        tk.Label(self.pin_frame, text="緯度：", font=("Segoe UI", 10),
                 bg=BG2, fg=TEXT2).grid(row=1, column=0, sticky="w")
        self.pin_lat = tk.StringVar(value="24.1368")
        tk.Entry(self.pin_frame, textvariable=self.pin_lat, width=16,
                 font=("Segoe UI", 11), bg=BG3, fg=ACCENT,
                 insertbackground=ACCENT, relief="flat", bd=4).grid(
                 row=1, column=1, padx=8)

        tk.Label(self.pin_frame, text="經度：", font=("Segoe UI", 10),
                 bg=BG2, fg=TEXT2).grid(row=1, column=2, sticky="w")
        self.pin_lon = tk.StringVar(value="120.6862")
        tk.Entry(self.pin_frame, textvariable=self.pin_lon, width=16,
                 font=("Segoe UI", 11), bg=BG3, fg=ACCENT,
                 insertbackground=ACCENT, relief="flat", bd=4).grid(
                 row=1, column=3, padx=8)

        # 預設地點快速選擇
        pin_presets_label = tk.Frame(self.pin_frame, bg=BG2)
        pin_presets_label.grid(row=2, column=0, columnspan=4, sticky="w", pady=(12, 4))
        tk.Label(pin_presets_label, text="快速選擇：",
                 font=("Segoe UI", 9), bg=BG2, fg=TEXT2).pack(side="left")

        pin_presets_btns = tk.Frame(self.pin_frame, bg=BG2)
        pin_presets_btns.grid(row=3, column=0, columnspan=4, sticky="w")
        pin_presets = [
            ("台中火車站", 24.1368, 120.6862),
            ("台北101",   25.0338, 121.5645),
            ("高雄85大樓", 22.6155, 120.3025),
            ("台南孔廟",   22.9969, 120.2008),
        ]
        for name, lat, lon in pin_presets:
            btn = tk.Button(pin_presets_btns, text=name,
                            font=("Segoe UI", 9),
                            bg=BG3, fg=TEXT2, relief="flat",
                            padx=10, pady=5, cursor="hand2",
                            command=lambda la=lat, lo=lon: (
                                self.pin_lat.set(str(la)),
                                self.pin_lon.set(str(lo))
                            ))
            btn.pack(side="left", padx=4)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=ACCENT2, fg=TEXT_ON_ACCENT))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=BG3, fg=TEXT2))

        # ── 速度設定 ──
        speed_frame = tk.Frame(self.right_col, bg=BG2, padx=20, pady=16)
        speed_frame.pack(fill="x", pady=(0, 12))
        self.speed_frame_ref = speed_frame

        tk.Label(speed_frame, text="移動速度", font=("Segoe UI", 11, "bold"),
                 bg=BG2, fg=TEXT).grid(row=0, column=0, sticky="w")

        self.speed_var = tk.DoubleVar(value=5.56)
        presets = [("步行 5 km/h", 1.39), ("慢跑 10 km/h", 2.78),
                   ("騎車 20 km/h", 5.56), ("開車 40 km/h", 11.11)]

        preset_frame = tk.Frame(speed_frame, bg=BG2)
        preset_frame.grid(row=1, column=0, sticky="w", pady=8)
        for label, val in presets:
            btn = tk.Button(preset_frame, text=label,
                            font=("Segoe UI", 9),
                            bg=BG3, fg=TEXT2, relief="flat",
                            padx=10, pady=5, cursor="hand2",
                            command=lambda v=val: self._set_speed(v))
            btn.pack(side="left", padx=4)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=ACCENT2, fg=TEXT_ON_ACCENT))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=BG3, fg=TEXT2))

        speed_row = tk.Frame(speed_frame, bg=BG2)
        speed_row.grid(row=2, column=0, sticky="w")
        tk.Label(speed_row, text="自訂 m/s：", font=("Segoe UI", 10),
                 bg=BG2, fg=TEXT2).pack(side="left")
        self.speed_entry = tk.Entry(speed_row, textvariable=self.speed_var,
                                    width=8, font=("Segoe UI", 11),
                                    bg=BG3, fg=ACCENT, insertbackground=ACCENT,
                                    relief="flat", bd=4)
        self.speed_entry.pack(side="left", padx=6)

        self.loop_var = tk.BooleanVar(value=False)
        tk.Checkbutton(speed_row, text="循環模式",
                       variable=self.loop_var,
                       font=("Segoe UI", 10), bg=BG2, fg=TEXT2,
                       selectcolor=BG3, activebackground=BG2,
                       activeforeground=TEXT).pack(side="left", padx=16)

        # ── 路線點 ──
        self.route_section = tk.Frame(self.right_col, bg=BG)
        self.route_section.pack(fill="x", padx=0)

        route_label_frame = tk.Frame(self.route_section, bg=BG)
        route_label_frame.pack(fill="x", padx=0, pady=(4, 4))
        tk.Label(route_label_frame, text="路線座標點",
                 font=("Segoe UI", 11, "bold"), bg=BG, fg=TEXT).pack(side="left")
        tk.Button(route_label_frame, text="🗑 清空座標點",
                  font=("Segoe UI", 9), bg=BG3, fg=TEXT2,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._clear_route_points).pack(side="right")
        tk.Button(route_label_frame, text="＋ 新增點",
                  font=("Segoe UI", 9), bg=ACCENT2, fg=TEXT_ON_ACCENT,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._add_point).pack(side="right")
        # 距離/時間資訊：與「＋ 新增點」同一列
        self.info_label = tk.Label(route_label_frame, text="",
                                   font=("Segoe UI", 10), bg=BG, fg=TEXT2)
        self.info_label.pack(side="left", padx=(16, 0))

        # 路線表格
        cols_frame = tk.Frame(self.route_section, bg=BG3)
        cols_frame.pack(fill="x", padx=0)
        for txt, w, exp in [("#", 4, False), ("緯度", 10, False), ("經度", 10, False),
                            ("備註", 10, True), ("", 6, False)]:
            tk.Label(cols_frame, text=txt, font=("Segoe UI", 9),
                     bg=BG3, fg=TEXT2, width=w, anchor="w",
                     padx=6, pady=4).pack(side="left", fill="x", expand=exp)

        # 表格內容區：用一個小型 canvas 包住，最多顯示 ROUTE_TABLE_MAX_ROWS 列，
        # 超過時才出現右側捲軸（同樣依內容自動顯示/隱藏）。
        route_table_wrap = tk.Frame(self.route_section, bg=BG2)
        route_table_wrap.pack(fill="x", padx=0)

        self.route_canvas = tk.Canvas(route_table_wrap, bg=BG2, highlightthickness=0)
        self.route_scrollbar = ttk.Scrollbar(route_table_wrap, orient="vertical",
                                              command=self.route_canvas.yview)
        self.route_canvas.configure(yscrollcommand=self.route_scrollbar.set)
        self.route_canvas.pack(side="left", fill="both", expand=True)

        self.route_container = tk.Frame(self.route_canvas, bg=BG2)
        route_frame_id = self.route_canvas.create_window((0, 0), window=self.route_container, anchor="nw")

        def _on_route_frame_configure(event):
            self.route_canvas.configure(scrollregion=self.route_canvas.bbox("all"))
        self.route_container.bind("<Configure>", _on_route_frame_configure)

        def _on_route_canvas_configure(event):
            self.route_canvas.itemconfig(route_frame_id, width=event.width)
        self.route_canvas.bind("<Configure>", _on_route_canvas_configure)

        self._refresh_route_rows()
        self._update_info()
        self._update_return_btn_state()

    def _switch_mode(self, mode):
        self.mode.set(mode)
        if mode == "route":
            self.route_mode_btn.config(bg=ACCENT, fg="#000")
            self.pin_mode_btn.config(bg=BG3, fg=TEXT2)
            self.pin_frame.pack_forget()
            self.speed_frame_ref.pack(fill="x", pady=(0, 12))
            self.route_section.pack(fill="x", padx=0)
            self.start_btn.config(text="▶  開始模擬")
        else:
            self.pin_mode_btn.config(bg=ACCENT2, fg=TEXT_ON_ACCENT)
            self.route_mode_btn.config(bg=BG3, fg=TEXT2)
            self.speed_frame_ref.pack_forget()
            self.route_section.pack_forget()
            self.pin_frame.pack(fill="x", pady=(0, 8))
            self.start_btn.config(text="📌  固定定位")
        self._update_return_btn_state()

    def _update_return_btn_state(self):
        self.return_btn.config(state="normal" if self.mode.get() == "route" else "disabled")

    def _refresh_fav_list(self):
        for w in self.fav_list_frame.winfo_children():
            w.destroy()
        if not self.favorites:
            tk.Label(self.fav_list_frame, text="尚無儲存的最愛地點",
                     font=("Segoe UI", 9), bg=BG2, fg=TEXT2,
                     pady=6).pack(anchor="w")
            return
        for i, fav in enumerate(self.favorites):
            row = tk.Frame(self.fav_list_frame,
                           bg=BG3 if i % 2 == 0 else BG2)
            row.pack(fill="x", pady=1)

            # 圖示
            icon = "📌" if fav["type"] == "pin" else "🗺"
            tk.Label(row, text=icon, font=("Segoe UI Emoji", 10),
                     bg=row["bg"], fg=TEXT2, width=3).pack(side="left", padx=4)

            # 名稱（佔最大表格寬度比例）
            tk.Label(row, text=fav["name"],
                     font=("Segoe UI", 10, "bold"), bg=row["bg"], fg=TEXT,
                     width=10, anchor="w").pack(side="left", fill="x", expand=True, padx=(0, 4))

            # 座標預覽
            if fav["type"] == "pin":
                preview = f"{fav['lat']:.4f}, {fav['lon']:.4f}"
            else:
                preview = f"{len(fav['route'])} 個節點"
            tk.Label(row, text=preview, font=("Segoe UI", 9),
                     bg=row["bg"], fg=TEXT2, width=14, anchor="w").pack(side="left")

            # 載入按鈕
            load_btn = tk.Button(row, text="載入",
                                  font=("Segoe UI", 8), bg=ACCENT, fg="#000",
                                  relief="flat", padx=8, pady=2, cursor="hand2",
                                  command=lambda f=fav: self._load_fav(f))
            load_btn.pack(side="left", padx=4)

            # 刪除按鈕
            del_btn = tk.Button(row, text="✕",
                                 font=("Segoe UI", 8), bg=row["bg"], fg=DANGER,
                                 relief="flat", padx=6, pady=2, cursor="hand2",
                                 command=lambda i=i: self._del_fav(i))
            del_btn.pack(side="left", padx=2)

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

    def _refresh_route_rows(self):
        for w in self.route_container.winfo_children():
            w.destroy()
        for i, pt in enumerate(self.route):
            row = tk.Frame(self.route_container,
                           bg=BG2 if i % 2 == 0 else BG3)
            row.pack(fill="x")
            tk.Label(row, text=str(i+1), width=4, font=("Segoe UI", 9),
                     bg=row["bg"], fg=TEXT2, padx=6, pady=4).pack(side="left")
            for j, (w, exp) in enumerate([(10, False), (10, False), (10, True)]):
                var = tk.StringVar(value=str(pt[j]))
                e = tk.Entry(row, textvariable=var, width=w,
                             font=("Segoe UI", 9), bg=row["bg"],
                             fg=ACCENT if j < 2 else TEXT,
                             insertbackground=ACCENT, relief="flat", bd=2)
                e.pack(side="left", padx=2, fill="x", expand=exp)
                idx, field = i, j
                var.trace_add("write", lambda *a, i=idx, f=field, v=var: self._on_edit(i, f, v))
            tk.Button(row, text="✕", font=("Segoe UI", 8),
                      bg=row["bg"], fg=DANGER, relief="flat",
                      cursor="hand2", width=3,
                      command=lambda i=i: self._del_point(i)).pack(side="left")
        self._update_route_table_height()

    def _update_route_table_height(self):
        rows = self.route_container.winfo_children()
        if not rows:
            return
        self.update_idletasks()
        row_h = rows[0].winfo_reqheight()
        visible_rows = min(len(rows), ROUTE_TABLE_MAX_ROWS)
        self.route_canvas.configure(height=row_h * visible_rows)
        self.route_canvas.configure(scrollregion=self.route_canvas.bbox("all"))
        self.update_idletasks()
        if self._content_fits(self.route_canvas):
            if self.route_scrollbar.winfo_ismapped():
                self.route_scrollbar.pack_forget()
        else:
            if not self.route_scrollbar.winfo_ismapped():
                self.route_scrollbar.pack(side="right", fill="y")

    def _on_edit(self, i, field, var):
        try:
            val = float(var.get()) if field < 2 else var.get()
            self.route[i][field] = val
            self._update_info()
        except ValueError:
            pass

    def _add_point(self):
        last = self.route[-1] if self.route else [24.0, 121.0, "新增點"]
        self.route.append([last[0]+0.001, last[1]+0.001, "新增點"])
        self._refresh_route_rows()
        self._update_info()

    def _del_point(self, i):
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
        self.info_label.config(text="")
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
            speed = self.speed_var.get()
            secs = dist / speed if speed > 0 else 0
            mins = int(secs // 60)
            sec2 = int(secs % 60)
            self.info_label.config(
                text=f"總距離：{dist/1000:.2f} 公里  ·  預計時間：{mins} 分 {sec2} 秒  ·  共 {len(self.route)} 個節點"
            )
        except Exception:
            pass

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

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
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.restore_btn.config(state="disabled")
        self._update_return_btn_state()
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
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.return_btn.config(state="disabled")
        self.restore_btn.config(state="disabled")
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
        self.restore_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")
        self.return_btn.config(state="disabled")
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
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.restore_btn.config(state="normal")
        self._update_return_btn_state()

    def _on_paused(self):
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.restore_btn.config(state="normal")
        self._update_return_btn_state()

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
            self.after(0, self.progress_label.config, {"text": "已恢復真實定位"})

    async def _walk_pin(self, sim):
        lat = float(self.pin_lat.get())
        lon = float(self.pin_lon.get())
        self.after(0, self._log, f"📌 固定位置：{lat:.6f}, {lon:.6f}")
        await sim.set(lat, lon)
        self.after(0, self.progress_var.set, 100)
        self.after(0, self.progress_label.config,
                   {"text": f"📌 固定中  {lat:.6f}, {lon:.6f}"})
        self.after(0, self._log, "✅ 定位已固定！按「停止」可保持在目前座標")
        self.pending_action = "pause"

    async def _walk_route(self, sim, direction):
        """direction=1 往路線終點走，direction=-1 往路線起點走回去。
        走到一半若 self.pending_action 被改成別的值（暫停/切換方向/斷線），
        會立刻中斷並把目前位置留在 self.point_idx，交回外層迴圈處理。"""
        action_name = "forward" if direction == 1 else "reverse"
        suffix = "" if direction == 1 else "（返回中）"
        loop_mode = self.loop_var.get() if direction == 1 else False
        if direction == -1:
            self.after(0, self._log, "↩  返回中，沿路線往回走...")

        idx = self.point_idx
        while True:
            speed = self.speed_var.get()
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
                progress = (i + 1) / total * 100 if direction == 1 else i / total * 100
                self.after(0, self.progress_var.set, progress)
                self.after(0, self.progress_label.config,
                           {"text": f"{progress:.1f}%  📍 {lat:.6f}, {lon:.6f}{suffix}"})
                await asyncio.sleep(1.0)

            if interrupted:
                return

            if direction == 1 and loop_mode and self.pending_action == "forward":
                self.after(0, self._log, "🔁 循環模式：回到起點重新出發")
                idx = 0
                self.point_idx = 0
                continue

            if direction == 1:
                self.after(0, self._log, "✅ 完成！保持於目前座標")
            else:
                self.after(0, self._log, "✅ 已返回起點，保持於目前座標")
            self.after(0, self.progress_label.config, {"text": "已完成"})
            self.pending_action = "pause"
            return


if __name__ == "__main__":
    app = GPSApp()
    app.mainloop()
