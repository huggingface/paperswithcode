-- Add Discrete Diffusion (no single introducing paper).
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
    'discrete-diffusion',
    'Discrete Diffusion',
    'Discrete Diffusion Models',
    'Discrete diffusion models apply the [diffusion](/methods/diffusion) framework to categorical data such as text tokens, graphs, molecules and quantized images. A forward Markov chain corrupts each token through a transition matrix, uniform (random replacement), nearest-neighbour or absorbing (replacement by a mask token), and a network is trained to invert it. The idea goes back to the binomial diffusion of [Deep Unsupervised Learning using Nonequilibrium Thermodynamics](/paper/1503.03585) and the multinomial diffusion of [Argmax Flows and Multinomial Diffusion](/paper/2102.05379); D3PM, from [Structured Denoising Diffusion Models in Discrete State-Spaces](/paper/2107.03006), generalized the corruption process and linked absorbing-state diffusion to masked language models. Later work added score-entropy training in [SEDD](/paper/2310.16834) and simplified masked objectives in [MDLM](/methods/mdlm), and scaled the approach to diffusion large language models such as [LLaDA](/methods/llada), which decode many tokens in parallel and refine them over a few denoising steps.',
    'discrete diffusion, D3PM, multinomial diffusion, discrete denoising diffusion, masked diffusion model',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://arxiv.org/abs/2506.13759',
    'Discrete Diffusion in Large Language and Multimodal Models: A Survey',
    'https://github.com/google-research/google-research/tree/master/d3pm',
    NULL,
    '[Structured Denoising Diffusion Models in Discrete State-Spaces](/paper/2107.03006)'
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

-- 314 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE discrete_diffusion_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'discrete-diffusion'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        5017, 6193, 6797, 7397, 9304, 10455, 11133, 11499, 11645, 11648, 13034, 13765,
        13955, 14607, 15293, 15723, 17106, 19222, 19862, 20396, 21084, 22328, 22571, 22614,
        22893, 23575, 24062, 24547, 26982, 27067, 27796, 28158, 31818, 32398, 32457, 32730,
        34694, 35054, 35724, 35872, 36588, 37308, 37494, 37772, 37827, 38111, 38222, 38279,
        38720, 38738, 38782, 39106, 39271, 39302, 41531, 41534, 42117, 42337, 42717, 43125,
        43564, 43578, 43867, 43955, 43982, 44169, 44347, 44559, 45123, 45248, 45304, 45544,
        45769, 45849, 45862, 45981, 46001, 46494, 46556, 46816, 47957, 48077, 48216, 48559,
        48774, 49029, 49178, 49259, 49448, 49461, 49477, 49616, 49705, 49768, 50124, 50414,
        51034, 51173, 51471, 51766, 51838, 51852, 52185, 52341, 52553, 52651, 52818, 52987,
        53203, 53206, 53276, 53315, 53785, 53813, 53876, 53958, 54033, 54144, 54694, 54751,
        54810, 54864, 55065, 55513, 55723, 56141, 56251, 56283, 56286, 56298, 56311, 56451,
        56589, 56815, 56861, 56905, 56943, 57102, 57160, 57499, 57647, 57663, 57725, 58363,
        58848, 59128, 59235, 59309, 59493, 59654, 60034, 60260, 60348, 60598, 60786, 61232,
        61338, 61432, 61596, 61756, 61783, 62066, 62623, 63096, 63311, 63326, 63662, 64464,
        64843, 65216, 65535, 65783, 65835, 66268, 66864, 67031, 67088, 67186, 67398, 67417,
        67598, 67847, 67870, 67883, 67924, 68607, 68891, 68902, 69364, 69523, 69550, 69613,
        70341, 70913, 71121, 72588, 72620, 72723, 75016, 75250, 75983, 76716, 82882, 83858,
        83963, 84223, 84557, 84633, 85738, 85995, 86070, 86364, 86369, 86447, 86784, 86864,
        86865, 86920, 86935, 87161, 88433, 88791, 89375, 89803, 91076, 91412, 91456, 91480,
        91990, 92252, 92593, 92853, 92877, 92911, 93046, 93255, 93320, 93364, 93631, 93758,
        93839, 93985, 94159, 94178, 94200, 94296, 94321, 94379, 94387, 94441, 94514, 94587,
        94879, 94899, 95056, 95107, 98288, 98498, 98950, 99186, 99384, 99611, 99646, 99825,
        99827, 99915, 99938, 100184, 100317, 100364, 101142, 101216, 101231, 101257, 101454, 101456,
        101493, 101520, 101707, 101769, 102179, 102221, 102242, 102348, 103617, 104029, 104035, 105490,
        105649, 105859, 105959, 106053, 106074, 106313, 106350, 106525, 108694, 108776, 108824, 109112,
        110234, 110981, 111091, 113790, 113950, 114002, 114095, 118555, 119405, 119426, 121010, 121647,
        122408, 122611
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM discrete_diffusion_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM discrete_diffusion_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
