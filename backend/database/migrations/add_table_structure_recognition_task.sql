-- Table Structure Recognition task: subtask of document-understanding.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Table Structure Recognition',
    'table-structure-recognition',
    'Table structure recognition recovers the logical structure of a table from a document image or PDF page: its rows, columns, cell boundaries, spanning cells and header hierarchy, usually output as HTML, LaTeX or a cell-adjacency graph together with the cell contents. It turns scanned papers, financial reports and forms into machine-readable data, and is typically paired with table detection from [Document Layout Analysis](/tasks/document-layout-analysis) and text recognition from [OCR](/tasks/ocr). Standard benchmarks are PubTabNet, FinTabNet, SciTSR and PubTables-1M, scored with TEDS and cell-adjacency F1. Recognized tables feed downstream [Table question answering](/tasks/table-question-answering).',
    'table structure recognition, table recognition, table structure extraction, table structure understanding, table structure parsing, table parsing, table extraction',
    (SELECT area_id FROM tasks WHERE slug = 'document-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'document-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'document-understanding' LIMIT 1),
    true,
    NULL,
    '[TableFormer: Table Structure Understanding with Transformers](/paper/2203.01017)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
