"""
전체 파이프라인 (GitHub Actions 실행용)
스크래핑 → Supabase 저장 → Claude 분석 → 완료
"""

import asyncio
import re
import random
import sys
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from db import upsert_product, save_rankings
from analyzer import run as run_analysis

CATEGORIES = {
    "스킨/토너":       "100000100010013",
    "에센스/세럼/앰플": "100000100010014",
    "크림":            "100000100010015",
    "로션":            "100000100010016",
    "미스트/오일":      "100000100010017",
    "시트팩":          "100000100020013",
    "패드":            "100000100020014",
    "클렌징폼/젤":     "100000100030013",
    "오일/밤":         "100000100030014",
    "선크림":          "100000100040013",
    "선스틱":          "100000100040014",
    "선쿠션":          "100000100040015",
    "립메이크업":      "100000100050013",
    "베이스메이크업":  "100000100050014",
    "아이메이크업":    "100000100050015",
    "샴푸/스케일러":   "100000100060013",
    "트리트먼트/팩":   "100000100060014",
    "샤워/입욕":       "100000100070013",
    "향수":            "100000100080013",
}

BASE  = "https://www.oliveyoung.co.kr"
TOP_N = 10

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--window-size=1366,768",
]


async def make_context(browser):
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        viewport={"width": 1366, "height": 768},
        extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
    )
    await ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "Object.defineProperty(navigator,'languages',{get:()=>['ko-KR','ko']});"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3]});"
    )
    return ctx


async def get_urls(page, cat_no: str) -> list[str]:
    url = (f"{BASE}/store/display/getMCategoryList.do"
           f"?dispCatNo={cat_no}&fltDispCatNo=&prdSort=03"
           f"&pageIdx=1&rowsPerPage=24&searchTypeSort=btn_thumb")
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(random.randint(2000, 3500))
    links = []
    for el in await page.query_selector_all("a.prd_thumb"):
        href = await el.get_attribute("href") or ""
        m = re.search(r"goodsNo=([A-Za-z0-9]+)", href)
        if m:
            links.append(f"{BASE}/store/goods/getGoodsDetail.do?goodsNo={m.group(1)}")
    return list(dict.fromkeys(links))[:TOP_N]


async def get_text(page, sel: str) -> str:
    try:
        el = await page.query_selector(sel)
        return (await el.inner_text()).strip() if el else ""
    except:
        return ""


def split_ingredients(raw: str) -> list[str]:
    raw = re.sub(r"\[.*?\]", "", raw)
    items = re.split(r"[,/]", raw)
    result = []
    for item in items:
        item = item.strip().strip(".")
        if len(item) > 100 and "," not in item:
            result.extend(s for s in item.split() if 2 <= len(s) <= 80)
        elif 2 <= len(item) <= 80:
            result.append(item)
    return result


async def get_ingredients(page) -> tuple[str, list[str]]:
    try:
        btns = await page.query_selector_all("[class*='Accordion_accordion-btn']")
        target = None
        for btn in btns:
            if "상품정보" in (await btn.inner_text()):
                target = btn
                break
        if not target and btns:
            target = btns[0]
        if target and await target.get_attribute("aria-expanded") == "false":
            await target.click()
            await page.wait_for_selector("[class*='Accordion_table']", timeout=10_000)
        await page.wait_for_timeout(400)
    except:
        pass

    for sel in ["[class*='Accordion_table'] tr", "table tr"]:
        for row in await page.query_selector_all(sel):
            try:
                th = await row.query_selector("th")
                td = await row.query_selector("td")
                if not th or not td:
                    continue
                th_text = await th.inner_text()
                if "기재해야" in th_text or "전성분" in th_text:
                    raw = (await td.inner_text()).strip()
                    if len(raw) > 20:
                        return raw, split_ingredients(raw)
            except:
                continue

    try:
        body = await page.inner_text("body")
        m = re.search(r"(정제수|Water|Aqua)[^\n]{80,}", body, re.I)
        if m:
            raw = m.group(0).strip()
            return raw, split_ingredients(raw)
    except:
        pass
    return "", []


async def scrape_product(page, url, rank, cat, retry=0) -> dict | None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(random.randint(2500, 4000))
    except PWTimeout:
        return None

    brand = await get_text(page, "[class*='TopUtils_btn-brand']")
    name  = await get_text(page, "[class*='GoodsDetailInfo_title']")
    if not name:
        title = await page.title()
        name  = title.replace("| 올리브영", "").strip()
    if not name:
        return None

    ing_raw, ing_list = await get_ingredients(page)
    if not ing_list and retry < 2:
        await asyncio.sleep((retry + 1) * 3)
        return await scrape_product(page, url, rank, cat, retry + 1)

    price      = await get_text(page, "[class*='SalePrice']") or await get_text(page, ".price-1 strong")
    rating_txt = await get_text(page, "[class*='ReviewStar']") or await get_text(page, ".review_point")
    review_txt = await get_text(page, "[class*='ReviewCount']") or await get_text(page, ".review_count")
    img_el     = await page.query_selector("[class*='GoodsImage'] img, .prd_detail_img img")
    img_url    = (await img_el.get_attribute("src") or "") if img_el else ""

    m_r = re.search(r"[\d.]+", rating_txt)
    m_v = re.search(r"[\d,]+", review_txt)

    ok = "✅" if ing_list else "⚠️"
    print(f"{ok} {brand} {name[:25]} ({len(ing_list)}개 성분)")

    return {
        "rank": rank, "category": cat,
        "brand": brand, "name": name, "price": price,
        "url": url, "image_url": img_url,
        "rating":           float(m_r.group()) if m_r else 0,
        "review_count":     int(m_v.group().replace(",", "")) if m_v else 0,
        "ingredients_raw":  ing_raw,
        "ingredients_list": ing_list,
    }


async def scrape_all(target_cats=None) -> dict:
    cats = {k: v for k, v in CATEGORIES.items()
            if target_cats is None or k in target_cats}
    result = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        for cat_name, cat_no in cats.items():
            print(f"\n  [{cat_name}]")
            ctx  = await make_context(browser)
            page = await ctx.new_page()
            products = []
            try:
                await page.goto(BASE, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(random.randint(1500, 2500))
                urls = await get_urls(page, cat_no)
                print(f"  URL {len(urls)}개 수집")
                for i, url in enumerate(urls, 1):
                    print(f"    [{i:2d}/{TOP_N}] ", end="", flush=True)
                    p = await scrape_product(page, url, i, cat_name)
                    if p:
                        products.append(p)
                    await asyncio.sleep(random.uniform(2.0, 3.5))
            except Exception as e:
                print(f"  ❌ {e}")
            finally:
                await ctx.close()
            result[cat_name] = products
            await asyncio.sleep(random.uniform(3, 5))
        await browser.close()
    return result


def save_all(all_products: dict):
    print("\n💾 Supabase 저장 중...")
    new_total = skip_total = 0
    for cat_name, products in all_products.items():
        ranked = []
        for p in products:
            if not p.get("brand") or not p.get("name"):
                continue
            pid, is_new = upsert_product(p)
            if is_new:
                new_total += 1
                print(f"  ✅ 신규: {p['brand']} {p['name'][:30]}")
            else:
                skip_total += 1
                print(f"  ⏭️  중복: {p['brand']} {p['name'][:30]}")
            ranked.append({"product_id": pid, "rank": p["rank"]})
        if ranked:
            save_rankings(cat_name, ranked)
    print(f"\n  신규 {new_total}개 / 중복 스킵 {skip_total}개")


async def main():
    target = sys.argv[1:] or None
    start  = datetime.now()
    print("=" * 60)
    print(f"  뷰티랭크 파이프라인: {start.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\n🔍 STEP 1: 스크래핑")
    all_products = await scrape_all(target)

    print("\n💾 STEP 2: DB 저장")
    save_all(all_products)

    print("\n🤖 STEP 3: Claude 성분 분석")
    run_analysis()

    elapsed = int((datetime.now() - start).total_seconds() // 60)
    print(f"\n{'='*60}")
    print(f"  ✅ 완료! 소요 {elapsed}분")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
