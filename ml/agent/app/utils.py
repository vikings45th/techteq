from typing import Dict


def translate_place_type_to_japanese(place_type: str) -> str:
    """
    Places APIの場所タイプを日本語に変換する

    Args:
        place_type: Places APIの場所タイプ（例: "park", "cafe"）

    Returns:
        日本語の場所タイプ名
    """
    type_mapping: Dict[str, str] = {
        "park": "公園",
        "gym": "ジム",
        "sports_complex": "スポーツ施設",
        "fitness_center": "フィットネスセンター",
        "hiking_area": "ハイキングエリア",
        "cycling_park": "サイクリングパーク",
        "stadium": "スタジアム",
        "sports_club": "スポーツクラブ",
        "sports_activity_location": "スポーツ活動場所",
        "swimming_pool": "プール",
        "athletic_field": "運動場",
        "playground": "遊び場",
        "arena": "アリーナ",
        "library": "図書館",
        "museum": "博物館",
        "cafe": "カフェ",
        "art_gallery": "美術館",
        "book_store": "書店",
        "university": "大学",
        "school": "学校",
        "auditorium": "講堂",
        "cultural_center": "文化センター",
        "performing_arts_theater": "劇場",
        "restaurant": "レストラン",
        "tourist_attraction": "観光スポット",
        "beach": "ビーチ",
        "botanical_garden": "植物園",
        "garden": "庭園",
        "plaza": "広場",
        "observation_deck": "展望台",
        "amusement_park": "遊園地",
        "water_park": "ウォーターパーク",
        "national_park": "国立公園",
        "state_park": "州立公園",
        "wildlife_park": "野生動物公園",
        "wildlife_refuge": "野生動物保護区",
        "zoo": "動物園",
        "unknown": "その他",
    }
    return type_mapping.get(place_type, place_type)
