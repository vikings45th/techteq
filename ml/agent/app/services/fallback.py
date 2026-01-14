from typing import Any, Dict, List, Optional


def choose_best_route(
    candidates: List[Dict[str, Any]],
    scores: Dict[str, float],
    theme: str,
) -> Optional[Dict[str, Any]]:
    """
    候補ルートから最適なルートを選択する
    
    選択ルール:
    1. テーマが一致する候補を優先
    2. 同じテーマ内では、スコアが最も高いものを選択
    3. スコアが利用できない場合は、テーマ一致候補の最初のものを選択
    
    Args:
        candidates: 候補ルートのリスト [{"route_id": "...", "theme": "...", ...}, ...]
        scores: ルートIDからスコアへのマッピング
        theme: 対象テーマ
    
    Returns:
        選択されたルート候補、またはNone（候補がない場合）
    """
    # テーマが一致する候補を抽出
    themed = [c for c in candidates if c.get("theme") == theme]
    # テーマ一致候補があればそれを使用、なければ全候補を使用
    pool = themed if themed else candidates
    if not pool:
        return None

    # 各候補にスコアを紐付け
    scored = [(c, scores.get(c["route_id"])) for c in pool]
    # スコアが存在する候補を抽出
    scored_with = [x for x in scored if x[1] is not None]
    if scored_with:
        # スコアの高い順にソートして、最も高いものを返す
        scored_with.sort(key=lambda x: x[1], reverse=True)
        return scored_with[0][0]

    # スコアが利用できない場合: 決定論的フォールバック（最初の候補を返す）
    return pool[0]
