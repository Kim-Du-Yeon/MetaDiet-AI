-- migrations/add_goal_columns.sql
-- 장기 목표(Goal Manager Agent용): 목표 체중/날짜/우선순위
-- Supabase SQL Editor에서 직접 실행 (이 스크립트는 자동 실행되지 않음)

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS target_weight_kg FLOAT,
  ADD COLUMN IF NOT EXISTS target_date DATE,
  ADD COLUMN IF NOT EXISTS goal_priority TEXT CHECK (goal_priority IN ('speed','muscle','balance'));
