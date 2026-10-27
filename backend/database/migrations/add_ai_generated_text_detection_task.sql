INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'AI-Generated Text Detection',
    'ai-generated-text-detection',
    'AI-generated text detection decides whether a passage was written by a human or produced by a language model, sometimes also attributing it to the source model or locating machine-written spans in mixed human-AI text. Approaches range from zero-shot statistical scores such as likelihood, rank, and probability curvature to fine-tuned neural classifiers and stylometric features, and are evaluated for robustness to unseen generators, domains, languages, and paraphrasing attacks. It complements [Fake News Detection](/tasks/fake-news-detection) and [Deepfake Detection](/tasks/deepfake-detection), and matters for academic integrity, peer review, journalism, and content moderation. Common metrics include AUROC, accuracy, F1, and TPR at a fixed low false-positive rate.',
    'ai-generated text detection, ai-generated text detector, ai generated text detection, ai text detection, ai text detector, ai-text detection, ai-written text detection, ai-generated text identification, ai-generated text classifier, llm-generated text detection, llm-generated text detector, llm text detection, machine-generated text detection, machine-generated text detector, machine generated text detection, machine-generated text identification, detecting machine-generated text, detecting ai-generated text, detecting llm-generated text, detection of machine-generated text, detection of ai-generated text, detection of llm-generated text, mgt detection, aigt detection, MGTD, DetectGPT, ai-generated essay detection, ai-generated code detection, machine-generated code detection, ai authorship detection, human-written vs. ai-generated text, human-written and machine-generated text, human-written and ai-generated text, human-written and llm-generated text',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    NULL,
    '[DetectGPT: Zero-Shot Machine-Generated Text Detection using Probability Curvature](/paper/2301.11305)',
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

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES ('fake-news-detection', 0), ('deepfake-detection', 1)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'ai-generated-text-detection'
ON CONFLICT DO NOTHING;
