-- migrations/add_region_column.sql
-- 지역 기반 영양 기준 우선순위(KR=KDRIs 우선, INTL=WHO 우선)
-- Supabase SQL Editor에서 직접 실행 (이 스크립트는 자동 실행되지 않음)

ALTER TABLE users ADD COLUMN IF NOT EXISTS region TEXT DEFAULT 'KR'
  CHECK (region IN ('KR', 'INTL'));
