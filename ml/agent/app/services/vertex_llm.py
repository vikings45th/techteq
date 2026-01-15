# vertex_llm.py
from __future__ import annotations

from typing import Optional, Any, Dict
import asyncio
import time
import logging

from google import genai
from google.genai import types

from app.settings import settings

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None  # Vertex AI GenAIクライアントのシングルトン


def _get_client() -> Optional[genai.Client]:
    """
    Vertex AI GenAIクライアントを取得（シングルトンパターン）
    
    Returns:
        GenAIクライアントインスタンス、またはNone（設定が不完全な場合）
    """
    global _client
    if not settings.VERTEX_PROJECT or not settings.VERTEX_LOCATION:
        return None
    if _client is None:
        _client = genai.Client(
            vertexai=True,  # Vertex AIを使用
            project=settings.VERTEX_PROJECT,  # GCPプロジェクトID
            location=settings.VERTEX_LOCATION,  # Vertex AIのリージョン
        )
    return _client


def _extract_text(resp: Any) -> str:
    """
    GenAI APIレスポンスからテキストを抽出する
    
    Args:
        resp: GenAI APIのレスポンスオブジェクト
    
    Returns:
        抽出されたテキスト（空文字列の場合は空文字列を返す）
    """
    # 直接text属性がある場合
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    # candidatesからテキストを抽出
    candidates = getattr(resp, "candidates", None)
    if candidates:
        c0 = candidates[0]  # 最初の候補を取得
        content = getattr(c0, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts:
            out = []
            # 各パートからテキストを抽出
            for p in parts:
                t = getattr(p, "text", None)
                if isinstance(t, str):
                    out.append(t)
            joined = "".join(out).strip()  # 結合して空白を除去
            if joined:
                return joined

    return ""  # テキストが見つからない場合は空文字列


def _safe_meta(resp: Any) -> Dict[str, Any]:
    """
    GenAI APIレスポンスからメタデータを安全に抽出する
    
    Args:
        resp: GenAI APIのレスポンスオブジェクト
    
    Returns:
        メタデータの辞書（usage_metadata, finish_reason, safety_ratings, has_partsを含む）
    """
    meta: Dict[str, Any] = {}
    meta["usage_metadata"] = getattr(resp, "usage_metadata", None)  # 使用量メタデータ（トークン数など）

    candidates = getattr(resp, "candidates", None)
    if candidates:
        c0 = candidates[0]  # 最初の候補
        meta["finish_reason"] = getattr(c0, "finish_reason", None)  # 終了理由（MAX_TOKENSなど）
        meta["safety_ratings"] = getattr(c0, "safety_ratings", None)  # 安全性評価

        content = getattr(c0, "content", None)
        parts = getattr(content, "parts", None) if content else None
        meta["has_parts"] = bool(parts)  # パーツ（テキスト）が存在するか
    else:
        meta["has_parts"] = False

    return meta


def _debug_dump(resp: Any) -> str:
    """
    レスポンスオブジェクトをデバッグ用の文字列に変換する
    
    Args:
        resp: GenAI APIのレスポンスオブジェクト
    
    Returns:
        デバッグ用の文字列表現（最大800文字、変換できない場合は"<unprintable>"）
    """
    try:
        s = str(resp)
        return s[:800]  # 最大800文字に制限
    except Exception:
        return "<unprintable>"  # 変換できない場合


def _spot_names(spots: Optional[list]) -> list[str]:
    """
    spotsから名前のリストを抽出する（dict/オブジェクト両対応）
    """
    if not spots:
        return []
    names: list[str] = []
    for s in spots:
        name = None
        if isinstance(s, dict):
            name = s.get("name")
        else:
            name = getattr(s, "name", None)
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _fallback_summary(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    """
    LLMが失敗した場合に使用する、テーマごとの簡潔な紹介文を返すフォールバック関数
    
    Args:
        theme: テーマ（"think", "exercise", "refresh", "nature"）
        distance_km: 距離（km）
        duration_min: 所要時間（分）
        spots: 見どころスポットのリスト（未使用）
    
    Returns:
        テーマに応じた紹介文
    """
    # テーマごとの簡潔な紹介文（定型文ではなく、自然な表現）
    theme_summaries = {
        "think": f"信号が少なく一定のリズムで歩ける約{distance_km:.1f}kmのルート。頭の中を整理するのに最適です。",
        "exercise": f"坂道や階段を多く含む約{distance_km:.1f}kmのルート。心拍数を上げてしっかり汗をかきましょう。",
        "refresh": f"賑やかな通りを歩く約{distance_km:.1f}kmのルート。エネルギーをチャージして気分転換できます。",
        "nature": f"緑豊かな公園をゆっくり抜ける約{distance_km:.1f}kmのルート。都会の喧騒から離れてリフレッシュできます。",
    }
    
    return theme_summaries.get(theme, f"約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける散歩コースです。")


def _fallback_title(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    """
    LLMが使えない場合のタイトル生成（内容に沿った短いタイトル）
    """
    theme_titles = {
        "think": "静けさの川沿い",
        "exercise": "アップダウン燃焼",
        "refresh": "街なかリフレッシュ",
        "nature": "木漏れ日の森歩き",
    }
    base = theme_titles.get(theme, "散歩")
    names = _spot_names(spots)
    if len(names) >= 2:
        return f"{names[0]}・{names[1]}を巡る{base}コース"
    if len(names) == 1:
        return f"{names[0]}から始まる{base}コース"
    return f"{base}コース"


def fallback_title(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    """
    外部から利用するフォールバックタイトル生成
    """
    return _fallback_title(theme, distance_km, duration_min, spots)


def _theme_to_natural(theme: str) -> str:
    """
    テーマコードを自然な日本語の説明に変換する
    
    Args:
        theme: テーマコード（"exercise", "think", "refresh", "nature"）
    
    Returns:
        自然な日本語の説明、または元のテーマコード（マッピングがない場合）
    """
    theme_map = {
        "exercise": "運動やエクササイズ",
        "think": "思考やリフレッシュ",
        "refresh": "気分転換やリフレッシュ",
        "nature": "自然や緑",
    }
    return theme_map.get(theme, theme)


def _build_prompt(theme: str, distance_km: float, duration_min: float, spots: Optional[list], *, strict: bool) -> str:
    """
    LLMに送信するプロンプトを生成する
    
    テーマごとの雰囲気を伝えるプロンプトを作成し、LLMが自然な紹介文を生成できるようにする。
    
    Args:
        theme: テーマ（"think", "exercise", "refresh", "nature"）
        distance_km: 距離（km）
        duration_min: 所要時間（分）
        spots: 見どころスポットのリスト（未使用）
        strict: Trueの場合、リトライ用の簡潔なプロンプトを生成
    
    Returns:
        LLMに送信するプロンプト文字列
    """
    # テーマごとの雰囲気・特徴の説明
    theme_descriptions = {
        "think": "思考や頭の整理に適した、信号が少なく一定のリズムで歩けるルート（例：川沿いの一本道など）。",
        "exercise": "運動やエクササイズに適した、坂道や階段を多く含む心拍数を上げるルート。",
        "refresh": "気分転換やリフレッシュに適した、賑やかな通りやお店が並ぶルート。",
        "nature": "自然や緑を楽しむ、都会の喧騒から離れた公園や緑豊かなルート。",
    }
    
    theme_desc = theme_descriptions.get(theme, f"約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける散歩コース。")

    if strict:
        # リトライ時：簡潔なプロンプト（MAX_TOKENSエラー対策）
        return (
            f"散歩ルートの紹介文を日本語で1文だけ（60文字前後）作成してください。"
            f"テーマの雰囲気を反映しつつ、自然で読みやすい文章にしてください。必ず句点「。」で終える。"
            f" テーマ: {theme_desc}"
            f" 距離: 約{distance_km:.1f}km。所要時間: 約{duration_min:.0f}分。"
        )

    # 通常時：自然な文章を生成するプロンプト
    return (
        f"散歩ルートの紹介文を日本語で1文だけ（40〜70文字程度）作成してください。"
        f"テーマの雰囲気や特徴を自然に反映し、読みやすく簡潔な文章にしてください。必ず句点「。」で終える。"
        f" テーマ: {theme_desc}"
        f" 距離: 約{distance_km:.1f}km。所要時間: 約{duration_min:.0f}分。"
    )


def _build_title_prompt(theme: str, distance_km: float, duration_min: float, spots: Optional[list], *, strict: bool) -> str:
    """
    LLMに送信するタイトル生成プロンプトを作成する
    """
    theme_descriptions = {
        "think": "思考や頭の整理に向いた静かな散歩",
        "exercise": "運動やエクササイズ向きの坂道・階段のある散歩",
        "refresh": "気分転換に適した賑やかな街歩き",
        "nature": "自然や緑を楽しむ落ち着いた散歩",
    }
    theme_desc = theme_descriptions.get(theme, "散歩コース")
    names = _spot_names(spots)
    spots_text = f" 見どころ: {', '.join(names[:4])}。" if names else ""
    if strict:
        return (
            "散歩コースのタイトルを日本語で1つ作成してください。"
            "12〜24文字程度。句点不要。汎用的すぎる表現は避ける。"
            "記号は「・」「〜」のみ使用可。"
            f" テーマ: {theme_desc}。距離: 約{distance_km:.1f}km。"
            f" 所要時間: 約{duration_min:.0f}分。{spots_text}"
        )
    return (
        "散歩コースのタイトルを日本語で1つ作成してください。"
        "10〜26文字程度。句点不要。コース内容に沿った具体的な表現にする。"
        "記号は「・」「〜」のみ使用可。"
        f" テーマ: {theme_desc}。距離: 約{distance_km:.1f}km。"
        f" 所要時間: 約{duration_min:.0f}分。{spots_text}"
    )


def _normalize_title(text: str) -> str:
    """
    LLM出力をタイトルとして整形する
    """
    if not text:
        return ""
    t = text.strip()
    if "\n" in t:
        t = t.splitlines()[0].strip()
    # 先頭/末尾の引用符を除去
    for q in ("「", "」", '"', "'"):
        t = t.strip(q)
    return t.strip()


def _build_config(*, temperature: float, max_output_tokens: int) -> types.GenerateContentConfig:
    """
    GenAI APIの生成設定を構築する
    
    Args:
        temperature: 温度パラメータ（0.0-1.0、低いほど一貫性が高い）
        max_output_tokens: 最大出力トークン数
    
    Returns:
        GenerateContentConfigオブジェクト
    """
    top_p = float(getattr(settings, "VERTEX_TOP_P", 0.95))  # Top-pサンプリングパラメータ
    top_k = int(getattr(settings, "VERTEX_TOP_K", 40))  # Top-kサンプリングパラメータ

    return types.GenerateContentConfig(
        temperature=temperature,  # 温度パラメータ
        max_output_tokens=max_output_tokens,  # 最大出力トークン数
        top_p=top_p,  # Top-pサンプリング
        top_k=top_k,  # Top-kサンプリング
        # thinking_config は thinking_budget パラメータをサポートしていないため削除
    )


async def _call_genai(client: genai.Client, model: str, prompt: str, cfg: types.GenerateContentConfig) -> Any:
    """
    GenAI APIを非同期で呼び出す
    
    SDKは同期関数のため、asyncio.to_thread()を使用して非同期実行する。
    
    Args:
        client: GenAIクライアントインスタンス
        model: モデル名
        prompt: プロンプト文字列
        cfg: 生成設定
    
    Returns:
        GenAI APIのレスポンスオブジェクト
    """
    return await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt,
        config=cfg,
    )


async def generate_summary(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> Optional[str]:
    """
    1文の散歩ルート紹介文を生成（Google Gen AI SDK / Vertex AI）

    重要:
    - SDK は同期関数のため asyncio.to_thread() で呼び出す
    - 失敗/空ならフォールバック文を返してUXを安定化
    - MAX_TOKENSエラーの場合はリトライを試みる
    
    Args:
        theme: テーマ（"think", "exercise", "refresh", "nature"）
        distance_km: 距離（km）
        duration_min: 所要時間（分）
        spots: 見どころスポットのリスト（未使用）
    
    Returns:
        生成された紹介文、またはNone（設定が不完全な場合）
    """
    model_name = settings.VERTEX_TEXT_MODEL
    if not model_name:
        return None

    client = _get_client()
    if client is None:
        return None

    # 通常設定
    temperature = float(getattr(settings, "VERTEX_TEMPERATURE", 0.3))  # 温度パラメータ
    max_out = int(float(getattr(settings, "VERTEX_MAX_OUTPUT_TOKENS", 256)))  # 最大出力トークン数

    # 1回目のAPI呼び出し
    prompt = _build_prompt(theme, distance_km, duration_min, spots, strict=False)
    cfg = _build_config(temperature=temperature, max_output_tokens=max_out)

    top_p = float(getattr(settings, "VERTEX_TOP_P", 0.95))
    top_k = int(getattr(settings, "VERTEX_TOP_K", 40))
    logger.info(
        "[GenAI SDK Call] model=%s temp=%.2f max_out=%d top_p=%.2f top_k=%d",
        model_name, temperature, max_out, top_p, top_k
    )

    t0 = time.time()
    try:
        resp = await _call_genai(client, model_name, prompt, cfg)
        text = _extract_text(resp)  # レスポンスからテキストを抽出
        meta = _safe_meta(resp)  # メタデータを取得

        dt = int((time.time() - t0) * 1000)
        logger.info("[GenAI SDK Done] elapsed_ms=%s text_len=%s meta=%s", dt, len(text) if text else 0, meta)

        if text:
            return text  # テキストが取得できた場合は返す

        # 空で、かつ MAX_TOKENS のときだけリトライ
        if str(meta.get("finish_reason")) == "FinishReason.MAX_TOKENS" or meta.get("finish_reason") == "MAX_TOKENS":
            logger.warning("[GenAI SDK Empty/MAX_TOKENS] retrying once. meta=%s resp=%s", meta, _debug_dump(resp))

            # リトライ: より簡潔なプロンプトと、より大きなトークン上限で再試行
            retry_prompt = _build_prompt(theme, distance_km, duration_min, spots, strict=True)
            retry_cfg = _build_config(
                temperature=min(temperature, 0.2),   # ブレ抑制（温度を下げる）
                max_output_tokens=max(max_out, 1024), # 上限増（ログで561トークン必要だったため）
            )
            resp2 = await _call_genai(client, model_name, retry_prompt, retry_cfg)
            text2 = _extract_text(resp2)
            meta2 = _safe_meta(resp2)

            dt2 = int((time.time() - t0) * 1000)
            logger.info("[GenAI SDK Retry Done] elapsed_ms=%s text_len=%s meta=%s", dt2, len(text2) if text2 else 0, meta2)

            if text2:
                return text2  # リトライでテキストが取得できた場合は返す

            logger.warning("[GenAI SDK Retry Empty] meta=%s resp=%s", meta2, _debug_dump(resp2))

        # それ以外の空はフォールバック（定型文を返す）
        return _fallback_summary(theme, distance_km, duration_min, spots)

    except Exception as e:
        # 例外が発生した場合もフォールバックを返す
        dt = int((time.time() - t0) * 1000)
        logger.exception("[GenAI SDK Error] elapsed_ms=%s err=%r", dt, e)
        return _fallback_summary(theme, distance_km, duration_min, spots)


async def generate_title(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> Optional[str]:
    """
    散歩ルートのタイトルを生成（Google Gen AI SDK / Vertex AI）
    """
    model_name = settings.VERTEX_TEXT_MODEL
    if not model_name:
        return None

    client = _get_client()
    if client is None:
        return None

    temperature = float(getattr(settings, "VERTEX_TEMPERATURE", 0.3))
    max_out = int(float(getattr(settings, "VERTEX_MAX_OUTPUT_TOKENS", 64)))

    prompt = _build_title_prompt(theme, distance_km, duration_min, spots, strict=False)
    cfg = _build_config(temperature=min(temperature + 0.1, 0.6), max_output_tokens=max_out)

    t0 = time.time()
    try:
        resp = await _call_genai(client, model_name, prompt, cfg)
        text = _extract_text(resp)
        meta = _safe_meta(resp)

        dt = int((time.time() - t0) * 1000)
        logger.info("[GenAI SDK Title Done] elapsed_ms=%s text_len=%s meta=%s", dt, len(text) if text else 0, meta)

        if text:
            normalized = _normalize_title(text)
            if normalized:
                return normalized

        if str(meta.get("finish_reason")) == "FinishReason.MAX_TOKENS" or meta.get("finish_reason") == "MAX_TOKENS":
            logger.warning("[GenAI SDK Title Empty/MAX_TOKENS] retrying once. meta=%s resp=%s", meta, _debug_dump(resp))
            retry_prompt = _build_title_prompt(theme, distance_km, duration_min, spots, strict=True)
            retry_cfg = _build_config(
                temperature=min(temperature, 0.2),
                max_output_tokens=max(max_out, 128),
            )
            resp2 = await _call_genai(client, model_name, retry_prompt, retry_cfg)
            text2 = _extract_text(resp2)
            meta2 = _safe_meta(resp2)

            dt2 = int((time.time() - t0) * 1000)
            logger.info("[GenAI SDK Title Retry Done] elapsed_ms=%s text_len=%s meta=%s", dt2, len(text2) if text2 else 0, meta2)

            normalized2 = _normalize_title(text2)
            if normalized2:
                return normalized2

            logger.warning("[GenAI SDK Title Retry Empty] meta=%s resp=%s", meta2, _debug_dump(resp2))

        return _fallback_title(theme, distance_km, duration_min, spots)

    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        logger.exception("[GenAI SDK Title Error] elapsed_ms=%s err=%r", dt, e)
        return _fallback_title(theme, distance_km, duration_min, spots)
