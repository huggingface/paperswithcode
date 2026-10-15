-- Add Multi-Agent Debate method, introduced in arXiv 2305.14325. The source paper
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
    'multi-agent-debate',
    'Multi-Agent Debate',
    'Multi-Agent Debate (MAD)',
    'Multi-Agent Debate improves the reasoning and factual accuracy of large language models by having several model instances discuss a question. Each agent first proposes its own answer; then, over several rounds, every agent reads the other agents'' responses and updates its answer, and the debate usually converges on a shared final answer. The method treats models as black boxes and needs only prompting, so it works with the same model for all agents or with different models. Debate improved arithmetic, grade-school math (GSM8K) and chess-move reasoning, and reduced hallucinated facts in biographies and MMLU answers, compared with single-agent reflection and with [chain-of-thought](/methods/chain-of-thought-cot) prompting alone. It is related to [self-consistency](/methods/self-consistency), which samples independent answers without interaction, and to [LLM-as-a-judge](/methods/llm-as-a-judge) setups.',
    'multi-agent debate, multiagent debate',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2305.14325'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Improving Factuality and Reasoning in Language Models through Multiagent Debate',
    'https://github.com/composable-models/llm_multiagent_debate',
    NULL,
    '[Improving Factuality and Reasoning in Language Models through Multiagent Debate](/paper/2305.14325)'
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
WHERE slug = 'multi-agent-debate'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'multi-agent-debate'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 671 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention multi-agent debate are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE multi_agent_debate_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'multi-agent-debate'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        14954, 16758, 16844, 17566, 17668, 18033, 18036, 18046, 18135, 18626, 18727, 18828,
        18972, 19046, 19306, 19445, 19575, 19624, 20053, 20130, 20197, 20327, 20341, 20357,
        20624, 20794, 20933, 20963, 21094, 21298, 21407, 21487, 21489, 21799, 21808, 21854,
        21954, 22811, 23120, 23215, 23225, 23288, 23289, 23350, 23430, 23476, 23530, 23551,
        23557, 23649, 23694, 23884, 23897, 23985, 24186, 24397, 24781, 24793, 25107, 25142,
        25219, 25319, 25460, 25562, 25714, 26091, 26198, 26626, 26681, 27012, 27057, 27060,
        27261, 27274, 27518, 27604, 27611, 27678, 27682, 27724, 27765, 27841, 27997, 28040,
        28070, 28138, 28151, 28186, 28429, 28536, 28549, 28776, 28999, 29437, 29996, 30074,
        30225, 30330, 31132, 31191, 31260, 31371, 31427, 31987, 32014, 32079, 32089, 32167,
        32334, 32439, 32493, 32643, 32645, 32687, 32706, 32834, 32853, 33045, 33178, 33489,
        33572, 34101, 34217, 34362, 34387, 34978, 35002, 35208, 35883, 36288, 36359, 36511,
        37048, 37053, 37333, 37562, 37615, 37664, 37759, 37954, 37972, 38121, 38170, 38258,
        38556, 38571, 38705, 39139, 39209, 39252, 39359, 39661, 39723, 40186, 40377, 40685,
        40718, 40782, 40994, 41260, 41793, 41963, 42058, 42317, 42489, 42647, 42692, 42731,
        42909, 43225, 43285, 43325, 43419, 43513, 43518, 43526, 43666, 43751, 43796, 43823,
        43906, 44098, 44258, 44270, 44285, 44607, 44872, 44955, 44987, 45182, 45257, 45287,
        45439, 45499, 45600, 45630, 45640, 45647, 45973, 46023, 46107, 46194, 46279, 46560,
        46572, 46717, 46851, 46858, 47204, 47432, 47771, 48002, 48004, 48022, 48204, 48347,
        48406, 48518, 48521, 48653, 48674, 49077, 49247, 49470, 49476, 49668, 49753, 49948,
        49976, 50133, 50170, 50480, 50646, 50661, 50700, 50819, 50835, 50862, 50906, 50995,
        51265, 51279, 51623, 51843, 51953, 52076, 52124, 52475, 52725, 52889, 53177, 53313,
        53344, 53374, 53577, 53588, 53677, 53791, 53805, 53836, 53941, 53967, 54142, 54331,
        54660, 54695, 55159, 55556, 55683, 55792, 55828, 55830, 55850, 56044, 56463, 56640,
        56941, 57081, 57161, 57222, 57264, 57530, 57798, 57913, 58399, 58405, 58662, 58950,
        59028, 59098, 59326, 59698, 59713, 59763, 59814, 59920, 59924, 59975, 60104, 60119,
        60362, 60401, 60922, 60938, 61006, 61133, 61141, 61321, 61323, 61427, 61569, 61587,
        61642, 61761, 61787, 61864, 62005, 62115, 62158, 62260, 62269, 62376, 62390, 62591,
        62616, 62654, 62697, 62721, 62834, 62905, 63221, 63347, 63624, 63855, 64131, 64531,
        64553, 64597, 64736, 64804, 65435, 65458, 65517, 65595, 65734, 65903, 66216, 66557,
        67102, 67133, 67221, 67368, 67393, 67586, 67791, 68101, 68259, 68297, 68452, 68704,
        68781, 68928, 68946, 68985, 68999, 69098, 69113, 69225, 69396, 69403, 69670, 70079,
        70172, 70290, 70298, 70301, 70352, 70553, 70914, 71227, 71555, 72149, 72178, 72201,
        72252, 72908, 73105, 73239, 73440, 74136, 74269, 74276, 74403, 74556, 74827, 74915,
        75294, 75499, 75782, 76010, 76952, 77131, 77504, 77769, 78009, 78267, 78460, 82877,
        82970, 83151, 83254, 83815, 83881, 83883, 84634, 85706, 85889, 85961, 85967, 86065,
        86123, 86405, 86456, 86605, 86806, 86923, 87151, 87287, 87583, 88274, 88662, 88790,
        88793, 89017, 89257, 89525, 89699, 90772, 91086, 91535, 92130, 92172, 92524, 92537,
        92554, 92640, 92766, 92787, 92822, 92875, 92889, 93231, 93344, 93496, 93579, 93630,
        94125, 94752, 94811, 94930, 95192, 97108, 98116, 98165, 98172, 98222, 98247, 98413,
        98438, 98508, 98510, 98767, 98784, 98991, 99214, 99263, 99413, 99518, 100173, 100337,
        100578, 100721, 101030, 101050, 101460, 101675, 102039, 102114, 102254, 102434, 102471, 102509,
        102526, 102766, 102778, 102901, 102935, 103024, 103092, 103279, 103364, 103378, 103386, 103438,
        103547, 103553, 103583, 103676, 103701, 104318, 104457, 104555, 104577, 105445, 106015, 106139,
        106148, 106201, 106235, 106287, 106318, 106326, 107027, 107141, 107160, 107368, 107563, 107954,
        107974, 107976, 108042, 108149, 108263, 108287, 108340, 108391, 108513, 108745, 108813, 108849,
        109024, 109138, 109506, 109647, 109751, 110061, 110169, 110295, 110312, 110321, 110338, 110420,
        110449, 111123, 112791, 113849, 119140, 121946, 121988, 121995, 122190, 122240, 122279, 122374,
        122981, 123243, 123289, 123364
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'multi-agent-debate citation review 2026-10-15: cites the source paper without using the method'
FROM multi_agent_debate_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING multi_agent_debate_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING multi_agent_debate_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
