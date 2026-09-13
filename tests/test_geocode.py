"""geocode.py 的回應解析測試（不發出任何網路請求）。"""

from gps_qt.geocode import parse_results


def test_parse_results_converts_string_coordinates_to_float():
    # Arrange：Nominatim 的 lat/lon 是字串
    raw = [{"display_name": "臺中車站, 中區, 臺中市", "lat": "24.1368", "lon": "120.6862"}]

    # Act
    results = parse_results(raw)

    # Assert
    assert results == [{"name": "臺中車站, 中區, 臺中市", "lat": 24.1368, "lon": 120.6862}]


def test_parse_results_skips_entries_without_coordinates():
    # Arrange：偶爾會回傳沒有座標的項目，不該讓整次查詢失敗
    raw = [
        {"display_name": "沒有座標"},
        {"display_name": "有座標", "lat": "24.0", "lon": "120.0"},
    ]

    # Act
    results = parse_results(raw)

    # Assert
    assert [r["name"] for r in results] == ["有座標"]


def test_parse_results_returns_empty_list_for_unexpected_shape():
    # Arrange / Act / Assert：錯誤回應通常是 dict 而非 list
    assert parse_results({"error": "Unable to geocode"}) == []
