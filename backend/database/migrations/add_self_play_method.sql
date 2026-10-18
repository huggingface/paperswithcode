-- Add Self-play (no single introducing paper).
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog.

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'self-play',
    'Self-play',
    'Self-play',
    'Self-play is a training paradigm in which an agent improves by interacting with copies or past versions of itself, so that its opponent, and thus the curriculum, grows stronger as it learns, without expert data or hand-designed opponents. It has a long history in game-playing AI: Arthur Samuel''s checkers program (1959) and TD-Gammon (1992) learned from games against themselves. AlphaGo Zero and [AlphaZero](/methods/alphazero) ([Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm](/paper/1712.01815)) combined self-play with [Monte-Carlo Tree Search](/methods/monte-carlo-tree-search) to reach superhuman play from scratch, followed by [MuZero](/methods/muzero) and large-scale self-play systems such as [OpenAI Five](/paper/1912.06680). Self-play has since moved to language models: [SPIN](/paper/2401.01335) fine-tunes an LLM to distinguish its own generations from human data, and methods such as [Absolute Zero](/paper/2505.03335) have models propose and solve their own tasks for reasoning, alignment, debate and safety training.',
    'self-play, self play',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://arxiv.org/abs/2408.01072',
    'A Survey on Self-play Methods in Reinforcement Learning',
    NULL,
    NULL,
    '[A Survey on Self-play Methods in Reinforcement Learning](/paper/2408.01072)'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

-- 189 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE self_play_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-play'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        237, 1009, 1254, 1289, 1444, 2513, 2930, 3062, 3779, 4745, 8063, 9154,
        9938, 10905, 12210, 13112, 13126, 15650, 16689, 19617, 21380, 22839, 23149, 23463,
        23933, 25099, 25414, 25582, 25616, 25645, 25684, 26957, 27386, 28792, 30424, 30984,
        31017, 31562, 31914, 32202, 32441, 33335, 33371, 33771, 35476, 35752, 36005, 36217,
        36842, 37303, 38113, 38153, 39475, 41444, 41634, 43487, 43608, 43823, 43896, 43957,
        43993, 44426, 44450, 44552, 44675, 45002, 45297, 45341, 46528, 48174, 48442, 48622,
        49873, 50992, 51595, 51787, 52434, 52709, 52962, 53042, 53049, 53265, 53793, 53855,
        53893, 54019, 54390, 54469, 54494, 55113, 55394, 55493, 55536, 55895, 56395, 56712,
        56746, 56784, 56906, 57158, 57598, 57862, 59326, 60825, 61195, 61366, 61375, 61545,
        62030, 62483, 62722, 62916, 62927, 63474, 63488, 64992, 66259, 66491, 67540, 68027,
        70178, 72144, 73154, 73691, 74494, 74560, 74840, 77497, 78420, 80674, 81803, 82974,
        82981, 83425, 83771, 85655, 86676, 88877, 89428, 91034, 91275, 91377, 92689, 92905,
        94149, 94472, 94542, 94608, 96623, 98101, 99834, 100624, 100721, 100758, 101111, 101221,
        101267, 101533, 102046, 102431, 103129, 103411, 103557, 103708, 103918, 104545, 105881, 106015,
        106047, 106090, 106105, 106189, 106334, 106396, 107816, 107980, 108250, 108850, 109496, 109798,
        110724, 110928, 113277, 113864, 117386, 118633, 122398, 122484, 123429
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM self_play_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM self_play_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
