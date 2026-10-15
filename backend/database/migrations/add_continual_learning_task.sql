-- Add Continual Learning as a top-level General task; production chat users
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
    'Continual Learning',
    'continual-learning',
    'Continual learning (also called lifelong or incremental learning) trains a model on a sequence of tasks, classes, or domains that arrive over time while retaining what it learned earlier. The central challenge is catastrophic forgetting: balancing stability on old knowledge with plasticity for new data, usually under limited memory and compute. Settings include task-, domain-, and class-incremental learning, few-shot class-incremental learning, and continual pre-training or instruction tuning of large models, with methods based on replay, regularization, parameter isolation, and prompts. It is closely related to [Domain Generalization](/tasks/domain-generalization) and is typically evaluated on incremental splits of [Image Classification](/tasks/image-classification) benchmarks such as Split CIFAR-100 and ImageNet-R.',
    'continual learning, lifelong learning, life-long learning, incremental learning, class-incremental learning, class incremental learning, task-incremental learning, task incremental learning, domain-incremental learning, domain incremental learning, few-shot class-incremental learning, few-shot class incremental learning, FSCIL, online continual learning, continual pre-training, continual pretraining, continual instruction tuning, catastrophic forgetting, rehearsal-free continual learning, exemplar-free class-incremental learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    0,
    NULL,
    '[A Comprehensive Survey of Continual Learning: Theory, Method and Application](/paper/2302.00487)',
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
