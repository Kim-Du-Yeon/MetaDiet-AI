-- migrations/add_source_column.sql
-- meal_logs.source: 영양성분 출처 추적 ("csv" | "llm_estimated")
-- Supabase SQL Editor에서 직접 실행 (이 스크립트는 자동 실행되지 않음)

ALTER TABLE meal_logs ADD COLUMN IF NOT EXISTS source TEXT;
