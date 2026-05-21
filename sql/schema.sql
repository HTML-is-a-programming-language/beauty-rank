-- ================================================================
-- 뷰티랭크 Supabase 스키마
-- Supabase → SQL Editor → 복붙 후 Run
-- ================================================================

-- 제품 테이블
CREATE TABLE IF NOT EXISTS products (
    id              BIGSERIAL PRIMARY KEY,
    brand           TEXT NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    price           TEXT,
    url             TEXT,
    image_url       TEXT,
    rating          NUMERIC(3,1) DEFAULT 0,
    review_count    INTEGER DEFAULT 0,
    ingredient_hash TEXT NOT NULL,
    ingredients_raw TEXT,
    first_seen      TIMESTAMPTZ DEFAULT NOW(),
    last_seen       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand, name, ingredient_hash)
);

-- 성분 테이블
CREATE TABLE IF NOT EXISTS ingredients (
    id          BIGSERIAL PRIMARY KEY,
    product_id  BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    position    INTEGER NOT NULL
);

-- 분석 결과 테이블
CREATE TABLE IF NOT EXISTS analyses (
    id                BIGSERIAL PRIMARY KEY,
    product_id        BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE UNIQUE,
    score             INTEGER,
    grade             TEXT,
    highlights        JSONB DEFAULT '[]',
    warnings          JSONB DEFAULT '[]',
    tags              JSONB DEFAULT '[]',
    summary           TEXT,
    ewg_risk          TEXT,
    is_vegan          BOOLEAN DEFAULT FALSE,
    is_fragrance_free BOOLEAN DEFAULT FALSE,
    is_alcohol_free   BOOLEAN DEFAULT FALSE,
    analyzed_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 순위 테이블
CREATE TABLE IF NOT EXISTS rankings (
    id          BIGSERIAL PRIMARY KEY,
    category    TEXT NOT NULL,
    product_id  BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    rank        INTEGER NOT NULL,
    ranked_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_products_category     ON products(category);
CREATE INDEX IF NOT EXISTS idx_rankings_category     ON rankings(category);
CREATE INDEX IF NOT EXISTS idx_rankings_ranked_at    ON rankings(ranked_at DESC);

-- ================================================================
-- 사이트용 뷰 (최신 순위 + 분석 조인)
-- ================================================================
CREATE OR REPLACE VIEW latest_rankings AS
WITH latest AS (
    SELECT category, MAX(ranked_at) AS latest_at
    FROM rankings
    GROUP BY category
)
SELECT
    r.category,
    r.rank,
    p.brand,
    p.name,
    p.price,
    p.url,
    p.image_url,
    p.rating,
    p.review_count,
    COALESCE(a.score, 0)          AS score,
    COALESCE(a.grade, '-')        AS grade,
    COALESCE(a.highlights, '[]')  AS highlights,
    COALESCE(a.warnings,   '[]')  AS warnings,
    COALESCE(a.tags,       '[]')  AS tags,
    COALESCE(a.summary,    '')    AS summary,
    r.ranked_at
FROM rankings r
JOIN latest       l ON l.category = r.category AND l.latest_at = r.ranked_at
JOIN products     p ON p.id = r.product_id
LEFT JOIN analyses a ON a.product_id = r.product_id
ORDER BY r.category, r.rank;

-- 익명 사용자에게 읽기 권한 부여 (사이트에서 anon key로 조회)
GRANT SELECT ON latest_rankings TO anon;
GRANT SELECT ON products        TO anon;
GRANT SELECT ON analyses        TO anon;
GRANT SELECT ON rankings        TO anon;
