-- Chat lookup-miss taxonomy gap fill (2026-10-29 audit): 24 tasks and 6 methods.
-- Applied to production on 2026-10-29; hero images were imported separately with import_entity_image.py.

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Open-Vocabulary Object Detection',
    'open-vocabulary-object-detection',
    'Open-vocabulary object detection localizes and names objects from categories described in free-form text, including categories never seen with box labels during training. Detectors typically align region features with a vision-language model such as CLIP and are evaluated on novel-category AP on LVIS and COCO splits. It extends [Object Detection](/tasks/object-detection) beyond a fixed label set and is closely related to [Visual Grounding](/tasks/visual-grounding).',
    'open-vocabulary object detection, open-vocabulary detection, open vocabulary object detection, open-vocabulary detector, open-set object detection, OVD, OVOD',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-detection'),
    (SELECT id FROM tasks WHERE slug = 'object-detection'),
    '[Open-Vocabulary Object Detection Using Captions](https://arxiv.org/abs/2011.10678)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Semi-Supervised Object Detection',
    'semi-supervised-object-detection',
    'Semi-supervised object detection trains detectors from a small set of box-labeled images plus a large pool of unlabeled images, usually through teacher-student pseudo-labeling and consistency regularization. Benchmarks report COCO mAP with 1%, 5%, or 10% of labels and PASCAL VOC with extra unlabeled data. It is the detection counterpart of [Semi-Supervised Image Classification](/tasks/semi-supervised-image-classification) within [Object Detection](/tasks/object-detection).',
    'semi-supervised object detection, semi-supervised detection, semi-supervised detector, SSOD',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-detection'),
    (SELECT id FROM tasks WHERE slug = 'object-detection'),
    '[A Simple Semi-Supervised Learning Framework for Object Detection](https://arxiv.org/abs/2005.04757)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Video Object Detection',
    'video-object-detection',
    'Video object detection detects and classifies objects in every frame of a video, using temporal context across frames to handle motion blur, occlusion, and rare poses that defeat single-image detectors. ImageNet VID mAP is the standard benchmark. It extends [Object Detection](/tasks/object-detection) to the temporal domain and differs from [Object Tracking](/tasks/object-tracking), which links identities over time.',
    'video object detection, object detection in videos, object detection in video',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-detection'),
    (SELECT id FROM tasks WHERE slug = 'object-detection'),
    '[Flow-Guided Feature Aggregation for Video Object Detection](https://arxiv.org/abs/1703.10025)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Panoptic Segmentation',
    'panoptic-segmentation',
    'Panoptic segmentation assigns every pixel a semantic class and, for countable objects, an instance identity, unifying semantic and [Instance Segmentation](/tasks/instance-segmentation) in one output. Results are reported as Panoptic Quality (PQ) on COCO Panoptic, Cityscapes, ADE20K, and Mapillary Vistas. It is a subtask of [Image Segmentation](/tasks/image-segmentation).',
    'panoptic segmentation, panoptic quality, panoptic segmenter, video panoptic segmentation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-segmentation'),
    (SELECT id FROM tasks WHERE slug = 'image-segmentation'),
    '[Panoptic Segmentation](/paper/1801.00868)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Few-Shot Segmentation',
    'few-shot-segmentation',
    'Few-shot segmentation segments objects of a novel class in a query image given only one or a few annotated support images of that class. Methods match support prototypes or dense correlations to the query and are evaluated by mIoU on PASCAL-5i and COCO-20i folds. It is a low-data subtask of [Image Segmentation](/tasks/image-segmentation) related to [Zero-Shot Segmentation](/tasks/zero-shot-segmentation).',
    'few-shot segmentation, few-shot semantic segmentation, one-shot segmentation, one-shot semantic segmentation, few-shot image segmentation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-segmentation'),
    (SELECT id FROM tasks WHERE slug = 'image-segmentation'),
    '[One-Shot Learning for Semantic Segmentation](/paper/1709.03410)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Medical Image Segmentation',
    'medical-image-segmentation',
    'Medical image segmentation delineates organs, tumors, lesions, and other structures in CT, MRI, ultrasound, endoscopy, and microscopy images. Models such as U-Net variants and promptable foundation models are evaluated with Dice and Hausdorff distance on benchmarks like BraTS, Synapse multi-organ, ACDC, and Kvasir-SEG. It is a subtask of [Medical Imaging](/tasks/medical-imaging) built on [Image Segmentation](/tasks/image-segmentation).',
    'medical image segmentation, medical segmentation, organ segmentation, tumor segmentation, tumour segmentation, lesion segmentation, polyp segmentation, brain tumor segmentation, multi-organ segmentation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'medical-imaging'),
    (SELECT id FROM tasks WHERE slug = 'medical-imaging'),
    '[A large annotated medical image dataset for the development and evaluation of segmentation algorithms](/paper/1902.09063)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Face Detection',
    'face-detection',
    'Face detection finds every face in an image and returns its bounding box, often with facial landmarks. It must handle tiny, occluded, and heavily posed faces and is benchmarked by AP on the WIDER FACE easy, medium, and hard splits. It is the first stage of most face pipelines such as [Face Recognition](/tasks/face-recognition) and [Facial Landmark Detection](/tasks/facial-landmark-detection).',
    'face detection, face detector, facial detection, detecting faces',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    '[WIDER FACE: A Face Detection Benchmark](/paper/1511.06523)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Facial Expression Recognition',
    'facial-expression-recognition',
    'Facial expression recognition classifies the emotion or expression shown on a face, such as happiness, anger, or surprise, from images or video. Models are evaluated by accuracy on in-the-wild datasets like RAF-DB, AffectNet, and FER2013. It builds on [Face Detection](/tasks/face-detection) and relates to [Facial Landmark Detection](/tasks/facial-landmark-detection).',
    'facial expression recognition, facial emotion recognition, facial affect recognition',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    '[AffectNet: A Database for Facial Expression, Valence, and Arousal Computing in the Wild](/paper/1708.03985)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Micro-Expression Recognition',
    'micro-expression-recognition',
    'Micro-expression recognition identifies brief, involuntary facial expressions that last a fraction of a second and reveal concealed emotions. Methods model subtle motion with optical flow or apex-frame features and report accuracy and UF1 on CASME II, SAMM, and SMIC, often under a composite leave-one-subject-out protocol. It is a subtask of [Facial Expression Recognition](/tasks/facial-expression-recognition).',
    'micro-expression recognition, micro-expression, micro expression recognition, facial micro-expression, micro-expression spotting',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'facial-expression-recognition'),
    (SELECT id FROM tasks WHERE slug = 'facial-expression-recognition'),
    '[A Survey of Automatic Facial Micro-expression Analysis: Databases, Methods and Challenges](https://arxiv.org/abs/1806.05781)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Age Estimation',
    'age-estimation',
    'Age estimation predicts a person''s age from a face image, treated as regression, ordinal classification, or label-distribution learning. Mean absolute error on MORPH II, FG-NET, CACD, and UTKFace is the standard metric. It is a facial-analysis task related to [Face Recognition](/tasks/face-recognition) and [Facial Expression Recognition](/tasks/facial-expression-recognition).',
    'age estimation, facial age estimation, age prediction from face, apparent age estimation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    '[Deep Label Distribution Learning With Label Ambiguity](/paper/1611.01731)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Image-Text Retrieval',
    'image-text-retrieval',
    'Image-text retrieval ranks images for a text query and captions for an image query by embedding both modalities in a shared space. Vision-language models such as CLIP and BLIP are evaluated by Recall@K on Flickr30K and MS-COCO 5K. It is the cross-modal subtask of [Image Retrieval](/tasks/image-retrieval), with [Video-Text Retrieval](/tasks/video-text-retrieval) as its video counterpart.',
    'image-text retrieval, image-text matching, text-to-image retrieval, image-to-text retrieval, cross-modal retrieval, text-image retrieval, image-caption retrieval',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-retrieval'),
    (SELECT id FROM tasks WHERE slug = 'image-retrieval'),
    '[Stacked Cross Attention for Image-Text Matching](https://arxiv.org/abs/1803.08024)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Chart Understanding',
    'chart-understanding',
    'Chart understanding reads plots and charts to answer questions, extract the underlying data table, or summarize trends, which requires combining OCR, visual parsing, and numerical reasoning. Multimodal models are evaluated on ChartQA, CharXiv, and PlotQA. It is a subtask of [Document Understanding](/tasks/document-understanding).',
    'chart understanding, chart question answering, chart reasoning, chart comprehension, chart-to-table, chart summarization, ChartQA',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'document-understanding'),
    (SELECT id FROM tasks WHERE slug = 'document-understanding'),
    '[ChartQA: A Benchmark for Question Answering about Charts with Visual and Logical Reasoning](/paper/2203.10244)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Topic Modeling',
    'topic-modeling',
    'Topic modeling discovers the latent themes in a document collection and represents each document as a mixture of topics, from probabilistic models like latent Dirichlet allocation to neural and embedding-clustering approaches such as BERTopic. Topic coherence (NPMI, C_V) and diversity on corpora like 20 Newsgroups are the usual metrics. It relates to [Text Classification](/tasks/text-classification) as an unsupervised way to organize text.',
    'topic modeling, topic modelling, topic model, neural topic model, topic discovery, topic extraction',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    '[Top2Vec: Distributed Representations of Topics](/paper/2008.09470)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Natural Language Inference',
    'natural-language-inference',
    'Natural language inference decides whether a premise entails, contradicts, or is neutral toward a hypothesis. It is a core test of sentence-level reasoning, benchmarked by accuracy on SNLI, MultiNLI, and adversarial ANLI, and is widely reused for zero-shot classification and fact verification. It relates to [Text Classification](/tasks/text-classification) and [Reasoning](/tasks/reasoning).',
    'natural language inference, textual entailment, recognizing textual entailment, entailment classification, NLI',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    '[Adversarial NLI: A New Benchmark for Natural Language Understanding](/paper/1910.14599)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Sentiment Analysis',
    'sentiment-analysis',
    'Sentiment analysis determines whether text expresses positive, negative, or neutral opinion, at document, sentence, or fine-grained level. Accuracy on SST-2, SST-5, IMDb, and Yelp reviews is the classic benchmark. It is a subtask of [Text Classification](/tasks/text-classification), with [Aspect-Based Sentiment Analysis](/tasks/aspect-based-sentiment-analysis) and [Multimodal Sentiment Analysis](/tasks/multimodal-sentiment-analysis) as finer-grained and multimodal variants.',
    'sentiment analysis, sentiment classification, opinion mining, polarity classification, sentiment detection',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'text-classification'),
    (SELECT id FROM tasks WHERE slug = 'text-classification'),
    '[A Survey on Aspect-Based Sentiment Analysis: Tasks, Methods, and Challenges](https://arxiv.org/abs/2203.01054)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Intent Detection',
    'intent-detection',
    'Intent detection classifies the goal behind a user utterance, such as booking a flight or checking a balance, usually together with slot filling in task-oriented dialogue systems. Accuracy on ATIS, SNIPS, CLINC150, and BANKING77, including out-of-scope detection, is the standard evaluation. It is a subtask of [Text Classification](/tasks/text-classification).',
    'intent detection, intent classification, user intent detection, slot filling',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'text-classification'),
    (SELECT id FROM tasks WHERE slug = 'text-classification'),
    '[An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction](/paper/1909.02027)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Dialect Identification',
    'dialect-identification',
    'Dialect identification determines which regional or national variety of a language a text or utterance is written in, for example Egyptian versus Gulf Arabic. Shared tasks such as NADI and MADAR report macro-F1. It is a fine-grained subtask of [Text Classification](/tasks/text-classification), related to [Spoken Language Identification](/tasks/spoken-language-identification).',
    'dialect identification, Arabic dialect identification, dialect classification, dialect detection, language variety identification',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'text-classification'),
    (SELECT id FROM tasks WHERE slug = 'text-classification'),
    '[NADI 2020: The First Nuanced Arabic Dialect Identification Shared Task](https://arxiv.org/abs/2010.11334)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Coreference Resolution',
    'coreference-resolution',
    'Coreference resolution groups mentions in text that refer to the same entity or event, within a document or across documents. Systems are evaluated by the average CoNLL F1 of MUC, B3, and CEAF on OntoNotes (CoNLL-2012), and on ECB+ for cross-document event coreference. It supports information extraction tasks such as [Entity Resolution](/tasks/entity-resolution).',
    'coreference resolution, coreference, cross-document coreference, entity coreference, event coreference, anaphora resolution',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    '[CorefQA: Coreference Resolution as Query-based Span Prediction](https://arxiv.org/abs/1911.01746)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Entity Resolution',
    'entity-resolution',
    'Entity resolution decides whether records from one or more databases describe the same real-world entity, such as matching product listings or deduplicating customer records. Deep and LLM-based matchers report F1 on the Magellan and WDC Products benchmarks. It is the structured-data counterpart of [Coreference Resolution](/tasks/coreference-resolution) and relates to [Tabular Learning](/tasks/tabular-learning).',
    'entity resolution, entity matching, record linkage, duplicate record detection, record deduplication',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    '[Deep Entity Matching with Pre-Trained Language Models](/paper/2004.00584)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'End-to-End Autonomous Driving',
    'end-to-end-autonomous-driving',
    'End-to-end autonomous driving maps raw sensor input directly to plans or control commands with one jointly trained model instead of separate perception, prediction, and planning modules. Methods are evaluated open-loop on nuScenes and NAVSIM and closed-loop by driving score in CARLA and Bench2Drive. It is a subtask of [Autonomous Driving](/tasks/autonomous-driving).',
    'end-to-end autonomous driving, end-to-end driving, sensor-to-control driving, closed-loop driving',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'autonomous-driving'),
    (SELECT id FROM tasks WHERE slug = 'autonomous-driving'),
    '[End-to-end Autonomous Driving: Challenges and Frontiers](/paper/2306.16927)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Continual Test-Time Adaptation',
    'continual-test-time-adaptation',
    'Continual test-time adaptation updates a deployed model online as its test distribution keeps shifting, without labels or source data, while avoiding error accumulation and forgetting. Methods report error rates over sequences of corruptions on CIFAR10-C, CIFAR100-C, and ImageNet-C. It is a subtask of [Test-Time Adaptation](/tasks/test-time-adaptation) related to [Continual Learning](/tasks/continual-learning).',
    'continual test-time adaptation, continual test time adaptation, lifelong test-time adaptation, CTTA',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'test-time-adaptation'),
    (SELECT id FROM tasks WHERE slug = 'test-time-adaptation'),
    '[Continual Test-Time Domain Adaptation](/paper/2203.13591)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Machine Unlearning',
    'machine-unlearning',
    'Machine unlearning removes the influence of specific training data or knowledge from a trained model without retraining from scratch, for privacy, copyright, or safety. Evaluations check forgetting on the forget set, retained utility, and resistance to membership inference, on benchmarks such as TOFU, WMDP, and MUSE for language models. It relates to [Continual Learning](/tasks/continual-learning).',
    'machine unlearning, LLM unlearning, unlearning, forget set',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    '[TOFU: A Task of Fictitious Unlearning for LLMs](/paper/2401.06121)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Meta-Learning',
    'meta-learning',
    'Meta-learning trains models across many related tasks so they can adapt to a new task from only a few examples, through learned initializations, metric spaces, or learned optimizers. Few-shot classification accuracy on miniImageNet, tieredImageNet, and Meta-Dataset is the standard evaluation. It underlies few-shot variants such as [Few-Shot Object Detection](/tasks/few-shot-object-detection) and [Few-Shot Segmentation](/tasks/few-shot-segmentation).',
    'meta-learning, meta learning, learning to learn, few-shot classification',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    '[Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks](/paper/1703.03400)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id, image_credit)
VALUES (
    'Pitch Estimation',
    'pitch-estimation',
    'Pitch estimation recovers the fundamental frequency (F0) of speech, singing, or instrument audio over time, a building block for music analysis, voice conversion, and speech synthesis. Raw pitch accuracy on MIR-1K, MDB-stem-synth, and PTDB is the usual metric. It relates to [Automatic Music Transcription](/tasks/automatic-music-transcription).',
    'pitch estimation, pitch tracking, fundamental frequency estimation, F0 estimation, melody extraction',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    '[SPICE: Self-supervised Pitch Estimation](https://arxiv.org/abs/1910.11664)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (slug, name, full_name, description, keywords, area_id, introduced_year, source_paper_id, source_url, source_title)
VALUES (
    'kalman-filter',
    'Kalman Filter',
    'Kalman Filter',
    'The Kalman filter recursively estimates the hidden state of a linear dynamical system from noisy measurements. Each step predicts the state and its covariance from a motion model, then corrects the prediction with the new observation, weighting the two by their uncertainties through the Kalman gain. Introduced by R. E. Kalman in 1960, it is optimal for linear-Gaussian systems; the extended and unscented variants handle nonlinear dynamics. In machine learning it is the motion model in multi-object trackers such as SORT and ByteTrack, a component of visual-inertial odometry and SLAM, and a recurring analogy for state-space sequence models.',
    'Kalman filter, Kalman Filter, Kalman smoother, Kalman Smoother',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1960,
    NULL,
    'https://doi.org/10.1115/1.3662552',
    'A New Approach to Linear Filtering and Prediction Problems'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (slug, name, full_name, description, keywords, area_id, introduced_year, source_paper_id, source_url, source_title)
VALUES (
    'hopfield-network',
    'Hopfield Network',
    'Hopfield Network',
    'A Hopfield network is a recurrent network of symmetrically connected units that works as a content-addressable associative memory: stored patterns are minima of an energy function, and the network retrieves a pattern by descending that energy from a partial or noisy cue. J. J. Hopfield introduced it in 1982. Modern Hopfield networks with continuous states and exponential energies store exponentially many patterns, and [Hopfield Networks is All You Need](/paper/2008.02217) showed that their update rule is equivalent to [Transformer](/methods/transformer) attention.',
    'Hopfield network, Hopfield Network, modern Hopfield, Modern Hopfield, dense associative memory, Dense Associative Memory, Hopfield layer, Hopfield Layer',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1982,
    NULL,
    'https://doi.org/10.1073/pnas.79.8.2554',
    'Neural networks and physical systems with emergent collective computational abilities'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (slug, name, full_name, description, keywords, area_id, introduced_year, source_paper_id, source_url, source_title)
VALUES (
    'hidden-markov-model',
    'Hidden Markov Model',
    'Hidden Markov Model (HMM)',
    'A hidden Markov model (HMM) describes a sequence of observations generated by an unobserved Markov chain of discrete states, with transition probabilities between states and an emission distribution per state. The forward-backward algorithm computes sequence likelihoods, Viterbi decoding finds the most likely state path, and Baum-Welch (expectation-maximization) learns the parameters. Formalized by Baum and Petrie in 1966, HMMs were the backbone of speech recognition and part-of-speech tagging for decades and remain common in bioinformatics, activity recognition, and as interpretable baselines for sequence models.',
    'hidden Markov model, Hidden Markov Model, Hidden Markov model, HMMs, HMM-based',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1966,
    NULL,
    'https://doi.org/10.1214/aoms/1177699147',
    'Statistical Inference for Probabilistic Functions of Finite State Markov Chains'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (slug, name, full_name, description, keywords, area_id, introduced_year, source_paper_id, source_url, source_title)
VALUES (
    'entmax',
    'Entmax',
    'α-entmax',
    'α-entmax is a family of sparse alternatives to [Softmax](/methods/softmax) that map scores to probability distributions able to assign exactly zero probability to low-scoring entries. The parameter α interpolates between softmax (α = 1) and [sparsemax](/paper/1602.02068) (α = 2); 1.5-entmax is the common default, computed exactly by sorting or bisection. Introduced for sparse attention and sparse output layers in sequence-to-sequence models, it yields interpretable attention and lets a model output a short list of plausible tokens, and is used in sparse attention Transformers and long-context generalization work.',
    'entmax, α-entmax, alpha-entmax, 1.5-entmax, entmax15',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2019,
    (SELECT id FROM papers WHERE arxiv_id = '1905.05702' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Sparse Sequence-to-Sequence Models'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (slug, name, full_name, description, keywords, area_id, introduced_year, source_paper_id, source_url, source_title)
VALUES (
    'sub-pixel-convolution',
    'Sub-Pixel Convolution',
    'Efficient Sub-Pixel Convolution (ESPCN)',
    'Sub-pixel convolution upsamples feature maps by a factor r by predicting r² channels per output channel at low resolution and then rearranging them into an r-times larger spatial grid (the periodic shuffle, exposed as PixelShuffle or depth-to-space). Introduced in ESPCN for real-time single-image and video super-resolution, it does all convolution in low-resolution space, avoiding the cost and checkerboard artifacts of deconvolution. It is the standard upsampling layer in [Image Super-Resolution](/tasks/image-super-resolution) networks and widely used in segmentation and generative decoders.',
    'sub-pixel convolution, sub-pixel convolutional, subpixel convolution, pixel shuffle, PixelShuffle, ESPCN, depth-to-space',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1609.05158' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Real-Time Single Image and Video Super-Resolution Using an Efficient Sub-Pixel Convolutional Neural Network'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (slug, name, full_name, description, keywords, area_id, introduced_year, source_paper_id, source_url, source_title)
VALUES (
    'additive-attention',
    'Additive Attention',
    'Additive Attention (Bahdanau Attention)',
    'Additive attention, introduced by Bahdanau, Cho and Bengio for neural machine translation, lets a decoder attend over all encoder states instead of compressing the source sentence into one fixed vector. It scores each encoder state against the current decoder state with a small feed-forward network, a tanh of their projected sum, normalizes the scores with [Softmax](/methods/softmax), and feeds the weighted sum to the decoder as context. It removed the fixed-length bottleneck of RNN encoder-decoders and learned soft alignments; the later dot-product attention of the [Transformer](/methods/transformer) replaced it in most models.',
    'additive attention, Bahdanau attention, Bahdanau Attention, Bahdanau-style attention',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2014,
    (SELECT id FROM papers WHERE arxiv_id = '1409.0473' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Neural Machine Translation by Jointly Learning to Align and Translate'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('entmax', 'sub-pixel-convolution', 'additive-attention')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- SwiftFormer and Fastformer name their efficient linear attention "additive
-- attention"; it is not Bahdanau attention.
INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT p.id, m.id, 'efficient linear additive attention, not Bahdanau attention'
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'additive-attention'
  AND p.is_latest_version
  AND (p.title LIKE 'SwiftFormer: Efficient Additive Attention%'
       OR p.title LIKE 'Fastformer: Additive Attention%')
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- Method image credits (figures imported with import_entity_image.py).
UPDATE methods SET image_credit = '[Sparse Sequence-to-Sequence Models](/paper/1905.05702)' WHERE slug = 'entmax';
UPDATE methods SET image_credit = '[Real-Time Single Image and Video Super-Resolution Using an Efficient Sub-Pixel Convolutional Neural Network](/paper/1609.05158)' WHERE slug = 'sub-pixel-convolution';
UPDATE methods SET image_credit = '[Neural Machine Translation by Jointly Learning to Align and Translate](/paper/1409.0473)' WHERE slug = 'additive-attention';
UPDATE methods SET image_credit = '[Basic concept of Kalman filtering](https://commons.wikimedia.org/wiki/File:Basic_concept_of_Kalman_filtering.svg), Petteri Aimonen, CC0' WHERE slug = 'kalman-filter';
UPDATE methods SET image_credit = '[Hopfield-network](https://commons.wikimedia.org/wiki/File:Hopfield-network.svg), MartinThoma, CC0' WHERE slug = 'hopfield-network';
UPDATE methods SET image_credit = '[HiddenMarkovModel](https://commons.wikimedia.org/wiki/File:HiddenMarkovModel.svg), Tdunning, CC BY 3.0' WHERE slug = 'hidden-markov-model';
-- Broad sources: keep only citers that name the method in title/abstract.
WITH targets(slug, pattern) AS (
    VALUES
        ('additive-attention', '(additive attention|bahdanau)'),
        ('sub-pixel-convolution', '(pixel.?shuffle|sub-?pixel conv|depth-to-space|espcn)')
),
reference_only AS (
    SELECT pm.paper_id, pm.method_id
    FROM paper_methods pm
    JOIN methods m ON m.id = pm.method_id
    JOIN targets t ON t.slug = m.slug
    JOIN papers p ON p.id = pm.paper_id
    WHERE lower(coalesce(p.title, '') || ' ' || coalesce(p.abstract, '')) !~ t.pattern
      AND EXISTS (
          SELECT 1 FROM paper_method_evidence e
          WHERE e.paper_id = pm.paper_id AND e.method_id = pm.method_id
            AND e.evidence_type = 'reference'
      )
      AND NOT EXISTS (
          SELECT 1 FROM paper_method_evidence e
          WHERE e.paper_id = pm.paper_id AND e.method_id = pm.method_id
            AND e.evidence_type <> 'reference'
      )
),
excluded AS (
    INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
    SELECT paper_id, method_id, 'cites the source paper without naming the method'
    FROM reference_only
    ON CONFLICT (paper_id, method_id) DO NOTHING
    RETURNING paper_id, method_id
)
DELETE FROM paper_methods pm
USING reference_only r
WHERE pm.paper_id = r.paper_id AND pm.method_id = r.method_id;
