-- Add GCG, introduced in arXiv 2307.15043.
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog. The source paper gets the source evidence row (Introduced banner).

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
    'gcg',
    'GCG',
    'Greedy Coordinate Gradient (GCG)',
    'Greedy Coordinate Gradient (GCG) is an automatic adversarial-suffix attack on aligned large language models. Given a harmful request, it optimizes a short string of suffix tokens so that the model''s probability of beginning an affirmative response (e.g. "Sure, here is...") is maximized instead of refusing. Each step uses the gradient of the loss with respect to one-hot token embeddings to propose the top-k candidate substitutions at every suffix position, evaluates a random batch of these single-token swaps exactly, and greedily keeps the best one; it resembles AutoPrompt but searches over all suffix positions at once. Optimizing one suffix across many prompts and several open models (Vicuna-7B and 13B) yields universal attacks that transfer to black-box systems such as ChatGPT, Bard, Claude and [LLaMA](/methods/llama)-2-Chat. GCG became the standard optimization-based jailbreak baseline for evaluating [RLHF](/methods/rlhf)-aligned models and defenses, and spawned many faster or more fluent variants.',
    'greedy coordinate gradient, GCG attack, GCG jailbreak, GCG suffix',
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
        WHERE arxiv_id = '2307.15043'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Universal and Transferable Adversarial Attacks on Aligned Language Models',
    'https://github.com/llm-attacks/llm-attacks',
    NULL,
    '[Universal and Transferable Adversarial Attacks on Aligned Language Models](/paper/2307.15043)'
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
SELECT source_paper_id, id FROM methods
WHERE slug = 'gcg' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gcg' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 1115 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE gcg_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gcg'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        17506, 17705, 17971, 18212, 18682, 18862, 19013, 19174, 19226, 19240, 19429, 19564,
        19876, 19999, 20018, 20053, 20377, 20428, 20583, 20594, 20722, 20861, 20933, 20987,
        21104, 21298, 21333, 21336, 21357, 21390, 21462, 21516, 21517, 21518, 21707, 21714,
        21753, 21882, 22037, 22045, 22115, 22218, 22382, 22419, 22766, 22816, 22829, 22890,
        22916, 22989, 23001, 23054, 23133, 23139, 23197, 23255, 23264, 23297, 23324, 23354,
        23368, 23392, 23408, 23557, 23717, 23832, 23953, 24068, 24211, 24216, 24227, 24296,
        24397, 24649, 24651, 24793, 25118, 25128, 25130, 25191, 25456, 25466, 25706, 25720,
        25737, 25755, 25781, 26079, 26151, 26193, 26200, 26210, 26314, 26427, 26457, 26495,
        26497, 26541, 26610, 26630, 26706, 26746, 26840, 26933, 27004, 27020, 27057, 27103,
        27115, 27136, 27158, 27227, 27261, 27273, 27287, 27300, 27311, 27381, 27385, 27390,
        27412, 27420, 27452, 27534, 27537, 27539, 27540, 27600, 27602, 27603, 27665, 27708,
        27735, 27763, 27858, 27886, 27894, 27915, 27937, 27961, 27970, 27974, 27996, 28002,
        28100, 28156, 28186, 28202, 28212, 28219, 28446, 28536, 28537, 28540, 28560, 28618,
        28749, 28754, 28816, 28888, 28892, 28931, 28966, 29148, 29291, 29510, 29615, 29794,
        29802, 29960, 30105, 30212, 30263, 30367, 30438, 30504, 30603, 30626, 30637, 30640,
        30665, 30699, 30716, 30745, 30763, 30800, 30808, 30830, 30974, 31212, 31277, 31291,
        31319, 31547, 31564, 31597, 31649, 31840, 31850, 31916, 31956, 32012, 32100, 32107,
        32121, 32130, 32131, 32157, 32227, 32245, 32255, 32324, 32332, 32386, 32448, 32555,
        32585, 32605, 32644, 32782, 32983, 33050, 33063, 33122, 33135, 33145, 33188, 33192,
        33207, 33223, 33224, 33225, 33280, 33296, 33320, 33398, 33424, 33491, 33495, 33498,
        33561, 33592, 33623, 33693, 33713, 33741, 33780, 33856, 33872, 34075, 34302, 34520,
        34548, 34776, 34843, 34924, 35002, 35051, 35101, 35119, 35160, 35223, 35238, 35311,
        35344, 35455, 35542, 35545, 35554, 35565, 35634, 35667, 36087, 36163, 36295, 36350,
        36460, 36469, 36606, 36651, 36859, 37193, 37240, 37350, 37404, 37457, 37481, 37660,
        37727, 37762, 37809, 37817, 37835, 37913, 37937, 38026, 38139, 38179, 38218, 38240,
        38323, 38329, 38336, 38339, 38388, 38397, 38449, 38619, 38628, 38647, 38687, 38697,
        38728, 38731, 38764, 38787, 38982, 38994, 39005, 39017, 39028, 39032, 39081, 39101,
        39303, 39427, 39615, 39639, 39710, 39846, 39926, 39957, 39989, 40047, 40102, 40245,
        40631, 40636, 40819, 40842, 40912, 41193, 41195, 41248, 41279, 41298, 41499, 41532,
        41594, 41877, 42016, 42049, 42089, 42301, 42370, 42450, 42457, 42499, 42548, 42643,
        42787, 42823, 42910, 42939, 42976, 43119, 43159, 43194, 43212, 43316, 43350, 43415,
        43422, 43442, 43512, 43522, 43539, 43553, 43649, 43693, 43767, 43842, 43847, 43855,
        43866, 43872, 44051, 44072, 44102, 44186, 44325, 44399, 44433, 44446, 44456, 44470,
        44495, 44571, 44603, 44651, 44732, 44760, 44828, 44862, 44867, 44885, 45080, 45097,
        45125, 45234, 45244, 45357, 45370, 45377, 45384, 45489, 45502, 45582, 45677, 45899,
        45901, 46069, 46106, 46378, 46404, 46425, 46518, 46533, 46573, 46682, 46910, 47071,
        47159, 47179, 47205, 47243, 47305, 47324, 47472, 47625, 47701, 47819, 47866, 47898,
        47989, 48099, 48132, 48180, 48553, 48674, 48806, 48862, 48901, 48972, 48975, 49080,
        49091, 49100, 49137, 49213, 49294, 49349, 49376, 49408, 49464, 49518, 49536, 49543,
        49676, 49845, 49968, 49994, 50109, 50116, 50175, 50223, 50454, 50474, 50510, 50565,
        50740, 50760, 50762, 50782, 50913, 51016, 51087, 51100, 51108, 51247, 51248, 51261,
        51327, 51655, 51672, 51891, 51915, 51918, 51970, 52177, 52209, 52222, 52329, 52360,
        52388, 52391, 52648, 52847, 52915, 53069, 53118, 53141, 53142, 53184, 53223, 53285,
        53441, 53493, 53538, 53539, 53544, 53611, 53692, 53732, 53830, 54058, 54107, 54223,
        54300, 54314, 54552, 54653, 54711, 54822, 54885, 54945, 55041, 55147, 55186, 55298,
        55366, 55428, 55536, 55538, 55586, 55598, 55798, 55879, 55984, 55989, 56040, 56044,
        56112, 56220, 56326, 56477, 56620, 57001, 57386, 57524, 57610, 57622, 57692, 57718,
        57828, 57837, 57999, 58004, 58020, 58033, 58143, 58380, 58383, 58399, 58422, 58434,
        58435, 58452, 58482, 58506, 58532, 58563, 58568, 58781, 58783, 58910, 59310, 59321,
        59504, 59595, 59682, 59705, 59844, 59881, 59891, 60070, 60097, 60144, 60366, 60443,
        60461, 60513, 60521, 60588, 60592, 60643, 60794, 60928, 61052, 61073, 61085, 61112,
        61114, 61127, 61143, 61200, 61203, 61222, 61240, 61245, 61291, 61481, 61485, 61524,
        61559, 61745, 61839, 61935, 62084, 62093, 62301, 62332, 62436, 62483, 62579, 62657,
        62694, 62703, 62741, 62757, 62868, 62891, 62898, 62905, 63029, 63032, 63044, 63110,
        63142, 63369, 63371, 63461, 63483, 63496, 63537, 63631, 63951, 63953, 64009, 64083,
        64292, 64446, 64503, 64653, 64787, 64827, 64835, 64929, 64987, 65007, 65069, 65137,
        65159, 65226, 65258, 65431, 65490, 65561, 65581, 65650, 65722, 65935, 65996, 66057,
        66114, 66152, 66198, 66257, 66325, 66681, 66847, 66919, 66935, 66992, 67046, 67158,
        67335, 67451, 67748, 67749, 67811, 67871, 67891, 68128, 68375, 68394, 68478, 68524,
        68673, 69019, 69058, 69077, 69173, 69223, 69275, 69366, 69451, 69533, 69591, 69825,
        69839, 69843, 69924, 69946, 69972, 70035, 70064, 70329, 70412, 70538, 70579, 70600,
        70606, 70638, 70649, 70682, 70709, 70960, 71159, 71335, 71599, 71634, 71730, 71763,
        71852, 71853, 71876, 72253, 72461, 72471, 72489, 72527, 72562, 72579, 72614, 72698,
        72708, 72716, 72830, 72835, 72843, 72851, 72978, 73023, 73142, 73289, 73308, 73366,
        73392, 73526, 73577, 73713, 73748, 73858, 74060, 74136, 74241, 74422, 74460, 74473,
        74486, 74499, 74532, 74599, 74608, 74624, 74707, 74751, 74936, 75053, 75085, 75125,
        75364, 75388, 75527, 75654, 75879, 76014, 76123, 76154, 76183, 76196, 76367, 76492,
        76670, 77058, 77140, 77178, 77280, 77312, 77449, 77477, 77695, 77698, 77743, 77759,
        77765, 77782, 77819, 77824, 77827, 77856, 78276, 78346, 78348, 78552, 78633, 78645,
        78661, 83204, 83244, 83249, 83253, 83319, 83426, 83510, 83733, 83734, 83981, 84013,
        84044, 85023, 85045, 85839, 85918, 85921, 86092, 86323, 86333, 86350, 86645, 86670,
        86800, 86994, 87001, 87072, 87154, 87231, 87268, 88040, 88459, 88566, 88573, 88666,
        88737, 88742, 88953, 88963, 89041, 89151, 89178, 89309, 89561, 89578, 89633, 89639,
        89699, 89702, 89739, 89863, 89918, 90046, 90168, 90383, 90620, 90685, 90764, 91056,
        91080, 91121, 91148, 91197, 91405, 91426, 91446, 91473, 91492, 91545, 91669, 91679,
        92004, 92143, 92153, 92172, 92252, 92296, 92381, 92401, 92758, 92760, 92821, 92858,
        92929, 92970, 93023, 93054, 93063, 93174, 93239, 93369, 93436, 93545, 93598, 93649,
        93688, 93705, 93872, 93915, 93963, 93976, 94001, 94026, 94093, 94095, 94110, 94136,
        94197, 94313, 94360, 94390, 94433, 94537, 94642, 94694, 94718, 94745, 94859, 94904,
        94908, 95134, 95396, 98175, 98179, 98545, 98728, 98828, 98961, 98985, 99020, 99116,
        99146, 99271, 99480, 99520, 99549, 99615, 99635, 99710, 99803, 99832, 99834, 99881,
        99933, 99948, 100003, 100034, 100065, 100087, 100109, 100162, 100165, 100329, 100331, 100431,
        100533, 100583, 100611, 100697, 100737, 100753, 100854, 100947, 100979, 101064, 101119, 101156,
        101168, 101207, 101325, 101336, 101441, 101489, 101689, 101711, 101725, 101738, 101745, 101778,
        101788, 101800, 102027, 102293, 102376, 102406, 102432, 102457, 102548, 102756, 102776, 102799,
        102849, 102857, 102869, 102870, 102899, 102933, 102963, 102969, 103076, 103123, 103131, 103147,
        103263, 103274, 103298, 103304, 103318, 103374, 103391, 103408, 103426, 103428, 103483, 103579,
        103581, 103611, 103621, 103661, 103712, 103738, 103742, 103758, 105999, 106087, 106130, 106202,
        106213, 106231, 106254, 106281, 106282, 106294, 106367, 106602, 106822, 106860, 106910, 106993,
        107088, 107116, 107143, 107223, 107229, 107599, 108050, 108153, 108325, 108814, 109101, 109519,
        109746, 109967, 109997, 110039, 110044, 110082, 110102, 110180, 110217, 110233, 110283, 110336,
        110351, 110446, 110489, 110548, 110647, 110740, 110773, 111115, 113813, 113963, 113991, 114058,
        114181, 116406, 116646, 118188, 118433, 119108, 121943, 121964, 122354, 122521, 122578
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gcg citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM gcg_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING gcg_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 26 local citers name the method in title or abstract.
CREATE TEMP TABLE gcg_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gcg'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        20141, 21460, 26058, 26687, 28273, 29857, 30241, 31009, 31697, 32135, 41399, 50709,
        51125, 53734, 57760, 59130, 62306, 71551, 76089, 85933, 89072, 99403, 100473, 101779,
        102155, 102915
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gcg_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM gcg_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 17 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE gcg_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gcg'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        20141, 21460, 26058, 26687, 29857, 31009, 32135, 36068, 41399, 51125, 59130, 76089,
        89072, 100473, 102155, 102915, 110470
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gcg_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gcg_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
