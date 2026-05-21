"""
미분석 제품 → Claude API → Supabase 저장
"""

import json
import time
import os
import anthropic
from db import get_unanalyzed, save_analysis

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM = "화장품 성분 전문가입니다. JSON만 반환하세요. 다른 텍스트 없이 JSON만."

PROMPT = """화장품 전성분을 분석해 JSON으로만 응답하세요.

제품: {brand} {name}
전성분: {ingredients}

{{
  "score": 0~100 정수,
  "grade": "최우수"|"우수"|"양호"|"보통"|"주의",
  "highlights": ["장점 최대3개"],
  "warnings": ["주의성분 최대3개"],
  "tags": ["#태그1","#태그2","#태그3"],
  "summary": "25자 이내 한줄요약",
  "ewg_risk": "low"|"medium"|"high",
  "is_vegan_likely": true|false,
  "is_fragrance_free": true|false,
  "is_alcohol_free": true|false
}}

점수기준: 90~100 EWG저위험+기능성풍부, 80~89 안전, 70~79 보통, 60~69 주의성분있음, 60미만 고위험"""


def analyze(product: dict) -> dict | None:
    ingredients = product.get("ingredients_raw", "")
    if not ingredients or len(ingredients) < 10:
        return None
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=SYSTEM,
            messages=[{"role": "user", "content": PROMPT.format(
                brand=product.get("brand", ""),
                name=product.get("name", ""),
                ingredients=ingredients[:3000],
            )}]
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","")
        return json.loads(raw)
    except Exception as e:
        print(f"    ❌ 분석 실패: {e}")
        return None


def run():
    products = get_unanalyzed(limit=300)
    if not products:
        print("✅ 분석할 신규 제품 없음")
        return

    print(f"🤖 Claude API 분석: {len(products)}개")
    ok = fail = 0
    for i, p in enumerate(products, 1):
        print(f"  [{i:3d}/{len(products)}] {p['brand']} {p['name'][:28]}... ", end="", flush=True)
        result = analyze(p)
        if result:
            save_analysis(p["id"], result)
            print(f"✅ {result['score']}점 ({result['grade']})")
            ok += 1
        else:
            print("⚠️  스킵")
            fail += 1
        if i < len(products):
            time.sleep(0.3)

    print(f"\n  완료: 성공 {ok} / 실패 {fail}")


if __name__ == "__main__":
    run()
