-- Add Backdoor Attack.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Backdoor Attack',
    'backdoor-attack',
    'A backdoor attack plants a hidden behavior in a model, usually by poisoning training data or weights so that an input carrying a secret trigger (a patch, a phrase, a style) is mapped to an attacker-chosen output while clean accuracy stays high. The task covers designing stealthy triggers and poisoning strategies for vision, language, speech, federated and reinforcement-learning models, plus the matching defenses: detecting poisoned data, inverting triggers and removing the backdoor. It is a core part of machine learning security and is evaluated with attack success rate against clean accuracy.',
    'backdoor attack, backdoor attacks, backdoor defense, backdoor defence, backdoor learning, backdoor trigger, backdoor injection, backdoor poisoning, backdoored model, backdoor detection, backdoor removal, trojan attack, neural trojan, trojaned model, clean-label backdoor',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    NULL,
    '[BackdoorBench: A Comprehensive Benchmark of Backdoor Learning](/paper/2206.12654)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

-- 315 papers match the task keywords (same matcher as the
-- weekly keyword backfill).
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'auto'
FROM papers p
CROSS JOIN tasks t
WHERE t.slug = 'backdoor-attack'
  AND p.id IN (
        5156, 5302, 5786, 6953, 7306, 7813, 7897, 8672, 9606, 10497, 10801, 11004,
        11202, 11220, 11293, 12048, 12531, 13383, 13401, 13443, 13521, 13632, 13679, 13895,
        13985, 14423, 14598, 14907, 15300, 15691, 16159, 16549, 16780, 17411, 18436, 18516,
        18745, 18810, 19017, 19052, 19715, 20090, 21012, 21705, 21873, 22002, 22085, 23427,
        23717, 23748, 23870, 24068, 24082, 25463, 25674, 26151, 26361, 27477, 27506, 28949,
        29181, 29400, 29868, 30473, 31379, 32107, 32665, 33009, 33206, 33223, 33623, 34184,
        34718, 34843, 36131, 36163, 37298, 37461, 37732, 37781, 38765, 39180, 41428, 41620,
        43565, 43854, 44464, 44884, 45201, 45541, 45996, 49427, 49458, 50065, 50614, 51104,
        51791, 52342, 53997, 55852, 56574, 57380, 58304, 58422, 60568, 60809, 61175, 61387,
        62693, 63780, 63882, 64020, 64282, 64371, 64572, 64623, 64804, 64987, 65090, 66499,
        66528, 66643, 67257, 69438, 70317, 71853, 71962, 72489, 73264, 73368, 73922, 74209,
        74475, 74599, 75602, 75657, 75736, 75767, 76009, 76237, 76246, 77085, 77436, 77452,
        77780, 77782, 77787, 77968, 78021, 78107, 78482, 79124, 79614, 83480, 83486, 83869,
        84085, 84611, 84769, 84887, 84928, 85337, 85586, 85660, 85708, 85774, 85781, 85830,
        86316, 86472, 86662, 86721, 86783, 86948, 87081, 87677, 87724, 87753, 87768, 88283,
        88392, 88953, 88983, 89108, 89117, 89409, 89561, 90110, 90168, 90173, 90220, 90367,
        90635, 90773, 90846, 90957, 91062, 91096, 91270, 91296, 91322, 91344, 91884, 91949,
        92135, 92403, 92908, 93184, 93239, 93460, 93487, 93506, 93705, 93818, 94248, 94403,
        94521, 95034, 95135, 97078, 98372, 99177, 99795, 99939, 100065, 100067, 100112, 100118,
        100194, 100346, 100390, 100409, 100452, 100532, 100855, 101351, 101582, 101641, 102432, 102851,
        102907, 103163, 103260, 103428, 106171, 106342, 106443, 106642, 106650, 106798, 106942, 107070,
        107406, 107443, 107618, 107619, 107660, 107811, 108025, 108160, 108204, 108295, 108325, 108359,
        108464, 108504, 110102, 110119, 110239, 110446, 110534, 112120, 112121, 112442, 112541, 113013,
        113033, 113248, 113279, 113327, 113586, 113636, 113683, 113695, 114223, 114399, 115020, 115633,
        115648, 115932, 116182, 116398, 116437, 116820, 116918, 117231, 118158, 118171, 118214, 118216,
        119643, 119873, 120849, 120974, 121047, 121062, 121164, 121278, 121304, 121564, 121706, 121892,
        122615, 122811, 123021
  )
ON CONFLICT DO NOTHING;
