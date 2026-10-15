-- Add P-Tuning method, introduced in arXiv 2103.10385. The source paper
-- gets the source evidence row (Introduced banner); citers are linked by
-- link_papers_by_source_citations.py and the hourly reference backfill.

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
    'p-tuning',
    'P-Tuning',
    'P-Tuning',
    'P-Tuning is a prompt-learning method that replaces hand-written discrete prompts with trainable continuous prompt embeddings. Pseudo prompt tokens are inserted into the input template, and their embeddings are produced by a small prompt encoder (a bidirectional [LSTM](/methods/lstm) followed by an MLP) that models dependencies between them; they can be combined with discrete anchor tokens. Optimizing only these embeddings, or tuning them together with the model, stabilizes training and greatly reduces the sensitivity of few-shot performance to prompt wording. The paper showed that with P-Tuning, GPT-style models match or exceed similar-sized [BERT](/methods/bert) models on natural language understanding tasks such as knowledge probing on LAMA and SuperGLUE. The follow-up [P-Tuning v2](/paper/2110.07602) adds trainable prompts at every layer, similar to [Prefix-Tuning](/methods/prefix-tuning), to match fine-tuning across model scales; the approach is closely related to [Prompt Tuning](/methods/prompt-tuning) and other [PEFT](/methods/peft) methods.',
    'P-Tuning, P-tuning',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2103.10385'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'GPT Understands, Too',
    'https://github.com/THUDM/P-tuning',
    NULL,
    '[GPT Understands, Too](/paper/2103.10385)'
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

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'p-tuning'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'p-tuning'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 266 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention P-Tuning are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE p_tuning_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'p-tuning'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        5090, 5474, 6036, 6324, 6534, 6541, 6565, 6632, 6657, 6877, 6909, 6934,
        6972, 7091, 7128, 7141, 7387, 7495, 7574, 7916, 7954, 8394, 8415, 8520,
        8602, 8737, 8747, 8892, 8918, 9171, 9178, 9265, 9431, 9444, 9974, 9977,
        10096, 10189, 10207, 10551, 10578, 10637, 10665, 10799, 10840, 10909, 10993, 11203,
        11259, 11260, 11362, 11479, 11500, 11551, 11695, 11805, 11889, 12225, 12408, 12583,
        13010, 13013, 13134, 13286, 13309, 13361, 13386, 13589, 13606, 13697, 13728, 13781,
        13889, 13912, 13999, 14175, 14201, 14231, 14291, 14642, 14710, 14787, 15054, 15057,
        15157, 15252, 15285, 15383, 15518, 15531, 15542, 15674, 15959, 15988, 16027, 16406,
        16701, 16739, 16757, 16990, 17124, 17179, 17194, 17255, 17368, 17401, 17599, 17745,
        17820, 18029, 18057, 18201, 18355, 18435, 18996, 19274, 19312, 19325, 19347, 19398,
        19531, 19598, 19836, 19886, 20011, 20050, 20071, 20170, 20257, 20420, 20465, 20481,
        20726, 20923, 20992, 21325, 21363, 21520, 21567, 21596, 21635, 21868, 21920, 22019,
        22145, 22986, 22987, 22996, 23041, 23311, 23645, 24133, 24208, 24383, 24589, 24977,
        25120, 25439, 25466, 25626, 26174, 26374, 26473, 26655, 26797, 26819, 26896, 26926,
        27028, 27385, 27545, 27732, 27929, 28111, 28173, 28229, 28573, 28626, 28647, 29017,
        29178, 29276, 29501, 29781, 30020, 30241, 30328, 30998, 31145, 31212, 31465, 31690,
        31938, 32030, 32614, 33134, 33176, 33196, 35545, 35721, 36651, 38327, 38874, 39326,
        40512, 41221, 41441, 42407, 42924, 43162, 43236, 44564, 45026, 45169, 46615, 46892,
        49049, 50680, 51597, 56621, 60545, 63451, 65130, 66030, 66679, 66711, 66878, 67955,
        71412, 71434, 72208, 76646, 76784, 77122, 77444, 78482, 78667, 79901, 79995, 80458,
        83617, 86502, 86773, 87332, 90404, 92561, 94133, 94234, 94861, 98611, 101895, 102826,
        103714, 106079, 109197, 110458, 111992, 112593, 116644, 117016, 118207, 118822, 120024, 122711
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'p-tuning citation review 2026-10-15: cites the source paper without using the method'
FROM p_tuning_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING p_tuning_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING p_tuning_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
