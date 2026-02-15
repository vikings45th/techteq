"""UIマイクロコピーのポストプロセス（タイトル・説明文の補正・正規化）"""


def normalize_title(title: str) -> str:
    """タイトルを補正する。短すぎる場合はデフォルトを返す。"""
    title = title.strip()
    banned = ["おすすめ", "コース", "!"]
    for w in banned:
        title = title.replace(w, "")
    title = title.strip()
    if len(title) < 4:
        return "静かな道"
    return title


def normalize_description(
    desc: str,
    theme: str,
    distance_km: float,
    duration_min: float,
) -> str:
    """説明文を補正する。短い場合はサフィックスを付与。禁止語を除去。"""
    desc = desc.strip()
    if len(desc) < 60:
        suffix = f" 約{distance_km:.1f}kmを{duration_min:.0f}分ほどの長さです。途中で戻っても問題ありません。"
        desc = desc + suffix

    banned = ["おすすめ", "ぴったり", "今すぐ", "絶対", "完了", "!"]
    for w in banned:
        desc = desc.replace(w, "")
    return desc.strip()
