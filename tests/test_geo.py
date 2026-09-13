"""geo.py 的純函式測試。"""

import math

import pytest

from gps_qt.geo import douglas_peucker, haversine, interpolate_points

EARTH_RADIUS_M = 6371000
ONE_DEGREE_LAT_M = math.radians(1) * EARTH_RADIUS_M  # 約 111194.9 公尺


def test_haversine_returns_zero_for_identical_points():
    # Arrange / Act
    distance = haversine(24.1368, 120.6862, 24.1368, 120.6862)

    # Assert
    assert distance == 0


def test_haversine_matches_one_degree_of_latitude():
    # Arrange / Act
    distance = haversine(24.0, 120.0, 25.0, 120.0)

    # Assert：容差 1 公尺
    assert distance == pytest.approx(ONE_DEGREE_LAT_M, abs=1.0)


def test_interpolate_points_keeps_both_endpoints():
    # Arrange
    route = [(24.0, 120.0, ""), (25.0, 120.0, "")]
    speed_ms = ONE_DEGREE_LAT_M / 10  # 每秒走十分之一段，預期切成 10 段

    # Act
    points = interpolate_points(route, speed_ms, 1.0)

    # Assert
    assert points[0] == (24.0, 120.0)
    assert points[-1] == (25.0, 120.0)
    assert len(points) == 11


def test_interpolate_points_handles_speed_faster_than_whole_route():
    # Arrange：速度快到一秒就走完整段，至少也要保留起點與終點
    route = [(24.0, 120.0, ""), (24.001, 120.0, "")]

    # Act
    points = interpolate_points(route, 10000.0, 1.0)

    # Assert
    assert points[0] == (24.0, 120.0)
    assert points[-1] == (24.001, 120.0)


def test_douglas_peucker_keeps_endpoints_and_drops_collinear_points():
    # Arrange：一條直線上均勻取點，中間點對路形沒有貢獻
    points = [(24.0 + i * 0.001, 120.0) for i in range(11)]

    # Act
    simplified = douglas_peucker(points, 5.0)

    # Assert
    assert simplified == [points[0], points[-1]]


def test_douglas_peucker_keeps_a_significant_corner():
    # Arrange：中間點偏離直線約 111 公尺，遠大於 5 公尺容差
    points = [(24.0, 120.0), (24.0005, 120.001), (24.0, 120.002)]

    # Act
    simplified = douglas_peucker(points, 5.0)

    # Assert
    assert simplified == points


def test_douglas_peucker_drops_a_corner_below_tolerance():
    # Arrange：中間點只偏離約 1 公分，遠小於 5 公尺容差
    points = [(24.0, 120.0), (24.0000001, 120.001), (24.0, 120.002)]

    # Act
    simplified = douglas_peucker(points, 5.0)

    # Assert
    assert simplified == [points[0], points[-1]]


def test_douglas_peucker_returns_input_when_disabled():
    # Arrange
    points = [(24.0, 120.0), (24.0005, 120.001), (24.0, 120.002)]

    # Act / Assert：容差 0 代表關閉簡化
    assert douglas_peucker(points, 0) == points


def test_douglas_peucker_handles_long_input_without_recursion_limit():
    # Arrange：用顯式堆疊而非遞迴，點數上千也不該撞到遞迴上限
    points = [(24.0 + i * 0.00001, 120.0 + (i % 2) * 0.00002) for i in range(3000)]

    # Act
    simplified = douglas_peucker(points, 5.0)

    # Assert
    assert simplified[0] == points[0]
    assert simplified[-1] == points[-1]
    assert len(simplified) < len(points)
