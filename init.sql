-- Islamic Q&A Database Initialization Script

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for better performance
-- Questions table indexes
CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
CREATE INDEX IF NOT EXISTS idx_questions_language ON questions(language);
CREATE INDEX IF NOT EXISTS idx_questions_created_at ON questions(created_at);
CREATE INDEX IF NOT EXISTS idx_questions_hash ON questions(question_hash);
CREATE INDEX IF NOT EXISTS idx_questions_text_gin ON questions USING gin(to_tsvector('english', question_text));

-- Answers table indexes
CREATE INDEX IF NOT EXISTS idx_answers_question_id ON answers(question_id);
CREATE INDEX IF NOT EXISTS idx_answers_source_name ON answers(source_name);
CREATE INDEX IF NOT EXISTS idx_answers_confidence ON answers(confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_answers_verified ON answers(is_verified);
CREATE INDEX IF NOT EXISTS idx_answers_created_at ON answers(created_at);

-- User interactions indexes
CREATE INDEX IF NOT EXISTS idx_interactions_session ON user_interactions(session_id);
CREATE INDEX IF NOT EXISTS idx_interactions_created_at ON user_interactions(created_at);
CREATE INDEX IF NOT EXISTS idx_interactions_rating ON user_interactions(satisfaction_rating);

-- Users table indexes
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);

-- Sources table indexes
CREATE INDEX IF NOT EXISTS idx_sources_active ON sources(is_active);
CREATE INDEX IF NOT EXISTS idx_sources_priority ON sources(priority);

-- Scraping jobs indexes
CREATE INDEX IF NOT EXISTS idx_scraping_jobs_status ON scraping_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scraping_jobs_created_at ON scraping_jobs(created_at);

-- Create full-text search configurations
-- English configuration
CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS english_islamic (COPY = english);

-- Arabic configuration (if supported)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'arabic') THEN
        CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS arabic_islamic (COPY = arabic);
    END IF;
END $$;

-- Create functions for better search
CREATE OR REPLACE FUNCTION search_questions(
    search_query TEXT,
    search_language VARCHAR(10) DEFAULT 'en',
    result_limit INTEGER DEFAULT 20
)
RETURNS TABLE(
    question_id UUID,
    question_text TEXT,
    category VARCHAR(100),
    language VARCHAR(10),
    rank REAL
) AS $$
BEGIN
    IF search_language = 'ar' THEN
        RETURN QUERY
        SELECT 
            q.id,
            q.question_text,
            q.category,
            q.language,
            ts_rank(to_tsvector('arabic', q.question_text), plainto_tsquery('arabic', search_query)) as rank
        FROM questions q
        WHERE q.language = 'ar'
            AND to_tsvector('arabic', q.question_text) @@ plainto_tsquery('arabic', search_query)
        ORDER BY rank DESC, q.created_at DESC
        LIMIT result_limit;
    ELSE
        RETURN QUERY
        SELECT 
            q.id,
            q.question_text,
            q.category,
            q.language,
            ts_rank(to_tsvector('english', q.question_text), plainto_tsquery('english', search_query)) as rank
        FROM questions q
        WHERE q.language = 'en'
            AND to_tsvector('english', q.question_text) @@ plainto_tsquery('english', search_query)
        ORDER BY rank DESC, q.created_at DESC
        LIMIT result_limit;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create function to get similar questions
CREATE OR REPLACE FUNCTION get_similar_questions(
    input_question_id UUID,
    similarity_threshold REAL DEFAULT 0.3,
    result_limit INTEGER DEFAULT 10
)
RETURNS TABLE(
    question_id UUID,
    question_text TEXT,
    similarity_score REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        q2.id,
        q2.question_text,
        similarity(q1.question_text, q2.question_text) as similarity_score
    FROM questions q1
    CROSS JOIN questions q2
    WHERE q1.id = input_question_id
        AND q2.id != input_question_id
        AND q1.language = q2.language
        AND similarity(q1.question_text, q2.question_text) > similarity_threshold
    ORDER BY similarity_score DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Create materialized view for analytics
CREATE MATERIALIZED VIEW IF NOT EXISTS question_analytics AS
SELECT 
    DATE_TRUNC('day', created_at) as date,
    language,
    category,
    COUNT(*) as question_count
FROM questions
GROUP BY DATE_TRUNC('day', created_at), language, category
WITH DATA;

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_question_analytics_date ON question_analytics(date);
CREATE INDEX IF NOT EXISTS idx_question_analytics_language ON question_analytics(language);

-- Create function to refresh analytics
CREATE OR REPLACE FUNCTION refresh_question_analytics()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW question_analytics;
END;
$$ LANGUAGE plpgsql;

-- Insert default sources
INSERT INTO sources (id, name, base_url, scraping_config, is_active, priority, created_at)
VALUES 
    (uuid_generate_v4(), 'IslamQA.info', 'https://islamqa.info', '{"sections": ["aqeedah", "worship", "jurisprudence"]}', true, 1, NOW()),
    (uuid_generate_v4(), 'Dar al-Ifta Egypt', 'https://www.dar-alifta.org', '{"sections": ["family", "worship", "business"]}', true, 2, NOW())
ON CONFLICT DO NOTHING;

-- Insert default admin user (password: admin123 - change in production!)
INSERT INTO users (id, username, email, hashed_password, is_active, is_admin, api_key, rate_limit, created_at)
VALUES (
    uuid_generate_v4(),
    'admin',
    'admin@islamqa.dev',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiQUO7.Xk/8.',
    true,
    true,
    encode(gen_random_bytes(32), 'hex'),
    1000,
    NOW()
) ON CONFLICT (username) DO NOTHING;

-- Create trigger to automatically update updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers to relevant tables
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_questions_updated_at') THEN
        CREATE TRIGGER update_questions_updated_at
            BEFORE UPDATE ON questions
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_answers_updated_at') THEN
        CREATE TRIGGER update_answers_updated_at
            BEFORE UPDATE ON answers
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;
