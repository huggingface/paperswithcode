-- "catastrophic forgetting" tagged 329 fine-tuning and transfer papers that
-- mention forgetting in passing but are not continual learning. Drop it;
-- rebuild this task's auto tags afterwards with
-- link_papers_by_task_keywords.py --rebuild --task-slug continual-learning.
UPDATE tasks
SET keywords = array_to_string(
        array_remove(
            array(SELECT trim(k) FROM unnest(string_to_array(keywords, ',')) AS k),
            'catastrophic forgetting'
        ),
        ', '
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'continual-learning';
