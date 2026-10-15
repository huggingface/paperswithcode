-- Add Aspect-Based Sentiment Analysis as a subtask of text-classification; production chat users searched for it
-- but the catalog had no matching task.

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
    'Aspect-Based Sentiment Analysis',
    'aspect-based-sentiment-analysis',
    'Aspect-based sentiment analysis (ABSA) determines the sentiment expressed toward specific aspects of an entity in text, rather than assigning a single polarity to the whole sentence or review. It covers subtasks such as aspect term extraction, aspect category detection, opinion term extraction, and aspect sentiment classification, as well as compound tasks that extract aspect-opinion-sentiment triplets or quadruples. A fine-grained form of [Text Classification](/tasks/text-classification) that also draws on [Named Entity Recognition](/tasks/named-entity-recognition)-style span extraction, it is commonly evaluated with accuracy and F1 on the SemEval 2014-2016 restaurant and laptop datasets.',
    'aspect-based sentiment analysis, aspect based sentiment analysis, ABSA, aspect sentiment classification, aspect-level sentiment classification, aspect-level sentiment analysis, aspect term extraction, aspect sentiment triplet extraction, aspect sentiment quad prediction, aspect category sentiment analysis, targeted sentiment analysis, target-oriented opinion words extraction',
    (SELECT area_id FROM tasks WHERE slug = 'text-classification' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'text-classification' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'text-classification' LIMIT 1),
    NULL,
    '[A Survey on Aspect-Based Sentiment Analysis: Tasks, Methods, and Challenges](https://arxiv.org/abs/2203.01054)',
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
