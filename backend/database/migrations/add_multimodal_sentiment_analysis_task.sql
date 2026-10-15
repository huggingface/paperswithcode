-- Add Multimodal Sentiment Analysis as a top-level General task; production chat users
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
    'Multimodal Sentiment Analysis',
    'multimodal-sentiment-analysis',
    'Multimodal sentiment analysis predicts the sentiment or sentiment intensity of a speaker from aligned language, acoustic, and visual signals, typically utterances in online videos. Beyond what is said, tone of voice and facial expressions can reinforce or contradict the text, so models focus on cross-modal fusion, alignment of asynchronous streams, and learning modality-invariant and modality-specific representations. It is closely related to multimodal [Emotion Recognition](/tasks/emotion-recognition) and [Text Classification](/tasks/text-classification), and is evaluated with binary and 7-class accuracy, F1, MAE, and correlation on CMU-MOSI, CMU-MOSEI, and CH-SIMS.',
    'multimodal sentiment analysis, multi-modal sentiment analysis, multimodal sentiment classification, video sentiment analysis, multimodal opinion sentiment, multimodal sentiment intensity, CMU-MOSI, CMU-MOSEI, CH-SIMS',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    0,
    NULL,
    '[MISA: Modality-Invariant and -Specific Representations for Multimodal Sentiment Analysis](https://arxiv.org/abs/2005.03545)',
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
