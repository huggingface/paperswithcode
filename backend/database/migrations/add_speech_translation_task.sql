-- Add Speech Translation as a top-level Audio task; production chat users
-- searched for it but the catalog had no matching task.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    parent_id,
    level,
    image_url,
    image_credit,
    is_visible
)
VALUES (
    'Speech Translation',
    'speech-translation',
    'Speech translation converts spoken utterances in one language into text (speech-to-text translation) or speech (speech-to-speech translation) in another language. Systems are either cascades of [Automatic Speech Recognition](/tasks/automatic-speech-recognition) and [Machine Translation](/tasks/machine-translation), optionally followed by [Text-to-Speech](/tasks/text-to-speech), or end-to-end models that translate directly from audio, including simultaneous (streaming) translation and massively multilingual speech foundation models. It is evaluated with BLEU, chrF, and COMET (ASR-BLEU for speech output) on benchmarks such as MuST-C, CoVoST 2, CVSS, and FLEURS.',
    'speech translation, speech-to-text translation, speech to text translation, speech-to-speech translation, speech to speech translation, end-to-end speech translation, simultaneous speech translation, spoken language translation, direct speech translation, S2TT, S2ST, MuST-C, CoVoST',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    NULL,
    0,
    NULL,
    '[Sequence-to-Sequence Models Can Directly Translate Foreign Speech](https://arxiv.org/abs/1703.08581)',
    true
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    parent_id = EXCLUDED.parent_id,
    level = EXCLUDED.level,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;
