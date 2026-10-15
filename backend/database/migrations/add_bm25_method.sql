-- BM25 emerged from the Okapi system at TREC-3 (1994) and Robertson & Walker's
-- 2-Poisson approximations, neither of which has a local paper row; the source is
-- the authors' canonical review and papers are linked from a reviewed set.

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
    'bm25',
    'BM25',
    'Okapi BM25',
    'BM25 (Best Matching 25), often called Okapi BM25, is a lexical ranking function that scores a document for a query by summing, over the query terms, the term''s inverse document frequency multiplied by a saturating function of its frequency in the document. The parameter k1 controls how quickly repeated occurrences stop adding score, and b controls normalization by document length relative to the corpus average. BM25 derives from the probabilistic relevance framework of Robertson and Spärck Jones and was developed for City University London''s Okapi system at TREC in 1994. Fast to compute with an inverted index and strong without training, it remains the standard sparse retrieval baseline, the first stage of many retrieve-and-rerank pipelines, the lexical half of hybrid search, and a common retriever in [RAG](/methods/rag); learned retrievers such as [Dense Passage Retrieval](/methods/dense-passage-retrieval) are routinely compared against it.',
    'BM25, Okapi BM25',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    1994,
    NULL,
    'https://doi.org/10.1561/1500000019',
    'The Probabilistic Relevance Framework: BM25 and Beyond (Robertson & Zaragoza, 2009)',
    'https://github.com/castorini/pyserini',
    NULL,
    NULL
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

-- Curated 2026-10-15 from every title/abstract mention of BM25: each paper below retrieves with, extends, evaluates or analyzes BM25.
CREATE TEMP TABLE bm25_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bm25'
  AND p.id IN (
        3406, -- Learning Term Discrimination
        3441, -- Complementing Lexical Retrieval with Semantic Residual Embedding
        4097, -- Revisiting the Open-Domain Question Answering Pipeline
        4170, -- Generation-Augmented Retrieval for Open-domain Question Answering
        4385, -- CoRT: Complementary Rankings from Transformers
        4944, -- Regulatory Compliance through Doc2Doc Information Retrieval: A case st
        5505, -- BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information
        5710, -- Yes, BM25 is a Strong Baseline for Legal Case Retrieval
        6449, -- Mr. TyDi: A Multi-lingual Benchmark for Dense Retrieval
        6531, -- Boosting Search Engines with Interactive Agents
        6920, -- Salient Phrase Aware Dense Retrieval: Can a Dense Retriever Imitate a
        7636, -- Establishing Strong Baselines for TripClick Health Retrieval
        7771, -- Out-of-Domain Semantics to the Rescue! Zero-Shot Hybrid Retrieval Mode
        8706, -- Multilingual Event Linking to Wikidata
        8891, -- To Interpolate or not to Interpolate: PRF, Dense and Sparse Retrievers
        9499, -- Towards Robust Ranker for Text Retrieval
        12305, -- InPars-v2: Large Language Models as Efficient Dataset Generators for I
        12340, -- InPars-Light: Cost-Effective Unsupervised Training of Efficient Ranker
        13737, -- Query2doc: Query Expansion with Large Language Models
        15017, -- Large Language Models are Strong Zero-Shot Retriever
        15426, -- Evaluating Embedding APIs for Information Retrieval
        15987, -- Conversational Recommendation as Retrieval: A Simple, Strong Baseline
        16012, -- DAPR: A Benchmark on Document-Aware Passage Retrieval
        16394, -- Expand, Rerank, and Retrieve: Query Reranking for Open-Domain Question
        16661, -- BEIR-PL: Zero Shot Information Retrieval Benchmark for the Polish Lang
        18859, -- Evaluating Instruction-Tuned Large Language Models on Code Comprehensi
        23410, -- Sequencing Matters: A Generate-Retrieve-Generate Model for Building Co
        28498, -- Large Language Models are In-Context Molecule Learners
        31241, -- ViWikiFC: Fact-Checking for Vietnamese Wikipedia-Based Textual Knowled
        33626, -- DEXTER: A Benchmark for open-domain Complex Question Answering using L
        34136, -- BM25S: Orders of magnitude faster lexical search via eager sparse scor
        35249, -- LitSearch: A Retrieval Benchmark for Scientific Literature Search
        35885, -- W-RAG: Weakly Supervised Dense Retrieval in RAG for Open-domain Questi
        38423, -- EasyRAG: Efficient Retrieval-Augmented Generation Framework for Automa
        39197, -- Telco-DPR: A Hybrid Dataset for Evaluating Retrieval Models of 3GPP Te
        41012, -- Domain-specific Question Answering with Hybrid Search
        41303, -- Bilingual BSARD: Extending Statutory Article Retrieval to Dutch
        41369, -- BEIR-NL: Zero-shot Information Retrieval Benchmark for the Dutch Langu
        42286, -- GliLem: Leveraging GliNER for Contextualized Lemmatization in Estonian
        42655, -- SWE-Fixer: Training Open-Source LLMs for Effective and Efficient GitHu
        43246, -- ASRank: Zero-Shot Re-Ranking with Answer Scent for Document Retrieval
        43916, -- CliniQ: A Multi-faceted Benchmark for Electronic Health Record Retriev
        44865, -- A Hybrid Approach to Information Retrieval and Answer Generation for R
        44901, -- Language Model Re-rankers are Steered by Lexical Similarities
        45162, -- From Retrieval to Generation: Comparing Different Approaches
        45871, -- JurisTCU: A Brazilian Portuguese Information Retrieval Dataset with Qu
        48069, -- CLIRudit: Cross-Lingual Information Retrieval of Scientific Documents
        48245, -- Don't Retrieve, Generate: Prompting LLMs for Synthetic Training Data i
        48671, -- Efficient and Reproducible Biomedical Question Answering using Retriev
        49113, -- Benchmarking the Myopic Trap: Positional Bias in Information Retrieval
        49175, -- Rank-K: Test-Time Reasoning for Listwise Reranking
        51176, -- Knowledge Compression via Question Generation: Enhancing Multihop Docu
        51193, -- InsertRank: LLMs can reason over BM25 scores to Improve Listwise Reran
        52287, -- BrowseComp-Plus: A More Fair and Transparent Evaluation Benchmark of D
        55827, -- SAGE: Benchmarking and Improving Retrieval for Deep Research Agents
        56285, -- RankEvolve: Automating the Discovery of Retrieval Algorithms via LLM-D
        58514, -- An Empirical Study of Many-Shot In-Context Learning for Machine Transl
        59053, -- ECI: Effective Contrastive Information to Evaluate Hard-Negatives
        59478, -- Structured Distillation for Personalized Agent Memory: 11x Token Reduc
        59826, -- StratRAG: A Multi-Hop Retrieval Evaluation Dataset for Retrieval-Augme
        59921, -- Nepali Passport Question Answering: A Low-Resource Dataset for Public
        61129, -- IRPAPERS: A Visual Document Benchmark for Scientific Retrieval and Que
        61942, -- S^3-Attention:Attention-Aligned Endogenous Retrieval for Memory-Bounde
        63733, -- Intelligent Scientific Literature Explorer using Machine Learning (ISL
        69363, -- SynthCoder: A Synthetical Strategy to Tune LLMs for Code Completion
        70319, -- Quantum-RAG and PunGPT2: Advancing Low-Resource Language Generation an
        70719, -- Injecting External Knowledge into the Reasoning Process Enhances Retri
        71070, -- Advancing Retrieval-Augmented Generation for Structured Enterprise and
        72014, -- TongSearch-QR: Reinforced Query Reasoning for Retrieval
        72273, -- LeanExplore: A search engine for Lean 4 declarations
        72275, -- T^2-RAGBench: Text-and-Table Benchmark for Evaluating Retrieval-Augmen
        75101, -- An Empirical Study of Retrieval-Augmented Code Generation: Challenges
        83010, -- Rethinking Agentic Search with Pi-Serini: Is Lexical Retrieval Suffici
        97974, -- Towards Retrieving Interaction Spaces for Agentic Search
        98394, -- DAT: Dynamic Alpha Tuning for Hybrid Retrieval in Retrieval-Augmented
        104473, -- AutoIndex: Learning Representation Programs for Retrieval
        105932, -- BM25 Wins at Scale: A Scaling Study of Retrieval-Augmented Generation
        107861, -- LiteLong: Resource-Efficient Long-Context Data Synthesis for LLMs
        109023, -- SuperLocalMemory 4.0: The Governed Memory Operating System for AI Agen
        110307, -- MoR: Better Handling Diverse Queries with a Mixture of Sparse, Dense,
        110774 -- Pathway to Relevance: How Cross-Encoders Implement a Semantic Variant
  );

DELETE FROM paper_method_exclusions x
USING bm25_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM bm25_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM bm25_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: BM25 appears only as a baseline the paper outperforms or as background.
CREATE TEMP TABLE bm25_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bm25'
  AND p.id IN (
        2181, -- Latent Retrieval for Weakly Supervised Open Domain Question Answering
        2693, -- Universal Text Representation from BERT: An Empirical Study
        3335, -- Dense Passage Retrieval for Open-Domain Question Answering
        3530, -- MultiReQA: A Cross-Domain Evaluation for Retrieval Question Answering
        4796, -- The Curse of Dense Low-Dimensional Information Retrieval for Large Ind
        4832, -- Multi-task Retrieval for Knowledge-Intensive Tasks
        5450, -- Efficiently Teaching an Effective Dense Retriever with Balanced Topic
        5460, -- COIL: Revisit Exact Lexical Match in Information Retrieval with Contex
        7500, -- Learning to Retrieve Passages without Supervision
        7548, -- Unsupervised Dense Information Retrieval with Contrastive Learning
        7565, -- The Web Is Your Oyster -- Knowledge-Intensive NLP against a Very Large
        7570, -- Article Reranking by Memory-Enhanced Key Sentence Matching for Detecti
        7741, -- Transfer Learning Approaches for Building Cross-Language Dense Retriev
        7926, -- InPars: Data Augmentation for Information Retrieval using Large Langua
        7964, -- Transformer Memory as a Differentiable Search Index
        8787, -- Synthetic Target Domain Supervision for Open Retrieval QA
        9132, -- Towards Tracing Factual Knowledge in Language Models Back to the Train
        9545, -- SPBERTQA: A Two-Stage Question Answering System Based on Sentence Tran
        9697, -- The Role of Complex NLP in Transformers for Text Ranking?
        9721, -- An Efficiency Study for SPLADE Models
        11846, -- Text Embeddings by Weakly-Supervised Contrastive Pre-training
        11910, -- Natural Logic-guided Autoregressive Multi-hop Document Retrieval for F
        14693, -- Automatic Semantic Augmentation of Language Model Prompts (for Code Su
        15780, -- Searching by Code: a New SearchBySnippet Dataset and SnippeR Retrieval
        18154, -- U-CREAT: Unsupervised Case Retrieval using Events extrAcTion
        18303, -- Soft Prompt Tuning for Augmenting Dense Retrieval with Large Language
        22345, -- PaRaDe: Passage Ranking using Demonstrations with Large Language Model
        25560, -- Building Efficient and Effective OpenQA Systems for Low-Resource Langu
        26429, -- ConFit: Improving Resume-Job Matching using Data Augmentation and Cont
        27757, -- Analysing The Impact of Sequence Composition on Language Model Pre-Tra
        28667, -- SPLADE-v3: New baselines for SPLADE
        31039, -- Semi-Parametric Retrieval via Binary Bag-of-Tokens Index
        33084, -- Unifying Multimodal Retrieval via Document Screenshot Embedding
        38784, -- Optimizing Retrieval-Augmented Generation with Elasticsearch for Enhan
        39718, -- Towards Competitive Search Relevance For Inference-Free Learned Sparse
        44441, -- ConFit v2: Improving Resume-Job Matching using Hypothetical Resume Emb
        46410, -- Task-Specific Data Selection for Instruction Tuning via Monosemantic N
        47063, -- Rec-R1: Bridging Generative Large Language Models and User-Centric Rec
        47118, -- ScholarCopilot: Training Large Language Models for Academic Writing wi
        48875, -- TARGET: Benchmarking Table Retrieval for Generative Tasks
        49609, -- RaDeR: Reasoning-aware Dense Retrieval Models
        49743, -- Anveshana: A New Benchmark Dataset for Cross-Lingual Information Retri
        52770, -- ClaimIQ at CheckThat! 2025: Comparing Prompted and Fine-Tuned Language
        53197, -- TalkPlay-Tools: Conversational Music Recommendation with LLM Tool Call
        58808, -- A Reference Architecture for Agentic Hybrid Retrieval in Dataset Searc
        59889, -- AgentIR: Reasoning-Aware Retrieval for Deep Research Agents
        59897, -- Retrieval or Representation? Reassessing Benchmark Gaps in Multilingua
        59949, -- The Science Data Lake: A Unified Open Infrastructure Integrating 293 M
        61213, -- SpIDER: Spatially Informed Dense Embedding Retrieval for Software Issu
        62237, -- Beyond the Geometric Curse: High-Dimensional N-Gram Hashing for Dense
        62901, -- STELLA: Self-Reflective Terminology-Aware Framework for Building an Ae
        64864, -- NeuCLIRBench: A Modern Evaluation Collection for Monolingual, Cross-La
        65858, -- Contextual Tokenization for Graph Inverted Indices
        70086, -- Query Attribute Modeling: Improving search relevance with Semantic Sea
        70166, -- A Comparative Study of Specialized LLMs as Dense Retrievers
        72645, -- ReSCORE: Label-free Iterative Retriever Training for Multi-hop Questio
        76674, -- RLCoder: Reinforcement Learning for Repository-Level Code Completion
        77352, -- Efficient Inverted Indexes for Approximate Retrieval over Learned Spar
        91156, -- Scalable Influence and Fact Tracing for Large Language Model Pretraini
        98484, -- Dr-DCI: Scaling Direct Corpus Interaction via Dynamic Workspace Expans
        98707, -- HAKARI-Bench: A Lightweight Benchmark for Comparing Retrieval Architec
        103817, -- CVPD at QIAS 2026: RAG-Guided LLM Reasoning for Al-Mawarith Share Comp
        107442, -- MicLog: Towards Accurate and Efficient LLM-based Log Parsing via Progr
        108705, -- Inference-Free Multimodal Learned Sparse Retrieval for Production-Scal
        108936, -- Teaching Nemotron Greek: Mining a Corpus, Adapting Retrieval, and Grou
        110491, -- Media Source Matters More Than Content: Unveiling Political Bias in LL
        110650, -- RPDR: A Round-trip Prediction-Based Data Augmentation Framework for Lo
        113890, -- ExecRetrieval: Measuring the Functional-Correctness Gap in Code-Embedd
        114088 -- PlannerForge: LLM Agents for Scenario-Based Testing of Motion Planners
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'BM25 curation 2026-10-15: mentions BM25 only as a baseline'
FROM bm25_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING bm25_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING bm25_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
