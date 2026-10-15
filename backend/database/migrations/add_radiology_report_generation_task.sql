-- Add Radiology Report Generation as a subtask of medical-imaging; production chat users searched for it
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
    'Radiology Report Generation',
    'radiology-report-generation',
    'Radiology report generation automatically writes the free-text findings and impression sections of a radiology report from medical images, most commonly chest X-rays. Reports must describe normal and abnormal observations accurately and completely, so beyond image captioning, models must handle long structured text, rare abnormalities, and clinical correctness, increasingly using vision-language and multimodal LLMs. It is a subtask of [Medical Imaging](/tasks/medical-imaging) related to [Medical Visual Question Answering](/tasks/medical-visual-question-answering), evaluated with natural-language metrics (BLEU, METEOR, ROUGE-L) and clinical-efficacy metrics (CheXpert F1, RadGraph F1, RadCliQ) on MIMIC-CXR and IU X-Ray.',
    'radiology report generation, medical report generation, chest X-ray report generation, CXR report generation, automatic radiology report generation, report generation from chest X-rays, radiology reporting, IU X-Ray',
    (SELECT area_id FROM tasks WHERE slug = 'medical-imaging' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'medical-imaging' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'medical-imaging' LIMIT 1),
    NULL,
    '[Generating Radiology Reports via Memory-driven Transformer](/paper/2010.16056)',
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
