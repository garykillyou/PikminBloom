"""routing.py 的解碼與解析測試（不發出任何網路請求）。"""

import pytest

from gps_qt.routing import decode_polyline6, parse_route


def _encode_polyline6(points):
    """測試用的 polyline6 編碼器，用來驗證 decode 能還原回原始座標。"""
    out = []
    prev_lat = prev_lon = 0
    for lat, lon in points:
        for value, prev in ((round(lat * 1e6), prev_lat), (round(lon * 1e6), prev_lon)):
            delta = value - prev
            delta = ~(delta << 1) if delta < 0 else (delta << 1)
            while delta >= 0x20:
                out.append(chr((0x20 | (delta & 0x1F)) + 63))
                delta >>= 5
            out.append(chr(delta + 63))
        prev_lat, prev_lon = round(lat * 1e6), round(lon * 1e6)
    return "".join(out)


def test_decode_polyline6_round_trips():
    # Arrange
    points = [(24.136800, 120.686200), (24.139000, 120.680000), (24.142000, 120.672000)]

    # Act
    decoded = decode_polyline6(_encode_polyline6(points))

    # Assert：精度 1e6 代表小數第六位，容差取到第七位
    assert decoded == pytest.approx(points, abs=1e-7)


def test_decode_polyline6_uses_1e6_not_1e5():
    """用錯精度不會報錯、只會讓座標差十倍，所以特別釘住這個行為。"""
    # Arrange / Act
    decoded = decode_polyline6(_encode_polyline6([(24.1368, 120.6862)]))

    # Assert
    assert decoded[0][0] == pytest.approx(24.1368, abs=1e-7)


def test_decode_polyline6_rejects_truncated_string():
    # Arrange：只有一半的編碼（缺經度）
    truncated = _encode_polyline6([(24.1368, 120.6862)])[:2]

    # Act / Assert
    with pytest.raises(ValueError):
        decode_polyline6(truncated)


def test_parse_route_joins_legs_without_duplicating_seam():
    # Arrange：前一段的終點等於下一段的起點，接起來不該出現重複座標
    shared = (24.139, 120.68)
    leg1 = [(24.1368, 120.6862), shared]
    leg2 = [shared, (24.142, 120.672)]
    raw = {"trip": {
        "legs": [{"shape": _encode_polyline6(leg1)}, {"shape": _encode_polyline6(leg2)}],
        "summary": {"length": 1.23, "time": 456},
    }}

    # Act
    points, length_km, time_sec = parse_route(raw)

    # Assert
    assert len(points) == 3
    assert length_km == 1.23
    assert time_sec == 456


def test_parse_route_returns_empty_for_missing_trip():
    # Arrange / Act
    points, length_km, time_sec = parse_route({"error": "No path could be found"})

    # Assert
    assert points == []
    assert (length_km, time_sec) == (0.0, 0.0)
