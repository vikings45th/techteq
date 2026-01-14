from __future__ import annotations

from typing import List, Tuple


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
