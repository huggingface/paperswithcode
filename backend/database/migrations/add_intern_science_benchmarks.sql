-- Add the scientific benchmarks reported by the InternLM Intern-S model family
-- (Intern-S1 arXiv:2508.15763, Intern-S1-Pro arXiv:2603.25040,
-- Intern-S2-Preview arXiv:2608.13505) to the Scientific Reasoning task.
--
-- Each benchmark gets one board on scientific-reasoning (task 992) with the
-- metric the benchmark reports, and its introducing paper is tagged with the
-- task. Evaluation rows are curated separately. SciCode already has its board
-- on code-generation and is left there. MP20 and ProteinBinder-9 are internal
-- Intern-S2 evaluation sets without a source paper, and SciTS is reported only
-- per subtask, so none of them is added.
--
-- Source papers must be indexed first (2005.00707 and 2608.00012 were indexed
-- with `python -m backend.cli paper index`).

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM tasks WHERE id = 992 AND slug = 'scientific-reasoning'
    ) THEN
        RAISE EXCEPTION 'Scientific Reasoning task identity precondition failed';
    END IF;

    IF (
        SELECT count(DISTINCT arxiv_id)
        FROM papers
        WHERE is_latest_version
          AND arxiv_id IN (
              '2506.10521',
              '2503.21821',
              '2402.09391',
              '2404.01475',
              '2005.00707',
              '2406.05540',
              '2503.13399',
              '2505.20740',
              '2503.23771',
              '2509.21320',
              '2306.08018',
              '2412.19191',
              '2601.15279',
              '2412.14642',
              '2608.00012',
              '2512.16969',
              '2606.07591'
          )
    ) <> 17 THEN
        RAISE EXCEPTION 'Intern science benchmark source paper precondition failed';
    END IF;

    IF (
        SELECT count(*) FROM metrics WHERE name IN ('Accuracy', 'Score')
    ) <> 2 THEN
        RAISE EXCEPTION 'Accuracy/Score metric precondition failed';
    END IF;
END
$$;

CREATE TEMP TABLE intern_science_benchmarks (
    slug varchar PRIMARY KEY,
    name varchar NOT NULL,
    full_name varchar NOT NULL,
    description text NOT NULL,
    url varchar,
    hf_url varchar,
    homepage varchar,
    arxiv_id varchar NOT NULL,
    metric varchar NOT NULL,
    aliases text[] NOT NULL
) ON COMMIT DROP;

INSERT INTO intern_science_benchmarks
    (slug, name, full_name, description, url, hf_url, homepage, arxiv_id, metric, aliases)
VALUES
    (
        'sfe',
        'SFE',
        'Scientists'' First Exam (SFE)',
        'Scientists'' First Exam (SFE) probes the scientific cognition of multimodal LLMs at three levels: signal perception, attribute understanding, and comparative reasoning. It contains 830 expert-verified visual question answering pairs across 66 multimodal tasks in five disciplines (astronomy, chemistry, earth science, life science, and materials science), built from raw scientific data formats in English and Chinese. Responses are graded with an LLM-as-a-judge score.',
        'https://github.com/PrismaX-Team/sfe',
        'https://huggingface.co/datasets/InternScience/SFE',
        'https://github.com/PrismaX-Team/sfe',
        '2506.10521',
        'Score',
        ARRAY['Scientists'' First Exam']::text[]
    ),
    (
        'physics',
        'PHYSICS',
        'PHYSICS: Benchmarking Foundation Models on University-Level Physics Problem Solving',
        'PHYSICS is a benchmark of 1,297 PhD-qualifying-exam physics problems (298 of them multimodal) spanning six core subfields: classical mechanics, quantum mechanics, thermodynamics and statistical mechanics, electromagnetism, atomic physics, and optics. Final answers are checked with automated symbolic equivalence verification. It is unrelated to the Physics-IQ video benchmark.',
        'https://github.com/yale-nlp/Physics',
        NULL,
        'https://github.com/yale-nlp/Physics',
        '2503.21821',
        'Accuracy',
        ARRAY[]::text[]
    ),
    (
        'smolinstruct',
        'SMolInstruct',
        'SMolInstruct (LlaSMol chemistry instruction benchmark)',
        'SMolInstruct (also written SmolInstruct) is a large-scale chemistry instruction dataset centred on small molecules, introduced with LlaSMol. It covers 14 tasks, including name conversion, property prediction, molecule captioning and generation, forward synthesis, and retrosynthesis, with about 3.3M query-response pairs in SMILES and SELFIES variants. Leaderboard scores average the task metrics on the official test split.',
        'https://github.com/OSU-NLP-Group/LLM4Chem',
        'https://huggingface.co/datasets/osunlp/SMolInstruct',
        'https://osu-nlp-group.github.io/LLM4Chem/',
        '2402.09391',
        'Score',
        ARRAY['SmolInstruct']::text[]
    ),
    (
        'chembench',
        'ChemBench',
        'ChemBench (Mirza et al., chemical knowledge and reasoning of LLMs)',
        'ChemBench is an automated framework for evaluating the chemical knowledge and reasoning of LLMs against human chemists. It contains 2,788 curated question-answer pairs spanning undergraduate and graduate chemistry topics, including multiple-choice and numeric questions on knowledge, calculation, reasoning, and chemical intuition. It is distinct from the ChemLLM ChemBench.',
        'https://github.com/lamalab-org/chembench',
        'https://huggingface.co/datasets/jablonkagroup/ChemBench',
        'https://chembench.lamalab.org/',
        '2404.01475',
        'Accuracy',
        ARRAY[]::text[]
    ),
    (
        'matbench',
        'MatBench',
        'MatBench (Matbench materials property prediction, LLM evaluation)',
        'Matbench is a standardized test suite of 13 supervised materials-property prediction tasks drawn from 10 density functional theory and experimental sources, with fixed cross-validation splits and the Automatminer reference algorithm. This leaderboard tracks the text-based LLM evaluation of Matbench tasks (as run in OpenCompass for the Intern-S models), reported as a single aggregate score; it is distinct from Matbench Discovery.',
        'https://github.com/materialsproject/matbench',
        NULL,
        'https://matbench.materialsproject.org/',
        '2005.00707',
        'Score',
        ARRAY[]::text[]
    ),
    (
        'proteinlmbench',
        'ProteinLMBench',
        'ProteinLMBench',
        'ProteinLMBench evaluates protein understanding in LLMs with 944 manually verified multiple-choice questions covering protein sequence, structure, and function. It is released together with a protein pretraining and supervised fine-tuning corpus.',
        'https://huggingface.co/datasets/tsynbio/ProteinLMBench',
        'https://huggingface.co/datasets/tsynbio/ProteinLMBench',
        'https://huggingface.co/datasets/tsynbio/ProteinLMBench',
        '2406.05540',
        'Accuracy',
        ARRAY[]::text[]
    ),
    (
        'microvqa',
        'MicroVQA',
        'MicroVQA: A Multimodal Reasoning Benchmark for Microscopy-Based Scientific Research',
        'MicroVQA is a microscopy-centred multimodal benchmark of 1,042 expert-curated multiple-choice questions across diverse imaging modalities and biological topics. It tests three research capabilities: expert image understanding, hypothesis generation, and experiment proposal.',
        'https://huggingface.co/datasets/jmhb/microvqa',
        'https://huggingface.co/datasets/jmhb/microvqa',
        'https://jmhb0.github.io/microvqa',
        '2503.13399',
        'Accuracy',
        ARRAY[]::text[]
    ),
    (
        'msearth-mcq',
        'MSEarth-MCQ',
        'MSEarth-MCQ (multiple-choice subset of MSEarth)',
        'MSEarth-MCQ is the multiple-choice subset of MSEarth, a multimodal Earth-science benchmark built from figures in high-quality Earth-science publications. It has about 2.78K figure-grounded questions across the atmosphere, cryosphere, hydrosphere, lithosphere, and biosphere.',
        'https://github.com/xiangyu-mm/MSEarth',
        'https://huggingface.co/datasets/PrismaX/MSEarth_MCQ',
        'https://github.com/xiangyu-mm/MSEarth',
        '2505.20740',
        'Accuracy',
        ARRAY['MSEarthMCQ']::text[]
    ),
    (
        'xlrs-bench',
        'XLRS-Bench',
        'XLRS-Bench: Extremely Large Ultra-High-Resolution Remote Sensing Benchmark',
        'XLRS-Bench evaluates multimodal LLMs on ultra-high-resolution remote-sensing imagery averaging about 8,500 x 8,500 pixels. Its human-verified annotations define 16 sub-tasks covering 6 perception and 4 reasoning abilities that reflect real-world remote-sensing scenarios.',
        'https://github.com/AI9Stars/XLRS-Bench',
        'https://huggingface.co/datasets/initiacms/XLRS-Bench-lite',
        'https://xlrs-bench.github.io/',
        '2503.23771',
        'Accuracy',
        ARRAY[]::text[]
    ),
    (
        'scireasoner',
        'SciReasoner',
        'SciReasoner scientific reasoning evaluation suite',
        'SciReasoner is a cross-disciplinary scientific evaluation suite released with the SciReasoner model. It spans 149 concrete tasks in 9 scientific domains, including physics, chemistry, biology, materials, and medicine, with formats such as multiple choice, fill-in-the-blank, sequence translation, and property prediction. Results are reported as an aggregate score across tasks.',
        'https://github.com/InternScience/SciReason',
        'https://huggingface.co/SciReason',
        'https://github.com/InternScience/SciReason',
        '2509.21320',
        'Score',
        ARRAY[]::text[]
    ),
    (
        'mol-instructions',
        'Mol-Instructions',
        'Mol-Instructions: A Large-Scale Biomolecular Instruction Dataset for Large Language Models',
        'Mol-Instructions is a biomolecular instruction dataset and benchmark for LLMs with three components: molecule-oriented, protein-oriented, and biomolecular text instructions. Tasks include molecule description and design, reaction prediction, protein function and design, and biomedical text understanding. Results are reported as an aggregate score across tasks.',
        'https://github.com/zjunlp/Mol-Instructions',
        'https://huggingface.co/datasets/zjunlp/Mol-Instructions',
        'https://github.com/zjunlp/Mol-Instructions',
        '2306.08018',
        'Score',
        ARRAY[]::text[]
    ),
    (
        'biology-instructions',
        'Biology-Instructions',
        'Biology-Instructions: Multi-Omics Sequence Understanding Benchmark',
        'Biology-Instructions is a multi-omics instruction dataset and benchmark that evaluates how well LLMs understand DNA, RNA, protein, and multi-molecule sequences. Its 21 tasks include promoter and enhancer detection, transcription-factor binding, RNA modification and isoform prediction, protein stability, solubility, and function, and cross-molecule interactions. Results are reported as the average score across tasks.',
        'https://github.com/hhnqqq/Biology-Instructions',
        NULL,
        'https://github.com/hhnqqq/Biology-Instructions',
        '2412.19191',
        'Score',
        ARRAY['Biology-Instruction']::text[]
    ),
    (
        'moleculariq',
        'MolecularIQ',
        'MolecularIQ: Symbolically Verified Chemical Reasoning on Molecular Graphs',
        'MolecularIQ evaluates whether language models reason faithfully over molecular graphs given as SMILES. It contains 5,111 symbolically verifiable questions about 849 structurally held-out molecules, grouped into counting, indexing, and constrained-generation task families, and reports overall accuracy.',
        'https://github.com/ml-jku/moleculariq',
        NULL,
        'https://github.com/ml-jku/moleculariq',
        '2601.15279',
        'Accuracy',
        ARRAY[]::text[]
    ),
    (
        'tomg-bench',
        'TOMG-Bench',
        'TOMG-Bench (S2-Bench): Text-based Open Molecule Generation Benchmark',
        'TOMG-Bench evaluates LLMs on open-domain, natural-language-driven molecule generation. It has three tasks (molecule editing, molecular property optimization, and customized molecule generation), each with three subtasks of 5,000 test samples. An automated framework checks validity, constraint satisfaction, and similarity or novelty, combined into a weighted success rate.',
        'https://github.com/phenixace/S2-TOMG-Bench',
        'https://huggingface.co/datasets/phenixace/S2-TOMG-Bench',
        'https://github.com/phenixace/S2-TOMG-Bench',
        '2412.14642',
        'Score',
        ARRAY[]::text[]
    ),
    (
        'obscrisis-bench',
        'ObsCrisis-Bench',
        'ObsCrisis-Bench (Obshazard-bench): Multimodal Disaster Intelligence from Raw Earth Observation',
        'ObsCrisis-Bench (released as Obshazard-bench) evaluates multimodal models on extreme-weather and geophysical disaster analysis from raw multispectral satellite sounding streams and optional weather-station measurements. It has 4,202 VQA samples covering 127 events, 8 disaster categories, and 61 countries, spanning early warning, event evolution, and impact and recovery assessment. A task-aware normalized score is averaged across disaster categories.',
        'https://huggingface.co/datasets/YYQ898/Obshazard-bench',
        'https://huggingface.co/datasets/YYQ898/Obshazard-bench',
        'https://huggingface.co/datasets/YYQ898/Obshazard-bench',
        '2608.00012',
        'Score',
        ARRAY['Obshazard-bench']::text[]
    ),
    (
        'sgi-bench',
        'SGI-Bench',
        'SGI-Bench: Scientific General Intelligence Benchmark',
        'SGI-Bench evaluates scientific general intelligence across the full inquiry cycle of the Practical Inquiry Model: deliberation, conception, action, and perception. It contains 1,263 expert-curated samples across ten scientific domains, covering scientific deep research, idea generation, dry and wet experiments, and multimodal experimental reasoning, scored with task-specific multi-dimensional metrics.',
        'https://github.com/InternScience/SGI-Bench',
        NULL,
        'https://internscience.github.io/SGI-Page/',
        '2512.16969',
        'Score',
        ARRAY[]::text[]
    ),
    (
        'researchclawbench',
        'ResearchClawBench',
        'ResearchClawBench: End-to-End Autonomous Scientific Research Benchmark',
        'ResearchClawBench evaluates whether autonomous agents can carry out end-to-end scientific research, from raw data and related literature to a publication-style report. It has 40 tasks derived from real papers across ten scientific domains, with the target paper withheld, and scores reports with expert-authored multimodal rubrics; 50 marks target-paper-level re-discovery.',
        'https://github.com/InternScience/ResearchClawBench',
        NULL,
        'https://internscience.github.io/ResearchClawBench-Home/',
        '2606.07591',
        'Score',
        ARRAY[]::text[]
    );

INSERT INTO datasets (
    name,
    full_name,
    slug,
    description,
    url,
    hf_url,
    homepage,
    introducing_paper_id,
    introducing_paper_title,
    paper_url,
    introduced_date,
    introduced_year,
    aliases
)
SELECT
    b.name,
    b.full_name,
    b.slug,
    b.description,
    b.url,
    b.hf_url,
    b.homepage,
    p.id,
    p.title,
    'https://paperswithcode.co/paper/' || p.arxiv_id,
    p.date_published,
    EXTRACT(YEAR FROM p.date_published)::int,
    b.aliases
FROM intern_science_benchmarks b
JOIN papers p ON p.arxiv_id = b.arxiv_id AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    url = EXCLUDED.url,
    hf_url = EXCLUDED.hf_url,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, 992, 'manual'
FROM intern_science_benchmarks b
JOIN papers p ON p.arxiv_id = b.arxiv_id AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT 992, d.id, FALSE
FROM intern_science_benchmarks b
JOIN datasets d ON d.slug = b.slug
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT 992, d.id, m.id
FROM intern_science_benchmarks b
JOIN datasets d ON d.slug = b.slug
JOIN metrics m ON m.name = b.metric
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
