-- Add DPM-Solver, introduced in arXiv 2206.00927.
-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.
-- The source paper gets the source evidence row (Introduced banner).

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
    'dpm-solver',
    'DPM-Solver',
    'DPM-Solver',
    'DPM-Solver is a training-free, high-order ODE solver for fast sampling from diffusion probabilistic models. It exploits the semi-linear structure of the diffusion ODE: the linear part is solved exactly and the remaining integral of the noise prediction is approximated with a change of variables to the log-SNR and Taylor expansion, giving first- to third-order solvers with convergence guarantees. It produces high-quality samples in about 10 to 20 function evaluations, versus hundreds for ancestral sampling, and generalizes [DDIM](/methods/ddim) as its first-order case. DPM-Solver++ extends it to guided sampling and is a default scheduler in libraries such as diffusers.',
    'DPM-Solver, DPM-Solver++, DPM Solver, DPMSolver',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2206.00927'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DPM-Solver: A Fast ODE Solver for Diffusion Probabilistic Model Sampling in Around 10 Steps',
    'https://github.com/LuChengTHU/dpm-solver',
    NULL,
    '[DPM-Solver: A Fast ODE Solver for Diffusion Probabilistic Model Sampling in Around 10 Steps](/paper/2206.00927)'
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
WHERE slug = 'dpm-solver' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'dpm-solver' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 1052 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE dpm_solver_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dpm-solver'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        8283, 8877, 9315, 9662, 10001, 10201, 10229, 10404, 10451, 10454, 10607, 10682,
        10716, 11115, 11170, 11188, 11209, 11347, 11348, 11416, 11461, 11525, 11529, 11585,
        11611, 11648, 11674, 11718, 11794, 11810, 11943, 12072, 12278, 12444, 12485, 12587,
        12602, 12698, 12751, 12752, 12845, 12884, 12925, 12960, 12976, 12980, 12996, 13141,
        13203, 13208, 13225, 13229, 13405, 13449, 13479, 13538, 13595, 13599, 13618, 13622,
        13674, 13823, 13842, 13869, 13873, 14074, 14080, 14120, 14336, 14351, 14477, 14760,
        14793, 14944, 15114, 15284, 15300, 15313, 15466, 15583, 16116, 16241, 16259, 16277,
        16308, 16500, 16509, 16528, 16600, 16621, 16671, 16676, 16690, 16748, 16795, 16798,
        16804, 16807, 16922, 17114, 17132, 17149, 17202, 17295, 17352, 17657, 17749, 17778,
        17877, 17889, 17969, 18025, 18151, 18289, 18291, 18332, 18453, 18465, 18487, 18494,
        18511, 18555, 18561, 18656, 18905, 19187, 19200, 19861, 19908, 20253, 20259, 20268,
        20321, 20332, 20344, 20443, 20609, 20631, 20654, 20879, 21037, 21061, 21073, 21108,
        21145, 21150, 21253, 21348, 21398, 21428, 21438, 21507, 21540, 21708, 21777, 21835,
        21884, 21908, 21973, 22105, 22309, 22335, 22600, 22729, 22773, 22791, 22886, 22910,
        22971, 23039, 23207, 23338, 23396, 23537, 23726, 23741, 23775, 23778, 23793, 23799,
        23839, 23863, 23869, 23873, 23906, 23920, 23955, 24007, 24059, 24124, 24151, 24178,
        24242, 24338, 24351, 24417, 24433, 24435, 24462, 24515, 24533, 24572, 24669, 24675,
        24726, 24837, 24883, 24905, 24973, 25010, 25012, 25015, 25239, 25243, 25333, 25384,
        25405, 25417, 25442, 25461, 25538, 25689, 25886, 25894, 25895, 25923, 25925, 25987,
        26098, 26419, 26496, 26517, 26537, 26587, 26672, 26941, 27048, 27094, 27096, 27122,
        27203, 27275, 27676, 27751, 27774, 27885, 28006, 28067, 28192, 28217, 28219, 28239,
        28326, 28359, 28521, 28556, 28635, 28706, 28825, 28910, 28920, 28972, 29023, 29024,
        29069, 29072, 29132, 29299, 29315, 29385, 29417, 29421, 29478, 29504, 29633, 29746,
        29771, 29801, 29825, 29864, 29871, 29906, 29955, 29989, 30017, 30068, 30090, 30119,
        30229, 30451, 30530, 30539, 30585, 30592, 30631, 30642, 30646, 30669, 30729, 30930,
        30946, 31012, 31146, 31176, 31178, 31179, 31214, 31231, 31408, 31568, 31635, 31650,
        31691, 31731, 31806, 31823, 31843, 31884, 31887, 31973, 32074, 32090, 32093, 32108,
        32164, 32171, 32195, 32217, 32272, 32295, 32398, 32459, 32566, 32572, 32640, 32669,
        32671, 32697, 32776, 32818, 33020, 33074, 33231, 33413, 33514, 33739, 33753, 33820,
        33967, 34049, 34069, 34317, 34539, 34729, 34791, 34835, 34915, 35273, 35422, 35448,
        35459, 35497, 35627, 35738, 35780, 35920, 36150, 36374, 36452, 36458, 36485, 36588,
        36629, 36853, 36866, 37326, 37353, 37393, 37401, 37493, 37494, 37521, 37624, 37679,
        37757, 37791, 37854, 38027, 38064, 38143, 38202, 38206, 38223, 38232, 38395, 38405,
        38451, 38468, 38501, 38561, 38597, 38660, 38671, 38985, 39127, 39128, 39148, 39151,
        39176, 39238, 39404, 39492, 39554, 39763, 39764, 39867, 40005, 40057, 40068, 40077,
        40452, 40552, 40653, 40677, 40701, 40807, 40815, 40942, 40985, 41066, 41205, 41307,
        41319, 41340, 41419, 41421, 41557, 41620, 41647, 41709, 41717, 41804, 41907, 41953,
        41980, 41983, 42064, 42089, 42203, 42593, 42634, 42802, 42807, 43031, 43068, 43120,
        43289, 43330, 43458, 43503, 43602, 43603, 43739, 43782, 43797, 43852, 43911, 43927,
        44062, 44073, 44074, 44215, 44347, 44385, 44778, 44896, 44997, 45136, 45152, 45297,
        45307, 45471, 45501, 45574, 45666, 45717, 45738, 45753, 45769, 45776, 45788, 45802,
        45805, 45875, 45948, 45978, 45993, 46031, 46080, 46097, 46239, 46322, 46387, 46464,
        46473, 46483, 46579, 46679, 46708, 46750, 46787, 46849, 46880, 47186, 47263, 47269,
        47385, 47449, 47482, 47605, 47657, 47688, 47779, 47809, 47929, 48001, 48122, 48138,
        48319, 48403, 48433, 48601, 48874, 48984, 49383, 49681, 49693, 49864, 49923, 49988,
        50212, 50440, 50491, 50625, 50657, 50904, 50920, 51197, 51224, 51235, 51424, 51554,
        51586, 51714, 51752, 51758, 51964, 52099, 52135, 52249, 52316, 52369, 52535, 52654,
        52655, 52804, 52857, 52875, 52896, 52989, 53062, 53150, 53214, 53288, 53327, 53382,
        53384, 53440, 53536, 53619, 53683, 53716, 53862, 53906, 53958, 54342, 54435, 54458,
        54497, 54502, 54773, 55009, 55032, 55066, 55677, 55983, 56206, 56312, 56338, 56357,
        56365, 56369, 56388, 56548, 56583, 56631, 56653, 56692, 56747, 56818, 56891, 57016,
        57119, 57135, 57200, 57395, 57422, 57475, 57549, 58573, 58764, 58804, 58909, 59113,
        59207, 59436, 59500, 59807, 59922, 60228, 60281, 60330, 60462, 60718, 60913, 61161,
        61171, 61386, 61596, 62129, 62352, 63140, 63227, 63430, 63508, 63554, 63724, 64171,
        64377, 64433, 64621, 64688, 64691, 65323, 65550, 65729, 65913, 65923, 65957, 66660,
        66940, 66948, 66979, 67013, 67085, 67106, 67252, 67395, 67406, 67415, 67417, 67423,
        67469, 67575, 67597, 67774, 67883, 68085, 68457, 68659, 69100, 69234, 69236, 69249,
        69328, 69389, 69540, 69758, 69800, 69901, 70285, 70427, 70559, 70657, 70755, 70815,
        70853, 70971, 71094, 71163, 71370, 71452, 71469, 71529, 71626, 71673, 71858, 71873,
        71881, 71965, 72073, 72082, 72283, 72360, 72756, 72926, 72967, 73128, 73445, 73500,
        73870, 74151, 74273, 74347, 74366, 75007, 75016, 75058, 75076, 75152, 75433, 75567,
        75579, 75874, 75937, 76151, 76467, 76833, 76993, 77068, 77206, 77213, 77222, 77346,
        77451, 77805, 78148, 78160, 78174, 78322, 78405, 78637, 78909, 79098, 79525, 79672,
        83684, 83931, 84007, 84031, 84115, 84184, 84195, 84230, 84259, 84272, 84467, 84497,
        84514, 84545, 84627, 84700, 84719, 84732, 84744, 84788, 84873, 84901, 84956, 85037,
        85464, 85515, 85535, 85536, 85748, 85762, 85825, 85843, 85897, 86072, 86248, 86288,
        86338, 86376, 86385, 86501, 86525, 86538, 86723, 86729, 86913, 86986, 87025, 87158,
        87202, 87549, 87604, 87606, 87644, 87742, 87779, 87782, 87929, 88044, 88104, 88122,
        88152, 88253, 88255, 88485, 88606, 88752, 88996, 89026, 89032, 89062, 89100, 89124,
        89221, 89223, 89394, 89511, 89791, 89803, 89850, 89929, 89941, 90109, 90126, 90159,
        90177, 90189, 90418, 90493, 90617, 90619, 90627, 90637, 90676, 90687, 90713, 90735,
        90767, 90852, 90870, 90914, 90988, 90994, 91308, 91453, 91491, 91507, 91516, 91770,
        91832, 91847, 92024, 92025, 92056, 92156, 92169, 92237, 92374, 92595, 92602, 92639,
        92669, 92705, 93188, 93270, 93273, 93320, 93359, 93581, 93722, 93761, 93917, 93934,
        93966, 93993, 94021, 94023, 94043, 94143, 94282, 94309, 94312, 94318, 94336, 94420,
        94452, 94588, 94616, 94634, 94721, 94863, 94905, 94950, 95001, 95026, 95064, 95215,
        97581, 98133, 98252, 98333, 98846, 98892, 99076, 99105, 99208, 99210, 99221, 99394,
        99429, 99474, 99529, 99541, 99559, 99648, 99698, 99729, 99745, 99765, 99770, 99804,
        99814, 99993, 100098, 100510, 100609, 100675, 100838, 101077, 101201, 101260, 101393, 101487,
        101595, 101714, 101873, 101890, 102140, 102176, 102225, 102436, 102551, 102616, 104392, 104789,
        104818, 105852, 105980, 106350, 106425, 106636, 106692, 106929, 107063, 107398, 107716, 108122,
        108450, 108524, 109769, 109977, 110212, 110790, 112196, 112555, 112712, 113029, 113188, 113257,
        113263, 113288, 113348, 113420, 113621, 113701, 115642, 115699, 115759, 115786, 115811, 115979,
        116035, 116045, 116071, 116170, 116203, 116307, 116317, 116396, 116555, 116564, 116610, 116791,
        116835, 116937, 117123, 117456, 117640, 117702, 117716, 117722, 117932, 118399, 118410, 118413,
        118419, 118430, 118452, 118504, 118530, 118531, 118543, 118551, 118556, 118560, 118599, 118602,
        118618, 119478, 120128, 120161, 120216, 120267, 120469, 120607, 120911, 121046, 121076, 121103,
        121806, 122289, 122747, 122872, 123036, 123124, 123137, 123548
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'dpm-solver citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM dpm_solver_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING dpm_solver_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 16 local citers name the method in title or abstract.
CREATE TEMP TABLE dpm_solver_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dpm-solver'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        11179, 14883, 16323, 17609, 21027, 22270, 23134, 24775, 28475, 37738, 38443, 39662,
        54767, 67319, 99125, 115480
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dpm_solver_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM dpm_solver_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 16 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE dpm_solver_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dpm-solver'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        11179, 14883, 16323, 17609, 21027, 22270, 23134, 28475, 37738, 38443, 39662, 41500,
        54767, 67319, 99125, 115480
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dpm_solver_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM dpm_solver_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
