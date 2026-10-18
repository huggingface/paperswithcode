-- Add CTC (no single introducing paper).
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog.

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
    'ctc',
    'CTC',
    'Connectionist Temporal Classification (CTC)',
    'Connectionist Temporal Classification (CTC) is an output layer and loss for training recurrent neural networks to label unsegmented sequence data directly, without pre-segmented training targets or post-processing of framewise outputs. The network emits, at each time step, a distribution over the label alphabet plus an extra ''blank'' symbol; a many-to-one map collapses repeated labels and removes blanks, so the probability of a target labelling is the sum over all alignment paths that map to it, computed efficiently with a forward-backward algorithm. Decoding uses best-path or prefix search. The original experiment on TIMIT phoneme recognition showed advantages over both an HMM baseline and a hybrid HMM-RNN. CTC became a cornerstone of end-to-end speech recognition and handwriting/scene-text recognition, is used as an auxiliary or primary objective on [Conformer](/methods/conformer) and [wav2vec 2.0](/methods/wav2vec) encoders, and inspired the [RNN-Transducer](/methods/rnn-transducer), which adds an output-dependency model to CTC''s conditionally independent outputs.',
    'connectionist temporal classification, CTC loss, CTC-based, CTC-Based, CTC decoding, CTC decoder, CTC/attention, CTC/Attention, CTC-attention, CTC-Attention, CTC prefix, CTC-prefix',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2006,
    NULL,
    'https://www.cs.toronto.edu/~graves/icml_2006.pdf',
    'Connectionist Temporal Classification: Labelling Unsegmented Sequence Data with Recurrent Neural Networks',
    'https://pytorch.org/docs/stable/generated/torch.nn.CTCLoss.html',
    NULL,
    '[Connectionist Temporal Classification: Labelling Unsegmented Sequence Data with Recurrent Neural Networks](https://www.cs.toronto.edu/~graves/icml_2006.pdf)'
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

-- 94 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE ctc_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ctc'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        458, 572, 905, 1264, 1613, 1649, 2797, 2875, 3309, 4975, 5031, 5069,
        5373, 5819, 6047, 6258, 6885, 7856, 9267, 9921, 10646, 10747, 11076, 11094,
        12589, 13311, 14236, 14719, 15769, 15772, 17356, 17374, 17994, 18099, 18712, 20416,
        20449, 20783, 23212, 25297, 25777, 26106, 27630, 32323, 35541, 38504, 40389, 42329,
        43502, 48696, 50208, 51159, 55187, 58818, 58963, 59555, 60222, 64101, 65389, 69910,
        71530, 71670, 71996, 74937, 74941, 76141, 76893, 79101, 79985, 80204, 80497, 80894,
        81204, 81558, 82228, 82324, 83084, 86063, 89740, 111220, 111426, 111482, 111518, 111629,
        111714, 111716, 111756, 111757, 111901, 112014, 112033, 112036, 116431, 122391
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ctc_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM ctc_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
