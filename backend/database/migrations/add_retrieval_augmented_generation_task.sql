-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    level,
    parent_id,
    image_url,
    image_credit,
    useful_leaderboards
)
VALUES (
    'Retrieval-Augmented Generation',
    'retrieval-augmented-generation',
    'Retrieval-augmented generation (RAG) grounds a language model''s output in documents fetched from an external corpus at inference time. A retriever, such as BM25, a dense embedding model or a hybrid search, selects passages for the query, and the generator conditions on them to answer, cite sources or write long-form text. This reduces hallucination and lets models use private or up-to-date knowledge without retraining. Research covers [retrieval](/tasks/retrieval) quality and [reranking](/tasks/text-reranking), chunking and indexing, iterative and agentic retrieval, [GraphRAG](/methods/graphrag), and the evaluation of answer faithfulness on multi-hop [question answering](/tasks/question-answering) benchmarks.',
    'retrieval-augmented generation, retrieval augmented generation, RAG, retrieval-augmented language model, retrieval-augmented LLM, retrieval-augmented large language model, agentic RAG, multimodal RAG',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](/paper/2005.11401)',
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
