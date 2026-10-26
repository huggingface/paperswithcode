-- Add Audio Source Separation.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Audio Source Separation',
    'audio-source-separation',
    'Audio source separation splits a mixed recording into its component sources, such as vocals, drums and bass in a song, or the individual voices in a crowded room (the cocktail party problem). Models take a mixture waveform or spectrogram and predict one signal or mask per source, from time-frequency masking networks to end-to-end waveform models like Conv-TasNet and band-split transformers. Music demixing and speech separation are the best-known settings, and the output often feeds [Automatic Speech Recognition](/tasks/automatic-speech-recognition) and [Speech Enhancement](/tasks/speech-enhancement).',
    'audio source separation, audio separation, source separation, music source separation, speech separation, sound separation, music demixing, stem separation, cocktail party problem, universal sound separation, singing voice separation, blind source separation',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Conv-TasNet: Surpassing Ideal Time-Frequency Magnitude Masking for Speech Separation](/paper/1809.07454)',
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

-- 169 papers match the task keywords (same matcher as the
-- weekly keyword backfill).
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'auto'
FROM papers p
CROSS JOIN tasks t
WHERE t.slug = 'audio-source-separation'
  AND p.id IN (
        782, 1205, 1212, 1217, 1218, 1325, 1503, 1679, 2019, 2310, 2878, 3319,
        3948, 4123, 4255, 4413, 4442, 4523, 4607, 7014, 7166, 7295, 7432, 7773,
        7860, 9224, 9539, 9570, 10265, 10474, 10510, 11217, 11333, 11374, 11962, 12165,
        12457, 12601, 12842, 13266, 13511, 13664, 15382, 15488, 15489, 16632, 17390, 17503,
        18568, 18756, 19093, 20136, 21124, 25339, 25837, 26223, 28079, 28378, 29529, 29828,
        32719, 33083, 33764, 34403, 34586, 34699, 35624, 36471, 37446, 37650, 37652, 39288,
        39552, 41456, 42773, 44958, 48119, 48153, 48497, 48922, 49718, 49917, 50127, 51901,
        52371, 53065, 54953, 61273, 61724, 63332, 63407, 65327, 65630, 65979, 66565, 67285,
        67711, 67968, 68029, 68037, 68156, 68502, 69896, 71152, 71895, 72559, 72995, 73096,
        75129, 75544, 76346, 76416, 77192, 77616, 78066, 78432, 78556, 78852, 78888, 78942,
        79367, 79873, 79874, 80314, 80526, 80816, 81039, 81211, 81300, 81325, 81743, 81879,
        82023, 85140, 85194, 86506, 89671, 89722, 92650, 98715, 99781, 102070, 106504, 108581,
        108582, 111285, 111383, 111386, 111387, 111388, 111389, 111390, 111391, 111450, 111459, 111464,
        111465, 111467, 111561, 111670, 111675, 111807, 111998, 111999, 112000, 112002, 112094, 115881,
        123563
  )
ON CONFLICT DO NOTHING;
