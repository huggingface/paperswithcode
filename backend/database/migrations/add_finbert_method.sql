-- Add FinBERT method, introduced in arXiv 1908.10063. The source paper
-- gets the source evidence row (Introduced banner); citers are linked by
-- link_papers_by_source_citations.py and the hourly reference backfill.

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'finbert',
    'FinBERT',
    'FinBERT',
    'FinBERT is a [BERT](/methods/bert) language model adapted to financial text. The original model further pre-trains BERT on a financial corpus (the Reuters TRC2-financial subset) and fine-tunes it for financial sentiment analysis on the Financial PhraseBank and FiQA sentiment datasets. Domain adaptation lets it outperform earlier machine-learning and deep-learning sentiment classifiers, including on small training sets, and the released checkpoint became a widely used off-the-shelf financial sentiment model. Several later models also use the name FinBERT, for example BERT models pre-trained from scratch on corporate filings, analyst reports and earnings call transcripts.',
    'FinBERT',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2019,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1908.10063'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'FinBERT: Financial Sentiment Analysis with Pre-trained Language Models',
    'https://github.com/ProsusAI/finBERT',
    NULL,
    '[FinBERT: Financial Sentiment Analysis with Pre-trained Language Models](/paper/1908.10063)'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'finbert'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'finbert'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
