-- =====================================================
-- db/schema.sql
-- Supabase SQL Editor에서 순서대로 실행
--
-- 기존 칼로리 앱과의 차이:
-- diet_strategies 테이블이 핵심.
-- 기존 앱은 오늘의 목표만 저장하지만,
-- 이 테이블은 인바디 변화에 따라 AI가 재설정한
-- "살아있는 전략 문서"를 버전별로 보관한다.
-- =====================================================

-- 1. 사용자 프로필
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id UUID UNIQUE NOT NULL,          -- Supabase Auth UID
    name TEXT NOT NULL,
    goal TEXT NOT NULL CHECK (goal IN ('diet','bulk','maintain')),
    height_cm FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 식단 기록 (매 끼니)
-- 기존 앱: 단순 칼로리 합산
-- 이 앱: meal_type으로 끼니별 분배 전략 계산에 활용
CREATE TABLE meal_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    log_date DATE NOT NULL DEFAULT CURRENT_DATE,
    meal_type TEXT CHECK (meal_type IN ('breakfast','lunch','dinner','snack')),
    food_name TEXT NOT NULL,
    quantity_g FLOAT NOT NULL,
    calories FLOAT NOT NULL,
    protein_g FLOAT NOT NULL,
    carbs_g FLOAT NOT NULL,
    fat_g FLOAT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 인바디 기록
-- 기존 앱: 체중만 연동
-- 이 앱: 골격근량·체지방률까지 보고 근손실 여부 판단
CREATE TABLE inbody_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    measured_date DATE NOT NULL,
    weight_kg FLOAT NOT NULL,
    skeletal_muscle_kg FLOAT NOT NULL,
    body_fat_kg FLOAT NOT NULL,
    body_fat_pct FLOAT NOT NULL,
    bmi FLOAT,
    bmr_kcal FLOAT,               -- 기초대사량
    protein_kg FLOAT,
    mineral_kg FLOAT,
    image_url TEXT,               -- OCR 원본 이미지 저장 경로
    raw_ocr_text TEXT,            -- OCR 추출 원문 (디버깅용)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 일상 체중 기록. 완전한 체성분 측정과 분리해 누락값을 만들지 않는다.
CREATE TABLE weight_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    measured_date DATE NOT NULL,
    weight_kg FLOAT NOT NULL CHECK (weight_kg > 0 AND weight_kg <= 500),
    source TEXT NOT NULL CHECK (source IN ('onboarding', 'manual', 'inbody')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, measured_date, source)
);

-- 4. AI 식단 전략 (핵심 차별점)
-- 기존 앱: 목표 칼로리 고정값
-- 이 앱: 인바디 업데이트마다 AI가 재계산한 전략을 버전으로 쌓음
--        전략 변화 이력을 보면 "왜 바뀌었는지" 추적 가능
CREATE TABLE diet_strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    daily_calories FLOAT NOT NULL,
    protein_g FLOAT NOT NULL,
    carbs_g FLOAT NOT NULL,
    fat_g FLOAT NOT NULL,
    strategy_note TEXT,           -- AI가 생성한 전략 근거 설명
    triggered_by TEXT,            -- 'initial' | 'inbody_update' | 'manual'
    inbody_log_id UUID REFERENCES inbody_logs(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. 채팅 이력 (컨텍스트 유지용)
CREATE TABLE chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL DEFAULT 'default',
    role TEXT CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    agent_type TEXT,              -- 어떤 Sub-Agent가 응답했는지 기록
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_meal_logs_user_date ON meal_logs(user_id, log_date);
CREATE INDEX idx_inbody_logs_user ON inbody_logs(user_id, measured_date DESC);
CREATE INDEX idx_diet_strategies_active ON diet_strategies(user_id, is_active);
CREATE INDEX idx_chat_history_user ON chat_history(user_id, created_at DESC);
CREATE INDEX idx_chat_history_user_thread ON chat_history(user_id, thread_id, created_at DESC);

-- RLS (Row Level Security) - 본인 데이터만 접근
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE meal_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE inbody_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE diet_strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_own" ON users FOR ALL USING (auth_id = auth.uid());
CREATE POLICY "meal_own" ON meal_logs FOR ALL USING (
    user_id = (SELECT id FROM users WHERE auth_id = auth.uid())
);
CREATE POLICY "inbody_own" ON inbody_logs FOR ALL USING (
    user_id = (SELECT id FROM users WHERE auth_id = auth.uid())
);
CREATE POLICY "strategy_own" ON diet_strategies FOR ALL USING (
    user_id = (SELECT id FROM users WHERE auth_id = auth.uid())
);
CREATE POLICY "chat_own" ON chat_history FOR ALL USING (
    user_id = (SELECT id FROM users WHERE auth_id = auth.uid())
);
