"""map_bridge.py 的 payload 序列化測試。"""

import json

from gps_qt.map_bridge import bounds_payload, favorites_payload, route_payload


def test_route_payload_is_stable_for_identical_input():
    """同樣的路線必須序列化成完全相同的字串。

    map.js 靠「JSON 與上次收到的相同就跳過重繪」擋掉雙向同步的回授迴圈，
    payload 一旦帶了流水號或時間戳這類會變動的欄位，那道防護就失效了。
    """
    # Arrange
    route = [[24.1368, 120.6862, "台中火車站"], [24.139, 120.68, ""]]

    # Act
    first, second = route_payload(route), route_payload(route)

    # Assert
    assert first == second


def test_route_payload_shape_and_types():
    # Arrange：緯經度給字串，備註給 None 以外的型別，確認會被正規化
    route = [["24.1368", "120.6862", "台中火車站"]]

    # Act
    payload = json.loads(route_payload(route))

    # Assert
    assert payload == {"points": [[24.1368, 120.6862, "台中火車站"]]}


def test_bounds_payload_drops_the_note_column():
    # Arrange
    route = [[24.1368, 120.6862, "台中火車站"], [24.139, 120.68, "下一點"]]

    # Act
    payload = json.loads(bounds_payload(route))

    # Assert
    assert payload == [[24.1368, 120.6862], [24.139, 120.68]]


def test_favorites_payload_keeps_only_pins_with_original_index():
    """路線最愛不畫在地圖上；index 必須是在完整清單裡的位置，點擊才能對回同一筆。"""
    # Arrange
    favorites = [
        {"type": "route", "name": "路線A", "route": [[24.0, 120.0], [24.1, 120.1]]},
        {"type": "pin", "name": "地點B", "lat": 24.1368, "lon": 120.6862},
    ]

    # Act
    pins = json.loads(favorites_payload(favorites))

    # Assert
    assert pins == [{"index": 1, "name": "地點B", "lat": 24.1368, "lon": 120.6862}]


def test_favorites_payload_skips_malformed_entries():
    # Arrange：缺座標的 pin 不該讓整張地圖畫不出來
    favorites = [
        {"type": "pin", "name": "壞掉的地點"},
        {"type": "pin", "name": "好的地點", "lat": 24.0, "lon": 120.0},
    ]

    # Act
    pins = json.loads(favorites_payload(favorites))

    # Assert
    assert [p["name"] for p in pins] == ["好的地點"]
