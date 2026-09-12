"""路線幾何計算：純函式，不相依任何 UI 框架。"""

import math


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def interpolate_points(route, speed_ms, interval_sec):
    points = []
    for i in range(len(route) - 1):
        lat1, lon1 = route[i][0], route[i][1]
        lat2, lon2 = route[i + 1][0], route[i + 1][1]
        dist = haversine(lat1, lon1, lat2, lon2)
        steps = max(1, int(dist / (speed_ms * interval_sec)))
        for s in range(steps):
            t = s / steps
            points.append((lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t))
    points.append((route[-1][0], route[-1][1]))
    return points
