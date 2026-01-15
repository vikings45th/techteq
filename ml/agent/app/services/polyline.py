from __future__ import annotations

from typing import List, Tuple
import math


def decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    """
    Google Mapsのエンコードされたpolylineを緯度経度のリストにデコードする
    
    Google Mapsで使用される標準のEncoded Polyline Algorithm Formatを実装。
    
    Args:
        encoded: エンコードされたpolyline文字列
    
    Returns:
        (緯度, 経度)のタプルのリスト
    """
    if not encoded:
        return []

    index = 0  # 文字列のインデックス
    lat = 0  # 緯度の累積値
    lng = 0  # 経度の累積値
    coordinates: List[Tuple[float, float]] = []  # 結果を格納するリスト

    length = len(encoded)

    while index < length:
        # 緯度をデコード
        shift = 0  # ビットシフト量
        result = 0  # デコード結果
        while True:
            if index >= length:
                return coordinates
            b = ord(encoded[index]) - 63  # ASCII文字を数値に変換（63を引く）
            index += 1
            result |= (b & 0x1F) << shift  # 下位5ビットを取得してシフト
            shift += 5
            if b < 0x20:  # 最上位ビットが0なら終了
                break
        # 符号付き数値に変換（最下位ビットが1なら負数）
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat  # 緯度の差分を累積

        # 経度をデコード（緯度と同じアルゴリズム）
        shift = 0
        result = 0
        while True:
            if index >= length:
                return coordinates
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng  # 経度の差分を累積

        # 1e5で割って実際の緯度経度に変換（エンコード時は1e5倍している）
        coordinates.append((lat / 1e5, lng / 1e5))
    return coordinates


def sample_points(points: List[Tuple[float, float]], ratios: List[float]) -> List[Tuple[float, float]]:
    """
    polylineから指定された比率（0.0-1.0）の位置にある代表点を抽出する
    
    25%/50%/75%の位置の点を安定して抽出する改良アルゴリズム:
    - 1点の場合: その点を返す
    - 2点の場合: 両方の点を返す（0%と100%）
    - 3点以上の場合: 指定された比率（25%, 50%, 75%）の位置の点を返す
    
    Args:
        points: (緯度, 経度)のタプルのリスト
        ratios: 抽出する位置の比率のリスト（例: [0.25, 0.5, 0.75]）
    
    Returns:
        抽出された代表点のリスト（重複除去済み、順序保持）
    """
    if not points:
        return []
    n = len(points)
    
    # エッジケースの処理
    if n == 1:
        return [points[0]]  # 1点のみの場合はその点を返す
    if n == 2:
        # 2点の場合は両方返す（開始点と終了点）
        return [points[0], points[1]]
    
    out: List[Tuple[float, float]] = []
    for r in ratios:
        r = max(0.0, min(1.0, float(r)))  # 比率を0.0-1.0の範囲にクランプ
        # floorを使用して安定したインデックスを確保: 0.25 -> floor(0.25 * (n-1))
        # これにより25%は開始に近く、50%は中間、75%は終了に近くなる
        idx = int(r * (n - 1))
        # 有効な範囲にクランプ
        idx = max(0, min(n - 1, idx))
        out.append(points[idx])
    
    # 順序を保持しながら重複を除去
    uniq: List[Tuple[float, float]] = []
    seen = set()
    for p in out:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """
    2点間の距離をメートルで計算する（haversine）
    """
    lat1, lng1 = a
    lat2, lng2 = b
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(h)))


def _point_segment_distance_m(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> float:
    """
    点pと線分abの最短距離（メートル、平面近似）
    """
    if a == b:
        return _haversine_m(p, a)

    lat0 = math.radians((a[0] + b[0]) / 2.0)
    r = 6371000.0
    ax = math.radians(a[1]) * math.cos(lat0) * r
    ay = math.radians(a[0]) * r
    bx = math.radians(b[1]) * math.cos(lat0) * r
    by = math.radians(b[0]) * r
    px = math.radians(p[1]) * math.cos(lat0) * r
    py = math.radians(p[0]) * r

    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    ab_len2 = abx * abx + aby * aby
    if ab_len2 <= 0.0:
        return math.hypot(apx, apy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_len2))
    cx = ax + t * abx
    cy = ay + t * aby
    return math.hypot(px - cx, py - cy)


def simplify_douglas_peucker(
    points: List[Tuple[float, float]],
    epsilon_m: float = 20.0,
) -> List[Tuple[float, float]]:
    """
    Douglas–Peuckerで折れ線を簡略化する（メートル基準）
    """
    if len(points) <= 2:
        return points

    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True

    stack: List[Tuple[int, int]] = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        max_dist = -1.0
        index = None
        a = points[start]
        b = points[end]
        for i in range(start + 1, end):
            d = _point_segment_distance_m(points[i], a, b)
            if d > max_dist:
                max_dist = d
                index = i
        if index is not None and max_dist > epsilon_m:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))

    return [p for i, p in enumerate(points) if keep[i]]


def pick_waypoints(points: List[Tuple[float, float]], max_points: int = 10) -> List[Tuple[float, float]]:
    """
    点列から最大max_points個を均等に選ぶ（順序保持）
    """
    if not points:
        return []
    if len(points) <= max_points:
        return points
    n = len(points)
    step = (n - 1) / (max_points - 1)
    indices = [int(i * step) for i in range(max_points)]
    indices[-1] = n - 1
    return [points[i] for i in indices]
