-- Add Fake News Detection as a top-level Language task; production chat users
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
    'Fake News Detection',
    'fake-news-detection',
    'Fake news detection classifies news articles, claims, or social media posts as genuine or fabricated and misleading. Models use the linguistic and visual content of a news item together with social context such as propagation patterns, user engagement, and source credibility, and increasingly address multimodal posts and LLM-generated misinformation. It is a form of [Text Classification](/tasks/text-classification) closely related to fact checking, rumor detection, and [Deepfake Detection](/tasks/deepfake-detection), and is evaluated with accuracy and F1 on datasets such as LIAR, FakeNewsNet (PolitiFact, GossipCop), Weibo, and Twitter.',
    'fake news detection, fake news classification, misinformation detection, disinformation detection, rumor detection, rumour detection, multimodal fake news detection, fake news, false news detection, LIAR dataset, FakeNewsNet',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    0,
    NULL,
    '[FakeNewsNet: A Data Repository with News Content, Social Context and Spatiotemporal Information for Studying Fake News on Social Media](/paper/1809.01286)',
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
