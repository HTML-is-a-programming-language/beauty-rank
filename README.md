# 뷰티랭크 — 클라우드 설정 가이드

## 구조
```
GitHub Actions (매월 1일) → Supabase (DB) → GitHub Pages (사이트)
```

---

## STEP 1 — Supabase 설정

1. [supabase.com](https://supabase.com) 가입 → 새 프로젝트 생성
2. `SQL Editor` → `sql/schema.sql` 전체 복붙 → Run
3. `Settings → API` 에서 아래 값 복사:
   - `Project URL`  → SUPABASE_URL
   - `anon public`  → 사이트 HTML에 입력
   - `service_role` → SUPABASE_KEY (GitHub Secrets에 저장)

---

## STEP 2 — GitHub 설정

1. 이 폴더를 GitHub 저장소로 push
2. `Settings → Secrets → Actions` 에서 3개 등록:
   - `ANTHROPIC_API_KEY` : sk-ant-...
   - `SUPABASE_URL`      : https://xxxx.supabase.co
   - `SUPABASE_KEY`      : service_role key

---

## STEP 3 — 사이트 설정

`site/index.html` 상단 2줄 교체:
```js
const SUPABASE_URL  = "https://본인URL.supabase.co";
const SUPABASE_ANON = "본인 anon public key";
```

---

## STEP 4 — GitHub Pages 배포

`Settings → Pages → Source: Deploy from branch`
- Branch: `main` / Folder: `/site`
- 주소: `https://본인아이디.github.io/저장소명`

---

## STEP 5 — 첫 실행 (수동)

GitHub Actions → `뷰티랭크 월간 업데이트` → `Run workflow`

이후 매월 1일 02:00 KST 자동 실행

---

## 자동화 흐름

```
매월 1일 02:00 KST
  → GitHub Actions 실행
  → 올리브영 전 카테고리 판매순 TOP10 스크래핑
  → Supabase 저장 (중복 스킵)
  → 신규 제품만 Claude API 성분 분석
  → 완료 (사이트는 Supabase에서 실시간 조회)
```
