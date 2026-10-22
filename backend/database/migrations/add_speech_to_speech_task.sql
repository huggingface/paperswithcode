-- Add Speech-to-Speech.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Speech-to-Speech',
    'speech-to-speech',
    'Speech-to-speech models take spoken input and produce spoken output directly, without a text cascade of recognition, a language model and synthesis in between. This preserves tone, emotion and timing and cuts latency, enabling full-duplex spoken dialogue systems such as Moshi and GPT-4o style voice assistants, as well as voice-to-voice translation (see [Speech Translation](/tasks/speech-translation)). Work focuses on discrete speech tokenizers, speech language models, real-time interaction and keeping the reasoning ability of the underlying text model.',
    'speech-to-speech, speech to speech, speech-to-speech model, speech-to-speech models, speech-to-speech dialogue, spoken dialogue model, spoken dialogue system, full-duplex spoken dialogue, end-to-end spoken dialogue, speech-to-speech language model, voice-to-voice',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Moshi: a speech-text foundation model for real-time dialogue](/paper/2410.00037)',
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

-- 156 papers match the task keywords (same matcher as the
-- weekly keyword backfill).
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'auto'
FROM papers p
CROSS JOIN tasks t
WHERE t.slug = 'speech-to-speech'
  AND p.id IN (
        225, 1924, 6225, 7518, 7675, 8596, 8812, 8868, 9036, 9190, 9274, 9676,
        10488, 11494, 13545, 13956, 14577, 15991, 16250, 16829, 16977, 17690, 18114, 19640,
        20648, 20699, 21790, 22546, 22614, 23007, 24507, 26238, 27643, 30164, 32359, 32701,
        32762, 33244, 34165, 36104, 37248, 37561, 38247, 39050, 39291, 39528, 39580, 40225,
        41822, 41978, 42463, 42728, 43706, 44623, 44883, 44970, 45373, 45565, 47015, 48732,
        49176, 50481, 50583, 51064, 51833, 52117, 52732, 53234, 53242, 53316, 54450, 55426,
        56871, 57594, 57658, 57673, 57886, 58107, 58146, 58202, 58588, 58844, 58875, 58969,
        59247, 59339, 59639, 59677, 60522, 60762, 60823, 60824, 62516, 62631, 63406, 63469,
        63635, 64500, 65025, 65850, 65972, 66743, 67108, 67120, 67580, 67693, 67752, 67798,
        67895, 68129, 68633, 69024, 69321, 69757, 70735, 70741, 70827, 71205, 71617, 72422,
        74246, 74579, 75578, 76394, 78393, 83962, 88806, 91279, 92564, 92593, 93112, 93130,
        93400, 98838, 99020, 102596, 102829, 103533, 106216, 110464, 110914, 111132, 111135, 111137,
        111439, 111605, 111659, 111663, 111664, 111977, 112068, 112086, 113973, 116506, 121969, 122099
  )
ON CONFLICT DO NOTHING;
