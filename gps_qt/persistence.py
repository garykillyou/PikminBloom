"""JSON 存讀與 KML 解析：與原 gps_app.py 完全相同的檔案格式與欄位。"""

import json
import os
import xml.etree.ElementTree as ET

FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gps_favorites.json")
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gps_settings.json")
FAVORITES_FILE = os.path.normpath(FAVORITES_FILE)
SETTINGS_FILE = os.path.normpath(SETTINGS_FILE)


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


def load_saved_route(settings):
    """讀取上次關閉程式前的路線座標點；沒有存檔或格式不對就回傳 None，讓呼叫端 fallback 回預設路線。"""
    raw = settings.get("last_route")
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    route = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return None
        lat, lon, name = item
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return None
        route.append([lat, lon, str(name)])
    return route


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
