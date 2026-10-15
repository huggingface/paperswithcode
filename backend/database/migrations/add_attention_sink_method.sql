-- Add Attention Sink method, introduced in arXiv 2309.17453. The source paper
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
    'attention-sink',
    'Attention Sink',
    'Attention Sinks (StreamingLLM)',
    'An attention sink is an initial token, usually the first one, that receives a disproportionately large share of attention in autoregressive language models regardless of its content, because softmax attention must assign its probability mass somewhere. The StreamingLLM paper identified the phenomenon and showed why plain window attention collapses once these initial tokens are evicted from the [key-value cache](/methods/key-value-cache). StreamingLLM keeps the key-value states of a few attention-sink tokens alongside a rolling window of recent tokens, which lets models such as Llama 2, MPT, Falcon and Pythia process streams of 4 million tokens or more without fine-tuning and runs up to 22.2x faster than [sliding-window](/methods/sliding-window-attention) recomputation. The paper also showed that adding a dedicated learnable sink token during pre-training improves streaming deployment, and attention sinks are now studied in quantization, KV-cache compression and long-context modeling.',
    'attention sink, StreamingLLM',
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
        WHERE arxiv_id = '2309.17453'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Efficient Streaming Language Models with Attention Sinks',
    'https://github.com/mit-han-lab/streaming-llm',
    NULL,
    '[Efficient Streaming Language Models with Attention Sinks](/paper/2309.17453)'
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
WHERE slug = 'attention-sink'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'attention-sink'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 1143 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention attention sinks or StreamingLLM are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE attention_sink_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'attention-sink'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        16559, 17739, 18610, 19943, 20498, 21259, 22696, 22706, 22903, 23346, 23382, 23424,
        23500, 23593, 23689, 24195, 24207, 24346, 24500, 24778, 24779, 24833, 24853, 24910,
        25165, 25296, 25411, 25466, 25506, 25520, 25551, 25624, 25641, 25717, 25791, 25827,
        26043, 26093, 26140, 26190, 26543, 26547, 26748, 26792, 26971, 27015, 27085, 27095,
        27116, 27329, 27342, 27375, 27430, 27518, 27520, 27740, 27742, 27922, 27967, 27979,
        28084, 28087, 28121, 28155, 28308, 28539, 28663, 28824, 29144, 29615, 29645, 29649,
        29851, 29981, 30012, 30035, 30106, 30160, 30187, 30249, 30295, 30335, 30471, 30493,
        30520, 30549, 30647, 30668, 30716, 30723, 30742, 30864, 30952, 31034, 31041, 31150,
        31192, 31381, 31407, 31461, 31462, 31478, 31492, 31503, 31544, 31555, 31570, 31578,
        31642, 31871, 31887, 31993, 32051, 32115, 32261, 32317, 32329, 32417, 32533, 32562,
        32686, 32729, 32731, 32862, 32879, 32935, 33015, 33104, 33158, 33191, 33237, 33266,
        33298, 33350, 33377, 33458, 33496, 33534, 33551, 33607, 33652, 33717, 33720, 33732,
        33832, 33865, 33987, 34041, 34059, 34098, 34225, 34471, 34487, 34510, 34547, 34570,
        34857, 35013, 35080, 35081, 35194, 35201, 35322, 35350, 35360, 35411, 35567, 35720,
        35810, 35816, 35903, 35926, 36043, 36255, 36300, 36387, 36399, 36535, 36603, 36745,
        36944, 36950, 37051, 37080, 37100, 37203, 37346, 37658, 37695, 37752, 37783, 37795,
        37807, 37835, 37850, 37857, 37938, 37956, 37992, 38019, 38134, 38290, 38298, 38307,
        38349, 38613, 38648, 38663, 38672, 38706, 38755, 38804, 38832, 38866, 38931, 38987,
        39018, 39055, 39063, 39107, 39126, 39169, 39173, 39282, 39305, 39417, 39577, 39650,
        39809, 39884, 39888, 40083, 40212, 40231, 40487, 40492, 40550, 40655, 40766, 40795,
        40894, 40934, 40965, 40977, 41084, 41389, 41434, 41463, 41472, 41487, 41543, 41652,
        41681, 41698, 41741, 41815, 41897, 42005, 42224, 42370, 42371, 42392, 42398, 42464,
        42579, 42669, 42737, 43097, 43111, 43136, 43228, 43399, 43437, 43480, 43491, 43519,
        43542, 43577, 43603, 43618, 43623, 43635, 43674, 43681, 43682, 43746, 43846, 43911,
        43953, 43954, 44012, 44026, 44035, 44127, 44172, 44218, 44277, 44289, 44409, 44411,
        44431, 44463, 44472, 44494, 44534, 44538, 44565, 44603, 44707, 44747, 44767, 44858,
        44880, 44895, 44936, 44943, 44954, 44955, 44991, 45001, 45050, 45176, 45189, 45205,
        45264, 45354, 45361, 45416, 45433, 45455, 45491, 45535, 45584, 45721, 45783, 45799,
        45921, 45957, 45983, 46003, 46037, 46098, 46126, 46397, 46452, 46459, 46496, 46501,
        46549, 46588, 46613, 46668, 46756, 46858, 46995, 47000, 47008, 47069, 47104, 47129,
        47132, 47346, 47432, 47452, 47568, 47580, 47582, 47596, 47660, 47921, 47984, 48016,
        48053, 48063, 48118, 48149, 48283, 48300, 48312, 48314, 48371, 48424, 48463, 48881,
        48934, 48997, 49015, 49057, 49124, 49225, 49278, 49336, 49374, 49500, 49660, 49691,
        49694, 49747, 49751, 49754, 49872, 49881, 49882, 49903, 49925, 49929, 49943, 49948,
        49957, 49967, 50053, 50105, 50112, 50199, 50204, 50366, 50460, 50471, 50482, 50563,
        50579, 50653, 50660, 50661, 50693, 50715, 50718, 50791, 50817, 50818, 50851, 50884,
        51055, 51068, 51072, 51184, 51280, 51284, 51373, 51378, 51391, 51422, 51439, 51471,
        51641, 51684, 51777, 51853, 51856, 51875, 51974, 52077, 52186, 52194, 52222, 52245,
        52254, 52361, 52399, 52539, 52571, 52816, 52866, 52897, 52909, 52997, 53027, 53082,
        53087, 53117, 53134, 53225, 53235, 53294, 53320, 53328, 53329, 53422, 53515, 53551,
        53575, 53584, 53591, 53687, 53803, 53806, 53816, 53846, 53959, 54288, 54358, 54392,
        54423, 54457, 54520, 54558, 54653, 54687, 54700, 54734, 54758, 54794, 54971, 54990,
        54994, 55005, 55097, 55117, 55253, 55293, 55391, 55491, 55523, 55534, 55605, 55649,
        55737, 55749, 55757, 55761, 55790, 55907, 55923, 55953, 55971, 56024, 56066, 56102,
        56178, 56199, 56500, 56585, 56609, 56612, 56648, 56698, 56713, 56728, 56730, 56731,
        56732, 56755, 56777, 56799, 56815, 56952, 57024, 57093, 57170, 57237, 57243, 57336,
        57350, 57407, 57446, 57539, 57651, 57726, 57761, 57834, 57983, 58015, 58042, 58078,
        58164, 58201, 58289, 58397, 58402, 58456, 58492, 58595, 58830, 59081, 59532, 59627,
        59687, 59855, 59873, 59969, 60091, 60139, 60253, 60343, 60460, 60638, 60678, 60698,
        60773, 60931, 61018, 61058, 61069, 61199, 61209, 61288, 61324, 61373, 61382, 61466,
        61514, 61534, 61597, 61673, 61759, 61794, 61921, 61942, 61961, 62042, 62061, 62069,
        62073, 62390, 62477, 62620, 62623, 62661, 62668, 62712, 62732, 62745, 62887, 62902,
        62941, 63074, 63077, 63201, 63297, 63518, 63570, 63661, 63752, 63774, 63793, 63904,
        64014, 64022, 64024, 64079, 64232, 64248, 64371, 64578, 64767, 64905, 64995, 65015,
        65176, 65457, 65525, 65565, 65723, 65869, 65955, 66026, 66088, 66148, 66200, 66316,
        66345, 66385, 66497, 66501, 66524, 66619, 66780, 66840, 67028, 67120, 67224, 67443,
        67450, 67546, 67563, 67578, 67593, 67662, 67670, 67953, 68147, 68234, 68480, 68542,
        68685, 68727, 68895, 68961, 69209, 69350, 69454, 69796, 69837, 69958, 69966, 70227,
        70269, 70343, 70477, 70518, 70607, 70697, 70707, 70710, 70981, 71130, 71171, 71223,
        71252, 71464, 71476, 71480, 71534, 71641, 71694, 71757, 71980, 72152, 72660, 72848,
        73038, 73277, 73288, 73307, 73394, 73723, 73827, 74052, 74110, 74128, 74149, 74156,
        74356, 74363, 74397, 74507, 74531, 74747, 74778, 74868, 74881, 75003, 75130, 75218,
        75253, 75350, 75763, 76168, 76614, 76660, 76791, 76854, 77082, 77108, 77555, 82906,
        82916, 82922, 82938, 82979, 82985, 82987, 83111, 83142, 83180, 83188, 83238, 83244,
        83366, 83379, 83399, 83401, 83488, 83509, 83521, 83584, 83589, 83730, 83744, 83802,
        83809, 83810, 83831, 83921, 83923, 83949, 83955, 83960, 84056, 84192, 84234, 84242,
        84263, 84438, 84497, 84504, 84735, 84775, 84879, 85000, 85034, 85278, 85384, 85441,
        85599, 85650, 85664, 85934, 86179, 86309, 86457, 86515, 86594, 86781, 86806, 86884,
        87107, 87119, 87127, 87183, 87472, 87491, 87507, 87587, 88695, 89369, 89372, 89379,
        89720, 89805, 89824, 89933, 90281, 90511, 91186, 91209, 91320, 91422, 91468, 91645,
        91668, 91693, 92052, 92168, 92486, 92495, 92538, 92548, 92575, 92731, 93064, 93283,
        93284, 93514, 93664, 93671, 93673, 93743, 93906, 93941, 93967, 94003, 94044, 94208,
        94222, 94234, 94244, 94338, 94560, 94598, 94646, 94714, 94722, 94795, 94802, 95006,
        97987, 98181, 98212, 98217, 98224, 98249, 98333, 98408, 98427, 98479, 98498, 98700,
        98810, 98936, 99096, 99132, 99133, 99167, 99234, 99293, 99463, 99534, 99604, 99641,
        99804, 99923, 99932, 99943, 100125, 100269, 100310, 100318, 100326, 100384, 100405, 100423,
        100479, 100515, 100552, 100599, 100799, 100848, 100940, 100991, 101032, 101046, 101305, 101308,
        101342, 101380, 101413, 101567, 101637, 101847, 101870, 101984, 102243, 102300, 102312, 102320,
        102376, 102427, 102484, 102587, 102612, 102624, 102710, 102711, 102763, 102781, 102883, 102941,
        102949, 102957, 102994, 103060, 103288, 103319, 103408, 103409, 103469, 103562, 103591, 103636,
        103662, 103667, 103690, 103691, 104019, 104027, 104220, 104413, 104485, 104552, 104738, 105852,
        105913, 105936, 105956, 105957, 105982, 106131, 106358, 106428, 106450, 106910, 107398, 107555,
        107773, 107817, 108093, 108267, 108410, 108469, 108703, 108717, 108764, 108958, 109028, 109134,
        109142, 109143, 109426, 109532, 109649, 109763, 109799, 110007, 110048, 110081, 110150, 110416,
        110719, 110852, 113788, 113895, 113901, 113930, 114016, 114109, 114175, 116104, 117665, 117702,
        117744, 118051, 118651, 118667, 118717, 118732, 119198, 119377, 119383, 119392, 119418, 119551,
        119620, 121076, 121957, 121980, 121998, 122010, 122081, 122136, 122267, 122393, 122502, 122515,
        122595, 122681, 122682, 122740, 122824, 122853, 122897, 122962, 123037, 123445
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'attention-sink citation review 2026-10-15: cites the source paper without using the method'
FROM attention_sink_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING attention_sink_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING attention_sink_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
