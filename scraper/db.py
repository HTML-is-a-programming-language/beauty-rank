"""
Supabase DB 연산
환경변수: SUPABASE_URL, SUPABASE_KEY (service_role key)
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]   # service_role key (서버용)
        _client = create_client(url, key)
    return _client


def ingredient_hash(ingredients_list: list[str]) -> str:
    normalized = ",".join(sorted(i.strip().lower() for i in ingredients_list))
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def upsert_product(product: dict) -> tuple[int, bool]:
    """
    저장 또는 업데이트.
    반환: (product_id, is_new)
    """
    sb  = get_client()
    now = datetime.now(timezone.utc).isoformat()
    ing_list = product.get("ingredients_list", [])
    ing_hash = ingredient_hash(ing_list)

    # 중복 확인
    res = sb.table("products").select("id").eq("brand", product["brand"]) \
            .eq("name", product["name"]).eq("ingredient_hash", ing_hash) \
            .execute()

    if res.data:
        pid = res.data[0]["id"]
        # last_seen / 가격 / 리뷰 업데이트
        sb.table("products").update({
            "last_seen":    now,
            "price":        product.get("price", ""),
            "rating":       product.get("rating", 0),
            "review_count": product.get("review_count", 0),
            "image_url":    product.get("image_url", ""),
        }).eq("id", pid).execute()
        return pid, False

    # 신규 INSERT
    res = sb.table("products").insert({
        "brand":           product["brand"],
        "name":            product["name"],
        "category":        product["category"],
        "price":           product.get("price", ""),
        "url":             product.get("url", ""),
        "image_url":       product.get("image_url", ""),
        "rating":          product.get("rating", 0),
        "review_count":    product.get("review_count", 0),
        "ingredient_hash": ing_hash,
        "ingredients_raw": product.get("ingredients_raw", ""),
    }).execute()
    pid = res.data[0]["id"]

    # 성분 INSERT
    if ing_list:
        sb.table("ingredients").insert([
            {"product_id": pid, "name": name, "position": i}
            for i, name in enumerate(ing_list)
        ]).execute()

    return pid, True


def save_analysis(product_id: int, analysis: dict):
    sb = get_client()
    sb.table("analyses").upsert({
        "product_id":        product_id,
        "score":             analysis.get("score", 0),
        "grade":             analysis.get("grade", ""),
        "highlights":        analysis.get("highlights", []),
        "warnings":          analysis.get("warnings", []),
        "tags":              analysis.get("tags", []),
        "summary":           analysis.get("summary", ""),
        "ewg_risk":          analysis.get("ewg_risk", ""),
        "is_vegan":          analysis.get("is_vegan_likely", False),
        "is_fragrance_free": analysis.get("is_fragrance_free", False),
        "is_alcohol_free":   analysis.get("is_alcohol_free", False),
        "analyzed_at":       datetime.now(timezone.utc).isoformat(),
    }, on_conflict="product_id").execute()


def save_rankings(category: str, ranked: list[dict]):
    sb  = get_client()
    now = datetime.now(timezone.utc).isoformat()
    sb.table("rankings").insert([
        {"category": category, "product_id": p["product_id"],
         "rank": p["rank"], "ranked_at": now}
        for p in ranked
    ]).execute()


def get_unanalyzed(limit: int = 200) -> list[dict]:
    """분석 안 된 제품 목록"""
    sb  = get_client()
    # analyses에 없는 product
    all_ids_res = sb.table("analyses").select("product_id").execute()
    analyzed    = {r["product_id"] for r in all_ids_res.data}

    res = sb.table("products").select(
        "id, brand, name, category, ingredients_raw"
    ).execute()

    result = []
    for p in res.data:
        if p["id"] not in analyzed and p.get("ingredients_raw"):
            result.append(p)
        if len(result) >= limit:
            break
    return result
