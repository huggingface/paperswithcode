-- Method gap fill (2026-11-10 audit), group E: learning paradigms and
-- probabilistic methods (area General). Twelve widely used techniques that the
-- catalog was missing.
--
-- Only Gumbel-Softmax has an introducing paper (arXiv 1611.01144; the Concrete
-- distribution, 1611.00712, appeared at the same time and is credited in the
-- description and as an alias). The other eleven are broad techniques with
-- contested or pre-arXiv origins (Caruana 1997, Bengio et al. 2009, Hyvarinen
-- 2005, Metropolis et al. 1953, Welling and Teh 2011, Dwork et al. 2006, ...),
-- so they keep source_paper_id NULL with a canonical reference in source_url
-- and no "Introduced" banner. Adversarial training credits Szegedy et al.,
-- Goodfellow et al. (FGSM) and Madry et al. (PGD) in its description rather
-- than naming one origin; differential privacy is the broad concept, with
-- DP-SGD (1607.00133) described as its standard training method.
--
-- Keywords stay on exact long forms. Bare ambiguous abbreviations are left out:
-- "AT", "DP" (dynamic programming), "OT", "VI", "MTL" and "AL". Adversarial
-- training keywords name only robustness variants (PGD/FGSM/virtual/fast/latent)
-- because bare "adversarial training" also means GAN and domain-adversarial
-- training; its abstract mentions go to the Jev judge.
--
-- Paper links: bounded title/abstract regex candidates on the exact names
-- (plus the local Semantic Scholar citers of 1611.01144 for Gumbel-Softmax),
-- reviewed 2026-11-10. For these common terms the exact-name matches are the
-- positive set once other senses (GAN/domain-adversarial training, propensity
-- score matching, Sinkhorn-Knopp normalisation, pedagogical active learning,
-- Langevin in chemistry) and contrastive mentions ("without adversarial
-- training", "unlike active learning") are removed; positives get 'manual'
-- evidence. Reviewed negatives (other senses,
-- contrastive or passing mentions, Gumbel-max-only work, and Gumbel-Softmax
-- citers whose title and abstract do not name it) become durable exclusions so
-- the keyword and reference backfills do not re-link them. Hero images were
-- imported separately with import_entity_image.py; credits are recorded below.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'transfer-learning',
    'Transfer Learning',
    'Transfer Learning',
    'Transfer learning reuses knowledge learned on a source task or domain to improve learning on a different target task, typically by starting from a model [pre-trained](/methods/pre-training) on a large dataset and adapting it with little target data. The adaptation can freeze the transferred network and train a new head (feature extraction or linear probing), [fine-tune](/methods/fine-tuning) all or some weights, or update a small set of added parameters as in [PEFT](/methods/peft). The idea long predates deep learning (Pan and Yang''s 2010 survey reviews inductive, transductive and unsupervised settings); [Yosinski et al.](/paper/1411.1792) showed that early convolutional layers learn general features while later layers become task-specific, and ImageNet pre-training became the default starting point in computer vision. In NLP, [ULMFiT](/paper/1801.06146), [BERT](/paper/1810.04805) and [T5](/paper/1910.10683) made pre-train-then-fine-tune the standard recipe, and today''s foundation models extend it. Closely related settings include [domain adaptation](/methods/domain-adaptation-da), where the task stays the same but the input distribution shifts, and [multi-task learning](/methods/multi-task-learning), where tasks are learned jointly rather than in sequence.',
    'transfer learning, transfer-learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1109/TKDE.2009.191',
    'A Survey on Transfer Learning',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'multi-task-learning',
    'Multi-Task Learning',
    'Multi-Task Learning (MTL)',
    'Multi-task learning (MTL) trains one model on several related tasks at once so that what is learned for one task helps the others, acting as an inductive bias that improves generalization and data efficiency. Caruana (1997) framed it as learning tasks in parallel with a shared representation. Deep MTL models usually share parameters in one of two ways: hard parameter sharing, with a common encoder and task-specific heads, or soft sharing, where each task has its own network and the networks are regularized to stay close ([Ruder''s overview](/paper/1706.05098)). Because tasks can compete, much work balances their losses or gradients, for example by weighting losses with homoscedastic uncertainty ([Kendall et al.](/paper/1705.07115)) or normalizing gradient magnitudes ([GradNorm](/paper/1711.02257)), and studies negative transfer between unrelated tasks. MTL is common in dense scene understanding, autonomous driving, recommendation, speech and NLP, where multi-task instruction tuning of large language models is a large-scale form of it. It differs from [transfer learning](/methods/transfer-learning), which learns tasks in sequence, and from [Mixture-of-Experts](/methods/mixture-of-experts) routing, which some MTL architectures use to share capacity across tasks.',
    'multi-task learning, multitask learning, multi task learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1023/A:1007379606734',
    'Multitask Learning',
    NULL,
    NULL,
    'always',
    ARRAY['Multitask Learning']
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'curriculum-learning',
    'Curriculum Learning',
    'Curriculum Learning',
    'Curriculum learning trains a model on examples ordered from easy to hard instead of in random order, inspired by the way people and animals learn more effectively when concepts are introduced gradually. Elman (1993) found that recurrent networks learned grammatical structure only when training began with simple inputs or limited memory, and Bengio et al. (2009) named and formalized the idea, showing faster convergence and better generalization on shape recognition and language modeling and interpreting a curriculum as a continuation method for non-convex optimization. A curriculum needs a difficulty measure and a pacing schedule; these can be hand-designed (sentence length, label noise, image resolution) or learned, as in self-paced learning, teacher-student curricula, and automatic curricula in [reinforcement learning](/tasks/reinforcement-learning) that adapt task difficulty to the agent. Curricula are now widely used in large language model pre-training and reasoning RL, where data is scheduled by quality or difficulty, and in robotics, machine translation, and [domain adaptation](/methods/domain-adaptation-da). Anti-curricula (hard examples first) and the effect of curricula under large data budgets remain active questions.',
    'curriculum learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2009,
    NULL,
    'https://doi.org/10.1145/1553374.1553380',
    'Curriculum Learning',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'active-learning',
    'Active Learning',
    'Active Learning',
    'Active learning reduces labeling cost by letting the model choose which unlabeled examples an annotator (the oracle) should label next, instead of labeling data at random. In the common pool-based setting, a model is trained on a small labeled set, an acquisition function scores the unlabeled pool, the top examples are labeled, and the loop repeats. Classic strategies, surveyed by Settles (2009), include uncertainty sampling (least confidence, margin, entropy), query-by-committee, expected model change and expected error reduction. Deep active learning adapts these to neural networks with Bayesian uncertainty from [dropout](/methods/dropout) ([Gal et al.](/paper/1703.02910)), diversity-based batch selection such as the core-set approach ([Sener and Savarese](/paper/1708.00489)), and hybrids that balance uncertainty and diversity. It is used in medical imaging, autonomous driving, NLP annotation and scientific discovery, and is often combined with [semi-supervised learning](/methods/semi-supervised-learning) or with large models acting as annotators. Active learning differs from [pseudo-labeling](/methods/pseudo-labeling), which labels data automatically, and is related to Bayesian optimization and experimental design.',
    'active learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://burrsettles.com/pub/settles.activelearning.pdf',
    'Active Learning Literature Survey',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'adversarial-training',
    'Adversarial Training',
    'Adversarial Training (AT)',
    'Adversarial training improves a model''s robustness to adversarial examples, small input perturbations crafted to cause errors, by generating such examples during training and fitting the model on them. [Szegedy et al.](/paper/1312.6199) discovered adversarial examples and noted that training on them can regularize a network; [Goodfellow et al.](/paper/1412.6572) introduced the fast gradient sign method (FGSM) and an adversarial training objective that mixes clean and FGSM losses; and [Madry et al.](/paper/1706.06083) cast it as a min-max robust optimization problem, training on examples found by multi-step projected gradient descent (PGD), which remains the standard baseline. Later work trades accuracy against robustness explicitly (TRADES), cuts the cost of the inner attack (free and fast adversarial training), studies robust overfitting, and adds generated data from [diffusion models](/methods/diffusion). Virtual adversarial training ([Miyato et al.](/paper/1704.03976)) applies the idea to [semi-supervised learning](/methods/semi-supervised-learning) without labels, and adversarial training of language models now also targets jailbreaks, often in latent space. This sense is distinct from the adversarial generator-discriminator training of a [GAN](/methods/gan) and from domain-adversarial training in [domain adaptation](/methods/domain-adaptation-da).',
    'PGD adversarial training, PGD-based adversarial training, FGSM adversarial training, virtual adversarial training, fast adversarial training, latent adversarial training',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    '/paper/1706.06083',
    'Towards Deep Learning Models Resistant to Adversarial Attacks',
    NULL,
    NULL,
    'judge',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'differential-privacy',
    'Differential Privacy',
    'Differential Privacy',
    'Differential privacy (DP) is a mathematical guarantee that the output of an algorithm changes little whether or not any single individual''s record is in its input, so the output reveals almost nothing about that individual. Formally, a randomized mechanism is (ε, δ)-differentially private if, for any two datasets differing in one record, the probability of any output changes by at most a factor e^ε plus δ. Dwork, McSherry, Nissim and Smith (2006) introduced the definition with the Laplace mechanism, which adds noise calibrated to a query''s sensitivity. In machine learning the standard method is DP-SGD ([Abadi et al.](/paper/1607.00133)), which clips each example''s gradient, adds Gaussian noise, and tracks the cumulative privacy loss with the moments accountant; Rényi DP and other accountants tighten the bounds. DP is used to train models on sensitive data, in [federated learning](/methods/federated-learning) with user-level guarantees, for private synthetic data and private fine-tuning of language models, and in deployed systems such as the US Census. Research studies the privacy-utility trade-off, private hyperparameter tuning, and auditing with membership inference attacks.',
    'differential privacy, differentially private, DP-SGD, DPSGD',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1007/11681878_14',
    'Calibrating Noise to Sensitivity in Private Data Analysis',
    'https://github.com/pytorch/opacus/blob/main/opacus/optimizers/optimizer.py',
    NULL,
    'always',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'score-matching',
    'Score Matching',
    'Score Matching',
    'Score matching fits a probabilistic model by matching the gradient of its log-density with respect to the data, the score, to that of the data distribution, which avoids computing the intractable normalizing constant of unnormalized and energy-based models. Hyvärinen (2005) showed that the objective can be rewritten using only the model''s score and its derivatives. Denoising score matching (Vincent, 2011) instead regresses the score of noise-perturbed data, and sliced score matching uses random projections to scale to high dimensions. [Song and Ermon](/paper/1907.05600) turned the idea into score-based generative modeling: a noise-conditional network learns scores at many noise levels and samples are drawn with annealed [Langevin dynamics](/methods/langevin-dynamics). [Song et al.](/paper/2011.13456) unified this with denoising [diffusion](/methods/diffusion) models ([DDPM](/paper/2006.11239)) through stochastic differential equations, whose reverse-time process is driven by the learned score. Score matching thus underlies modern diffusion training, and is also used for energy-based models, density estimation, and [score distillation sampling](/methods/score-distillation-sampling).',
    'score matching, score-matching, denoising score matching, sliced score matching, score-based generative model, score-based generative modeling, score-based generative modelling, score-based diffusion model',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2005,
    NULL,
    'https://jmlr.org/papers/v6/hyvarinen05a.html',
    'Estimation of Non-Normalized Statistical Models by Score Matching',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'optimal-transport',
    'Optimal Transport',
    'Optimal Transport',
    'Optimal transport (OT) finds the cheapest way to move one probability distribution onto another, given a cost for moving a unit of mass between two points; the minimal cost defines the Wasserstein distance, which compares distributions using the geometry of the space even when their supports do not overlap. Monge posed the problem in 1781 and Kantorovich relaxed it to a linear program over transport plans. For machine learning, [Cuturi](/paper/1306.0895) added entropic regularization so that the Sinkhorn algorithm computes approximate OT quickly on GPUs, and [Peyré and Cuturi](/paper/1803.00567) survey the computational toolbox. OT is used as a training loss ([Wasserstein GAN](/paper/1701.07875)), for [domain adaptation](/methods/domain-adaptation-da), point-set and graph matching, cross-modal alignment, and clustering, and to couple noise and data samples in [flow matching](/methods/flow-matching) and rectified flows ([minibatch OT couplings](/paper/2302.00482)). Related tools include Wasserstein barycenters, Gromov-Wasserstein distances for comparing spaces, unbalanced OT, and Schrödinger bridges, the entropic dynamic form of OT.',
    'optimal transport, optimal transportation, entropic optimal transport, Sinkhorn distance, Sinkhorn divergence',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    '/paper/1803.00567',
    'Computational Optimal Transport',
    'https://github.com/PythonOT/POT',
    NULL,
    'always',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'variational-inference',
    'Variational Inference',
    'Variational Inference',
    'Variational inference (VI) approximates an intractable posterior distribution by choosing, from a tractable family of distributions, the member closest to it in KL divergence, which turns Bayesian inference into optimization. Since the log evidence cannot be computed directly, VI maximizes the evidence lower bound (ELBO), which equals the log evidence minus the KL divergence from the approximation to the true posterior. Classic mean-field VI factorizes the approximation and uses coordinate ascent ([Blei et al.''s review](/paper/1601.00670)); stochastic variational inference scales it to large datasets with minibatches; and black-box VI with the reparameterization trick allows arbitrary differentiable models. Amortized VI trains an inference network to output the approximate posterior for each input, the basis of the [variational autoencoder](/methods/vae) ([Kingma and Welling](/paper/1312.6114)), and [normalizing flows](/methods/normalizing-flows) give richer approximating families ([Rezende and Mohamed](/paper/1505.05770)). VI is used in Bayesian neural networks, topic models, Gaussian processes, latent-variable and [diffusion](/methods/diffusion) models, and is typically faster but more biased than [Markov Chain Monte Carlo](/methods/markov-chain-monte-carlo) sampling.',
    'variational inference, variational bayes, stochastic variational inference, amortized variational inference',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    '/paper/1601.00670',
    'Variational Inference: A Review for Statisticians',
    NULL,
    NULL,
    'always',
    ARRAY['Variational Bayes']
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'markov-chain-monte-carlo',
    'Markov Chain Monte Carlo',
    'Markov Chain Monte Carlo (MCMC)',
    'Markov Chain Monte Carlo (MCMC) draws samples from a probability distribution known only up to a normalizing constant by simulating a Markov chain whose stationary distribution is the target; averages over the chain''s states then estimate expectations such as posterior means. The Metropolis algorithm (Metropolis et al., 1953) proposes a move and accepts it with a probability that preserves the target distribution, and Hastings (1970) generalized it to asymmetric proposals; Gibbs sampling updates one variable at a time from its conditional distribution. Hamiltonian Monte Carlo uses gradients and simulated Hamiltonian dynamics to make long, low-correlation moves, and the No-U-Turn Sampler tunes it automatically in tools such as Stan and PyMC. Gradient-based variants such as [Langevin dynamics](/methods/langevin-dynamics) and its stochastic-gradient forms scale MCMC to large datasets and neural networks. MCMC is the standard tool for Bayesian inference, and in machine learning it is used to train and sample energy-based models, as a corrector in [diffusion](/methods/diffusion) sampling, and for uncertainty estimation; it is asymptotically exact but usually slower than [variational inference](/methods/variational-inference). [Sequential Monte Carlo](/methods/particle-filter) is a related family.',
    'markov chain monte carlo, MCMC, hamiltonian monte carlo, metropolis-hastings',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1953,
    NULL,
    'https://doi.org/10.1063/1.1699114',
    'Equation of State Calculations by Fast Computing Machines',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'langevin-dynamics',
    'Langevin Dynamics',
    'Langevin Dynamics',
    'Langevin dynamics samples from a distribution p(x) by following the gradient of the log-density, the score, plus injected Gaussian noise: each step moves x by a small step along ∇log p(x) and adds noise scaled to the step size, so that the iterates converge to p as the step size shrinks. The update discretizes the Langevin stochastic differential equation from statistical physics; without a correction it is the unadjusted Langevin algorithm, and adding a Metropolis-Hastings accept step gives the Metropolis-adjusted Langevin algorithm (MALA), a form of [MCMC](/methods/markov-chain-monte-carlo). Welling and Teh (2011) introduced stochastic gradient Langevin dynamics (SGLD), which uses minibatch gradients so that [SGD](/methods/sgd)-style training turns into posterior sampling for Bayesian learning on large datasets. [Song and Ermon](/paper/1907.05600) used annealed Langevin dynamics with learned scores to generate images, linking it to [score matching](/methods/score-matching) and [diffusion](/methods/diffusion) models, where Langevin steps serve as correctors. It is also used to sample energy-based models, for posterior sampling in inverse problems, and in theoretical analyses of noisy gradient descent and its generalization.',
    'langevin dynamics, stochastic gradient langevin dynamics, langevin monte carlo, langevin sampling, unadjusted langevin algorithm, metropolis-adjusted langevin, SGLD',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://www.stats.ox.ac.uk/~teh/research/compstats/WelTeh2011a.pdf',
    'Bayesian Learning via Stochastic Gradient Langevin Dynamics',
    NULL,
    NULL,
    'always',
    ARRAY['Langevin Monte Carlo']
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'gumbel-softmax',
    'Gumbel-Softmax',
    'Gumbel-Softmax',
    'Gumbel-Softmax is a continuous, differentiable relaxation of sampling from a categorical distribution, which lets gradients flow through discrete choices in neural networks. It builds on the Gumbel-max trick, which draws a category by adding independent Gumbel noise to the logits and taking the argmax; Gumbel-Softmax replaces the argmax with a softmax at temperature τ, giving samples on the probability simplex that approach one-hot vectors as τ goes to zero, so the [reparameterization](/methods/vae) trick applies and the gradient has lower variance than score-function estimators such as [REINFORCE](/methods/reinforce). The straight-through variant uses a hard one-hot sample in the forward pass and the relaxed gradient in the backward pass. [Jang et al.](/paper/1611.01144) introduced it alongside the simultaneous, equivalent [Concrete distribution](/paper/1611.00712) of Maddison et al. It is widely used for discrete latent variables and codebook quantization (for example in [vq-wav2vec](/paper/1910.05453)), differentiable [neural architecture search](/methods/neural-architecture-search), token and channel selection and pruning, [Mixture-of-Experts](/methods/mixture-of-experts) gating, and backpropagating through sampled text tokens.',
    'gumbel-softmax, gumbel softmax, concrete distribution',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1611.01144'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Categorical Reparameterization with Gumbel-Softmax',
    'https://github.com/pytorch/pytorch/blob/main/torch/nn/functional.py',
    NULL,
    'always',
    ARRAY['Concrete Distribution']
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Introduced banner for Gumbel-Softmax.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'gumbel-softmax' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gumbel-softmax' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- transfer-learning: 1066 links, 3 exclusions.
CREATE TEMP TABLE transfer_learning_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'transfer-learning'
  AND p.id IN (
        18, -- 1207.4708 The Arcade Learning Environment: An Evaluation Platform for General Ag
        149, -- 1501.04560 Transductive Multi-view Zero-Shot Learning
        190, -- 1505.07427 PoseNet: A Convolutional Network for Real-Time 6-DOF Camera Relocaliza
        197, -- 1506.02075 Large-scale Simple Question Answering with Memory Networks
        505, -- 1611.04558 Google's Multilingual Neural Machine Translation System: Enabling Zero
        525, -- 1611.09842 Split-Brain Autoencoders: Unsupervised Learning by Cross-Channel Predi
        702, -- 1705.02364 Supervised Learning of Universal Sentence Representations from Natural
        714, -- 1705.06273 Transfer Learning for Named-Entity Recognition with Neural Networks
        857, -- 1708.06734 Representation Learning by Learning to Count
        881, -- 1709.06030 N2N Learning: Network to Network Compression via Policy Gradient Reinf
        984, -- 1711.09082 Cross-Domain Self-supervised Multi-task Feature Learning using Synthet
        1057, -- 1801.06146 Universal Language Model Fine-tuning for Text Classification
        1116, -- 1802.07569 Continual Lifelong Learning with Neural Networks: A Review
        1161, -- 1803.06397 Deep learning for affective computing: text-based emotion recognition
        1191, -- 1803.11175 Universal Sentence Encoder
        1229, -- 1804.06658 NTUA-SLP at SemEval-2018 Task 1: Predicting Affective Content in Tweet
        1233, -- 1804.07461 GLUE: A Multi-Task Benchmark and Analysis Platform for Natural Languag
        1238, -- 1804.07931 Entire Space Multi-Task Model: An Effective Approach for Estimating Po
        1255, -- 1805.00932 Exploring the Limits of Weakly Supervised Pretraining
        1333, -- 1806.04558 Transfer Learning from Speaker Verification to Multispeaker Text-To-Sp
        1373, -- 1806.11532 TextWorld: A Learning Environment for Text-based Games
        1411, -- 1807.11293 Improving Spatiotemporal Self-Supervision by Deep Reinforcement Learni
        1441, -- 1808.06752 Lessons from Natural Language Inference in the Clinical Domain
        1454, -- 1808.08762 Sentence Embeddings in NLI with Iterative Refinement Encoders
        1468, -- 1808.10583 AISHELL-2: Transforming Mandarin ASR Research Into Industrial Scale
        1475, -- 1809.00717 NTUA-SLP at IEST 2018: Ensemble of Neural Transfer Methods for Implici
        1561, -- 1810.09774 Testing the Generalization Power of Neural Network Models Across NLI B
        1573, -- 1810.12118 Finding Answers from the Word of God: Domain Adaptation for Neural Net
        1677, -- 1812.01187 Bag of Tricks for Image Classification with Convolutional Neural Netwo
        1738, -- 1901.01695 Vector representations of text data in deep learning
        1769, -- 1901.08149 TransferTransfo: A Transfer Learning Approach for Neural Network Based
        1803, -- 1902.00751 Parameter-Efficient Transfer Learning for NLP
        1855, -- 1902.10526 DiscoFuse: A Large-Scale Dataset for Discourse-Based Sentence Fusion
        1856, -- 1902.10547 An Embarrassingly Simple Approach for Transfer Learning from Pretraine
        1898, -- 1903.05769 Improving Prostate Cancer Detection with Breast Histopathology Images
        1938, -- 1904.00625 Med3D: Transfer Learning for 3D Medical Image Analysis
        2028, -- 1904.09728 SocialIQA: Commonsense Reasoning about Social Interactions
        2050, -- 1904.12848 Unsupervised Data Augmentation for Consistency Training
        2055, -- 1905.00537 SuperGLUE: A Stickier Benchmark for General-Purpose Language Understan
        2096, -- 1905.05704 A logical-based corpus for cross-lingual evaluation
        2104, -- 1905.07213 Adaptation of Deep Bidirectional Multilingual Transformers for Russian
        2126, -- 1905.09272 Data-Efficient Image Recognition with Contrastive Predictive Coding
        2132, -- 1905.10044 BoolQ: Exploring the Surprising Difficulty of Natural Yes/No Questions
        2151, -- 1905.11946 EfficientNet: Rethinking Model Scaling for Convolutional Neural Networ
        2162, -- 1905.12897 A Compare-Aggregate Model with Latent Clustering for Answer Selection
        2187, -- 1906.00695 Continual learning with hypernetworks
        2255, -- 1906.05474 Transfer Learning in Biomedical Natural Language Processing: An Evalua
        2257, -- 1906.05750 The iMaterialist Fashion Attribute Dataset
        2285, -- 1906.08230 Evaluating Protein Transfer Learning with TAPE
        2326, -- 1907.04307 Multilingual Universal Sentence Encoder for Semantic Retrieval
        2340, -- 1907.05774 Hello, It's GPT-2 -- How Can I Help You? Towards the Use of Pretrained
        2367, -- 1907.10641 WinoGrande: An Adversarial Winograd Schema Challenge at Scale
        2373, -- 1907.12237 KNEEL: Knee Anatomical Landmark Localization Using Hourglass Networks
        2439, -- 1908.07836 PubLayNet: largest dataset ever for document layout analysis
        2463, -- 1908.10084 Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks
        2497, -- 1909.01326 The Woman Worked as a Babysitter: On Biases in Language Generation
        2586, -- 1909.11229 Pretraining boosts out-of-domain robustness for pose estimation
        2598, -- 1909.11879 Aspect and Opinion Term Extraction for Hotel Reviews using Transfer Le
        2626, -- 1910.01108 DistilBERT, a distilled version of BERT: smaller, faster, cheaper and
        2673, -- 1910.06294 Training Compact Models for Low Resource Entity Tagging using Pre-trai
        2704, -- 1910.09217 Decoupling Representation and Classifier for Long-Tailed Recognition
        2715, -- 1910.10683 Exploring the Limits of Transfer Learning with a Unified Text-to-Text
        2718, -- 1910.10781 Hierarchical Transformers for Long Document Classification
        2735, -- 1910.12607 Generative Pre-Training for Speech with Autoregressive Predictive Codi
        2785, -- 1911.03310 How Language-Neutral is Multilingual BERT?
        2788, -- 1911.03437 SMART: Robust and Efficient Fine-Tuning for Pre-trained Natural Langua
        2799, -- 1911.04211 NegBERT: A Transfer Learning Approach for Negation Detection and Scope
        2840, -- 1911.09514 Continual Learning with Adaptive Weights (CLAW)
        2850, -- 1911.10134 A Transfer Learning Method for Goal Recognition Exploiting Cross-Domai
        2910, -- 1912.03330 ClusterFit: Improving Generalization of Visual Representations
        2928, -- 1912.06290 Meta-Learning Initializations for Image Segmentation
        2929, -- 1912.06670 Common Voice: A Massively-Multilingual Speech Corpus
        2931, -- 1912.07076 Multilingual is not enough: BERT for Finnish
        2942, -- 1912.08881 Pruning by Explaining: A Novel Criterion for Deep Neural Network Pruni
        2950, -- 1912.10070 Destruction of Image Steganography using Generative Adversarial Networ
        3009, -- 2001.06381 A Common Semantic Space for Monolingual and Cross-Lingual Meta-Embeddi
        3157, -- 2003.00080 Transferring Dense Pose to Proximal Animal Classes
        3187, -- 2003.03151 Demographic Bias in Presentation Attack Detection of Iris Recognition
        3189, -- 2003.03256 Traffic Signs Detection and Recognition System using Deep Learning
        3267, -- 2003.13145 Can AI help in screening Viral and COVID-19 pneumonia?
        3270, -- 2003.13503 Diagnosis of Breast Cancer Based on Modern Mammography using Hybrid Tr
        3282, -- 2004.00248 Adversarial Transfer Learning for Punctuation Restoration
        3294, -- 2004.01804 Google Landmarks Dataset v2 -- A Large-Scale Benchmark for Instance-Le
        3298, -- 2004.02349 TAPAS: Weakly Supervised Table Parsing via Pre-training
        3320, -- 2004.04100 KdConv: A Chinese Multi-domain Dialogue Dataset Towards Multi-turn Kno
        3332, -- 2004.04721 Translation Artifacts in Cross-lingual Transfer Learning
        3337, -- 2004.05160 On the Language Neutrality of Pre-trained Multilingual Representations
        3355, -- 2004.06824 Melanoma Detection using Adversarial Training and Deep Transfer Learni
        3356, -- 2004.06824 Melanoma Detection using Adversarial Training and Deep Transfer Learni
        3378, -- 2004.08955 ResNeSt: Split-Attention Networks
        3414, -- 2004.12276 Fashionpedia: Ontology, Segmentation, and an Attribute Localization Da
        3420, -- 2004.12629 CascadeTabNet: An approach for end to end table detection and structur
        3467, -- 2004.14765 Pruning artificial neural networks: a way to find well-generalizing, h
        3489, -- 2005.00247 AdapterFusion: Non-Destructive Task Composition for Transfer Learning
        3495, -- 2005.00547 GoEmotions: A Dataset of Fine-Grained Emotions
        3499, -- 2005.00628 Intermediate-Task Transfer Learning with Pretrained Models for Natural
        3507, -- 2005.00796 A Simple Language Model for Task-Oriented Dialogue
        3510, -- 2005.00944 Understanding and Improving Information Transfer in Multi-Task Learnin
        3512, -- 2005.01107 Simplifying Paragraph-level Question Generation via Transformer Langua
        3515, -- 2005.01328 DoQA -- Accessing Domain-Specific FAQs via Conversational QA
        3523, -- 2005.01972 End-to-end Whispered Speech Recognition with Frequency-weighted Approa
        3562, -- 2005.05442 On the Generation of Medical Dialogues for COVID-19
        3576, -- 2005.07202 Pre-training technique to localize medical BERT and enhance biomedical
        3581, -- 2005.07683 Movement Pruning: Adaptive Sparsity by Fine-Tuning
        3606, -- 2005.10433 Text-to-Text Pre-Training for Data-to-Text Tasks
        3633, -- 2005.14140 Modeling the Distribution of Normal Data in Pre-Trained Deep Features
        3707, -- 2006.07698 Transferring Monolingual Model to Low-Resource Language: The Case of T
        3769, -- 2006.11325 Self-Supervised Prototypical Transfer Learning for Few-Shot Classifica
        3772, -- 2006.11436 BEV-Seg: Bird's Eye View Semantic Segmentation Using Geometry and Sema
        3803, -- 2006.14512 Uncovering the Connections Between Adversarial Transferability and Kno
        3833, -- 2006.16712 Model-based Reinforcement Learning: A Survey
        3849, -- 2007.00992 Rethinking Channel Dimensions for Efficient Model Design
        3856, -- 2007.01852 Language-agnostic BERT Sentence Embedding
        3905, -- 2007.08489 Do Adversarially Robust ImageNet Models Transfer Better?
        3906, -- 2007.08558 On Robustness and Transferability of Convolutional Neural Networks
        3925, -- 2007.11622 TinyTL: Reduce Activations, Not Trainable Parameters for Efficient On-
        3949, -- 2007.14895 Reliable Tuberculosis Detection using Chest X-ray with Deep Learning,
        4015, -- 2008.05348 Approaching Neural Chinese Word Segmentation as a Low-Resource Machine
        4019, -- 2008.05671 Large-scale Transfer Learning for Low-resource Spoken Language Underst
        4086, -- 2008.13546 Effective Transfer Learning for Identifying Similar Questions: Matchin
        4098, -- 2009.01303 Comparative Evaluation of Pretrained Transfer Learning Models on Autom
        4120, -- 2009.04170 Diversified Mutual Learning for Deep Metric Learning
        4151, -- 2009.07185 Critical Thinking for Language Models
        4271, -- 2010.02573 The Multilingual Amazon Reviews Corpus
        4293, -- 2010.03450 "I'd rather just go to bed": Understanding Indirect Answers
        4298, -- 2010.03692 An Audio-Video Deep and Transfer Learning Framework for Multimodal Emo
        4314, -- 2010.04791 ChrEn: Cherokee-English Machine Translation for Endangered Language Re
        4325, -- 2010.05171 fairseq S2T: Fast Speech-to-Text Modeling with fairseq
        4407, -- 2010.11574 Exploiting News Article Structure for Automatic Corpus Generation of E
        4410, -- 2010.11694 Unsupervised Representation Learning by InvariancePropagation
        4424, -- 2010.12321 BARThez: a Skilled Pretrained French Sequence-to-Sequence Model
        4450, -- 2010.13902 Graph Contrastive Learning with Augmentations
        4505, -- 2011.02727 An analysis of the transfer learning of convolutional neural networks
        4510, -- 2011.03023 Language Model is All You Need: Natural Language Understanding as Ques
        4637, -- 2011.14522 Feature Learning in Infinite-Width Neural Networks
        4735, -- 2012.07463 Parameter-Efficient Transfer Learning with Diff Pruning
        4780, -- 2012.12624 Learning Dense Representations of Phrases at Scale
        4833, -- 2101.00121 WARP: Word-level Adversarial ReProgramming
        4858, -- 2101.01213 Improving Portuguese Semantic Role Labeling with Transformers and Tran
        4894, -- 2101.05022 Re-labeling ImageNet: from Single to Multi-Labels, from Global to Loca
        4913, -- 2101.07597 UniSpeech: Unified Speech Representation Learning with Labeled and Unl
        4916, -- 2101.08133 Active Learning for Sequence Tagging with Deep Pre-trained Models and
        4922, -- 2101.08674 DAF:re: A Challenging, Crowd-Sourced, Large-Scale, Long-Tailed Dataset
        5004, -- 2102.04208 Contrastive Embeddings for Neural Architectures
        5038, -- 2102.07150 indicnlp@kgp at DravidianLangTech-EACL2021: Offensive Language Identif
        5068, -- 2102.09854 Intrinsically Motivated Open-Ended Multi-Task Learning Using Transfer
        5172, -- 2103.05959 Beyond Self-Supervision: A Simple Yet Effective Network Distillation A
        5178, -- 2103.06410 MediaSum: A Large-scale Media Interview Dataset for Dialogue Summariza
        5195, -- 2103.07449 Cooperative Self-training of Machine Reading Comprehension
        5223, -- 2103.10069 Constructive and Toxic Speech Detection for Open-domain Social Media C
        5235, -- 2103.10957 Efficient Visual Pretraining with Contrastive Detection
        5246, -- 2103.11811 MasakhaNER: Named Entity Recognition for African Languages
        5259, -- 2103.12731 Scaling Local Self-Attention for Parameter Efficient Visual Backbones
        5381, -- 2104.02133 SpeechStew: Simply Mix All Available Speech Recognition Data to Train
        5384, -- 2104.02443 CodeTrans: Towards Cracking the Language of Silicon's Code Through Sel
        5400, -- 2104.04015 CutPaste: Self-Supervised Learning for Anomaly Detection and Localizat
        5463, -- 2104.07412 XTREME-R: Towards More Challenging and Nuanced Multilingual Evaluation
        5489, -- 2104.08247 What to Pre-Train on? Efficient Intermediate Task Selection
        5519, -- 2104.08771 Cross-Attention is All You Need: Adapting Pretrained Transformers for
        5538, -- 2104.09696 X-METRA-ADA: Cross-lingual Meta-Transfer Learning Adaptation to Natura
        5570, -- 2104.11673 Deep Learning Based Assessment of Synthetic Speech Naturalness
        5620, -- 2105.00157 A Deep Learning Framework for Lifelong Machine Learning
        5635, -- 2105.01147 Sketches image analysis: Web image search engine usingLSH index and DN
        5653, -- 2105.02855 Adapting Monolingual Models: Data can be Scarce when Language Similari
        5664, -- 2105.03323 TITAN: T Cell Receptor Specificity Prediction with Bimodal Attention N
        5782, -- 2105.11741 ConSERT: A Contrastive Framework for Self-Supervised Sentence Represen
        5860, -- 2106.01548 When Vision Transformers Outperform ResNets without Pre-training or St
        5880, -- 2106.02637 Aligning Pretraining for Detection via Object-Level Contrastive Learni
        5909, -- 2106.03847 GAN Cocktail: mixing GANs without dataset access
        5911, -- 2106.03983 Investigating Transfer Learning in Multilingual Pre-trained Language M
        5954, -- 2106.05937 Fair Normalizing Flows
        5968, -- 2106.06257 HPO-B: A Large-Scale Reproducible Benchmark for Black-Box HPO based on
        5985, -- 2106.07139 Pre-Trained Models: Past, Present and Future
        6039, -- 2106.09756 PyKale: Knowledge-Aware Machine Learning from Multiple Sources in Pyth
        6047, -- 2106.10161 Golos: Russian Dataset for Speech Research
        6094, -- 2106.12479 Classifying Textual Data with Pre-trained Vision Models through Transf
        6246, -- 2107.07106 Online Learning for Recommendations at Grubhub
        6293, -- 2107.10471 Improving Polyphonic Sound Event Detection on Multichannel Recordings
        6330, -- 2107.14372 Using transfer learning to study burned area dynamics: A case study of
        6360, -- 2108.01819 Transfer Learning for Pose Estimation of Illustrated Characters
        6435, -- 2108.07258 On the Opportunities and Risks of Foundation Models
        6450, -- 2108.08810 Do Vision Transformers See Like Convolutional Neural Networks?
        6473, -- 2108.10724 How Hateful are Movies? A Study and Prediction on Movie Subtitles
        6517, -- 2108.13672 SANSformers: Self-Supervised Forecasting in Electronic Health Records
        6549, -- 2109.01903 Robust fine-tuning of zero-shot models
        6558, -- 2109.02903 IndicBART: A Pre-trained Model for Indic Natural Language Generation
        6594, -- 2109.04655 Zero-Shot Dialogue State Tracking via Cross-Task Transfer
        6713, -- 2109.11680 Simple and Effective Zero-shot Cross-lingual Phoneme Recognition
        6720, -- 2109.12068 AraT5: Text-to-Text Transformers for Arabic Language Generation
        6739, -- 2109.13228 PASS: An ImageNet replacement for self-supervised pretraining without
        6763, -- 2109.15298 Multi-granular Legal Topic Classification on Greek Legislation
        6804, -- 2110.02442 PoNet: Pooling Network for Efficient Token Mixing in Long Sequences
        6808, -- 2110.02639 On The Transferability of Deep-Q Networks
        6854, -- 2110.04366 Towards a Unified View of Parameter-Efficient Transfer Learning
        6861, -- 2110.04627 Vector-quantized Image Modeling with Improved VQGAN
        6872, -- 2110.05266 Chaos as an interpretable benchmark for forecasting and data-driven mo
        6900, -- 2110.06273 Småprat: DialoGPT for Natural Language Generation of Swedish Dialogue
        6941, -- 2110.07560 Composable Sparse Fine-Tuning for Cross-Lingual Transfer
        7018, -- 2110.11006 Bristle: Decentralized Federated Learning in Byzantine, Non-i.i.d. Env
        7022, -- 2110.11316 CLOOB: Modern Hopfield Networks with InfoLOOB Outperform CLIP
        7059, -- 2110.13683 BioIE: Biomedical Information Extraction with Multi-head Attention Enh
        7071, -- 2110.14764 Generalized Funnelling: Ensemble Learning and Heterogeneous Document E
        7093, -- 2110.15717 LIDSNet: A Lightweight on-device Intent Detection model using Deep Sia
        7113, -- 2111.00526 FinEAS: Financial Embedding Analysis of Sentiment
        7137, -- 2111.01722 Predicting the Location of Bicycle-sharing Stations using OpenStreetMa
        7161, -- 2111.03017 MT3: Multi-Task Multitrack Music Transcription
        7164, -- 2111.03452 Generalized Radiograph Representation Learning via Cross-supervision b
        7165, -- 2111.03511 Disengagement Cause-and-Effect Relationships Extraction Using an NLP P
        7184, -- 2111.04798 TAGLETS: A System for Automatic Semi-Supervised Learning with Auxiliar
        7191, -- 2111.05754 Prune Once for All: Sparse Pre-Trained Language Models
        7235, -- 2111.08872 TorchGeo: Deep Learning With Geospatial Data
        7243, -- 2111.09415 Automated PII Extraction from Social Media for Raising Privacy Awarene
        7244, -- 2111.09453 RoBERTuito: a pre-trained language model for social media text in Span
        7254, -- 2111.09832 Merging Models with Fisher-Weighted Averaging
        7256, -- 2111.09839 Training Neural Networks with Fixed Sparse Masks
        7262, -- 2111.10050 Combined Scaling for Zero-shot Transfer Learning
        7272, -- 2111.10952 ExT5: Towards Extreme Multi-Task Scaling for Transfer Learning
        7282, -- 2111.11429 Benchmarking Detection Transfer Learning with Vision Transformers
        7284, -- 2111.11432 Florence: A New Foundation Model for Computer Vision
        7293, -- 2111.12158 Using Language Model to Bootstrap Human Activity Recognition Ambient S
        7313, -- 2111.13445 How Well Do Sparse Imagenet Models Transfer?
        7489, -- 2112.06825 VL-Adapter: Parameter-Efficient Transfer Learning for Vision-and-Langu
        7498, -- 2112.07637 Exploring Neural Models for Query-Focused Summarization
        7505, -- 2112.07869 Fine-Tuning Large Neural Language Models for Biomedical Natural Langua
        7547, -- 2112.09106 RegionCLIP: Region-based Language-Image Pretraining
        7554, -- 2112.09290 PeopleSansPeople: A Synthetic Data Generator for Human-Centric Compute
        7564, -- 2112.09866 Cascading Adaptors to Leverage English Data to Improve Performance of
        7598, -- 2112.12650 Distilling the Knowledge of Romanian BERTs Using Multiple Teachers
        7615, -- 2112.14569 Fine-Tuning Transformers: Vocabulary Transfer
        7621, -- 2112.15121 On the Role of Neural Collapse in Transfer Learning
        7629, -- 2112.15442 Mythological Medical Machine Learning: Boosting the Performance of a D
        7713, -- 2201.06642 Towards a Cleaner Document-Oriented Multilingual Crawled Corpus
        7739, -- 2201.08371 Revisiting Weakly Supervised Pre-Training of Visual Perception Models
        7741, -- 2201.08471 Transfer Learning Approaches for Building Cross-Language Dense Retriev
        7751, -- 2201.09390 AttentionHTR: Handwritten Text Recognition Based on Attention Encoder-
        7763, -- 2201.09997 Razmecheno: Named Entity Recognition from Digital Archive of Diaries "
        7821, -- 2202.00095 Deconfounded Representation Similarity for Comparison of Neural Networ
        7844, -- 2202.01011 Auto-Transfer: Learning to Route Transferrable Representations
        7845, -- 2202.01096 Identifying Suitable Tasks for Inductive Transfer Through the Analysis
        7926, -- 2202.05144 InPars: Data Augmentation for Information Retrieval using Large Langua
        7933, -- 2202.05457 Hindi/Bengali Sentiment Analysis Using Transfer Learning and Joint Dua
        7958, -- 2202.06823 Development and Comparison of Scoring Functions in Curriculum Learning
        7969, -- 2202.07415 NeuPL: Neural Population Learning
        8004, -- 2202.08906 ST-MoE: Designing Stable and Transferable Sparse Expert Models
        8026, -- 2202.10222 Robots Learn Increasingly Complex Tasks with Intrinsic Motivation and
        8030, -- 2202.10453 Predicting emotion from music videos: exploring the relative contribut
        8036, -- 2202.11094 GroupViT: Semantic Segmentation Emerges from Text Supervision
        8102, -- 2203.00077 One Model is All You Need: Multi-Task Learning Enables Simultaneous Hi
        8111, -- 2203.00585 Self-Supervised Vision Transformers Learn Visual Concepts in Histopath
        8188, -- 2203.04668 Towards Inadequately Pre-trained Models in Transfer Learning
        8251, -- 2203.07436 SuperAnimal pretrained pose estimation models for behavioral analysis
        8361, -- 2203.11008 Transformer-based HTR for Historical Documents
        8366, -- 2203.11096 CLIP meets GamePhysics: Towards bug identification in gameplay videos
        8377, -- 2203.11562 A Text-to-Speech Pipeline, Evaluation Methodology, and Initial Fine-Tu
        8412, -- 2203.13248 Pastiche Master: Exemplar-Based High-Resolution Portrait Style Transfe
        8444, -- 2203.14415 Mugs: A Multi-Granular Self-Supervised Learning Framework
        8455, -- 2203.14940 Learning to Prompt for Open-Vocabulary Object Detection with Vision-La
        8489, -- 2203.16329 Parameter-efficient Model Adaptation for Vision Transformers
        8619, -- 2204.03649 Unsupervised Prompt Learning for Vision-Language Models
        8705, -- 2204.06487 Adapting Pre-trained Language Models to African Languages via Multilin
        8719, -- 2204.07118 DeiT III: Revenge of the ViT
        8725, -- 2204.07305 Pushing the Limits of Simple Pipelines for Few-Shot Learning: External
        8755, -- 2204.08083 AfriWOZ: Corpus for Exploiting Cross-Lingual Transferability for Gener
        8869, -- 2204.13545 Predicting Cellular Responses to Novel Drug Perturbations at a Single-
        8915, -- 2205.01381 Kompetencer: Fine-grained Skill Classification in Danish Job Postings
        9031, -- 2205.07477 Manifold Characteristics That Predict Downstream Task Performance
        9046, -- 2205.08808 Evaluation of Transfer Learning for Polish with a Text-to-Text Model
        9055, -- 2205.09328 TransTab: Learning Transferable Tabular Transformers Across Tables
        9122, -- 2205.11108 Paddy Doctor: A Visual Image Dataset for Automated Paddy Disease Class
        9150, -- 2205.12148 Hyper-X: A Unified Hypernetwork for Multi-Task Multilingual Transfer
        9180, -- 2205.12647 Overcoming Catastrophic Forgetting in Zero-Shot Cross-Lingual Generati
        9327, -- 2206.00962 Transfer Language Selection for Zero-Shot Cross-Lingual Abusive Langua
        9373, -- 2206.02421 MorisienMT: A Dataset for Mauritian Creole Machine Translation
        9462, -- 2206.06522 LST: Ladder Side-Tuning for Parameter and Memory Efficient Transfer Le
        9542, -- 2206.09556 An Empirical Analysis on the Vulnerabilities of End-to-End Speech Segr
        9639, -- 2206.14504 GERNERMED++: Transfer Learning in German Medical NLP
        9650, -- 2206.15369 No Reason for No Supervision: Improved Generalization in Supervised Mo
        9716, -- 2207.03552 An Embedding-Dynamic Approach to Self-supervised Learning
        9723, -- 2207.03881 The Power of Transfer Learning in Agricultural Applications: AgriNet
        9770, -- 2207.05739 A Data-Based Perspective on Transfer Learning
        9809, -- 2207.08051 SatMAE: Pre-training Transformers for Temporal and Multi-Spectral Sate
        9831, -- 2207.09150 On the Usability of Transformers-based models for a French Question-An
        9845, -- 2207.09858 GenHPF: General Healthcare Predictive Framework with Multi-task Multi-
        9858, -- 2207.10409 Sequence Models for Drone vs Bird Classification
        9926, -- 2207.14200 CrAM: A Compression-Aware Minimizer
        10090, -- 2208.09708 DenseShift: Towards Accurate and Efficient Low-Bit Power-of-Two Quanti
        10147, -- 2208.12415 MuLan: A Joint Embedding of Music Audio and Natural Language
        10149, -- 2208.12666 Effectiveness of Mining Audio and Text Pairs from Public Data for Impr
        10244, -- 2209.03917 Exploring Target Representations for Masked Autoencoders
        10320, -- 2209.08199 ScreenQA: Large-Scale Question-Answer Pairs over Mobile App Screenshot
        10408, -- 2209.12325 An Empirical Study on Cross-X Transfer for Legal Judgment Prediction
        10424, -- 2209.13224 Regularized Soft Actor-Critic for Behavior Transfer Learning
        10448, -- 2209.14500 Bidirectional Language Models Are Also Few-shot Learners
        10623, -- 2210.03422 SpaceQA: Answering Questions about the Design of Space Missions and Sp
        10760, -- 2210.06455 Token-Label Alignment for Vision Transformers
        10794, -- 2210.07225 Unified Vision and Language Prompt Learning
        10814, -- 2210.07574 Is synthetic data from generative models ready for image recognition?
        10968, -- 2210.12391 MasakhaNER 2.0: Africa-centric Transfer Learning for Named Entity Reco
        10998, -- 2210.12809 Data Augmentation for Automated Essay Scoring using Transformer Models
        11002, -- 2210.12843 Delving into Masked Autoencoders for Multi-Label Thorax Disease Classi
        11125, -- 2210.16559 Few-shot Image Generation via Adaptation-Aware Kernel Modulation
        11184, -- 2211.01226 DEArt: Dataset of European Art
        11254, -- 2211.03946 Understanding the Role of Mixup in Knowledge Distillation: An Empirica
        11266, -- 2211.04325 Will we run out of data? Limits of LLM scaling based on human-generate
        11343, -- 2211.07636 EVA: Exploring the Limits of Masked Visual Representation Learning at
        11345, -- 2211.07730 QueryForm: A Simple Zero-shot Form Entity Query Framework
        11506, -- 2211.11747 NEVIS'22: A Stream of 100 Tasks Sampled from 30 Years of Computer Visi
        11508, -- 2211.11798 Can You Label Less by Using Out-of-Domain Data? Active & Transfer Lear
        11630, -- 2211.14539 An Automatic SOAP Classification System Using Weakly Supervision And T
        11662, -- 2211.15457 Hypernetworks for Zero-shot Transfer in Reinforcement Learning
        11673, -- 2211.15717 Learning deep abdominal CT registration through adaptive loss weightin
        11715, -- 2211.17042 Spatio-Temporal Crop Aggregation for Video Representation Learning
        11721, -- 2211.17148 ConvLab-3: A Flexible Dialogue System Toolkit Based on a Unified Data
        11831, -- 2212.03220 Visual Query Tuning: Towards Effective Usage of Intermediate Represent
        11836, -- 2212.03246 MobileTL: On-device Transfer Learning with Inverted Residual Blocks
        11850, -- 2212.03760 Pivotal Role of Language Modeling in Recommender Systems: Enriching Ta
        12032, -- 2212.08681 Plansformer: Generating Symbolic Plans using Transformers
        12043, -- 2212.08992 PoE: a Panel of Experts for Generalized Automatic Dialogue Assessment
        12107, -- 2212.10051 A Framework of Customer Review Analysis Using the Aspect-Based Opinion
        12170, -- 2212.10773 MultiInstruct: Improving Multi-Modal Zero-Shot Learning via Instructio
        12280, -- 2301.00785 CLIP-Driven Universal Model for Organ Segmentation and Tumor Detection
        12308, -- 2301.01928 Event Camera Data Pre-training
        12347, -- 2301.03136 Removing Non-Stationary Knowledge From Pre-Trained Language Models for
        12348, -- 2301.03150 MOTOR: A Time-To-Event Foundation Model For Structured Medical Records
        12424, -- 2301.07067 Transformers as Algorithms: Generalization and Stability in In-context
        12425, -- 2301.07069 Prompting Large Language Model for Machine Translation: A Case Study
        12489, -- 2301.09626 Efficient Language Model Training through Cross-Lingual and Progressiv
        12583, -- 2301.11660 Probing Out-of-Distribution Robustness of Language Models with Paramet
        12618, -- 2301.12246 A Closer Look at Few-shot Classification Again
        12898, -- 2302.03133 Domain Adaptation for Time Series Under Feature and Label Shifts
        12917, -- 2302.03499 Exploring Data Augmentation for Code Generation Tasks
        12945, -- 2302.04009 Investigating the role of model-based learning in exploration and tran
        12993, -- 2302.04852 SparseProp: Efficient Sparse Backpropagation for Faster Training of Ne
        12997, -- 2302.04870 Offsite-Tuning: Transfer Learning without Full Model
        13019, -- 2302.05441 Project and Probe: Sample-Efficient Domain Adaptation by Interpolating
        13071, -- 2302.06605 UniAdapter: Unified Parameter-Efficient Transfer Learning for Cross-mo
        13104, -- 2302.07350 Graph schemas as abstractions for transfer learning, inference, and pl
        13192, -- 2302.09483 Why Is Public Pretraining Necessary for Private Model Training?
        13255, -- 2302.11529 Modular Deep Learning
        13269, -- 2302.12022 DoG is SGD's Best Friend: A Parameter-Free Dynamic Step Size Schedule
        13357, -- 2302.14225 Weighted Sampling for Masked Language Modeling
        13367, -- 2302.14354 Deep Learning for Identifying Iran's Cultural Heritage Buildings in Ne
        13436, -- 2303.01105 Evidence-empowered Transfer Learning for Alzheimer's Disease
        13504, -- 2303.02861 Multitask Prompt Tuning Enables Parameter-Efficient Transfer Learning
        13560, -- 2303.04278 CUDA: Convolution-based Unlearnable Datasets
        13577, -- 2303.04751 Multimodal Parameter-Efficient Few-Shot Class Incremental Learning
        13650, -- 2303.06167 Overwriting Pretrained Bias with Finetuning Data
        13750, -- 2303.07910 Revisit Parameter-Efficient Transfer Learning: A Two-Stage Paradigm
        13845, -- 2303.09663 Efficient Computation Sharing for Multi-Task Visual Scene Understandin
        13854, -- 2303.09769 Denoising Diffusion Autoencoders are Unified Self-supervised Learners
        13895, -- 2303.10594 AdaptGuard: Defending Against Universal Attacks for Model Adaptation
        13961, -- 2303.11643 Manipulating Transfer Learning for Property Inference
        13980, -- 2303.12001 ViC-MAE: Self-Supervised Representation Learning from Images and Video
        14008, -- 2303.12489 Few-shot Multimodal Multitask Multilingual Learning
        14092, -- 2303.13931 MSdocTr-Lite: A Lite Transformer for Full Page Multi-script Handwritin
        14152, -- 2303.14773 BlackVIP: Black-Box Visual Prompting for Robust Transfer Learning
        14236, -- 2303.16256 Scalable handwritten text recognition system for lexicographic sources
        14358, -- 2304.00083 A Generative Framework for Low-Cost Result Validation of Machine Learn
        14369, -- 2304.00387 HaLP: Hallucinating Latent Positives for Skeleton-based Self-Supervise
        14378, -- 2304.00685 Vision-Language Models for Vision Tasks: A Survey
        14388, -- 2304.00869 GreekBART: The First Pretrained Greek Sequence-to-Sequence Model
        14583, -- 2304.04703 Transfer Learning for Low-Resource Sentiment Analysis
        14598, -- 2304.04934 Model Sparsity Can Simplify Machine Unlearning
        14599, -- 2304.04947 Conditional Adapters: Parameter-efficient Transfer Learning with Fast
        14625, -- 2304.05430 Transfer Learning Across Heterogeneous Features For Efficient Tensor P
        14668, -- 2304.06446 SpectFormer: Frequency and Attention is what you need in a Vision Tran
        14676, -- 2304.06704 How Will It Drape Like? Capturing Fabric Mechanics from Depth Images
        14824, -- 2304.10036 Visual DNA: Representing and Comparing Images using Distributions of N
        14908, -- 2304.11834 Robust Tickets Can Transfer Better: Drawing More Transferable Subnetwo
        14921, -- 2304.12314 Distilling from Similar Tasks for Transfer Learning on a Budget
        15128, -- 2305.01278 VPGTrans: Transfer Visual Prompt Generator across LLMs
        15160, -- 2305.01918 Improving Contrastive Learning of Sentence Embeddings from AI Feedback
        15198, -- 2305.02459 Transfer and Active Learning for Dissonance Detection: Addressing the
        15260, -- 2305.03407 Online Gesture Recognition using Transformer and Natural Language Proc
        15322, -- 2305.04501 SEGA: Structural Entropy Guided Anchor View for Graph Contrastive Lear
        15328, -- 2305.04582 MultiTACRED: A Multilingual Version of the TAC Relation Extraction Dat
        15623, -- 2305.09690 A Whisper transformer for audio captioning trained with synthetic capt
        15641, -- 2305.09972 Real-Time Flying Object Detection with YOLOv8
        15646, -- 2305.10018 Transfer Learning for Fine-grained Classification Using Semi-supervise
        15779, -- 2305.11624 Efficient ConvBN Blocks for Transfer Learning and Beyond
        15797, -- 2305.11834 Pengi: An Audio Language Model for Audio Tasks
        15808, -- 2305.11944 Exploring the Viability of Synthetic Query Generation for Relevance Pr
        15951, -- 2305.13456 Revisiting pre-trained remote sensing model benchmarks: resizing and n
        16240, -- 2305.15348 READ: Recurrent Adaptation of Large Transformers
        16409, -- 2305.17223 Do We Really Need a Large Number of Visual Prompts?
        16414, -- 2305.17303 Distilling BlackBox to Interpretable models for Efficient Transfer Lea
        16646, -- 2305.19623 Point-GCC: Universal Self-supervised 3D Scene Pre-training via Geometr
        16655, -- 2305.19759 Simple yet Effective Code-Switching Language Identification with Multi
        16711, -- 2306.00124 Pre-Trained Language-Meaning Models for Multilingual Parsing and Gener
        16774, -- 2306.00789 Improved Cross-Lingual Transfer Learning For Automatic Speech Translat
        16843, -- 2306.01327 Speech Translation with Foundation Models and Optimal Transport: UPC a
        16868, -- 2306.01690 Context selectivity with dynamic availability enables lifelong continu
        16873, -- 2306.01708 TIES-Merging: Resolving Interference When Merging Models
        16874, -- 2306.01709 Distilling Efficient Language-Specific Models for Cross-Lingual Transf
        16959, -- 2306.02775 Input-gradient space particle inference for neural network ensembles
        17051, -- 2306.03789 On the Robustness of Arabic Speech Dialect Identification
        17103, -- 2306.04399 Transfer Learning of Transformer-based Speech Recognition Models from
        17123, -- 2306.04724 Prompter: Zero-shot Adaptive Prefixes for Dialogue State Tracking Doma
        17200, -- 2306.05539 Instruction Tuned Models are Quick Learners
        17215, -- 2306.05785 End-to-End Neural Network Compression via $\frac{\ell_1}{\ell_2}$ Regu
        17241, -- 2306.06156 PoET: A generative model of protein families as sequences-of-sequences
        17292, -- 2306.06955 A Brief Review of Hypernetworks in Deep Learning
        17327, -- 2306.07373 EriBERTa: A Bilingual Pre-Trained Language Model for Clinical Natural
        17382, -- 2306.07967 One-for-All: Generalized LoRA for Parameter-Efficient Fine-tuning
        17540, -- 2306.09910 LabelBench: A Comprehensive Framework for Benchmarking Adaptive Label-
        17619, -- 2306.11341 MSVD-Indonesian: A Benchmark for Multimodal Video-Text Tasks in Indone
        17684, -- 2306.12834 Natural Language Processing in Electronic Health Records in Relation t
        17751, -- 2306.14169 A Web-based Mpox Skin Lesion Detection System Using State-of-the-art D
        17767, -- 2306.14592 Transfer Learning across Several Centuries: Machine and Historian Inte
        17809, -- 2306.15550 CamemBERT-bio: Leveraging Continual Pre-training for Cost-Effective Mo
        17820, -- 2306.15706 Approximated Prompt Tuning for Vision-Language Pre-trained Models
        18242, -- 2307.07280 Replay to Remember: Continual Layer-Specific Fine-tuning for German Sp
        18246, -- 2307.07397 Improving Zero-Shot Generalization for CLIP with Synthesized Prompts
        18303, -- 2307.08303 Soft Prompt Tuning for Augmenting Dense Retrieval with Large Language
        18335, -- 2307.08702 Diffusion Models Beat GANs on Image Classification
        18362, -- 2307.09233 Distilling Knowledge from Text-to-Image Generative Models Improves Vis
        18537, -- 2307.12018 GEM: Boost Simple Network for Glass Surface Segmentation via Vision Fo
        18621, -- 2307.13546 Transfer Learning for Portfolio Optimization
        18665, -- 2307.14316 Reinforcement Learning by Guided Safe Exploration
        18668, -- 2307.14334 Towards Generalist Biomedical AI
        18775, -- 2307.16372 LP-MusicCaps: LLM-Based Pseudo Music Captioning
        19146, -- 2308.05986 Fast and Accurate Transferability Measurement by Evaluating Intra-clas
        19180, -- 2308.06522 SLoRA: Federated Parameter Efficient Fine-Tuning of Language Models
        19266, -- 2308.07706 Exploring Transfer Learning in Medical Image Segmentation using Vision
        19424, -- 2308.09610 On the Effectiveness of LayerNorm Tuning for Continual Learning in Vis
        19434, -- 2308.09710 SimDA: Simple Diffusion Adapter for Efficient Video Generation
        19468, -- 2308.09971 Disposable Transfer Learning for Selective Source Task Unlearning
        19491, -- 2308.10144 ExpeL: LLM Agents Are Experiential Learners
        19498, -- 2308.10172 VLN-PETL: Parameter-Efficient Transfer Learning for Vision-and-Languag
        19603, -- 2308.11186 Knowledge-Aware Prompt Tuning for Generalizable Vision-Language Models
        19626, -- 2308.11448 Masked Momentum Contrastive Learning for Zero-shot Semantic Understand
        19752, -- 2308.12962 Motion-Guided Masking for Spatiotemporal Representation Learning
        19787, -- 2308.13373 Enhanced Mortality Prediction In Patients With Subarachnoid Haemorrhag
        19852, -- 2308.14316 UniPT: Universal Parallel Tuning for Transfer Learning with Efficient
        19863, -- 2308.14500 LAC: Latent Action Composition for Skeleton-based Action Segmentation
        19888, -- 2308.14969 Uncovering the Hidden Cost of Model Compression
        19895, -- 2308.15074 Exploring Model Transferability through the Lens of Potential Energy
        19918, -- 2308.15474 A General-Purpose Self-Supervised Model for Computational Pathology
        20071, -- 2309.01479 Parameter and Computation Efficient Transfer Learning for Vision-Langu
        20131, -- 2309.02429 Building a Winning Team: Selecting Source Model Ensembles using a Subm
        20269, -- 2309.05173 DePT: Decomposed Prompt Tuning for Parameter-Efficient Fine-tuning
        20339, -- 2309.06526 Exploring the Benefits of Differentially Private Pre-training and Para
        20405, -- 2309.07499 Efficiently Robustify Pre-trained Models
        20432, -- 2309.07911 Disentangling Spatial and Temporal Learning for Efficient Image-to-Vid
        20478, -- 2309.08513 SCT: A Simple Baseline for Parameter-Efficient Fine-Tuning via Salient
        20637, -- 2309.10910 Amplifying Pathological Detection in EEG Signaling Pathways through Cr
        20838, -- 2309.13504 Attention Is All You Need For Blind Room Volume Estimation
        21041, -- 2309.16633 Mixup Your Own Pairs
        21227, -- 2310.01217 ScaLearn: Simple and Highly Parameter-Efficient Task Transfer by Learn
        21416, -- 2310.03119 Crossed-IoT device portability of Electromagnetic Side Channel Analysi
        21535, -- 2310.04686 Tight Rates in Supervised Outlier Transfer Learning
        21541, -- 2310.04757 CAD Models to Real-World Images: A Practical Approach to Unsupervised
        21575, -- 2310.05063 Pushing the Limits of Pre-training for Time Series Forecasting in the
        21613, -- 2310.05393 Hierarchical Side-Tuning for Vision Transformers
        21704, -- 2310.06369 Geometrically Aligned Transfer Encoder for Inductive Transfer in Regre
        21717, -- 2310.06511 Self-Supervised Dataset Distillation for Transfer Learning
        22143, -- 2310.11670 Prototype-based HyperAdapter for Sample-Efficient Multi-task Tuning
        22189, -- 2310.12321 A Survey of GPT-3 Family Large Language Models Including ChatGPT and G
        22265, -- 2310.13228 The Less the Merrier? Investigating Language Representation in Multili
        22567, -- 2310.16825 CommonCanvas: An Open Diffusion Model Trained with Creative-Commons Im
        22733, -- 2310.19168 BirdSAT: Cross-View Contrastive Masked Autoencoders for Bird Species C
        22756, -- 2310.19567 CreoleVal: Multilingual Multitask Benchmarks for Creoles
        22883, -- 2311.00958 IndoToD: A Multi-Domain Indonesian Benchmark For End-to-End Task-Orien
        22904, -- 2311.01310 Scattering Vision Transformer: Spectral Mixing Matters
        22981, -- 2311.02971 TabRepo: A Large Scale Repository of Tabular Model Evaluations and its
        23066, -- 2311.04313 Improved Child Text-to-Speech Synthesis through Fastpitch-based Transf
        23145, -- 2311.05659 Enhancing Instance-Level Image Classification with Set-Level Labels
        23168, -- 2311.06169 Deep Fast Vision: A Python Library for Accelerated Deep Transfer Learn
        23174, -- 2311.06242 Florence-2: Advancing a Unified Representation for a Variety of Vision
        23183, -- 2311.06382 Transfer Learning for Structured Pruning under Limited Task Data
        23220, -- 2311.07161 Developing a Named Entity Recognition Dataset for Tagalog
        23507, -- 2311.11001 Gendec: A Machine Learning-based Framework for Gender Detection from J
        23508, -- 2311.11012 Bit Cipher -- A Simple yet Powerful Word Representation System that In
        23511, -- 2311.11077 Adapters: A Unified Library for Parameter-Efficient and Modular Transf
        23633, -- 2311.12943 InteRACT: Transformer Models for Human Intent Prediction Conditioned o
        24002, -- 2311.18034 Hyperpolyglot LLMs: Cross-Lingual Interpretability in Token Embeddings
        24220, -- 2312.02021 Strong but simple: A Baseline for Domain Generalized Dense Perception
        24341, -- 2312.03248 Customizable Combination of Parameter-Efficient Modules for Multi-Task
        24373, -- 2312.03694 Parameter-Efficient Transfer Learning of Audio Spectrogram Transformer
        24570, -- 2312.05968 Jumpstarting Surgical Computer Vision
        24656, -- 2312.07028 Dynamic Corrective Self-Distillation for Better Fine-Tuning of Pretrai
        24673, -- 2312.07315 NVS-Adapter: Plug-and-Play Novel View Synthesis from a Single Image
        24778, -- 2312.08900 Context-PEFT: Efficient Multi-Modal, Multi-Task Fine-Tuning
        24817, -- 2312.09299 Weight subcloning: direct initialization of transformers using larger
        24893, -- 2312.10613 p-Laplacian Adaptation for Generative Pre-trained Vision-Language Mode
        24898, -- 2312.10700 Cross-Domain Robustness of Transformer-based Keyphrase Generation
        24939, -- 2312.11502 Labrador: Exploring the Limits of Masked Language Modeling for Laborat
        25148, -- 2312.14963 Optimizing Mario Adventures in a Constrained Environment
        25183, -- 2312.15612 APTv2: Benchmarking Animal Pose Estimation and Tracking with a Large-s
        25240, -- 2312.16424 Soft Contrastive Learning for Time Series
        25330, -- 2401.00025 Any-point Trajectory Modeling for Policy Learning
        25404, -- 2401.01178 GBSS:a global building semantic segmentation dataset for large-scale r
        25578, -- 2401.03955 Tiny Time Mixers (TTMs): Fast Pre-trained Models for Enhanced Zero/Few
        25688, -- 2401.05727 Zero Resource Cross-Lingual Part Of Speech Tagging
        25749, -- 2401.06466 PersianMind: A Cross-Lingual Persian-English Large Language Model
        26029, -- 2401.10472 Named Entity Recognition Under Domain Shift via Metric Learning for Li
        26128, -- 2401.12072 Cross-lingual Transfer Learning for Javanese Dependency Parsing
        26146, -- 2401.12215 Less Could Be Better: Parameter-efficient Fine-tuning Advances Medical
        26192, -- 2401.12902 Facing the Elephant in the Room: Visual Prompt Tuning or Full Finetuni
        26264, -- 2401.13942 StyleInject: Parameter Efficient Tuning of Text-to-Image Diffusion Mod
        26310, -- 2401.14421 Multi-Agent Based Transfer Learning for Data-Driven Air Traffic Applic
        26490, -- 2401.17181 Transfer Learning for Text Diffusion Models
        26504, -- 2401.17396 Fine-tuning Transformer-based Encoder for Turkish Language Understandi
        26550, -- 2402.00068 Adapting Amidst Degradation: Cross Domain Li-ion Battery Health Estima
        26596, -- 2402.00828 Efficient Fine-tuning of Audio Spectrogram Transformers via Soft Mixtu
        26684, -- 2402.01692 Maximizing Data Efficiency for Cross-Lingual TTS Adaptation by Self-Su
        26822, -- 2402.03131 Constrained Decoding for Cross-lingual Label Projection
        26890, -- 2402.03749 Vision Superalignment: Weak-to-Strong Generalization for Vision Founda
        26928, -- 2402.04177 Scaling Laws for Downstream Task Performance of Large Language Models
        27014, -- 2402.05128 Enhancing textual textbook question answering with large language mode
        27218, -- 2402.07894 MODIPHY: Multimodal Obscured Detection for IoT using PHantom Convoluti
        27237, -- 2402.08112 A Competition Winning Deep Reinforcement Learning Agent in microRTS
        27442, -- 2402.10877 Robust agents learn causal world models
        27719, -- 2402.13542 ARL2: Aligning Retrievers for Black-box Large Language Models via Self
        27887, -- 2402.15181 Substrate Prediction for RiPP Biosynthetic Enzymes via Masked Language
        27990, -- 2402.16785 CARTE: Pretraining and Transfer for Tabular Learning
        28014, -- 2402.16928 CLAP: Learning Transferable Binary Code Representations with Natural L
        28112, -- 2402.18028 OpenMEDLab: An Open-source Platform for Multi-modality Foundation Mode
        28127, -- 2402.18153 Diffusion-Based Neural Network Weights Generation
        28361, -- 2403.02112 A New Perspective on Smiling and Laughter Detection: Intensity Levels
        28647, -- 2403.06407 Can LLMs' Tuning Methods Work in Medical Multimodal Domain?
        28704, -- 2403.07282 Enhancing Transfer Learning with Flexible Nonparametric Posterior Samp
        28934, -- 2403.10516 FeatUp: A Model-Agnostic Framework for Features at Any Resolution
        28962, -- 2403.10912 Automatic location detection based on deep learning
        29033, -- 2403.11772 S-JEPA: towards seamless cross-dataset transfer through dynamic spatia
        29168, -- 2403.13257 Arcee's MergeKit: A Toolkit for Merging Large Language Models
        29333, -- 2403.15360 SiMBA: Simplified Mamba-Based Architecture for Vision and Multivariate
        29375, -- 2403.15882 VLUE: A New Benchmark and Multi-task Knowledge Transfer Learning for V
        29503, -- 2403.17921 The Need for Speed: Pruning Transformers with One Recipe
        29699, -- 2404.00424 Quantformer: from attention to profit with a quantitative transformer
        29706, -- 2404.00488 Noise-Aware Training of Layout-Aware Language Models
        29741, -- 2404.00801 R^2-Tuning: Efficient Image-to-Video Transfer Learning for Video Tempo
        29742, -- 2404.00801 $R^2$-Tuning: Efficient Image-to-Video Transfer Learning for Video Tem
        29744, -- 2404.00862 Bailong: Bilingual Transfer Learning based on QLoRA and Zip-tie Embedd
        29793, -- 2404.01300 NeRF-MAE: Masked AutoEncoders for Self-Supervised 3D Representation Le
        29883, -- 2404.02684 Cross-Architecture Transfer Learning for Linear-Cost Inference Transfo
        29944, -- 2404.03558 How does Multi-Task Training Affect Transformer In-Context Capabilitie
        30053, -- 2404.05022 DinoBloom: A Foundation Model for Generalizable Cell Embeddings in Hem
        30141, -- 2404.06392 Event Extraction in Basque: Typologically motivated Cross-Lingual Tran
        30166, -- 2404.06773 Adapting LLaMA Decoder to Vision Transformer
        30176, -- 2404.06996 XNLIeu: a dataset for cross-lingual NLI in Basque
        30222, -- 2404.07662 PINNACLE: PINN Adaptive ColLocation and Experimental points selection
        30270, -- 2404.08259 Investigating Neural Machine Translation for Low-Resource Languages: U
        30293, -- 2404.08613 Using Explainable AI and Transfer Learning to understand and predict t
        30468, -- 2404.11428 Explainable Lung Disease Classification from Chest X-Ray Images Utiliz
        31008, -- 2405.01217 CromSS: Cross-modal pre-training with noisy labels for remote sensing
        31131, -- 2405.04760 Large Language Models for Cyber Security: A Systematic Literature Revi
        31144, -- 2405.05176 Encoder-Decoder Framework for Interactive Free Verses with Generation
        31163, -- 2405.05588 Model Inversion Robustness: Can Transfer Learning Help?
        31195, -- 2405.06463 MRSegmentator: Multi-Modality Segmentation of 40 Classes in MRI and CT
        31316, -- 2405.09318 Transfer Learning in Pre-Trained Large Language Models for Malware Det
        31380, -- 2405.10626 Dynamic data sampler for cross-language transfer learning in large lan
        31424, -- 2405.11752 Towards Foundation Model for Chemical Reactor Modeling: Meta-Learning
        31605, -- 2405.14660 Implicit In-context Learning
        31752, -- 2405.16287 LoGAH: Predicting 774-Million-Parameter Transformers using Graph Hyper
        31786, -- 2405.16671 Mixture of Latent Experts Using Tensor Products
        31952, -- 2405.18449 Adaptive Multiscale Retinal Diagnosis: A Hybrid Trio-Model Approach fo
        32020, -- 2405.19501 MDS-ViTNet: Improving saliency prediction for Eye-Tracking with Vision
        32275, -- 2406.02032 M2D-CLAP: Masked Modeling Duo Meets CLAP for Learning General-purpose
        32537, -- 2406.05347 MSAGPT: Neural Prompting Protein Structure Prediction via MSA Generati
        32704, -- 2406.07337 Transferring Knowledge from Large Foundation Models to Small Downstrea
        32924, -- 2406.09717 UniBridge: A Unified Approach to Cross-Lingual Transfer Learning for L
        33193, -- 2406.12031 Large Scale Transfer Learning for Tabular Data via Language Modeling
        33214, -- 2406.12179 The Wisdom of a Crowd of Brains: A Universal Brain Encoder
        33272, -- 2406.12723 BIOSCAN-5M: A Multimodal Dataset for Insect Biodiversity
        33760, -- 2406.18665 RouteLLM: Learning to Route LLMs with Preference Data
        33792, -- 2406.19223 T-FREE: Subword Tokenizer-Free Generative LLMs via Sparse Representati
        33843, -- 2406.19888 Fine-tuning of Geospatial Foundation Models for Aboveground Biomass Es
        33909, -- 2407.00648 LegalTurk Optimized BERT for Multi-Label Text Classification and NER
        33919, -- 2407.00818 Image Classification for Snow Detection to Improve Pedestrian Safety
        34026, -- 2407.02156 Towards Training Music Taggers on Synthetic Data
        34178, -- 2407.04158 ELCC: the Emergent Language Corpus Collection
        34189, -- 2407.04325 Understanding the Role of Invariance in Transfer Learning
        34379, -- 2407.06950 Spanish TrOCR: Leveraging Transfer Learning for Language Adaptation
        34420, -- 2407.07523 SHERL: Synthesizing High Accuracy and Efficient Memory for Resource-Li
        34989, -- 2407.14757 Enhancing Skin Disease Classification Leveraging Transformer-based Dee
        35190, -- 2407.17904 Exploring the Effect of Dataset Diversity in Self-Supervised Learning
        35341, -- 2407.20798 Diffusion Augmented Agents: A Framework for Efficient Exploration and
        35397, -- 2408.00002 Transfer Learning for Wildlife Classification: Evaluating YOLOv8 again
        35468, -- 2408.00981 Cross-domain Named Entity Recognition via Graph Matching
        35503, -- 2408.01527 Using LLMs to Establish Implicit User Sentiment of Software Desirabili
        35605, -- 2408.03322 Segment Anything in Medical Images and Videos: Benchmark and Deploymen
        35607, -- 2408.03326 LLaVA-OneVision: Easy Visual Task Transfer
        35610, -- 2408.03351 Quantum Transfer Learning for MNIST Classification Using a Hybrid Quan
        35664, -- 2408.04498 Model-Based Transfer Learning for Contextual Reinforcement Learning
        35706, -- 2408.05178 ECG-FM: An Open Electrocardiogram Foundation Model
        35813, -- 2408.07079 Anatomical Foundation Models for Brain MRIs
        35943, -- 2408.09441 CLIP-CID: Efficient CLIP Distillation via Cluster-Instance Discriminat
        36066, -- 2408.11294 RedWhale: An Adapted Korean LLM Through Efficient Continual Pretrainin
        36165, -- 2408.12837 Underwater SONAR Image Classification and Analysis using LIME-based Ex
        36246, -- 2408.14494 Knowledge Graph Modeling-Driven Large Language Model Operating System
        36878, -- 2409.09305 The T05 System for The VoiceMOS Challenge 2024: Transfer Learning from
        37264, -- 2409.15879 Machine Translation Advancements of Low-Resource Indian Languages by T
        37352, -- 2409.17481 MaskLLM: Learnable Semi-Structured Sparsity for Large Language Models
        37452, -- 2409.19075 Meta-RTL: Reinforcement-Based Meta-Transfer Learning for Low-Resource
        37747, -- 2410.02319 QDGset: A Large Scale Grasping Dataset Generated with Quality-Diversit
        38585, -- 2410.12183 TransAgent: Transfer Vision-Language Foundation Models with Heterogene
        38604, -- 2410.12391 Tracking Universal Features Through Fine-Tuning and Model Merging
        38859, -- 2410.15148 Less is More: Parameter-Efficient Selection of Intermediate Tasks for
        39205, -- 2410.19898 A Review of Deep Learning Approaches for Non-Invasive Cognitive Impair
        39361, -- 2410.22490 The PV-ALE Dataset: Enhancing Apple Leaf Disease Classification Throug
        40006, -- 2411.09539 A Practical Guide to Fine-tuning Language Models with Limited Data
        40142, -- 2411.12008 Compression of Higher Order Ambisonics with Multichannel RVQGAN
        40263, -- 2411.14393 POS-tagging to highlight the skeletal structure of sentences
        40281, -- 2411.14525 SegBook: A Simple Baseline and Cookbook for Volumetric Medical Image S
        40453, -- 2411.16725 $\textit{Revelio}$: Interpreting and leveraging semantic information i
        40561, -- 2411.17870 Breast Tumor Classification Using EfficientNet Deep Learning Model
        40568, -- 2411.18021 Can bidirectional encoder become the ultimate winner for downstream ap
        41099, -- 2412.04616 Assessing and Learning Alignment of Unimodal Vision and Language Model
        41339, -- 2412.07771 PETALface: Parameter Efficient Transfer Learning for Low-resolution Fa
        41437, -- 2412.09084 Evaluating Pixel Language Models on Non-Standardized Languages
        41704, -- 2412.12143 Harnessing Transfer Learning from Swahili: Advancing Solutions for Com
        41834, -- 2412.13924 Language verY Rare for All
        42320, -- 2501.00057 VisTabNet: Adapting Vision Transformers for Tabular Data
        42539, -- 2501.03176 Scalable Forward-Forward Algorithm
        42576, -- 2501.03863 Improving Dialectal Slot and Intent Detection with Auxiliary Tasks: A
        42649, -- 2501.04969 AD-L-JEPA: Self-Supervised Spatial World Models with Joint Embedding P
        42858, -- 2501.08580 Densely Connected Parameter-Efficient Tuning for Referring Image Segme
        42878, -- 2501.08912 Empowering Agricultural Insights: RiceLeafBD - A Novel Dataset and Opt
        43011, -- 2501.11196 Enhancing Brain Tumor Segmentation Using Channel Attention and Transfe
        43133, -- 2501.13354 NUDT4MSTAR: A Large Dataset and Benchmark Towards Remote Sensing Objec
        43191, -- 2501.14279 Deep Learning-Powered Classification of Thoracic Diseases in Chest X-R
        43266, -- 2501.15510 Universal Image Restoration Pre-training via Degradation Classificatio
        43268, -- 2501.15547 Building Efficient Lightweight CNN Models
        43322, -- 2501.16652 Molecular-driven Foundation Model for Oncologic Pathology
        43609, -- 2502.01861 Learning Hyperparameters via a Data-Emphasized Variational Objective
        43611, -- 2502.01890 Geometric Framework for Cell Oversegmentation
        43894, -- 2502.05931 Protecting Intellectual Property of EEG-based Neural Networks with Wat
        43912, -- 2502.06171 A Data-Efficient Pan-Tumor Foundation Model for Oncology CT Interpreta
        43925, -- 2502.06374 Hyperparameters in Score-Based Membership Inference Attacks
        43985, -- 2502.06970 Model Diffusion for Certifiable Few-shot Transfer Learning
        44089, -- 2502.08347 Hi-End-MAE: Hierarchical encoder-driven masked autoencoders are strong
        44374, -- 2502.11824 M-ABSA: A Multilingual Dataset for Aspect-Based Sentiment Analysis
        44469, -- 2502.12638 NExT-Mol: 3D Diffusion Meets 1D Language Modeling for 3D Molecule Gene
        44492, -- 2502.12930 Universal Embedding Function for Traffic Classification via QUIC Domai
        44524, -- 2502.13142 Pre-training Auto-regressive Robotic Models with 4D Representations
        44850, -- 2502.16622 Diagnosing COVID-19 Severity from Chest X-Ray Images Using ViT and CNN
        45227, -- 2502.21263 RuCCoD: Towards Automated ICD Coding in Russian
        45469, -- 2503.03205 MA-LoT: Multi-Agent Lean-based Long Chain-of-Thought Reasoning enhance
        45508, -- 2503.03773 A Phylogenetic Approach to Genomic Language Modeling
        45516, -- 2503.03962 On the Acquisition of Shared Grammatical Representations in Bilingual
        45578, -- 2503.04872 TinyR1-32B-Preview: Boosting Accuracy with Branch-Merge Distillation
        45617, -- 2503.05349 Spatial Distillation based Distribution Alignment (SDDA) for Cross-Hea
        45627, -- 2503.05604 CACTUS: An Open Dataset and Framework for Automated Cardiac Assessment
        45637, -- 2503.05750 CSTRL: Context-Driven Sequential Transfer Learning for Abstractive Rad
        45881, -- 2503.08497 MMRL: Multi-Modal Representation Learning for Vision-Language Models
        46761, -- 2503.20000 The Coralscapes Dataset: Semantic Scene Understanding in Coral Reefs
        46854, -- 2503.21530 Low-Resource Transliteration for Roman-Urdu and Urdu Using Transformer
        47192, -- 2504.02012 Instruction-Guided Autoregressive Neural Network Parameter Generation
        47398, -- 2504.05565 Cross-functional transferability in universal machine learning interat
        47484, -- 2504.07426 Conditional Data Synthesis Augmentation
        47554, -- 2504.08568 Banana Ripeness Level Classification using a Simple CNN Model Trained
        47761, -- 2504.11581 Towards a Universal Vibration Analysis Dataset: A Framework for Transf
        47900, -- 2504.13648 Enhancing Pothole Detection and Characterization: Integrated Segmentat
        47905, -- 2504.13820 CheXWorld: Exploring Image World Modeling for Radiograph Representatio
        48308, -- 2505.00534 A Robust Deep Networks based Multi-Object MultiCamera Tracking System
        48722, -- 2505.09358 Marigold: Affordable Adaptation of Diffusion-Based Image Generators fo
        48757, -- 2505.10088 MMRL++: Parameter-Efficient and Interaction-Aware Representation Learn
        49226, -- 2505.14725 HR-VILAGE-3K3M: A Human Respiratory Viral Immunization Longitudinal Ge
        49576, -- 2505.18125 TabSTAR: A Foundation Tabular Model With Semantically Target-Aware   R
        49603, -- 2505.18355 X-MethaneWet: A Cross-scale Global Wetland Methane Emission Benchmark
        50150, -- 2505.23745 To Trust Or Not To Trust Your Vision-Language Model's Prediction
        50305, -- 2506.00381 Neuro2Semantic: A Transfer Learning Framework for Semantic Reconstruct
        50898, -- 2506.09022 Do MIL Models Transfer?
        50910, -- 2506.09161 An Explainable Deep Learning Framework for Brain Stroke and Tumor Prog
        52094, -- 2507.21364 Evaluating Deep Learning Models for African Wildlife Image   Classific
        53096, -- 2509.22889 Convolutional Set Transformer
        55882, -- 2602.06883 Vision Transformer Finetuning Benefits from Non-Smooth Components
        56353, -- 2602.18253 MEG-to-MEG Transfer Learning and Cross-Task Speech/Silence Detection w
        56417, -- 2602.24121 Planning from Observation and Interaction
        57492, -- 2604.14004 Memory Transfer Learning: How Memories are Transferred Across Domains
        57751, -- 2604.23099 ProEval: Proactive Failure Discovery and Efficient Performance Estimat
        57901, -- 2604.22723 Zero-Shot Morphological Discovery in Low-Resource Bantu Languages via
        57958, -- 2604.20813 Adapting TrOCR for Printed Tigrinya Text Recognition: Word-Aware Loss
        57964, -- 2604.20615 Semi supervised GAN for smart microscopy, fast and data efficient cell
        58674, -- 2604.00686 Full-Gradient Successor Feature Representations
        58841, -- 2603.26597 From Static to Dynamic: Exploring Self-supervised Image-to-Video Repre
        58877, -- 2603.25351 Image Rotation Angle Estimation: Comparing Circular-Aware Methods
        58996, -- 2603.22985 Beyond Hate: Differentiating Uncivil and Intolerant Speech in Multimod
        59380, -- 2603.14563 Multilingual TinyStories: A Synthetic Combinatorial Corpus of Indic Ch
        60031, -- 2603.01879 Diagnosing Generalization Failures from Representational Geometry Mark
        60278, -- 2602.21905 TIRAuxCloud: A Thermal Infrared Dataset for Day and Night Cloud Detect
        60407, -- 2512.21390 GraviBERT: Transformer-based inference for gravitational-wave time ser
        60518, -- 2602.16811 Evaluating Monolingual and Multilingual Large Language Models for Gree
        60689, -- 2505.11771 Residual Feature Integration is Sufficient to Prevent Negative Transfe
        60906, -- 2602.10168 EVA: Towards a universal model of the immune system
        61888, -- 2601.20845 PatchFormer: A Patch-Based Time Series Foundation Model with Hierarchi
        62776, -- 2601.05052 DeepWeightFlow: Re-Basined Flow Matching for Generating Neural Network
        63134, -- 2601.00355 The Impact of Lesion Focus on the Performance of AI-Based Melanoma Cla
        63298, -- 2601.09719 Bounded Hyperbolic Tangent: A Stable and Efficient Alternative to Pre-
        63378, -- 2512.22243 Predicting Mycotoxin Contamination in Irish Oats Using Deep and Transf
        63795, -- 2512.11360 Reliable Detection of Minute Targets in High-Resolution Aerial Imagery
        63838, -- 2512.10608 Robust Multi-Disease Retinal Classification via Xception-Based Transfe
        64444, -- 2511.22095 Binary-30K: A Heterogeneous Dataset for Deep Learning in Binary Analys
        64981, -- 2511.12048 DeiTFake: Deepfake Detection Model using DeiT Multi-Stage Training
        65175, -- 2511.08156 LandSegmenter: Towards a Flexible Foundation Model for Land Use and La
        65649, -- 2510.26100 Applications of Machine Learning in Polymer Materials: Property Predic
        65694, -- 2511.01892 Retrieval-Augmented Multimodal Depression Detection
        66085, -- 2510.18725 SemiAdapt and SemiLoRA: Efficient Domain Adaptation for   Transformer-
        66465, -- 2510.12085 GraphShaper: Geometry-aware Alignment for Improving Transfer Learning
        66549, -- 2510.10671 Image-to-Video Transfer Learning based on Image-Language Foundation Mo
        66752, -- 2510.07773 Trajectory Conditioned Cross-embodiment Skill Transfer
        66790, -- 2510.07191 Resolution scaling governs DINOv3 transfer performance in chest radiog
        67197, -- 2510.00902 Intuitions of Machine Learning Researchers about Transfer Learning for
        67862, -- 2509.20209 Low-Resource English-Tigrinya MT: Leveraging Multilingual Models, Cust
        67884, -- 2509.19941 CorIL: Towards Enriching Indian Language to Indian Language Parallel
        68016, -- 2509.22701 Enhancing Cluster Scheduling in HPC: A Continuous Transfer Learning fo
        68416, -- 2509.11273 Synthetic Dataset Evaluation Based on Generalized Cross Validation
        68497, -- 2509.09303 From scratch to silver: Creating trustworthy training data for patent-
        68597, -- 2509.07202 Neurocognitive Modeling for Text Generation: Deep Learning Architectur
        68615, -- 2509.06831 Leveraging Generic Foundation Models for Multimodal Surgical Data   An
        68630, -- 2509.06516 QualityFM: a Multimodal Physiological Signal Foundation Model with Sel
        68975, -- 2509.00226 GraViT: Transfer Learning with Vision Transformers and MLP-Mixer for
        69131, -- 2508.19353 Efficient Multi-Source Knowledge Transfer by Model Merging
        69278, -- 2508.17107 SugarcaneShuffleNet: A Very Fast, Lightweight Convolutional Neural   N
        69521, -- 2508.13028 Integrating Feedback Loss from Bi-modal Sarcasm Detector for Sarcastic
        69530, -- 2508.12861 Cross-Domain Few-Shot Learning via Multi-View Collaborative Optimizati
        69687, -- 2508.10360 A dataset and model for recognition of audiologically relevant   envir
        69914, -- 2508.07295 CCFQA: A Benchmark for Cross-Lingual and Cross-Modal Speech and Text
        70088, -- 2508.04665 Perch 2.0: The Bittern Lesson for Bioacoustics
        70328, -- 2508.01772 LoRA-based methods on Unet for transfer learning in Subarachnoid   Hem
        70491, -- 2507.23358 Text-to-SQL Task-oriented Dialogue Ontology Construction
        70692, -- 2507.19878 Efficient Self-Supervised Neuro-Analytic Visual Servoing for Real-time
        70859, -- 2507.16922 A Unifying Scheme for Extractive Content Selection Tasks
        70949, -- 2507.15142 A Case Against Implicit Standards: Homophone Normalization in Machine
        70985, -- 2507.14613 Depthwise-Dilated Convolutional Adapters for Medical Object Tracking a
        71005, -- 2507.14334 Language Models as Ontology Encoders
        71342, -- 2507.05764 PSAT: Pediatric Segmentation Approaches via Adult Augmentations and Tr
        71396, -- 2505.13860 Domain Adaptation of VLM for Soccer Video Understanding
        71442, -- 2507.03578 SciVid: Cross-Domain Evaluation of Video Models in Scientific   Applic
        71588, -- 2507.00297 Natural language processing for African languages
        71622, -- 2506.23605 AI-Generated Lecture Slides for Improving Slide Element Detection and
        71646, -- 2506.23210 FedRef: Communication-Efficient Bayesian Fine-Tuning using a Reference
        71764, -- 2507.01045 Sensing Cardiac Health Across Scenarios and Devices: A Multi-Modal   F
        72049, -- 2506.11170 PromptTSS: A Prompting-Based Approach for Interactive Multi-Granularit
        72078, -- 2506.21803 From Token to Rhythm: A Multi-Scale Approach for ECG-Language   Pretra
        72134, -- 2506.07619 The Catechol Benchmark: Time-series Solvent Selection Data for Few-sho
        72327, -- 2506.02916 Towards Transfer-Efficient Multi-modal Sequential Recommendation with
        72332, -- 2506.02866 MVTD: A Benchmark Dataset for Maritime Visual Object Tracking
        72476, -- 2506.03193 Human Fall Detection using Transfer Learning-based 3D CNN
        72853, -- 2505.16635 WikiDBGraph: Large-Scale Database Graph of Wikidata for Collaborative
        73259, -- 2504.21066 A Brief Review for Compression and Transfer Learning Techniques in   D
        73335, -- 2504.18072 A Model Zoo on Phase Transitions in Neural Networks
        73405, -- 2504.16140 SparseJEPA: Sparse Representation Learning of Joint Embedding Predicti
        73413, -- 2504.16136 Active Learning Methods for Efficient Data Utilization and Model   Per
        73561, -- 2504.08584 Boosting multi-demographic federated learning for chest radiograph ana
        73617, -- 2504.06559 TabKAN: Advancing Tabular Data Analysis using Kolmogorov-Arnold Networ
        73697, -- 2504.04271 ADA-Net: Attention-Guided Domain Adaptation Network with Contrastive
        73874, -- 2503.19945 Optimizing Breast Cancer Detection in Mammograms: A Comprehensive Stud
        73943, -- 2503.16784 Multi-property directed generative design of inorganic materials throu
        73975, -- 2504.02839 PETIMOT: A Novel Framework for Inferring Protein Motions from Sparse D
        74037, -- 2503.13560 MSWAL: 3D Multi-class Segmentation of Whole Abdominal Lesions Dataset
        74080, -- 2503.12099 Automatic Characterization of Fluxonium Superconducting Qubits Paramet
        74123, -- 2503.09850 TabNSA: Native Sparse Attention for Efficient Tabular Data Learning
        74168, -- 2503.08154 S2A: A Unified Framework for Parameter and Memory Efficient Transfer
        74189, -- 2503.07821 Elderly Activity Recognition in the Wild: Results from the EAR Challen
        74230, -- 2503.05431 Quantum-PEFT: Ultra parameter-efficient fine-tuning
        74354, -- 2503.04797 Parallel Corpora for Machine Translation in Low-resource Indic   Langu
        74850, -- 2502.04883 Evaluating Standard and Dialectal Frisian ASR: Multilingual Fine-tunin
        74855, -- 2501.12983 LLM4WM: Adapting LLM for Wireless Multi-Tasking
        74913, -- 2502.02722 Cross-Lingual Transfer for Low-Resource Natural Language Processing
        74961, -- 2502.01102 Towards Robust and Generalizable Lensless Imaging with Modular Learned
        74978, -- 2502.00806 UniGraph2: Learning a Unified Embedding Space to Bind Multimodal Graph
        75011, -- 2502.00315 MonoDINO-DETR: Depth-Enhanced Monocular 3D Object Detection Using a
        75033, -- 2502.01654 Predicting concentration levels of air pollutants by transfer learning
        75391, -- 2412.15966 Monkey Transfer Learning Can Improve Human Pose Estimation
        75420, -- 2412.14449 Color Enhancement for V-PCC Compressed Point Cloud via 2D Attribute Ma
        75455, -- 2412.11967 A Digital Twin for Diesel Engines: Operator-infused Physics-Informed
        75722, -- 2411.15923 Deep Learning for automated multi-scale functional field boundaries ex
        75811, -- 2411.08785 Zero-shot Cross-lingual Transfer Learning with Multiple Source and Tar
        75845, -- 2411.04644 wav2sleep: A Unified Multi-Modal Approach to Sleep Stage Classificatio
        76041, -- 2410.12082 Learning to rumble: Automated elephant call classification, detection
        76203, -- 2410.13867 Self-Supervised Pre-Training with Joint-Embedding Predictive   Archite
        76354, -- 2409.11862 Location based Probabilistic Load Forecasting of EV Charging Sites: De
        76836, -- 2407.02277 MelodyT5: A Unified Score-to-Score Transformer for Symbolic Music   Pr
        76987, -- 2406.10973 ExPLoRA: Parameter-Efficient Extended Pre-Training to Adapt Vision Tra
        76995, -- 2406.11903 A Survey of Large Language Models for Financial Applications: Progress
        77079, -- 2406.03725 LLMEmbed: Rethinking Lightweight LLM's Genuine Function in Text Classi
        77089, -- 2406.02806 Randomized Geometric Algebra Methods for Convex Neural Networks
        77117, -- 2406.00773 Diffusion Tuning: Transferring Diffusion Models via Chain of Forgettin
        77162, -- 2405.18585 Transfer Learning for Emulating Ocean Climate Variability across CO_2
        77240, -- 2405.12972 Accelerating Resonance Searches via Signature-Oriented Pre-training
        77368, -- 2404.16436 Leveraging tropical reef, bird and unrelated sounds for superior trans
        77509, -- 2404.02235 Is Exploration All You Need? Effective Exploration Characteristics for
        77604, -- 2403.13602 Bayesian Physics-informed Neural Networks for System Identification of
        77699, -- 2403.02484 Encodings for Prediction-based Neural Architecture Search
        77702, -- 2403.02138 Self-Supervised Facial Representation Learning with Facial Region Awar
        77817, -- 2402.08184 Enabling Multi-Agent Transfer Reinforcement Learning via Scenario Inde
        77857, -- 2402.02242 Parameter-Efficient Fine-Tuning for Pre-Trained Vision Models: A Surve
        78111, -- 2312.07723 Automated Behavioral Analysis Using Instance Segmentation
        78149, -- 2312.03503 Transfer learning for galaxy feature detection: Finding Giant   Star-f
        78384, -- 2310.08782 Selectivity Drives Productivity: Efficient Dataset Pruning for Enhance
        78503, -- 2309.11202 Using Artificial Intelligence for the Automation of Knitting Patterns
        78573, -- 2309.00862 Big-model Driven Few-shot Continual Learning
        78631, -- 2308.09945 Dual Branch Deep Learning Network for Detection and Stage Grading of D
        78785, -- 2304.04000 SimbaML: Connecting Mechanistic Models and Machine Learning with Augme
        78808, -- 2307.01310 Leveraging Cross-Lingual Transfer Learning in Spoken Named Entity Reco
        78919, -- 2306.05432 Towards End-to-end Speech-to-text Summarization
        78954, -- 2305.18977 Cross Encoding as Augmentation: Towards Effective Educational Text Cla
        78969, -- 2305.17473 A Comprehensive Overview and Comparative Analysis on Deep Learning Mod
        78992, -- 2305.15036 Exploring Adapter-based Transfer Learning for Recommender Systems: Emp
        79089, -- 2304.14065 Lightweight, Pre-trained Transformers for Remote Sensing Timeseries
        79120, -- 2304.09715 UniCal: a Single-Branch Transformer-Based Model for Camera-to-LiDAR Ca
        79158, -- 2304.03509 Local Rose Breeds Detection System Using Transfer Learning Techniques
        79352, -- 2302.08797 Deep comparisons of Neural Networks from the EEGNet family
        79353, -- 2302.08747 Seismic Arrival-time Picking on Distributed Acoustic Sensing Data usin
        79354, -- 2302.08427 Learning to diagnose cirrhosis from radiological and histological labe
        79467, -- 2212.12645 HandsOff: Labeled Dataset Generation With No Additional Human Annotati
        79699, -- 2210.09290 Automated Identification of Tree Species by Bark Texture Classificatio
        79779, -- 2208.10448 Dialogue Term Extraction using Transfer Learning and Topological Data
        79825, -- 2207.11808 ArmanEmo: A Persian Dataset for Text-based Emotion Detection
        79864, -- 2207.01084 Enhancing Automated Software Traceability by Transfer Learning from
        79890, -- 2206.08574 Using Transfer Learning for Code-Related Tasks
        79903, -- 2206.05683 APT-36K: A Large-scale Benchmark for Animal Pose Estimation and Tracki
        79988, -- 2205.05940 SimCPSR: Simple Contrastive Learning for Paper Submission Recommendati
        80029, -- 2202.05735 SleepPPG-Net: a deep learning algorithm for robust sleep staging from
        80218, -- 2202.03844 EvoPruneDeepTL: An Evolutionary Pruning Model for Transfer Learning ba
        80376, -- 2111.12071 Minimizing subject-dependent calibration for BCI with Riemannian trans
        80479, -- 2110.01606 Breast Cancer Diagnosis in Two-View Mammography Using End-to-End Train
        80596, -- 2107.12135 Fine-Grained Emotion Prediction by Modeling Emotion Definitions
        80711, -- 2105.11021 Multi-Type-TD-TSR -- Extracting Tables from Document Images using a
        80712, -- 2105.09880 DeepDarts: Modeling Keypoints as Objects for Automatic Scorekeeping in
        80793, -- 2104.01322 Learning the CSI Recovery in FDD Systems
        80890, -- 2102.04411 Traceability Transformed: Generating more Accurate Links with   Pre-Tr
        80986, -- 2012.02096 Emergent Complexity and Zero-shot Transfer via Unsupervised Environmen
        81035, -- 2011.03443 Is Transfer Learning Necessary for Protein Landscape Prediction?
        81046, -- 2010.12885 Unsupervised Paraphrasing with Pretrained Language Models
        81158, -- 2008.09772 A Benchmark for Studying Diabetic Retinopathy: Segmentation, Grading,
        81234, -- 2007.00144 A Sequential Self Teaching Approach for Improving Generalization in
        81257, -- 2006.09950 Delta Schema Network in Model-based Reinforcement Learning
        81267, -- 2006.06494 Anti-Transfer Learning for Task Invariance in Convolutional Neural Net
        81322, -- 2005.04473 Visually Impaired Aid using Convolutional Neural Networks, Transfer Le
        81330, -- 1909.04422 The Mapillary Traffic Sign Dataset for Detection and Classification on
        81353, -- 2005.02165 AutoTune: Automatically Tuning Convolutional Neural Networks for Impro
        81357, -- 2004.10746 Chip Placement with Deep Reinforcement Learning
        81376, -- 2004.05405 Unveiling COVID-19 from Chest X-ray with deep learning: a hurdles race
        81411, -- 2003.07820 Overview of the TREC 2019 deep learning track
        81421, -- 2003.11523 Tigrinya Neural Machine Translation with Transfer Learning for Humanit
        81435, -- 2002.11656 Inceptive Event Time-Surfaces for Object Classification Using Neuromor
        81477, -- 2001.01469 TableNet: Deep Learning model for end-to-end Table detection and Tabul
        81489, -- 1912.12378 Deep neural network models for computational histopathology: A survey
        81525, -- 1911.09659 AdaFilter: Adaptive Filter Fine-tuning for Deep Transfer Learning
        81551, -- 1911.05479 Decoding Neural Responses in Mouse Visual Cortex through a Deep Neural
        81597, -- 1909.10086 Learning Universal Graph Neural Network Embeddings With Aid Of Transfe
        81771, -- 1904.02420 Transfer Learning with Sparse Associative Memories
        81795, -- 1903.03178 Transfer Learning Using Ensemble Neural Networks for Organic Solar Cel
        81832, -- 1901.04772 Transfer Learning for Prosthetics Using Imitation Learning
        81872, -- 1811.05660 MT-CGCNN: Integrating Crystal Graph Convolutional Neural Network with
        81940, -- 1808.07931 Financial Aspect-Based Sentiment Analysis using Deep Representations
        81981, -- 1806.08908 Zeta Distribution and Transfer Learning Problem
        82024, -- 1805.02283 DocFace: Matching ID Document Photos to Selfies
        82155, -- 1711.01369 Knowledge Transfer from Weakly Labeled Audio using Convolutional Neura
        82186, -- 1709.04305 Automated Cloud Provisioning on AWS using Deep Reinforcement Learning
        83982, -- 2502.01117 Learning to Learn Weight Generation via Local Consistency Diffusion
        85329, -- 2604.09088 Memory-Efficient Transfer Learning with Fading Side Networks via Maske
        85523, -- 2605.07256 TAS-LoRA: Transformer Architecture Search with Mixture-of-LoRA Experts
        85751, -- 2505.01281 A Physics-preserved Transfer Learning Method for Differential Equation
        86015, -- 2510.01248 SSTAG: Structure-Aware Self-Supervised Learning Method for Text-Attrib
        86042, -- 2502.04491 Provable Sample-Efficient Transfer Learning Conditional Diffusion Mode
        86272, -- 2506.01728 Principled data augmentation for learning to solve quadratic programmi
        86308, -- 2505.17203 Transfer Faster, Price Smarter: Minimax Dynamic Pricing under Cross-Ma
        86380, -- 2506.09714 Auto-Compressing Networks
        86439, -- 2502.04242 A High-Dimensional Statistical Method for Optimizing Transfer Quantiti
        86463, -- 2402.06674 Impact of Dataset Properties on Membership Inference Vulnerability of
        86487, -- 2509.11711 The Quest for Universal Master Key Filters in DS-CNNs
        86507, -- 2505.16217 Reward-Aware Proto-Representations in Reinforcement Learning
        86524, -- 2505.17404 Wasserstein Transfer Learning
        86600, -- 2507.04194 Mixed-Sample SGD: an End-to-end Analysis of Supervised Transfer Learni
        86617, -- 2505.16130 Scalable Graph Generative Modeling via Substructure Sequences
        86917, -- 2510.05527 Transfer Learning on Edge Connecting Probability Estimation Under Grap
        86930, -- 2510.15337 Transfer Learning for Benign Overfitting in High-Dimensional Linear Re
        87056, -- 2510.14810 Rethinking Hebbian Principle: Low-Dimensional Structural Projection fo
        87137, -- 2506.07085 State Entropy Regularization for Robust Reinforcement Learning
        87200, -- 2506.07413 Variational Supervised Contrastive Learning
        87274, -- 2505.14125 Contrastive Consolidation of Top-Down Modulations Achieves Sparsely Su
        87536, -- 2605.28229 VidPrism: Heterogeneous Mixture of Experts for Image-to-Video Transfer
        87870, -- 2503.11328 TransiT: Transient Transformer for Non-line-of-sight Videography
        88047, -- 2508.03742 Boosting Vision Semantic Density with Anatomy Normality Modeling for M
        88095, -- 2507.14449 IRGPT: Understanding Real-world Infrared Image with Bi-cross-modal Cur
        88144, -- 2503.15877 Repurposing 2D Diffusion Models with Gaussian Atlas for 3D Generation
        88333, -- 2503.06361 Adversarial Robustness of Discriminative Self-Supervised Learning in V
        88560, -- 2506.07534 Flowing Datasets with Wasserstein over Wasserstein Gradient Flows
        88640, -- 2506.00424 COGNATE: Acceleration of Sparse Tensor Programs on Emerging Hardware u
        88846, -- 2410.08194 Features are fate: a theory of transfer learning in high-dimensional r
        89029, -- 2406.04824 FunBO: Discovering Acquisition Functions for Bayesian Optimization wit
        89248, -- 2507.05502 Predicting mutational effects on protein binding from folding energy
        89317, -- 2503.00174 Optimal Transfer Learning for Missing Not-at-Random Matrix Completion
        89413, -- 2411.19230 Pre-Training Graph Contrastive Masked Autoencoders are Strong Distille
        89415, -- 2501.18901 Lightspeed Geometric Dataset Distance via Sliced Optimal Transport
        89453, -- 2506.14329 Adjustment for Confounding using Pre-Trained Representations
        89531, -- 2502.08146 Knowledge-Guided Wasserstein Distributionally Robust Optimization
        89585, -- 2501.18373 Function Encoders: A Principled Approach to Transfer Learning in Hilbe
        89622, -- 2501.18836 Transfer Learning for Nonparametric Contextual Dynamic Pricing
        89778, -- 2505.18447 Pessimism Principle Can Be Effective: Towards a Framework for Zero-Sho
        89821, -- 2502.19255 Can RLHF be More Efficient with Imperfect Reward Models? A Policy Cove
        89855, -- 2406.09546 QMamba: On First Exploration of Vision Mamba for Image Quality Assessm
        89869, -- 2502.10691 Controlling Neural Collapse Enhances Out-of-Distribution Detection and
        90043, -- 2502.16849 Provable Benefits of Unsupervised Pre-training and Transfer Learning v
        90265, -- 2411.19041 TAMT: Temporal-Aware Model Tuning for Cross-Domain Few-Shot Action Rec
        90455, -- 2411.17332 On the Generalization of Handwritten Text Recognition Models
        90665, -- 2501.04293 TADFormer: Task-Adaptive Dynamic TransFormer for Efficient Multi-Task
        90704, -- 2411.11223 Efficient Transfer Learning for Video-language Foundation Models
        90783, -- 2411.15224 Parameter Efficient Mamba Tuning via Projector-targeted Diagonal-centr
        90989, -- 2503.15019 Learning 4D Panoptic Scene Graph Generation from Rich 2D Visual Scene
        91013, -- 2412.20047 SimLTD: Simple Supervised and Semi-Supervised Long-Tailed Object Detec
        91416, -- 2502.19252 GraphBridge: Towards Arbitrary Transfer Learning in GNNs
        91719, -- 2411.17201 Learning Hierarchical Polynomials of Multiple Nonlinear Features
        91789, -- 2405.16236 A transfer learning framework for weak to strong generalization
        91896, -- 2406.15079 GOAL: A Generalist Combinatorial Optimization Agent Learner
        92047, -- 2410.04814 Learning Interpretable Hierarchical Dynamical Systems Models from Time
        92083, -- 2409.14623 From Lazy to Rich: Exact Learning Dynamics in Deep Linear Networks
        92086, -- 2402.04676 Group Distributionally Robust Dataset Distillation with Risk Minimizat
        92446, -- 2502.07547 Instance-dependent Early Stopping
        92576, -- 2606.00558 Semi-Supervised Noise Adaptation: Transferring Knowledge from Noise Do
        92638, -- 2510.19675 Study of Training Dynamics for Memory-Constrained Fine-Tuning
        92915, -- 2511.06641 Neyman-Pearson Classification under Both Null and Alternative Distribu
        92968, -- 2507.04448 Transfer Learning in Infinite Width Feature Learning Networks
        93076, -- 2502.08416 Multifidelity Simulation-based Inference for Computationally Expensive
        93125, -- 2603.19486 Any-Subgroup Equivariant Networks via Symmetry Breaking
        93615, -- 2505.23933 BIRD: Behavior Induction via Representation-structure Distillation
        93979, -- 2507.17725 On the Interaction of Compressibility and Adversarial Robustness
        93984, -- 2510.20616 On Optimal Hyperparameters for Differentially Private Deep Transfer Le
        94450, -- 2508.12877 Preserve and Sculpt: Manifold-Aligned Fine-tuning of Vision-Language M
        95017, -- 2601.21251 Abstracting Robot Manipulation Skills via Mixture-of-Experts Diffusion
        96284, -- external SF-ODNav: Successor Feature Framework for Map-Less Target-Driven Outdo
        96433, -- external Neuromorphic Event Camera-Based Object Recognition and Grasping Positi
        96853, -- 2312.09436 Temporal Transfer Learning for Traffic Optimization with Coarse-Graine
        97508, -- 2509.09747 D-CAT: Decoupled Cross-Attention Knowledge Transfer between Sensor Mod
        97838, -- 2503.17501 Shear-Based Grasp Control for Multi-Fingered Underactuated Tactile Rob
        97991, -- 2602.03918 Entropy Reveals Block Importance in Masked Self-Supervised Vision Tran
        98359, -- 1811.07056 Domain Adaptive Transfer Learning with Specialist Models
        98637, -- 2012.09439 FG-Net: Fast Large-Scale LiDAR Point Clouds Understanding Network Leve
        98733, -- 2606.20886 Toward Parking Spot Occupancy Recognition: A Self-Supervised Approach
        99780, -- 2602.04328 Multiview Self-Representation Learning across Heterogeneous Views
        100238, -- 2512.11089 TPV: Parameter Perturbations Through the Lens of Test Prediction Varia
        100283, -- 2605.01452 Stable Localized Conformal Prediction via Transduction
        100978, -- 2605.20302 Neural Collapse by Design: Learning Class Prototypes on the Hyperspher
        101226, -- 2506.13015 Geometric Embedding Alignment via Curvature Matching in Transfer Learn
        101985, -- 2506.14126 From Memorization to Parameter Interference: How Overtraining Experts
        102100, -- 2512.00239 Self-Supervised Dynamical System Representations for Physiological Tim
        102286, -- 2605.15615 Neutral-Reference Prompting for Vision–Language Models
        102502, -- 2605.30997 Hedging on the Frontier: Learning New Tasks with Few Samples
        102744, -- 2402.10793 An end-to-end attention-based approach for learning on graphs
        103785, -- 2603.25222 Translation or Recitation? Calibrating Evaluation Scores for Machine T
        104086, -- 2203.07910 Deep Transfer Learning with Graph Neural Network for Sensor-Based Huma
        104101, -- 2604.21369 Channel-Free Human Activity Recognition via Inductive-Bias-Aware Fusio
        104103, -- 2505.04907 VaCDA: Variational Contrastive Alignment-based Scalable Human Activity
        104141, -- 1611.09813 Monocular 3D Human Pose Estimation In The Wild Using Improved CNN Supe
        104144, -- 1704.02447 Towards 3D Human Pose Estimation in the Wild: a Weakly-supervised Appr
        104258, -- 2206.05514 Toward Real-world Single Image Deraining: A New Benchmark and Beyond
        104270, -- external Automated Cervical Cancer Detection Using Feature-Fused Deep CNNs and
        104616, -- 2103.00119 ASMNet: a Lightweight Deep Neural Network for Face Alignment and Pose
        104970, -- 2505.10579 Bias and Generalizability of Foundation Models across Datasets in Brea
        104986, -- external Brain-Environment Cross-Attention (BECA) Meta-Matching: A New Perspect
        105008, -- external CAUDA-MI: Cross Attention-Guided Unsupervised Domain Adaptation with M
        105231, -- 2506.19552 General Methods Make Great Domain-specific Foundation Models: A Case-s
        105402, -- 2504.15865 MedNNS: Supernet-based Medical Task-Adaptive Neural Network Search
        105728, -- 2501.02227 tCURLoRA: Tensor CUR Decomposition Based Low-Rank Parameter Adaptation
        105773, -- 2506.17503 Trustworthy Few-Shot Transfer of Medical VLMs through Split Conformal
        105898, -- 2206.04325 CFA: Coupled-hypersphere-based Feature Adaptation for Target-Oriented
        106901, -- 2603.06186 SpaCRD: Multimodal Deep Fusion of Histology and Spatial Transcriptomic
        106971, -- 2603.01816 Voices, Faces, and Feelings: Multi-modal Emotion-Cognition Captioning
        107629, -- 2605.04058 MP-ISMoE: Mixed-Precision Interactive Side Mixture-of-Experts for Effi
        107663, -- 2512.06811 RMAdapter: Reconstruction-based Multi-Modal Adapter for Vision-Languag
        107815, -- 2601.08120 Structure Detection for Contextual Reinforcement Learning
        108225, -- 2410.09908 Beyond Adapter Retrieval: Latent Geometry-Preserving Composition via S
        108450, -- 2508.05685 DogFit: Domain-guided Fine-tuning for Efficient Transfer Learning of D
        109217, -- 2007.03347 SpinalNet: Deep Neural Network with Gradual Input
        109677, -- 2105.08913 Multiple Meta-model Quantifying for Medical Visual Question Answering
        110029, -- external Few-Shot Learning Translation from New Languages
        110599, -- 2506.05128 DiCoRe: Enhancing Zero-shot Event Detection via Divergent-Convergent L
        110699, -- 2510.03467 Searching for the Most Human-like Emergent Language
        110732, -- 2505.10481 Logos as a Well-Tempered Pre-train for Sign Language Recognition
        110920, -- 2505.14272 Data-Efficient Hate Speech Detection via Cross-Lingual Nearest Neighbo
        111226, -- external Whisper-Based Multilingual Alzheimer's Disease Detection and Improveme
        111231, -- external Towards atypical speech transcription using LLM-based ASR
        111495, -- external Evaluating Speech Foundation Models for Automatic Speech Recognition i
        111716, -- 2505.13079 Cross-modal Knowledge Transfer Learning as Graph Matching Based on Opt
        112539, -- 2408.00677 Scaling Backwards: Minimal Synthetic Pre-training?
        112617, -- external Improving Zero-Shot Generalization for CLIP with Variational Adapter
        112726, -- 2407.08156 AddressCLIP: Empowering Vision-Language Models for City-wide Image Add
        112803, -- 2403.17915 Leveraging Near-Field Lighting for Monocular Depth Estimation from End
        112883, -- 2408.16965 Contrastive Learning with Synthetic Positives
        112937, -- external Three Things We Need to Know About Transferring Stable Diffusion to Vi
        112962, -- 2311.11533 Event Camera Data Dense Pre-training
        112964, -- 2407.06871 Rethinking Image-to-Video Adaptation: An Object-centric Perspective
        112993, -- 2407.06964 Parameter-Efficient and Memory-Efficient Tuning for Vision Transformer
        113079, -- 2403.04697 AUFormer: Vision Transformers are Parameter-Efficient Facial Action Un
        113163, -- 2406.04898 Labeled Data Selection for Category Discovery
        113440, -- 2407.14302 Dyn-Adapter: Towards Disentangled Representation for Efficient Visual
        113441, -- external Physics-informed Knowledge Transfer for Underwater Monocular Depth Est
        113451, -- 2407.14330 Straightforward Layer-wise Pruning for More Efficient Visual Adaptatio
        113543, -- 2403.17869 To Supervise or Not to Supervise: Understanding and Addressing the Key
        113644, -- 2408.02014 Unsupervised Representation Learning by Balanced Self Attention Matchi
        113669, -- 2407.15648 TreeSBA: Tree-Transformer for Self-Supervised Sequential Brick Assembl
        113678, -- 2410.08015 Non-transferable Pruning
        114351, -- 2408.02001 AdaCBM: An Adaptive Concept Bottleneck Model for Explainable and Accur
        114386, -- 2407.13708 Are We Ready for Out-of-Distribution Detection in Digital Pathology?
        114395, -- 2408.15947 Auxiliary Input in Training: Incorporating Catheter Features into Deep
        114413, -- external BrainSCK: Brain Structure and Cognition Alignment via Knowledge Inject
        114855, -- 2405.15728 Disease-informed Adaptation of Vision-Language Models
        114943, -- 2403.07576 Fine-grained Prompt Tuning: A Parameter and Memory Efficient Transfer
        114944, -- 2403.13341 FissionFusion: Fast Geometric Generation and Hierarchical Souping for
        114995, -- 2403.05396 HistGen: Histopathology Report Generation via Local-Global Feature Enc
        115102, -- 2402.17725 MedContext: Learning Contextual Cues for Efficient Volumetric Medical
        115142, -- 2405.13771 Multi-Dataset Multi-Task Learning for COVID-19 Prognosis
        115235, -- external Real-world Visual Navigation for Cardiac Ultrasound View Planning
        115328, -- 2405.19346 Subject-Adaptive Transfer Learning Using Resting State EEG Signals for
        115365, -- 2407.07360 Towards a text-based quantitative and explainable histopathology image
        115531, -- 2403.17173 Task2Box: Box Embeddings for Modeling Asymmetric Task Relationships
        115568, -- 2403.01439 Dynamic Adapter Meets Prompt Tuning: Parameter-Efficient Transfer Lear
        115569, -- 2405.04771 Exploring Vision Transformers for 3D Human Motion-Language Models with
        115840, -- 2305.10300 One-Prompt to Segment All Medical Images
        115894, -- external Enhanced Motion-Text Alignment for Image-to-Video Transfer Learning
        115938, -- 2304.00553 From Isolated Islands to Pangea: Unifying Semantic Space for Human Act
        116037, -- external Evaluating Transferability in Retrieval Tasks: An Approach Using MMD a
        116164, -- 2404.07603 GLID: Pre-training a Generalist Encoder-Decoder Vision Model
        116349, -- 2401.04716 Low-Resource Vision Challenges for Foundation Models
        116421, -- 2312.12730 A Closer Look at the Few-Shot Adaptation of Large Vision-Language Mode
        116463, -- 2405.04115 A Stealthy Wrongdoer: Feature-Oriented Reconstruction Attack against S
        116556, -- 2301.07868 MV-Adapter: Multimodal Video Transfer Learning for Video Text Retrieva
        116649, -- 2403.09639 GroupContrast: Semantic-aware Self-supervised Representation Learning
        116722, -- external Structured Model Probing: Empowering Efficient Transfer Learning by St
        116946, -- 2404.05621 MULTIFLOW: Shifting Towards Task-Agnostic Vision-Language Pruning
        116992, -- 2306.02416 Training Like a Medical Resident: Context-Prior Learning Toward Univer
        116993, -- 2312.05716 Initialization Matters for Adversarial Transfer Learning
        117197, -- external MMA: Multi-Modal Adapter for Vision-Language Models
        117411, -- 2606.19938 Triangular Consistency as a Universal Constraint for Learning Optical
        118173, -- 2606.24175 Tri-Efficient Transfer Learning for Point Cloud Videos
        119847, -- external Gain from Neighbors: Boosting Model Robustness in the Wild via Adversa
        119920, -- external CLIP is Almost All You Need: Towards Parameter-Efficient Scene Text Re
        119981, -- 2603.01759 Meta-Learning Hyperparameters for Parameter Efficient Fine-Tuning
        120027, -- 2505.24693 Conformal Prediction for Zero-Shot Models
        120335, -- 2505.12685 Mamba-Adaptor: State Space Model Adaptor for Visual Recognition
        121413, -- external Modeling the Brain's Grammar: ROI-Guided fMRI Pretraining for Transfer
        121746, -- external EthoCLIP: Ontology-Enhanced Video-Language Pretraining for Animal Beha
        122612, -- 2609.39627 Introduction to Computer Vision
        123072, -- 1905.09113 A Comprehensive Study of ImageNet Pre-Training for Historical Document
        123226, -- 1706.07522 Deep Hashing Network for Unsupervised Domain Adaptation
        123646, -- 2212.03145 FacT: Factor-Tuning for Lightweight Adaptation on Vision Transformer
        123647, -- 2302.08106 Towards Efficient Visual Adaption via Structural Re-parameterization
        123648, -- 2207.07039 Convolutional Bypasses Are Better Vision Transformer Adapters
        123649, -- 2312.07856 DTL: Disentangled Transfer Learning for Visual Recognition
        123651, -- 2310.06234 Efficient Adaptation of Large Vision Transformer via Adapter Re-Compos
        124534, -- external Uni-Cheb: A Basis-Agnostic Learnable Chebyshev Filter for Multimodal S
        125926, -- external On the Effect of Token Correlations on Semantic Transfer in Transforme
        125946, -- 2605.11881 Learning Subspace-Preserving Sparse Attention Graphs from Heterogeneou
        126283, -- external Cross-Attentive Bayesian Low-Rank Adaptation for Multimodal Uncertaint
        126735, -- external Learning to Undo: Transfer Reinforcement Learning under State Space Tr
        126969, -- 2505.12027 Relation-Aware Graph Foundation Model
        127482, -- 2510.04421 Learning Survival Models with Right-Censored Reporting Delays
        127579, -- external DeepVoting: Learning and Improving Voting Rules with Fine-Tuning
        128384, -- external Do LLMs Bind Episodes? Probing Cross-Episode Parametric Retrieval Thro
        128596, -- external CONSTRAINER: Promptable Graph-Structured Optimization via Constraint C
        128607, -- 2602.02358 Transfer Learning Through Conditional Quantile Matching
        128615, -- external Uncertainty Aware SURE Transfer Learning for Classification Problems
        129813, -- external Cross-Architecture Transferability is Width-Confounded:Diagnosis and S
        129821, -- external CAST: Certifiable Aggregation of Smoothed Teachers for Robust Policy A
        130160, -- external NNCoxKL: Risk-Set Distillation from Probability-Free Prognostic Teache
        130388, -- 2602.16531 Transfer Learning of Linear Regression with Multiple Pretrained Models
        130389, -- 2605.07194 Closed-Form Linear-Probe Dataset Distillation for Pre-trained Vision M
        130679, -- external DUST: Directional Uncertainty-aware and Scale-invariant Transfer Learn
        130762, -- external Langevin-Informed Transfer Learning: Replacing the Target Samples by B
        131123, -- 2602.09969 Causal Multi-Task Demand Learning
        131342, -- 2610.31288 DISC: Domain-Integrated Similarity Cost for Time-Series Dataset
        131520  -- 2108.12617 AP-10K: A Benchmark for Animal Pose Estimation in the Wild
  );

DELETE FROM paper_method_exclusions x
USING transfer_learning_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM transfer_learning_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM transfer_learning_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE transfer_learning_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'transfer-learning'
  AND p.id IN (
        3534, -- 2005.02706 Knee Injury Detection using MRI with Efficiently-Layered Network (ELNe
        18226, -- 2307.07044 AnyStar: Domain randomized universal star-convex 3D instance segmentat
        40369  -- 2411.15576 MulModSeg: Enhancing Unpaired Multi-Modal Medical Image Segmentation w
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM transfer_learning_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING transfer_learning_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING transfer_learning_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- multi-task-learning: 636 links, 4 exclusions.
CREATE TEMP TABLE multi_task_learning_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'multi-task-learning'
  AND p.id IN (
        421, -- 1606.09282 Learning without Forgetting
        625, -- 1703.07026 Cross-modal Deep Metric Learning with Multi-task Regularization
        641, -- 1704.00051 Reading Wikipedia to Answer Open-Domain Questions
        719, -- 1705.07115 Multi-Task Learning Using Uncertainty to Weigh Losses for Scene Geomet
        818, -- 1707.08114 A Survey on Multi-Task Learning
        954, -- 1711.02257 GradNorm: Gradient Normalization for Adaptive Loss Balancing in Deep M
        984, -- 1711.09082 Cross-Domain Self-supervised Multi-task Feature Learning using Synthet
        1271, -- 1805.04687 BDD100K: A Diverse Driving Dataset for Heterogeneous Multitask Learnin
        1354, -- 1806.08730 The Natural Language Decathlon: Multitask Learning as Question Answeri
        1545, -- 1810.05943 Varifocal-Net: A Chromosome Classification Approach using Deep Convolu
        1621, -- 1811.06031 A Hierarchical Multi-task Approach for Learning Embeddings from Semant
        1676, -- 1812.01097 LEAF: A Benchmark for Federated Settings
        1728, -- 1812.11459 A neural joint model for Vietnamese word segmentation, POS tagging and
        2024, -- 1904.09482 Improving Multi-Task Deep Neural Networks via Knowledge Distillation f
        2041, -- 1904.11407 DynamoNet: Dynamic Action and Motion Network
        2065, -- 1905.01492 SoilingNet: Soiling Detection on Automotive Surround-View Cameras
        2105, -- 1905.07289 Conversion Prediction Using Multi-task Conditional Attention Networks
        2375, -- 1907.12412 ERNIE 2.0: A Continual Pre-training Framework for Language Understandi
        2456, -- 1908.09283 Multi-task Learning for Low-resource Second Language Acquisition Model
        2470, -- 1908.11049 Multilingual and Multi-Aspect Hate Speech Analysis
        2555, -- 1909.07846 Multimodal Multitask Representation Learning for Pathology Biobank Met
        2668, -- 1910.05872 Self-supervised Label Augmentation via Input Transformations
        2711, -- 1910.09753 MRQA 2019 Shared Task: Evaluating Generalization in Reading Comprehens
        2719, -- 1910.10897 Meta-World: A Benchmark and Evaluation for Multi-Task and Meta Reinfor
        2749, -- 1910.14296 LIMIT-BERT : Linguistic Informed Multi-Task BERT
        2766, -- 1911.01678 A Joint Model for Definition Extraction with Syntactic Connection and
        2939, -- 1912.07976 A Multi-task Learning Model for Chinese-oriented Aspect Polarity Class
        3013, -- 2001.06782 Gradient Surgery for Multi-Task Learning
        3144, -- 2002.11312 Multitask Learning and Multistage Fusion for Dimensional Audiovisual E
        3160, -- 2003.00152 Training BatchNorm and Only BatchNorm: On the Expressive Power of Rand
        3282, -- 2004.00248 Adversarial Transfer Learning for Punctuation Restoration
        3473, -- 2004.14875 Polygonal Building Segmentation by Frame Field Learning
        3489, -- 2005.00247 AdapterFusion: Non-Destructive Task Composition for Transfer Learning
        3510, -- 2005.00944 Understanding and Improving Information Transfer in Multi-Task Learnin
        3653, -- 2006.01895 Learning to Branch for Multi-Task Learning
        3730, -- 2006.09136 When Does Self-Supervision Help Graph Convolutional Networks?
        3780, -- 2006.11807 Improving Image Captioning with Better Use of Captions
        3851, -- 2007.01152 Learning to Segment from Scribbles using Multi-scale Adversarial Atten
        4019, -- 2008.05671 Large-scale Transfer Learning for Low-resource Spoken Language Underst
        4242, -- 2010.00980 MultiCQA: Zero-Shot Transfer of Self-Supervised Text Matching Models o
        4325, -- 2010.05171 fairseq S2T: Fast Speech-to-Text Modeling with fairseq
        4434, -- 2010.12812 A Frustratingly Easy Approach for Entity and Relation Extraction
        4557, -- 2011.07866 Cluster-Specific Predictions with Multi-Task Gaussian Processes
        4597, -- 2011.11012 Distributed Deep Reinforcement Learning: An Overview
        4871, -- 2101.03024 LiteMuL: A Lightweight On-Device Sequence Tagger using Multi-task Lear
        4913, -- 2101.07597 UniSpeech: Unified Speech Representation Learning with Labeled and Unl
        4947, -- 2101.11038 Muppet: Massive Multi-task Representations with Pre-Finetuning
        4989, -- 2102.02779 Unifying Vision-and-Language Tasks via Text Generation
        5068, -- 2102.09854 Intrinsically Motivated Open-Ended Multi-Task Learning Using Transfer
        5077, -- 2102.11103 User Factor Adaptation for User Embedding via Multitask Learning
        5307, -- 2103.15721 CaSiNo: A Corpus of Campsite Negotiation Dialogues for Automatic Negot
        5384, -- 2104.02443 CodeTrans: Towards Cracking the Language of Silicon's Code Through Sel
        5685, -- 2105.04206 You Only Learn One Representation: Unified Network for Multiple Tasks
        5751, -- 2105.08645 CoTexT: Multi-task Learning with Code-Text Transformer
        5770, -- 2105.09996 VLM: Task-agnostic Video-Language Model Pre-training for Video Underst
        5905, -- 2106.03760 DSelect-k: Differentiable Selection in the Mixture of Experts with App
        5917, -- 2106.04489 Parameter-efficient Multi-task Fine-tuning for Transformers via Shared
        6057, -- 2106.10595 Heterogeneous Multi-task Learning with Expert Diversity
        6391, -- 2108.04186 Pose is all you need: The pose only group activity recognition system
        6429, -- 2108.06955 MobIE: A German Dataset for Named Entity Recognition, Entity Linking a
        6479, -- 2108.11250 YOLOP: You Only Look Once for Panoptic Driving Perception
        6504, -- 2108.12828 MEDIC: A Multi-Task Learning Dataset for Disaster Image Classification
        6535, -- 2109.00859 CodeT5: Identifier-aware Unified Pre-trained Encoder-Decoder Models fo
        6618, -- 2109.05897 Question Answering over Electronic Devices: A New Benchmark Dataset an
        6792, -- 2110.01900 DistilHuBERT: Speech Representation Learning by Layer-wise Distillatio
        6841, -- 2110.03895 ALL-IN-ONE: Multi-Task Learning BERT models for Evaluating Peer Assess
        6878, -- 2110.05752 UniSpeech-SAT: Universal Speech Representation Learning with Speaker A
        6968, -- 2110.08207 Multitask Prompted Training Enables Zero-Shot Task Generalization
        7011, -- 2110.10429 Knowledge distillation from language model to acoustic model: a hierar
        7078, -- 2110.15028 Facial Emotion Recognition: A multi-task approach using deep learning
        7100, -- 2110.15943 MetaICL: Learning to Learn In Context
        7156, -- 2111.02585 InQSS: a speech intelligibility and quality assessment model using a m
        7268, -- 2111.10601 Deep Safe Multi-Task Learning
        7272, -- 2111.10952 ExT5: Towards Extreme Multi-Task Scaling for Transfer Learning
        7600, -- 2112.12750 SLIP: Self-supervision meets Language-Image Pre-training
        7955, -- 2202.06689 CodeFill: Multi-token Code Completion by Jointly Learning from Structu
        8026, -- 2202.10222 Robots Learn Increasingly Complex Tasks with Intrinsic Motivation and
        8096, -- 2202.13914 Combining Modular Skills in Multitask Learning
        8102, -- 2203.00077 One Model is All You Need: Multi-Task Learning Enables Simultaneous Hi
        8155, -- 2203.03312 SkillNet-NLU: A Sparsely Activated Model for General-Purpose Natural L
        8365, -- 2203.11089 PersFormer: 3D Lane Detection via Perspective Transformer and the Open
        8502, -- 2203.16708 Task Adaptive Parameter Sharing for Multi-Task Learning
        8512, -- 2203.17113 Pre-Training Transformer Decoder for End-to-End ASR Model with Unpaire
        8596, -- 2204.02967 Enhanced Direct Speech-to-Speech Translation Using Self-supervised Pre
        8613, -- 2204.03508 A Survey of Multi-task Learning in Natural Language Processing: Regard
        8678, -- 2204.05513 End-to-end Autonomous Driving with Semantic Depth Cloud Mapping and Mu
        8683, -- 2204.05698 Medusa: Universal Feature Learning via Attentional Multitasking
        8738, -- 2204.07600 In-BoXBART: Get Instructions into Biomedical Multi-Task Learning
        8743, -- 2204.07689 Sparsely Activated Mixture-of-Experts are Robust Multi-Task Learners
        8837, -- 2204.11588 Ad Creative Discontinuation Prediction with Multi-Modal Multi-Task Neu
        8846, -- 2204.12184 SkillNet-NLG: General-Purpose Natural Language Generation with a Spars
        8861, -- 2204.12811 SkillSpan: Hard and Soft Skill Extraction from English Job Postings
        9010, -- 2205.06130 Multi Task Learning For Zero Shot Performance Prediction of Multilingu
        9062, -- 2205.09651 Wojood: Nested Arabic Named Entity Corpus and Recognition using BERT
        9068, -- 2205.09743 BEVerse: Unified Perception and Prediction in Birds-Eye-View for Visio
        9128, -- 2205.11413 QASem Parsing: Text-to-text Modeling of QA-based Semantics
        9341, -- 2206.01256 PETRv2: A Unified Framework for 3D Perception from Multi-Camera Images
        9363, -- 2206.02096 PEER: A Comprehensive and Multi-Task Benchmark for Protein Sequence Un
        9451, -- 2206.05922 From Perception to Programs: Regularize, Overparameterize, and Amortiz
        9622, -- 2206.13476 Impact of Acoustic Event Tagging on Scene Classification in a Multi-Ta
        9648, -- 2206.15076 BigBIO: A Framework for Data-Centric Biomedical Natural Language Proce
        9681, -- 2207.01328 DUET: Cross-modal Semantic Grounding for Contrastive Zero-shot Learnin
        9705, -- 2207.03051 A Large Scale Search Dataset for Unbiased Learning to Rank
        9845, -- 2207.09858 GenHPF: General Healthcare Predictive Framework with Multi-task Multi-
        9855, -- 2207.10333 Jointly Predicting Emotion, Age, and Country Using Pre-Trained Acousti
        9921, -- 2207.13703 SoundChoice: Grapheme-to-Phoneme Models with Semantic Disambiguation
        10018, -- 2208.05379 Multi-task Active Learning for Pre-trained Transformer-based Models
        10204, -- 2209.00930 Mind the Gap! Injecting Commonsense Knowledge for Abstractive Dialogue
        10208, -- 2209.01217 A Method for Discovering Novel Classes in Tabular Data
        10462, -- 2209.14927 Spotlight: Mobile UI Understanding using Vision-Language Models with a
        10581, -- 2210.02493 Depth Is All You Need for Monocular 3D Detection
        10639, -- 2210.03871 Data-Efficiency with a Single GPU: An Exploration of Transfer Methods
        10771, -- 2210.06726 Explanations from Large Language Models Make Small Reasoners Better
        10873, -- 2210.09759 Pareto Manifold Learning: Tackling multiple tasks via ensembles of sin
        10892, -- 2210.10258 Continued Pretraining for Better Zero- and Few-Shot Promptability
        11047, -- 2210.13832 FineD-Eval: Fine-grained Automatic Dialogue-Level Evaluation
        11079, -- 2210.14793 M$^3$ViT: Mixture-of-Experts Vision Transformer for Efficient Multi-ta
        11241, -- 2211.03352 Curriculum-based Asymmetric Multi-task Reinforcement Learning
        11381, -- 2211.08850 Consecutive Question Generation via Dynamic Multitask Learning
        11420, -- 2211.09808 Uni-Perceiver v2: A Generalist Model for Large-Scale Vision and Vision
        11597, -- 2211.13723 Improving Multi-task Learning via Seeking Task-based Flat Regions
        11604, -- 2211.13873 Global and Local Hierarchy-aware Contrastive Framework for Implicit Di
        11639, -- 2211.14666 Synergies between Disentanglement and Sparsity: Generalization and Ide
        11697, -- 2211.16352 Découvrir de nouvelles classes dans des données tabulaires
        11716, -- 2211.17046 Rationale-Guided Few-Shot Classification to Detect Abusive Language
        11784, -- 2212.01378 ColD Fusion: Collaborative Descent for Distributed Multitask Finetunin
        11824, -- 2212.02846 Statistical mechanics of continual learning: variational principle and
        11904, -- 2212.05199 MAGVIT: Masked Generative Video Transformer
        12309, -- 2301.01935 Topic Segmentation Model Focusing on Local Context
        12329, -- 2301.02494 Adaptive Pattern Extraction Multi-Task Learning for Multi-Step Convers
        12403, -- 2301.05948 tasksource: A Dataset Harmonization Framework for Streamlined NLP Mult
        12424, -- 2301.07067 Transformers as Algorithms: Generalization and Stability in In-context
        12589, -- 2301.11716 Pre-training for Speech Translation: CTC Meets Optimal Transport
        12878, -- 2302.02907 GAT: Guided Adversarial Training with Pareto-optimal Auxiliary Tasks
        12912, -- 2302.03328 Multi-Task Recommendations with Reinforcement Learning
        13053, -- 2302.06354 Less is More: Selective Layer Finetuning with SubTuning
        13131, -- 2302.07975 Multi-Task Differential Privacy Under Distribution Skew
        13304, -- 2302.12623 TUTORING: Instruction-Grounded Conversational Agent for Language Learn
        13504, -- 2303.02861 Multitask Prompt Tuning Enables Parameter-Efficient Transfer Learning
        13690, -- 2303.06856 Dynamic Neural Network for Multi-Task Learning Searching across Divers
        13842, -- 2303.09556 Efficient Diffusion Training via Min-SNR Weighting Strategy
        13845, -- 2303.09663 Efficient Computation Sharing for Multi-Task Visual Scene Understandin
        14008, -- 2303.12489 Few-shot Multimodal Multitask Multilingual Learning
        14023, -- 2303.12745 Audio-Visual Deception Detection: DOLOS Dataset and Parameter-Efficien
        14252, -- 2303.16563 Skill Reinforcement Learning and Planning for Open-World Long-Horizon
        14296, -- 2303.17376 A Study of Autoregressive Decoders for Multi-Tasking in Computer Visio
        14352, -- 2303.18248 Towards Flexible Multi-modal Document Models
        14361, -- 2304.00152 Learning the Distribution of Errors in Stereo Matching for Joint Dispa
        14600, -- 2304.04959 AdaTT: Adaptive Task-to-Task Fusion Network for Multitask Learning in
        14722, -- 2304.07645 Magnitude Invariant Parametrizations Improve Hypernetwork Learning
        14806, -- 2304.09801 MetaBEV: Solving Sensor Failures for BEV Detection and Map Segmentatio
        15001, -- 2304.13949 UCF: Uncovering Common Features for Generalizable Deepfake Detection
        15083, -- 2305.00441 Multi-Task Structural Learning using Local Task Similarity induced Neu
        15166, -- 2305.02008 Zenseact Open Dataset: A large-scale and diverse multimodal dataset fo
        15419, -- 2305.06218 Multi-Task End-to-End Training Improves Conversational Recommendation
        15539, -- 2305.08264 MatSci-NLP: Evaluating Scientific Language Models on Materials Science
        15869, -- 2305.12633 Multi-task Hierarchical Adversarial Inverse Reinforcement Learning
        16077, -- 2305.14352 An Extensible Multimodal Multi-task Object Dataset with Materials
        16140, -- 2305.14782 IBCL: Zero-shot Model Generation for Task Trade-offs in Continual Lear
        16553, -- 2305.18691 Edge-MoE: Memory-Efficient Multi-Task Vision Transformer Architecture
        16593, -- 2305.19000 Independent Component Alignment for Multi-Task Learning
        16732, -- 2306.00354 Addressing Negative Transfer in Diffusion Models
        17094, -- 2306.04306 Allophant: Cross-lingual Phoneme Recognition with Articulatory Attribu
        17141, -- 2306.04925 Prefer to Classify: Improving Text Classifiers via Auxiliary Preferenc
        17200, -- 2306.05539 Instruction Tuned Models are Quick Learners
        17377, -- 2306.07952 MOFI: Learning Image Representations from Noisy Entity Annotated Image
        17585, -- 2306.10785 Multitrack Music Transcription with a Time-Frequency Perceiver
        17723, -- 2306.13661 Constructing Time-Series Momentum Portfolios with Deep Multi-Task Lear
        17834, -- 2306.15978 Sentence-to-Label Generation Framework for Multi-task Learning of Japa
        17900, -- 2306.17165 An Efficient General-Purpose Modular Vision Model via Multi-Task Heter
        17984, -- 2307.01401 Multi-Task Learning Improves Performance In Deep Argument Mining Model
        18075, -- 2307.03374 STG-MTL: Scalable Task Grouping for Multi-Task Learning Using Data Map
        18174, -- 2307.05634 Hyperspherical Embedding for Point Cloud Completion
        18398, -- 2307.09758 Longitudinal Data and a Semantic Similarity Reward for Chest X-Ray Rep
        18730, -- 2307.15324 TaskExpert: Dynamically Assembling Multi-Task Representations with Mem
        18740, -- 2307.15429 Improvable Gap Balancing for Multi-Task Learning
        18790, -- 2307.16617 FULLER: Unified Multi-modality Multi-task 3D Perception via Multi-leve
        19148, -- 2308.05996 Deep Task-specific Bottom Representation Network for Multi-Task Recomm
        19211, -- 2308.06873 SpeechX: Neural Codec Language Model as a Versatile Speech Transformer
        19312, -- 2308.08234 Challenges and Opportunities of Using Transformer-Based Multi-Task Lea
        19673, -- 2308.11928 OFVL-MS: Once for Visual Localization across Multiple Indoor Scenes
        19701, -- 2308.12221 Critical Learning Periods Emerge Even in Deep Linear Networks
        19712, -- 2308.12372 Vision Transformer Adapters for Generalizable Multitask Learning
        19749, -- 2308.12952 BridgeData V2: A Dataset for Robot Learning at Scale
        19847, -- 2308.14280 FonMTL: Towards Multitask Learning for the Fon Language
        20158, -- 2309.03130 MyoDex: A Generalizable Prior for Dexterous Manipulation
        20440, -- 2309.07937 Voxtlm: unified decoder-only models for consolidating speech recogniti
        20454, -- 2309.08156 RADE: Reference-Assisted Dialogue Evaluation for Open-Domain Dialogue
        20785, -- 2309.12970 PI-RADS v2 Compliant Automated Segmentation of Prostate Zones Using co
        20975, -- 2309.15596 PolarNet: 3D Point Clouds for Language-Guided Robotic Manipulation
        21060, -- 2309.16921 YOLOR-Based Multi-Task Learning
        21205, -- 2310.00986 Multi-task Learning with 3D-Aware Regularization
        21227, -- 2310.01217 ScaLearn: Simple and Highly Parameter-Efficient Task Transfer by Learn
        21349, -- 2310.02281 End-to-End Continuous Speech Emotion Recognition in Real-life Customer
        21366, -- 2310.02575 AdaMerging: Adaptive Model Merging for Multi-Task Learning
        21501, -- 2310.04313 KoMultiText: Large-Scale Korean Text Dataset for Classifying Biased Sp
        21760, -- 2310.07138 Denoising Task Routing for Diffusion Models
        21797, -- 2310.07510 Heuristic Vision Pre-Training with Self-Supervised and Supervised Mult
        21928, -- 2310.08795 Mitigating Bias for Question Answering Models by Tracking Bias Influen
        21974, -- 2310.09478 MiniGPT-v2: large language model as a unified interface for vision-lan
        22143, -- 2310.11670 Prototype-based HyperAdapter for Sample-Efficient Multi-task Tuning
        22258, -- 2310.13135 LeTFuser: Light-weight End-to-end Transformer-Based Sensor Fusion for
        22291, -- 2310.13550 Provable Benefits of Multi-task RL under Non-Markovian Decision Making
        22340, -- 2310.14326 CLMSM: A Multi-Task Learning Framework for Pre-training on Procedural
        22438, -- 2310.15308 SAM-CLIP: Merging Vision Foundation Models towards Semantic and Spatia
        22534, -- 2310.16484 Subspace Chronicles: How Linguistic Information Emerges, Shifts and In
        22659, -- 2310.18119 Towards a Unified Conversational Recommendation System: Multi-task Lea
        22786, -- 2310.19975 BioInstruct: Instruction Tuning of Large Language Models for Biomedica
        22933, -- 2311.01851 Holistic Representation Learning for Multitask Trajectory Anomaly Dete
        22955, -- 2311.02303 MFTCoder: Boosting Code LLMs with Multitask Fine-Tuning
        23174, -- 2311.06242 Florence-2: Advancing a Unified Representation for a Variety of Vision
        23462, -- 2311.10089 Emu Edit: Precise Image Editing via Recognition and Generation Tasks
        23532, -- 2311.11501 MultiLoRA: Democratizing LoRA for Better Multi-Task Learning
        24096, -- 2312.00292 SEPSIS: I Can Catch Your Lies -- A New Paradigm for Deception Detectio
        24114, -- 2312.00477 Interpretable Meta-Learning of Physical Systems
        24341, -- 2312.03248 Customizable Combination of Parameter-Efficient Modules for Multi-Task
        24346, -- 2312.03414 Compressed Context Memory For Online Language Model Interaction
        24542, -- 2312.05525 You Only Learn One Query: Learning Unified Human Query for Single-Stag
        24578, -- 2312.06134 Order Matters in the Presence of Dataset Imbalance for Multilingual Le
        25151, -- 2312.14991 FoodLMM: A Versatile Food Assistant using Large Multi-modal Model
        25248, -- 2312.16610 Efficient Deweather Mixture-of-Experts with Uncertainty-aware Feature-
        25357, -- 2401.00536 A Multi-Task, Multi-Modal Approach for Predicting Categorical and Dime
        25535, -- 2401.03158 CoT-Driven Framework for Short Text Classification: Enhancing and Tran
        25647, -- 2401.05163 MISS: A Generative Pretraining and Finetuning Approach for Med-VQA
        25724, -- 2401.06139 Stockformer: A Price-Volume Factor Stock Selection Model Based on Wave
        25986, -- 2401.09942 Multi-task Learning for Joint Re-identification, Team Affiliation, and
        26135, -- 2401.12149 Personalized Over-the-Air Federated Learning with Personalized Reconfi
        26530, -- 2401.17862 Proximity QA: Unleashing the Power of Multi-Modal Large Language Model
        26788, -- 2402.02705 Representation Surgery for Multi-Task Model Merging
        27077, -- 2402.05929 An Interactive Agent Foundation Model
        27118, -- 2402.06332 InternLM-Math: Open Math Large Language Models Toward Verifiable Reaso
        27256, -- 2402.08437 Camera Calibration through Geometric Constraints from Rotation and Pro
        27496, -- 2402.11417 LoRETTA: Low-Rank Economic Tensor-Train Adaptation for Ultra-Low-Param
        27806, -- 2402.14522 Towards Unified Task Embeddings Across Multiple Models: Bridging the G
        28020, -- 2402.17016 Multi-Task Contrastive Learning for 8192-Token Bilingual Text Embeddin
        28184, -- 2402.19059 WHU-Synthetic: A Synthetic Perception Dataset for 3-D Multitask Model
        28457, -- 2403.03432 Mixture-of-LoRAs: An Efficient Multitask Tuning for Large Language Mod
        28836, -- 2403.09176 Switch Diffusion Transformer: Synergizing Denoising Tasks with Sparse
        28944, -- 2403.10662 SwinMTL: A Shared Architecture for Simultaneous Depth Estimation and S
        29118, -- 2403.12749 Sebastian, Basti, Wastl?! Recognizing Named Entities in Bavarian Diale
        29168, -- 2403.13257 Arcee's MergeKit: A Toolkit for Merging Large Language Models
        29183, -- 2403.13358 GeRM: A Generalist Robotic Model with Mixture-of-experts for Quadruped
        29433, -- 2403.16941 SPACE-IDEAS: A Dataset for Salient Information Detection in Space Inno
        29584, -- 2403.19113 FACTOID: FACtual enTailment fOr hallucInation Detection
        29679, -- 2403.20320 MTLoRA: A Low-Rank Adaptation Approach for Efficient Multi-Task Learni
        29881, -- 2404.02588 Large Language Models for Expansion of Spoken Language Understanding S
        29944, -- 2404.03558 How does Multi-Task Training Affect Transformer In-Context Capabilitie
        29958, -- 2404.03637 Sequential Recommendation for Optimizing Both Immediate Feedback and L
        30328, -- 2404.09027 MING-MOE: Enhancing Medical Multi-Task Learning in Large Language Mode
        30701, -- 2404.15159 MixLoRA: Enhancing Large Language Models Fine-Tuning with LoRA-based M
        30937, -- 2404.19665 ATOMMIC: An Advanced Toolbox for Multitask Medical Imaging Consistency
        31120, -- 2405.04408 DocRes: A Generalist Model Toward Unifying Document Image Restoration
        31346, -- 2405.10004 ROCOv2: Radiology Objects in COntext Version 2, an Updated Multimodal
        31786, -- 2405.16671 Mixture of Latent Experts Using Tensor Products
        32045, -- 2405.19795 SLM as Guardian: Pioneering AI Safety with Small Language Models
        32359, -- 2406.03049 StreamSpeech: Simultaneous Speech-to-Speech Translation with Multi-tas
        32833, -- 2406.08742 DeepUnifiedMom: Unified Time-series Momentum Portfolio Construction vi
        32987, -- 2406.10327 Analysing Multi-Task Regression via Random Matrix Theory with Applicat
        33098, -- 2406.11385 MetaGPT: Merging Large Language Models Using Model Exclusive Task Arit
        33403, -- 2406.14491 Instruction Pre-Training: Language Models are Supervised Multitask Lea
        33574, -- 2406.16441 UniCoder: Scaling Code Large Language Model via Universal Code
        33628, -- 2406.17229 Self-Supervised Embeddings for Detecting Individual Symptoms of Depres
        33878, -- 2407.00121 Granite-Function Calling Model: Introducing Function Calling Abilities
        34282, -- 2407.05645 OneDiff: A Generalist Model for Image Difference Captioning
        34456, -- 2407.08056 Pareto Low-Rank Adapters: Efficient Multi-Task Learning with Preferenc
        35146, -- 2407.17053 Automated Code-centric Software Vulnerability Assessment: How Far Are
        35468, -- 2408.00981 Cross-domain Named Entity Recognition via Graph Matching
        35709, -- 2408.05211 VITA: Towards Open-Source Interactive Omni Multimodal LLM
        35715, -- 2408.05430 HoME: Hierarchy of Multi-Gate Experts for Multi-Task Learning at Kuais
        35811, -- 2408.07057 A Survey on Model MoErging: Recycling and Routing Among Specialized Ex
        35844, -- 2408.07666 Model Merging in LLMs, MLLMs, and Beyond: Methods, Theories, Applicati
        36124, -- 2408.12194 Large Language Models as Foundations for Next-Gen Dense Retrieval: A C
        36912, -- 2409.09891 Acquiring Pronunciation Knowledge from Transcribed Speech Audio via Mu
        37548, -- 2409.20370 The Perfect Blend: Redefining RLHF with Mixture of Judges
        37764, -- 2410.02475 Efficient Residual Learning with Mixture-of-Experts for Universal Dext
        37906, -- 2410.03782 DaWin: Training-free Dynamic Weight Interpolation for Robust Adaptatio
        38096, -- 2410.06158 GR-2: A Generative Video-Language-Action Model with Web-Scale Knowledg
        38149, -- 2410.06741 CoBa: Convergence Balancer for Multitask Finetuning of Large Language
        38361, -- 2410.09437 MTL-LoRA: Low-Rank Adaptation for Multi-Task Learning
        38465, -- 2410.10801 Mix Data or Merge Models? Optimizing for Diverse Multi-Task Learning
        38817, -- 2410.14633 Swiss Army Knife: Synergizing Biases in Knowledge from Vision Foundati
        39658, -- 2411.03055 ATM: Improving Model Merging by Alternating Tuning and Merging
        39820, -- 2411.05903 Towards Multi-Modal Mastery: A 4.5B Parameter Truly Multi-Modal Small
        39899, -- 2411.07343 Multi-head Span-based Detector for AI-generated Fragments in Scientifi
        40119, -- 2411.11736 Advacheck at GenAI Detection Task 1: AI Detection Powered by Domain-Aw
        40130, -- 2411.11904 GeoGround: A Unified Large Vision-Language Model for Remote Sensing Vi
        40612, -- 2411.18615 Proactive Gradient Conflict Mitigation in Multi-Task Learning: A Spars
        40718, -- 2411.19865 Reverse Thinking Makes LLMs Stronger Reasoners
        40923, -- 2412.02693 Diffusion-based Visual Anagram as Multi-task Learning
        41427, -- 2412.08946 MoSLD: An Extremely Parameter-Efficient Mixture-of-Shared LoRAs for Mu
        41447, -- 2412.09278 Towards a Multimodal Large Language Model with Pixel-Level Insight for
        41759, -- 2412.12953 Efficient Diffusion Transformer Policies with Mixture of Expert Denois
        42208, -- 2412.19098 Tint Your Models Task-wise for Improved Multi-task Model Merging
        42411, -- 2501.01230 Modeling Multi-Task Model Merging as Adaptive Projective Gradient Desc
        42576, -- 2501.03863 Improving Dialectal Slot and Intent Detection with Auxiliary Tasks: A
        42873, -- 2501.08809 XMusic: Towards a Generalized and Controllable Symbolic Music Generati
        43035, -- 2501.11631 Noise-Agnostic Multitask Whisper Training for Reducing False Alarm Err
        43236, -- 2501.15103 Each Rank Could be an Expert: Single-Ranked Mixture of Experts LoRA fo
        43648, -- 2502.02358 MotionLab: Unified Human Motion Generation and Editing via the Motion-
        43716, -- 2502.03499 Omni-DNA: A Unified Genomic Foundation Model for Cross-Modal and Multi
        43742, -- 2502.03979 Towards Unified Music Emotion Recognition across Dimensional and Categ
        43979, -- 2502.06877 WirelessGPT: A Generative Pre-trained Multi-task Learning Framework fo
        44452, -- 2502.12490 UniGenCoder: Merging Seq2Seq and Seq2Tree Paradigms for Unified Code G
        44502, -- 2502.13019 Oreo: A Plug-in Context Reconstructor to Enhance Retrieval-Augmented G
        44977, -- 2502.17919 AirCast: Improving Air Pollution Forecasting Through Multi-Variable Da
        45610, -- 2503.05316 CoinRobot: Generalized End-to-end Robotic Learning for Physical Intell
        45679, -- 2503.06273 Zero-AVSR: Zero-Shot Audio-Visual Speech Recognition with LLMs by Lear
        45763, -- 2503.07137 A Comprehensive Survey of Mixture-of-Experts: Algorithms, Theory, and
        45789, -- 2503.07413 REF-VLM: Triplet-Based Referring Paradigm for Unified Visual Decoding
        45839, -- 2503.08037 ObjectMover: Generative Object Movement with Video Prior
        46211, -- 2503.12649 FW-Merging: Scaling Model Merging with Frank-Wolfe Optimization
        46608, -- 2503.18100 M3Net: Multimodal Multi-task Learning for 3D Detection, Segmentation,
        46735, -- 2503.19794 PAVE: Patching and Adapting Video Large Language Models
        46829, -- 2503.21169 VADMamba: Exploring State Space Models for Fast Video Anomaly Detectio
        46913, -- 2503.22178 AdaRank: Adaptive Rank Pruning for Enhanced Model Merging
        47051, -- 2503.24057 AMMSM: Adaptive Motion Magnification and Sparse Mamba for Micro-Expres
        48485, -- 2505.04424 RLMiniStyler: Light-weight RL Style Agent for Arbitrary Sequential Neu
        48772, -- 2505.10413 Hierarchical Document Refinement for Long-context Retrieval-augmented
        49651, -- 2505.18777 HD-PiSSA: High-Rank Distributed Orthogonal Adaptation
        49888, -- 2505.20589 Prot2Token: A Unified Framework for Protein Modeling via Next-Token Pr
        50747, -- 2506.07080 FLAIR-HUB: Large-scale Multimodal Dataset for Land Cover and Crop Mapp
        50908, -- 2506.09093 Merging Smarter, Generalizing Better: Enhancing Model Merging on OOD D
        51103, -- 2506.12379 Training-free LLM Merging for Multi-task Learning
        51246, -- 2506.14861 BMFM-RNA: An Open Framework for Building and Evaluating Transcriptomic
        51252, -- 2506.15154 SonicVerse: Multi-Task Learning for Music Feature-Informed Captioning
        51625, -- 2507.01828 Autoadaptive Medical Segment Anything Model
        51893, -- 2507.11181 Mixture of Experts in Large Language Models
        52092, -- 2507.21049 Rep-MTL: Unleashing the Power of Representation-level Task Saliency fo
        52623, -- 2509.02108 DivMerge: A divergence-based model merging method for multi-tasking
        53733, -- 2510.07581 Expanding the Action Space of LLMs to Reason Beyond Language
        53911, -- 2510.22264 PatenTEB: A Comprehensive Benchmark and Model Family for Patent Text
        53924, -- 2501.15302 The ICME 2025 Audio Encoder Capability Challenge
        54170, -- 2511.10647 Depth Anything 3: Recovering the Visual Space from Any Views
        54636, -- 2512.07831 UnityVideo: Unified Multi-Modal Multi-Task Learning for Enhancing Worl
        54855, -- 2512.13190 WAY: Estimation of Vessel Destination in Worldwide AIS Trajectory
        58046, -- 2604.17915 OneDrive: Unified Multi-Paradigm Driving with Vision-Language-Action M
        58203, -- 2604.12918 Radar-Camera BEV Multi-Task Learning with Cross-Task Attention Bridge
        58839, -- 2603.26945 Real-time Appearance-based Gaze Estimation for Open Domains
        58889, -- 2603.25041 AdaLTM: Adaptive Layer-wise Task Vector Merging for Categorical Speech
        59890, -- 2603.04356 RoboCasa365: A Large-Scale Simulation Framework for Training and Bench
        60637, -- 2602.14231 Robust multi-task boosting using clustering and local ensembling
        60857, -- 2602.10503 Towards Long-Lived Robots: Continual Learning VLA Models via Reinforce
        61298, -- 2602.04063 iSight: Towards expert-AI co-assessment for improved immunohistochemis
        61450, -- 2602.01899 Multi-Task Learning for Robot Perception with Imbalanced Data
        61554, -- 2602.01055 Baseline Method of the Foundation Model Challenge for Ultrasound Image
        61574, -- 2604.02338 LiME: Lightweight Mixture of Experts for Efficient Multimodal Multi-ta
        61590, -- 2602.00839 TransNormal: Dense Visual Semantics for Diffusion-based Transparent Ob
        61908, -- 2602.02536 From Sparse Decisions to Dense Reasoning: A Multi-attribute Trajectory
        62107, -- 2602.15853 A Lightweight Explainable Guardrail for Prompt Safety
        62295, -- 2601.13886 Revisiting Multi-Task Visual Representation Learning
        62994, -- 2601.02209 ARCADE: A City-Scale Corpus for Fine-Grained Arabic Dialect Tagging
        64096, -- 2512.05117 The Universal Weight Subspace Hypothesis
        64118, -- 2512.04629 BioMedGPT-Mol: Multi-task Learning for Molecular Understanding and Gen
        64127, -- 2512.04513 BiTAgent: A Task-Aware Modular Framework for Bidirectional Coupling be
        64316, -- 2512.01128 OmniFD: A Unified Model for Versatile Face Forgery Detection
        64479, -- 2511.21272 Co-Training Vision Language Models for Remote Sensing Multi-task Learn
        65080, -- 2511.09970 MultiTab: A Scalable Foundation for Multitask Learning on Tabular Data
        65454, -- 2511.01831 Dynamic Routing Between Experts: A Data-Efficient Approach to Continua
        65542, -- 2511.00504 VinDr-CXR-VQA: A Visual Question Answering Dataset for Explainable Che
        65658, -- 2510.25970 SplitFlow: Flow Decomposition for Inversion-Free Text-to-Image Editing
        65694, -- 2511.01892 Retrieval-Augmented Multimodal Depression Detection
        65788, -- 2510.23559 KongNet: A Multi-headed Deep Learning Model for Detection and   Classi
        66159, -- 2510.17532 OncoReason: Structuring Clinical Reasoning in LLMs for Robust and   In
        66264, -- 2510.15299 GRank: Towards Target-Aware and Streamlined Industrial Retrieval with
        66601, -- 2510.10068 Probabilistic Hyper-Graphs using Multiple Randomly Masked Autoencoders
        67284, -- 2509.26601 MENLO: From Preferences to Proficiency -- Evaluating and Modeling   Na
        67408, -- 2509.25107 Knowledge Extraction on Semi-Structured Content: Does It Remain Releva
        67480, -- 2509.24391 UniFlow-Audio: Unified Flow Matching for Audio Generation from   Omni-
        68059, -- 2509.16959 Graph Coloring for Multi-Task Learning
        68595, -- 2509.07252 GCond: Gradient Conflict Resolution via Accumulation-based Stabilizati
        68800, -- 2509.02809 Predicting Movie Success with Multi-Task Learning: A Hybrid Framework
        68815, -- 2509.02450 EmoPerso: Enhancing Personality Detection with Self-Supervised   Emoti
        69050, -- 2509.04460 CoCoNUTS: Concentrating on Content while Neglecting Uninformative   Te
        69337, -- 2508.16082 On Task Vectors and Gradients
        69420, -- 2508.14600 Energy Injection Identification enabled Disaggregation with Deep Multi
        69427, -- 2508.14486 WeedSense: Multi-Task Learning for Weed Segmentation, Height Estimatio
        69610, -- 2508.11565 INFNet: A Task-aware Information Flow Network for Large-Scale   Recomm
        69772, -- 2508.09381 What Can We Learn from Inter-Annotator Variability in Skin Lesion Segm
        69971, -- 2508.06360 Cyberbullying Detection via Aggression-Enhanced Prompting
        70023, -- 2508.05633 KuaiLive: A Real-time Interactive Dataset for Live Streaming   Recomme
        70065, -- 2508.05078 Align, Don't Divide: Revisiting the LoRA Architecture in Multi-Task
        70087, -- 2508.04682 TurboTrain: Towards Efficient and Balanced Multi-Task Learning for   M
        70379, -- 2508.01148 DisTaC: Conditioning Task Vectors via Distillation for Robust Model Me
        70621, -- 2507.21358 Collaborative Perceiver: Elevating Vision-based 3D Object Detection vi
        70731, -- 2507.19077 Multi-Task Dense Prediction Fine-Tuning with Mixture of Fine-Grained E
        70763, -- 2507.18542 Effective Multi-Task Learning for Biomedical Named Entity Recognition
        70858, -- 2507.16951 Harnessing RLHF for Robust Unanswerability Recognition and Trustworthy
        71110, -- 2507.11411 Robust-Multi-Task Gradient Boosting
        71261, -- 2507.07883 SAMO: A Lightweight Sharpness-Aware Approach for Multi-Task Optimizati
        71344, -- 2507.05742 Whole Slide Concepts: A Supervised Foundation Model For Pathological I
        71530, -- 2507.01348 SpeechAccentLLM: A Unified Framework for Foreign Accent Conversion and
        72026, -- 2506.08666 LLaVA-c: Continual Improved Visual Instruction Tuning
        72200, -- 2506.06130 Gradient Similarity Surgery in Multi-Task Deep Learning
        72298, -- 2506.03574 SwitchVLA: Execution-Aware Task Switching for Vision-Language-Action
        72556, -- 2505.23117 Decom-Renorm-Merge: Model Merging on the Right Space Improves   Multit
        72568, -- 2505.22635 Learning Composable Chains-of-Thought
        72594, -- 2505.22053 AudioGenie: A Training-Free Multi-Agent Framework for Diverse   Multim
        72611, -- 2505.21866 CSI-Bench: A Large-Scale In-the-Wild Dataset for Multi-task WiFi Sensi
        74180, -- 2503.08007 MoRE: Unlocking Scalability in Reinforcement Learning for Quadruped Vi
        74299, -- 2503.02717 Catheter Detection and Segmentation in X-ray Images via Multi-task Lea
        74704, -- 2502.09854 Efficient Multitask Learning in Small Language Models Through   Upside
        75066, -- 2501.15934 Leveraging multi-task learning to improve the detection of SATD and
        75151, -- 2501.10945 Gradient-Based Multi-Objective Deep Learning: Algorithms, Theories, Ap
        75359, -- 2412.18524 HTR-JAND: Handwritten Text Recognition with Joint Attention Network an
        75512, -- 2412.08908 WiFo: Wireless Foundation Model for Channel Prediction
        75617, -- 2412.02279 A Comprehensive Evaluation of Large Language Models on Aspect-Based Se
        75679, -- 2411.18607 Task Arithmetic Through The Lens Of One-Shot Federated Learning
        75931, -- 2410.21696 The Effects of Multi-Task Learning on ReLU Neural Network Functions
        76238, -- 2409.20154 GravMAD: Grounded Spatial Value Maps Guided Action Diffusion for   Gen
        76379, -- 2409.16317 A Literature Review of Keyword Spotting Technologies for Urdu
        76382, -- 2409.09877 REG: Refined Generalized Focal Loss for Road Asset Detection on Thai H
        76519, -- 2408.13976 Sifting through the Chaff: On Utilizing Execution Feedback for Ranking
        76629, -- 2408.02198 Synergistic Learning with Multi-Task DeepONet for Efficient PDE Proble
        77317, -- 2405.03446 SEvenLLM: Benchmarking, Eliciting, and Enhancing Abilities of Large
        77473, -- 2404.05943 Interplay of Machine Translation, Diacritics, and Diacritization
        77640, -- 2403.08654 An Efficient End-to-End Approach to Noise Invariant Speech Features vi
        77820, -- 2402.07767 Text Detoxification as Style Transfer in English and Hindi
        77925, -- 2401.11124 Cross-Task Affinity Learning for Multitask Dense Scene Predictions
        77930, -- 2401.10228 RMP-SAM: Towards Real-Time Multi-Purpose Segment Anything
        78038, -- 2312.15674 Multi-Task Multi-Agent Shared Layers are Universal Cognition of   Mult
        78079, -- 2312.10515 PETDet: Proposal Enhancement for Two-Stage Fine-Grained Object Detecti
        78524, -- 2309.08368 Robust Burned Area Delineation through Multitask Learning
        78925, -- 2306.02553 Learning to Relate to Previous Turns in Conversational Search
        79073, -- 2305.01482 Multitask learning in Audio Captioning: a sentence embedding regressio
        79097, -- 2304.13085 AI-Synthesized Voice Detection Using Neural Vocoder Artifacts
        79107, -- 2304.11708 Sound-based drone fault classification using multitask learning
        79220, -- 2303.11573 BigSmall: Efficient Multi-Task Learning for Disparate Spatial and Temp
        79350, -- 2302.09437 RobustDistiller: Compressing Universal Speech Representations for Enha
        79776, -- 2208.11434 YOLOPv2: Better, Faster, Stronger for Panoptic Driving Perception
        79919, -- 2206.03377 RAAT: Relation-Augmented Attention Transformer for Relation Modeling i
        79995, -- 2205.05313 Towards Unified Prompt Tuning for Few-shot Text Classification
        80012, -- 2205.02671 What is Right for Me is Not Yet Right for You: A Dataset for Grounding
        80090, -- 2203.16838 NeuFA: Neural Network Based End-to-End Forced Alignment with   Bidirec
        80246, -- 2201.10649 Attentive Task Interaction Network for Multi-Task Learning
        80299, -- 2112.11610 EyePAD++: A Distillation-based approach for joint Eye Authentication a
        80334, -- 2112.03566 More layers! End-to-end regression and uncertainty on tabular data wit
        80577, -- 2108.05251 Improving Single-Image Defocus Deblurring: How Dual-Pixel Images Help
        80596, -- 2107.12135 Fine-Grained Emotion Prediction by Modeling Emotion Definitions
        80691, -- 2106.03487 Exploiting Emotional Dependencies with Graph Convolutional Networks fo
        80716, -- 2105.08190 Graph Neural Networks for Knowledge Enhanced Visual Representation of
        80906, -- 2101.11935 A Machine Learning Challenge for Prognostic Modelling in Head and Neck
        81068, -- 2010.07785 Response Selection for Multi-Party Conversations with Dynamic Topic
        81308, -- 2005.09801 FashionBERT: Text and Image Matching with Adaptive Loss for Cross-moda
        81366, -- 2004.13852 TXtract: Taxonomy-Aware Knowledge Extraction for Thousands of Product
        81450, -- 2002.05873 Speech Enhancement using Self-Adaptation and Multi-Head Self-Attention
        81872, -- 1811.05660 MT-CGCNN: Integrating Crystal Graph Convolutional Neural Network with
        82122, -- 1712.08862 Neural Network Multitask Learning for Traffic Flow Forecasting
        82143, -- 1711.08195 On the Automatic Generation of Medical Imaging Reports
        82158, -- 1710.11438 Learning Neural Representations of Human Cognition across Many fMRI St
        82223, -- 1706.05098 An Overview of Multi-Task Learning in Deep Neural Networks
        82440, -- 1601.00400 Multi-task CNN Model for Attribute Prediction
        82566, -- 1406.2199 Two-Stream Convolutional Networks for Action Recognition in Videos
        82855, -- 2605.03395 APEX: Large-scale Multi-task Aesthetic-Informed Popularity Prediction
        83791, -- 2605.26046 When Gradients Collide: Failure Modes of Multi-Objective Prompt Optimi
        84036, -- 2506.08013 StableMTL: Repurposing Latent Diffusion Models for Multi-Task Learning
        84224, -- 2511.18814 DetAny4D: Detect Anything 4D Temporally in a Streaming RGB Video
        84252, -- 2511.20646 3D-Aware Multi-Task Learning with Cross-View Correlations for Dense Sc
        84288, -- 2511.23332 UniGeoSeg: Towards Unified Open-World Segmentation for Geospatial Scen
        84353, -- 2512.06251 NexusFlow: Unifying Disparate Tasks under Partial Supervision via Inve
        84737, -- 2603.03920 BD-Merging: Bias-Aware Dynamic Model Merging with Evidence-Guided Cont
        85001, -- 2603.20403 FAAR: Efficient Frequency-Aware Multi-Task Fine-Tuning via Automatic R
        86830, -- 2508.04605 Multitask Learning  with Stochastic Interpolants
        87213, -- 2411.12164 UrbanDiT: A Foundation Model for Open-World Urban Spatio-Temporal Lear
        87248, -- 2510.12007 Semi-infinite Nonconvex Constrained Min-Max Optimization
        87329, -- 2502.06244 PiKE: Adaptive Data Mixing for Large-Scale Multi-Task Learning Under L
        87473, -- 2503.04046 Continual Optimization with Symmetry Teleportation for Multi-Task Lear
        87476, -- 2411.06780 SynCL: A Synergistic Training Strategy with Instance-Aware Contrastive
        87593, -- 2503.17564 ModalTune: Fine-Tuning Slide-Level Foundation Models with Multi-Modal
        87632, -- 2509.07879 Active Membership Inference Test (aMINT): Enhancing Model Auditability
        87694, -- 2411.15537 MUNBa: Machine Unlearning via Nash Bargaining
        87986, -- 2507.07485 Resolving Token-Space Gradient Conflicts: Token Space Manipulation for
        88092, -- 2501.01184 Vulnerability-Aware Spatio-Temporal Learning for Generalizable Deepfak
        88167, -- 2509.17462 MAESTRO: Task-Relevant Optimization via Adaptive Feature Enhancement a
        88885, -- 2502.14096 Aligned Multi Objective Optimization
        89103, -- 2506.13406 CALM: Consensus-Aware Localized Merging for Multi-Task Learning
        89117, -- 2505.11586 The Ripple Effect: On Unforeseen Complications of Backdoor Attacks
        89636, -- 2401.12526 Refined generalization analysis of the Deep Ritz Method and Physics-In
        89804, -- 2410.15729 A Two-Stage Learning-to-Defer Approach for Multi-Task Learning
        90431, -- 2312.04540 Sim-to-Real Causal Transfer: A Metric Learning Approach to Causally-Aw
        90665, -- 2501.04293 TADFormer: Task-Adaptive Dynamic TransFormer for Efficient Multi-Task
        91009, -- 2411.10013 Efficient Depth Estimation for Unstable Stereo Camera Systems on AR Gl
        91207, -- 2403.04099 Many-Objective Multi-Solution Transport
        91218, -- 2503.06181 Make Haste Slowly: A Theory of Emergent Structured Mixed Selectivity i
        91247, -- 2412.15182 STRAP: Robot Sub-Trajectory Retrieval for Augmented Policy Learning
        91248, -- 2407.11249 Disentangling Representations through Multi-task Learning
        91561, -- 2405.19440 MGDA Converges under Generalized Smoothness, Provably
        91663, -- 2502.14934 Fast and Accurate Blind Flexible Docking
        91695, -- 2405.16206 GlycanML: A Multi-Task and Multi-Structure Benchmark for Glycan Machin
        91870, -- 2502.11986 Selective Task Group Updates for Multi-Task Optimization
        92070, -- 2409.00101 NeuroLM: A Universal Multi-task Foundation Model for Bridging the Gap
        92110, -- 2410.10516 UniGEM: A Unified Approach to Generation and Property Prediction for M
        92740, -- 2602.18591 Ensemble Prediction of Task Affinity for Efficient Multi-Task Learning
        92923, -- 2511.02830 Densemarks: Learning Canonical Embeddings for Human Heads Images via P
        92979, -- 2506.16460 Black-Box Privacy Attacks on Shared Representations in Multitask Learn
        93772, -- 2602.01626 Toward Enhancing Representation Learning in Federated Multi-Task Setti
        95017, -- 2601.21251 Abstracting Robot Manipulation Skills via Mixture-of-Experts Diffusion
        95018, -- 2601.20069 Domain Expansion: A Latent Space Construction Framework for Multi-Task
        95405, -- 2509.18802 Surgical Video Understanding with Label Interpolation
        96433, -- external Neuromorphic Event Camera-Based Object Recognition and Grasping Positi
        97252, -- external Compositional Context Fine-Tuning Vision-Language Model for Complex As
        97362, -- external Multi-Task Visual Perception with Temporal Feature Fusion for Autonomo
        97438, -- external Y-MAP-Net: Learning from Foundation Models for Real-Time, Multi-Task S
        97732, -- external OccLLaMA: A Unified Occupancy-Language-Action World Model for Enhancin
        97990, -- 2412.18988 MTCAE-DFER: Multi-Task Cascaded Autoencoder for Dynamic Facial Express
        98367, -- 1909.12271 RLBench: The Robot Learning Benchmark & Learning Environment
        98385, -- 2201.00206 Learning Free Gait Transition for Quadruped Robots via Phase-Guided Co
        98424, -- 2606.16838 OneRank: Unified Transformer-Native Ranking Architecture for Multi-Tas
        99217, -- 2603.10718 Riemannian MeanFlow for One-Step Generation on Manifolds
        99684, -- 2605.21539 DualOptim+: Bridging Shared and Decoupled Optimizer States for Better
        99700, -- 2606.11057 Flexible Kernels for Protein Property Prediction
        99746, -- 2601.22384 Graph is a Substrate Across Data Modalities
        99779, -- 2606.02221 CORE-MTL: Rethinking Gradient Balancing via Causal Orthogonal Represen
        100676, -- 2508.17742 EEG-FM-Bench: A Comprehensive Benchmark for the Systematic Evaluation
        101084, -- 2601.20774 When More Data Doesn't Help: Limits of Adaptation in Multitask Learnin
        101547, -- 2602.04479 Complexity of Decentralized Optimization with Mixed Affine Constraints
        101620, -- 2605.22635 The Double Dilemma in Multi-Task Radiology Report Generation: A Gradie
        101665, -- 2605.00473 Near-Optimal and Efficient First-Order Algorithm for Multi-Task Learni
        101773, -- 2605.01907 Adaptive Estimation and Inference in Semi-parametric Heterogeneous Clu
        102075, -- 2603.02462 Can Computational Reducibility Lead to Transferable Models for Graph C
        102772, -- 2510.08878 ControlAudio: Tackling Text-Guided, Timing-Indicated and Intelligible
        103132, -- 2511.01526 Difficulty-Controllable Cloze Question Distractor Generation
        103940, -- 1901.08907 Multi-Task Feature Learning for Knowledge Graph Enhanced Recommendatio
        104026, -- 2607.13250 AffectFlow-DINO: Uncertainty-Aware Multi-Task Affect Estimation via Co
        104082, -- 2503.17978 PIM: Physics-Informed Multi-task Pre-training for Improving Inertial S
        104095, -- 2507.00061 Smooth-Distill: A Self-distillation Framework for Multitask Learning w
        104436, -- 2607.15550 SeerGuard: A Safety Framework for Mobile GUI Agents via World Model Pr
        104641, -- 2402.18320 Location-guided Head Pose Estimation for Fisheye Image
        104697, -- external A Multi-Task Learning Framework for Head Pose Estimation under Target
        104920, -- 2507.05020 Adaptation of Multi-modal Representation Models for Multi-task Surgica
        104937, -- external An Anatomical Significance-Aware Architecture for Explainable Myocardi
        104995, -- external Bridging Knowledge Discrepancy in Retinal Image Analysis through Feder
        105189, -- external FDAS: Foundation Model Distillation and Anatomic Structure-aware Multi
        105408, -- external Meta-analysis guided multi-task graph transformer network for diagnosi
        105427, -- external MoMIL: Mixture of Multi-Instance Learners for Modeling Multiple Compou
        105504, -- 2506.20282 Opportunistic Osteoporosis Diagnosis via Texture-Preserving Self-Super
        105552, -- external Predicting Radiation Therapy Response based on Dynamic Temporal Featur
        105642, -- external Self-Propagative Multi-Task Learning for Predicting Cardiometabolic Ri
        105740, -- external Tetra-orientated Mamba with T2-FLAIR Mismatch Features for Glioma Segm
        105839, -- 2509.25518 World Model for AI Autonomous Navigation in Mechanical Thrombectomy
        106948, -- 2601.07474 Task Prototype-Based Knowledge Retrieval for Multi-Task Learning from
        107327, -- 2511.06790 Robust Causal Discovery Under Imperfect Structural Constraints
        107707, -- 2511.12779 Scalable Multi-Objective and Meta Reinforcement Learning via Gradient
        107815, -- 2601.08120 Structure Detection for Contextual Reinforcement Learning
        107879, -- 2511.11676 Learning with Preserving for Continual Multitask Learning
        108260, -- 2511.13079 Decoupling Scene Perception and Ego Status: A Multi-Context Fusion App
        108272, -- 2512.18718 Rectification Reimagined: A Unified Mamba Model for Image Correction a
        108398, -- 2510.18910 Large Connectome Model: An fMRI Foundation Model of Brain Connectomes
        108451, -- 2511.18286 RoadSceneVQA: Benchmarking Visual Question Answering in Roadside Perce
        108974, -- 2608.03573 SFT Conflicts, RL Coexists: A Theoretical and Empirical Analysis of Mu
        108984, -- 2608.06013 OneEmo: A Unified Multimodal Reasoning Model for Emotion Perception, U
        109216, -- 2205.12755 An Evolutionary Approach to Dynamic Introduction of Tasks in Large-sca
        109323, -- 2004.01888 FairMOT: On the Fairness of Detection and Re-Identification in Multipl
        109399, -- 2012.06185 Exploring wav2vec 2.0 on speaker verification and language identificat
        109431, -- 2409.06154 Static for Dynamic: Towards a Deeper Understanding of Dynamic Facial E
        110304, -- 2510.00662 Facilitating Cognitive Accessibility with LLMs: A Multi-Task Approach
        110529, -- 2502.11513 MaZO: Masked Zeroth-Order Optimization for Multi-Task Fine-Tuning of L
        111100, -- external DrFrattn: Directly Learn Adaptive Policy from Attention for Simultaneo
        111273, -- external Addressing Task Conflicts in Stuttering Detection via MMoE-Based Multi
        111408, -- external Count Your Speakers! Multitask Learning for Multimodal Speaker Diariza
        111451, -- 2505.22005 Leveraging LLM for Stuttering Speech: A Unified Architecture Bridging
        111506, -- external Mitigating Overfitting During Speech Foundation Model Fine-tuning: App
        111553, -- external Multimodal and Multitask Learning for Predicting Multiple Scores in L2
        111561, -- external SepVAC: Multitask Learning of Speaker Separation, Speaker Localization
        111886, -- external Speaker-Aware Multi-Task Learning for Speech Emotion Recognition
        111946, -- 2506.10930 Developing a High-performance Framework for Speech Emotion Recognition
        111952, -- external Multi-task learning for speech emotion recognition in naturalistic con
        111953, -- 2506.09556 Medusa: A Multimodal Deep Fusion Multi-Stage Training Framework for Sp
        111959, -- 2508.17878 Enhancing Speech Emotion Recognition with Multi-Task Learning and Dyna
        112015, -- external Multilingual Speech Assessment Using Cross-Attention and Multitask Lea
        112078, -- 2506.09549 A Study on Speech Assessment with Visual Cues
        112086, -- external A-SMiLE: Affective Sparse Mixture-of-Experts Adapter with Multi-Task L
        112093, -- 2506.07515 Speaker-Distinguishable CTC: Learning Speaker Distinction Using CTC fo
        112129, -- external Multitask Learning with Fused Attention for Improved ASR and Mispronun
        112434, -- 2407.08801 DG-PIC: Domain Generalized Point-In-Context Learning for Point Cloud U
        112441, -- external Adaptive Multi-task Learning for Few-shot Object Detection
        112795, -- 2407.10876 RepVF: A Unified Vector Fields Representation for Multi-task 3D Percep
        112829, -- 2407.02846 Multi-Task Domain Adaptation for Language Grounding with 3D Objects
        113577, -- 2409.16651 Learning Representation for Multitask Learning through Self-Supervised
        114111, -- 2609.11156 UniH^3: Unifying Hierarchical Homogeneity and Heterogeneity for All-in
        114363, -- external Airway segmentation based on topological structure enhancement using m
        114428, -- external CausCLIP: Causality-Adapting Visual Scoring of Visual Language Models
        114864, -- external DomainAdapt: Leveraging Multitask Learning and Domain Insights for Chi
        114914, -- external Explanation-driven Cyclic Learning for High-Quality Brain MRI Reconstr
        114959, -- 2407.05726 Gait Patterns as Biomarkers: A Video-Based Approach for Classifying Sc
        115038, -- 2403.03891 Joint multi-task learning improves weakly-supervised biomarker predict
        115139, -- external mQSM: Multitask Learning-based Quantitative Susceptibility Mapping for
        115142, -- 2405.13771 Multi-Dataset Multi-Task Learning for COVID-19 Prognosis
        115144, -- external Multi-Frequency and Smoke Attention-aware Learning based Diffusion Mod
        115163, -- external NeuroLink: Bridging Weak Signals in Neuronal Imaging with Morphology L
        115681, -- 2312.00834 AV-RIR: Audio-Visual Room Impulse Response Estimation
        116259, -- 2311.13250 FedHCA2: Towards Hetero-Client Federated Multi-Task Learning
        116388, -- 2403.14158 Volumetric Environment Representation for Vision-Language Navigation
        116579, -- 2401.13856 LAA-Net: Localized Artifact Attention Network for Quality-Agnostic and
        116638, -- 2405.14136 Efficient Multitask Dense Predictor via Binarization
        116798, -- 2406.02996 Quantifying Task Priority for Multi-Task Optimization
        116803, -- 2404.02072 EGTR: Extracting Graph from Transformer for Scene Graph Generation
        116841, -- 2405.06284 Modality-agnostic Domain Generalizable Medical Image Segmentation by M
        116904, -- 2404.14471 Narrative Action Evaluation with Prompt-Guided Multimodal Interaction
        117077, -- 2507.13364 OmniVec2 - A Novel Transformer based Network for Large Scale Multimoda
        117145, -- 2404.01976 Joint-Task Regularization for Partially Labeled Multi-Task Learning
        117678, -- 2606.30047 Argus: Metric Panoramic 3D Reconstruction for Indoor Scenes
        118198, -- 2502.08585 LDC-MTL: Balancing Multi-Task Learning through Scalable Loss Discrepan
        118203, -- 2606.30370 MUSE: Unlocking Timestep as Native Task Steering for One-Step Dense Pr
        118204, -- external RUTaL: Residual Upcycling with Task Ladder for Efficient Multi-Task Le
        118231, -- 2607.19384 SUM: Unified Geometric Surgery on Spatio-Temporal Adaptation Vectors f
        119312, -- 2604.06010 OmniCamera: A Unified Framework for Multi-task Video Generation with A
        119893, -- 2502.06029 DiTASK: Multi-Task Fine-Tuning with Diffeomorphic Transformations
        119902, -- 2504.02264 MMTL-UniAD: A Unified Framework for Multimodal and Multi-Task Learning
        120006, -- external Joint Scheduling of Causal Prompts and Tasks for Multi-Task Learning
        120045, -- external Towards Consistent Multi-Task Learning: Unlocking the Potential of Tas
        120058, -- 2503.12124 Z-Magic: Zero-shot Multiple Attributes Guided Image Creator
        120165, -- external Revisiting Fairness in Multitask Learning: A Performance-Driven Approa
        120383, -- external SKE-Layout: Spatial Knowledge Enhanced Layout Generation with LLMs
        120405, -- external ALIEN: Implicit Neural Representations for Human Motion Prediction und
        120552, -- external Identifying and Mitigating Spurious Correlation in Multi-Task Learning
        120820, -- 2603.21111 Frequency Switching Mechanism for Parameter-Efficient Multi-Task Learn
        121299, -- 2512.01022 CycleManip: Enabling Cycle-based Manipulation via Effective History Pe
        121305, -- external TaskForce: Cooperative Multi-agent Reinforcement Learning for Multi-ta
        121386, -- external Dual-Prototype-Guided Multi-task Learning for Unsupervised Anomaly Det
        123732, -- 2010.07954 Room-Across-Room: Multilingual Vision-and-Language Navigation with Den
        124191, -- external Hydra: Towards Transferable Multi-Task Learning on Temporal Graphs
        124457, -- external A Margin Perspective on LoRA: Robustness to Catastrophic Forgetting an
        124512, -- 2512.00469 FairMT: Fairness for Heterogeneous Multi-Task Learning
        125342, -- 2603.05066 Reward-Conditioned Reinforcement Learning
        125720, -- 2512.08814 Ask, Answer, and Detect: Role-Playing LLMs for Personality Detection w
        126582, -- 2605.09355 FLAME: Adaptive Mixture-of-Experts for Continual Multimodal Multi-Task
        126842, -- external Balanced Multi-Task Learning from an Optimality-Gap Perspective
        127473, -- 2604.08939 Delve into the Applicability of Advanced Optimizers for Multi-Task Lea
        127499, -- 2608.18982 Monroe: A Molecular Foundation Model for In-context Probabilistic Infe
        127681, -- external Curvature-Guided Parameter Initialization for Multi-Task Learning
        128893, -- 2606.03904 MAdam: Metric-Aware Multi-Objective Adam
        128958, -- external Leveraging Dale’s Principle as an Inductive Bias in Recurrent Neural N
        129691, -- 2610.06397 Learning Pareto Stationary Fronts via Single-Pass Backpropagation
        130267, -- 2605.09879 M2A: Synergizing Mathematical and Agentic Reasoning in Large Language
        130509, -- external Rare-Class Signal Suppression in Long-Tailed Multi-Expert Fine-Tuning
        131418  -- external CH-SIMS: A Chinese Multimodal Sentiment Analysis Dataset with Fine-gra
  );

DELETE FROM paper_method_exclusions x
USING multi_task_learning_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM multi_task_learning_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM multi_task_learning_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE multi_task_learning_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'multi-task-learning'
  AND p.id IN (
        837, -- 1708.02901 Transitive Invariance for Self-supervised Visual Representation Learni
        12098, -- 2212.09849 Dataless Knowledge Fusion by Merging Weights of Language Models
        108673, -- 1910.01717 On the Detection of Digital Face Manipulation
        127563  -- external Loop alignment: Self-organized Weight Transpose in Predictive Coding t
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM multi_task_learning_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING multi_task_learning_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING multi_task_learning_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- curriculum-learning: 385 links, 0 exclusions.
CREATE TEMP TABLE curriculum_learning_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'curriculum-learning'
  AND p.id IN (
        830, -- 1708.01354 CASSL: Curriculum Accelerated Self-Supervised Learning
        1253, -- 1805.00833 Learnable PINs: Cross-Modal Embeddings for Person Identity
        2048, -- 1904.12584 The Neuro-Symbolic Concept Learner: Interpreting Scenes, Words, and Se
        2687, -- 1910.07224 Teacher algorithms for curriculum learning of Deep RL in continuously
        2743, -- 1910.13427 Distribution Density, Tails, and Outliers in Machine Learning: Metrics
        3103, -- 2002.06306 Jelly Bean World: A Testbed for Never-Ending Learning
        3202, -- 2003.04664 Automatic Curriculum Learning For Deep RL: A Short Survey
        3450, -- 2004.14269 Training Curricula for Open Domain Answer Re-Ranking
        3834, -- 2006.16779 PLATO-2: Towards Building an Open-Domain Chatbot via Curriculum Learni
        4025, -- 2008.06456 Mastering Rate based Curriculum Learning
        4567, -- 2011.08463 Meta Automatic Curriculum Learning
        5215, -- 2103.09504 PredRNN: A Recurrent Neural Network for Spatiotemporal Predictive Lear
        5220, -- 2103.09815 TeachMyAgent: a Benchmark for Automatic Curriculum Learning in Deep RL
        5350, -- 2104.00650 Frozen in Time: A Joint Video and Image Encoder for End-to-End Retriev
        5689, -- 2105.04475 Self-Guided Curriculum Learning for Neural Machine Translation
        5832, -- 2106.00291 Preview, Attend and Review: Schema-Aware Curriculum Learning for Multi
        7514, -- 2112.08288 Improving Both Domain Robustness and Domain Adaptability in Machine Tr
        7725, -- 2201.07365 Improving Neural Machine Translation by Denoising Training
        7855, -- 2202.01344 Formal Mathematics Statement Curriculum Learning
        7936, -- 2202.05531 Cyclical Curriculum Learning
        7958, -- 2202.06823 Development and Comparison of Scoring Functions in Curriculum Learning
        8026, -- 2202.10222 Robots Learn Increasingly Complex Tasks with Intrinsic Motivation and
        8569, -- 2204.02030 $\textit{latent}$-GLAT: Glancing at Latent Variables for Parallel Text
        8655, -- 2204.04812 OutfitTransformer: Learning Outfit Representations for Fashion Recomme
        9901, -- 2207.12644 Learning Bipedal Walking On Planned Footsteps For Humanoid Robots
        9921, -- 2207.13703 SoundChoice: Grapheme-to-Phoneme Models with Semantic Disambiguation
        10648, -- 2210.03980 Distilling Causal Effect from Miscellaneous Other-Class for Continual
        10844, -- 2210.08713 Supervised Prototypical Contrastive Learning for Emotion Recognition i
        10890, -- 2210.10243 CLUTR: Curriculum Learning via Unsupervised Task Representation Learni
        11075, -- 2210.14724 Improving Imbalanced Text Classification with Dynamic Curriculum Learn
        11211, -- 2211.02077 Scaling Multimodal Pre-Training via Cross-Modality Gradient Harmonizat
        11409, -- 2211.09703 EfficientTrain: Exploring Generalized Curriculum Learning for Training
        11664, -- 2211.15470 Learning to Learn: How to Continuously Teach Humans and Machines
        11978, -- 2212.07571 Fixing MoE Over-Fitting on Low-Resource Languages in Multilingual Mach
        12214, -- 2212.12712 When Do Curricula Work in Federated Learning?
        12219, -- 2212.12809 Understanding the Complexity Gains of Single-Task RL with a Curriculum
        12298, -- 2301.01661 RecRecNet: Rectangling Rectified Wide-Angle Images by Thin-Plate Splin
        12310, -- 2301.01949 SPRING: Situated Conversation Agent Pretrained with Multimodal Questio
        12592, -- 2301.11796 Call for Papers -- The BabyLM Challenge: Sample-efficient pretraining
        12674, -- 2301.13105 Generalization on the Unseen, Logic Reasoning and Degree Curriculum
        12770, -- 2302.00954 Curriculum-guided Abstractive Summarization for Mental Health Online P
        13112, -- 2302.07515 TiZero: Mastering Multi-Agent Football with Curriculum Learning and Se
        13608, -- 2303.05309 MixSpeech: Cross-Modality Self-Learning with Audio-Visual Stream Mixup
        14092, -- 2303.13931 MSdocTr-Lite: A Lite Transformer for Full Page Multi-script Handwritin
        14373, -- 2304.00464 UniDexGrasp++: Improving Dexterous Grasping Policy Learning via Geomet
        15012, -- 2304.14118 Learning Neural PDE Solvers with Parameter-Guided Channel Attention
        15268, -- 2305.03610 The Role of Data Curation in Image Captioning
        15370, -- 2305.05383 Code Execution with Pre-trained Language Models
        16787, -- 2306.00890 LLaVA-Med: Training a Large Language-and-Vision Assistant for Biomedic
        18189, -- 2307.06018 PolyLM: An Open Source Polyglot Large Language Model
        18767, -- 2307.16184 UnIVAL: Unified Model for Image, Video, Audio and Language Tasks
        18982, -- 2308.03282 Environment-Invariant Curriculum Relation Learning for Fine-Grained Sc
        19316, -- 2308.08285 Pre-training with Large Language Model-based Document Expansion for De
        19335, -- 2308.08625 BIOptimus: Pre-training an Optimal Biomedical Language Model with Curr
        19425, -- 2308.09611 Language-guided Human Motion Synthesis with Atomic Actions
        19495, -- 2308.10155 Unilaterally Aggregated Contrastive Learning with Hierarchical Augment
        19668, -- 2308.11901 Camera-Driven Representation Learning for Unsupervised Domain Adaptive
        19697, -- 2308.12202 Curriculum Learning with Adam: The Devil Is in the Wrong Details
        20210, -- 2309.03989 CDFSL-V: Cross-Domain Few-Shot Learning for Videos
        21766, -- 2310.07188 Adaptive Gating in Mixture-of-Experts based Language Models
        22228, -- 2310.12931 Eureka: Human-Level Reward Design via Coding Large Language Models
        22456, -- 2310.15539 SteloCoder: a Decoder-Only LLM for Multi-Language to Python Code Trans
        23355, -- 2311.08886 CLIMB: Curriculum Learning for Infant-inspired Model Building
        23642, -- 2311.13081 Learning to Fly in Seconds
        23909, -- 2311.17050 Surf-D: Generating High-Quality Surfaces of Arbitrary Topologies Using
        24092, -- 2312.00249 Acoustic Prompt Tuning: Empowering Large Language Models with Audition
        24425, -- 2312.04326 iDesigner: A High-Resolution and Complex-Prompt Following Text-to-Imag
        26776, -- 2402.02544 LHRS-Bot: Empowering Remote Sensing with VGI-Enhanced Large Multimodal
        27308, -- 2402.09141 Advancing NLP Models with Strategic Text Augmentation: A Comprehensive
        27693, -- 2402.13250 Video ReCap: Recursive Captioning of Hour-Long Videos
        28334, -- 2403.01636 Sample Efficient Myopic Exploration Through Multitask Reinforcement Le
        28701, -- 2403.07230 Curry-DPO: Enhancing Alignment using Curriculum Learning & Ranked Pref
        28920, -- 2403.10348 Denoising Task Difficulty-based Curriculum for Training Diffusion Mode
        29059, -- 2403.12014 EnvGen: Generating and Adapting Environments via LLMs for Training Emb
        29655, -- 2403.20012 Colorful Cutout: Enhancing Image Data Augmentation with Curriculum Lea
        29726, -- 2404.00656 WavLLM: Towards Robust and Adaptive Speech Large Language Model
        29944, -- 2404.03558 How does Multi-Task Training Affect Transformer In-Context Capabilitie
        30730, -- 2404.15702 Nyonic Technical Report
        31276, -- 2405.08295 SpeechVerse: A Large-scale Generalizable Audio Language Model
        31441, -- 2405.12105 End-to-End Full-Page Optical Music Recognition for Pianoform Sheet Mus
        31525, -- 2405.13637 Curriculum Direct Preference Optimization for Diffusion and Consistenc
        32074, -- 2405.20216 Boost Your Human Image Generation Model via Direct Preference Optimiza
        32174, -- 2406.00380 HonestLLM: Toward an Honest and Helpful Large Language Model
        33381, -- 2406.14219 Proving Olympiad Algebraic Inequalities without Human Demonstrations
        34013, -- 2407.02005 An End-to-End Speech Summarization Using Large Language Model
        34040, -- 2407.02315 VFIMamba: Video Frame Interpolation with State Space Models
        34104, -- 2407.03203 TheoremLlama: Transforming General-Purpose LLMs into Lean4 Experts
        34141, -- 2407.03656 WildDESED: An LLM-Powered Dataset for Wild Domestic Environment Sound
        34309, -- 2407.06048 Vision-Braille: An End-to-End Tool for Chinese Braille Image-to-Text T
        34626, -- 2407.10194 Curriculum Learning for Small Code Language Models
        36761, -- 2409.07045 Beyond IID: Optimizing Instruction Learning from the Perspective of In
        37107, -- 2409.13183 $\textit{SKIntern}$: Internalizing Symbolic Knowledge for Distilling B
        37181, -- 2409.14485 Video-XL: Extra-Long Vision Language Model for Hour-Scale Video Unders
        38103, -- 2410.06209 LeanAgent: Lifelong Learning for Formal Theorem Proving
        38594, -- 2410.12312 FaceChain-FACT: Face Adapter with Decoupled Training for Identity-pres
        38725, -- 2410.13674 Diffusion Curriculum: Synthetic-to-Real Generative Curriculum Learning
        39318, -- 2410.21728 Let's Be Self-generated via Step by Step: A Curriculum Learning Approa
        39378, -- 2410.22886 Less is More: Pre-Training Cross-Lingual Small-Scale Language Models w
        39453, -- 2410.24050 Clustering Head: A Visual Case Study of the Training Dynamics in Trans
        39692, -- 2411.03957 Fine-Grained Guidance for Retrievers: Leveraging LLMs' Feedback in Ret
        40095, -- 2411.11098 MolParser: End-to-end Visual Recognition of Molecule Structures in the
        40574, -- 2411.18126 Curriculum Demonstration Selection for In-Context Learning
        40775, -- 2412.00626 MambaNUT: Nighttime UAV Tracking via Mamba-based Adaptive Curriculum L
        42027, -- 2412.16589 Improving FIM Code Completions via Context & Curriculum Based Learning
        42270, -- 2412.20211 Generative Regression Based Watch Time Prediction for Short-Video Reco
        42644, -- 2501.04945 Step-by-Step Mastery: Enhancing Soft Constraint Following Ability of L
        42651, -- 2501.04982 CuRLA: Curriculum Learning Based Deep Reinforcement Learning for Auton
        42706, -- 2501.05952 Scalable Vision Language Model Training via High Quality Data Curation
        42720, -- 2501.06186 LlamaV-o1: Rethinking Step-by-step Visual Reasoning in LLMs
        43648, -- 2502.02358 MotionLab: Unified Human Motion Generation and Editing via the Motion-
        43889, -- 2502.05855 DexVLA: Vision-Language Model with Plug-In Diffusion Expert for Genera
        44048, -- 2502.07709 MAGELLAN: Metacognitive predictions of learning progress guide autotel
        44665, -- 2502.14565 ReVISE: Learning to Refine at Test-Time via Intrinsic Self-Verificatio
        44957, -- 2502.17543 Training a Generally Curious Agent
        44976, -- 2502.17910 Scaling LLM Pre-training with Vocabulary Curriculum
        45474, -- 2503.03285 Enhancing Vietnamese VQA through Curriculum Learning on Raw and Augmen
        45519, -- 2503.03983 Audio Flamingo 2: An Audio-Language Model with Long-Audio Understandin
        45648, -- 2503.05978 MagicInfinite: Generating Infinite Talking Videos with Your Words and
        45970, -- 2503.09481 BAMBI: Developing Baby Language Models for Italian
        46134, -- 2503.11227 GKG-LLM: A Unified Framework for Generalized Knowledge Graph Construct
        46219, -- 2503.12759 RAG-RL: Advancing Retrieval-Augmented Generation via RL and Curriculum
        46329, -- 2503.14350 VEGGIE: Instructional Editing and Reasoning Video Concepts with Ground
        46525, -- 2503.16929 TEMPLE:Temporal Preference Learning of Video LLMs via Difficulty Sched
        46577, -- 2503.17735 RDTF: Resource-efficient Dual-mask Training Framework for Multi-frame
        47152, -- 2504.01395 From Easy to Hard: Building a Shortcut for Differentially Private Imag
        47168, -- 2504.01792 UniViTAR: Unified Vision Transformer with Native Resolution
        47288, -- 2504.03380 Online Difficulty Filtering for Reasoning Oriented Reinforcement Learn
        47378, -- 2504.05287 RobustDexGrasp: Robust Dexterous Grasping of General Objects
        47394, -- 2504.05520 Efficient Reinforcement Finetuning via Adaptive Curriculum Learning
        47626, -- 2504.09710 DUMP: Automated Distribution-Level Curriculum Learning for RL-based LL
        48043, -- 2504.15900 SARI: Structured Audio Reasoning via Curriculum-Guided Reinforcement L
        48341, -- 2505.01481 VideoHallu: Evaluating and Mitigating Multi-modal Hallucinations on Sy
        48598, -- 2505.06584 JAEGER: Dual-Level Humanoid Whole-Body Controller
        48681, -- 2505.08364 Learning Like Humans: Advancing LLM Reasoning Capabilities via Adaptiv
        48791, -- 2505.10597 Two Minds Better Than One: Collaborative Reward Modeling for LLM Align
        48987, -- 2505.12697 Towards A Generalist Code Embedding Model Based On Massive Data Synthe
        49019, -- 2505.13026 Step-wise Adaptive Integration of Supervised Fine-tuning and Reinforce
        49072, -- 2505.13447 Mean Flows for One-step Generative Modeling
        49147, -- 2505.14256 FuxiMT: Sparsifying Large Language Models for Chinese-Centric Multilin
        49245, -- 2505.14970 Self-Evolving Curriculum for LLM Reasoning
        49399, -- 2505.16368 SATURN: SAT-based Reinforcement Learning to Unleash Language Model Rea
        49402, -- 2505.16400 AceReason-Nemotron: Advancing Math and Code Reasoning through Reinforc
        49530, -- 2505.17558 Teaching with Lies: Curriculum DPO on Synthetic Negatives for Hallucin
        49854, -- 2505.20285 MASKSEARCH: A Universal Pre-Training Framework to Enhance Agentic Sear
        50036, -- 2505.22757 Pre-Training Curriculum for Multi-Token Prediction in Language Models
        50324, -- 2506.00555 MMedAgent-RL: Optimizing Multi-Agent Collaboration for Multimodal Medi
        50338, -- 2506.00830 SkyReels-Audio: Omni Audio-Conditioned Talking Portraits in Video Diff
        50439, -- 2506.02281 Angles Don't Lie: Unlocking Training-Efficient RL Through the Model's
        50650, -- 2506.05328 AV-Reasoner: Improving and Benchmarking Clue-Grounded Audio-Visual Cou
        51034, -- 2506.10892 The Diffusion Duality
        51310, -- 2506.16962 Enhancing Step-by-Step and Verifiable Medical Reasoning in MLLMs
        51500, -- 2506.21230 World-aware Planning Narratives Enhance Large Vision-Language Model Pl
        51763, -- 2507.06167 Skywork-R1V3 Technical Report
        51863, -- 2507.09318 ZipVoice-Dialog: Non-Autoregressive Spoken Dialogue Generation with Fl
        51999, -- 2507.15205 Long-Short Distance Graph Neural Networks and Improved Curriculum Lear
        52046, -- 2507.17512 Can One Domain Help Others? A Data-Centric Study on Multi-Domain   Rea
        52192, -- 2508.02324 Qwen-Image Technical Report
        52325, -- 2508.08665 Aryabhata: An exam-focused language model for JEE Math
        52332, -- 2508.08940 Train Long, Think Short: Curriculum Learning for Efficient Reasoning
        52701, -- 2509.06949 Revolutionizing Reinforcement Learning Framework for Diffusion Large
        53121, -- 2510.01037 CurES: From Gradient Analysis to Efficient Curriculum Learning for   R
        53469, -- 2510.11769 GAR: Generative Adversarial Reinforcement Learning for Formal Theorem
        53646, -- 2510.15742 Scaling Instruction-Based Video Editing with a High-Quality Synthetic
        53725, -- 2510.18795 ProCLIP: Progressive Vision-Language Alignment via LLM-based Embedder
        53735, -- 2510.15710 Unimedvl: Unifying Medical Multimodal Understanding And Generation   T
        54079, -- 2511.03773 Scaling Agent Learning via Experience Synthesis
        54132, -- 2511.07061 Do LLMs Feel? Teaching Emotion Recognition with Prompts, Retrieval, an
        54199, -- 2511.09915 HI-TransPA: Hearing Impairments Translation Personal Assistant
        54323, -- 2511.18050 UltraFlux: Data-Model Co-Design for High-quality Native 4K Text-to-Ima
        54450, -- 2511.23404 LFM2 Technical Report
        54482, -- 2512.00077 A Hierarchical Framework for Humanoid Locomotion with Supernumerary Li
        54646, -- 2512.06835 Decouple to Generalize: Context-First Self-Evolving Learning for Data-
        54875, -- 2512.16649 JustRL: Scaling a 1.5B LLM with a Simple RL Recipe
        55206, -- 2601.04888 SmartSearch: Process Reward-Guided Query Refinement for Search Agents
        55424, -- 2601.13044 Typhoon ASR Real-time: FastConformer-Transducer for Thai Automatic Spe
        55480, -- 2601.16018 Mecellem Models: Turkish Models Trained from Scratch and Continually P
        55859, -- 2601.18415 Pisets: A Robust Speech Recognition System for Lectures and Interviews
        56022, -- 2602.10229 Latent Thoughts Tuning: Bridging Context and Reasoning with Fused Info
        56067, -- 2602.08194 Dreaming in Code for Curriculum Learning in Open-Ended Worlds
        56265, -- 2602.21193 On Data Engineering for Scaling LLM Terminal Capabilities
        56466, -- 2603.03379 MemSifter: Offloading LLM Memory Retrieval via Outcome-Driven Proxy Re
        56964, -- 2603.22458 MinerU-Diffusion: Rethinking Document OCR as Inverse Rendering via Dif
        57125, -- 2603.29852 VectorGym: A Multitask Benchmark for SVG Code Generation, Sketching, a
        57265, -- 2604.04767 Cog-DRIFT: Exploration on Adaptively Reformulated Instances Enables Le
        58395, -- 2604.07879 FlowGuard: Towards Lightweight In-Generation Safety Detection for Diff
        58718, -- 2604.00076 Learning to Play Blackjack: A Curriculum Learning Perspective
        58811, -- 2603.27226 Rethinking Easy-to-Hard: Limits of Curriculum Learning in Post-Trainin
        58923, -- 2603.24589 YingMusic-Singer: Controllable Singing Voice Synthesis with Flexible L
        58970, -- 2603.23308 Curriculum-Driven 3D CT Report Generation via Language-Free Visual Gra
        59375, -- 2506.06632 Curriculum Reinforcement Learning from Easy to Hard Tasks Improves LLM
        59479, -- 2603.12967 Language-Grounded Decoupled Action Representation for Robotic Manipula
        59577, -- 2603.11089 V2A-DPO: Omni-Preference Optimization for Video-to-Audio Generation
        59634, -- 2603.09326 OddGridBench: Exposing the Lack of Fine-Grained Visual Discrepancy Sen
        59678, -- 2603.08182 TildeOpen LLM: Leveraging Curriculum Learning to Achieve Equitable Lan
        60137, -- 2603.00578 Draft-Thinking: Learning Efficient Reasoning in Long Chain-of-Thought
        60290, -- 2602.21628 RuCL: Stratified Rubric-Based Curriculum Learning for Multimodal Large
        60355, -- 2602.20426 Learning to Rewrite Tool Descriptions for Reliable LLM-Agent Tool Use
        60727, -- 2602.17709 UBio-MolFM: A Universal Molecular Foundation Model for Bio-Systems
        61191, -- 2602.05165 EBPO: Empirical Bayes Shrinkage for Stabilizing Group-Relative Policy
        61434, -- 2602.02096 WADEPre: A Wavelet-based Decomposition Model for Extreme Precipitation
        61812, -- 2601.21711 TACLer: Tailored Curriculum Reinforcement Learning for Efficient Reaso
        61918, -- 2601.20305 Endogenous Reprompting: Self-Evolving Cognitive Alignment for Unified
        62055, -- 2601.18296 Temp-R1: A Unified Autonomous Agent for Complex Temporal KGQA via Reve
        62262, -- 2601.14615 SearchGym: Bootstrapping Real-World Search Agents via Cost-Effective a
        62298, -- 2601.13802 Habibi: Laying the Open-Source Foundation of Unified-Dialectal Arabic
        62446, -- 2601.11658 Towards AGI A Pragmatic Approach Towards Self Evolving Agent
        62907, -- 2601.03725 EDCO: Dynamic Curriculum Orchestration for Domain-specific Large Langu
        63257, -- 2512.22854 ByteLoom: Weaving Geometry-Consistent Human-Object Interactions throug
        63741, -- 2512.12633 DiG: Differential Grounding for Enhancing Fine-Grained Perception in M
        63985, -- 2512.07454 Persian-Phi: Efficient Cross-Lingual Adaptation of Compact LLMs via Cu
        64132, -- 2512.04359 Efficient Reinforcement Learning with Semantic and Token Entropy for L
        64171, -- 2512.11831 On the Design of One-step Diffusion via Shortcutting Flow Paths
        64281, -- 2512.01512 MCAT: Scaling Many-to-Many Speech-to-Text Translation with MLLMs to 70
        64782, -- 2511.16326 ARK: Answer-Centric Retriever Tuning via KG-augmented Curriculum Learn
        65149, -- 2511.08555 RESTL: Reinforcement Learning Guided by Multi-Aspect Rewards for Signa
        65185, -- 2511.08653 Accelerating Training Speed of Tiny Recursive Models with Curriculum G
        65692, -- 2511.01894 LGCC: Enhancing Flow Matching Based Text-Guided Image Editing with Loc
        66230, -- 2510.16476 NP-Engine: Empowering Optimization Reasoning in Large Language Models
        66487, -- 2510.11474 Coordinated Strategies in Realistic Air Combat by Hierarchical Multi-A
        66821, -- 2510.06826 Mid-Training of Large Language Models: A Survey
        67178, -- 2510.01135 Prompt Curriculum Learning for Efficient LLM Post-Training
        67353, -- 2509.25779 Planner-R1: Reward Shaping Enables Efficient Agentic RL with Smaller
        67420, -- 2509.25004 CLPO: Curriculum Learning meets Policy Optimization for LLM Reasoning
        67542, -- 2509.23841 Towards Fine-Grained Text-to-3D Quality Assessment: A Benchmark and A
        67706, -- 2509.22115 Learning More with Less: A Dynamic Dual-Level Down-Sampling Framework
        68176, -- 2509.15389 Exploring Fine-Tuning of Large Audio Language Models for Spoken Langua
        68415, -- 2509.11287 Mitigating Hallucinations in Large Vision-Language Models by   Self-In
        68873, -- 2509.01411 MILO: A Lightweight Perceptual Quality Metric for Image and Latent-Spa
        69167, -- 2508.18701 Attention2Probability: Attention-Driven Terminology Probability   Esti
        69363, -- 2508.15495 SynthCoder: A Synthetical Strategy to Tune LLMs for Code Completion
        69365, -- 2508.15475 Influence-driven Curriculum Learning for Pre-training on Limited Data
        69625, -- 2508.11360 CRAFT-GUI: Curriculum-Reinforced Agent For GUI Tasks
        69873, -- 2508.07809 EvoCoT: Overcoming the Exploration Bottleneck in Reinforcement Learnin
        70108, -- 2508.09168 SVGen: Interpretable Vector Graphics Generation with Large Language
        70234, -- 2508.03018 Beyond Policy Optimization: A Data Curation Flywheel for Sparse-Reward
        70272, -- 2508.02362 Text2Lip: Progressive Lip-Synced Talking Face Generation from Text via
        70974, -- 2507.14783 Omni-Thinker: Scaling Cross-Domain Generalization in LLMs via Multi-Ta
        71162, -- 2507.10628 GHPO: Adaptive Guidance for Stable and Efficient LLM Reinforcement   L
        71203, -- 2507.09374 EduFlow: Advancing MLLMs' Problem-Solving Proficiency through Multi-St
        71305, -- 2507.06815 Data-Balanced Curriculum Learning for Audio Question Answering
        71396, -- 2505.13860 Domain Adaptation of VLM for Soccer Video Understanding
        71436, -- 2507.03779 FastDINOv2: Frequency Based Curriculum Learning Improves Robustness an
        71533, -- 2507.01327 Reasoner for Real-World Event Detection: Scaling Reinforcement Learnin
        71934, -- 2506.14168 VideoMAR: Autoregressive Video Generatio with Continuous Tokens
        72029, -- 2506.11300 Beyond Random Sampling: Efficient Language Model Pretraining via   Cur
        72213, -- 2506.05843 FontAdapter: Instant Font Adaptation in Visual Text Generation
        72499, -- 2506.00288 Emergent Abilities of Large Language Models under Continued Pretrainin
        72596, -- 2505.22042 Estimating the Effects of Sample Training Orders for Large Language
        73784, -- 2504.00640 POPEN: Preference-Based Optimization and Ensemble for LVLM-Based Reaso
        73883, -- 2503.19311 DGTRSD & DGTRS-CLIP: A Dual-Granularity Remote Sensing Image-Text   Da
        73885, -- 2411.13059 Towards Unbiased and Robust Spatio-Temporal Scene Graph Generation and
        74411, -- 2502.20678 STPro: Spatial and Temporal Progressive Learning for Weakly Supervised
        74492, -- 2502.17793 SYNTHIA: Novel Concept Design with Affordance Composition
        74538, -- 2502.15442 Learning Long-Horizon Robot Manipulation Skills via Privileged Action
        74831, -- 2502.05378 NextBestPath: Efficient 3D Mapping of Unseen Environments
        75359, -- 2412.18524 HTR-JAND: Handwritten Text Recognition with Joint Attention Network an
        76445, -- 2409.04730 IR2: Implicit Rendezvous for Robotic Exploration Teams under Sparse
        76602, -- 2408.05326 A Psychology-based Unified Dynamic Framework for Curriculum Learning
        77578, -- 2403.16535 Arm-Constrained Curriculum Learning for Loco-Manipulation of the   Whe
        78033, -- 2312.16995 FlowDA: Unsupervised Domain Adaptive Framework for Optical Flow Estima
        79388, -- 2302.01342 Curriculum-Guided Abstractive Summarization
        80025, -- 2205.00275 Dynamic Curriculum Learning for Great Ape Detection in the Wild
        80873, -- 2102.09777 Progressive Transformer-Based Generation of Radiology Reports
        81380, -- 2004.03672 Dynamic Data Selection and Weighting for Iterative Back-Translation
        81472, -- 2001.06001 Curriculum Labeling: Revisiting Pseudo-Labeling for Semi-Supervised Le
        81595, -- 1909.10642 Data Ordering Patterns for Neural Machine Translation: An Empirical St
        83425, -- 2604.03472 Vocabulary Dropout for Curriculum Diversity in LLM Co-Evolution
        84214, -- 2511.18378 Synthetic Curriculum Reinforces Compositional Text-to-Image Generation
        84445, -- 2512.22647 FinPercep-RM: A Fine-grained Reward Model and Co-evolutionary Curricul
        84488, -- 2601.15408 CURE: Curriculum-guided Multi-task Training for Reliable Anatomy Groun
        84821, -- 2603.09101 MedKCO: Medical Vision-Language Pretraining via Knowledge-Driven Cogni
        85087, -- 2603.24322 Heuristic Self-Paced Learning for Domain Adaptive Semantic Segmentatio
        85288, -- 2604.05354 Unsupervised Multi-agent and Single-agent Perception from Cooperative
        85479, -- 2604.28193 Generalizable Sparse-View 3D Reconstruction from Unconstrained Images
        85537, -- 2605.09802 CrossVL: Complexity-Aware Feature Routing and Paired Curriculum for Cr
        87050, -- 2505.15133 DeepKD: A Deeply Decoupled and Denoised Knowledge Distillation Trainer
        87745, -- 2509.17040 From Easy to Hard: The MIR Benchmark for Progressive Interleaved Multi
        89740, -- 2506.13485 Curriculum Learning for Biological Sequence Prediction: The Case of De
        89843, -- 2205.10016 Learning Progress Driven Multi-Agent Curriculum
        89860, -- 2505.06744 LineFlow: A Framework to Learn Active Control of Production Lines
        89949, -- 2502.01046 Emotional Face-to-Speech
        90042, -- 2505.16080 SynEVO: A neuro-inspired spatiotemporal evolutional framework for cros
        90838, -- 2404.00916 Gyro-based Neural Single Image Deblurring
        90882, -- 2411.10685 From Prototypes to General Distributions: An Efficient Curriculum for
        92243, -- 2408.04591 HiLo: A Learning Framework for Generalized Category Discovery Robust t
        92367, -- 2502.15832 DeepRTL: Bridging Verilog Understanding and Generation with a Unified
        92619, -- 2605.28828 Micro-Macro Retrieval: Reducing Long-Form Hallucination in Large Langu
        92866, -- 2506.18110 RL for Reasoning by Adaptively Revealing Rationales
        93155, -- 2512.14722 HATSolver: Learning Gröbner Bases with Hierarchical Attention Transfor
        93878, -- 2510.26792 Learning Pseudorandom Numbers with Transformers: Permuted Congruential
        94610, -- 2507.16663 Turning Internal Gap into Self-Improvement: Promoting the Generation-U
        94790, -- 2509.26140 OWL : Geometry-Aware Spatial Reasoning for Audio Large Language Models
        94947, -- 2604.10075 Learning Hierarchical and Geometry-Aware Graph Representations for Tex
        95400, -- 2509.13229 Curriculum Multi-Task Self-Supervision Improves Lightweight Architectu
        95754, -- external MAKP: Multi-Mode Accurate Kicking Policy for Humanoid Robots
        95817, -- 2505.12679 Dribble Master: Learning Agile Humanoid Dribbling through Legged Locom
        95879, -- 2510.20174 Reinforcement Learning-Based Robust Wall Climbing Locomotion Controlle
        96184, -- external PDLNet: Learning Point Cloud Distortion for Unsupervised Cross-Domain
        96367, -- external LeGO-MM: Learning Navigation for Goal-Oriented Mobile Manipulation Via
        96684, -- 2505.08222 Scaling Multi-Agent Reinforcement Learning for Underwater Acoustic Tra
        97122, -- external MoE-Powered Fast VLMs Via Curriculum Learning-Based Knowledge Distilla
        97166, -- 2506.03896 FLIP: Flowability-Informed Powder Weighing
        97342, -- 2411.13438 Robust Monocular Visual Odometry Via Dual-Paradigm Curriculum Learning
        97374, -- external Scalable Multi-Agent Reinforcement Learning Framework for Multi-Machin
        97807, -- 2504.04516 DexSinGrasp: Learning a Unified Policy for Dexterous Object Singulatio
        97870, -- external Heterogeneous Skill Learning for Asynchronous Multi-Robot Relay Pushin
        98553, -- external Regressive Plasticity Schedule: A Two-Stage Post-Training Schedule for
        98675, -- 2606.19827 When, Where, and How: Adaptive Binning for Tabular Self-Supervised Lea
        98686, -- 2606.19750 Manifold Bandits: Bayesian Curriculum Learning over the Latent Geometr
        98951, -- 2606.29705 GUICrafter: Weakly-Supervised GUI Agent Leveraging Massive Unannotated
        98993, -- 2606.29308 MirrorPPR: Exemplar-Based Portrait Photo Retouching
        99185, -- 2605.16122 GenShield: Unified Detection and Artifact Correction for AI-Generated
        99862, -- 2510.12334 Finite-time Convergence Analysis of Actor-Critic with Evolving Reward
        100618, -- 2604.10517 From Perception to Planning: Evolving Ego-Centric Task-Oriented Spatio
        101198, -- 2602.17993 Turbo Connection: Reasoning as Information Flow from Higher to Lower L
        101323, -- 2605.30895 CamGeo: Sparse Camera-Conditioned Image-to-Video Generation with 3D Ge
        102144, -- 2606.01075 On the Generalization Gap in Self-Evolving Language Model Reasoning
        102187, -- 2603.29038 Trojan-Speak: Bypassing Constitutional Classifiers with No Jailbreak T
        102266, -- 2605.14215 GenCircuit-RL: Reinforcement Learning from Hierarchical Verification f
        102942, -- 2509.23649 From Past To Path: Masked History Learning for Next-Item Prediction in
        103210, -- 2604.24114 IRIS: Interleaved Reinforcement with Incremental Staged Curriculum for
        103345, -- 2604.22209 UniSonate: A Unified Model for Speech, Music, and Sound Effect Generat
        103407, -- 2606.01677 UniVocal: Unified Speech-Singing Code-Switching Synthesis
        103476, -- 2510.19099 What Makes a Good Curriculum? Disentangling the Effects of Data Orderi
        104409, -- 2607.17097 HarmoHOI: Harmonizing Appearance and 3D Motion for Multi-view Hand-Obj
        105020, -- 2508.01594 CLIMD: A Curriculum Learning Framework for Imbalanced Multimodal Diagn
        106003, -- 2605.27921 Show, Don't TELL: Explainable AI-Generated Text Detection
        106059, -- 2608.02023 SwanTale: Unified Multi-Speaker Speech and Audio Generation for Instru
        106129, -- 2504.06407 Understanding Machine Unlearning Through the Lens of Mode Connectivity
        107239, -- 2503.00191 Learning Vision-Based Neural Network Controllers with Semi-Probabilist
        107611, -- 2511.10229 LangGPS: Language Separability Guided Data Pre-Selection for Joint Mul
        107796, -- 2508.07313 DocR1: Evidence Page-Guided GRPO for Multi-Page Document Understanding
        108158, -- 2511.09478 AdaCuRL: Adaptive Curriculum Reinforcement Learning with Invalid Sampl
        108629, -- 2004.00288 CurricularFace: Adaptive Curriculum Learning Loss for Deep Face Recogn
        108709, -- 2608.02833 CURV: Enhancing Chart Understanding Through Curriculum Visual Grounded
        108973, -- 2608.03571 Beyond Simply Environment Scaling: Designing Effective Environment Dis
        109161, -- external Alignment Curriculum Learning with RPS
        110073, -- external pFedGPT: Hierarchically Optimizing LoRA Aggregation Weights for Person
        110236, -- 2505.17923 Language models can learn implicit multi-hop reasoning, but only if th
        110353, -- external CARE: A Disagreement Detection Framework with Concept Alignment and Re
        110518, -- external UI-Hawk: Unleashing the Screen Stream Understanding for Mobile GUI Age
        110973, -- external NL2Lean: Translating Natural Language into Lean 4 through Multi-Aspect
        111088, -- external Long Chain-of-Thought Fine-tuning via Understanding-to-Reasoning Trans
        111136, -- 2505.24691 Speech-to-Text Translation with Phoneme-Augmented CoT: Enhancing Cross
        111501, -- 2508.10412 Facilitating Personalized TTS for Dysarthric Speakers Using Knowledge
        111517, -- external Dysarthric Speech Recognition Using Curriculum Learning and Multi-stre
        111561, -- external SepVAC: Multitask Learning of Speaker Separation, Speaker Localization
        111594, -- external GTA: Towards Generative Text-To-Audio Retrieval via Multi-Scale Tokeni
        111652, -- external MTSE: Multi-Target Speaker Extraction for Conversation Scenarios
        111696, -- 2506.00848 Speech Unlearning
        111710, -- external CBA-Whisper: Curriculum Learning-Based AdaLoRA Fine-Tuning on Whisper
        111839, -- 2505.19179 BR-ASR: Efficient and Scalable Bias Retrieval Framework for Contextual
        112060, -- 2505.13976 Naturalness-Aware Curriculum Learning with Dynamic Temperature for Spe
        113162, -- 2407.15158 HERGen: Elevating Radiology Report Generation with Longitudinal Data
        113789, -- 2510.08630 ExPO-HM: Learning to Explain-then-Detect for Hateful Meme Detection
        114322, -- 2405.10246 A Foundation Model for Brain Lesion Segmentation with Mixture of Modal
        114353, -- external Adaptive Curriculum Query Strategy for Active Learning in Medical Imag
        114356, -- 2407.16128 Advancing Brain Imaging Analysis Step-by-step via Progressive Self-pac
        115216, -- 2407.07853 Progressive Growing of Patch Size: Resource-Efficient Curriculum Learn
        115496, -- 2404.11998 Curriculum Point Prompting for Weakly-Supervised Referring Image Segme
        116948, -- 2311.16926 LLaFS: When Large Language Models Meet Few-Shot Segmentation
        117345, -- 2601.13126 A Streamlined Attention-based Network for Descriptor Extraction
        117774, -- 2607.25377 Gaussian Volumetric Representation for Efficient Shear–Warp Visualizat
        118756, -- 2606.22158 Improving Reasoning in Vision-Language Models via Perception Verified
        119006, -- external TiCRL: Textual Image Classification with Reinforcement Learning-Based
        119214, -- 2607.11199 DynEval: Holistic Evaluations of T2I Generative Models in the Wild
        119242, -- external LOOM: Weaving Geometry-Consistent Human-Object Interaction Videos via
        119271, -- 2606.25065 Self-supervised Garment Dynamics with Persistent Wrinkles
        119321, -- 2606.30019 OmniDance: Multimodal Driven Dance Video Generation with Large-scale I
        120226, -- external UHD-processer: Unified UHD Image Restoration with Progressive Frequenc
        121435, -- 2603.09377 SinGeo: Unlock Single Model's Potential for Robust Cross-View Geo-Loca
        122558, -- 2610.00906 ActiveSaddler: Automated Curriculum Learning for Agent Harness Optimiz
        123746, -- 2610.22744 OmniXRef: A Unified Framework for Multimodal Multi-Reference Video Edi
        124718, -- external OopsWorld! Operation-Grounded Seamless World Generation
        124823, -- external On the Pitfalls of Instance-Based Dynamic Curricula
        125356, -- 2604.17739 Democratizing Tool Learning with Environments Fully Simulated by a Fre
        126099, -- external Rare-Tail Statistics For Learning Biased Gaussian Halfspaces with Labe
        126615, -- external Skill-Level Effects in Behavioral Cloning: When Low-Skill Data Improve
        127184, -- external Think Densely, Act Sparsely: Latent Expert Cognitive Chains for Vision
        129589, -- external Effectiveness of Curriculum Learning Depends on Reward Sparsity and Co
        130001, -- external Neural Operator-based Curriculum Learning for Physics-Informed Neural
        130227, -- external Diffusion Fine-Tuning: Iterative Refinement for Advanced Grounding wit
        130441, -- 2605.26315 Curriculum Learning for Safety Alignment
        130765, -- 2608.05777 Curriculum Multiple Shooting for Robust Training of Neural and Univers
        132122  -- 2611.02810 TRIO: Task Refinement with Individual Optimization for Retrieval-Augme
  );

DELETE FROM paper_method_exclusions x
USING curriculum_learning_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM curriculum_learning_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM curriculum_learning_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- active-learning: 346 links, 2 exclusions.
CREATE TEMP TABLE active_learning_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'active-learning'
  AND p.id IN (
        228, -- 1508.04525 Recognizing Extended Spatiotemporal Expressions by Actively Trained Av
        563, -- 1701.03555 Active Self-Paced Learning for Cost-Effective and Progressive Face Ide
        818, -- 1707.08114 A Survey on Multi-Task Learning
        826, -- 1708.00489 Active Learning for Convolutional Neural Networks: A Core-Set Approach
        1798, -- 1902.00067 Bayesian active learning for optimization and uncertainty quantificati
        2108, -- 1905.07424 Galaxy Zoo: Probabilistic Morphology through Bayesian CNNs and Active
        2784, -- 1911.03270 Char-RNN and Active Learning for Hashtag Segmentation
        2814, -- 1911.05894 Coincidence, Categorization, and Consolidation: Learning to Recognize
        2824, -- 1911.07335 Using Error Decay Prediction to Overcome Practical Issues of Deep Acti
        2876, -- 1911.12809 Greed is Good: Exploration and Exploitation Trade-offs in Bayesian Opt
        3091, -- 2002.04709 Task-Aware Variational Adversarial Active Learning
        3111, -- 2002.07916 Information Condensing Active Learning
        3739, -- 2006.09916 Bayesian active learning for production, a systematic study and a reus
        3798, -- 2006.14063 Practical applications of metric space magnitude and weighting vectors
        4030, -- 2008.07267 A Survey of Active Learning for Text Classification using Deep Neural
        4070, -- 2008.11201 Deep Active Learning in Remote Sensing for data efficient Change Detec
        4091, -- 2009.00236 A Survey of Deep Active Learning
        4105, -- 2009.01797 A Wholistic View of Continual Learning with Deep Neural Networks: Forg
        4468, -- 2010.15382 Learning to Actively Learn: A Robust Approach
        4694, -- 2012.04225 Active Learning: Problem Settings and Recent Developments
        4856, -- 2101.00977 Towards Understanding the Behaviors of Optimal Deep Active Learning Al
        4916, -- 2101.08133 Active Learning for Sequence Tagging with Deep Pre-trained Models and
        4979, -- 2102.01909 HeBERT & HebEMO: a Hebrew BERT Model and a Tool for Polarity Analysis
        5068, -- 2102.09854 Intrinsically Motivated Open-Ended Multi-Task Learning Using Transfer
        5165, -- 2103.05331 Active Testing: Sample-Efficient Model Evaluation
        5437, -- 2104.06394 All you need are a few pixels: semantic segmentation with PixelPick
        5446, -- 2104.06879 Can Active Learning Preemptively Mitigate Fairness Issues?
        6086, -- 2106.12059 Stochastic Batch Acquisition: A Simple Baseline for Deep Active Learni
        6116, -- 2106.13500 TableSense: Spreadsheet Table Detection with Convolutional Neural Netw
        6186, -- 2107.02331 Mind Your Outliers! Investigating the Negative Impact of Outliers on A
        6203, -- 2107.03792 Automated Gain Control Through Deep Reinforcement Learning for Downstr
        6228, -- 2107.05687 Revisiting Uncertainty-based Query Strategies for Active Learning with
        6290, -- 2107.10314 Small-Text: Active Learning for Text Classification in Python
        6440, -- 2108.07670 ImitAL: Learning Active Learning Strategies from Synthetic Data
        6459, -- 2108.09331 Influence Selection for Active Learning
        6705, -- 2109.11301 A Survey on Cost Types, Interaction Schemes, and Annotator Performance
        6707, -- 2109.11319 Active Learning for Argument Strength Estimation
        6775, -- 2110.00777 Automated Seed Quality Testing System using GAN & Active Learning
        7096, -- 2110.15784 Convergence of Uncertainty Sampling for Active Learning
        7228, -- 2111.08430 Code-free development and deployment of deep segmentation models for d
        7238, -- 2111.09064 Guiding Generative Language Models for Data Augmentation in Few-Shot T
        7305, -- 2111.12940 Towards Fewer Annotations: Active Learning via Region Impurity and Pre
        7383, -- 2112.01406 Active Learning for Domain Adaptation: An Energy-Based Approach
        7419, -- 2112.03105 Active Learning Meets Optimized Item Selection
        7495, -- 2112.07522 LMTurk: Few-Shot Learners as Crowdsourcing Workers in a Language-Model
        7762, -- 2201.09992 HC4: A New Suite of Test Collections for Ad Hoc CLIR
        7881, -- 2202.02794 Active Learning on a Budget: Opposite Strategies Suit High and Low Bud
        8268, -- 2203.07845 Bamboo: Building Mega-Scale Vision Dataset Continually with Human-Mach
        8310, -- 2203.09178 Multilingual Detection of Personal Employment Status on Twitter
        8319, -- 2203.09410 A Framework and Benchmark for Deep Batch Active Learning for Regressio
        8417, -- 2203.13450 A Comparative Survey of Deep Active Learning
        8968, -- 2205.03598 Towards Computationally Feasible Deep Active Learning
        9126, -- 2205.11320 Active Learning Through a Covering Lens
        9988, -- 2208.03274 A Holistic Approach to Undesired Content Detection in the Real World
        10018, -- 2208.05379 Multi-task Active Learning for Pre-trained Transformer-based Models
        10126, -- 2208.11636 ImitAL: Learned Active Learning Strategy on Synthetic Data
        10529, -- 2210.01213 Robust Active Distillation
        10579, -- 2210.02442 Making Your First Choice: To Address Cold Start Problem in Vision Acti
        10597, -- 2210.03005 To Softmax, or not to Softmax: that is the question when applying Acti
        10634, -- 2210.03822 Is margin all you need? An extensive empirical study of active learnin
        10774, -- 2210.06788 TiDAL: Learning Training Dynamics for Active Learning
        10994, -- 2210.12765 Multi-Objective GFlowNets
        11197, -- 2211.01568 Fine-Tuning Language Models via Epistemic Neural Networks
        11238, -- 2211.03263 AfroLM: A Self-Active Learning-based Multilingual Pretrained Language
        11508, -- 2211.11798 Can You Label Less by Using Out-of-Domain Data? Active & Transfer Lear
        11592, -- 2211.13579 Knowledge-Aware Federated Active Learning with Non-IID Data
        11754, -- 2212.00772 Margin-based sampling in high dimensions: When being active is less ef
        11945, -- 2212.06493 Pixel is All You Need: Adversarial Trajectory-Ensemble Active Learning
        12369, -- 2301.04420 Combining Self-labeling with Selective Sampling
        12409, -- 2301.06270 Computational Assessment of Hyperpartisanship in News Titles
        12513, -- 2301.10460 HAL3D: Hierarchical Active Learning for Fine-Grained 3D Part Labeling
        12593, -- 2301.11856 ActiveLab: Active Learning with Re-Labeling by Multiple Annotators
        13092, -- 2302.06976 Investigating Multi-source Active Learning for Natural Language Infere
        13103, -- 2302.07317 Algorithm Selection for Deep Active Learning with Imbalanced Datasets
        13169, -- 2302.08893 Active learning for data streams: a survey
        13286, -- 2302.12246 Active Prompting with Chain-of-Thought for Large Language Models
        13495, -- 2303.02535 Streaming Active Learning with Deep Neural Networks
        13950, -- 2303.11530 Active Coarse-to-Fine Segmentation of Moveable Parts from Real Images
        14178, -- 2303.15256 Active Self-Supervised Learning: A Few Low-Cost Relationships Are All
        14267, -- 2303.16817 Adaptive Superpixel for Active Learning in Semantic Segmentation
        14545, -- 2304.04012 Progressive Volume Distillation with Active Learning for Efficient NeR
        14902, -- 2304.11762 You Never Get a Second Chance To Make a Good First Impression: Seeding
        15198, -- 2305.02459 Transfer and Active Learning for Dissonance Detection: Addressing the
        15314, -- 2305.04392 Disentangled Multi-Fidelity Deep Bayesian Active Learning
        15436, -- 2305.06408 Accelerating Batch Active Learning Using Continual Learning Techniques
        16321, -- 2305.16312 UMat: Uncertainty-Aware Single Image High Resolution Material Capture
        16325, -- 2305.16334 OlaGPT: Empowering LLMs With Human-like Problem-Solving Abilities
        16687, -- 2305.20050 Let's Verify Step by Step
        17042, -- 2306.03566 Memory-Based Dual Gaussian Processes for Sequential Learning
        17107, -- 2306.04454 Training-Free Neural Active Learning with Initialization-Robustness Gu
        17454, -- 2306.08954 Re-Benchmarking Pool-Based Active Learning for Binary Classification
        17540, -- 2306.09910 LabelBench: A Comprehensive Framework for Benchmarking Adaptive Label-
        17824, -- 2306.15766 Large Language Models as Annotators: Enhancing Generalization of NLP M
        17942, -- 2307.00398 ProbVLM: Probabilistic Adapter for Frozen Vision-Language Models
        18089, -- 2307.03741 Training Ensembles with Inliers and Outliers for Semi-supervised Activ
        18092, -- 2307.03764 For Women, Life, Freedom: A Participatory AI-Based Social Web Analysis
        18275, -- 2307.07942 KECOR: Kernel Coding Rate Maximization for Active 3D Object Detection
        18549, -- 2307.12226 Geometry-Aware Adaptation for Pretrained Models
        19600, -- 2308.11166 Hierarchical Point-based Active Learning for Semi-supervised Point Clo
        20304, -- 2309.05780 LUNet: Deep Learning for the Segmentation of Arterioles and Venules in
        20433, -- 2309.07914 ALWOD: Active Learning for Weakly-Supervised Object Detection
        21563, -- 2310.04966 Improved Active Learning via Dependent Leverage Score Sampling
        21576, -- 2310.05066 Guideline Learning for In-context Information Extraction
        22362, -- 2310.14554 Making RL with Preference-based Feedback Efficient via Randomization
        22801, -- 2310.20293 Annotator: A Generic Active Learning Baseline for LiDAR Semantic Segme
        22975, -- 2311.02879 Exploring Active Learning in Meta-Learning: Enhancing Context Set Labe
        23193, -- 2311.06542 Generation Of Colors using Bidirectional Long Short Term Memory Networ
        23452, -- 2311.09825 Human Still Wins over LLM: An Empirical Study of Active Learning on Do
        23514, -- 2311.11178 Active Prompt Learning in Vision Language Models
        23790, -- 2311.15614 FreeAL: Towards Human-Free Active Learning in the Era of Large Languag
        24666, -- 2312.07169 Semi-supervised Active Learning for Video Action Detection
        25265, -- 2312.16965 Reinforcement-based Display-size Selection for Frugal Satellite Image
        25812, -- 2401.07395 Harnessing the Power of Beta Scoring in Deep Active Learning for Multi
        25869, -- 2401.08501 ValUES: A Framework for Systematic Validation of Uncertainty Estimatio
        25954, -- 2401.09555 Improving Classification Performance With Human Feedback: Label a few,
        25979, -- 2401.09787 Querying Easily Flip-flopped Samples for Deep Active Learning
        26325, -- 2401.14555 Revisiting Active Learning in the Era of Vision Foundation Models
        27092, -- 2402.06045 Direct Acquisition Optimization for Low-Budget Active Learning
        27127, -- 2402.06560 Video Annotator: A framework for efficiently building video classifier
        27239, -- 2402.08114 Active Preference Learning for Large Language Models
        27889, -- 2402.15198 Bidirectional Uncertainty-Based Active Learning for Open Set Annotatio
        27957, -- 2402.16159 DistALANER: Distantly Supervised Active Learning Augmented Named Entit
        28179, -- 2402.18958 Boosting Semi-Supervised Object Detection in Remote Sensing Images Wit
        28299, -- 2403.01165 STAR: Constraint LoRA with Dynamic Active Learning for Data-Efficient
        28307, -- 2403.01234 Active Deep Kernel Learning of Molecular Functionalities: Realizing Dy
        28503, -- 2403.04272 Active Generalized Category Discovery
        30056, -- 2404.05094 Active Test-Time Adaptation: Theoretical Analyses and An Algorithm
        30084, -- 2404.05623 AnchorAL: Computationally Efficient Active Learning for Large and Imba
        30558, -- 2404.12522 Neural Active Learning Beyond Bandits
        30731, -- 2404.15720 Annotator-Centric Active Learning for Subjective NLP Tasks
        32869, -- 2406.09206 Self-Training for Sample-Efficient Active Learning for Text Classifica
        32949, -- 2406.10023 Deep Bayesian Active Learning for Preference Modeling in Large Languag
        34255, -- 2407.05355 VideoCoT: A Video Chain-of-Thought Dataset with Active Annotation Tool
        35243, -- 2407.18899 Learn from the Learnt: Source-Free Active Domain Adaptation via Contra
        35861, -- 2408.08072 I-SHEEP: Self-Alignment of LLM from Scratch through an Iterative Self-
        37004, -- 2409.11378 Diversify and Conquer: Diversity-Centric Data Selection with Iterative
        38245, -- 2410.08020 Efficiently Learning at Test-Time: Active Fine-Tuning of LLMs
        38703, -- 2410.13383 Railway LiDAR semantic segmentation based on intelligent semi-automate
        39767, -- 2411.05045 Performance-Guided LLM Knowledge Distillation for Efficient Text Class
        40095, -- 2411.11098 MolParser: End-to-end Visual Recognition of Molecule Structures in the
        41203, -- 2412.06014 Post-hoc Probabilistic Vision-Language Models
        41290, -- 2412.07207 MAPLE: A Framework for Active Preference Learning Guided by Large Lang
        43859, -- 2502.05244 Probabilistic Artificial Intelligence
        44370, -- 2502.11767 From Selection to Generation: A Survey of LLM-based Active Learning
        44697, -- 2502.14842 Generating $π$-Functional Molecules Using STGG+ with Active Learning
        45296, -- 2503.01076 Active Learning for Direct Preference Optimization
        45995, -- 2503.09701 Have LLMs Made Active Learning Obsolete? Surveying the NLP Community
        47214, -- 2504.02323 CoTAL: Human-in-the-Loop Prompt Engineering, Chain-of-Thought Reasonin
        47535, -- 2504.08110 Towards Unconstrained 2D Pose Estimation of the Human Spine
        47692, -- 2504.10559 Efficient Process Reward Model Training via Active Learning
        48406, -- 2505.02686 Sailing AI by the Stars: A Survey of Learning from Rewards in Post-Tra
        48481, -- 2505.04376 Label-efficient Single Photon Images Classification via Active Learnin
        50344, -- 2506.00910 PCoreSet: Effective Active Learning through Knowledge Distillation fro
        50535, -- 2506.03817 Survey of Active Learning Hyperparameters: Insights from a Large-Scale
        50827, -- 2506.08070 Info-Coevolution: An Efficient Framework for Data Model Coevolution
        51764, -- 2507.06181 CriticLean: Critic-Guided Reinforcement Learning for Mathematical Form
        52621, -- 2509.02040 Attributes as Textual Genes: Leveraging LLMs as Genetic Algorithm   Si
        54538, -- 2512.03442 PretrainZero: Reinforcement Active Pretraining
        54706, -- 2512.10739 Long-horizon Reasoning Agent for Olympiad-Level Mathematical Problem S
        54708, -- 2512.10756 OPV: Outcome-based Process Verifier for Efficient Long Chain-of-Though
        55151, -- 2601.02933 Pearmut: Human Evaluation of Translation Made Trivial
        55413, -- 2601.13677 Finally Outshining the Random Baseline: A Simple and Effective Solutio
        57887, -- 2604.23290 An Analysis of Active Learning Algorithms using Real-World Crowd-sourc
        58688, -- 2511.02721 PETra: A Multilingual Corpus of Pragmatic Explicitation in Translation
        59623, -- 2603.09692 ActiveUltraFeedback: Efficient Preference Data Generation using Active
        63678, -- 2512.13930 Hierarchical Multi-agent Large Language Model Reasoning for Autonomous
        64335, -- 2512.00884 Towards Active Synthetic Data Generation for Finetuning Language Model
        64388, -- 2511.23476 Thinking by Doing: Building Efficient World Model Reasoning in LLMs vi
        64611, -- 2511.19183 nnActive: A Framework for Evaluation of Active Learning in 3D Biomedic
        66127, -- 2506.07259 ALINE: Joint Amortization for Bayesian Inference and Active Data Acqui
        67040, -- 2510.03046 Bayesian E(3)-Equivariant Interatomic Potential with Iterative Restrat
        68030, -- 2509.17393 Program Synthesis via Test-Time Transduction
        68346, -- 2509.13539 Op-Fed: Opinion, Stance, and Monetary Policy Annotations on FOMC Trans
        70045, -- 2508.05310 ASkDAgger: Active Skill-level Data Aggregation for Interactive Imitati
        70063, -- 2508.05090 Cold-Start Active Preference Learning in Socio-Economic Domains
        70836, -- 2507.17351 Exploring Active Learning for Label-Efficient Training of Semantic   N
        71391, -- 2507.04630 Learn 3D VQA Better with Active Selection and Reannotation
        71583, -- 2507.00474 ADAptation: Reconstruction-based Unsupervised Active Learning for Brea
        72066, -- 2506.22444 Active Learning for Forecasting Severity among Patients with Post Acut
        72134, -- 2506.07619 The Catechol Benchmark: Time-series Solvent Selection Data for Few-sho
        73413, -- 2504.16136 Active Learning Methods for Efficient Data Utilization and Model   Per
        74785, -- 2502.06209 Enhancing Cost Efficiency in Active Learning with Candidate Set Query
        75012, -- 2502.00305 DEUCE: Dual-diversity Enhancement and Uncertainty-awareness for   Cold
        75032, -- 2410.00542 Differentially Private Active Learning: Balancing Effective Data Selec
        75094, -- 2501.14278 Active Learning for Continual Learning: Keeping the Past Alive in the
        75116, -- 2501.12643 Tensor cross interpolation approach for quantum impurity problems base
        75728, -- 2411.16722 Active Prompt Learning with Vision-Language Model Priors
        76479, -- 2409.01416 Active Symbolic Discovery of Ordinary Differential Equations via Phase
        76494, -- 2405.13930 AlabOS: A Python-based Reconfigurable Workflow Management Framework fo
        76535, -- 2408.12942 Causal-Guided Active Learning for Debiasing Large Language Models
        78053, -- 2312.13927 On the Convergence of Loss and Uncertainty-based Active Learning Algor
        78205, -- 2311.14146 Class Balanced Dynamic Acquisition for Domain Adaptive Semantic Segmen
        78381, -- 2310.08944 A Confidence-based Acquisition Model for Self-supervised Active Learni
        78523, -- 2309.08660 Astronomaly at scale: searching for anomalies amongst 4 million galaxi
        78651, -- 2308.06675 Learning fast, accurate, and stable closures of a kinetic theory of an
        78905, -- 2306.05724 Explaining Predictive Uncertainty with Information Theoretic Shapley V
        79487, -- 2212.08620 POTATO: The Portable Text Annotation Tool
        80237, -- 2201.12909 Scaling Gaussian Process Optimization by Evaluating a Few Unique Candi
        80528, -- 2109.05207 AstronomicAL: An interactive dashboard for visualisation, integration
        80650, -- 2106.11609 Distributional Gradient Matching for Learning Uncertain Neural Dynamic
        81075, -- 2010.06896 Efficient Estimation of Material Property Curves and Surfaces via Acti
        81193, -- 2007.13442 Fast active learning for pure exploration in reinforcement learning
        81212, -- 1707.02038 A Tutorial on Thompson Sampling
        81235, -- 2006.16947 Sampling from a k-DPP without looking at all items
        81277, -- 2006.04120 Sophisticated Inference
        81443, -- 2002.09564 Towards Robust and Reproducible Active Learning Using Neural Networks
        81772, -- 1904.02285 HoloDetect: Few-Shot Learning for Error Detection
        82264, -- 1703.02910 Deep Bayesian Active Learning with Image Data
        83442, -- 2605.14236 Active Learners as Efficient PRP Rerankers
        83678, -- 2212.11109 MAViC: Multimodal Active Learning for Video Captioning
        83966, -- 2403.02877 ActiveAD: Planning-Oriented Active Learning for End-to-End Autonomous
        84276, -- 2511.22344 Cleaning the Pool: Progressive Filtering of Unlabeled Pools in Deep Ac
        84455, -- 2601.01695 Learnability-Driven Submodular Optimization for Active Roadside 3D Det
        84528, -- 2602.18867 Similarity-as-Evidence: Calibrating Overconfident VLMs for Interpretab
        84806, -- 2603.07898 Revisiting Unknowns: Towards Effective and Efficient Open-Set Active L
        84837, -- 2603.10341 Federated Active Learning Under Extreme Non-IID and Global Class Imbal
        85026, -- 2603.21356 FluidGaussian: Propagating Simulation-Based Uncertainty Toward Functio
        85107, -- 2603.25107 Label What Matters: Modality-Balanced and Difficulty-Aware Multimodal
        85540, -- 2605.10349 Portable Active Learning for Object Detection
        86013, -- 2506.15893 Formal Models of Active Learning from Contrastive Examples
        86105, -- 2506.06630 Active Test-time Vision-Language Navigation
        86791, -- 2503.04223 Spiking Meets Attention: Efficient Remote Sensing Image Super-Resoluti
        87060, -- 2503.01215 Architectural and Inferential Inductive Biases for Exchangeable Sequen
        87167, -- 2505.22494 ProSpero: Active Learning for Robust Protein Design Beyond Wild-Type N
        87611, -- 2412.11154 From Easy to Hard: Progressive Active Learning Framework for Infrared
        87832, -- 2507.15381 To Label or Not to Label: PALM - A Predictive Model for Evaluating Sam
        88064, -- 2507.22615 Generative Active Learning for Long-tail Trajectory Prediction via Con
        88698, -- 2505.23032 Bayesian Neural Scaling Law Extrapolation with Prior-Data Fitted Netwo
        88757, -- 2312.09196 Improved Algorithm for Deep Active Learning under Imbalance via Optima
        88769, -- 2410.02145 Active Learning of Deep Neural Networks via Gradient-Free Cutting Plan
        88784, -- 2411.12010 Active Learning for Efficient Discovery of Optimal Combinatorial Pertu
        88926, -- 2410.13853 AutoAL: Automated Active Learning with Differentiable Query Strategy S
        89706, -- 2502.16870 Distributionally Robust Active Learning for Gaussian Process Regressio
        89741, -- 2505.05242 Enhancing Treatment Effect Estimation via Active Learning: A Counterfa
        90306, -- 2503.16125 Uncertainty Meets Diversity: A Comprehensive Active Learning Framework
        90666, -- 2503.04639 Enhancing SAM with Efficient Prompting and Preference Optimization for
        90754, -- 2503.06517 Instance-wise Supervision-level Optimization in Active Learning
        90818, -- 2503.02491 Joint Out-of-Distribution Filtering and Data Discovery Active Learning
        90880, -- 2502.19691 Rethinking Epistemic and Aleatoric Uncertainty for Active Open-Set Ann
        91176, -- 2410.19631 Efficient Biological Data Acquisition through Inference Set Design
        91177, -- 2412.20644 Uncertainty Herding: One Active Learning Method for All Label Budgets
        92162, -- 2410.02268 Structural-Entropy-Based Sample Selection for Efficient and Effective
        92191, -- 2408.01536 Active Learning for Neural PDE Solvers
        92360, -- 2408.16115 Uncertainty Modeling in Graph Neural Networks via Stochastic Different
        92409, -- 2410.01917 Provably Accurate Shapley Value Estimation via Leverage Score Sampling
        92741, -- 2509.24293 ActiveCQ: Active Estimation of Causal Quantities
        93563, -- 2601.20775 Active Learning for Decision Trees with Provable Guarantees
        94243, -- 2601.22595 Learn More with Less: Uncertainty Consistency Guided Query Selection f
        95162, -- 2507.15499 CLEVER: Stream-Based Active Learning for Robust Semantic Perception fr
        95642, -- external Mixed-Type Query Selection for Robotic Scientific Data Collection
        95935, -- external Multivariate Active Learning and Adaptive Sampling with Multi-Kernel G
        96158, -- 2509.18786 Human-Interpretable Uncertainty Explanations for Point Cloud Registrat
        96331, -- 2510.01389 INSIGHT: INference-Time Sequence Introspection for Generating Help Tri
        96673, -- external FALCO: Foundation Model Guided Active Learning for Cost-Effective Off-
        96966, -- 2506.04646 ActivePusher: Active Learning and Planning with Residual Physics for N
        97030, -- 2504.01156 Active Learning Design: Modeling Force Output for Axisymmetric Soft Pn
        99007, -- 2606.32032 Reinforcement Learning with Metacognitive Feedback Elicits Faithful Un
        100276, -- 2606.07630 Active Learning with Foundation Model Priors: Efficient Learning under
        100344, -- 2507.20490 HIAL: Towards Semantics-Aware Hypergraph Active Learning via Dual-Pers
        100361, -- 2601.23031 Asymptotic Theory of Iterated Empirical Risk Minimization, with Applic
        100419, -- 2605.17486 DyGRO-VLA: Cross-Task Scaling of Vision–Language–Action Models via Dyn
        100431, -- 2509.21947 Active Attacks: Red-teaming LLMs via Adaptive Environments
        100511, -- 2509.26005 BALLAST: Bayesian Active Learning with Look-ahead Amendment for Sea-dr
        101207, -- 2605.01687 MultiBreak: A Scalable and Diverse Multi-turn Jailbreak Benchmark for
        101499, -- 2606.00846 CUPID in the Model Zoo: Online Matchmaking for Selecting Your Dream LL
        101578, -- 2508.14022 BLIPs: Bayesian Learned Interatomic Potentials
        101579, -- 2509.21866 Causal-EPIG: Causally Aligned Active CATE Estimation
        101655, -- 2606.16045 Active Learning with Low-Rank Structure for Data Selection
        102343, -- 2603.27049 Overcoming the Incentive Collapse Paradox
        102448, -- 2605.29715 User-Aware Active Knowledge Acquisition for Emotional Support Dialogue
        102501, -- 2605.30625 Active Timepoint Selection for Learning Measure-Valued Trajectories
        103082, -- 2604.17501 CoAct: Co-Active LLM Preference Learning with Human-AI Synergy
        104134, -- 2304.09530 SelfAct: Personalized Activity Recognition based on Self-Supervised an
        104917, -- external Active Source-Free Cross-Domain and Cross-Modality Adaptation for Volu
        105062, -- external Cost-effective Active Learning for Nucleus Detection Using Crowdsource
        105071, -- external CSAL-3D: Cold-start Active Learning for 3D Medical Image Segmentation
        105089, -- external Deep Learning Framework for Managing Inter-Reader Variability in Backg
        105496, -- 2312.05407 ODES: Online Domain Adaptation with Expert Guidance for Medical Image
        105501, -- external One-shot active learning for vessel segmentation
        105502, -- 2506.15318 OpenPath: Open-Set Active Learning for Pathology Image Classification
        105676, -- external Spatial Aggregation for Semi-supervised Active Learning in 3D Medical
        105694, -- 2507.22059 StepAL: Step-aware Active Learning for Cataract Surgical Videos
        105704, -- external SUGFW: A SAM-based Uncertainty-guided Feature Weighting Framework for
        105733, -- external Temporal Model-Based Federated Active Medical Image Classification
        105818, -- external Vector-Quantization-Driven Active Learning for Efficient Multi-Modal M
        107033, -- 2601.15773 Next Generation Active Learning: Mixture of LLMs in the Loop
        107703, -- 2601.10993 Memorize Early, Then Query: Inlier-Memorization-Guided Active Outlier
        107751, -- 2511.12315 Active Learning of Symbolic Automata over Rational Numbers
        108211, -- 2512.12341 Uncertainty Quantification for Machine Learning: One Size Does Not Fit
        108365, -- 2601.17536 OTI: A Model-free and Visually Interpretable Measure of Image Attackab
        108563, -- 2508.18839 DRMD: Deep Reinforcement Learning for Malware Detection Under Concept
        110018, -- 2502.07143 Ask Patients with Patience: Enabling LLMs for Human-Centric Medical Di
        110758, -- 2509.07512 ALLabel: Three-stage Active Learning for LLM-based Entity Recognition
        110812, -- external Enhancing Large Vision-Language Models with Ultra-Detailed Image Capti
        111575, -- external When The MOS Predictor Asks For Training Annotation In Cross Lingual/D
        112571, -- 2312.05328 Bad Students Make Great Teachers: Active Learning Accelerates Large-Sc
        112830, -- external Efficient Active Domain Adaptation for Semantic Segmentation by Select
        113016, -- external Two-Stage Active Learning for Efficient Temporal Action Segmentation
        113034, -- 2403.06517 Active Generation for Image Classification
        113250, -- 2407.07268 Dataset Quantization with Active Learning based Adaptive Sampling
        113628, -- 2407.12212 Generalized Coverage for More Robust Low-Budget Active Learning
        113637, -- 2403.04482 On the Topology Awareness and Generalization Performance of Graph Neur
        114084, -- 2609.06806 Train Smarter, Not Harder: Switching Signal-Guided Training in Active
        114350, -- 2407.05973 Active Label Refinement for Robust Training of Imbalanced Medical Imag
        114353, -- external Adaptive Curriculum Query Strategy for Active Learning in Medical Imag
        114360, -- 2406.13645 Advancing UWF-SLO Vessel Segmentation with Source-Free Active Domain A
        114440, -- external Class-Balancing Deep Active Learning with Auto-Feature Mixing and Mino
        115182, -- external OSAL-ND: Open-set Active Learning for Nucleus Detection
        115264, -- external SBC-AL: Structure and Boundary Consistency-based Active Learning for M
        115536, -- 2312.02567 Think Twice Before Selection: Federated Evidential Active Learning for
        116118, -- 2404.10124 Epistemic Uncertainty Quantification For Pre-Trained Neural Networks
        116138, -- external Active Domain Adaptation with False Negative Prediction for Object Det
        116199, -- external Weakly Supervised Point Cloud Semantic Segmentation via Artificial Ora
        116897, -- 2211.11612 Plug and Play Active Learning for Object Detection
        117338, -- 2512.22771 Next Best View Selections for Semantic and Dynamic 3D Gaussian Splatti
        117953, -- 2607.00144 A Mechanism-Driven Theory of Phase Transitions in Active Learning
        118328, -- 2509.24181 Combining Discrepancy-Confusion Uncertainty and Calibration Diversity
        119022, -- external FuDU: A Fuzzy Dual-dimension Uncertainty Framework for Streaming Activ
        120432, -- external Towards Cost-Effective Learning: A Synergy of Semi-Supervised and Acti
        122185, -- 2609.26489 Calibration as a First-Class Criterion in LLM Evaluation
        123231, -- external A scalable active framework for region annotation in 3D shape collecti
        123307, -- 1905.08628 Constraining the Parameters of High-Dimensional Models with Active Lea
        124321, -- 2602.02081 Active Learning From Positive and Unlabeled Examples
        124806, -- external Active Learning of Conditional Generative Models via the Transport Neu
        124823, -- external On the Pitfalls of Instance-Based Dynamic Curricula
        125142, -- 2606.25197 Efficient Adaptive Data Acquisition via Pretrained Belief Representati
        125309, -- external Cool Graphs: Active Property Search Towards Quantum Nano-Refrigerators
        125503, -- 2606.04100 Stein Kernelized Molecular Dynamics for Active Learning of Interatomic
        125955, -- 2602.17605 Adapting Actively on the Fly: Relevance-Guided Online Meta-Learning wi
        126286, -- external Improved Leverage Score Sampling for Constrained Active Linear Regress
        127145, -- 2605.05435 Active Learning for Conditional Generative Compressed Sensing
        127200, -- external Generative Active Learning via Bayesian Acquisition for Improving the
        127602, -- external Safe Active Learning with Future Viability Guarantees in Time-Series M
        128805, -- external Measuring Coherence in Predictive Models
        129039, -- external Active Learning as Nullspace Regulation: A Spectral Representation Per
        129102, -- 2608.12219 ScreenShot: A Foundation Model for Few-Shot Combination Drug Screening
        129360, -- external Forgetting to Improve: Principled Data Removal in Active Learning
        129401, -- 2606.09949 Learning Where to Simulate: Generative Active Sampling for Online PDE
        129654, -- external Deconstructing Multi-Task Active Learning: The Paradox of Gradient Con
        129772, -- external GOAT-AL: Pseudo Neural Collapse Guides Adaptive Coverage for All-Budge
        129951, -- 2606.19476 Can In-Context Learning Support Intrinsic Curiosity?
        130133, -- external A Solver-Efficient Neural Adversarial Attack on Subgraph Matching Mode
        130260, -- 2605.12190 Information-Theoretic Generalization Bounds for Sequential Decision Ma
        130349, -- 2610.20881 Pixels to Tokens: Token Space Efficient Active Learning for Low-Budget
        130841, -- 2605.10654 Active Learning for Gaussian Process Regression Under Self-Induced Bol
        131115  -- external Efficient Analytic Uncertainty Quantification for Multimodal Regressio
  );

DELETE FROM paper_method_exclusions x
USING active_learning_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM active_learning_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM active_learning_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE active_learning_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'active-learning'
  AND p.id IN (
        67061, -- 2510.02663 TutorBench: A Benchmark To Assess Tutoring Capabilities Of Large   Lan
        125388  -- 2510.09770 GOLD PANNING: Strategic Context Shuffling for Needle-in-Haystack Reaso
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM active_learning_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING active_learning_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING active_learning_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- adversarial-training: 327 links, 217 exclusions.
CREATE TEMP TABLE adversarial_training_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adversarial-training'
  AND p.id IN (
        138, -- 1412.6572 Explaining and Harnessing Adversarial Examples
        381, -- 1605.07725 Adversarial Training Methods for Semi-Supervised Text Classification
        664, -- 1704.03976 Virtual Adversarial Training: A Regularization Method for Supervised a
        956, -- 1711.02846 Intriguing Properties of Adversarial Examples
        1458, -- 1808.09115 All You Need is "Love": Evading Hate-speech Detection
        1616, -- 1811.05021 Improved Dynamic Memory Network for Dialogue Act Classification with A
        1921, -- 1903.11508 Text Processing Like Humans Do: Visually Attacking and Shielding NLP S
        1993, -- 1904.06347 Unrestricted Adversarial Examples via Semantic Manipulation
        2270, -- 1906.06784 Interpolated Adversarial Training: Achieving Robust Neural Networks wi
        2731, -- 1910.12196 Word-level Textual Adversarial Attacking as Combinatorial Optimization
        2843, -- 1911.09665 Adversarial Examples Improve Image Recognition
        3151, -- 2002.12047 FMix: Enhancing Mixed Sample Data Augmentation
        3181, -- 2003.02484 Adversarial Vertex Mixup: Toward Better Adversarially Robust Generaliz
        3344, -- 2004.05884 Adversarial Weight Perturbation Helps Robust Generalization
        3528, -- 2005.02313 Adversarial Training against Location-Optimized Adversarial Patches
        3668, -- 2006.03654 DeBERTa: Decoding-enhanced BERT with Disentangled Attention
        3708, -- 2006.07710 The Pitfalls of Simplicity Bias in Neural Networks
        3730, -- 2006.09136 When Does Self-Supervision Help Graph Convolutional Networks?
        3732, -- 2006.09373 The shape and simplicity biases of adversarially robust ImageNet-train
        4159, -- 2009.07964 Tasty Burgers, Soggy Fries: Probing Aspect Robustness in Aspect-Based
        4207, -- 2009.12064 Attention Meets Perturbations: Robust and Interpretable Attention with
        4229, -- 2009.14720 DVERGE: Diversifying Vulnerabilities for Enhanced Robust Generation of
        4790, -- 2012.13628 A Simple Fine-tuning Is All You Need: Towards Robust Deep Learning Via
        4907, -- 2101.06639 Removing Undesirable Feature Contributions Using Out-of-Distribution D
        5342, -- 2104.00322 Domain Invariant Adversarial Learning
        5403, -- 2104.04107 FACESEC: A Fine-grained Robustness Evaluation Framework for Face Recog
        5422, -- 2104.05062 Achieving Model Robustness through Discrete Adversarial Training
        5502, -- 2104.08635 UPB at SemEval-2021 Task 5: Virtual Adversarial Training for Toxic Spa
        5517, -- 2104.08763 Making Attention Mechanisms More Robust and Interpretable with Virtual
        5680, -- 2105.04070 Robust Training Using Natural Transformation
        5784, -- 2105.12237 Practical Convex Formulation of Robust One-hidden-layer Neural Network
        5847, -- 2106.01065 Towards Robustness of Text-to-SQL Models against Synonym Substitution
        6152, -- 2106.15776 Local Reweighting for Adversarial Training
        6216, -- 2107.04954 ReconVAT: A Semi-Supervised Automatic Music Transcription Framework fo
        6326, -- 2107.13639 Imbalanced Adversarial Training with Reweighting
        6392, -- 2108.04217 ROPUST: Improving Robustness through Fine-tuning with Photonic Process
        6533, -- 2109.00678 Regional Adversarial Training for Better Robust Generalization
        6839, -- 2110.03825 Exploring Architectural Ingredients of Adversarially Robust Deep Neura
        7148, -- 2111.02331 LTD: Low Temperature Distillation for Robust Adversarial Training
        7455, -- 2112.05005 Mutual Adversarial Training: Learning together is better than going al
        7651, -- 2201.01965 Efficient Global Optimization of Two-layer ReLU Networks: Quadratic-ti
        7874, -- 2202.02626 Layer-wise Regularized Adversarial Training using Layers Sustainabilit
        8023, -- 2202.10103 Robustness and Accuracy Could Be Reconcilable by (Proper) Definition
        8228, -- 2203.06649 Joint rotational invariance and adversarial training of a dual-stream
        8341, -- 2203.10346 Perturbations in the Wild: Leveraging Human-Written Text Perturbations
        8390, -- 2203.12208 Self-supervised Learning of Adversarial Example: Towards Good Generali
        8563, -- 2204.01738 Experimental quantum adversarial learning with programmable supercondu
        8577, -- 2204.02481 Adversarial Robustness through the Lens of Convolutional Filters
        8589, -- 2204.02738 Masking Adversarial Damage: Finding Adversarial Saliency for Robust an
        8920, -- 2205.01663 Adversarial Training for High-Stakes Reliability
        9029, -- 2205.07460 Diffusion Models for Adversarial Purification
        9244, -- 2205.14230 Semi-supervised Semantics-guided Adversarial Training for Trajectory P
        9263, -- 2205.14826 Robust Weight Perturbation for Adversarial Training
        9402, -- 2206.03353 Improving Adversarial Robustness by Putting More Regularizations on Le
        9853, -- 2207.10283 One-vs-the-Rest Loss to Focus on Important Samples in Adversarial Trai
        9881, -- 2207.11378 Do Perceptually Aligned Gradients Imply Adversarial Robustness?
        9994, -- 2208.03635 Federated Adversarial Learning: A Framework with Convergence Analysis
        10019, -- 2208.05395 A Sublinear Adversarial Training Algorithm
        10188, -- 2209.00005 Be Your Own Neighborhood: Detecting Adversarial Example by the Neighbo
        10437, -- 2209.14053 Inducing Data Amplification Using Auxiliary Datasets in Adversarial Tr
        10734, -- 2210.05938 Robust Models are less Over-Confident
        10778, -- 2210.06888 AccelAT: A Framework for Accelerating the Adversarial Training of Deep
        11155, -- 2211.00241 Adversarial Policies Beat Superhuman Go AIs
        11727, -- 2211.17244 Tight Certification of Adversarially Trained Neural Networks via Nonco
        11960, -- 2212.07016 Understanding Zero-Shot Adversarial Robustness for Large-Scale Models
        12345, -- 2301.03110 RobArch: Designing Robust Architectures against Adversarial Attacks
        12648, -- 2301.12643 Adversarial Style Augmentation for Domain Generalization
        12723, -- 2301.13838 Image Shortcut Squeezing: Countering Perturbative Availability Poisons
        12878, -- 2302.02907 GAT: Guided Adversarial Training with Pareto-optimal Auxiliary Tasks
        12980, -- 2302.04638 Better Diffusion Models Further Improve Adversarial Training
        13435, -- 2303.01052 Demystifying Causal Features on Adversarial Examples and Causal Inocul
        13482, -- 2303.02251 Certified Robust Neural Networks: Generalization and Corruption Resist
        13560, -- 2303.04278 CUDA: Convolution-based Unlearnable Datasets
        13716, -- 2303.07320 Model-tuning Via Prompts Makes NLP Models Adversarially Robust
        13810, -- 2303.09051 Robust Evaluation of Diffusion-Based Adversarial Purification
        13814, -- 2303.09105 Rethinking Model Ensemble in Transfer-based Adversarial Attacks
        14018, -- 2303.12669 An Extended Study of Human-like Behavior under Adversarial Training
        14283, -- 2303.17096 ImageNet-E: Benchmarking Neural Network Robustness via Attribute Editi
        14328, -- 2303.17764 Towards Adversarially Robust Continual Learning
        14797, -- 2304.09563 On the Robustness of Aspect-based Sentiment Analysis: Rethinking Model
        15116, -- 2305.01139 Stratified Adversarial Robustness with Rejection
        15827, -- 2305.12118 Annealing Self-Distillation Rectification Improves Adversarial Trainin
        16018, -- 2305.13991 Expressive Losses for Verified Robustness via Convex Combinations
        16420, -- 2305.17342 Rethinking Adversarial Policies: A Generalized Attack Formulation and
        16883, -- 2306.01762 Rapid Plug-in Defenders
        17074, -- 2306.04064 Transferable Adversarial Robustness for Categorical Data via Universal
        17233, -- 2306.06081 Carefully Blending Adversarial Training, Purification, and Aggregation
        17309, -- 2306.07197 AROID: Improving Adversarial Robustness Through Online Instance-Wise D
        17546, -- 2306.10001 Group Orthogonalization Regularization For Vision Models Adaptation an
        17596, -- 2306.11035 Adversarial Training Should Be Cast as a Non-Zero-Sum Game
        17692, -- 2306.12941 Towards Reliable Evaluation and Fast Training of Robust Semantic Segme
        17845, -- 2306.16170 Mitigating Accuracy-Robustness Trade-off via Balanced Multi-Teacher Ad
        18039, -- 2307.02500 Interpretable Computer Vision Models through Adversarial Training: Unv
        18240, -- 2307.07250 Mitigating Adversarial Vulnerability through Causal Parameter Estimati
        18399, -- 2307.09763 Towards Building More Robust Models with Frequency Bias
        18424, -- 2307.10235 Towards Viewpoint-Invariant Visual Recognition via Adversarial Trainin
        18718, -- 2307.15061 The RoboDepth Challenge: Methods and Advancements Towards Robust Depth
        18773, -- 2307.16361 Benchmarking and Analyzing Robust Point Cloud Recognition: Bag of Tric
        18827, -- 2308.00311 Doubly Robust Instance-Reweighted Adversarial Training
        18900, -- 2308.01888 FROD: Robust Object Detection for Free
        18939, -- 2308.02533 Improving Generalization of Adversarial Training via Robust Critical F
        19028, -- 2308.04061 Enhancing Adversarial Robustness in Low-Label Regime via Adaptively We
        19484, -- 2308.10110 Robust Mixture-of-Expert Training for Convolutional Neural Networks
        19742, -- 2308.12857 Fast Adversarial Training with Smooth Convergence
        19959, -- 2308.16454 Adversarial Finetuning with Latent Representation Constraint to Mitiga
        20018, -- 2309.00614 Baseline Defenses for Adversarial Attacks Against Aligned Language Mod
        20111, -- 2309.02057 Robust Recommender System: A Survey and Future Directions
        21166, -- 2310.00567 Understanding the Robustness of Randomized Feature Defense Against Que
        21681, -- 2310.06112 Theoretical Analysis of Robust Overfitting for Wide DNNs: An NTK Appro
        21932, -- 2310.08847 On the Over-Memorization During Natural, Robust and Catastrophic Overf
        22011, -- 2310.10036 Evading Detection Actively: Toward Anti-Forensics against Forgery Loca
        22625, -- 2310.17645 PubDef: Defending Against Transfer Attacks From Public Models
        25674, -- 2401.05566 Sleeper Agents: Training Deceptive LLMs that Persist Through Safety Tr
        26100, -- 2401.11618 Efficient local linearity regularization to overcome catastrophic over
        26175, -- 2401.12532 DAFA: Distance-Aware Fair Adversarial Training
        26343, -- 2401.14948 Conserve-Update-Revise to Cure Generalization and Robustness Trade-off
        26430, -- 2401.16352 Adversarial Training on Purification (AToP): Advancing Both Robustness
        26855, -- 2402.03477 Arabic Synonym BERT-based Adversarial Examples for Text Classification
        26933, -- 2402.04249 HarmBench: A Standardized Evaluation Framework for Automated Red Teami
        27115, -- 2402.06255 Fight Back Against Jailbreaking via Prompt Adversarial Tuning
        27536, -- 2402.11733 The Effectiveness of Random Forgetting for Robust Generalization
        28142, -- 2402.18329 Robust Synthetic Data-Driven Detection of Living-Off-the-Land Reverse
        28560, -- 2403.05030 Defending Against Unforeseen Failure Modes with Latent Adversarial Tra
        28892, -- 2403.09863 Towards White Box Deep Learning
        28902, -- 2403.10045 Towards Adversarially Robust Dataset Distillation by Curvature Regular
        29155, -- 2403.13134 Robust NAS under adversarial training: benchmark, theory, and beyond
        29857, -- 2404.02151 Jailbreaking Leading Safety-Aligned LLMs with Simple Adaptive Attacks
        30264, -- 2404.08154 Eliminating Catastrophic Overfitting Via Abnormal Adversarial Examples
        31190, -- 2405.06361 Certified $\ell_2$ Attribution Robustness via Uniformly Smoothed Attri
        31671, -- 2405.15234 Defensive Unlearning with Adversarial Training for Robust Concept Eras
        31697, -- 2405.15589 Efficient Adversarial Training in LLMs with Continuous Attacks
        31748, -- 2405.16262 Layer-Aware Analysis of Catastrophic Overfitting: Revealing the Pseudo
        31757, -- 2405.16341 R.A.C.E.: Robust Adversarial Concept Erasure for Secure Text-to-Image
        32448, -- 2406.04313 Improving Alignment and Robustness with Circuit Breakers
        33296, -- 2406.12935 ChatBug: A Common Vulnerability of Aligned LLMs Induced by Chat Templa
        33491, -- 2406.15444 Cutting Through the Noise: Boosting LLM Performance on Math Word Probl
        33885, -- 2407.00248 DiffuseDef: Improved Robustness to Adversarial Attacks via Iterative D
        34342, -- 2407.06315 Shedding More Light on Robust Classifiers under the lens of Energy-bas
        34776, -- 2407.11969 Does Refusal Training in LLMs Generalize to the Past Tense?
        35051, -- 2407.15549 Latent Adversarial Training Improves Robustness to Persistent Harmful
        35511, -- 2408.01705 Downstream Transfer Attack: Adversarial Attacks on Downstream Models w
        35716, -- 2408.05446 Ensemble everything everywhere: Multi-scale aggregation for adversaria
        35747, -- 2408.06079 Towards Adversarial Robustness via Debiased High-Confidence Logit Alig
        37351, -- 2409.17476 Improving the Shortest Plank: Vulnerability-Aware Adversarial Training
        38806, -- 2410.14470 How Do Training Methods Influence the Utilization of Vision Models?
        39374, -- 2410.22844 Understanding and Improving Adversarial Collaborative Filtering for Ro
        41289, -- 2412.07199 A Parametric Approach to Adversarial Augmentation for Cross-Domain Iri
        41428, -- 2412.08969 Deep Learning Model Security: Threats and Defenses
        42153, -- 2412.18196 Robustness-aware Automatic Prompt Optimization
        43442, -- 2501.18841 Trading Inference-Time Compute for Adversarial Robustness
        43465, -- 2501.19180 Enhancing Model Defense Against Jailbreaks with Proactive Safety Reaso
        43613, -- 2502.01896 INTACT: Inducing Noise Tolerance through Adversarial Curriculum Traini
        43866, -- 2502.05374 Towards LLM Unlearning Resilient to Relearning Attacks: A Sharpness-Aw
        44722, -- 2502.14976 EigenShield: Causal Subspace Filtering via Random Matrix Theory for Ad
        44909, -- 2502.17121 Adversarial Training for Defense Against Label Poisoning Attacks
        47159, -- 2504.01550 Representation Bending for Large Language Model Safety
        47305, -- 2504.03735 Misaligned Roles, Misplaced Images: Structural Input Perturbations Exp
        49464, -- 2505.16947 MixAT: Combining Continuous and Discrete Adversarial Training for LLMs
        50165, -- 2505.23803 MultiPhishGuard: An LLM-based Multi-Agent System for Phishing Email De
        50223, -- 2505.24369 Adversarial Preference Learning for Robust LLM Alignment
        58420, -- 2604.06950 Making MLLMs Blind: Adversarial Smuggling Attacks in MLLM Content Mode
        60592, -- 2602.15238 Closing the Distribution Gap in Adversarial Training for LLMs
        62784, -- 2601.04991 Higher-Order Adversarial Patches for Real-Time Object Detectors
        63369, -- 2512.20806 Safety Alignment of LMs via Non-cooperative Games
        63691, -- 2512.13568 Superposition as Lossy Compression: Measure with Sparse Autoencoders a
        63835, -- 2512.10637 Adaptive Intrusion Detection System Leveraging Dynamic Neural Models w
        64020, -- 2512.06899 Patronus: Identifying and Mitigating Transferable Backdoors in Pre-tra
        64682, -- 2511.18324 Gradient Masters at BLP-2025 Task 1: Advancing Low-Resource NLP for Be
        64812, -- 2511.15807 TopoReformer: Mitigating Adversarial Attacks Using Topological Purific
        66493, -- 2510.13872 Joint Discriminative-Generative Modeling via Dual Adversarial Training
        67676, -- 2510.00037 On Robustness of Vision-Language-Action Model against Multi-Modal Pert
        68571, -- 2509.07673 Nearest Neighbor Projection Removal Adversarial Training
        69094, -- 2509.00088 AEGIS : Automated Co-Evolutionary Framework for Guarding Prompt   Inje
        69769, -- 2508.10946 IPG: Incremental Patch Generation for Generalized Adversarial Patch Tr
        69964, -- 2508.10029 Latent Fusion Jailbreak: Blending Harmful and Harmless Representations
        71272, -- 2507.07776 SCOOTER: A Human Evaluation Framework for Unrestricted Adversarial Exa
        72449, -- 2506.00874 Breaking Latent Prior Bias in Detectors for Generalizable AIGC Image
        72527, -- 2501.10639 Latent-space adversarial training with post-aware calibration for defe
        72998, -- 2505.12301 Beyond Single-Point Judgment: Distribution Alignment for LLM-as-a-Judg
        73503, -- 2504.10850 How to Enhance Downstream Adversarial Robustness (almost) without Touc
        73634, -- 2504.06141 Adversarial Training of Reward Models
        73853, -- 2503.20454 Lipschitz Constant Meets Condition Number: Learning Robust and Compact
        73911, -- 2503.18784 Leveraging Perturbation Robustness to Enhance Out-of-Distribution Dete
        74110, -- 2503.10191 Robustness Tokens: Towards Adversarial Robustness of Transformers
        74924, -- 2502.02096 Dual-Flow: Transferable Multi-Target, Instance-Agnostic Attacks via
        76417, -- 2409.07390 D-CAPTCHA++: A Study of Resilience of Deepfake CAPTCHA under Transfera
        77825, -- 2402.06827 RAMP: Boosting Adversarial Robustness Against Multiple l_p Perturbatio
        78485, -- 2309.13190 Spatial-frequency channels, shape bias, and adversarial robustness
        78507, -- 2309.10348 Language Guided Adversarial Purification
        78594, -- 2308.16258 Robust Principles: Architectural Design Principles for Adversarially
        80105, -- 2203.14533 Robust Unlearnable Examples: Protecting Data Against Adversarial Learn
        80146, -- 2106.01606 Exploring Memorization in Adversarial Training
        80356, -- 2111.15121 Pyramid Adversarial Training Improves ViT Performance
        80396, -- 2111.06979 Neural Population Geometry Reveals the Role of Stochasticity in Robust
        81096, -- 2010.01724 TextAttack: Lessons learned in designing Python frameworks for NLP
        82948, -- 2605.07447 Sparse Autoencoders as Plug-and-Play Firewalls for Adversarial Attack
        83981, -- 2502.00653 Towards Robust Multimodal Large Language Models Against Jailbreak Atta
        84018, -- 2505.19459 Your Classifier Can Do More: Towards Balancing the Gaps in Classificat
        84083, -- 2508.13309 DASH: A Meta-Attack Framework for Synthesizing Effective and Stealthy
        84271, -- 2511.22147 RemedyGS: Defend 3D Gaussian Splatting Against Computation Cost Attack
        84444, -- 2512.22522 Towards Reliable Evaluation of Adversarial Robustness for Spiking Neur
        84568, -- 2602.20053 Decoupling Defense Strategies for Robust Image Watermarking
        85159, -- 2603.27139 The Geometry of Robustness: Optimizing Loss Landscape Curvature and Fe
        85205, -- 2603.29410 AGFT: Alignment-Guided Fine-Tuning for Zero-Shot Adversarial Robustnes
        85459, -- 2604.24332 Mitigating Error Amplification in Fast Adversarial Training
        85552, -- 2605.13395 Taming the Long Tail: Rebalancing Adversarial Training via Adaptive Pe
        86333, -- 2502.04204 Short-length Adversarial Training Helps LLMs Defend Long-length Jailbr
        86630, -- 2508.14757 Distributional Adversarial Attacks and Training in Deep Hedging
        87666, -- 2508.02186 Failure Cases Are Better Learned But Boundary Says Sorry: Facilitating
        87676, -- 2506.23581 PBCAT: Patch-Based Composite Adversarial Training against Physically R
        87868, -- 2311.17608 Adversarial Robust Memory-Based Continual Learner
        88638, -- 2502.07225 CAT: Contrastive Adversarial Training for Evaluating the Robustness of
        89041, -- 2405.17130 Explaining the role of Intrinsic Dimensionality in Adversarial Trainin
        89059, -- 2506.07804 Enhancing Adversarial Robustness with Conformal Prediction: A Framewor
        89387, -- 2306.01271 On the Clean Generalization and Robust Overfitting in Adversarial Trai
        89487, -- 2506.05032 Identifying and Understanding Cross-Class Features in Adversarial Trai
        90022, -- 2407.18213 Scaling Trends in Language Model Robustness
        90207, -- 2503.11032 Weakly Supervised Contrastive Adversarial Training for Learning Robust
        90226, -- 2503.01407 Divide and Conquer: Heterogeneous Noise Integration for Diffusion-base
        90233, -- 2504.05838 Mind the Trojan Horse: Image Prompt Adapter Enabling Scalable and Dece
        90344, -- 2503.21815 ATP: Adaptive Threshold Pruning for Efficient Data Encoding in Quantum
        90671, -- 2408.16807 STEREO: A Two-Stage Framework for Adversarially Robust Concept Erasing
        90764, -- 2411.16721 Steering Away from Harm: An Adaptive Approach to Defending Vision Lang
        91516, -- 2502.17099 Improved Diffusion-based Generative Model with Better Adversarial Robu
        91610, -- 2402.14648 Rethinking Invariance Regularization in Adversarial Training to Improv
        91641, -- 2502.14572 Factor Graph-based Interpretable Neural Networks
        91669, -- 2409.20089 Robust LLM safeguarding via refusal feature adversarial training
        91812, -- 2503.06461 Long-tailed Adversarial Training with Self-Distillation
        91813, -- 2312.03286 Indirect Gradient Matching for Adversarial Robust Distillation
        91904, -- 2410.08503 Adversarial Training Can Provably Improve Robustness: Theoretical Anal
        91909, -- 2406.11458 Adversaries With Incentives:  A Strategic Alternative to Adversarial R
        91936, -- 2503.04315 Provable Robust Overfitting Mitigation in Wasserstein Distributionally
        91950, -- 2502.11858 Rethinking Audio-Visual Adversarial Vulnerability from Temporal and Mo
        91997, -- 2410.10744 Adversarially Robust Out-of-Distribution Detection Using Lyapunov-Stab
        92245, -- 2411.00121 I Can Hear You: Selective Robust Training for Deepfake Audio Detection
        92296, -- 2410.13211 Estimating the Probabilities of Rare Outputs in Language Models
        92431, -- 2410.10373 Sharpness-Aware Minimization Efficiently Selects Flatter Minima Late I
        92821, -- 2510.21910 Adversarial Déjà Vu: Jailbreak Dictionary Learning for Stronger Genera
        93028, -- 2510.26981 Fine-Grained Iterative Adversarial Attacks with Limited Computation Bu
        93190, -- 2504.01735 AdPO: Enhancing the Adversarial Robustness of Large Vision-Language Mo
        93206, -- 2506.17040 Stretching Beyond the Obvious: A Gradient-Free Framework to Unveil the
        93265, -- 2510.00310 Robust Federated Inference
        93417, -- 2509.24359 DRIFT: Divergent Response in Filtered Transformations for Robust Adver
        93979, -- 2507.17725 On the Interaction of Compressibility and Adversarial Robustness
        94001, -- 2505.14042 Adversarially Pretrained Transformers May Be Universally Robust In-Con
        94197, -- 2604.12817 Understanding and Improving Continuous LLM Adversarial Training via In
        94703, -- 2602.01369 Exposing and Defending the Achilles' Heel of Video Mixture-of-Experts
        95033, -- 2602.03284 Time Is All It Takes: Spike-Retiming Attacks on Event-Driven Spiking N
        96660, -- external When the Adversary Knows You Better: Adversarial Training for Learning
        98164, -- 2506.06891 Robust In-Context Reinforcement Learning Under Reward Poisoning Attack
        99888, -- 2604.19724 Benign Overfitting in Adversarial Training for Vision Transformers
        99902, -- 2606.00738 SORA: Free Second-Order Attacks in Fast Adversarial Training
        100583, -- 2605.24535 Steering Beyond the Support: Adversarial Training on Unsupervised Jail
        100704, -- 2602.20351 BiRQA: Bidirectional Robust Quality Assessment for Images
        101471, -- 2605.21999 Toward Understanding Adversarial Distillation: Why Robust Teachers Fai
        101778, -- 2602.00857 Unifying Adversarial Robustness and Training Across Text Scoring Model
        101975, -- 2511.22888 Adversarial Training for Process Reward Models
        102777, -- 2604.09024 Leave My Images Alone: Preventing Multi-Modal Large Language Models fr
        105268, -- 2503.10629 Hierarchical Self-Supervised Adversarial Training for Robust Vision Mo
        106294, -- 2607.07918 Efficient Safety Alignment of Language Models via Latent Personality T
        106809, -- 2507.08303 Keep On Going: Learning Robust Humanoid Motion Skills via Selective Ad
        107026, -- 2509.08000 AntiDote: Bi-level Adversarial Training for Tamper-Resistant LLMs
        107089, -- 2511.18138 Vulnerability-Aware Robust Multimodal Adversarial Training
        107791, -- 2511.22872 FedAU2: Attribute Unlearning for User-Level Federated Recommender Syst
        108060, -- 2511.09933 Debiased Dual-Invariant Defense for Adversarially Robust Person Re-Ide
        108365, -- 2601.17536 OTI: A Model-free and Visually Interpretable Measure of Image Attackab
        110901, -- 2509.13982 CLMTracing: Black-box User-level Watermarking for Code Language Model
        111422, -- external Mimic Blocker: Self-Supervised Adversarial Training for Voice Conversi
        111492, -- external Defending Speech-enabled LLMs Against Adversarial Jailbreak Threats
        112401, -- external Adversarially Robust Distillation by Reducing the Student-Teacher Vari
        112630, -- 2403.00942 Resilience of Entropy Model in Distributed Neural Networks
        112727, -- 2407.12443 Preventing Catastrophic Overfitting in Fast Adversarial Training: A Bi
        112944, -- 2402.18211 Catastrophic Overfitting: A Potential Blessing in Disguise
        113006, -- 2402.17976 Enhancing Tracking Robustness with Auxiliary Adversarial Defense Netwo
        113333, -- external Delving into Adversarial Robustness on Document Tampering Localization
        113517, -- 2409.20139 Characterizing Model Robustness via Natural Input Gradients
        113538, -- external Rethinking Fast Adversarial Training: A Splitting Technique To Overcom
        113612, -- 2409.08509 Exploiting Supervised Poison Vulnerability to Strengthen Self-Supervis
        115257, -- 2406.17338 Robustly Optimized Deep Feature Decoupling Network for Fatty Liver Dis
        115444, -- 2312.07067 Focus on Hiders: Exploring Hidden Threats for Enhancing Adversarial Tr
        115750, -- 2401.04727 Revisiting Adversarial Training at Scale
        115751, -- 2402.17729 Towards Fairness-Aware Adversarial Learning
        115831, -- external Towards Understanding and Improving Adversarial Robustness of Vision T
        115865, -- 2403.10073 Revisiting Adversarial Training Under Long-Tailed Distributions
        115940, -- 2403.09101 Soften to Defend: Towards Adversarial Robustness via Self-Guided Label
        115955, -- 2405.05502 Towards Accurate and Robust Architectures via Neural Architecture Sear
        115974, -- external Re-thinking Data Availability Attacks Against Deep Neural Networks
        116191, -- external Random Entangled Tokens for Adversarially Robust Vision Transformer
        116460, -- 2301.13096 Language-Driven Anchors for Zero-Shot Adversarial Robustness
        116465, -- 2310.02544 SlowFormer: Adversarial Attack on Compute and Energy Consumption of Ef
        116521, -- 2404.04647 Structured Gradient-based Interpretations via Norm-Regularized Adversa
        116782, -- 2403.17520 Boosting Adversarial Training via Fisher-Rao Norm-based Regularization
        116785, -- 2401.04350 Pre-trained Model Guided Fine-Tuning for Zero-Shot Adversarial Robustn
        116993, -- 2312.05716 Initialization Matters for Adversarial Transfer Learning
        118138, -- 2411.17936 Stealthy Multi-task Adversarial Attacks
        119097, -- 2607.10580 DiffUE: Enhancing Utility-Unlearnability Trade-off of Unlearnable Exam
        119105, -- 2607.03075 Robustness Meets Uncertainty: Evidential Adversarial Training for Robu
        119136, -- 2512.06010 Fast and Flexible Robustness Certificates for Semantic Segmentation
        119143, -- 2607.06109 RoME: Robust Mixture of Low-Rank Experts against Multiple Adversarial
        119847, -- external Gain from Neighbors: Boosting Model Robustness in the Wild via Adversa
        119946, -- 2503.01924 TAET: Two-Stage Adversarial Equalization Training on Long-Tailed  Dist
        120061, -- external On the Zero-shot Adversarial Robustness of Vision-Language Models: A T
        120146, -- 2412.02171 Can't Slow Me Down: Learning Robust and Hardware-Adaptive Object Detec
        120337, -- 2506.09237 PatchGuard: Adversarially Robust Anomaly Detection and Localization th
        120672, -- external Towards Robust Vision Transformers: Path Dependency Analysis and a Sim
        120877, -- external FedCART: Tackling Long-Tailed Distributions in Federated Adversarial T
        121041, -- external A Combination of Noise and Bilateral Filters Achieve Supralinear and S
        121437, -- external Robustness Under Data Scarcity: Few-Shot Continual Adversarial Trainin
        121555, -- external AdvFM: Lookahead Flow-Matching Velocity-Field Attacks for Imperceptibl
        121679, -- external SafeLogo: Turning Your Logos into Jailbreak Shields via Micro-Regional
        121832, -- 2603.26984 A Provable Energy-Guided Test-Time Defense Boosting Adversarial Robust
        122814, -- 2610.08773 AdvSim2Real : Training Web Agents Against Adaptive Prompt Injection in
        124186, -- 2607.10630 World Models as Adversaries: Multi-Agent Self-Play Fine-Tuning for Rob
        124242, -- external Preference-Guided Adversarial Policy Optimization for Long-Tail Robust
        124549, -- 2607.20435 Making Open-Source Text LLM Watermarks Durable Against Merging
        125540, -- external Contrastive Adversarial Training for Robust Graph Neural Networks unde
        125996, -- external RAD-TFM: Robust and Domain-Adapted Tabular Foundation Models
        126587, -- external Sparse Fine-Tuning for Parameter-Efficient Adversarial Training
        127568, -- 2610.09109 Breaking Adversarial Transferability in Fine-Tuned Speech Recognition
        127582, -- external A Simple Class-Agnostic Approach to Enhance Fair Adversarial Training
        129307, -- external Do Robust LVLMs Hallucinate More? Uncovering Robustness-Induced Halluc
        129653, -- 2609.31363 Brenier Meets Adversarial Training: Optimal Transport Geometry for Rob
        129675, -- 2602.19931 Expanding the Role of Diffusion Models for Robust Classifier Training
        129697, -- external GUARD: Scalable Gradient-based Unlearning with Adversarial Robustness
        130054, -- 2603.24511 Claudini: Autoresearch Discovers State-of-the-Art Adversarial Attack A
        130368, -- external BayesAT: Bayes-Guided Progressive Distillation for Semi-Supervised Adv
        130796  -- 2602.02626 Learning Better Certified Models from Empirically-Robust Teachers
  );

DELETE FROM paper_method_exclusions x
USING adversarial_training_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM adversarial_training_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM adversarial_training_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE adversarial_training_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adversarial-training'
  AND p.id IN (
        191, -- 1505.07818 Domain-Adversarial Training of Neural Networks
        894, -- 1709.08624 Long Text Generation via Adversarial Training with Leaked Information
        1051, -- 1801.04062 MINE: Mutual Information Neural Estimation
        1147, -- 1803.04626 Maintaining Natural Image Statistics with the Contextual Loss
        1181, -- 1803.09655 BAGAN: Data Augmentation with Balancing GAN
        1187, -- 1803.10348 Structural inpainting
        1277, -- 1805.05151 Domain Adaptation with Adversarial Training and Graph Embeddings
        1589, -- 1811.00552 Multiple-Attribute Text Style Transfer
        1643, -- 1811.09393 Learning Temporal Coherence via Self-Supervision for GAN-based Video G
        1933, -- 1903.12530 Photo-Realistic Monocular Gaze Redirection Using Generative Adversaria
        1975, -- 1904.03969 Issue Framing in Online Discussion Fora
        2068, -- 1905.01723 Few-Shot Unsupervised Image-to-Image Translation
        2115, -- 1905.08233 Few-Shot Adversarial Learning of Realistic Neural Talking Head Models
        2304, -- 1907.00448 Self-Supervised Dialogue Learning
        2320, -- 1907.02544 Large Scale Adversarial Representation Learning
        2711, -- 1910.09753 MRQA 2019 Shared Task: Evaluating Generalization in Reading Comprehens
        2813, -- 1911.05889 Generating Persona Consistent Dialogues by Exploiting Natural Language
        3194, -- 2003.03879 An Empirical Evaluation on Robustness and Uncertainty of Regularizatio
        3282, -- 2004.00248 Adversarial Transfer Learning for Punctuation Restoration
        3355, -- 2004.06824 Melanoma Detection using Adversarial Training and Deep Transfer Learni
        3356, -- 2004.06824 Melanoma Detection using Adversarial Training and Deep Transfer Learni
        3392, -- 2004.10404 Logical Natural Language Generation from Open-Domain Tables
        4268, -- 2010.02502 Denoising Diffusion Implicit Models
        4468, -- 2010.15382 Learning to Actively Learn: A Robust Approach
        5456, -- 2104.07078 UDALM: Unsupervised Domain Adaptation through Language Modeling
        5775, -- 2105.11084 Unsupervised Speech Recognition
        6327, -- 2107.13720 Convolutional Transformer based Dual Discriminator Generative Adversar
        6823, -- 2110.03313 Distributed Methods with Compressed Communication for Solving Variatio
        7212, -- 2111.07218 Meta-Voice: Fast few-shot style transfer for expressive voice cloning
        7315, -- 2111.13650 Latent Space Smoothing for Individually Fair Representations
        7319, -- 2111.13839 Towards Principled Disentanglement for Domain Generalization
        7551, -- 2112.09219 All You Need is RAW: Defending Against Adversarial Attacks with Camera
        7633, -- 2201.00112 SurfGen: Adversarial 3D Shape Synthesis with Explicit Surface Discrimi
        7930, -- 2202.05352 Domain Adversarial Training: A Game Perspective
        7954, -- 2202.06687 Domain Adaptation via Prompt Learning
        7996, -- 2202.08520 End-to-end Music Remastering System Using Self-supervised and Adversar
        8255, -- 2203.07593 Distraction is All You Need for Fairness
        8529, -- 2204.00570 Connect, Not Collapse: Explaining Contrastive Learning for Unsupervise
        8981, -- 2205.04682 Selective Fairness in Recommendation via Prompts
        9196, -- 2205.12952 Pretraining is All You Need for Image-to-Image Translation
        9504, -- 2206.08213 A Closer Look at Smoothness in Domain Adversarial Training
        9729, -- 2207.04129 How many perturbations break this model? Evaluating robustness beyond
        9998, -- 2208.04035 TGAVC: Improving Autoencoder Voice Conversion with Text-Guided and Adv
        10524, -- 2210.01029 WaveFit: An Iterative and Non-autoregressive Neural Vocoder based on F
        11046, -- 2210.13811 MetaSpeech: Speech Effects Switch Along with Environment for Metaverse
        11048, -- 2210.13836 Deconfounding Legal Judgment Prediction for European Court of Human Ri
        12245, -- 2212.14169 Discriminator-Cooperated Feature Map Distillation for GAN Compression
        12736, -- 2302.00194 Free Lunch for Domain Adversarial Training: Environment Label Smoothin
        12738, -- 2302.00236 Generative Adversarial Symmetry Discovery
        12788, -- 2302.01330 SceneDreamer: Unbounded 3D Scene Generation from 2D Image Collections
        12870, -- 2302.02607 Target-based Surrogates for Stochastic Optimization
        13009, -- 2302.05185 On Penalty-based Bilevel Gradient Descent Method
        13224, -- 2302.10536 Nonparallel Emotional Voice Conversion For Unseen Speaker-Emotion Pair
        14173, -- 2303.15124 Blind Inpainting with Object-aware Discrimination for Artificial Marke
        14249, -- 2303.16456 Global Adaptation meets Local Generalization: Unsupervised Domain Adap
        14290, -- 2303.17156 MAHALO: Unifying Offline Reinforcement Learning and Imitation Learning
        15417, -- 2305.06176 Fine-tuning Language Models with Generative Adversarial Reward Modelli
        15599, -- 2305.09167 Adversarial Speaker Disentanglement Using Unannotated External Data fo
        16560, -- 2305.18712 Can We Evaluate Domain Adaptation Models Without Target-Domain Labels?
        16965, -- 2306.02842 Improving Conversational Recommendation Systems via Counterfactual Dat
        17189, -- 2306.05426 SequenceMatch: Imitation Learning for Autoregressive Sequence Modellin
        17230, -- 2306.06044 GANeRF: Leveraging Discriminators to Optimize Neural Radiance Fields
        17352, -- 2306.07691 StyleTTS 2: Towards Human-Level Text-to-Speech through Style Diffusion
        18095, -- 2307.03838 RADAR: Robust AI-Text Detection via Adversarial Learning
        18272, -- 2307.07928 Reinforced Disentanglement for Face Swapping without Skip Connection
        18970, -- 2308.03166 Strategic Preys Make Acute Predators: Enhancing Camouflaged Object Det
        19686, -- 2308.12045 CgT-GAN: CLIP-guided Text GAN for Image Captioning
        19731, -- 2308.12605 APLA: Additional Perturbation for Latent Noise with Adversarial Traini
        20793, -- 2309.13006 Deep3DSketch+: Rapid 3D Modeling from Single Free-hand Sketches
        21348, -- 2310.02279 Consistency Trajectory Models: Learning Probability Flow ODE Trajector
        21370, -- 2310.02611 Analyzing and Improving Optimal-Transport-based Adversarial Networks
        22335, -- 2310.14189 Improved Techniques for Training Consistency Models
        23429, -- 2311.09661 Evolving Domain Adaptation of Pretrained Language Models for Text Clas
        23516, -- 2311.11208 LogicNet: A Logical Consistency Embedded Face Attribute Learning Netwo
        25582, -- 2401.04056 A Minimaximalist Approach to Reinforcement Learning from Human Feedbac
        25603, -- 2401.04348 LAMPAT: Low-Rank Adaption for Multilingual Paraphrasing Using Adversar
        25644, -- 2401.05018 AdvMT: Adversarial Motion Transformer for Long-term Human Motion Predi
        26279, -- 2401.14111 Image Synthesis with Graph Conditioning: CLIP-Guided Diffusion Models
        27287, -- 2402.08787 Rethinking Machine Unlearning for Large Language Models
        27964, -- 2402.16321 Self-Supervised Speech Quality Estimation and Enhancement Using Only C
        28514, -- 2403.04493 What makes an image realistic?
        28670, -- 2403.06807 Multistep Consistency Models
        28944, -- 2403.10662 SwinMTL: A Shared Architecture for Simultaneous Depth Estimation and S
        29362, -- 2403.15690 EAGLE: A Domain Generalization Framework for AI-generated Text Detecti
        29714, -- 2404.00569 CM-TTS: Enhancing Real Time Text-to-Speech Synthesis Efficiency throug
        30392, -- 2404.09995 Taming Latent Diffusion Model for Neural Radiance Field Inpainting
        31211, -- 2405.06780 Deep MMD Gradient Flow without adversarial training
        31674, -- 2405.15304 Unlearning Concepts in Diffusion Model via Concept Domain Correction a
        32213, -- 2406.01018 Accent Conversion in Text-To-Speech Using Multi-Level VAE and Adversar
        32224, -- 2406.01264 FreeTumor: Advance Tumor Segmentation via Large-Scale Tumor Synthesis
        32267, -- 2406.01867 MoLA: Motion Generation and Editing with Latent Diffusion Enhanced by
        32351, -- 2406.02959 Adversarial Moment-Matching Distillation of Large Language Models
        32437, -- 2406.04254 GeoGen: Geometry-Aware Generative Modeling via Signed Distance Functio
        32454, -- 2406.04324 SF-V: Single Forward Video Generation Model
        32876, -- 2406.09293 StableMaterials: Enhancing Diversity in Material Generation via Semi-S
        33216, -- 2406.12194 Universal Score-based Speech Enhancement with High Content Preservatio
        33462, -- 2406.14962 Contextual Interaction via Primitive-based Adversarial Training For Co
        33913, -- 2407.00753 FLY-TTS: Fast, Lightweight and High-Quality End-to-End Text-to-Speech
        34716, -- 2407.11243 Representation Learning and Identity Adversarial Training for Facial B
        35277, -- 2407.19593 Bridging the Gap: Studio-like Avatar Creation from a Monocular Phone C
        36404, -- 2408.17046 Text-to-Image Generation Via Energy-Based CLIP
        36440, -- 2409.00204 MedDet: Generative Adversarial Distillation for Efficient Cervical Dis
        37041, -- 2409.12117 Low Frame-rate Speech Codec: a Codec Designed for Fast High-quality Sp
        37164, -- 2409.14013 ChronoGAN: Supervised and Embedded Generative Adversarial Networks for
        38694, -- 2410.13288 DurIAN-E 2: Duration Informed Attention Network with Adaptive Variatio
        40875, -- 2412.02030 NitroFusion: High-Fidelity Single-Step Diffusion through Dynamic Adver
        42044, -- 2412.16906 Self-Corrected Flow Distillation for Consistent One-Step and Few-Step
        42957, -- 2501.10045 HiFi-SR: A Unified Generative Transformer-Convolutional Adversarial
        43861, -- 2502.05332 Removing Neural Signal Artifacts with Autoencoder-Targeted Adversarial
        45097, -- 2502.19537 No, of course I can! Refusal Mechanisms Can Be Exploited Using Harmles
        45501, -- 2503.03708 Rethinking Video Tokenization: A Conditioned Diffusion-based Approach
        46709, -- 2503.19462 AccVideo: Accelerating Video Diffusion Model with Synthetic Dataset
        46803, -- 2503.20730 Benchmarking and optimizing organism wide single-cell RNA alignment me
        48773, -- 2505.10420 Learned Lightweight Smartphone ISP with Unpaired Data
        50622, -- 2506.05070 RIVAL: Reinforcement Learning with Iterative and Adversarial Optimizat
        50920, -- 2506.09350 Autoregressive Adversarial Post-Training for Real-Time Interactive Vid
        51224, -- 2506.14603 Align Your Flow: Scaling Continuous-Time Flow Map Distillation
        52821, -- 2509.20878 The Unanticipated Asymmetry Between Perceptual Optimization and   Asse
        53716, -- 2510.17699 GAS: Improving Discretization of Diffusion ODEs via Generalized   Adve
        54419, -- 2511.22475 Adversarial Flow Models
        54530, -- 2511.22184 Shoe Style-Invariant and Ground-Aware Learning for Dense Foot Contact
        54600, -- 2512.05150 TwinFlow: Realizing One-step Generation on Large Models with Self-adve
        55187, -- 2601.04233 LEMAS: Large A 150K-Hour Large-scale Extensible Multilingual Audio Sui
        57818, -- 2604.28190 Representation Fréchet Loss for Visual Generation
        57945, -- 2604.03873 SODA: Semi On-Policy Black-Box Distillation for Large Language Models
        59495, -- 2511.14099 FAPE-IR: Frequency-Aware Planning and Execution Framework for All-in-O
        59533, -- 2603.11589 Toward Complex-Valued Neural Networks for Waveform Generation
        60760, -- 2602.12155 FAIL: Flow Matching Adversarial Imitation Learning for Image Generatio
        61610, -- 2602.00656 Riemannian Flow Matching for Disentangled Graph Domain Adaptation
        61816, -- 2601.21688 XFACTORS: Disentangled Information Bottleneck via Contrastive Supervis
        64330, -- 2512.00937 Arabic TTS with FastPitch: Reproducible Baselines, Adversarial Trainin
        64539, -- 2511.20307 TReFT: Taming Rectified Flow Models For One-Step Image Translation
        64743, -- 2511.17138 One-Step Diffusion Transformer for Controllable Real-World Image Super
        65498, -- 2511.01275 Adversarial Spatio-Temporal Attention Networks for Epileptic Seizure F
        67673, -- 2509.22459 Universal Inverse Distillation for Matching Models with Real-Data Supe
        67774, -- 2509.21470 Score-based Idempotent Distillation of Diffusion Models
        68546, -- 2509.08188 ArtifactGen: Benchmarking WGAN-GP vs Diffusion for Label-Aware EEG   A
        68999, -- 2508.21476 Igniting Creative Writing in Small Language Models: LLM-as-a-Judge   v
        69138, -- 2508.19200 The Ramon Llull's Thinking Machine for Automated Ideation
        70255, -- 2508.02643 CAK: Emergent Audio Effects from Minimal Deep Learning
        71677, -- 2506.22423 ARMOR: Robust Reinforcement Learning-based Control for UAVs under   Ph
        71943, -- 2506.13846 Fake it till You Make it: Reward Modeling as Discriminative Prediction
        74048, -- 2503.12608 UniBERTs: Adversarial Training for Language-Universal Representations
        75423, -- 2412.14150 ZipGAN: Super-Resolution-based Generative Adversarial Network Framewor
        75811, -- 2411.08785 Zero-shot Cross-lingual Transfer Learning with Multiple Source and Tar
        78709, -- 2307.16549 DiffProsody: Diffusion-based Latent Prosody Generation for Expressive
        80485, -- 2109.15102 Fake It Till You Make It: Face analysis in the wild using synthetic da
        80677, -- 2106.06103 Conditional Variational Autoencoder with Adversarial Learning for   En
        80986, -- 2012.02096 Emergent Complexity and Zero-shot Transfer via Unsupervised Environmen
        81276, -- 2006.04021 Skill Discovery of Coordination in Multi-agent Reinforcement Learning
        81323, -- 2005.04410 High Resolution Face Age Editing
        81351, -- 2004.12331 Neural Topic Modeling with Bidirectional Adversarial Training
        82033, -- 1804.08473 Beyond Narrative Description: Generating Poetry from Images by Multi-A
        82899, -- 2605.00623 Recovering Hidden Reward in Diffusion-Based Policies
        84427, -- 2512.19049 Decoupled Generative Modeling for Human-Object Interaction Synthesis
        84525, -- 2602.18845 Echoes of Ownership: Adversarial-Guided Dual Injection for Copyright P
        85774, -- 2509.26032 Stealthy Yet Effective: Distribution-Preserving Backdoor Attacks on Gr
        88182, -- 2506.23347 CycleVAR: Repurposing Autoregressive Model for Unsupervised One-Step I
        88973, -- 2410.08976 Learning Representations of Instruments for Partial Identification of
        89886, -- 2505.05195 Concept-Based Unsupervised Domain Adaptation
        89989, -- 2506.07308 PASS: Private Attributes Protection with Stochastic Data Substitution
        90616, -- 2504.00996 TurboFill: Adapting Few-step Text-to-image Model for Fast Image Inpain
        91605, -- 2502.00156 ALBAR: Adversarial Learning approach to mitigate Biases in Action Reco
        91959, -- 2410.03973 Efficient Training of Neural Stochastic Differential Equations by Matc
        92417, -- 2502.05780 GOLD: Graph Out-of-Distribution Detection via Implicit Adversarial Lat
        92737, -- 2511.17879 Generative Adversarial Post-Training Mitigates Reward Hacking in Live
        93776, -- 2510.01153 Neural Hamilton--Jacobi Characteristic Flows for Optimal Transport
        94482, -- 2504.15457 Improving Human-AI Coordination through Online Adversarial Training an
        94586, -- 2506.01502 Learning of Population Dynamics: Inverse Optimization Meets JKO Scheme
        95056, -- 2509.22925 Soft-Di[M]O: Improving One-Step Discrete Image Generation with Soft Em
        95117, -- 1606.00709 f-GAN: Training Generative Neural Samplers using Variational Divergenc
        95542, -- external Offline-Trained GAN-Augmented Highly Adaptive Control with Multi-DoF F
        95796, -- external ARMOR: Attack-Resilient Reinforcement Learning Control for UAVs
        101408, -- 2605.08651 Privacy-Aware Video Anomaly Detection through Orthogonal Subspace Proj
        101793, -- 2406.14762 One-step Optimal Transport via Regularized Distribution Matching Disti
        102615, -- 2507.20590 Harnessing Diffusion-Yielded Score Priors for Image Restoration
        104159, -- 1902.09868 RepNet: Weakly Supervised Training of an Adversarial Reprojection Netw
        104342, -- 1705.05823 Real-Time Adaptive Image Compression
        104932, -- 2506.20563 AdvMIM: Adversarial Masked Image Modeling for Semi-Supervised Medical
        105025, -- 2505.18010 Clinical Validation of Deep Learning for Real-Time Tissue Oxygenation
        105418, -- external MindLink: Subject-agnostic Cross-Subject Brain Decoding Framework
        105659, -- 2408.13065 SIMPLE: Simultaneous Multi-plane Self-supervised Learning for Isotropi
        106163, -- 2604.17614 Characterizing Model-Native Skills
        107934, -- 2511.10935 CAT-Net: A Cross-Attention Tone Network for Cross-Subject EEG-EMG Fusi
        110319, -- 2508.19633 A Symbolic Adversarial Learning Framework for Evolving Fake News Gener
        111059, -- external Image Difference Captioning via Adversarial Preference Optimization
        111133, -- external CMSP-ST: Cross-modal Mixup with Speech Purification for End-to-End Spe
        111377, -- external Speaker Normalization and Content Restoration for Zero-Shot Voice Conv
        111985, -- 2508.17874 Vocoder-Projected Feature Discriminator
        112436, -- 2408.14738 Learning Differentially Private Diffusion Models via Stochastic Advers
        112666, -- 2411.02149 Improving Domain Generalization in Self-Supervised Monocular Depth Est
        114495, -- external Decoupled Training for Semi-supervised Medical Image Segmentation with
        115027, -- 2406.08282 Interpretable Representation Learning of Cardiac MRI via Attribute Reg
        115060, -- external Learning to Segment Multiple Organs from Multimodal Partially Labeled
        115171, -- 2503.02899 OCL: Ordinal Contrastive Learning for Imputating Features with Progres
        116381, -- 2402.19387 SeD: Semantic-Aware Discriminator for Image Super-Resolution
        116539, -- 2403.18469 Density-guided Translator Boosts Synthetic-to-Real Unsupervised Domain
        116575, -- 2403.07560 Unleashing Network Potentials for Semantic Scene Completion
        116712, -- 2402.17563 Structure-Guided Adversarial Training of Diffusion Models
        117137, -- 2403.11310 A Dual-Augmentor Framework for Domain Generalization in 3D Human Pose
        120552, -- external Identifying and Mitigating Spurious Correlation in Multi-Task Learning
        120625, -- external UMFN: Unified Multi-Domain Face Normalization for Joint Cross-domain P
        120803, -- external FlashIn: Fast and Accurate Image Inversion for Real-time Image Editing
        122274, -- 2609.38170 Adversarial Training for Pixel Diffusion
        123425, -- 2610.18472 Simplifying and Improving On-Policy Distillation for Few-Step Diffusio
        124002, -- 1805.06725 GANomaly: Semi-Supervised Anomaly Detection via Adversarial Training
        124288, -- external Robust Concept Unlearning in Diffusion Models via Directional Stabilit
        125624, -- external Heterogeneous Graph Federated Learning with Structure-Aware Data-Free
        125648, -- external Poison-then-Hide: Finetuning-Activated Backdoor Attack on Pretrained V
        125675, -- external Magnitude-preserving Layers Enable Efficient GANs
        128568, -- external Lower-Level Agnostic Bilevel Optimization
        129001, -- external Brain2voice 2.0: High-performance voice synthesis brain-computer inter
        130381, -- 2605.15959 When and Why Adversarial Training Improves PINNs: A Neural Tangent Ker
        130906, -- external Learning Domain Trajectories with Flow Matching for Gradual Domain Ada
        130934, -- 2606.05138 Generating Financial Time Series by Matching Random Convolutional Feat
        131525, -- 1711.10098 Attentive Generative Adversarial Network for Raindrop Removal from a S
        131898  -- 2611.05648 NitroFusion2: Bringing Adversarial Loss to the Text Stream of Multimod
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM adversarial_training_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING adversarial_training_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING adversarial_training_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- differential-privacy: 468 links, 0 exclusions.
CREATE TEMP TABLE differential_privacy_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'differential-privacy'
  AND p.id IN (
        422, -- 1607.00133 Deep Learning with Differential Privacy
        2153, -- 1905.12101 Differential Privacy Has Disparate Impact on Model Accuracy
        2182, -- 1906.00389 Disparate Vulnerability to Membership Inference Attacks
        3944, -- 2007.14191 Tempered Sigmoid Activations for Deep Learning with Differential Priva
        4347, -- 2010.06667 Chasing Your Long Tails: Differentially Private Prediction in Health C
        4921, -- 2101.08658 Fidelity and Privacy of Synthetic Medical Data
        5730, -- 2105.07513 Decision Making with Differential Privacy under a Fairness Lens
        5904, -- 2106.03645 Photonic Differential Privacy with Direct Feedback Alignment
        6034, -- 2106.09680 Accuracy, Interpretability, and Differential Privacy via Explainable B
        6041, -- 2106.09805 Shuffle Private Stochastic Convex Optimization
        6100, -- 2106.12576 DP-SGD vs PATE: Which Has Less Disparate Impact on Model Accuracy?
        6834, -- 2110.03620 Hyperparameter Tuning with Renyi Differential Privacy
        6877, -- 2110.05679 Large Language Models Can Be Strong Differentially Private Learners
        7349, -- 2111.15521 Node-Level Differentially Private Graph Neural Networks
        7811, -- 2201.13123 Lessons from the AdKDD'21 Privacy-Preserving ML Challenge
        7999, -- 2202.08728 Nonparametric extensions of randomized response for private confidence
        8527, -- 2204.00401 CTAB-GAN+: Enhancing Tabular Data Synthesis
        8809, -- 2204.10536 Sharper Utility Bounds for Differentially Private Models
        9321, -- 2206.00846 Faster Rates of Convergence to Stationary Points in Differentially Pri
        9400, -- 2206.03317 Subject Membership Inference Attacks in Federated Learning
        9439, -- 2206.05199 Bayesian Estimation of Differential Privacy
        9568, -- 2206.10713 Beyond Uniform Lipschitz Condition in Differentially Private Optimizat
        10491, -- 2210.00038 Differentially Private Optimization on Large Model at Small Cost
        10541, -- 2210.01504 Knowledge Unlearning for Mitigating Privacy Risks in Language Models
        10545, -- 2210.01708 Exploring Parameter-Efficient Fine-Tuning to Enable Foundation Models
        10621, -- 2210.03403 TAN Without a Burn: Scaling Laws of DP-SGD
        10832, -- 2210.08371 Sketching for First Order Method: Efficient Algorithm for Low-Bandwidt
        10925, -- 2210.11222 Learning-Augmented Private Algorithms for Multiple Quantile Release
        11037, -- 2210.13662 Analyzing Privacy Leakage in Machine Learning via Multiple Hypothesis
        11063, -- 2210.14315 Streaming Submodular Maximization with Differential Privacy
        11086, -- 2210.15042 Privately Fine-Tuning Large Language Models with Differential Privacy
        11119, -- 2210.16242 Differential Privacy has Bounded Impact on Fairness in Classification
        11180, -- 2211.01141 User-Entity Differential Privacy in Learning Natural Language Models
        11253, -- 2211.03942 Privacy-Aware Compression for Federated Learning Through Numerical Mec
        11312, -- 2211.06530 Multi-Epoch Matrix Factorization Mechanisms for Private Machine Learni
        12497, -- 2301.10053 A Linear Reconstruction Approach for Attribute Inference Attacks again
        12638, -- 2301.12535 Concurrent Shuffle Differential Privacy Under Continual Observation
        12673, -- 2301.13104 Equivariant Differentially Private Deep Learning: Why DP-SGD Needs Spa
        12716, -- 2301.13778 Differentially Private Distributed Bayesian Linear Regression with MCM
        12754, -- 2302.00539 Analyzing Leakage of Personally Identifiable Information in Language M
        12781, -- 2302.01190 On the Efficacy of Differentially Private Few-shot Image Classificatio
        12822, -- 2302.01855 From Robustness to Privacy and Back
        12893, -- 2302.03098 One-shot Empirical Privacy Estimation for Federated Learning
        12937, -- 2302.03884 DIFF2: Differential Private Optimization via Gradient Differences for
        12955, -- 2302.04260 The Test of Tests: A Framework For Differentially Private Hypothesis T
        12989, -- 2302.04787 On the Privacy-Robustness-Utility Trilemma in Distributed Learning
        13052, -- 2302.06322 One-Shot Federated Conformal Prediction
        13090, -- 2302.06943 Private Statistical Estimation of Many Quantiles
        13131, -- 2302.07975 Multi-Task Differential Privacy Under Distribution Skew
        13303, -- 2302.12559 From Noisy Fixed-Point Iterations to Private ADMM for Centralized and
        13340, -- 2302.13945 On Differentially Private Federated Linear Contextual Bandits
        13352, -- 2302.14154 Near-Optimal Algorithms for Private Online Optimization in the Realiza
        13442, -- 2303.01262 Subset-Based Instance Optimality in Private Estimation
        13562, -- 2303.04288 Polynomial Time and Private Learning of Unbounded Gaussian Mixture Mod
        13651, -- 2303.06171 DP-Fast MH: Private, Fast, and Accurate Metropolis-Hastings for Large-
        13995, -- 2303.12247 Exploring the Benefits of Visual Prompting in Differential Privacy
        14416, -- 2304.01300 On Mitigating the Utility-Loss in Differentially Private Learning: A n
        15144, -- 2305.01588 Revisiting Gradient Clipping: Stochastic bias and tight convergence gu
        15151, -- 2305.01639 Privacy-Preserving In-Context Learning for Large Language Models
        15331, -- 2305.04701 Differentially Private Attention Computation
        15341, -- 2305.04912 On User-Level Private Convex Optimization
        15400, -- 2305.05973 Synthetic Query Generation for Privacy-Preserving Deep Retrieval Syste
        15418, -- 2305.06212 Privacy-Preserving Prompt Tuning for Large Language Model Services
        16061, -- 2305.14311 Statistical Indistinguishability of Learning Algorithms
        16257, -- 2305.15560 Differentially Private Synthetic Data via Foundation Model APIs 1: Ima
        16307, -- 2305.16202 DP-SGD Without Clipping: The Lipschitz Neural Network Way
        16819, -- 2306.01121 Differentially Private Episodic Reinforcement Learning with Heavy-tail
        16866, -- 2306.01684 Harnessing large-language models to generate private synthetic text
        17009, -- 2306.03257 Generating Private Synthetic Data with Genetic Algorithms
        17156, -- 2306.05131 Conformal Prediction for Federated Uncertainty Quantification Under La
        17166, -- 2306.05275 Federated Linear Contextual Bandits with User-level Differential Priva
        17206, -- 2306.05651 Differentially Private Sharpness-Aware Training
        17643, -- 2306.11913 Randomized Quantization is All You Need for Differential Privacy in Fe
        18101, -- 2307.03941 Right to be Forgotten in the Era of Large Language Models: Implication
        18288, -- 2307.08122 Tangent Transformers for Composition, Privacy and Removal
        18485, -- 2307.11106 The importance of feature preprocessing for differentially private lin
        19607, -- 2308.11223 LDP-Feat: Image Features with Local Differential Privacy
        20339, -- 2309.06526 Exploring the Benefits of Differentially Private Pre-training and Para
        20714, -- 2309.11765 Privacy-Preserving In-Context Learning with Differentially Private Few
        21121, -- 2310.00098 Enabling Differentially Private Federated Learning for Speech Recognit
        21269, -- 2310.01568 Defending Against Authorship Identification Attacks
        21732, -- 2310.06771 Correlated Noise Provably Beats Independent Noise for Differentially P
        21787, -- 2310.07367 Improved Analysis of Sparse Linear Regression in Local Differential Pr
        22072, -- 2310.10665 Privacy Preservation in Artificial Intelligence and Extended Reality (
        22377, -- 2310.14661 Tractable MCMC for Private Learning with Pure and Gaussian Differentia
        22455, -- 2310.15526 Privacy Amplification for Matrix Mechanisms
        22578, -- 2310.16960 Privately Aligning Language Models with Reinforcement Learning
        23727, -- 2311.14632 Differentially Private SGD Without Clipping Bias: An Error-Feedback Ap
        23805, -- 2311.15792 Rethinking Privacy in Machine Learning Pipelines from an Information F
        25311, -- 2312.17493 Differentially Private Low-Rank Adaptation of Large Language Model Usi
        25924, -- 2401.09073 Fixed-Budget Differentially Private Best Arm Identification
        26070, -- 2401.11081 Learning from Aggregate responses: Instance Level versus Bag Level Los
        27142, -- 2402.06806 Systematic Assessment of Tabular Data Synthesis Algorithms
        27154, -- 2402.07002 Clients Collaborate: Flexible Differentially Private Federated Learnin
        27794, -- 2402.14397 Closed-Form Bounds for DP-SGD against Record-level Inference
        28338, -- 2403.01749 Differentially Private Synthetic Data via Foundation Model APIs 2: Tex
        28814, -- 2403.08917 Efficiently Computing Similarities to Private Datasets
        29085, -- 2403.12313 Improving LoRA in Privacy-preserving Federated Learning
        29246, -- 2403.14332 A Differentially Private Clustering Algorithm for Well-Clustered Graph
        30316, -- 2404.08847 LazyDP: Co-Designing Algorithm-Software for Scalable Training of Diffe
        31100, -- 2405.03903 Unified Locational Differential Privacy Framework
        35710, -- 2408.05212 Preserving Privacy in Large Language Models: A Survey on Current Threa
        37602, -- 2410.00751 Thinking Outside of the Differential Privacy Box: A Case Study in Text
        38437, -- 2410.10481 Model-based Large Language Model Customization as Service
        38837, -- 2410.14765 What's New in My Data? Novelty Exploration via Contrastive Generation
        39707, -- 2411.04205 Scalable DP-SGD: Shuffling vs. Poisson Subsampling
        39805, -- 2411.05750 On Differentially Private String Distances
        41141, -- 2412.05164 A Differentially Private Kaplan-Meier Estimator for Privacy-Preserving
        41288, -- 2412.07187 A New Federated Learning Framework Against Gradient Inversion Attacks
        41428, -- 2412.08969 Deep Learning Model Security: Threats and Defenses
        42290, -- 2412.20641 SafeSynthDP: Leveraging Large Language Models for Privacy-Preserving S
        42585, -- 2501.03941 Synthetic Data Privacy Metrics
        42776, -- 2501.07046 Differentially Private Kernelized Contextual Bandits
        43447, -- 2501.18914 Scaling Laws for Differentially Private Language Models
        43536, -- 2502.01013 Encrypted Large Model Inference: The Equivariant Encryption Paradigm
        43820, -- 2502.04758 Differential Privacy of Quantum and Quantum-Inspired-Classical Recomme
        43875, -- 2502.05505 Differentially Private Synthetic Data via APIs 3: Using Simulators Ins
        43925, -- 2502.06374 Hyperparameters in Score-Based Membership Inference Attacks
        44618, -- 2502.14087 Learning from End User Data with Shuffled Differential Privacy over Ke
        44762, -- 2502.15436 Fed-SB: A Silver Bullet for Extreme Communication Efficiency and Perfo
        45095, -- 2502.19525 Differentially Private Sequential Learning
        45483, -- 2503.03454 Data Poisoning Attacks to Locally Differentially Private Range Query P
        45846, -- 2503.08098 Locally Private Nonparametric Contextual Multi-armed Bandits
        46185, -- 2503.12220 PA-CFL: Privacy-Adaptive Clustered Federated Learning for Transformer-
        46828, -- 2503.21159 Multi-Objective Optimization for Privacy-Utility Balance in Differenti
        47152, -- 2504.01395 From Easy to Hard: Building a Shortcut for Differentially Private Imag
        47198, -- 2504.02114 On Model Protection in Federated Learning against Eavesdropping Attack
        47902, -- 2504.13774 DP2Unlearning: An Efficient and Guaranteed Unlearning Framework for LL
        48078, -- 2504.16438 Private Federated Learning using Preference-Optimized Synthetic Data
        48132, -- 2504.18147 NoEsis: Differentially Private Knowledge Transfer in Modular LLM Adapt
        48162, -- 2504.18939 Federated Learning-based Semantic Segmentation for Lane and Object Det
        48999, -- 2505.12805 FedSVD: Adaptive Orthogonalization for Private Federated Learning with
        51739, -- 2507.05578 The Landscape of Memorization in LLMs: Mechanisms, Measurement, and
        51902, -- 2507.11441 Implementing Adaptations for Vision AutoRegressive Model
        52110, -- 2507.22565 Efficient Differentially Private Fine-Tuning of LLMs via Reinforcement
        52366, -- 2508.10482 When Explainability Meets Privacy: An Investigation at the Intersectio
        52833, -- 2509.10696 Struct-Bench: A Benchmark for Differentially Private Structured Text
        52838, -- 2509.13755 Scrub It Out! Erasing Sensitive Memorization in Code Language Models v
        53260, -- 2510.04979 Federated Computation of ROC and PR Curves
        55406, -- 2601.10237 Fundamental Limitations of Favorable Privacy-Utility Guarantees for DP
        55939, -- 2602.07090 Concept-Aware Privacy Mechanisms for Defending Embedding Inversion Att
        57804, -- 2604.23426 Enhanced Privacy and Communication Efficiency in Non-IID Federated Lea
        58119, -- 2604.15851 DPrivBench: Benchmarking LLMs' Reasoning for Differential Privacy
        58508, -- 2604.04461 DP-OPD: Differentially Private On-Policy Distillation for Language Mod
        58786, -- 2506.04450 Learning to Diagnose Privately: DP-Powered LLMs for Radiology Report C
        60080, -- 2603.01098 Differential privacy representation geometry for medical image analysi
        60433, -- 2505.13362 Dynamic Probabilistic Noise Injection for Membership Inference Defense
        60445, -- 2602.18633 DP-RFT: Learning to Generate Synthetic Text via Differentially Private
        61148, -- 2602.05838 FHAIM: Fully Homomorphic AIM For Private Synthetic Data Generation
        61904, -- 2601.20901 Towards Sensitivity-Aware Language Models
        61970, -- 2601.19618 The role of self-supervised pretraining in differentially private medi
        64996, -- 2511.11569 Private Frequency Estimation Via Residue Number Systems
        65345, -- 2511.04261 A Parallel Region-Adaptive Differential Privacy Framework for Image
        65545, -- 2511.00487 With Privacy, Size Matters: On the Importance of Dataset Size in   Dif
        65759, -- 2510.24807 Learning to Attack: Uncovering Privacy Risks in Sequential Data Releas
        68289, -- 2509.13739 ParaAegis: Parallel Protection for Flexible Privacy-preserved Federate
        68334, -- 2509.14275 FedMentor: Domain-Aware Differential Privacy for Heterogeneous Federat
        68509, -- 2509.09097 DP-FedLoRA: Privacy-Enhanced Federated Fine-Tuning for On-Device Large
        68755, -- 2509.05362 AI-in-the-Loop: Privacy Preserving Real-Time Scam Detection and   Conv
        69916, -- 2508.14062 Assessing and Mitigating Data Memorization Risks in Fine-Tuned Large
        69969, -- 2508.06377 DP-SPRT: Differentially Private Sequential Probability Ratio Tests
        70401, -- 2508.00718 Democratizing Tabular Data Access with an Openx2013Source   Syntheticx
        70910, -- 2507.15997 "We Need a Standard": Toward an Expert-Informed Privacy Label for Diff
        71114, -- 2507.11324 A Review of Privacy Metrics for Privacy-Preserving Synthetic Data Gene
        71289, -- 2507.07316 AdeptHEQ-FL: Adaptive Homomorphic Encryption for Federated Learning of
        71399, -- 2507.04528 Towards integration of Privacy Enhancing Technologies in Explainable
        71542, -- 2507.01154 FlashDP: Private Training Large Language Models with Efficient DP-SGD
        72286, -- 2506.05407 PCEvolve: Private Contrastive Evolution for Synthetic Dataset Generati
        72462, -- 2506.00745 Controlling the Spread of Epidemics on Networks with Differential   Pr
        72473, -- 2506.00660 Differential privacy for medical deep learning: methods, tradeoffs, an
        74215, -- 2403.07588 Visual Privacy Auditing with Diffusion Models
        74336, -- 2503.01482 Revisiting Locally Differentially Private Protocols: Towards Better
        74640, -- 2502.12103 CriteoPrivateAd: A Real-World Bidding Dataset to Design Private   Adve
        75032, -- 2410.00542 Differentially Private Active Learning: Balancing Effective Data Selec
        75233, -- 2501.05737 Efficient Gradient Tracking Algorithms for Distributed Optimization
        75353, -- 2412.19291 RAG with Differential Privacy
        75413, -- 2412.14832 Federated Heavy Hitter Analytics with Local Differential Privacy
        75507, -- 2412.09222 Building a Privacy Web with SPIDEr -- Secure Pipeline for Information
        75771, -- 2411.12451 Empirical Privacy Evaluations of Generative and Predictive Machine Lea
        76259, -- 2409.19078 Differential privacy enables fair and accurate AI-based analysis of sp
        76698, -- 2407.16405 On Differentially Private 3D Medical Image Synthesis with Controllable
        76937, -- 2406.13985 The Elusive Pursuit of Reproducing PATE-GAN: Benchmarking, Auditing, D
        77294, -- 2405.06368 DP-DyLoRA: Fine-Tuning Transformer-Based Models On-Device under Differ
        77494, -- 2404.03873 PrivShape: Extracting Shapes in Time Series under User-Level Local   D
        77649, -- 2403.07842 DP-TLDM: Differentially Private Tabular Latent Diffusion Model
        78143, -- 2312.04404 On the Impact of Multi-dimensional Local Differential Privacy on Fairn
        78273, -- 2311.04037 Causal Discovery Under Local Privacy
        78567, -- 2309.01597 Revealing the True Cost of Locally Differentially Private Protocols: A
        78739, -- 2307.11939 Batch Clipping and Adaptive Layerwise Clipping for Differential Privat
        78756, -- 2307.07744 On the Utility Gain of Iterative Bayesian Update for Locally Different
        78865, -- 2306.12608 DP-BREM: Differentially-Private and Byzantine-Robust Federated Learnin
        79099, -- 2304.12845 (Local) Differential Privacy has NO Disparate Impact on Fairness
        79341, -- 2302.12020 Personalized Privacy-Preserving Framework for Cross-Silo Federated Lea
        79385, -- 2302.01622 Private, fair and accurate: Training large-scale, privacy-preserving A
        79494, -- 2212.05796 Generalizing DP-SGD with Shuffling and Batch Clipping
        79645, -- 2210.11542 Sketching Meets Differential Privacy: Fast Algorithm for Dynamic   Kro
        79702, -- 2210.00262 Frequency Estimation of Evolving Data Under Local Differential Privacy
        80011, -- 2205.02648 Multi-Freq-LDPy: Multiple Frequency Estimation Under Local Differentia
        80024, -- 2205.00436 Differentially Private Multivariate Time Series Forecasting of Aggrega
        80084, -- 2204.00850 Production of Categorical Data Verifying Differential Privacy: Concept
        80322, -- 2112.07061 Differentially Private Data Publication with Multi-level Data Utility
        80343, -- 2112.01704 Differential Privacy in Privacy-Preserving Big Data and Learning: Chal
        80349, -- 2112.00828 The Price of Differential Privacy under Continual Observation
        80403, -- 2111.04636 Improving the utility of locally differentially private protocols for
        80473, -- 2110.01643 Privacy enabled Financial Text Classification using Differential Priva
        80518, -- 2109.07269 Random Sampling Plus Fake Data: Multidimensional Frequency Estimates W
        81460, -- 2001.09700 DP-CGAN: Differentially Private Synthetic Data and Label Generation
        81532, -- 1911.07135 The Secret Revealer: Generative Model-Inversion Attacks Against Deep N
        82041, -- 1804.06752 When the signal is in the noise: Exploiting Diffix's Sticky Noise
        84002, -- 2504.10190 Differentially Private 2D Human Pose Estimation
        84368, -- 2512.08443 Fully Decentralized Certified Unlearning
        84567, -- 2602.19945 DP-FedAdamW: An Efficient Optimizer for Differentially Private Federat
        84728, -- 2603.03711 LDP-Slicing: Local Differential Privacy for Images via Randomized Bit-
        85475, -- 2604.27833 Taming Noise-Induced Prototype Degradation for Privacy-Preserving Pers
        85920, -- 2506.12994 Differentially Private Bilevel Optimization: Efficient Algorithms with
        85965, -- 2503.07199 How Well Can Differential Privacy Be Audited in One Run?
        86048, -- 2510.00574 Private Online Learning against an Adaptive Adversary: Realizable and
        86173, -- 2502.08202 Privacy amplification by random allocation
        86198, -- 2509.16180 Query-Efficient Locally Private Hypothesis Selection via the Scheffe G
        86228, -- 2509.08195 Sketched Gaussian Mechanism for Private Federated Learning
        86237, -- 2505.14251 A Private Approximation of the 2nd-Moment Matrix of Any Subsamplable I
        86290, -- 2509.16915 Differential Privacy for Euclidean Jordan Algebra with Applications to
        86319, -- 2407.04884 Convex Approximation of Two-Layer ReLU Networks for Hidden State Diffe
        86335, -- 2505.15647 Second-Order Convergence in Private Stochastic Non-Convex Optimization
        86352, -- 2505.24603 The Gaussian Mixing Mechanism: Differential Privacy via Gaussian Sketc
        86371, -- 2506.08312 Private Evolution Converges
        86373, -- 2509.07055 Sequentially Auditing Differential Privacy
        86395, -- 2503.21071 Purifying Approximate Differential Privacy with Randomized Post-proces
        86449, -- 2506.08347 Differentially Private Relational Learning with Entity-level Privacy G
        86463, -- 2402.06674 Impact of Dataset Properties on Membership Inference Vulnerability of
        86494, -- 2510.09485 Locally Optimal Private Sampling: Beyond the Global Minimax
        86528, -- 2507.06969 Unifying Re-Identification, Attribute Inference, and Data Reconstructi
        86545, -- 2505.12541 Private Statistical Estimation via Truncation
        86626, -- 2505.05613 Optimal Regret of Bandits under Differential Privacy
        86639, -- 2507.02974 InvisibleInk: High-Utility and Low-Cost Text Generation with Different
        86749, -- 2510.04027 Multi-Class Support Vector Machine with Differential Privacy
        86838, -- 2405.13375 Adaptive Data Analysis for Growing Data
        86883, -- 2506.15018 Private Continual Counting of Unbounded Streams
        86900, -- 2505.20189 Private Geometric Median in Nearly-Linear Time
        86963, -- 2506.07555 Synthesize Privacy-Preserving High-Resolution Images via Private Textu
        86968, -- 2506.06549 GeoClip: Geometry-Aware Clipping for Differentially Private SGD
        86988, -- 2502.06597 Continual Release Moment Estimation with Differential Privacy
        87023, -- 2508.15183 Private Hyperparameter Tuning with Ex-Post Guarantee
        87065, -- 2507.09990 Differentially Private Federated Low Rank Adaptation Beyond Fixed-Matr
        87144, -- 2502.17384 On Traceability in $\ell_p$ Stochastic Convex Optimization
        87149, -- 2506.01162 Nearly-Linear Time Private Hypothesis Selection with the Optimal Appro
        87316, -- 2505.13662 Differentially Private Quantiles with Smaller Error
        87323, -- 2408.01798 Differentially Private Gomory-Hu Trees
        87340, -- 2505.23620 Instance-Optimality for Private KL Distribution Estimation
        87341, -- 2503.11897 PREAMBLE: Private and Efficient Aggregation via Block Sparse Vectors
        87401, -- 2506.19881 Blameless Users in a Clean Room: Defining Copyright Protection for Gen
        88237, -- 2406.01355 Differentially Private Fine-Tuning of Diffusion Models
        88471, -- 2508.01749 Improving Noise Efficiency in Privacy-preserving Dataset Distillation
        88565, -- 2506.05503 On Differential Privacy for Adaptively Solving Search Problems via Ske
        88589, -- 2406.13433 Certification for Differentially Private Prediction in Gradient-Based
        88631, -- 2503.11850 Local Pan-privacy for Federated Analytics
        88725, -- 2503.03622 It's My Data Too: Private ML for Datasets with Multi-User Training Exa
        88733, -- 2503.12347 Synthesizing Privacy-Preserving Text Data via Finetuning *without* Fin
        88758, -- 2410.16161 DMM: Distributed Matrix Mechanism for Differentially-Private Federated
        88808, -- 2505.02383 Connecting Thompson Sampling and UCB: Towards More Efficient Trade-off
        88855, -- 2502.17150 Differential Privacy Guarantees of Markov Chain Monte Carlo Algorithms
        88899, -- 2506.19220 Private Model Personalization Revisited
        88927, -- 2506.02563 Privacy-Preserving Federated Convex Optimization: Balancing Partial-Pa
        88965, -- 2506.05101 Privacy Amplification Through Synthetic Data: Insights from Linear Reg
        88971, -- 2505.22449 Private Lossless Multiple Release
        88985, -- 2507.01873 Breaking the n1.5 Additive Error Barrier for Private and Efficient Gra
        89013, -- 2412.00497 Distributed Differentially Private Data Analytics via Secure Sketching
        89075, -- 2502.01168 On the Private Estimation of Smooth Transport Maps
        89191, -- 2506.17292 Theoretically Unmasking Inference Attacks Against LDP-Protected Client
        89230, -- 2501.18121 Optimal Survey Design for Private Mean Estimation
        89246, -- 2503.09889 Tracking The Best Expert Privately
        89261, -- 2308.00957 Improving the Variance of Differentially Private Randomized Experiment
        89276, -- 2505.23682 Differentially Private Space-Efficient Algorithms for Counting Distinc
        89287, -- 2505.24737 Adapting to Linear Separable Subsets with Large-Margin in Differential
        89334, -- 2410.05880 Improved Sample Complexity for Private Nonsmooth Nonconvex Optimizatio
        89341, -- 2504.14730 Optimizing Noise Distributions for Differential Privacy
        89392, -- 2505.21790 Faster Rates for Private Adversarial Bandits
        89414, -- 2405.20415 Differentially Private Boxplots
        89465, -- 2502.08878 Scalable Private Partition Selection via Adaptive Weighting
        89478, -- 2411.05733 Differential Privacy Under Class Imbalance: Methods and Empirical Insi
        89578, -- 2503.12314 Empirical Privacy Variance
        89665, -- 2502.15929 Approximate Differential Privacy of the ℓ2 Mechanism
        89834, -- 2406.11206 Retraining with Predicted Hard Labels Provably Increases Model Accurac
        89883, -- 2505.05922 Cape: Context-Aware Prompt Perturbation Mechanism with Differential Pr
        89916, -- 2502.00245 Contrastive Private Data Synthesis via Weighted Multi-PLM Fusion
        89928, -- 2505.01874 Towards Trustworthy Federated Learning with Untrusted Participants
        89977, -- 2502.08007 The Role of Randomness in Stability
        89999, -- 2502.02410 Privacy Amplification by Structured Subsampling for Deep Differentiall
        90007, -- 2502.02990 Lightweight Protocols for Distributed Private Quantile Estimation
        90010, -- 2505.15694 A Unified Theoretical Analysis of Private and Robust Offline Alignment
        91203, -- 2501.13904 Privacy-Preserving Personalized Federated Prompt Learning for Multimod
        91251, -- 2410.06186 The Last Iterate Advantage: Empirical Auditing and Principled Heuristi
        91302, -- 2409.08301 Gaussian Differentially Private Human Faces Under a Face Radial Curve
        91331, -- 2501.18532 Differentially Private Steering for Large Language Model Alignment
        91374, -- 2502.12794 RAPID: Retrieval Augmented Training of Differentially Private Diffusio
        91524, -- 2410.12085 Data-adaptive Differentially Private Prompt Synthesis for In-Context L
        91539, -- 2406.02502 Singular Subspace Perturbation Bounds via Rectangular Random Matrix Di
        91567, -- 2502.18706 Differentially Private Federated Learning with Time-Adaptive Privacy S
        91573, -- 2501.13890 Federated Granger Causality Learning For Interdependent Clients With S
        91692, -- 2405.14457 Tighter Privacy Auditing of DP-SGD in the Hidden State Threat Model
        91804, -- 2410.03883 DiSK: Differentially Private Optimizer with Simplified Kalman Filter f
        92002, -- 2410.07738 Enhancing Federated Domain Adaptation with Multi-Domain Prototype-Base
        92017, -- 2409.07025 CPSample: Classifier Protected Sampling for Guarding Training Data Dur
        92029, -- 2310.03104 Differentially private optimization for non-decomposable objective fun
        92030, -- 2503.03486 Differentially private learners for heterogeneous treatment effects
        92034, -- 2410.06881 Privately Counting Partially Ordered Data
        92035, -- 2410.01068 Convergent Privacy Loss of Noisy-SGD without Convexity and Smoothness
        92235, -- 2502.12976 Does Training with Synthetic Data Truly Protect Privacy?
        92306, -- 2410.07502 Adaptive Batch Size for Privately Finding Second-Order Stationary Poin
        92349, -- 2405.15150 Enhancing Learning with Label Differential Privacy by Vector Approxima
        92356, -- 2503.00703 Towards hyperparameter-free optimization with differential privacy
        92605, -- 2603.03226 Adaptive Methods Are Preferable in High Privacy Settings: An SDE Persp
        92715, -- 2605.07930 INO-SGD: Addressing Utility Imbalance under Individualized Differentia
        92755, -- 2503.16251 RESFL: An Uncertainty-Aware Framework for Responsible Federated Learni
        92944, -- 2512.06971 Prediction with Expert Advice under Local Differential Privacy
        92967, -- 2602.10360 Skirting Additive Error Barriers for Private Turnstile Streams
        93031, -- 2505.22703 Private Rate-Constrained Optimization with Applications to Fair Learni
        93036, -- 2408.15621 Convergent Differential Privacy Analysis for General Federated Learnin
        93120, -- 2507.15836 Optimizing Canaries for Privacy Auditing with Metagradient Descent
        93538, -- 2406.07698 Label Smoothing Improves Machine Unlearning
        93592, -- 2503.09538 Differentially Private Equilibrium Finding in Polymatrix Games
        93663, -- 2509.22794 Differentially Private Two-Stage Gradient Descent for Instrumental Var
        93805, -- 2509.21800 Federated Learning of Quantile Inference under Local Differential Priv
        93808, -- 2511.21804 Beyond Membership: Limitations of Add/Remove Adjacency in Differential
        93853, -- 2507.04531 DP-Fusion: Token-Level Differentially Private Inference for Large Lang
        93883, -- 2603.02017 Protection against Source Inference Attacks in Federated Learning
        93947, -- 2505.12128 Back to Square Roots: An Optimal Bound on the Matrix Factorization Err
        93984, -- 2510.20616 On Optimal Hyperparameters for Differentially Private Deep Transfer Le
        94386, -- 2509.03472 DPQuant: Efficient and Private Model Training via Dynamic Quantization
        94427, -- 2510.17480 Unified Privacy Guarantees for Decentralized Learning via Matrix Facto
        94605, -- 2602.19926 Rethinking LoRA for Privacy-Preserving Federated Learning in Large Mod
        94725, -- 2510.10990 Secret-Protected Evolution for Differentially Private Synthetic Text G
        94907, -- 2603.00811 Curation Leaks: Membership Inference Attacks against Data Curation for
        98583, -- external DP-Morph: Improving the Privacy-Utility-Performance Trade-off for Diff
        98776, -- 2606.21763 From Gradient Clipping to Structural Refinement: Improving DPSGD for M
        99269, -- 2605.27782 Revisiting ML Training under Fully Homomorphic Encryption: Convergence
        99858, -- 2506.00158 Privacy Amplification in Differentially Private Zeroth-Order Optimizat
        99906, -- 2511.18006 Understanding Private Learning From Feature Perspective
        100013, -- 2601.07545 Near-Optimal Private Linear Regression via Iterative Hessian Mixing
        100057, -- 2606.18773 Private Learning with Public Feature Conditioning
        100095, -- 2602.01339 Finding Differentially Private Second Order Stationary Points in Stoch
        100104, -- 2601.22945 Persuasive Privacy
        100144, -- 2604.28032 Shuffling-Aware Optimization for Private Vector Mean Estimation
        100233, -- 2512.04008 Efficient Public Verification of Private ML via Regularization
        100234, -- 2606.09145 PrivCode++: Latent-Conditioned Differentially Private Code Generation
        100252, -- 2602.12209 Keeping a Secret Requires a Good Memory: Unconditional Streaming Lower
        100259, -- 2510.18232 ACTG-ARL: Differentially Private Conditional Text Generation with RL-B
        100300, -- 2605.01960 LAPRAS : Learning-Augmented PRivate  Answering for linear query Stream
        100349, -- 2606.14951 Differentially Private Submodular Maximization with a Knapsack Constra
        100398, -- 2601.22409 Optimization,  Generalization and Differential Privacy Bounds for Grad
        100792, -- 2605.13418 DP-KFC: Data-Free Preconditioning for Privacy-Preserving Deep Learning
        100891, -- 2602.02766 Privately Fine-Tuned LLMs Preserve Temporal Dynamics in Tabular Data
        100903, -- 2509.22213 Accuracy-First Rényi Differential Privacy and Post-Processing Immunity
        100925, -- 2606.08681 Asymptotic Optimality of the High-Dimensional Gaussian Mechanism and I
        101109, -- 2605.03425 FIBER: A Differentially Private Optimizer with Filter-Aware Innovation
        101192, -- 2605.24879 Efficient DP-SGD for LLMs with Randomized Clipping
        101680, -- 2606.08179 Differentially Private Range Subgraph Counting
        101681, -- 2604.26838 Solving Positive Linear Programs with Differential Privacy
        101835, -- 2602.04562 Optimal conversion from Rényi Differential Privacy to $f$-Differential
        101889, -- 2605.28078 Mind the Gap: Mixtures of Gaussians in Approximate Differential Privac
        101934, -- 2606.00944 PRISM: Gauge-Invariant Tangent-Space Differentially Private LoRA
        101941, -- 2601.21989 Adaptively Robust Resettable Streaming
        101998, -- 2603.01986 Accurate, Private, Secure, Federated U-statistics with Higher Degree
        102023, -- 2605.27591 Gradient Transformer: Learning to Generate Updates for LLMs
        102055, -- 2602.17284 Efficient privacy loss accounting for subsampling and random allocatio
        102072, -- 2605.30808 Differentially Private Preference Data Synthesis for Large Language Mo
        102076, -- 2606.01908 Private and Stable Test-time Adaptation with Differential Privacy
        102115, -- 2605.11170 Unlearning with Asymmetric Sources: Improved Unlearning-Utility Trade-
        102206, -- 2605.01425 Barriers to Counterfactual Credit Attribution for Autoregressive Model
        102232, -- 2504.11304 Differentially Private Geodesic Regression
        102251, -- 2606.08259 Differentially Private Synthetic Data via APIs 4: Tabular Data
        102671, -- external DP-FedSOFIM: Differentially Private Federated Stochastic Optimization
        102881, -- 2606.05004 SharedRequest: Privacy-Preserving Model-Agnostic Inference for Large L
        103618, -- 2605.18936 FedMental: Evaluating Federated Learning for Mental Health Detection f
        103652, -- 2602.13529 SecureGate: Learning When to Reveal PII Safely via Token-Gated Dual-Ad
        104380, -- 2607.06815 Behavioral Privacy Leakage in Agentic Negotiation: Formalizing and Mit
        105149, -- 2507.02671 Embedding-Based Federated Data Sharing via Differentially Private Cond
        106355, -- 2603.19258 MAPLE: Metadata Augmented Private Language Evolution
        106373, -- 2512.16059 ContextLeak: Auditing Leakage in Private In-Context Learning Methods
        106542, -- 2511.11319 Improved Differentially Private Algorithms for Rank Aggregation
        106548, -- 2511.07997 PrAda-GAN: A Private Adaptive Generative Adversarial Network with Baye
        106609, -- 2601.08603 Estimating the True Distribution of Data Collected with Randomized Res
        106721, -- 2511.09876 DP-GenG: Differentially Private Dataset Distillation Guided by DP-Gene
        106810, -- 2508.03836 DP-NCB: Privacy Preserving Fair Bandits
        106945, -- 2512.00849 Topological Federated Clustering via Gravitational Potential Fields Un
        107122, -- 2502.17772 An Improved Privacy and Utility Analysis of Differentially Private SGD
        107396, -- 2511.22270 Towards Understanding Generalization in DP-GD: A Case Study in Trainin
        107397, -- 2511.08841 Enhancing DPSGD via Per-Sample Momentum and Low-Pass Filtering
        107417, -- 2509.13625 Privacy Preserving In-Context-Learning Framework for Large Language Mo
        107687, -- 2509.23022 Copyright Infringement Detection in Text-to-Image Diffusion Models via
        107842, -- 2511.22788 PRISM: Privacy-Aware Routing for Adaptive Cloud–Edge LLM Inference via
        108155, -- 2511.07242 Privacy on the Fly: A Predictive Adversarial Transformation Network fo
        108526, -- 2501.19315 Differentially Private Linear Programming: Reduced Sub-Optimality and
        108551, -- 2601.11113 Differentially Private Subspace Fine-Tuning for Large Language Models
        110061, -- 2502.18517 RewardDS: Privacy-Preserving Fine-Tuning for Large Language Models via
        110213, -- 2508.20736 Leveraging Semantic Triples for Private Document Generation with Local
        110397, -- 2502.15857 PPC-GPT: Federated Task-Specific Compression of Large Language Models
        110761, -- external DPED: Multi-Layer Noise Distillation for Privacy-Preserving Text Embed
        112436, -- 2408.14738 Learning Differentially Private Diffusion Models via Stochastic Advers
        112821, -- external Federated Learning with Local Openset Noisy Labels
        115669, -- external In-distribution Public Data Synthesis with Diffusion Models for Differ
        116032, -- 2312.05264 All Rivers Run to the Sea: Private Learning with Asymmetric Flows
        119089, -- 2608.17415 Spectral Gradient Orthogonalization Improves Differentially Private Tr
        120705, -- 2504.00952 Personalized Federated Training of Diffusion Models with Privacy Guara
        121550, -- external FedAlign: Differentially Private Distribution Alignment for Non-IID Fe
        124010, -- 2610.22659 Exploring The Empirical Privacy Landscape of Synthetic Data
        124244, -- 2507.08158 A Unified Framework for Adversary-Aware Differential Privacy Bounds
        124351, -- 2605.20069 Smooth Partial Lotteries for Stable Randomized Selection
        124520, -- 2602.05219 Private Prediction via Shrinkage
        124523, -- external An Õptimal Differentially Private PAC Learner for Concept Classes with
        124535, -- 2610.19573 On Inherent Privacy of Posterior Sampling: A Unified R\'enyi-Divergenc
        124721, -- 2605.21780 Provable Robustness against Backdoor Attacks via the Primal-Dual Persp
        124722, -- 2610.04600 Asymptotically Optimal Best Arm Identification with Fixed-Budget under
        124909, -- external DP-EGGROLL: Centered Fitness-Vector Privatization for Backprop-Free Di
        124918, -- 2510.05416 Correlating Cross-Iteration Noise for DP-SGD using Model Curvature
        124934, -- 2510.01137 Re-examining Low Rank adaptation for private LLM fine-tuning
        125088, -- 2609.38339 Aegis: Generative Gradient Masking for Privacy-Preserving Medical Fede
        125327, -- external Settling Pure Differentially Private Covariance Estimation
        125508, -- external FedProG: Federated Graph Learning via Server-Side LLM Semantic Bridgin
        125849, -- 2609.36678 Understanding Private Evolution as Learning-Augmented Clustering
        126117, -- 2509.20283 Monitoring Violations of Differential Privacy over Time
        126137, -- external Rank-Aware Differentially Private Release of Listwise Preferences for
        126248, -- 2605.28952 Optimal Rates for Differentially Private Hypothesis Testing with E-val
        126316, -- 2605.27912 Privately Estimating Monotone Statistics in Polynomial Time
        126725, -- 2606.07443 Sort, Partition, Randomize: Optimal Binary Hypothesis Testing under Lo
        126918, -- external The Denoising Wrapper: A Modular Post-Processing Framework for Noisy F
        126942, -- external Privacy-Preserving Retrieval-Augmented Generation with Plausible Denia
        126995, -- external Shared-Noise Mechanisms for Verifiable Differentially Private Counting
        127561, -- external Inference for Many Quantiles under Local Differential Privacy
        127733, -- external Complexity of Differentially Private Selection via Federated APIs
        127781, -- external Row-Private Symmetric Cone Programming: Scale-Efficient Algorithm and
        127806, -- 2602.09499 Computationally Efficient Replicable Learning of Parities and Applicat
        127969, -- external Budget-Conditioned Clipping Policies for Differentially Private Federa
        127987, -- 2605.24295 Private Adaptive Covariance Estimation via Gaussian Graphical Models
        127995, -- external PRIME: A Modular Approach for Private Synthetic Data
        128215, -- external Optimal Rates for Adaptive Private $k$-PCA
        128249, -- 2602.00417 Shuffle and Joint Differential Privacy for Generalized Linear Contextu
        128421, -- external A Private Empirical Defense Against Privacy Audits
        128501, -- 2605.22756 Lumberjack: Better Differentially Private Random Forests through Heavy
        128520, -- 2602.04895 Privacy Amplification Persists under Unlimited Synthetic Data Release
        128532, -- external LDPCache: Locally Differentially Private Multi-Query Processing with C
        128642, -- 2604.06492 Optimal Rates for Pure $\varepsilon$-Differentially Private Stochastic
        128654, -- external Online Allocation with Differential Privacy
        128932, -- external Towards Hyperparameter Transfer for Differentially Private Optimizatio
        128993, -- 2608.27896 Online Differentially Private Consistent Clustering
        129042, -- external The Price of Locality in Label Privacy: Optimal Rates for Classificati
        129107, -- 2605.07049 Towards Differentially Private Reinforcement Learning with General Fun
        129223, -- 2602.11454 Adaptive Power Iteration Method for Differentially Private PCA
        129235, -- 2601.21636 Sampling-Free Privacy Accounting for Matrix Mechanisms under Random Al
        129320, -- 2604.07238 On the Price of Privacy for Language Identification and Generation
        129367, -- 2610.08460 One-Shot Private Confidence Regions via Resampling
        129597, -- 2604.20985 Differentially Private Model Merging
        129749, -- external Ask in the Crowd: Differentially Private LLM Inference via Dummy-Augme
        129768, -- external Privately Clipping Heavy-Tailed Data
        129850, -- external Privacy Meets Hierarchy: Differentially Private Distributed Trilevel L
        130000, -- external Private Online Prediction from Experts with Small Losses
        130334, -- external Efficient Adaptive Data Analysis over Dense Data Distributions
        130409, -- external High Performance Differentially Private Fine-Tuning using Dataset Dist
        130518, -- 2601.01710 Publishing Below-Threshold Triangle Counts under Local Weight Differen
        130685, -- external On Differential Private $\ell_1$, $\ell_2$ and $\ell_p^p$ Distance Que
        130801, -- external Improved Regret bounds in Tabular Reinforcement Learning under Local D
        130810, -- 2606.04683 Minimax Private Estimation of Smooth Optimal-Transport Maps
        130904, -- 2602.06756 𝑓-Differential Privacy Filters: Validity and Approximate Solutions
        130938, -- external On Differentially Private Mechanisms for Linear Regression
        131031, -- external Differentially Private Sparse Reward Estimation with Preference Feedba
        131042, -- 2511.13502 SnapAudit: Active Auditing of Differentially Private In-Context Learni
        131230, -- external Optimal Algorithms for Fixed-Graph Multi-Attribution Privacy
        131242  -- external Optimal Byzantine-resilient Federated Learning with User-level Differe
  );

DELETE FROM paper_method_exclusions x
USING differential_privacy_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM differential_privacy_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM differential_privacy_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- score-matching: 277 links, 1 exclusions.
CREATE TEMP TABLE score_matching_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'score-matching'
  AND p.id IN (
        22, -- 1211.4246 What Regularized Auto-Encoders Learn from the Data Generating Distribu
        2338, -- 1907.05600 Generative Modeling by Estimating Gradients of the Data Distribution
        3764, -- 2006.11239 Denoising Diffusion Probabilistic Models
        4095, -- 2009.00713 WaveGrad: Estimating Gradients for Waveform Generation
        4441, -- 2010.13132 Multiscale Score Matching for Out-of-Distribution Detection
        4628, -- 2011.13456 Score-Based Generative Modeling through Stochastic Differential Equati
        5717, -- 2105.06337 Grad-TTS: A Diffusion Probabilistic Model for Text-to-Speech
        5805, -- 2105.14080 Gotta Go Fast When Generating Data with Score-Based Models
        7219, -- 2111.08005 Solving Inverse Problems in Medical Imaging with Score-Based Generativ
        7429, -- 2112.03696 Noise Distribution Adaptive Self-Supervised Image Denoising using Twee
        7872, -- 2202.02514 Score-based Generative Modeling of Graphs via the System of Stochastic
        7879, -- 2202.02763 Riemannian Score-Based Generative Modelling
        8435, -- 2203.14206 Denoising Likelihood Score Matching for Conditional Score-based Data G
        8510, -- 2203.17004 Speech Enhancement with Score-Based Generative Models in the Complex S
        8524, -- 2204.00227 Perception Prioritized Training of Diffusion Models
        9394, -- 2206.03065 Universal Speech Enhancement with Score-based Diffusion
        9438, -- 2206.05173 How Much is Enough? A Study on Diffusion Times in Score-based Generati
        9484, -- 2206.07632 Exploring Chemical Space with Score-based Out-of-distribution Generati
        10135, -- 2208.11970 Understanding Diffusion Models: A Unified Perspective
        10241, -- 2209.03855 SE(3)-DiffusionFields: Learning smooth cost functions for joint grasp
        10415, -- 2209.12753 On Investigating the Conservative Property of Score-Based Generative M
        11204, -- 2211.01916 Improved Analysis of Score-based Generative Modeling: User-Friendly Bo
        11223, -- 2211.02590 Modeling Temporal Data as Continuous Functions with Stochastic Process
        11567, -- 2211.13006 Quantized Compressed Sensing with Score-based Generative Models
        11717, -- 2211.17091 Refining Generative Process with Discriminator Guidance in Score-based
        12236, -- 2212.13771 Exploring Vision Transformers as Diffusion Learners
        12341, -- 2301.03028 Generative Time Series Forecasting with Diffusion, Denoise, and Disent
        12867, -- 2302.02591 Generative Diffusion Models on Graphs: Methods and Applications
        12931, -- 2302.03791 How to Trust Your Diffusion Model: A Convex Optimization Approach to C
        12986, -- 2302.04759 Robust and Scalable Bayesian Online Changepoint Detection
        13011, -- 2302.05290 Removing Structured Noise with Diffusion Models
        13229, -- 2302.10688 On Calibrating Diffusion Probabilistic Models
        13418, -- 2303.00800 Continuous-Time Functional Diffusion Processes
        13465, -- 2303.01748 A Complete Recipe for Diffusion Generative Models
        13468, -- 2303.01861 Diffusion Models are Minimax Optimal Distribution Estimators
        13793, -- 2303.08797 Stochastic Interpolants: A Unifying Framework for Flows and Diffusions
        14477, -- 2304.02532 Goal-Conditioned Imitation Learning using Score-based Diffusion Polici
        14586, -- 2304.04740 Reflected Diffusion Models
        14901, -- 2304.11751 Score-Based Diffusion Models as Principled Priors for Inverse Imaging
        14968, -- 2304.13214 Single-View Height Estimation with Conditional Diffusion Probabilistic
        15121, -- 2305.01166 Solving Inverse Problems with Score-Based Generative Priors learned fr
        15690, -- 2305.10699 Dirichlet Diffusion Score Model for Biological Sequence Generation
        16227, -- 2305.15267 Training Energy-Based Normalizing Flow with Score-Matching Objectives
        16487, -- 2305.18231 High-Fidelity Image Compression with Score-based Generative Models
        16569, -- 2305.18766 HiFA: High-fidelity Text-to-3D Generation with Advanced Diffusion Guid
        16582, -- 2305.18900 One-Line-of-Code Data Mollification Improves Optimization of Likelihoo
        16755, -- 2306.00602 Approximate Stein Classes for Truncated Density Estimation
        16997, -- 2306.03109 Machine Learning Force Fields with Data Cost Aware Training
        16999, -- 2306.03117 Str2Str: A Score-based Framework for Zero-shot Protein Conformation Sa
        18010, -- 2307.02037 Reverse Diffusion Monte Carlo
        20164, -- 2309.03199 Matcha-TTS: A fast TTS architecture with conditional flow matching
        20575, -- 2309.09968 Generating and Imputing Tabular Data via Diffusion and Flow-based Grad
        20611, -- 2309.10450 Unsupervised speech enhancement with diffusion-based generative models
        20654, -- 2309.11043 Score Mismatching for Generative Modeling
        20846, -- 2309.13598 On the Posterior Distribution in Denoising: Application to Uncertainty
        21061, -- 2309.16948 Denoising Diffusion Bridge Models
        21064, -- 2309.16984 Consistency Models as a Rich and Efficient Policy Class for Reinforcem
        21145, -- 2310.00311 Efficient Planning with Latent Diffusion
        21293, -- 2310.01762 Sampling Multimodal Distributions with the Vanilla Score: Benefits of
        21348, -- 2310.02279 Consistency Trajectory Models: Learning Probability Flow ODE Trajector
        21946, -- 2310.09031 MINDE: Mutual Information Neural Diffusion Estimation
        21989, -- 2310.09656 Mixed-Type Tabular Data Synthesis with Score-based Diffusion in Latent
        22194, -- 2310.12395 Closed-Form Diffusion Models
        22571, -- 2310.16834 Discrete Diffusion Modeling by Estimating the Ratios of the Data Distr
        22787, -- 2310.20030 Scaling Riemannian Diffusion Models
        23522, -- 2311.11284 LucidDreamer: Towards High-Fidelity Text-to-3D Generation via Interval
        23822, -- 2311.15996 Closing the ODE-SDE gap in score-based diffusion models through the Fo
        24883, -- 2312.10431 Continuous Diffusion for Mixed-Type Tabular Data
        25190, -- 2312.15707 High-Fidelity Diffusion-based Image Editing
        25493, -- 2401.02414 Bring Metric Functions into Diffusion Models
        25596, -- 2401.04283 FADI-AEC: Fast Score Based Diffusion Model Guided by Far-end Signal fo
        26376, -- 2401.15604 Neural Network-Based Score Estimation in Diffusion Models: Optimizatio
        26537, -- 2401.17958 Convergence Analysis for General Probability Flow ODEs of Diffusion Mo
        27233, -- 2402.08082 Score-based generative models break the curse of dimensionality in lea
        27271, -- 2402.08667 Target Score Matching
        27885, -- 2402.15170 The Surprising Effectiveness of Skip-Tuning in Diffusion Sampling
        28066, -- 2402.17517 Label-Noise Robust Diffusion Models
        28302, -- 2403.01189 Training Unbiased Diffusion Models From Biased Dataset
        28475, -- 2403.03852 Accelerating Convergence of Score-Based Diffusion Models, Provably
        29282, -- 2403.14623 Simplified Diffusion Schrödinger Bridge
        30930, -- 2404.19525 MicroDreamer: Efficient 3D Generation in $\sim$20 Seconds by Score-bas
        31401, -- 2405.11252 Dreamer XL: Towards High-Resolution Text-to-3D Generation via Trajecto
        31778, -- 2405.16577 Reflected Flow Matching
        32541, -- 2406.05396 Mean-field Chaos Diffusion Models
        32776, -- 2406.08070 CFG++: Manifold-constrained Classifier Free Guidance for Diffusion Mod
        33216, -- 2406.12194 Universal Score-based Speech Enhancement with High Content Preservatio
        34450, -- 2407.07998 What's the score? Automated Denoising Score Matching for Nonlinear Dif
        36903, -- 2409.09642 Extract and Diffuse: Latent Integration for Improved Diffusion-based S
        36957, -- 2409.10753 Investigating Training Objectives for Generative Speech Enhancement
        37999, -- 2410.05167 Presto! Distilling Steps and Layers for Accelerating Music Generation
        39293, -- 2410.21299 TV-3DG: Mastering Text-to-3D Customized Generation with Visual Prompt
        39449, -- 2410.24012 Diffusion Twigs with Loop Guidance for Conditional Graph Generation
        41028, -- 2412.03962 Local Curvature Smoothing with Stein's Identity for Efficient Score Ma
        42503, -- 2501.02680 From thermodynamics to protein design: Diffusion models for biomolecul
        43504, -- 2502.00473 Weak-to-Strong Diffusion with Reflection
        44964, -- 2502.17727 Can Score-Based Generative Modeling Effectively Handle Medical Image C
        45329, -- 2503.01485 FlowDec: A flow-based full-band general audio codec with high perceptu
        45434, -- 2503.02819 Feynman-Kac Correctors in Diffusion: Annealing, Guidance, and Product
        45849, -- 2503.08120 Uni$\textbf{F}^2$ace: Fine-grained Face Understanding and Generation w
        45857, -- 2503.08250 Aligning Text to Image in Diffusion Models is Easier Than You Think
        46554, -- 2503.17361 Gumbel-Softmax Flow Matching with Straight-Through Guidance for Contro
        48077, -- 2504.16431 Target Concrete Score Matching: A Holistic Framework for Discrete Diff
        50375, -- 2506.01320 Psi-Sampler: Initial Particle Sampling for SMC-Based Inference-Time Re
        51020, -- 2506.10634 Symmetrical Flow Matching: Unified Image Generation, Segmentation, and
        51197, -- 2506.14202 DiffusionBlocks: Blockwise Training for Generative Models via Score-Ba
        53211, -- 2510.02730 Dale meets Langevin: A Multiplicative Denoising Diffusion Model
        53993, -- 2510.27684 Phased DMD: Few-step Distribution Matching Distillation via Score   Ma
        54362, -- 2511.20462 STARFlow-V: End-to-End Video Generative Modeling with Normalizing Flow
        54377, -- 2511.15906 Unified all-atom molecule generation with neural fields
        57098, -- 2603.25832 A Neural Score-Based Particle Method for the Vlasov-Maxwell-Landau Sys
        57462, -- 2604.10465 Rethinking the Diffusion Model from a Langevin Perspective
        57839, -- 2605.00414 Trees to Flows and Back: Unifying Decision Trees and Diffusion Models
        59562, -- 2603.10874 A Physics-Informed, Global-in-Time Neural Particle Method for the Spat
        59899, -- 2603.04223 Semi-Supervised Generative Learning via Latent Space Distribution Matc
        61754, -- 2601.09931 Diffusion-based Frameworks for Unsupervised Speech Enhancement
        66863, -- 2510.06174 Thermodynamic Performance Limits for Score-Based Diffusion Models
        68856, -- 2509.05342 Delta Velocity Rectified Flow for Text-to-Image Editing
        69285, -- 2508.16990 Score Matching on Large Geometric Graphs for Cosmology Generation
        70470, -- 2507.23715 DiffuMatch: Category-Agnostic Spectral Diffusion Priors for Robust   N
        71059, -- 2507.13401 MADI: Masking-Augmented Diffusion with Inference-Time Scaling for Visu
        71673, -- 2506.22780 Multimodal Atmospheric Super-Resolution With Deep Generative Models
        72628, -- 2505.21469 PropMolFlow: Property-guided Molecule Generation with Geometry-Complet
        73101, -- 2505.07442 DiffCrysGen: A Score-Based Diffusion Model for Design of Diverse   Ino
        73407, -- 2504.15513 InstaRevive: One-Step Image Enhancement via Dynamic Score Matching
        75919, -- 2410.22421 Point cloud-based diffusion models for the Electron-Ion Collider
        77920, -- 2401.12160 ScoreDec: A Phase-preserving High-Fidelity Audio Codec with A Generali
        78917, -- 2306.04175 ScoreCL: Augmentation-Adaptive Contrastive Learning via Score-Matching
        80680, -- 2106.05527 Soft Truncation: A Universal Training Technique of Score-based Diffusi
        80879, -- 2101.03288 How to Train Your Energy-Based Models
        82899, -- 2605.00623 Recovering Hidden Reward in Diffusion-Based Policies
        84031, -- 2506.05398 2ndMatch: Finetuning Pruned Diffusion Models via Second-Order Jacobian
        85800, -- 2508.12650 Score-informed Neural Operator for Enhancing Ordering-based Causal Dis
        85843, -- 2507.08956 Beyond Scores: Proximal Diffusion Models
        85988, -- 2502.04849 Advancing Wasserstein Convergence Analysis of Score-Based Models: Insi
        86090, -- 2505.10880 Approximation and Generalization Abilities of Score-based Neural Netwo
        86154, -- 2509.15257 RespoDiff: Dual-Module Bottleneck Transformation for Responsible & Fai
        86215, -- 2506.06542 Direct Fisher Score Estimation for Likelihood Maximization
        86229, -- 2505.10311 Whitened Score Diffusion: A Structured Prior for Imaging Inverse Probl
        86277, -- 2510.02305 Diffusion Models and the Manifold Hypothesis: Log-Domain Smoothing is
        86402, -- 2507.00846 BoltzNCE: Learning likelihoods for Boltzmann Generation with Stochasti
        86478, -- 2505.18276 Preconditioned Langevin Dynamics with Score-based Generative Models fo
        86726, -- 2501.16642 A Stochastic Interpolant-based Framework for Data Assimilation
        86876, -- 2506.23726 System-Embedded Diffusion Bridge Models
        87085, -- 2508.07581 When and how can inexact generative models still sample from the data
        87100, -- 2502.10354 Dimension-free Score Matching and Time Bootstrapping for Diffusion Mod
        87336, -- 2509.15328 Kuramoto Orientation Diffusion Models
        87346, -- 2506.05310 Learning normalized image densities via dual score matching
        87828, -- 2412.01787 Pretrained Reversible Generation as Unsupervised Visual Representation
        88289, -- 2412.07229 Moderating the Generalization of Score-based Generative Model
        88343, -- 2506.23282 Autoregressive Denoising Score Matching is a Good Video Anomaly Detect
        88532, -- 2506.00557 Score Matching with Missing Data
        88546, -- 2412.20292 An analytic theory of creativity in convolutional diffusion models
        88572, -- 2506.17039 LSCD: Lomb--Scargle Conditioned Diffusion for Time series Imputation
        88583, -- 2407.09297 Learning Distances from Data with Normalizing Flows and Score Matching
        88606, -- 2502.12631 Score-Based Diffusion Policy Compatible with Reinforcement Learning vi
        88645, -- 2502.04725 Can Diffusion Models Learn Hidden Inter-Feature Rules Behind Images?
        88761, -- 2501.19158 A Theoretical Framework For Overfitting In Energy-based Modeling
        88842, -- 2504.03461 Conditioning Diffusions Using Malliavin Calculus
        89070, -- 2506.14607 Expressive Score-Based Priors for Distribution Matching with Geometry-
        89163, -- 2502.00361 Efficient Online Reinforcement Learning for Diffusion Policy
        89289, -- 2502.00557 Sampling Binary Data by Denoising through Score Functions
        89553, -- 2502.01819 Score as Action: Fine Tuning Diffusion Generative Models by Continuous
        89782, -- 2501.02298 Beyond Log-Concavity and Score Regularity: Improved Convergence Bounds
        90012, -- 2406.09570 Improving Consistency Models with Generator-Augmented Flows
        90921, -- 2505.00998 Deterministic-to-Stochastic Diverse Latent Feature Mapping for Human M
        90949, -- 2503.20297 Traversing Distortion-Perception Tradeoff using a Single Score-Based G
        91149, -- 2410.14237 Unified Convergence Analysis for Score-Based Diffusion Models with Det
        91213, -- 2503.01006 Underdamped Diffusion Bridges with Applications to Sampling
        91237, -- 2410.13855 Diffusing States and Matching Scores: A New Framework for Imitation Le
        91370, -- 2501.14856 Noise-conditioned Energy-based Annealed Rewards (NEAR): A Generative F
        91632, -- 2406.10354 SigDiffusions: Score-Based Diffusion Models for Time Series via Log-Si
        91819, -- 2405.16104 Global Well-posedness and Convergence Analysis of Score-based Generati
        91832, -- 2406.01561 Guided Score identity Distillation for Data-Free One-Step Text-to-Imag
        92012, -- 2409.18959 O(d/T) Convergence Theory for Diffusion Probabilistic Models under Min
        92215, -- 2503.03595 Towards Understanding Text Hallucination of Diffusion Models via Local
        92377, -- 2410.13738 Improved Convergence Rate for Diffusion Probabilistic Models
        92803, -- 2503.08028 Computational Bottlenecks for Denoising Diffusions
        93015, -- 2505.11853 Measurement Score-Based Diffusion Model
        93067, -- 2603.10281 Taming Score-Based Denoisers in ADMM: A Convergent Plug-and-Play Frame
        93077, -- 2507.03756 Implicit Regularisation in Diffusion Models: An Algorithm-Dependent Ge
        93148, -- 2509.25837 Distillation of Large Language Models via Concrete Score Matching
        93268, -- 2505.14429 Compositional amortized inference for large-scale hierarchical Bayesia
        93458, -- 2510.09146 Score-Based Density Estimation from Pairwise Comparisons
        93912, -- 2511.22069 Convergence Dynamics of Over-Parameterized Score Matching for a Single
        94127, -- 2601.19169 Recover Cell Tensor: Diffusion-Equivalent Tensor Completion for Fluore
        94292, -- 2509.25080 Towards a Certificate of Trust: Task-Aware OOD Detection for Scientifi
        94402, -- 2508.07631 Efficient Approximate Posterior Sampling with Annealed Langevin Monte
        95284, -- 2604.24487 Guiding Vector Field Generation Via Score-Based Diffusion Model
        96564, -- 2602.19651 Denoising Particle Filters: Learning State Estimation with Single-Step
        98873, -- 2606.27192 LISA: Likelihood Score Alignment for Visual-condition Controllable Gen
        99210, -- 2606.11155 Mean Flow Distillation: Robust and Stable Distillation for Flow Matchi
        99415, -- 2605.30153 Diffusion Models Are Statistically Optimal for Learning Low-Dimensiona
        99524, -- 2606.01847 The Lie We Tell: Correcting the Euclidean Fallacy in Vision Language A
        99555, -- 2606.03347 AugMask: Training Diffusion Models on Incomplete Tabular Data via Stoc
        100161, -- 2605.13278 Proximal-Based Generative Modeling for Bayesian Inverse Problems
        100487, -- 2601.21025 A Diffusive Classification Loss for Learning Energy-based Generative M
        100588, -- 2604.10074 Transformers Learn the Optimal DDPM Denoiser for Multi-Token GMMs
        100760, -- 2512.20523 ScoreMatchingRiesz: Score Matching for Debiased Machine Learning and P
        100779, -- 2510.08409 Optimal Stopping in Latent Diffusion Models
        100888, -- 2601.20756 Supervised Guidance Training for Infinite-Dimensional Diffusion Models
        100994, -- 2603.11319 On the Robustness of Langevin Dynamics to Score Function Error
        101015, -- 2510.22899 On the Anisotropy of Score-Based Generative Models
        101351, -- 2605.02202 CBV: Clean-label Backdoor Attacks on Vision Language Models via Diffus
        101437, -- 2605.31106 Riemannian Diffusion Models on General Manifolds via Physics-Informed
        101478, -- 2605.30038 Alignment-Guided Score Matching for Text-to-Image Alignment in Diffusi
        101513, -- 2602.06621 Infinite-Dimensional Generative Diffusions via Doob’s h-Transform
        101855, -- 2509.24710 MAD: Manifold Attracted Diffusion
        101944, -- 2602.16601 Quantifying Error Propagation and Model Collapse in Diffusion Models
        101945, -- 2510.11964 Normalization-equivariant Diffusion Models: Learning Posterior Sampler
        102056, -- 2605.30573 Zeroth-Order Non-Log-Concave Sampling with Variance Reduction and Appl
        102117, -- 2606.00496 Torus Graphs for Large Scale Neural Phase Analysis
        103934, -- 2211.09324 Blurring-Sharpening Process Models for Collaborative Filtering
        104774, -- 2512.03028 SMP: Reusable Score-Matching Motion Priors for Physics-Based Character
        105006, -- 2505.22489 Cascaded 3D Diffusion Models for Whole-body 3D 18-F FDG PET/CT synthes
        105534, -- external Phenotype Representation and Analysis via Discriminative Atypicality (
        107180, -- 2602.18355 Rethinking Flow and Diffusion Bridge Models for Speech Enhancement
        107458, -- 2506.22295 Score-Based Model for Low-Rank Tensor Recovery
        107805, -- 2601.20268 Robust SDE Parameter Estimation Under Missing Time Information Setting
        107987, -- 2508.03252 Robust Single-Stage Fully Sparse 3D Object Detection via Detachable La
        108029, -- 2601.04572 Spatial-Temporal Feedback Diffusion Guidance for Controlled Traffic Im
        108106, -- 2603.03665 Machine Pareidolia: Protecting Facial Image with Emotional Editing
        111594, -- external GTA: Towards Generative Text-To-Audio Retrieval via Multi-Scale Tokeni
        112098, -- 2505.13771 Score-Based Training for Energy-Based TTS Models
        113483, -- 2407.15739 Diffusion for Out-of-Distribution Detection on Road Scenes and Beyond
        113772, -- 2608.19987 STEP: Score-Based Temporal Energy for Human Pose Video Anomaly Detecti
        114452, -- 2403.06940 Conditional Score-Based Diffusion Model for Cortical Thickness Traject
        115044, -- external k-t Self-Consistency Diffusion: A Physics-Informed Model for Dynamic M
        115661, -- 2305.15873 Confronting Ambiguity in 6D Object Pose Estimation via Score-Based Dif
        115892, -- 2312.16519 Image Restoration by Denoising Diffusion Models with Iteratively Preco
        116698, -- 2403.14497 MULDE: Multiscale Log-Density Estimation via Denoising Score Matching
        116712, -- 2402.17563 Structure-Guided Adversarial Training of Diffusion Models
        117768, -- 2509.22476 Multi-Channel Uncertainty-Weighted Score Matching for Conditional Diff
        118517, -- 2507.09052 Contrastive Conditional–Unconditional Alignment for Long-tailed Diffus
        118618, -- 2511.17038 DAPS++: Rethinking Diffusion Inverse Problems with Decoupled Posterior
        120911, -- 2605.28962 Resolving Endpoint Underfitting in Diffusion Bridges via Noise Alignme
        120926, -- external RNED: Rotary Number Encoding and Decoding for Medical VLMs
        121869, -- external Efficient Weighted Sampling via Score-based Generative Models
        122747, -- 2609.36099 Data Unlearning via Inverse Distillation
        124172, -- 2605.09654 Metropolis-Adjusted Diffusion Models
        124236, -- 2605.16644 The Score Kalman Filter
        124257, -- 2610.18075 Causal Discovery Under Hard Selection Bias: A New Robust Score-Matchin
        124502, -- external Improving Conditional Modeling via Inter-Class Likelihood-Ratio Maximi
        124807, -- 2604.27443 ABC: Any-Subset Autoregression via Non-Markovian Diffusion Bridges in
        124927, -- 2605.10019 The two clocks and the innovation window: When and how generative mode
        125076, -- external Sticky Jump Diffusions: A Unifying Framework for Discrete, Continuous,
        125104, -- 2606.06179 Diffusion Models Observe Only Gradients: A Geometric Perspective on Sc
        125413, -- external Tabular Foundation Model for Generative Modelling
        125418, -- 2605.07950 Slowly Annealed Langevin Dynamics: Theory and Applications to Training
        125515, -- external Reversing the Roles of Signal and Noise: Modeling Noise in Astronomica
        125567, -- external Noise-Regularized Training for Learned Image Compression
        125583, -- 2605.10727 Kernel-Gradient Drifting Models
        125896, -- external Enhanced convergence guarantees of score-based generative models in $\
        125991, -- external Enabling Denoising Score Matching Type Training for Manifold Diffusion
        126074, -- 2605.26850 Learning Energy-Based Models from Stochastic Interpolants using Spatio
        126105, -- external Drifting Field Policy: Wasserstein Gradient Flow on Policy Space for O
        126219, -- 2605.14276 Training-Free Generative Sampling via Moment-Matched Score Smoothing
        126340, -- external JaSpec-LID: Local Intrinsic Dimension Estimation via Jacobian Spectra
        126719, -- 2604.06333 Drifting Fields are not Conservative
        127151, -- external Horizontal Diffusion Models: Score-based Generative Modeling on Frame-
        127691, -- external DexOPE: 6D Object Pose Estimation in Dexterous Manipulation
        127869, -- external Cauchy Scientific Networks: Loss–Architecture Alignment and Its Limit
        128104, -- external Denoising Implicit Variational Inference
        128898, -- external Likelihood-Free Generative Policy Optimization
        129358, -- 2609.33337 Safe Score Matching: Diffusion Policies with Hamilton-Jacobi Reachabil
        129510, -- 2605.06367 The Interplay of Data Structure and Imbalance in the Learning Dynamics
        129581, -- external Per-Starting-Point Plausibility and Diversity Bounds for Score-Based D
        129642, -- external ART for Diffusion Sampling: A Reinforcement Learning Approach to Times
        129656, -- 2606.22630 Scalable Maximum Entropy Reinforcement Learning for Diffusion Policies
        129870, -- 2605.08777 Measuring and Decomposing Mode Separation via the Canonical Diffusion
        129896, -- external What Kind of Diffusion Models Do We Need in Online Reinforcement Learn
        129959, -- 2605.11506 Principled Design of Diffusion-based Optimizers for Inverse Problems
        130018, -- 2606.29451 The Platonic Defense: Backdoor Defense for Self-Supervised Encoders in
        130099, -- 2604.17415 Reward Score Matching: Unifying Reward-based Fine-tuning for Flow and
        130712, -- 2510.27562 Optimal Convergence Analysis of DDPM for General Distributions
        130816, -- external Euclidean Score-Based Generative Modeling with Permutation Semantics
        132048, -- 2607.10951 Sticky Jump Diffusions: A Unifying View of Masked, Continuous, and Hyb
        132063  -- 2610.14349 Multimodal Co-Generation With Continuous Bitstream Diffusion
  );

DELETE FROM paper_method_exclusions x
USING score_matching_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM score_matching_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM score_matching_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE score_matching_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'score-matching'
  AND p.id IN (
        105168  -- external Enhancing Soft Tissue Sarcoma Classification by Mitigating Patient-Spe
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM score_matching_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING score_matching_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING score_matching_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- optimal-transport: 635 links, 3 exclusions.
CREATE TEMP TABLE optimal_transport_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'optimal-transport'
  AND p.id IN (
        1207, -- 1804.01947 Sliced-Wasserstein Autoencoder: An Embarrassingly Simple Generative Mo
        1760, -- 1901.06283 Improving Sequence-to-Sequence Learning via Optimal Transport
        1886, -- 1903.03850 Recovery Bounds on Class-Based Optimal Transport: A Sum-of-Norms Regul
        2364, -- 1907.10165 Optimal Transport-based Alignment of Learned Character Representations
        2593, -- 1909.11740 UNITER: UNiversal Image-TExt Representation Learning
        2667, -- 1910.05653 Model Fusion via Optimal Transport
        2808, -- 1911.05371 Self-labelling via simultaneous clustering and representation learning
        2866, -- 1911.11763 SuperGlue: Learning Feature Matching with Graph Neural Networks
        3805, -- 2006.14744 Graph Optimal Transport for Cross-Domain Alignment
        4146, -- 2009.06962 Puzzle Mix: Exploiting Saliency and Local Statistics for Optimal Mixup
        4218, -- 2009.13077 Distribution Matching for Crowd Counting
        4595, -- 2011.10797 Adversarial Classification: Necessary conditions and geometric flows
        5019, -- 2102.05912 On Transportation of Mini-batches: A Hierarchical Approach
        6002, -- 2106.08233 Spot the Difference: Detection of Topological Changes via Geometric Al
        6312, -- 2107.12654 Co-Transport for Class-Incremental Learning
        6465, -- 2108.09645 Improving Mini-batch Optimal Transport via Partial Transportation
        6815, -- 2110.02999 Generative Modeling with Optimal Transport Maps
        6880, -- 2110.05789 Learning Discrete Representations via Constrained Clustering for Effec
        7087, -- 2110.15538 On Cross-Layer Alignment for Model Fusion of Heterogeneous Neural Netw
        7226, -- 2111.08366 Multi-Vector Models with Textual Guidance for Fine-Grained Scientific
        7294, -- 2111.12187 Input Convex Gradient Networks
        7836, -- 2202.00665 Tutorial on amortized optimization
        8075, -- 2202.13196 Toward Interpretable Semantic Textual Similarity via Optimal Transport
        8237, -- 2203.06965 UniVIP: A Unified Framework for Self-Supervised Visual Pre-training
        8283, -- 2203.08382 Dual Diffusion Implicit Bridges for Image-to-Image Translation
        8322, -- 2203.09630 Monotonic Differentiable Sorting Networks
        8623, -- 2204.03734 MHMS: Multimodal Hierarchical Multimedia Summarization
        8856, -- 2204.12676 The Multimarginal Optimal Transport Formulation of Adversarial Multicl
        9270, -- 2205.14923 Unbalanced CO-Optimal Transport
        9282, -- 2205.15403 Neural Optimal Transport with General Cost Functionals
        9440, -- 2206.05262 Meta Optimal Transport
        9653, -- 2206.15469 Watch and Match: Supercharging Imitation with Regularized Optimal Tran
        10233, -- 2209.03316 On the Complementarity between Pre-Training and Random-Initialization
        10406, -- 2209.12172 Optimal Transport-based Identity Matching for Identity-invariant Facia
        10450, -- 2209.14577 Rectified Flow: A Marginal Preserving Approach to Optimal Transport
        10486, -- 2209.15466 Sparsity-Constrained Optimal Transport
        10586, -- 2210.02747 Flow Matching for Generative Modeling
        10608, -- 2210.03164 InfoOT: Information Maximizing Optimal Transport
        10676, -- 2210.04722 Semantics-Consistent Cross-domain Summarization via Optimal Transport
        10768, -- 2210.06662 Action Matching: Learning Stochastic Dynamics from Samples
        10894, -- 2210.10275 Towards Explaining Distribution Shifts
        11066, -- 2210.14523 OTSeq2Set: An Optimal Transport Enhanced Sequence-to-Set Model for Ext
        11183, -- 2211.01156 Entropic Neural Optimal Transport via Diffusion Processes
        11435, -- 2211.10420 Mirror Sinkhorn: Fast Online Optimization on Transport Polytopes
        12200, -- 2212.12042 Re-basin via implicit Sinkhorn differentiation
        12469, -- 2301.09017 Transfer Knowledge from Natural Language to Electrocardiography: Can W
        12554, -- 2301.11302 Minimax estimation of discontinuous optimal transport maps: The semi-d
        12589, -- 2301.11716 Pre-training for Speech Translation: CTC Meets Optimal Transport
        12658, -- 2301.12811 SAN: Inducing Metrizability of GAN with Discriminative Normalized Line
        12685, -- 2301.13197 Unlocking Slot Attention by Changing Optimal Transport Costs
        12751, -- 2302.00482 Improving and generalizing flow-based generative models with minibatch
        12903, -- 2302.03232 Linear Optimal Partial Transport Embedding
        12947, -- 2302.04065 Monge, Bregman and Occam: Interpretable Optimal Transport in High-Dime
        13000, -- 2302.04953 The Monge Gap: A Regularizer to Learn All Transport Maps
        14051, -- 2303.13290 Unsupervised Deep Probabilistic Approach for Partial Point Cloud Regis
        14094, -- 2303.13971 Optimal Transport for Offline Imitation Learning
        14650, -- 2304.06094 Energy-guided Entropic Neural Optimal Transport
        14948, -- 2304.12944 Latent Traversals in Generative Models as Potential Flows
        15639, -- 2305.09943 Demonstration-free Autonomous Reinforcement Learning via Implicit and
        16221, -- 2305.15196 Feature-aligned N-BEATS with Sinkhorn divergence
        16334, -- 2305.16406 Context-aware attention layers coupled with optimal transport domain a
        16441, -- 2305.17555 Diffeomorphic Mesh Deformation via Efficient Optimal Transport for Cor
        16558, -- 2305.18702 Adversarial Adaptive Sampling: Unify PINN and Optimal Transport for th
        16843, -- 2306.01327 Speech Translation with Foundation Models and Optimal Transport: UPC a
        16930, -- 2306.02342 Deep Optimal Transport: A Practical Algorithm for Photo-realistic Imag
        16948, -- 2306.02565 Coupled Variational Autoencoder
        17045, -- 2306.03615 PEARL: Zero-shot Cross-task Preference Alignment and Robust Reward Lea
        17079, -- 2306.04116 Unbalanced Optimal Transport for Unbalanced Word Alignment
        17269, -- 2306.06626 On Kinetic Optimal Probability Paths for Generative Models
        17409, -- 2306.08330 Multimodal Optimal Transport-based Co-Attention Transformer with Globa
        17968, -- 2307.01050 Transport meets Variational Inference: Controlled Monte Carlo Diffusio
        17978, -- 2307.01226 vONTSS: vMF based semi-supervised neural topic modeling with optimal t
        18031, -- 2307.02460 Performance Scaling via Optimal Transport: Enabling Data Selection fro
        18110, -- 2307.04096 Optimal Transport Posterior Alignment for Cross-lingual Semantic Parsi
        18317, -- 2307.08483 Differentiable Transportation Pruning
        18494, -- 2307.11308 DPM-OT: A New Diffusion Probabilistic Model Based on Optimal Transport
        18892, -- 2308.01779 Point2Mask: Point-supervised Panoptic Segmentation via Optimal Transpo
        19375, -- 2308.09228 Generalized Sum Pooling for Metric Learning
        20131, -- 2309.02429 Building a Winning Team: Selecting Source Model Ensembles using a Subm
        21221, -- 2310.01174 Light Schrödinger Bridge
        21314, -- 2310.01973 Federated Wasserstein Distance
        21370, -- 2310.02611 Analyzing and Improving Optimal-Transport-based Adversarial Networks
        21553, -- 2310.04918 SWAP: Sparse Entropic Wasserstein Regression for Robust Network Prunin
        21638, -- 2310.05719 Transformer Fusion with Optimal Transport
        21673, -- 2310.06002 LCOT: Linear circular optimal transport
        21839, -- 2310.07932 What Matters to You? Towards Visual Representation Alignment for Robot
        22420, -- 2310.15141 SpecTr: Fast Speculative Decoding via Optimal Transport
        23755, -- 2311.15100 Unbalancedness in Neural Monge Maps Improves Unpaired Domain Translati
        23816, -- 2311.15937 Optimal Transport Aggregation for Visual Place Recognition
        23920, -- 2311.17101 A High-Quality Robust Diffusion Framework for Corrupted Dataset
        24029, -- 2311.18531 Dataset Distillation via the Wasserstein Metric
        25538, -- 2401.03228 Reflected Schrödinger Bridge for Constrained Generative Modeling
        25937, -- 2401.09266 P$^2$OT: Progressive Partial Optimal Transport for Deep Imbalanced Clu
        26154, -- 2401.12253 Accelerating Sinkhorn Algorithm with Sparse Newton Iterations
        26462, -- 2401.16702 Multi-granularity Correspondence Learning from Long-term Noisy Videos
        26766, -- 2402.02444 BECLR: Batch Enhanced Contrastive Few-Shot Learning
        27210, -- 2402.07839 Towards Meta-Pruning via Optimal Transport
        27398, -- 2402.10422 Pushing the Limits of Zero-shot End-to-End Speech Translation
        27571, -- 2402.12030 Towards Cross-Tokenizer Distillation: the Universal Logit Distillation
        27866, -- 2402.14991 Quantum Theory and Application of Contextual Optimal Transport
        28024, -- 2402.17110 Sinkhorn Distance Minimization for Knowledge Distillation
        28104, -- 2402.17967 Imitation-regularized Optimal Transport on Networks: Provable Robustne
        28343, -- 2403.01781 Integrating Efficient Optimal Transport and Functional Maps For Unsupe
        29237, -- 2403.14183 OTSeg: Multi-prompt Sinkhorn Attention for Zero-Shot Semantic Segmenta
        29633, -- 2403.19655 GaussianCube: A Structured and Explicit Radiance Representation for 3D
        29751, -- 2404.00925 LLMs are Good Sign Language Translators
        29938, -- 2404.03446 SP$^2$OT: Semantic-Regularized Progressive Partial Optimal Transport f
        30364, -- 2404.09632 Bridging Vision and Language Spaces with Assignment Prediction
        31584, -- 2405.14449 Adversarial Schrödinger Bridge Matching
        32580, -- 2406.05882 Distributional Preference Alignment of LLMs via Optimal Transport
        32614, -- 2406.06279 Multi-Prompting Decoder Helps Better Language Understanding
        33197, -- 2406.12042 Not All Prompts Are Made Equal: Prompt-based Pruning of Text-to-Image
        33235, -- 2406.12329 Opt-Out: Investigating Entity-Level Unlearning for Large Language Mode
        34049, -- 2407.02398 Consistency Flow Matching: Defining Straight Flows with Velocity Consi
        34573, -- 2407.09498 OT-VP: Optimal Transport-guided Visual Prompting for Test-Time Adaptat
        35043, -- 2407.15447 SIGMA:Sinkhorn-Guided Masked Video Modeling
        36042, -- 2408.11048 RP1M: A Large-Scale Motion Dataset for Piano Playing with Bi-Manual De
        36118, -- 2408.12109 RoVRM: A Robust Visual Reward Model Optimized via Auxiliary Textual Pr
        36365, -- 2408.16325 P2P-Bridge: Diffusion Bridges for 3D Point Cloud Denoising
        36737, -- 2409.06615 One-Shot Imitation under Mismatched Execution
        37586, -- 2410.00418 Posterior-Mean Rectified Flow: Towards Minimum MSE Photo-Realistic Ima
        39388, -- 2410.23054 Controlling Language and Diffusion Models by Transporting Activations
        40128, -- 2411.11875 Exploring Optimal Transport-Based Multi-Grained Alignments for Text-Mo
        40756, -- 2412.00420 TAROT: Targeted Data Selection via Optimal Transport
        41924, -- 2412.15195 Preventing Local Pitfalls in Vector Quantization via Optimal Transport
        42154, -- 2412.18221 GIMS: Image Matching System Based on Adaptive Graph Construction and G
        43569, -- 2502.01441 Improved Training Technique for Latent Consistency Models
        43610, -- 2502.01889 Displacement-Sparse Neural Optimal Transport
        44875, -- 2502.16806 CoT2Align: Cross-Chain of Thought Distillation via Optimal Transport A
        45042, -- 2502.18779 Towards Optimal Multi-draft Speculative Decoding
        45246, -- 2503.00266 Flow Matching for Medical Image Synthesis: Bridging the Gap Between Sp
        45378, -- 2503.01917 Steer LLM Latents for Hallucination Detection
        46082, -- 2503.10636 The Curse of Conditions: Analyzing and Improving Optimal Transport for
        46145, -- 2503.11439 COIN: Confidence Score-Guided Distillation for Annotation-Free Cell Se
        49059, -- 2505.13413 Joint Velocity-Growth Flow Matching for Single-Cell Dynamics Modeling
        49332, -- 2505.15808 Neural Conditional Transport Maps
        49584, -- 2505.18150 Generative Distribution Embeddings
        49622, -- 2505.18521 Improved Immiscible Diffusion: Accelerate Diffusion Training by Reduci
        49952, -- 2505.21494 Adversarial Attacks against Closed-Source MLLMs via Feature Optimal Al
        50692, -- 2506.05899 WhisQ: Cross-Modal Representation Learning for Text-to-Music MOS Predi
        51479, -- 2506.20741 OTSurv: A Novel Multiple Instance Learning Framework for Survival Pred
        51701, -- 2507.04517 DOTResize: Reducing LLM Width via Discrete Optimal Transport-based   N
        51839, -- 2507.08396 Subject-Consistent and Pose-Diverse Text-to-Image Generation
        52544, -- 2508.19527 MotionFlux: Efficient Text-Guided Motion Generation through Rectified
        53295, -- 2510.06030 Adaptive Pruning for Increased Robustness and Reduced Computational
        54165, -- 2511.07499 Toward the Frontiers of Reliable Diffusion Sampling via Adversarial Si
        54419, -- 2511.22475 Adversarial Flow Models
        55670, -- 2602.01624 PISCES: Annotation-free Text-to-Video Post-Training via Optimal Transp
        55893, -- 2601.23039 Avoiding Premature Collapse: Adaptive Annealing for Entropy-Regularize
        55957, -- 2602.07022 Condition Errors Refinement in Autoregressive Image Generation with Di
        56452, -- 2603.01400 Token Reduction via Local and Global Contexts Optimization for Efficie
        56610, -- 2603.07513 Bolbosh: Script-Aware Flow Matching for Kashmiri Text-to-Speech
        56781, -- 2603.15132 WiT: Waypoint Diffusion Transformers via Trajectory Conflict Navigatio
        56885, -- 2603.13395 COT-FM: Cluster-wise Optimal Transport Flow Matching
        56911, -- 2603.17512 Language on Demand, Knowledge at Core: Composing LLMs with Encoder-Dec
        57543, -- 2604.14265 Reinforcement Learning via Value Gradient Flow
        57545, -- 2211.16780 An Optimal Transport-driven Approach for Cultivating Latent Space in O
        58678, -- 2604.00593 A Geometric Theory of Cosmological Structure via Entropic Curvature in
        59891, -- 2603.04355 Efficient Refusal Ablation in LLM through Optimal Transport
        60201, -- 2602.23353 SOTAlign: Semi-Supervised Alignment of Unimodal Vision and Language Mo
        60234, -- 2602.22678 ViCLIP-OT: The First Foundation Vision-Language Model for Vietnamese I
        60399, -- 2602.20409 CLIPoint3D: Language-Grounded Few-Shot Unsupervised 3D Point Cloud Dom
        60422, -- 2602.19083 ChordEdit: One-Step Low-Energy Transport for Image Editing
        61169, -- 2602.05495 Transport and Merge: Cross-Architecture Merging for Large Language Mod
        61878, -- 2601.21126 AI-Augmented Density-Driven Optimal Control (D2OC) for Decentralized E
        62224, -- 2601.15380 You Need Better Attention Priors
        62392, -- 2602.11165 Assessing LLM Reliability on Temporally Recent Open-Domain Questions
        62411, -- 2601.11716 AllShowers: One model for all calorimeter showers
        62699, -- 2601.11618 Geometric Attention: A Regime-Explicit Operator Semantics for Transfor
        63003, -- 2601.02080 The Homogeneity Trap: Spectral Collapse in Doubly-Stochastic Deep Netw
        63115, -- 2601.00548 Optimal Transport-Based Decentralized Multi-Agent Distribution Matchin
        63544, -- 2512.17051 SFBD-OMNI: Bridge models for lossy measurement restoration with limite
        64028, -- 2512.06802 VDOT: Efficient Unified Video Creation via Optimal Transport Distillat
        64428, -- 2511.22425 Wukong's 72 Transformations: High-fidelity Textured 3D Morphing via Fl
        64539, -- 2511.20307 TReFT: Taming Rectified Flow Models For One-Step Image Translation
        64877, -- 2511.14477 2D Gaussians Spatial Transport for Point-supervised Density Regression
        64896, -- 2511.14109 A^2GC: Asymmetric Aggregation with Geometric Constraints for Locally A
        64950, -- 2511.12756 Density-Driven Optimal Control for Non-Uniform Area Coverage in Decent
        64960, -- 2511.12492 Density-Driven Multi-Agent Coordination for Efficient Farm Coverage an
        65131, -- 2511.08972 Selective Sinkhorn Routing for Improved Sparse Mixture of Experts
        65478, -- 2511.01540 Distributionally robust expected shortfall for convex risks
        65884, -- 2510.22033 Linearized Optimal Transport for Analysis of High-Dimensional Point-Cl
        65923, -- 2510.21250 Improved Training Technique for Shortcut Models
        66065, -- 2510.19257 FnRGNN: Distribution-aware Fairness in Graph Neural Network
        66562, -- 2510.11752 Fast and Interpretable Protein Substructure Alignment via Optimal   Tr
        67598, -- 2509.23348 Entering the Era of Discrete Diffusion Models: A Benchmark for Schrödi
        68706, -- 2509.04844 REMOTE: A Unified Multimodal Relation Extraction Framework with   Mult
        69504, -- 2508.13376 Whispering Context: Distilling Syntax and Semantics for Long Speech Tr
        70271, -- 2508.02363 Transport-Guided Rectified Flow Inversion: Improved Image Editing Usin
        70424, -- 2508.00451 WeightFlow: Learning Stochastic Dynamics via Evolving Weight of Neural
        70559, -- 2507.22270 Weighted Conditional Flow Matching
        70641, -- 2507.20708 Exposing the Illusion of Fairness: Auditing Vulnerabilities to Distrib
        70876, -- 2507.16569 Families of Optimal Transport Kernels for Cell Complexes
        71253, -- 2507.08136 RegGS: Unposed Sparse Views Gaussian Splatting with 3DGS Registration
        71446, -- 2507.03434 Unlearning the Noisy Correspondence Makes CLIP More Robust
        72279, -- 2506.04015 GORACS: Group-level Optimal Transport-guided Coreset Selection for   L
        72592, -- 2505.22109 The quest for the GRAph Level autoEncoder (GRALE)
        73139, -- 2505.05034 Dequantified Diffusion-Schr{ö}dinger Bridge for Density Ratio   Estima
        73670, -- 2504.05022 Solving the fully nonlinear Monge-Ampère equation using the Legendre-K
        73891, -- 2503.19062 Color Transfer with Modulated Flows
        74167, -- 2503.08155 Domain Adaptation and Entanglement: an Optimal Transport Perspective
        74849, -- 2502.05242 Beyond External Monitors: Enhancing Transparency of Large Language   M
        74941, -- 2502.01588 A Differentiable Alignment Framework for Sequence-to-Sequence Modeling
        75026, -- 2501.18943 HeLiOS: Heterogeneous LiDAR Place Recognition via Overlap-based Learni
        75636, -- 2412.00833 AlignMamba: Enhancing Multimodal Mamba with Local and Global Cross-mod
        75851, -- 2407.18163 Statistical optimal transport
        76507, -- 2409.07462 S-MolSearch: 3D Semi-supervised Contrastive Learning for Bioactive Mol
        77164, -- 2405.18525 REPARO: Compositional 3D Assets Generation with Differentiable 3D Layo
        77443, -- 2404.08977 RoNID: New Intent Discovery with Generated-Reliable Labels and   Clust
        77901, -- 2401.14069 Neural Sinkhorn Gradient Flow
        78407, -- 2310.05461 Sparsistency for Inverse Optimal Transport
        79410, -- 2301.11496 On Excess Mass Behavior in Gaussian Mixture Models with   Orlicz-Wasse
        80127, -- 2203.10335 TO-FLOW: Efficient Continuous Normalizing Flows with Temporal   Optimi
        80626, -- 2107.01872 Parts2Words: Learning Joint Embedding of Point Clouds and Texts by Bid
        81124, -- 1902.10288 Clustering, factor discovery and optimal transport
        81233, -- 1910.14090 Conditional Density Estimation, Latent Variable Discovery and Optimal
        82096, -- 1802.07191 Neural Architecture Search with Bayesian Optimisation and Optimal Tran
        83542, -- 2605.20158 Rethinking Visual Attribution for Chest X-ray Reasoning in Large Visio
        83759, -- 2605.25294 Geometry-Aware Image Flow Matching
        84043, -- 2506.13723 SOTA: Self-adaptive Optimal Transport for Zero-Shot Classification wit
        84077, -- 2508.05135 HFedATM: Hierarchical Federated Domain Generalization via Optimal Tran
        84212, -- 2511.18359 TRANSPORTER: Transferring Visual Semantics from VLM Manifolds
        84666, -- 2603.00493 COG: Confidence-aware Optimal Geometric Correspondence for Unsupervise
        84855, -- 2603.11492 SPEGC: Continual Test-Time Adaptation via Semantic-Prompt-Enhanced Gra
        84860, -- 2603.11617 Noise-Aware Few-Shot Learning through Bi-directional Multi-View Prompt
        84861, -- 2603.11618 Shape-of-You: Fused Gromov-Wasserstein Optimal Transport for Semantic
        84881, -- 2603.12766 Catalyst4D: High-Fidelity 3D-to-4D Scene Editing via Dynamic Propagati
        85298, -- 2604.06631 Submodel Extraction for Efficient and Personalized Federated Learning
        85399, -- 2604.16481 Erasing Thousands of Concepts: Towards Scalable and Practical Concept
        85435, -- 2604.20358 ConeSep: Cone-based Robust Noise-Unlearning Compositional Network for
        85502, -- 2605.03877 DMGD: Train-Free Dataset Distillation with Semantic-Distribution Match
        86004, -- 2509.19626 EgoBridge: Domain Adaptation for Generalizable Imitation from Egocentr
        86190, -- 2503.10576 Sample and Map from a Single Convex Potential: Generation using Conjug
        86214, -- 2509.17276 Probabilistic Token Alignment for Large Language Model Fusion
        86253, -- 2505.17644 Towards Prospective Medical Image Reconstruction via Knowledge-Informe
        86354, -- 2507.10425 Non-exchangeable Conformal Prediction with Optimal Transport: Tackling
        86447, -- 2509.13866 Masked Diffusion Models as Energy Minimization
        86484, -- 2504.10612 Energy Matching: Unifying Flow Matching and Energy-Based Models for Ge
        86531, -- 2505.23949 TSENOR: Highly-Efficient Algorithm for Finding Transposable N:M Sparse
        86543, -- 2412.09059 Go With the Flow: Fast Diffusion for Gaussian Mixture Models
        86563, -- 2504.03188 Pairwise Optimal Transports for Training All-to-All Flow-Based Conditi
        86632, -- 2509.14722 Towards Pre-trained Graph Condensation via Optimal Transport
        86713, -- 2505.11823 Variational Regularized Unbalanced Optimal Transport: Single Network,
        86761, -- 2505.19712 On the Relation between Rectified Flows and Optimal Transport
        86917, -- 2510.05527 Transfer Learning on Edge Connecting Probability Estimation Under Grap
        86989, -- 2508.15593 Inductive Domain Transfer In Misspecified Simulation-Based Inference
        87101, -- 2506.09534 Gaussian Herding across Pens: An Optimal Transport Perspective on Glob
        87156, -- 2505.17293 Model-Free Graph Data Selection under Distribution Shift
        87209, -- 2510.08294 Counterfactual Identifiability via Dynamic Optimal Transport
        87331, -- 2505.22049 Differentiable Generalized Sliced Wasserstein Plans
        87426, -- 2506.12025 Unsupervised Learning for Optimal Transport plan prediction between un
        87441, -- 2505.23062 Composite Flow Matching for Reinforcement Learning with Shifted-Dynami
        87566, -- 2503.10663 Optimal Transport for Brain-Image Alignment: Unveiling Redundancy and
        87780, -- 2507.03539 CLOT: Closed Loop Optimal Transport for Unsupervised Action Segmentati
        87794, -- 2503.16832 Joint Self-Supervised Video Alignment and Action Segmentation
        87808, -- 2507.00648 UMDATrack: Unified Multi-Domain Adaptive Tracking Under Adverse Weathe
        87833, -- 2507.03657 Dynamic Multimodal Prototype Learning in Vision-Language Models
        87857, -- 2507.02581 Structure-aware Semantic Discrepancy and Consistency for 3D Medical Im
        88075, -- 2406.08933 LaCoOT: Layer Collapse through Optimal Transport
        88156, -- 2507.07568 Learnable Retrieval Enhanced Visual-Text Alignment and Fusion for Radi
        88163, -- 2506.08694 MoSiC: Optimal-Transport Motion Trajectory for Dense Self-Supervised L
        88197, -- 2507.08178 Cracking Instance Jigsaw Puzzles: An Alternative to Multiple Instance
        88351, -- 2507.09524 When Schrodinger Bridge Meets Real-World Image Dehazing with Unpaired
        88392, -- 2503.08829 Seal Your Backdoor with Variational Defense
        88479, -- 2503.14975 Taming Flow Matching with Unbalanced Optimal Transport into Fast Pansh
        88505, -- 2506.24063 Continual Adaptation: Environment-Conditional Parameter Generation for
        88522, -- 2503.03025 Hierarchical Refinement: Optimal Transport to Infinity and Beyond
        88534, -- 2405.08719 Addressing Misspecification in Simulation-based Inference through Data
        88560, -- 2506.07534 Flowing Datasets with Wasserstein over Wasserstein Gradient Flows
        88606, -- 2502.12631 Score-Based Diffusion Policy Compatible with Reinforcement Learning vi
        88749, -- 2212.00133 Universal Neural Optimal Transport
        88762, -- 2411.00698 Wasserstein Flow Matching: Generative Modeling Over Families of Distri
        88830, -- 2502.07962 ESPFormer: Doubly-Stochastic Attention with Expected Sliced Transport
        88903, -- 2506.02712 Theoretical Performance Guarantees for Partial Domain Adaptation via P
        88935, -- 2406.13725 Tree-Sliced Wasserstein Distance: A Geometric Perspective
        88941, -- 2505.00968 Tree-Sliced Wasserstein Distance with Nonlinear Projection
        88999, -- 2507.00894 An in depth look at the Procrustes-Wasserstein distance: properties an
        89039, -- 2505.24642 WILTing Trees: Interpreting the Distance Between MPNN Embeddings
        89075, -- 2502.01168 On the Private Estimation of Smooth Transport Maps
        89082, -- 2410.08751 Zero-Shot Offline Imitation Learning via Optimal Transport
        89089, -- 2501.18991 Optimal transport-based conformal prediction
        89124, -- 2505.23264 Efficiently Access Diffusion Fisher: Within the Outer Product Span Spa
        89171, -- 2502.04583 Overcoming Spurious Solutions in Semi-Dual Neural Optimal Transport: A
        89181, -- 2506.02619 HGOT: Self-supervised Heterogeneous Graph Neural Network with Optimal
        89415, -- 2501.18901 Lightspeed Geometric Dataset Distance via Sliced Optimal Transport
        89437, -- 2506.12408 PROTOCOL: Partial Optimal Transport-enhanced Contrastive Learning for
        89570, -- 2502.01164 Tightening Causal Bounds via Covariate-Aware Optimal Transport
        89577, -- 2405.15441 Statistical and Computational Guarantees of Kernel Max-Sliced Wasserst
        89584, -- 2505.22364 Computing Optimal Transport Maps and Wasserstein Barycenters Using Con
        89781, -- 2504.20858 Chaos Meets Attention: Transformers for Large-Scale Dynamical Predicti
        89810, -- 2501.14635 Optimal Transport Barycenter via Nonconvex-Concave Minimax Optimizatio
        89898, -- 2506.16218 FOCoOp: Enhancing Out-of-Distribution Robustness in Federated Prompt L
        89914, -- 2409.20547 Annealing Flow Generative Models Towards Sampling High-Dimensional and
        89975, -- 2309.10737 Monte-Carlo Tree Search with Uncertainty Propagation via Optimal Trans
        90145, -- 2412.01256 NLPrompt: Noise-Label Prompt Learning for Vision-Language Models
        90339, -- 2503.24282 Style Quantization for Data-Efficient GAN Training
        90396, -- 2503.17080 Seeing What Matters: Empowering CLIP with Patch Generation-to-Selectio
        90721, -- 2503.22984 Optimal Transport-Guided Source-Free Adaptation for Face Anti-Spoofing
        90745, -- 2503.00063 NoPain: No-box Point Cloud Attack via Optimal Transport Singular Bound
        90797, -- 2503.15337 Recover and Match: Open-Vocabulary Multi-Label Recognition through Kno
        90835, -- 2503.22168 Spatial Transport Optimization by Repositioning Attention Map for Trai
        90836, -- 2310.11439 From Alexnet to Transformers: Measuring the Non-linearity of Deep Neur
        90861, -- 2505.07209 Discovering Fine-Grained Visual-Concept Relations by Disentangled Opti
        90986, -- 2503.21099 Learning Class Prototypes for Unified Sparse-Supervised 3D Object Dete
        91073, -- 2412.14421 Comparing noisy neural population dynamics using optimal transport dis
        91074, -- 2410.00844 Learning stochastic dynamics from snapshots through regularized unbala
        91135, -- 2412.12540 Stiefel Flow Matching for Moment-Constrained Structure Elucidation
        91170, -- 2502.14628 PEARL: Towards Permutation-Resilient LLMs
        91207, -- 2403.04099 Many-Objective Multi-Solution Transport
        91312, -- 2411.07432 Fast unsupervised ground metric learning with tree-Wasserstein distanc
        91315, -- 2410.03974 Robust Barycenter Estimation using Semi-Unbalanced Neural Optimal Tran
        91358, -- 2410.16669 Linear Partial Gromov-Wasserstein Embedding
        91408, -- 2407.07829 Disentangled Representation Learning with the Gromov-Monge Gap
        91415, -- 2405.15252 Accelerating 3D Molecule Generation via Jointly Geometric Optimal Tran
        91503, -- 2410.12176 Expected Sliced Transport Plans
        91537, -- 2410.03024 Flow Matching with Gaussian Process Priors for Probabilistic Time Seri
        91585, -- 2503.11249 Spherical Tree-Sliced Wasserstein Distance
        91589, -- 2503.11050 Distance-Based Tree-Sliced Wasserstein Distance
        91603, -- 2410.03052 Learning Structured Representations by Embedding Class Hierarchy with
        91676, -- 2406.01130 SAVA: Scalable Learning-Agnostic Data Valuation
        91736, -- 2502.09122 Improving Deep Regression with Tightness
        91784, -- 2410.03783 Improving Neural Optimal Transport via Displacement Interpolation
        91857, -- 2406.07475 Partially Observed Trajectory Inference using Optimal Transport and a
        91901, -- 2411.05464 Generalization, Expressivity, and Universality of Graph Neural Network
        91971, -- 2405.16541 Variance-Reducing Couplings for Random Features
        92170, -- 2502.12456 Not-So-Optimal Transport Flows for 3D Point Cloud Generation
        92432, -- 2411.06055 Linear Spherical Sliced Optimal Transport: A Fast Metric for Comparing
        92720, -- 2602.19331 Partial Soft-Matching Distance For Neural Representational Comparison
        92845, -- 2510.01706 Representational Alignment Across Model Layers and Brain Regions with
        92861, -- 2604.20627 Occupancy Reward Shaping: Improving Credit Assignment for Offline Goal
        92971, -- 2507.17513 HOTA: Hamiltonian framework for Optimal Transport Advection
        93026, -- 2510.18982 Test-time Verification via Optimal Transport: Coverage, ROC, & Sub-opt
        93286, -- 2603.01771 Hyperparameter Trajectory Inference with Conditional Lagrangian Optima
        93345, -- 2509.24920 A Spectral-Grassmann Wasserstein metric for operator representations o
        93385, -- 2512.10683 Optimal transport unlocks end-to-end learning for single-molecule loca
        93633, -- 2506.01158 Efficient Regression-based Training of Normalizing Flows for Boltzmann
        93634, -- 2511.15898 Global Resolution: Optimal Multi-Draft Speculative Sampling via Convex
        93746, -- 2512.06652 Adaptive Test-Time Training for Predicting Need for Invasive Mechanica
        93776, -- 2510.01153 Neural Hamilton--Jacobi Characteristic Flows for Optimal Transport
        93806, -- 2505.13660 Sobolev Gradient Ascent for Optimal Transport: Barycenter Optimization
        93809, -- 2512.09365 KGOT: Unified Knowledge Graph and Optimal Transport Pseudo-Labeling fo
        93877, -- 2510.15038 AlignFlow: Improving Flow-based Generative Models with Semi-Discrete O
        93909, -- 2410.02601 Diffusion & Adversarial Schrödinger Bridges via Iterative Proportional
        94011, -- 2506.14020 Bures-Wasserstein Flow Matching for Graph Generation
        94040, -- 2509.25519 Flow Matching with Semidiscrete Couplings
        94224, -- 2509.25444 Neural Optimal Transport Meets Multivariate Conformal Prediction
        94260, -- 2509.22138 Slicing Wasserstein over Wasserstein via Functional Optimal Transport
        94280, -- 2510.02903 Learning Explicit Single-Cell Dynamics Using ODE Representations
        94313, -- 2602.24027 GuardAlign: Test-time Safety Alignment in Multimodal Large Language Mo
        94575, -- 2502.01310 A Statistical Learning Perspective on Semi-dual Adversarial Neural Opt
        94664, -- 2603.28603 ELViS: Efficient Visual Similarity from Local Descriptors that General
        94707, -- 2602.22785 SceneTransporter: Optimal Transport-Guided Compositional Latent Diffus
        94754, -- 2601.21320 Optimal Transport-Induced Samples against Out-of-Distribution Overconf
        94885, -- 2410.05419 Joint Distribution–Informed Shapley Values for Sparse Counterfactual E
        94887, -- 2601.06810 WFR-FM: Simulation-Free Dynamic Unbalanced Optimal Transport
        94967, -- 2509.17405 Efficient Sliced Wasserstein Distance Computation via Adaptive Bayesia
        94972, -- 2503.11892 DecAlign: Hierarchical Cross-Modal Alignment for Decoupled Multimodal
        95054, -- 2502.04575 Complexity Analysis of Normalizing Constant Estimation: from Jarzynski
        95315, -- 2508.01622 VFP: Variational Flow-Matching Policy for Multi-Modal Robot Manipulati
        96053, -- external CLOT: Multi-Robot Motion Planning Via Collaborative Optimal Transport
        96836, -- 2506.15175 SHeRLoc: Synchronized Heterogeneous Radar Place Recognition for Cross-
        98000, -- external VDOT: Efficient Unified Video Creation via Optimal Transport Distillat
        98091, -- external COT-FM: Cluster-wise Optimal Transport Flow Matching (AutoSOTA)
        99128, -- 2605.06083 Revisiting Uncertainty: On Evidential Learning for Partially Relevant
        99152, -- 2605.00392 RTPrune: Reading-Twice Inspired Token Pruning for Efficient DeepSeek-O
        99284, -- 2505.06835 Streaming Sliced Optimal Transport
        99372, -- 2605.28809 AREA: Attribute Extraction and Aggregation for CLIP-Based Class-Increm
        99395, -- 2602.03067 FlashSinkhorn: IO-Aware Entropic Optimal Transport on GPU
        99399, -- 2606.00847 Partial Identification under High-Dimensional Potential Outcomes and C
        99462, -- 2605.08851 Geometrically Constrained Stenosis Editing in Coronary Angiography via
        99550, -- 2605.00545 Beyond Continuity: Simulation-free Reconstruction of Discrete Branchin
        99567, -- 2605.13155 Pareto-Guided Optimal Transport for Multi-Reward Alignment
        99573, -- 2606.05883 Geometry-Aware Dataset Condensation for Diffusion Model Training
        99584, -- 2502.07397 Linear Bandits beyond Inner Product Spaces, the case of Bandit Optimal
        99618, -- 2601.20606 WFR-MFM: One-Step Inference for Dynamic Unbalanced Optimal Transport
        99673, -- 2605.21094 UOTIP: Unbalanced Optimal Transport Map for Unpaired Inverse Problems
        99756, -- 2605.26894 SIMPC: Learning Self-Induced Mirror-Point Consistency for Unsupervised
        99771, -- 2601.07144 Optimal Transport under Group Fairness Constraints
        99846, -- 2602.01179 Rethinking the Flow-based Gradual Domain Adaptation: A Semi-Dual Optim
        99887, -- 2602.08868 AnomSeer: Reinforcing Multimodal LLMs to Reason for Time-Series Anomal
        99905, -- 2602.00318 BOCLOAK: Optimal Transport-Guided Adversarial Attacks on Graph Neural
        99914, -- 2606.18729 TimeLAVA: Learning-Agnostic Valuation for Time Series Data
        100085, -- 2605.24644 Quadratically Regularized Optimal Transport: Localization Bounds and A
        100122, -- 2606.03100 Zero-Shot 3D Question Answering via Hierarchical View-to-Token Transpo
        100388, -- 2602.06658 Gromov-Wasserstein at Scale, Beyond Squared Norms
        100413, -- 2512.08317 GeoDM: Geometry-aware Distribution Matching for Dataset Distillation
        100441, -- 2604.06210 Distributional Open-Ended Evaluation of LLM Cultural Value Alignment B
        100499, -- 2509.12689 Loss-Aware Distributionally Robust Optimization via Trainable Optimal
        100545, -- 2605.10917 Optimal and Scalable MAPF via Multi-Marginal Optimal Transport and Sch
        100675, -- 2509.24531 Diffusion Bridge or Flow Matching? A Unifying Framework and Comparativ
        100682, -- 2606.02047 Convex Distance Operator Transport: A Convex and Geometry-Preserving F
        100738, -- 2605.22350 Partial Fusion of Neural Networks: Efficient Tradeoffs Between Ensembl
        100751, -- 2509.23162 Dense associative memory for Gaussian distributions
        100795, -- 2603.02237 Concept Heterogeneity-aware Representation Steering
        100828, -- 2602.03566 Riemannian Neural Optimal Transport
        100836, -- 2411.00759 Minibatch Optimal Transport and Perplexity Bound Estimation in Discret
        100883, -- 2606.00651 MESA: Improving MoE Safety Alignment via Decentralized Expertise
        100926, -- 2605.20989 Modeling Temporal scRNA-seq Data with Latent Gaussian Process and Opti
        101042, -- 2510.01015 Quantifying the noise sensitivity of the Wasserstein metric for images
        101219, -- 2505.17370 Ellipsoidal Time Series Forecasting
        101235, -- 2605.24395 AvAtar: Learning to Align via Active Optimal Transport
        101303, -- 2511.19953 Supervise Less, See More: Training-free Nuclear Instance Segmentation
        101530, -- 2509.24894 Improved Stochastic Optimization of LogSumExp
        101654, -- 2410.02628 Inverse Entropic Optimal Transport Solves Semi-supervised Learning via
        101721, -- 2606.16856 Video-Based Optimal Transport for Feedback-Efficient Offline Preferenc
        101756, -- 2606.05327 Multimarginal flow matching with optimal transport potentials
        101793, -- 2406.14762 One-step Optimal Transport via Regularized Distribution Matching Disti
        101818, -- 2605.30635 CellBRIDGE: Learning Cellular Trajectories via Interaction-Aware Align
        101905, -- 2602.02241 Variational Entropic Optimal Transport
        101935, -- 2510.25956 Gradient Flow Sampler-based Distributionally Robust Optimization
        101971, -- 2601.20692 Optimal Transport Group Counterfactual Explanations
        102005, -- 2509.04477 Universal Representation of Generalized Convex Functions and their Gra
        102057, -- 2603.08824 SoftJAX & SoftTorch: Empowering Automatic Differentiation Libraries wi
        102241, -- 2603.03578 Transport Clustering: Solving Low-Rank Optimal Transport via Clusterin
        102260, -- 2606.16655 Distribution Alignment for One-Shot Federated Learning via Optimal Tra
        102262, -- 2605.08485 Sinkhorn Treatment Effects: A Causal Optimal Transport Measure
        102319, -- 2604.21097 Learning to Emulate Chaos: Adversarial Optimal Transport Regularizatio
        102357, -- 2606.01666 DOT-MoE: Differentiable Optimal Transport for MoEfication
        102390, -- 2605.08793 cuRegOT: A GPU-Accelerated Solver for Entropic-Regularized Optimal Tra
        102501, -- 2605.30625 Active Timepoint Selection for Learning Measure-Valued Trajectories
        102593, -- 2606.28393 Transition-Aware best-of-N sampling for Longitudinal Chest X-ray Repor
        103244, -- 2601.07200 Safeguarding LLM Fine-tuning via Push-Pull Distributional Alignment
        103914, -- 2405.19657 Uncertainty-guided Optimal Transport in Depth Supervised Sparse-View 3
        104413, -- 2607.17146 The Geometry of Semantic Space: A Continuous Geometric Framework for t
        104944, -- external Anatomy-Conserving Unpaired CBCT-to-CT Translation via Schrödinger Bri
        104998, -- external C²MAOT: Cross-modal Complementary Masked Autoencoder with Optimal Tran
        105433, -- external MoST-IG: Morphology-Guided Spatial Transcriptomics Integration via Vis
        105435, -- 2506.22900 MOTOR: Multimodal Optimal Transport via Grounded Retrieval in Medical
        105621, -- 2507.04999 Robust Incomplete-Modality Alignment for Ophthalmic Disease Grading an
        105623, -- 2502.20144 Robust sensitivity control in digital pathology via tile score distrib
        106324, -- 2604.26170 EvoSelect: Data-Efficient LLM Evolution for Targeted Task Adaptation
        106413, -- 2511.08901 Asymmetric Cross-Modal Knowledge Distillation: Bridging Modalities wit
        106422, -- 2512.07760 Modality-Aware Bias Mitigation and Invariance Learning for Unsupervise
        106537, -- 2508.00357 Sheaf Graph Neural Networks via PAC-Bayes Spectral Optimization
        106571, -- 2511.12545 Center-Outward q-Dominance: A Sample-Computable Proxy for Strong Stoch
        106704, -- 2511.16778 GCL-OT: Graph Contrastive Learning with Optimal Transport for Heteroph
        106857, -- 2511.13124 Departures: Distributional Transport for Single-Cell Perturbation Pred
        106883, -- 2511.07941 Libra-MIL: Multimodal Prototypes Stereoscopic Infused with Task-specif
        107310, -- 2511.17585 PaSE: Prototype-aligned Calibration and Shapley-based Equilibrium for
        107351, -- 2503.23002 ST-TPP: Learning Semi-Transductive Temporal Point Processes with Gromo
        107435, -- 2511.16140 Real-time 3D Object Detection with Inference-Aligned Learning
        107456, -- 2506.23205 BridgeShape: Latent Diffusion Schrödinger Bridge for 3D Shape Completi
        107592, -- 2511.11162 OT-ALD: Aligning Latent Distributions with Optimal Transport for Accel
        107640, -- 2511.12785 Lightweight Optimal-Transport Harmonization on Edge Devices
        107760, -- 2511.13786 CellStream: Dynamical Optimal Transport Informed Embeddings for Recons
        107938, -- 2511.09392 Potent but Stealthy: Rethink Profile Pollution Against Sequential Reco
        108215, -- 2508.02364 A Novel Sliced Fused Gromov-Wasserstein Distance
        108540, -- 2412.00563 Designing Optimal Mechanisms to Locate Facilities with Insufficient Ca
        108842, -- 2607.18184 anyakrakusuma: A Python Library for Entropic Schrödinger Bridges on Id
        109351, -- 2608.09613 Marrying Optimal Transport and ODEs for Unified Continuous-Time 4D Rec
        109721, -- 2608.24738 TorchMorph: CUDA-accelerated Morphological Transforms
        110095, -- 2510.10963 APLOT: Robust Reward Modeling via Adaptive Preference Learning with Op
        110165, -- external EMO: Embedding Model Distillation via Intra-Model Relation and Optimal
        110239, -- 2509.18717 Pre-training CLIP against Data Poisoning with Optimal Transport-based
        110342, -- external Calibrating Pseudo-Labeling with Class Distribution for Semi-supervise
        110981, -- 2506.13579 Flexible-length Text Infilling for Discrete Diffusion Models
        111371, -- 2506.09709 Training-Free Voice Conversion with Factorized Optimal Transport
        111716, -- 2505.13079 Cross-modal Knowledge Transfer Learning as Graph Matching Based on Opt
        111911, -- 2506.01138 PARROT: Synergizing Mamba and Attention-based SSL Pre-Trained Models v
        112211, -- external BSP-OT: Sparse transport plans between discrete measures in loglinear
        112314, -- external Efficient and Scalable Spatial Regularization of Optimal Transport
        112383, -- external Diffusion Bridges for 3D Point Cloud Denoising
        112400, -- 2409.01726 Mahalanobis Distance-based Multi-view Optimal Transport for Multi-view
        112457, -- 2408.01946 Masked Angle-Aware Autoencoder for Remote Sensing Images
        112806, -- external Click Prompt Learning with Optimal Transport for Interactive Segmentat
        112835, -- external Visual Prompting via Partial Optimal Transport
        112906, -- external Optimal Transport of Diverse Unsupervised Tasks for Robust Learning fr
        113302, -- 2407.01851 Meerkat: Audio-Visual Large Language Model for Grounding in Space and
        113504, -- external LLMCO4MR: LLMs-aided Neural Combinatorial Optimization for Ancient Man
        114920, -- 2409.04975 Fair and Accurate Skin Disease Image Classification by Alignment with
        115146, -- 2406.17225 Multimodal Cross-Task Interaction for Survival Analysis in Whole Slide
        115344, -- 2303.05780 TAKT: Target-Aware Knowledge Transfer for Whole Slide Image Classifica
        115409, -- external Vertex Proportion Loss for Multi-Class Cell Detection from Label Propo
        115454, -- 2403.13261 Self-Supervised Class-Agnostic Motion Prediction with Spatial and Temp
        115530, -- external FCS: Feature Calibration and Separation for Non-Exemplar Class Increme
        115538, -- external Mind Artist: Creating Artistic Snapshots with Human Thought
        115827, -- 2404.01518 Temporally Consistent Unbalanced Optimal Transport for Unsupervised Ac
        115973, -- 2309.13855 Adaptive Softassign via Hadamard-Equipped Sinkhorn
        116197, -- 2403.19949 FairCLIP: Harnessing Fairness in Vision-Language Learning
        116479, -- 2403.05105 Learning to Rematch Mismatched Pairs for Robust Cross-Modal Retrieval
        116939, -- 2403.00041 Global and Local Prompts Cooperation via Optimal Transport for Federat
        116944, -- external Distilling CLIP with Dual Guidance for Learning Discriminative Human B
        117397, -- 2608.01793 ReFP-AD: Rectified Flow Preconditioning for Energy-Based Anomaly Detec
        117576, -- 2606.26754 Capacity-Controlled Multi-View Stylization of 3D Gaussian Splatting
        118157, -- 2604.06614 Holistic Optimal Label Selection for Robust Prompt Learning under Part
        118443, -- 2606.31026 OTCache: Optimal Transport for Geometry-Aware Caching in Diffusion Mod
        118623, -- 2606.31683 Histogram-constrained Image Generation
        118627, -- 2606.31225 A First Exploration of Neuromorphic OT-CFM for Multi-Speaker VSR
        118642, -- 2608.13226 CoverPrune: Coverage-Driven Token Pruning for 3D VLMs via Optimal Tran
        118711, -- 2606.26891 Bridging Vision and Language Concepts through Optimal Transport Semant
        118725, -- external Unbalanced Optimal Transport for Efficient Visual Document Retrieval
        118742, -- 2512.05635 Experts-Guided Unbalanced Optimal Transport for ISP Learning from Unpa
        118747, -- external Enhancing Interpretability in CLIP with Optimal Transport-based Submod
        118758, -- 2606.24786 Counting Trees from Satellite Imagery with Noisy Supervision
        118763, -- 2511.18089 Together, Then Apart: Balancing Alignment and Distinctiveness for Mult
        118847, -- 2606.31609 Learning Structurally Consistent Representations for Multi-View Radar
        118972, -- 2607.05263 Learning Probabilistic Embeddings for Unsupervised Action Segmentation
        119904, -- external Boosting Point-Supervised Temporal Action Localization through Integra
        119987, -- 2510.08791 Alignment, Mining and Fusion: Representation Alignment with Hard Negat
        120027, -- 2505.24693 Conformal Prediction for Zero-Shot Models
        120076, -- external OPTICAL: Leveraging Optimal Transport for Contribution Allocation in D
        120087, -- external Gromov-Wasserstein Problem with Cyclic Symmetry
        120242, -- external Detecting Open World Objects via Partial Attribute Assignment
        120342, -- external Camouflage Anything: Learning to Hide using Controlled Out-painting an
        120350, -- external Distinguish Then Exploit: Source-free Open Set Domain Adaptation via W
        120363, -- 2506.11493 Preserving Clusters in Prompt Learning for Unsupervised Domain Adaptat
        120382, -- external POT: Prototypical Optimal Transport for Weakly Supervised Semantic Seg
        120443, -- external Enhanced then Progressive Fusion with View Graph for Multi-View Cluste
        120759, -- 2605.28347 FedMPT: Federated Multi-Label Prompt Tuning of Vision-Language Models
        120807, -- external Imbalanced View Contribution Evaluation and Refinement for Deep Incomp
        120879, -- external Frequency-Aware Affinity for Weakly Supervised Semantic Segmentation
        120929, -- external BiOTPrompt: Bidirectional Optimal Transport Guided Prompting for Disea
        120942, -- external Towards Uncertainty-aware Unsupervised Domain Adaptation for Videos an
        120975, -- 2507.06603 Progressive Cross-Modal Causal Intervention for Long-Term Action Recog
        121024, -- external Bulk RNA-seq Guided Multi-modal Detection of Anomalous Regions in Huma
        121255, -- external Beyond the Static World: Continual Category Discovery under Visual Dri
        121295, -- external FLOW: Optimal Transport-Driven Feature Warping for Generalized Remote
        121377, -- external Vision-Language Model Guided Source-Free Domain Adaptation via Optimal
        121546, -- 2506.21398 FastRef: Fast Prototype Refinement for Few-shot Industrial Anomaly Det
        121563, -- 2605.29602 CogniVerse: Revolutionizing Multi-Modal Retrieval-Augmented Generation
        121597, -- external Annotation-Efficient Coreset Selection for Context-dependent Segmentat
        121646, -- external Bypassing the Transport Plan: Dynamic Reweighting for Out-of-Distribut
        122370, -- 2609.34899 ColNanoVDR: Document-Free Query Distillation for Multi-Vector Visual D
        122549, -- 2609.30840 Aligning One-Step Generative Models with Reward-Weighted Transport Dis
        122622, -- 2609.36602 OTRetarget: Joint Robot and Object Motion Retargeting via Optimal Tran
        123159, -- 2605.06797 MIND: Monge Inception Distance for Generative Models Evaluation
        123280, -- 2610.13989 PsyBer-Agent: A Psychology-Driven User Agent for Recommender Systems
        123476, -- 2610.18838 Scaling Online Optimal Transport Minibatches for Flow Matching
        123910, -- 2610.28074 Slot-JEPA: Object-Structured Prediction Interfaces for Latent World Mo
        124126, -- 2605.08705 Minimax Optimal Estimation of Transport-Growth Pairs in Unbalanced Opt
        124216, -- external Exact Recovery of Lipschitz Orthogonal Coordinate Transformations via
        124376, -- 2606.07239 Generative Molecular Morphing for Flexible-Size Design via Unbalanced
        124455, -- external Learning Optimal Transport Plans Via Autoregressive Token Regression
        124620, -- external CrossWeave: Emergent Cross-Modal Scene and Instance Retrieval from Spa
        124653, -- external Time-Frequency Decoupled Cross-Scale Partial Optimal Transport for Tim
        124681, -- 2605.04175 A Provably Convergent and Practical Algorithm for Gromov–Wasserstein O
        124691, -- 2605.18587 PACE: Geometry-Aware Bridge Transport for Single-Cell Trajectory Infer
        124757, -- external Topology-Aware Optimal Transport for Source-Free Test-Time Adaptation
        124779, -- external Values Are Not Single Labels: Distributional Value Profiling Across Gr
        124856, -- 2604.03566 Fréchet Regression on the Bures-Wasserstein Manifold
        124913, -- external Graph Learning from Label Proportions using Topology-Aware Pseudo Labe
        124960, -- 2603.07156 Inexact Bregman Sparse Newton Method for Efficient Optimal Transport
        125009, -- 2607.16987 Twisted Schrödinger Bridge Matching
        125099, -- 2610.04601 WASP: Weakly Aligned Spatiotemporal Pairs for Fetal Brain MRI-Ultrasou
        125113, -- 2608.18875 Computing All Optimal Partial $p$-Wasserstein Matchings on the Line
        125120, -- 2609.27033 WTF?! Simulation-Free Reinforcement Learning with Wasserstein-Tilted F
        125166, -- 2609.04710 Simulation-free Unbalanced Dynamic Optimal Transport with General Grow
        125239, -- external Local Manifold Identification with Latent Linear Models and OT Flows
        125245, -- 2610.01028 Optimal Transport Reweighting for Robust Learning under Spurious Corre
        125255, -- 2605.11270 A Unified Approach for Computing Wasserstein Barycenters of Discrete a
        125267, -- 2605.16529 Multiscale Supervised Unbalanced Optimal Transport Flow Matching
        125359, -- external OTEdit: Entropic Transport Corrected Trajectory for Inversion-Free Flo
        125522, -- external Efficient One-to-many Domain Translation via Diffusive Entropic Optima
        125526, -- 2605.27619 Supervised Distributional Reduction via Optimal Transport and Dependen
        125767, -- 2303.05978 Uncovering Challenges of Solving the Continuous Gromov-Wasserstein Pro
        125815, -- external Identifiable Feedback-Controlled Latent Flow for Unpaired Single-cell
        125816, -- 2605.20030 Take It or Leave It: Intent-Controlled Partial Optimal Transport
        125825, -- 2609.25659 When Riemann flows with Wasserstein: Generative Modeling of Probabilit
        125948, -- 2605.28233 Geometry of Relaxed Fair Regression: A Unified Framework for Aware and
        125963, -- external GeoPMR: Preserving Relational and Hierarchical Geometry in Multimodal
        126084, -- external A Grid Efficient Transport Optimization Model for the Wasserstein Bary
        126190, -- external Statistical Inference in Causal Partial Identification under Smooth De
        126204, -- external Test-Time Adaptation via Self-Reinforced Optimal Transport for Zero-Sh
        126217, -- 2605.04543 UniVer: A Unified Perspective for Multi-step and Multi-draft Speculati
        126259, -- external Causal heteroscedastic structure learning from incomplete temporal dat
        126288, -- external Concept-Aware Wasserstein Routing with Vision-Language Guidance for Fe
        126305, -- external Identifiable alignment of unpaired representations
        126353, -- external Reinforcement Learning for View-Adaptive Distillation in 3D Gaussian C
        126549, -- external Contact Geometry for Generative Models: An Unbalanced Optimal Transpor
        126801, -- external Inference-Time Self-Aligned Drifting for Few-Step Flow Matching
        126898, -- 2605.12951 Coreset-Induced Conditional Velocity Flow Matching
        126991, -- external New Coresets for Fair Clustering
        127000, -- 2609.39757 Revisiting On-policy Adversarial Black-Box Distillation: Calibrating G
        127339, -- 2609.38049 Improving Function Space Flow Matching with Kernel Optimal Transport
        127386, -- 2610.00785 VTV-FM: Flow Matching through Variational Terminal-Velocity Closure
        127408, -- 2511.11359 Log-Averaged Mirror Prox for Fast, Large-Scale Optimal Transport in Li
        127425, -- external OT-Robust3DVLA: A Wasserstein Barycenter is the Right Inductive Bias f
        127546, -- 2602.07235 ArcMark: Distortion-Free Multi-Byte LLM Watermark via Optimal Transpor
        127683, -- 2609.31470 Beyond Empirical Support: Structured Outlier Generation via Sinkhorn O
        127715, -- external Neural Optimal Transport in Hilbert Spaces
        128008, -- 2605.07513 Tessellations of Semi-Discrete Flow Matching
        128127, -- 2602.04335 Geometry-Aware Optimal Transport: Fast Intrinsic Dimension and Wassers
        128195, -- external Orlicz–Sobolev with Musielak: An Efficient Regularization Approach for
        128211, -- 2610.10087 Multi-Agent Coordination via Support-Preserving Distillation
        128293, -- 2511.19741 Efficient Transferable Optimal Transport via Min-Sliced Transport Plan
        128325, -- external Variational Wasserstein Model on Riemannian Manifolds for Image Segmen
        128376, -- 2609.36264 OTROPE: Optimal Transport-based Robust Off-policy Evaluation for Large
        128399, -- external Beyond Linear Decoders: Dynamic Expert-Coupled Optimal Decoding for Ti
        128564, -- external OTformer: Non-Stationarity-Aware Adaptive Optimal Transport Attention
        128685, -- 2605.19944 A Measure-Theoretic Analysis of Reasoning: Structural Generalization a
        128692, -- 2607.10517 Conditional Optimal Bridge for Riemannian Activation Steering
        128754, -- 2604.26942 Hyper Input Convex Neural Networks for Shape Constrained Learning and
        128787, -- external Minimax Optimization without Spurious Solutions in Optimal Transport L
        128797, -- external Mitigating Compounding Errors in Online Reinforcement Learning via Opt
        128842, -- 2605.09782 Near-Linear Time Generalized Sinkhorn Algorithms for Bounded Genus Gra
        128917, -- 2607.04738 Wasserstein residuals: Learning Gradient Flows from Population Dynamic
        129072, -- external Reliable Clustering and Quantization via Distortion-Constrained Optima
        129166, -- 2602.23566 Flowette: Flow Matching with Graphette Priors for Graph Generation
        129237, -- external CMI-Trans: Cross Modal Inconsistency-aware Transport for HSI-LiDAR Cla
        129465, -- 2604.15114 Amortized Optimal Transport from Sliced Potentials
        129587, -- external A Principled Optimal Transport Framework for Frame Selection in Long V
        129588, -- 2510.21171 TokenCLIP: Token-wise Prompt Learning for Zero-shot Anomaly Detection
        129632, -- 2606.02515 A Biconvex Formulation for Stable Transport of Mixture Models with a U
        129652, -- 2605.08254 HyperTransport: Amortized Conditioning of T2I Generative Models
        129653, -- 2609.31363 Brenier Meets Adversarial Training: Optimal Transport Geometry for Rob
        129673, -- external VecUQ-OT: Aggregating Uncertainty Measures via Multivariate Ranks
        129795, -- 2605.08123 Block-Wise Differentiable Sinkhorn Attention: Tail-Refinement Gradient
        129816, -- external BDC-Merge: Cross-Architecture Model Merging via Dependency Alignment
        129835, -- external State Evolution Awareness for Category-agnostic 3D Point Cloud Trackin
        129852, -- 2602.12683 Flow Matching from Viewpoint of Proximal Operators
        129940, -- external $SE(2)$-Aware Conditional Distribution Transport for Vehicle Trajector
        130002, -- external Reweighted Flow Matching via Unbalanced Optimal Transport for Label-fr
        130023, -- external Transductive Generalization for GNNs via Optimal Transport
        130031, -- 2610.07706 WASD: Wasserstein-based Knowledge Distillation for Large Language Mode
        130182, -- 2609.06598 Deep Barycentric Regression for Optimal Transport Map Estimation and i
        130348, -- 2605.08515 Quantile-Coupled Flow Matching for Distributional Reinforcement Learni
        130372, -- external MOSAIC: Concept Bottlenecks via Text-Anchored Optimal Transport
        130395, -- 2609.15883 Learning Multimodal One-step Flow Policy via Value-weighted Optimal Tr
        130500, -- 2608.21070 TracingFlow: A Simulation-Free Trajectory Inference Framework Based on
        130558, -- external Look-ahead Variational Flow for Generative Online Reinforcement Learni
        130657, -- external Scalable Supervised Optimal Transport of Gaussian Mixture Models
        130658, -- external LAMP: Language-Modulated Geometric Preservation for Multi-Modal Object
        130748, -- external Exploration as Constrained Policy-Space Optimization
        130761, -- external Transporting the Past: An Optimal Transport View of Backtracking Count
        130771, -- 2606.00514 Generate in Reconstruction Space, Match in Semantic Space: Transport G
        130810, -- 2606.04683 Minimax Private Estimation of Smooth Optimal-Transport Maps
        130925, -- external A Separation Principle for Cooperative Multi-Agent Reinforcement Learn
        130932, -- 2605.12174 Expected Batch Optimal Transport Plans and Consequences for Flow Match
        131088, -- external Diffeomoprhism-Informed 3D Gaussian Splattings via Screen-Space Optima
        131143, -- 2605.28567 Semantic Optimal Transport for Sparse Autoencoder Feature Matching and
        131160, -- external Quantifying Centrality for Complex Data
        131270, -- 2606.25265 Variational Inference via Entropic Transport Descent
        132023, -- 2405.14664 Fisher Flow Matching for Generative Modeling over Discrete Data
        132129, -- 1306.0895 Sinkhorn Distances: Lightspeed Computation of Optimal Transportation D
        132132  -- 1803.00567 Computational Optimal Transport
  );

DELETE FROM paper_method_exclusions x
USING optimal_transport_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM optimal_transport_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM optimal_transport_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE optimal_transport_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'optimal-transport'
  AND p.id IN (
        45767, -- 2503.07191 All That Glitters Is Not Gold: Key-Secured 3D Secrets within 3D Gaussi
        128922, -- 2603.20656 Sinkhorn Based Associative Memory Retrieval Using Spherical Hellinger
        131071  -- 2605.12338 Manifold Sampling via Entropy Maximization
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM optimal_transport_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING optimal_transport_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING optimal_transport_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- variational-inference: 253 links, 0 exclusions.
CREATE TEMP TABLE variational_inference_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'variational-inference'
  AND p.id IN (
        69, -- 1312.6114 Auto-Encoding Variational Bayes
        188, -- 1505.05770 Variational Inference with Normalizing Flows
        485, -- 1610.05683 Reparameterization Gradients through Acceptance-Rejection Sampling Alg
        592, -- 1702.08359 Dynamic Word Embeddings
        950, -- 1711.00848 Variational Inference of Disentangled Latent Concepts from Unlabeled O
        1097, -- 1802.04220 Augment and Reduce: Stochastic Inference for Large Categorical Distrib
        1386, -- 1807.03756 Latent Alignment and Variational Attention
        1526, -- 1810.01367 FFJORD: Free-form Continuous Dynamics for Scalable Reversible Generati
        1601, -- 1811.01339 A Novel Predictive-Coding-Inspired Variational RNN Model for Online Pr
        1638, -- 1811.08337 Black-Box Autoregressive Density Estimation for State-Space Models
        1797, -- 1902.00057 Probabilistic Discriminative Learning with Layered Graphical Models
        1910, -- 1903.09940 Variational Inference with Latent Space Quantization for Adversarial R
        2238, -- 1906.04032 Neural Spline Flows
        2414, -- 1908.04847 Convergence Rates of Variational Inference in Sparse Deep Learning
        2840, -- 1911.09514 Continual Learning with Adaptive Weights (CLAW)
        2973, -- 1912.13440 Approximate Inference for Fully Bayesian Gaussian Process Regression
        3226, -- 2003.07718 Nonparametric Deconvolution Models
        3381, -- 2004.09143 Variational Inference for Learning Representations of Natural Language
        3915, -- 2007.09880 Mixture Representation Learning with Coupled Autoencoders
        4536, -- 2011.05041 Sparse within Sparse Gaussian Processes using Neighbor Information
        5682, -- 2105.04143 Matching Visual Features to Hierarchical Semantic Topics for Image Par
        6276, -- 2107.09028 Structured Stochastic Gradient MCMC
        6582, -- 2109.04325 Learning Opinion Summarizers by Selecting Informative Reviews
        7133, -- 2111.01482 DAGSurv: Directed Acyclic Graph Based Survival Analysis Using Deep Neu
        7836, -- 2202.00665 Tutorial on amortized optimization
        8142, -- 2203.02336 Differentiable Causal Discovery Under Latent Interventions
        8293, -- 2203.08509 Differentiable DAG Sampling
        8374, -- 2203.11437 Representation Uncertainty in Self-Supervised Learning as Variational
        8729, -- 2204.07372 A Personalized Dialogue Generator with Implicit User Persona Detection
        9030, -- 2205.07475 MixFlows: principled variational inference via mixed flows
        9125, -- 2205.11275 RL with KL penalties is better viewed as Bayesian inference
        9195, -- 2205.12934 Amortized Inference for Causal Structure Learning
        9273, -- 2205.15008 Efficient Transformed Gaussian Processes for Non-Stationary Dependent
        9348, -- 2206.01665 BaCaDI: Bayesian Causal Discovery with Unknown Interventions
        9595, -- 2206.12040 End-to-End Text-to-Speech Based on Latent Representation of Speaking S
        9786, -- 2207.06415 The Free Energy Principle for Perception and Action: A Deep Learning P
        10086, -- 2208.09392 Cold Diffusion: Inverting Arbitrary Image Transforms Without Noise
        10349, -- 2209.09422 Bit Allocation using Optimization
        10442, -- 2209.14249 Compositional Score Modeling for Simulation-based Inference
        10572, -- 2210.02390 Bayesian Prompt Learning for Image-Language Model Generalization
        10751, -- 2210.06345 Variational Open-Domain Question Answering
        11010, -- 2210.12928 GFlowOut: Dropout with Generative Flow Networks
        11303, -- 2211.05964 Thompson Sampling for High-Dimensional Sparse Linear Contextual Bandit
        11584, -- 2211.13402 MP-GELU Bayesian Neural Networks: Moment Propagation by GELU Nonlinear
        12553, -- 2301.11294 Coin Sampling: Gradient-Based Bayesian Inference without Learning Rate
        12564, -- 2301.11355 Rigid Body Flows for Sampling Molecular Crystal Structures
        12643, -- 2301.12594 A theory of continuous generative flow networks
        13063, -- 2302.06576 GFlowNet-EM for learning compositional latent variable models
        13206, -- 2302.09921 Free-Form Variational Inference for Gaussian Process State-Space Model
        13379, -- 2302.14578 Interactive Segmentation as Gaussian Process Classification
        13684, -- 2303.06682 DDS2M: Self-Supervised Denoising Diffusion Spatio-Spectral Model for H
        13888, -- 2303.10472 Practical and Matching Gradient Variance Bounds for Black-Box Variatio
        14426, -- 2304.01514 Robust Outlier Rejection for 3D Registration with Variational Bayes
        14623, -- 2304.05398 Forward-backward Gaussian variational inference via JKO in the Bures-W
        14901, -- 2304.11751 Score-Based Diffusion Models as Principled Priors for Inverse Imaging
        16654, -- 2305.19744 Neural Markov Jump Processes
        16888, -- 2306.01802 Linear Time GPs for Inferring Latent Trajectories from Neural Spike Tr
        16937, -- 2306.02418 ContraBAR: Contrastive Bayes-Adaptive Deep RL
        16959, -- 2306.02775 Input-gradient space particle inference for neural network ensembles
        17086, -- 2306.04201 Improving Hyperparameter Learning under Approximate Inference in Gauss
        17519, -- 2306.09595 Structured Cooperative Learning with Graphical Model Priors
        17527, -- 2306.09702 A Hierarchical Bayesian Model for Deep Few-Shot Meta Learning
        17668, -- 2306.12509 Joint Prompt Optimization of Stacked LLMs using Variational Inference
        17968, -- 2307.01050 Transport meets Variational Inference: Controlled Monte Carlo Diffusio
        18845, -- 2308.00904 VLUCI: Variational Learning of Unobserved Confounders for Counterfactu
        19068, -- 2308.04682 Score Priors Guided Deep Variational Inference for Unsupervised Real-W
        20966, -- 2309.15458 LogicMP: A Neuro-symbolic Approach for Encoding First-order Logic Cons
        21926, -- 2310.08774 PhyloGFN: Phylogenetic inference with generative flow networks
        22238, -- 2310.12975 Variational Inference for SDEs Driven by Fractional Noise
        22962, -- 2311.02516 Forward $χ^2$ Divergence Based Variational Importance Sampling
        22998, -- 2311.03309 Neural Structure Learning with Stochastic Differential Equations
        23603, -- 2311.12454 HierSpeech++: Bridging the Gap between Semantic and Acoustic Represent
        23763, -- 2311.15211 Probabilistic Transformer: A Probabilistic Dependency Model for Contex
        26020, -- 2401.10402 Reconstructing the Invisible: Video Frame Restoration through Siamese
        27242, -- 2402.08182 Variational Continual Test-Time Adaptation
        27458, -- 2402.11025 Training Bayesian Neural Networks with Sparse Subspace Variational Inf
        29374, -- 2403.15881 Fast and Unified Path Gradient Estimators for Normalizing Flows
        30479, -- 2404.11599 Variational Bayesian Last Layers
        30858, -- 2404.17951 Cauchy-Schwarz Divergence Information Bottleneck for Regression
        32502, -- 2406.04843 Variational Flow Matching for Graph Generation
        33516, -- 2406.15742 Probabilistic Programming with Programmable Variational Inference
        33692, -- 2406.17863 What type of inference is planning?
        34310, -- 2407.06057 Variational Best-of-N Alignment
        34496, -- 2407.08551 Autoregressive Speech Synthesis without Vector Quantization
        35085, -- 2407.16125 Diffusion Prior-Based Amortized Variational Inference for Noisy Invers
        36570, -- 2409.02529 Sample what you cant compress
        41181, -- 2412.05723 Training-Free Bayesianization for Low-Rank Adapters of Large Language
        41534, -- 2412.10208 Efficient Generative Modeling with Residual Vector Quantization-Based
        43578, -- 2502.01567 Scalable Language Models with Posterior Inference of Latent Thought Ve
        45238, -- 2503.00156 Neural Posterior Estimation for Cataloging Astronomical Images with Sp
        46803, -- 2503.20730 Benchmarking and optimizing organism wide single-cell RNA alignment me
        47335, -- 2504.04318 Variational Self-Supervised Learning
        52957, -- 2509.22637 Variational Reasoning for Language Models
        53895, -- 2510.23925 Latent Chain-of-Thought for Visual Reasoning
        54890, -- 2512.12576 Coupled Variational Reinforcement Learning for Language Model General
        60752, -- 2602.12243 Federated Gaussian Process Learning via Pseudo-Representations for Lar
        60849, -- 2602.10623 Mitigating Reward Hacking in RLHF via Bayesian Non-negative Reward Mod
        63957, -- 2512.14713 A Bayesian latent class reinforcement learning framework to capture ad
        70183, -- 2508.03589 VITA: Variational Pretraining of Transformers for Climate-Robust Crop
        71662, -- 2506.22963 CN-SBM: Categorical Block Modelling For Primary and Residual Copy Numb
        73917, -- 2503.17940 FisherTune: Fisher-Guided Robust Tuning of Vision Foundation Models fo
        75592, -- 2412.04130 Deep priors for satellite image restoration with accurate uncertaintie
        78181, -- 2311.17744 Variational Bayes image restoration with compressive autoencoders
        78402, -- 2310.06643 Implicit Variational Inference for High-Dimensional Posteriors
        78549, -- 2309.03122 Bayesian Evidence Synthesis for Modeling SARS-CoV-2 Transmission
        78713, -- 2307.16171 HierVST: Hierarchical Adaptive Zero-shot Voice Style Transfer
        79276, -- 2303.04156 Computing with Categories in Machine Learning
        79625, -- 2210.14709 Learning on Large-scale Text-attributed Graphs via Variational Inferen
        79998, -- 2205.04550 A for-loop is all you need. For solving the inverse problem in the cas
        80444, -- 2110.08607 Physics-guided Deep Markov Models for Learning Nonlinear Dynamical Sys
        80637, -- 2106.14806 Laplace Redux -- Effortless Bayesian Deep Learning
        80677, -- 2106.06103 Conditional Variational Autoencoder with Adversarial Learning for   En
        81524, -- 1911.09804 Measuring Uncertainty through Bayesian Learning of Deep Neural Network
        81802, -- 1903.00450 Multi-Object Representation Learning with Iterative Variational Infere
        81891, -- 1810.11859 Consistency of ELBO maximization for model selection
        82028, -- 1805.00909 Reinforcement Learning and Control as Probabilistic Inference: Tutoria
        82149, -- 1711.02679 Neural Variational Inference and Learning in Undirected Graphical Mode
        82487, -- 1507.03228 Scalable Bayesian Inference for Excitatory Point Process Networks
        82569, -- 1406.1485 Iterative Neural Autoregressive Distribution Estimator (NADE-k)
        83151, -- 2605.08978 Learning to Explore: Scaling Agentic Reasoning via Exploration-Aware P
        83514, -- 2605.19376 Generative Recursive Reasoning
        85811, -- 2506.04749 Amortized Variational Transdimensional Inference
        85814, -- 2505.14161 Personalized Bayesian Federated Learning with Wasserstein Barycenter A
        85927, -- 2509.23602 Deep Taxonomic Networks for Unsupervised Hierarchical Prototype Discov
        86171, -- 2506.22666 VERA: Variational Inference Framework for Jailbreaking Large Language
        86265, -- 2505.21721 Nearly Dimension-Independent Convergence of Mean-Field Black-Box Varia
        86389, -- 2410.19315 Brain-like variational inference
        86429, -- 2509.16606 Bayesian Ego-graph inference for Networked Multi-Agent Reinforcement L
        86503, -- 2506.22655 Learning Stochastic Multiscale Models
        86510, -- 2405.15167 ProDAG: Projected Variational Inference for Directed Acyclic Graphs
        86553, -- 2504.14025 Large Language Bayes
        86646, -- 2509.25822 Act to See, See to Act: Diffusion-Driven Perception-Action Interplay f
        86714, -- 2502.06164 Functional Complexity-adaptive Temporal Tensor Decomposition
        86858, -- 2506.17796 SING: SDE Inference via Natural Gradients
        86877, -- 2502.19670 Training Robust Graph Neural Networks by Modeling Noise Dependencies
        86903, -- 2506.18283 Quantifying Uncertainty in the Presence of Distribution Shifts
        86977, -- 2506.13613 Variational Inference with  Mixtures of Isotropic Gaussians
        87005, -- 2502.18475 Least squares variational inference
        87122, -- 2506.07687 Rao-Blackwellised Reparameterisation Gradients
        87200, -- 2506.07413 Variational Supervised Contrastive Learning
        87333, -- 2505.24243 Model Informed Flows for Bayesian Inference of Probabilistic Programs
        87469, -- 2502.08253 Multi-View Oriented GPLVM: Expressiveness and Efficiency
        88392, -- 2503.08829 Seal Your Backdoor with Variational Defense
        88535, -- 2501.18756 A Unified Framework for Entropy Search and Expected Improvement in Bay
        88593, -- 2506.18340 Controlled Generation with Equivariant Variational Flow Matching
        88881, -- 2502.09591 Censor Dependent Variational Inference
        88995, -- 2505.22438 Synonymous Variational Inference for Perceptual Image Compression
        89032, -- 2506.06778 Continuous Semi-Implicit Models
        89147, -- 2411.05331 Discovering Latent Causal Graphs from Spatiotemporal Data
        89524, -- 2507.07621 Sparse Causal Discovery with Generative Intervention for Unsupervised
        89568, -- 2506.03839 Revisiting Unbiased Implicit Variational Inference
        89603, -- 2406.16971 Flexible Tails for Normalizing Flows
        89812, -- 2502.03686 Variational Control for Guidance in Diffusion Models
        89858, -- 2312.16560 Adaptive Message Passing: A General Framework to Mitigate Oversmoothin
        89931, -- 2501.16825 Can Transformers Learn Full Bayesian Inference in Context?
        89985, -- 2502.00846 Federated Generalised Variational Inference: A Robust Probabilistic Fe
        91057, -- 2410.05602 Amortized Control of Continuous State Space Feynman-Kac Model for Irre
        91064, -- 2405.15325 On the Identification of Temporal Causal Representation with Instantan
        91127, -- 2410.07927 Efficient Reinforcement Learning with Large Language Model Priors
        91240, -- 2406.09116 Injective flows for star-like manifolds
        91259, -- 2503.00524 End-to-end Learning of Gaussian Mixture Priors for Diffusion Sampler
        91363, -- 2410.13117 Preference Diffusion for Recommendation
        91522, -- 2409.06142 Variational Search Distributions
        91672, -- 2502.21143 Variational Bayesian Pseudo-Coreset
        91718, -- 2410.22948 ELBOing Stein: Variational Bayes with Stein Mixture Inference
        91777, -- 2410.12730 Counterfactual Generative Modeling with Variational Causal Inference
        91987, -- 2410.02490 Stochastic variance-reduced Gaussian variational inference on the Bure
        91990, -- 2502.08696 Scalable Discrete Diffusion Samplers: Combinatorial Optimization and S
        92228, -- 2501.17325 Connecting Federated ADMM to Bayes
        92379, -- 2406.00368 Learning Spatiotemporal Dynamical Systems from Point Process Observati
        92425, -- 2407.15687 SoftCVI: Contrastive variational inference with self-generated soft la
        92921, -- 2505.20235 Variational Deep Learning via Implicit Regularization
        93065, -- 2602.08782 Amortising Inference and Meta-Learning Priors in Neural Networks
        93382, -- 2605.13151 GenCape: Structure-Inductive Generative Modeling for Category-Agnostic
        93891, -- 2505.24664 Learning Distributions over Permutations and Rankings with Factorized
        94382, -- 2305.12996 Multilevel Control Functional
        94478, -- 2509.19078 Diffusion Bridge Variational Inference for Deep Gaussian Processes
        96378, -- 2411.06378 PKF: Probabilistic Data Association Kalman Filter for Multi-Object Tra
        96894, -- 2512.19855 Gaussian Variational Inference with Non-Gaussian Factors for State Est
        97303, -- 2604.02696 VBGS-SLAM: Variational Bayesian Gaussian Splatting Simultaneous Locali
        97759, -- 2509.08069 SVN-ICP: Uncertainty Estimation of ICP-Based LiDAR Odometry Using Stei
        97795, -- external Tacser and Action-Conditioned Latent Filter for Generalizable Robotic
        99209, -- 2602.05774 Variational Speculative Decoding: Rethinking Draft Training from Token
        99251, -- 2510.21300 Amortized Variational Inference for Partial-Label Learning: A Probabil
        99435, -- 2605.30968 Variational Adapter for Cross-modal Similarity Representation
        99456, -- 2510.17759 VERA-V: Variational Inference Framework for Jailbreaking Vision-Langua
        99617, -- 2605.28441 Bayesian Gated Non-Negative Contrastive Learning
        99774, -- 2605.05133 Transformed Latent Variable Multi-Output Gaussian Processes
        100049, -- 2602.18718 Stochastic Gradient Variational Inference with Price's Gradient Estima
        100138, -- 2601.21696 Independent Component Discovery in Temporal Count Data
        100475, -- 2603.20111 Var-JEPA: A Variational Formulation of the Joint-Embedding Predictive
        100824, -- 2601.00632 Variational inference via Gaussian interacting particles in the Bures-
        101003, -- 2602.15206 MAVRL: Learning Reward Functions from Multiple Feedback Types with Amo
        101147, -- 2606.07677 Disentangling Latent Risk Pathways via Bayesian Hypergraph Inference
        101540, -- 2605.30873 Federated Variational Preference Alignment with Gumbel-Softmax Prior f
        101545, -- 2507.05482 Stein Diffusion Guidance: Training-Free Posterior Correction for Sampl
        101618, -- 2605.15417 $f$-Trajectory Balance: A Loss Family for Tuning GFlowNets, Generative
        101672, -- 2205.13911 Pseudo-Mallows for Efficient Probabilistic Preference Learning
        101743, -- 2606.25745 Gaussian Mean Field Variational Inference can Overestimate Predictive
        101769, -- 2606.02133 Variational Learning for Insertion-based Generation
        101876, -- 2410.14843 Predictive variational inference: Learn the predictively optimal poste
        101982, -- 2606.00309 Large-scale Uncertainty Quantification for Latent Variable Models Usin
        102521, -- 2603.09453 Variational Routing: A Scalable Bayesian Framework for Calibrated Mixt
        104361, -- 2006.04240 Improving Inference for Neural Image Compression
        104966, -- external BayeSMM: Robust Deep Combined Computing Tackling Heavy-tailed Distribu
        105684, -- 2503.06588 Speech Audio Generation from Dynamic MRI via a Knowledge Enhanced Cond
        105745, -- external The Refining of Brain Connectivity Features on Residual Posterior Patt
        105868, -- 2607.17674 Uncovering Latent Reasoning Strategies in Language Models
        107246, -- 2511.12917 Explore How to Inject Beneficial Noise in MLLMs
        108523, -- 2508.02724 Veli: Unsupervised Method and Unified Benchmark for Low-Cost Air Quali
        111334, -- 2506.07536 Bayesian Learning for Domain-Invariant Speaker Verification and Anti-S
        113384, -- 2408.08149 Unsupervised Variational Translator for Bridging Image Restoration and
        114016, -- 2609.07816 Kalman Delta Networks: Uncertainty-aware Associative Memory
        116157, -- 2403.17502 SeNM-VAE: Semi-Supervised Noise Modeling with Hierarchical Variational
        116242, -- 2403.11193 Neural Markov Random Field for Stereo Matching
        117856, -- 2603.17415 Structured SIR: Efficient and Expressive Importance-Weighted Inference
        120645, -- external Beyond Euclidean Gossip: KL-Barycentric Consensus on Heterogeneous and
        120853, -- external Variational Graph-based Normal Integration
        123303, -- 1811.04551 Learning Latent Dynamics for Planning from Pixels
        123934, -- 2012.04567 Bayesian Image Reconstruction using Deep Generative Models
        124664, -- 2610.03647 Amortized Structured Stochastic Variational Inference for Gaussian Pro
        125112, -- external ELPAC: Endpoint-Anchored Latent Progression with Stage-Varying Multimo
        125404, -- 2604.21407 Even More Guarantees for Variational Inference in the Presence of Symm
        125568, -- external Generalised Linear Models in Deep Bayesian RL with Learnable Basis Fun
        125735, -- 2602.12923 Annealing in variational inference mitigates mode collapse: a theoreti
        126127, -- external Parallel-in-Time Variational Inference for Latent Stochastic Different
        126378, -- external Approximate Bayesian inference with exchangeable distributions for neu
        126393, -- 2606.01954 Flow-Transformed Implicit Processes for Function-Space Variational Inf
        127346, -- 2606.16408 MUNI: Multimodal Unified Latent Diffusion for Coherent Any-to-Any Gene
        127510, -- 2602.08819 Bayesian Preference Learning for Test-Time Steerable Reward Models
        128104, -- external Denoising Implicit Variational Inference
        128332, -- external Probabilistic Recursive Reasoning
        128402, -- external Incorporating Neural Network Structure in the Bayesian Learning Rule
        128426, -- external Confounding-Aware Client Selection in Federated Learning via Causal Me
        128429, -- external Score-based Variational Inference via Quantum Maximally Mixed States
        128618, -- external TailAdapt: Heavy-Tailed Sparse Variational Adaptation for Long-Tailed
        129156, -- 2609.32363 DiffPTS: Rethinking Diffusion ELBO for Probabilistic Time Series Forec
        129230, -- 2606.16138 Closing the Approximation Gap in Simulation-free Latent SDEs
        129280, -- 2604.18310 Symmetry Guarantees Statistic Recovery in Variational Inference
        129290, -- external Parallel Computation Algorithms and Convergence Guarantees for Mean-Fi
        129704, -- external Aligning Few-Step Generative Model via Amortizing Sample-Based Variati
        129970, -- external Heteroscedastic Variational Last Layers
        130019, -- 2607.08254 CASL-VAE: Learning Structured Latent Variables from Unpaired Data for
        130401, -- external Distributionally Robust Domain Randomization with Learned Risk-Sensiti
        130451, -- external Efficient Variational Inference for Log-Gaussian Cox Processes via Vor
        130585, -- 2605.07676 Structured Coupling for Flow Matching
        130780, -- external Beyond Single-Step Likelihood: Gibbs Variational Last Layers for Long-
        130813, -- 2511.21223 Maxitive Donsker-Varadhan Formulation for Possibilistic Variational In
        130905, -- external The balance between feature learning and collapse in generative dynami
        131047, -- external CLUE: Correlated Latent Uncertainty for Single-Pass Deep Uncertainty E
        131235, -- external DnNP: Denoising Input Uncertainty in Neural Processes
        131270, -- 2606.25265 Variational Inference via Entropic Transport Descent
        132131  -- 1601.00670 Variational Inference: A Review for Statisticians
  );

DELETE FROM paper_method_exclusions x
USING variational_inference_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM variational_inference_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM variational_inference_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- markov-chain-monte-carlo: 209 links, 3 exclusions.
CREATE TEMP TABLE markov_chain_monte_carlo_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'markov-chain-monte-carlo'
  AND p.id IN (
        22, -- 1211.4246 What Regularized Auto-Encoders Learn from the Data Generating Distribu
        29, -- 1305.6663 Generalized Denoising Auto-Encoders as Generative Models
        390, -- 1606.01855 Bayesian Poisson Tucker Decomposition for Learning the Structure of In
        853, -- 1708.06040 Meta-Learning MCMC Proposals
        1654, -- 1811.10996 CGMH: Constrained Sentence Generation by Metropolis-Hastings Sampling
        1737, -- 1901.00862 Learning Nonlinear State Space Models with Hamiltonian Sequential Mont
        2709, -- 1910.09483 Sampling random graph homomorphisms and applications to network data a
        2973, -- 1912.13440 Approximate Inference for Fully Bayesian Gaussian Process Regression
        3106, -- 2002.06707 Stochastic Normalizing Flows
        3399, -- 2004.11231 Federated Stochastic Gradient Langevin Dynamics
        4615, -- 2011.12829 All You Need is a Good Functional Prior for Bayesian Deep Learning
        5669, -- 2105.03418 Deep Learning Hamiltonian Monte Carlo
        5967, -- 2106.06245 Model Selection for Bayesian Autoencoders
        6276, -- 2107.09028 Structured Stochastic Gradient MCMC
        6571, -- 2109.03839 Sqrt(d) Dimension Dependence of Langevin Monte Carlo
        7220, -- 2111.08140 Bayesian inference of the climbing grade scale
        7391, -- 2112.01586 HMC with Normalizing Flows
        9030, -- 2205.07475 MixFlows: principled variational inference via mixed flows
        9447, -- 2206.05764 Mining Multi-Label Samples from Single Positive Labels
        10442, -- 2209.14249 Compositional Score Modeling for Simulation-based Inference
        10451, -- 2209.14593 Denoising MCMC for Accelerating Diffusion-Based Generative Models
        10471, -- 2209.15031 Automatic Data Augmentation via Invariance-Constrained Learning
        11303, -- 2211.05964 Thompson Sampling for High-Dimensional Sparse Linear Contextual Bandit
        11996, -- 2212.07959 Scalable Bayesian Uncertainty Quantification for Neural Network Potent
        12306, -- 2301.01828 On Sequential Bayesian Inference for Continual Learning
        12716, -- 2301.13778 Differentially Private Distributed Bayesian Linear Regression with MCM
        12755, -- 2302.00564 Automatically Marginalized MCMC in Probabilistic Programming
        12778, -- 2302.01170 Timewarp: Transferable Acceleration of Molecular Dynamics by Learning
        12801, -- 2302.01513 Towards Practical Preferential Bayesian Optimization with Skew Gaussia
        12973, -- 2302.04534 Fully Bayesian Autoencoders with Latent Sparse Gaussian Processes
        12988, -- 2302.04763 On Sampling with Approximate Transport Maps
        13206, -- 2302.09921 Free-Form Variational Inference for Gaussian Process State-Space Model
        13256, -- 2302.11552 Reduce, Reuse, Recycle: Compositional Generation with Energy-Based Dif
        13651, -- 2303.06171 DP-Fast MH: Private, Fast, and Accurate Metropolis-Hastings for Large-
        16135, -- 2305.14765 Masked Bayesian Neural Networks : Theoretical Guarantee and its Poster
        16293, -- 2305.15988 Non-Log-Concave and Nonsmooth Sampling via Langevin Monte Carlo Algori
        16489, -- 2305.18246 Provable and Practical: Efficient Exploration in Reinforcement Learnin
        16635, -- 2305.19473 Chain of Log-Concave Markov Chains
        16648, -- 2305.19684 End-to-end Training of Deep Boltzmann Machines by Unbiased Contrastive
        16685, -- 2305.20028 A Study of Bayesian Neural Network Surrogates for Bayesian Optimizatio
        17300, -- 2306.07060 Prediction Algorithms Achieving Bayesian Decision Theoretical Optimali
        17336, -- 2306.07473 3D molecule generation by denoising voxel grids
        17663, -- 2306.12360 Protein Discovery with Discrete Walk-Jump Sampling
        17829, -- 2306.15837 Symbol emergence as interpersonal cross-situational learning: the emer
        17946, -- 2307.00494 Improving Protein Optimization with Smoothed Fitness Landscapes
        18010, -- 2307.02037 Reverse Diffusion Monte Carlo
        20268, -- 2309.05153 Learning Energy-Based Models by Cooperative Diffusion Recovery Likelih
        21615, -- 2310.05401 Entropy-MCMC: Sampling from Flat Basins with Ease
        22377, -- 2310.14661 Tractable MCMC for Private Learning with Pure and Gaussian Differentia
        23077, -- 2311.04457 Evaluating Uncertainty Quantification approaches for Neural PDEs in sc
        24243, -- 2312.02179 Training Chain-of-Thought via Latent-Variable Inference
        25966, -- 2401.09665 Accelerating Distributed Stochastic Optimization via Self-Repellent Ra
        26389, -- 2401.15838 Distributed Markov Chain Monte Carlo Sampling based on the Alternating
        29158, -- 2403.13178 Fast Value Tracking for Deep Reinforcement Learning
        30359, -- 2404.09591 3D Gaussian Splatting as Markov Chain Monte Carlo
        32151, -- 2406.00049 QUEST: Quality-Aware Metropolis-Hastings Sampling for Machine Translat
        33344, -- 2406.13661 Hitchhiker's guide on the relation of Energy-Based Models with other g
        40439, -- 2411.16567 Enhancing Few-Shot Learning with Integrated Data and GAN Model Approac
        45003, -- 2502.18300 Bayesian Computation in Deep Learning
        47312, -- 2504.03790 Sample, Don't Search: Rethinking Test-Time Alignment for Language Mode
        50212, -- 2505.24222 Unleashing High-Quality Image Generation in Diffusion Sampling Using S
        53131, -- 2510.00225 TGPO: Temporal Grounded Policy Optimization for Signal Temporal Logic
        53814, -- 2510.14901 Reasoning with Sampling: Your Base Model is Smarter Than You Think
        55585, -- 2601.21590 Scalable Power Sampling: Unlocking Efficient, Training-Free Reasoning
        59559, -- 2603.10987 MCMC Informed Neural Emulators for Uncertainty Quantification in Dynam
        59724, -- 2603.07651 Fisher Curvature Scaling at Critical Points: An Exact Information-Geom
        61542, -- 2602.01176 Multi-Fidelity Physics-Informed Neural Networks with Bayesian Uncertai
        62136, -- 2601.16736 A Step to Decouple Optimization in 3DGS
        65166, -- 2511.11666 Adaptive Stepsizing for Stochastic Gradient Langevin Dynamics in Bayes
        66493, -- 2510.13872 Joint Discriminative-Generative Modeling via Dual Adversarial Training
        66662, -- 2510.09078 MCMC: Bridging Rendering, Optimization and Generative AI
        67251, -- 2510.00352 AReUReDi: Annealed Rectified Updates for Refining Discrete Flows with
        69197, -- 2508.18175 Amortized Sampling with Transferable Normalizing Flows
        69399, -- 2508.15069 Sampling by averaging: A multiscale approach to score estimation
        72089, -- 2410.19897 Reconstructions of Einstein-Aether Gravity from Barrow Agegraphic and
        73698, -- 2504.04211 Accelerated Bayesian Inference for Pulsar Timing Arrays: Normalizing
        74664, -- 2502.12279 Bayesian inference from time series of allele frequency data using exa
        75062, -- 2501.18630 Deformable Beta Splatting
        75211, -- 2501.07268 A differentiable binary microlensing model using adaptive contour   in
        75678, -- 2411.18777 KIC 4150611: A quadruply eclipsing heptuple star system with a g-mode
        75732, -- 2411.14911 Radii, masses, and transit-timing variations of the three-planet syste
        76118, -- 2410.06505 Neural network emulator to constrain the high-z IGM thermal state from
        77124, -- 2406.00565 Efficient Massive Black Hole Binary parameter estimation for LISA usin
        77292, -- 2405.06464 Single-seed generation of Brownian paths and integrals for adaptive an
        78138, -- 2401.00003 Generative Inverse Design of Metamaterials with Functional Responses b
        78297, -- 2310.20447 Efficient Bayesian Learning Curve Extrapolation using Prior-Data Fitte
        78549, -- 2309.03122 Bayesian Evidence Synthesis for Modeling SARS-CoV-2 Transmission
        78560, -- 2309.02213 Bayesian Bi-clustering of Neural Spiking Activity with Latent Structur
        78806, -- 2307.01463 Hybrid two-level MCMC for Bayesian Inverse Problems
        79199, -- 2303.15486 Unimodal Training-Multimodal Prediction: Cross-modal Federated Learnin
        80684, -- 2106.04399 Flow Network based Generative Models for Non-Iterative Diverse Candida
        80879, -- 2101.03288 How to Train Your Energy-Based Models
        81138, -- 2009.05580 Autoregressive Transformer Neural Network for Simulating Open Quantum
        81252, -- 2006.11235 Constraining Early Dark Energy with Large-Scale Structure
        81874, -- 1811.04343 Langevin-gradient parallel tempering for Bayesian neural learning
        82148, -- 1711.03219 Denotational validation of higher-order Bayesian inference
        82235, -- 1705.10498 Zonotope hit-and-run for efficient sampling from projection DPPs
        82288, -- 1701.02434 A Conceptual Introduction to Hamiltonian Monte Carlo
        82538, -- 1411.5018 Frequentism and Bayesianism: A Python-driven Primer
        82551, -- 1409.6772 Protein Chemical Shift Prediction
        82622, -- 1304.1920 Generalizing the No-U-Turn Sampler to Riemannian Manifolds
        84201, -- 2511.17339 ReBaPL: Repulsive Bayesian Prompt Learning
        84214, -- 2511.18378 Synthetic Curriculum Reinforces Compositional Text-to-Image Generation
        85740, -- 2505.17741 Discrete Neural Flow Samplers with Locally Equivariant Transformer
        86028, -- 2506.05754 Constrained Sampling for Language Models Should Be Easy: An MCMC Persp
        86474, -- 2502.16292 Generative diffusion for perceptron problems: statistical physics anal
        86547, -- 2505.12553 Hamiltonian Descent Algorithms for Optimization: Accelerated Rates via
        86553, -- 2504.14025 Large Language Bayes
        86608, -- 2503.01707 Metropolis Adjusted Microcanonical Hamiltonian Monte Carlo
        86717, -- 2505.14177 From stability of Langevin diffusion to convergence of proximal MCMC f
        86870, -- 2506.12945 Metropolis-Hastings Sampling for 3D Gaussian Reconstruction
        87052, -- 2505.19552 On scalable and efficient training of diffusion samplers
        87163, -- 2508.18413 Parallelizing MCMC Across the Sequence Length
        87211, -- 2505.15059 Restricted Spectral Gap Decomposition for Simulated  Tempering Targeti
        87419, -- 2506.02162 Asymptotically exact variational flows via involutive MCMC kernels
        87591, -- 2509.03775 ContraGS: Codebook-Condensed and Trainable Gaussian Splatting for Fast
        88559, -- 2505.18300 Beyond Self-Repellent Kernels: History-Driven Target Towards Efficient
        88596, -- 2502.11909 Neural Guided Diffusion Bridges
        88738, -- 2502.15110 Variational Phylogenetic Inference with Products over Bipartitions
        88855, -- 2502.17150 Differential Privacy Guarantees of Markov Chain Monte Carlo Algorithms
        88915, -- 2506.05231 Progressive Tempering Sampler with Diffusion
        89222, -- 2505.20251 Learning Extrapolative Sequence Transformations from Markov Chains
        89263, -- 2410.10112 Can We Predict Performance of Large Models across Vision-Language Task
        89284, -- 2410.18929 AutoStep: Locally adaptive involutive MCMC
        89412, -- 2503.05574 BARK: A Fully Bayesian Tree Kernel for Black-box Optimization
        89535, -- 2505.19438 Sampling from Binary Quadratic Distributions via Stochastic Localizati
        89568, -- 2506.03839 Revisiting Unbiased Implicit Variational Inference
        89776, -- 2503.15704 Tuning Sequential Monte Carlo Samplers via Greedy Incremental Divergen
        89931, -- 2501.16825 Can Transformers Learn Full Bayesian Inference in Context?
        89996, -- 2503.17405 Efficiently Vectorized MCMC on Modern Accelerators
        91138, -- 2503.00699 Parameter Expanded Stochastic Gradient Markov Chain Monte Carlo
        91243, -- 2409.05873 Procedural Synthesis of Synthesizable Molecules
        91303, -- 2410.22625 Non-Equilibrium Dynamics of Hybrid Continuous-Discrete Ground-State Sa
        91540, -- 2503.08918 Multilevel Generative Samplers for Investigating Critical Phenomena
        91557, -- 2406.00104 Scalable Bayesian Learning with posteriors
        91590, -- 2407.16936 Provable Benefit of Annealed Langevin Monte Carlo for Non-log-concave
        91717, -- 2405.15376 Fast training and sampling of Restricted Boltzmann Machines
        91798, -- 2502.17912 Decoupled Graph Energy-based Model for Node Out-of-Distribution Detect
        91990, -- 2502.08696 Scalable Discrete Diffusion Samplers: Combinatorial Optimization and S
        92104, -- 2502.03685 Controlled LLM Decoding via Discrete Auto-regressive Biasing
        92132, -- 2501.16718 Outlier Synthesis via Hamiltonian Monte Carlo for Out-of-Distribution
        92425, -- 2407.15687 SoftCVI: Contrastive variational inference with self-generated soft la
        92657, -- 2603.01591 FAST‑DIPS: Adjoint‑Free Analytic Steps and Hard‑Constrained Likelihood
        92772, -- 2502.10328 Accelerated Parallel Tempering via Neural Transports
        93004, -- 2509.26544 Bayesian Influence Functions for Hessian-Free Data Attribution
        93045, -- 2603.01230 Stochastic Neural Networks for Causal Inference with Missing Confounde
        93435, -- 2510.00545 Bayesian Neural Networks for Functional ANOVA Model
        93685, -- 2506.08894 Product of Experts for Visual Generation
        94023, -- 2505.23614 Inference-time scaling of diffusion models through classical search
        94217, -- 2604.16919 Noise-Adaptive Diffusion Sampling for Inverse Problems Without Task-Sp
        94537, -- 2506.10060 Textual Bayes: Quantifying Prompt Uncertainty in LLM-Based Systems
        97960, -- 2606.05972 LLM Explainability with Counterfactual Chains and Causal Graphs
        98284, -- 2605.21859 PhylaFlow: Hybrid Flow Matching in Billera-Holmes-Vogtmann Tree Space
        99122, -- 2602.06500 Can Microcanonical Langevin Dynamics Leverage Mini-Batch Gradient Nois
        99209, -- 2602.05774 Variational Speculative Decoding: Rethinking Draft Training from Token
        99448, -- 2406.05242 Markov Chain Monte Carlo without Evaluating the Target: an Auxiliary V
        100008, -- 2602.07767 BFTS: Thompson Sampling with Bayesian Additive Regression Trees
        100261, -- 2602.02806 De-Linearizing Agent Traces: Bayesian Inference of Latent Partial Orde
        100757, -- 2605.09537 Rethinking Instruction Drift as a Sampling Error: SNR-Aware Power Dist
        101012, -- 2601.22367 Amortized Simulation-Based Inference in Generalized Bayes via Neural P
        101167, -- 2605.15487 Learning Normalized Energy Models for Linear Inverse Problems
        101483, -- 2506.03672 Latent Guided Sampling for Combinatorial Optimization
        101587, -- 2602.15925 Robust Stochastic Gradient Posterior Sampling with Lattice Based Discr
        101621, -- 2412.08876 Practical and Scalable Hamiltonian Monte Carlo Without the Metropolis
        101666, -- 2602.17587 Asymptotically Optimal Sequential Testing with Markovian Data
        101668, -- 2601.20782 Neural Quantum States in Mixed Precision
        101672, -- 2205.13911 Pseudo-Mallows for Efficient Probabilistic Preference Learning
        101982, -- 2606.00309 Large-scale Uncertainty Quantification for Latent Variable Models Usin
        101994, -- 2604.22948 Score-Repellent Monte Carlo: Toward Efficient Non-Markovian Sampler wi
        102025, -- 2606.00293 Accurate Large-sample Uncertainty Quantification using Stochastic Grad
        102341, -- 2410.17147 Covariance estimation using Markov chain Monte Carlo
        102348, -- 2605.21722 MetaDNS: Enhancing Exploration in Discrete Neural Samplers via Metadyn
        104836, -- 2605.09117 Rao-Blackwellized Markov Chain Monte Carlo Light Transport
        107806, -- 2603.04392 SELDON: Supernova Explosions Learned by Deep ODE Networks
        109057, -- 2608.08156 A Hybrid Nested Harness for Decoupling Structure and Parameters in LLM
        109117, -- 2607.25356 Data Quality Profiling at Scale with Progressive Sampling: A Benchmark
        109997, -- 2509.07617 Transferable Direct Prompt Injection via Activation-Guided MCMC Sampli
        112202, -- 2409.07148 Jump Restore Light Transport
        113663, -- external Energy-Clibrated VAE with Test Time Free Lunch
        115697, -- 2404.15620 A Dynamic Kernel Prior Model for Unsupervised Blind Image Super-Resolu
        117397, -- 2608.01793 ReFP-AD: Rectified Flow Preconditioning for Energy-Based Anomaly Detec
        117523, -- 2603.19834 Fourier Splatting: Generalized Fourier encoded primitives for scalable
        118242, -- 2607.03855 PRISM3D: Probabilistic Refinement and Robust Initialization for Physic
        121822, -- external Making the Classification Explanation Faithful to the Confidence Score
        123297, -- 1705.07959 Comparison of statistical sampling methods with ScannerBit, the GAMBIT
        123323, -- 2107.04613 Dark matter and lepton flavour phenomenology in a singlet-doublet scot
        124276, -- 2606.30773 Diffusion-warm sampling of the XY model enables fast thermalization at
        124857, -- 2605.12807 Multi-Marginal Couplings for Metropolis--Hastings
        125170, -- external Breaking the $\sqrt{d}$ Communication Barrier in Federated Sampling wi
        125278, -- external Variational Monte Carlo for Quantum Excited States via Nested Low-Rank
        125333, -- external A Revisit of Hamiltonian Monte Carlo Efficiency on Bayesian Neural Net
        125337, -- 2609.00905 When Metropolis and Hastings Meet Bradley and Terry: Exact MCMC From P
        125354, -- external Fast Accurate Quantum Monte Carlo without Metropolis Adjustment
        125604, -- external Parallel Broyden methods for efficiently evaluating nonlinear state sp
        126165, -- external High-Fidelity Boltzmann Samplingvia Physical Prior Lifted Continuous G
        126400, -- 2606.16073 Stop the Sampler! Classifier-Based Adaptive Stopping for Sampling Kern
        127119, -- 2610.19053 Deep Generative Models for Phylogenetic Inference with Complex Evoluti
        127350, -- external Direct Conditional Parameterization for N-Dimensional Splatting
        127960, -- external Diverse Representative Rashomon Sets for Sparse Generalized Additive M
        128123, -- external Complexity Aware Continuous Level of Details for Gaussian Splatting
        129236, -- 2606.02294 Regularized Large Neighborhood Search
        129274, -- external Contour Monte Carlo: Sampling via Energy Level Sets
        130089, -- external Finetuning with Sampling: Make SFT Generalize, Not Forget
        130481, -- external Birth-Death Structural Learning for 3D Gaussian Splatting
        130749, -- external Mesh Invaiant Infinite Dimensional Adaptive MCMC for Latent Gaussian P
        130839, -- 2606.04324 Neural Galerkin Normalizing Flows for Bayesian Inference of Diffusions
        130967, -- 2605.20345 Corrected Integrated Laplace Approximation for Bayesian Inference in L
        131015, -- external Geometry-Aware Score-Repellent Monte Carlo
        132131  -- 1601.00670 Variational Inference: A Review for Statisticians
  );

DELETE FROM paper_method_exclusions x
USING markov_chain_monte_carlo_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM markov_chain_monte_carlo_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM markov_chain_monte_carlo_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE markov_chain_monte_carlo_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'markov-chain-monte-carlo'
  AND p.id IN (
        12888, -- 2302.03026 Sampling-Based Accuracy Testing of Posterior Estimators for General In
        89011, -- 2501.18528 Joint Learning of Energy-based Models and their Partition Function
        101905  -- 2602.02241 Variational Entropic Optimal Transport
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM markov_chain_monte_carlo_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING markov_chain_monte_carlo_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING markov_chain_monte_carlo_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- langevin-dynamics: 170 links, 4 exclusions.
CREATE TEMP TABLE langevin_dynamics_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'langevin-dynamics'
  AND p.id IN (
        29, -- 1305.6663 Generalized Denoising Auto-Encoders as Generative Models
        497, -- 1611.01838 Entropy-SGD: Biasing Gradient Descent Into Wide Valleys
        2338, -- 1907.05600 Generative Modeling by Estimating Gradients of the Data Distribution
        3106, -- 2002.06707 Stochastic Normalizing Flows
        3399, -- 2004.11231 Federated Stochastic Gradient Langevin Dynamics
        3764, -- 2006.11239 Denoising Diffusion Probabilistic Models
        6276, -- 2107.09028 Structured Stochastic Gradient MCMC
        6571, -- 2109.03839 Sqrt(d) Dimension Dependence of Langevin Monte Carlo
        7457, -- 2112.05120 On Convergence of Federated Averaging Langevin Dynamics
        8046, -- 2202.11705 COLD Decoding: Energy-based Constrained Text Generation with Langevin
        9555, -- 2206.10365 A Flexible Diffusion Model
        9733, -- 2207.04387 Bregman Proximal Langevin Monte Carlo via Bregman--Moreau Envelopes
        10086, -- 2208.09392 Cold Diffusion: Inverting Arbitrary Image Transforms Without Noise
        10451, -- 2209.14593 Denoising MCMC for Accelerating Diffusion-Based Generative Models
        12867, -- 2302.02591 Generative Diffusion Models on Graphs: Methods and Applications
        13465, -- 2303.01748 A Complete Recipe for Diffusion Generative Models
        14993, -- 2304.13742 TR0N: Translator Networks for 0-Shot Plug-and-Play Conditional Generat
        16293, -- 2305.15988 Non-Log-Concave and Nonsmooth Sampling via Langevin Monte Carlo Algori
        16489, -- 2305.18246 Provable and Practical: Efficient Exploration in Reinforcement Learnin
        16635, -- 2305.19473 Chain of Log-Concave Markov Chains
        17336, -- 2306.07473 3D molecule generation by denoising voxel grids
        17416, -- 2306.08494 Langevin Monte Carlo for strongly log-concave distributions: Randomize
        17663, -- 2306.12360 Protein Discovery with Discrete Walk-Jump Sampling
        18010, -- 2307.02037 Reverse Diffusion Monte Carlo
        21293, -- 2310.01762 Sampling Multimodal Distributions with the Vanilla Score: Benefits of
        21451, -- 2310.03546 Plug-and-Play Posterior Sampling under Mismatched Measurement and Prio
        21678, -- 2310.06081 Ito Diffusion Approximation of Universal Ito Chains for Sampling, Opti
        21835, -- 2310.07894 Efficient Integrators for Diffusion Generative Models
        24169, -- 2312.01127 Symmetric Mean-field Langevin Dynamics for Distributional Minimax Prob
        25238, -- 2312.16360 Mean-field underdamped Langevin dynamics and its spacetime discretizat
        27273, -- 2402.08679 COLD-Attack: Jailbreaking LLMs with Stealthiness and Controllability
        27865, -- 2402.14989 Stable Neural Stochastic Differential Equations in Analyzing Irregular
        29148, -- 2403.13031 RigorLLM: Resilient Guardrails for Large Language Models against Undes
        29158, -- 2403.13178 Fast Value Tracking for Deep Reinforcement Learning
        30359, -- 2404.09591 3D Gaussian Splatting as Markov Chain Monte Carlo
        32013, -- 2405.19376 PureEBM: Universal Poison Purification via Mid-Run Dynamics of Energy-
        35920, -- 2408.09000 Classifier-Free Guidance is a Predictor-Corrector
        37983, -- 2410.04844 PostEdit: Posterior Sampling for Efficient Zero-Shot Image Editing
        40677, -- 2411.19415 AMO Sampler: Enhancing Text Rendering with Overshooting
        43489, -- 2502.00277 Regularized Langevin Dynamics for Combinatorial Optimization
        43714, -- 2502.03491 Lanpaint: Training-Free Diffusion Inpainting with Exact and Fast Condi
        45024, -- 2502.18462 Scalable Equilibrium Sampling with Sequential Boltzmann Generators
        45393, -- 2503.02187 h-Edit: Effective and Flexible Diffusion-Based Editing via Doob's h-Tr
        46915, -- 2503.22194 ORIGEN: Zero-Shot 3D Orientation Grounding in Text-to-Image Generation
        47884, -- 2504.13320 Gradient-Free Sequential Bayesian Experimental Design via Interacting
        50212, -- 2505.24222 Unleashing High-Quality Image Generation in Diffusion Sampling Using S
        50375, -- 2506.01320 Psi-Sampler: Initial Particle Sampling for SMC-Based Inference-Time Re
        50778, -- 2506.07661 The Universality Lens: Why Even Highly Over-Parametrized Models Learn
        51907, -- 2507.11531 Langevin Flows for Modeling Neural Latent Dynamics
        53211, -- 2510.02730 Dale meets Langevin: A Multiplicative Denoising Diffusion Model
        56810, -- 2603.14588 SuperLocalMemory V3: Information-Geometric Foundations for Zero-LLM En
        57366, -- 2604.08536 RewardFlow: Generate Images by Optimizing What You Reward
        57462, -- 2604.10465 Rethinking the Diffusion Model from a Langevin Perspective
        58773, -- 2603.28248 Reasoning as Energy Minimization over Structured Latent Trajectories
        59797, -- 2603.06028 Improved high-dimensional estimation with Langevin dynamics and stocha
        65166, -- 2511.11666 Adaptive Stepsizing for Stochastic Gradient Langevin Dynamics in Bayes
        66417, -- 2510.24736 RNAGenScape: Property-Guided, Optimized Generation of mRNA Sequences w
        66493, -- 2510.13872 Joint Discriminative-Generative Modeling via Dual Adversarial Training
        68876, -- 2509.01349 Phase diagram and eigenvalue dynamics of stochastic gradient descent i
        69399, -- 2508.15069 Sampling by averaging: A multiscale approach to score estimation
        71191, -- 2507.09608 prNet: Data-Driven Phase Retrieval via Stochastic Refinement
        76071, -- 2410.09700 Microstructural Geometry Revealed by NMR Lineshape Analysis
        76210, -- 2409.02135 Optimization by Parallel Quasi-Quantum Annealing with Gradient-Based S
        77292, -- 2405.06464 Single-seed generation of Brownian paths and integrals for adaptive an
        79065, -- 2305.03486 Iterative α-(de)Blending: a Minimalist Deterministic Diffusion   Model
        79275, -- 2303.04137 Diffusion Policy: Visuomotor Policy Learning via Action Diffusion
        80703, -- 2105.14951 SNIPS: Solving Noisy Inverse Problems Stochastically
        80910, -- 2101.09552 Stochastic Image Denoising by Sampling from the Posterior Distribution
        81571, -- 1910.05383 The chemical Langevin equation: a path integral view of Gillespie's de
        81874, -- 1811.04343 Langevin-gradient parallel tempering for Bayesian neural learning
        82636, -- 1212.2010 Out-of-equilibrium catalysis of chemical reactions by electronic tunne
        82709, -- 1104.4621 Kramers problem for nonequilibrium current-induced chemical reactions
        82816, -- 0707.2234 State-dependent diffusion: thermodynamic consistency and its path inte
        85923, -- 2505.18427 Learning Latent Variable Models via Jarzynski-adjusted Langevin Algori
        86285, -- 2506.12544 Constrained Diffusers for Safe Planning and Control
        86478, -- 2505.18276 Preconditioned Langevin Dynamics with Score-based Generative Models fo
        86608, -- 2503.01707 Metropolis Adjusted Microcanonical Hamiltonian Monte Carlo
        86717, -- 2505.14177 From stability of Langevin diffusion to convergence of proximal MCMC f
        87163, -- 2508.18413 Parallelizing MCMC Across the Sequence Length
        87318, -- 2505.19087 Temperature is All You Need for Generalization in Langevin Dynamics an
        87414, -- 2401.13530 Continuous-time Riemannian SGD and SVRG Flows on Wasserstein Probabili
        88578, -- 2507.03602 Kinetic Langevin Diffusion for Crystalline Materials Generation
        88686, -- 2410.02711 NETS: A Non-equilibrium Transport Sampler
        88693, -- 2505.18786 Leveraging Per-Instance Privacy for Machine Unlearning
        88855, -- 2502.17150 Differential Privacy Guarantees of Markov Chain Monte Carlo Algorithms
        88943, -- 2502.05784 Propagation of Chaos for Mean-Field Langevin Dynamics and its Applicat
        89008, -- 2405.00228 Synthetic Face Datasets Generation via Latent Space Exploration from B
        89144, -- 2505.19659 LangDAug: Langevin Data Augmentation for Multi-Source Domain Generaliz
        89148, -- 2412.05135 The Polynomial Stein Discrepancy for Assessing Moment Convergence
        89289, -- 2502.00557 Sampling Binary Data by Denoising through Score Functions
        89776, -- 2503.15704 Tuning Sequential Monte Carlo Samplers via Greedy Incremental Divergen
        89791, -- 2501.05370 Accelerated Diffusion Models via Speculative Sampling
        89904, -- 2506.15563 Control and Realism: Best of Both Worlds in Layout-to-Image without Tr
        91138, -- 2503.00699 Parameter Expanded Stochastic Gradient Markov Chain Monte Carlo
        91323, -- 2410.03282 Neural Sampling from Boltzmann Densities: Fisher-Rao Curves in the Was
        91499, -- 2412.07081 Sequential Controlled Langevin Diffusions
        91590, -- 2407.16936 Provable Benefit of Annealed Langevin Monte Carlo for Non-log-concave
        91827, -- 2408.07254 Learning Multi-Index Models with Neural Networks via Mean-Field Langev
        91857, -- 2406.07475 Partially Observed Trajectory Inference using Optimal Transport and a
        91864, -- 2410.09697 Provable Convergence and Limitations of Geometric Tempering for Langev
        92104, -- 2502.03685 Controlled LLM Decoding via Discrete Auto-regressive Biasing
        92273, -- 2502.06335 Microcanonical Langevin Ensembles: Advancing the Sampling of Bayesian
        92688, -- 2509.02196 Beyond Ensembles: Simulating All-Atom Protein Dynamics in a Learned La
        93018, -- 2504.18274 Structural Inference: Interpreting Small Language Models with Suscepti
        93067, -- 2603.10281 Taming Score-Based Denoisers in ADMM: A Convergent Plug-and-Play Frame
        93249, -- 2506.07614 Poisson Midpoint Method for Log Concave Sampling: Beyond the Strong Er
        93458, -- 2510.09146 Score-Based Density Estimation from Pairwise Comparisons
        93922, -- 2505.18017 Strictly Constrained Generative Modeling via Split Augmented Langevin
        94023, -- 2505.23614 Inference-time scaling of diffusion models through classical search
        94402, -- 2508.07631 Efficient Approximate Posterior Sampling with Annealed Langevin Monte
        96164, -- 2505.13667 Adaptive Diffusion Constrained Sampling for Bimanual Robot Manipulatio
        99122, -- 2602.06500 Can Microcanonical Langevin Dynamics Leverage Mini-Batch Gradient Nois
        99291, -- 2512.23566 From geometry to dynamics: Learning overdamped Langevin dynamics from
        99691, -- 2601.22932 DC-LA: Difference-of-Convex Langevin Algorithm
        99880, -- 2510.02174 Flatness-Aware Stochastic Gradient Langevin Dynamics
        100617, -- 2605.28589 Thinned Mean Field Langevin Dynamics
        100736, -- 2605.07939 Accelerating Langevin Monte Carlo via Efficient Stochastic Runge-Kutta
        100821, -- 2606.02453 Initialization is Half the Battle: Generating Diverse Images from a Gu
        100994, -- 2603.11319 On the Robustness of Langevin Dynamics to Score Function Error
        101069, -- 2606.02455 Speculative Sampling For Faster Molecular Dynamics
        101083, -- 2505.02621 Mirror Mean-Field Langevin Dynamics
        101223, -- 2603.02429 Dimension-Independent Convergence of Underdamped Langevin Monte Carlo
        101290, -- 2601.04791 Measurement-Consistent Langevin Corrector for Stabilizing Latent Diffu
        101587, -- 2602.15925 Robust Stochastic Gradient Posterior Sampling with Lattice Based Discr
        101591, -- 2602.23039 Dynamics of neural scaling laws in random feature regression with powe
        101605, -- 2601.22349 Forward-KL Convergence of Time-Inhomogeneous Langevin Diffusions
        101621, -- 2412.08876 Practical and Scalable Hamiltonian Monte Carlo Without the Metropolis
        101762, -- 2602.01449 Dimension-Free Multimodal Sampling via Preconditioned Annealed Langevi
        101792, -- 2510.06028 Generalization of Gibbs and Langevin Monte Carlo Algorithms in the Int
        101968, -- 2601.12703 Towards Spectroscopy: Susceptibility Clusters in Language Models
        101982, -- 2606.00309 Large-scale Uncertainty Quantification for Latent Variable Models Usin
        102025, -- 2606.00293 Accurate Large-sample Uncertainty Quantification using Stochastic Grad
        102056, -- 2605.30573 Zeroth-Order Non-Log-Concave Sampling with Variance Reduction and Appl
        102115, -- 2605.11170 Unlearning with Asymmetric Sources: Improved Unlearning-Utility Trade-
        102430, -- 2605.27990 Geometry-Correct Diffusion Posterior Sampling with Denoiser-Pullback C
        106788, -- 2511.13571 Opt3DGS: Optimizing 3D Gaussian Splatting with Adaptive Exploration an
        107588, -- 2501.17323 Exploring Non-Convex Discrete Energy Landscapes: An Efficient Langevin
        110316, -- external Dynamic Energy-Based Contrastive Learning with Multi-Stage Knowledge V
        115697, -- 2404.15620 A Dynamic Kernel Prior Model for Unsupervised Blind Image Super-Resolu
        117208, -- 2312.00075 Accelerating Neural Field Training via Soft Mining
        117397, -- 2608.01793 ReFP-AD: Rectified Flow Preconditioning for Energy-Based Anomaly Detec
        120600, -- external Consistency Posterior Sampling for Diverse Image Synthesis
        120937, -- external Energy Waveify and Redistribution for Test-Time Adaptation: A Control
        123251, -- 2610.00359 Diffusion Editing with Soft Mask: Pixel Level Redo of Image and Video
        124172, -- 2605.09654 Metropolis-Adjusted Diffusion Models
        124444, -- external Preconditioned Implicit Midpoint Langevin Sampling for Non-Smooth Baye
        124473, -- 2605.09302 Discrete Langevin-Inspired Posterior Sampling
        124651, -- 2605.21253 Theoretical guidelines for annealed Langevin dynamics in compositional
        125041, -- external Global Convergence in Deep Networks via the Second Law of Thermodynami
        125170, -- external Breaking the $\sqrt{d}$ Communication Barrier in Federated Sampling wi
        125418, -- 2605.07950 Slowly Annealed Langevin Dynamics: Theory and Applications to Training
        125515, -- external Reversing the Roles of Signal and Noise: Modeling Noise in Astronomica
        126115, -- 2605.16473 Dimension-Uniform Discretization Analysis of Preconditioned Annealed L
        126219, -- 2605.14276 Training-Free Generative Sampling via Moment-Matched Score Smoothing
        126267, -- external Scale-mixture Langevin sampling in the subspaces of recurrent cortical
        126747, -- external Decentralized Coupled Representation Learning
        127373, -- external NLD4CO: Neural Langevin Dynamics  for Combinatorial Optimization
        129232, -- external Towards Closing the Autoregressive Gap in Language Modeling via Entrop
        129290, -- external Parallel Computation Algorithms and Convergence Guarantees for Mean-Fi
        129415, -- external Beyond Langevin: Sampling Multimodal Densities using the Witten Laplac
        129471, -- 2601.21951 Diffusion Path Samplers via Sequential Monte Carlo
        130237, -- 2605.18381 Generating Physically Consistent Molecules with Energy-Based Models
        130749, -- external Mesh Invaiant Infinite Dimensional Adaptive MCMC for Latent Gaussian P
        130758, -- external How Should Parallel Langevin Chains Share Noise?
        130762, -- external Langevin-Informed Transfer Learning: Replacing the Target Samples by B
        130919, -- external Gibbs Gradient Descent: A Langevin Approach to Optimization
        131079, -- external Learning Rate Decay Can Exponentially Accelerate SGD for Global Optimi
        131125, -- 2606.22346 Flow Annealing Posterior Sampling for Function-Space Regression and In
        131270, -- 2606.25265 Variational Inference via Entropic Transport Descent
        132034  -- 2605.07013 CoBit: Language Modeling with Bitstream Diffusion
  );

DELETE FROM paper_method_exclusions x
USING langevin_dynamics_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM langevin_dynamics_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM langevin_dynamics_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE langevin_dynamics_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'langevin-dynamics'
  AND p.id IN (
        74695, -- 2502.10022 Cl+ and HCl+ in Reaction with H2 and Isotopologues: A Glance into H
        77163, -- 2405.18528 Interacting Streams of Cognitive Active Agents in a Three-Way   Inters
        100604, -- 2601.08136 Reverse Flow Matching: A Unified Framework for Online Reinforcement Le
        106949  -- 2408.06996 Blessing of Dimensionality for Approximating Sobolev Classes on Manifo
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM langevin_dynamics_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING langevin_dynamics_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING langevin_dynamics_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- gumbel-softmax: 63 links, 681 exclusions.
CREATE TEMP TABLE gumbel_softmax_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gumbel-softmax'
  AND p.id IN (
        493, -- 1611.01144 Categorical Reparameterization with Gumbel-Softmax
        2666, -- 1910.05453 vq-wav2vec: Self-Supervised Learning of Discrete Speech Representation
        3653, -- 2006.01895 Learning to Branch for Multi-Task Learning
        4600, -- 2011.11233 ROME: Robustifying Memory-Efficient NAS via Topology Disentanglement a
        4899, -- 2101.05442 Automated Model Design and Benchmarking of 3D Deep Learning Models for
        5528, -- 2104.09122 Probabilistic Mixture-of-Experts for Efficient Deep Reinforcement Lear
        6631, -- 2109.06474 Space Time Recurrent Memory Network
        8068, -- 2202.12986 Extracting Effective Subnetworks with Gumbel-Softmax
        14127, -- 2303.14470 Compacting Binary Neural Networks by Sparse Kernel Selection
        17753, -- 2306.14268 Adaptive Window Pruning for Efficient Local Motion Deblurring
        22511, -- 2310.16240 Mixture-of-Linguistic-Experts Adapters for Improving and Interpreting
        29925, -- 2404.03323 Sparse Concept Bottleneck Models: Gumbel Tricks in Contrastive Learnin
        37352, -- 2409.17481 MaskLLM: Learnable Semi-Structured Sparsity for Large Language Models
        38720, -- 2410.13643 Fine-Tuning Discrete Diffusion Models via Reward Optimization with App
        42089, -- 2412.17522 DiffusionAttacker: Diffusion-Driven Prompt Manipulation for LLM Jailbr
        46508, -- 2503.16660 When Less is Enough: Adaptive Token Reduction for Efficient Image   Re
        46554, -- 2503.17361 Gumbel-Softmax Flow Matching with Straight-Through Guidance for Contro
        48006, -- 2504.15270 An LMM for Efficient Video Understanding via Reinforced Compression of
        51748, -- 2507.05911 Differentiable Reward Optimization for LLM based TTS system
        54117, -- 2511.06411 SofT-GRPO: Surpassing Discrete-Token LLM Reinforcement Learning via
        54627, -- 2512.07834 Voxify3D: Pixel Art Meets Volumetric Rendering
        55040, -- 2512.22206 CosineGate: Semantic Dynamic Routing via Cosine Incompatibility in Res
        55285, -- 2601.07632 GeoMotionGPT: Geometry-Aligned Motion Understanding with Large Languag
        56584, -- 2603.07233 Retrieval-Augmented Generation for Predicting Cellular Responses to Ge
        57270, -- 2604.03266 Emergent Compositional Communication for Latent World Properties
        58032, -- 2604.18556 GSQ: Highly-Accurate Low-Precision Scalar Quantization for LLMs via Gu
        58048, -- 2604.17852 LLM-Codec: Neural Audio Codec Meets Language Model Objectives
        61962, -- 2601.19711 Differentiable Semantic ID for Generative Recommendation
        63953, -- 2512.08123 Universal Adversarial Suffixes Using Calibrated Gumbel-Softmax Relaxat
        65071, -- 2511.10190 Towards Leveraging Sequential Structure in Animal Vocalizations
        66525, -- 2510.10962 MC#: Mixture Compressor for Mixture-of-Experts Large Models
        70184, -- 2508.03587 Zero-Variance Gradients for Variational Autoencoders
        70198, -- 2508.03440 LLMs are Single-threaded Reasoners: Demystifying the Working Mechanism
        72141, -- 2506.07500 Mind the Gap: Removing the Discretization Gap in Differentiable Logic
        72173, -- 2506.07013 UNO: Unified Self-Supervised Monocular Odometry for Platform-Agnostic
        74882, -- 2502.03608 (GG) MoE vs. MLP on Tabular Data
        80914, -- 2101.08525 GhostSR: Learning Ghost Features for Efficient Image Super-Resolution
        81709, -- 1906.01784 Learning to Compose and Reason with Language Tree Structures for Visua
        81851, -- 1812.03299 Learning to Assemble Neural Module Tree Networks for Visual Grounding
        93637, -- 2604.18907 Gradient-Based Program Synthesis with Neurally Interpreted Languages
        94022, -- 2602.09001 DirMoE: Dirichlet-Routed Mixture of Experts
        96323, -- 2505.12693 TACOcc: Target-Adaptive Cross-Modal Fusion with Sequential Volume Rend
        97518, -- 2509.12594 The Better You Learn, the Smarter You Prune: Towards Efficient Vision-
        100321, -- 2602.03896 A hitchhiker's guide to Poisson gradient estimation
        101540, -- 2605.30873 Federated Variational Preference Alignment with Gumbel-Softmax Prior f
        101571, -- 2508.06588 Graph is a Natural Regularization: Revisiting Vector Quantization for
        101747, -- 2605.25551 Learning Permutation from Structure Without Supervision
        101844, -- 2602.12703 SWING: Unlocking Implicit Graph Representations for Graph Random Featu
        105416, -- 2407.21604 MicroMIL: Graph-Based Multiple Instance Learning for Context-Aware Dia
        106785, -- 2511.12079 Point Cloud Quantization Through Multimodal Prompting for 3D Understan
        107336, -- 2508.01562 Adaptive LiDAR Scanning: Harnessing Temporal Cues for Efficient 3D Obj
        107532, -- 2410.18396 Revisiting Differentiable Structure Learning: Inconsistency of L1 Pena
        107811, -- 2602.11213 Transferable Backdoor Attacks for Code Models via Sharpness-Aware Adve
        107877, -- 2512.13285 CausalCLIP: Causally-Informed Feature Disentanglement and Filtering fo
        108635, -- 2604.22979 Towards Causally Interpretable Wi-Fi CSI-Based Human Activity Recognit
        111117, -- external D-RAG: Differentiable Retrieval-Augmented Generation for Knowledge Gra
        116088, -- 2408.06747 Learn to Rectify the Bias of CLIP for Unsupervised Semantic Segmentati
        119778, -- 2312.14474 MonoLSS: Learnable Sample Selection For Monocular 3D Detection
        125130, -- 2609.30935 Estimating and Orthogonalizing Unknown Pre-training Gradients for Cont
        127802, -- 2605.08648 FLUX: Geometry-Aware Longitudinal Flow Matching with Mixture of Expert
        129200, -- external On Reparameterizing the Score Function
        131465, -- 2610.34886 ThinkBit: Search Codewords, Recalibrate Scales, Select by Reasoning
        132127  -- 1611.00712 The Concrete Distribution: A Continuous Relaxation of Discrete Random
  );

DELETE FROM paper_method_exclusions x
USING gumbel_softmax_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gumbel_softmax_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM gumbel_softmax_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE gumbel_softmax_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gumbel-softmax'
  AND p.id IN (
        640, -- 1704.00028 Improved Training of Wasserstein GANs
        745, -- 1706.02275 Multi-Agent Actor-Critic for Mixed Cooperative-Competitive Environment
        951, -- 1711.00937 Neural Discrete Representation Learning
        985, -- 1711.09485 SkipNet: Learning Dynamic Routing in Convolutional Networks
        1197, -- 1804.00104 Learning Disentangled Joint Continuous and Discrete Representations
        1386, -- 1807.03756 Latent Alignment and Variational Attention
        1400, -- 1807.08024 Explaining Image Classifiers by Counterfactual Generation
        1537, -- 1810.04020 A Comprehensive Survey of Deep Learning for Image Captioning
        1691, -- 1812.03443 FBNet: Hardware-Aware Efficient ConvNet Design via Differentiable Neur
        1738, -- 1901.01695 Vector representations of text data in deep learning
        1760, -- 1901.06283 Improving Sequence-to-Sequence Learning via Optimal Transport
        2015, -- 1904.08608 Learning to Collocate Neural Modules for Image Captioning
        2019, -- 1904.09013 Self-Supervised Audio-Visual Co-Segmentation
        2037, -- 1904.10921 Plug-in, Trainable Gate for Streamlining Arbitrary Neural Networks
        2128, -- 1905.09717 Network Pruning via Transformable Architecture Search
        2219, -- 1906.02691 An Introduction to Variational Autoencoders
        2387, -- 1908.00709 AutoML: A Survey of the State-of-the-Art
        2449, -- 1908.08926 Efficient Deep Neural Networks
        2466, -- 1908.10382 Feature Gradients: Scalable Feature Selection via Discrete Relaxation
        2680, -- 1910.06827 Learning Generalisable Omni-Scale Representations for Person Re-Identi
        2723, -- 1910.11424 Capacity, Bandwidth, and Compositionality in Emergent Language Learnin
        2772, -- 1911.02590 Optimizing Millions of Hyperparameters by Implicit Differentiation
        2899, -- 1912.02164 Plug and Play Language Models: A Simple Approach to Controlled Text Ge
        2996, -- 2001.04346 Asymmetrical Hierarchical Networks with Attentive Interactions for Int
        3026, -- 2001.09063 Towards Graph Representation Learning in Emergent Communication
        3065, -- 2002.01335 Structural Inductive Biases in Emergent Communication
        3108, -- 2002.07510 Sequential Latent Knowledge Selection for Knowledge-Grounded Dialogue
        3263, -- 2003.12694 Countering Language Drift with Seeded Iterated Learning
        3629, -- 2005.13510 Synthetic Observational Health Data with GANs: from slow adoption to a
        3643, -- 2006.00687 Phase-aware Single-stage Speech Denoising and Dereverberation with U-N
        3669, -- 2006.03656 AutoHAS: Efficient Hyperparameter and Architecture Search
        3773, -- 2006.11477 wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Repres
        3797, -- 2006.13979 Unsupervised Cross-lingual Representation Learning for Speech Recognit
        3834, -- 2006.16779 PLATO-2: Towards Building an Open-Domain Chatbot via Curriculum Learni
        3857, -- 2007.02066 Weight-dependent Gates for Network Pruning
        3913, -- 2007.09448 Towards Emergent Language Symbolic Semantic Segmentation and Model Int
        3915, -- 2007.09880 Mixture Representation Learning with Coupled Autoencoders
        3956, -- 2007.15353 Growing Efficient Deep Networks by Structured Continuous Sparsificatio
        3962, -- 2007.15796 AR-Net: Adaptive Frame Resolution for Efficient Action Recognition
        4054, -- 2008.09866 Symbolic Semantic Segmentation and Interpretation of COVID-19 Lung Inf
        4058, -- 2008.10292 Automated Search for Resource-Efficient Branched Multi-Task Networks
        4122, -- 2009.04264 Unsupervised Part Discovery by Unsupervised Disentanglement
        4126, -- 2009.04534 Pay Attention when Required
        4165, -- 2009.08115 A Probabilistic End-To-End Task-Oriented Dialog Model with Latent Beli
        4324, -- 2010.05113 Contrastive Representation Learning: A Framework and Review
        4406, -- 2010.11430 Self-training and Pre-training are Complementary for Speech Recognitio
        4680, -- 2012.03358 Select, Label, and Mix: Learning Discriminative Invariant Feature Repr
        4731, -- 2012.07280 Contrastive Learning with Adversarial Perturbations for Conditional Te
        4735, -- 2012.07463 Parameter-Efficient Transfer Learning with Diff Pruning
        4743, -- 2012.08117 Writing Polishment with Simile: Task, Dataset and A Neural Approach
        4756, -- 2012.09841 Taming Transformers for High-Resolution Image Synthesis
        4788, -- 2012.13577 LOREN: Logic-Regularized Reasoning for Interpretable Fact Verification
        4820, -- 2012.15562 UNKs Everywhere: Adapting Multilingual Language Models to New Scripts
        4913, -- 2101.07597 UniSpeech: Unified Speech Representation Learning with Labeled and Unl
        4929, -- 2101.09336 A Comprehensive Survey on Hardware-Aware Neural Architecture Search
        4961, -- 2101.12059 VX2TEXT: End-to-End Learning of Video-Based Text Generation From Multi
        5018, -- 2102.05775 AdaFuse: Adaptive Temporal Fusion Network for Efficient Action Recogni
        5081, -- 2102.11646 HardCoRe-NAS: Hard Constrained diffeRentiable Neural Architecture Sear
        5086, -- 2102.12092 Zero-Shot Text-to-Image Generation
        5088, -- 2102.12145 GDRNPP: A Geometry-guided and Fully Learning-based Object Pose Estimat
        5117, -- 2103.00742 Automated Machine Learning on Graphs: A Survey
        5133, -- 2103.01937 Neural Production Systems: Learning Rule-Governed Visual Dynamics
        5139, -- 2103.02164 Dynamic Gaussian Mixture based Deep Generative Model For Robust Foreca
        5161, -- 2103.04922 Deep Generative Modelling: A Comparative Review of VAEs, GANs, Normali
        5205, -- 2103.08541 Get Your Vitamin C! Robust Fact Verification with Contrastive Evidence
        5272, -- 2103.13630 A Survey of Quantization Methods for Efficient Neural Network Inferenc
        5301, -- 2103.15538 SUTD-TrafficQA: A Question Answering Benchmark and an Efficient Networ
        5359, -- 2104.01027 Robust wav2vec 2.0: Analyzing Domain Shift in Self-Supervised Pre-Trai
        5775, -- 2105.11084 Unsupervised Speech Recognition
        5795, -- 2105.13290 CogView: Mastering Text-to-Image Generation via Transformers
        5806, -- 2105.14103 An Attention Free Transformer
        5846, -- 2106.00967 Multiresolution Equivariant Graph Variational Autoencoder
        5905, -- 2106.03760 DSelect-k: Differentiable Selection in the Mixture of Experts with App
        5943, -- 2106.05319 Stein Latent Optimization for Generative Adversarial Networks
        5958, -- 2106.06038 Modeling Hierarchical Structures with Continuous Recursive Neural Netw
        6003, -- 2106.08254 BEiT: BERT Pre-Training of Image Transformers
        6143, -- 2106.15078 Don't Take It Literally: An Edit-Invariant Sequence Loss for Text Gene
        6232, -- 2107.05842 Motion Planning by Learning the Solution Manifold in Trajectory Optimi
        6253, -- 2107.07402 CLSRIL-23: Cross Lingual Speech Representations for Indic Languages
        6319, -- 2107.13132 Unsupervised Learning of Neurosymbolic Encoders
        6351, -- 2108.01265 Memorize, Factorize, or be Naïve: Learning Optimal Feature Interaction
        6506, -- 2108.12988 Learning Meta Representations for Agents in Multi-Agent Reinforcement
        6582, -- 2109.04325 Learning Opinion Summarizers by Selecting Informative Reviews
        6637, -- 2109.06777 PETGEN: Personalized Text Generation Attack on Deep Sequence Embedding
        6640, -- 2109.06870 Performance-Efficiency Trade-offs in Unsupervised Pre-training for Spe
        6653, -- 2109.07713 Transferable Persona-Grounded Dialogues via Grounded Minimal Edits
        6713, -- 2109.11680 Simple and Effective Zero-shot Cross-lingual Phoneme Recognition
        6878, -- 2110.05752 UniSpeech-SAT: Universal Speech Representation Learning with Speaker A
        6887, -- 2110.05999 DiscoDVT: Generating Long Text with Discourse-Aware Discrete Variation
        6898, -- 2110.06257 Causal Discovery from Conditionally Stationary Time Series
        7024, -- 2110.11405 Illiterate DALL-E Learns to Compose
        7076, -- 2110.14961 Roto-translated Local Coordinate Frames For Interacting Dynamical Syst
        7155, -- 2111.02552 Is Bang-Bang Control All You Need? Solving Continuous Control with Ber
        7241, -- 2111.09296 XLS-R: Self-supervised Cross-lingual Speech Representation Learning at
        7261, -- 2111.10007 FBNetV5: Neural Architecture Search for Multiple Tasks in One Run
        7314, -- 2111.13495 SQUID: Deep Feature In-Painting for Unsupervised Anomaly Detection
        7335, -- 2111.14819 Point-BERT: Pre-training 3D Point Cloud Transformers with Masked Point
        7367, -- 2112.00653 Variational Learning for Unsupervised Knowledge Grounded Dialogs
        7397, -- 2112.01799 Global Context with Discrete Diffusion in Vector Quantised Modelling f
        7454, -- 2112.04895 Latent Space Explanation by Intervention
        7552, -- 2112.09245 Automated Deep Learning: Neural Architecture Search Is Not the End
        7607, -- 2112.13592 Multimodal Image Synthesis and Editing: The Generative AI Era
        7614, -- 2112.14397 EvoMoE: An Evolutional Mixture-of-Experts Training Framework via Dense
        7622, -- 2112.15139 Finding the Task-Optimal Low-Bit Sub-Distribution in Deep Neural Netwo
        7753, -- 2201.09522 Accelerated Intravascular Ultrasound Imaging using Deep Reinforcement
        7759, -- 2201.09830 Learning Graph Augmentations to Learn Graph Representations
        8001, -- 2202.08791 cosFormer: Rethinking Softmax in Attention
        8021, -- 2202.09914 SOInter: A Novel Deep Energy Based Interpretation Method for Explainin
        8036, -- 2202.11094 GroupViT: Semantic Segmentation Emerges from Text Supervision
        8096, -- 2202.13914 Combining Modular Skills in Multitask Learning
        8142, -- 2203.02336 Differentiable Causal Discovery Under Latent Interventions
        8160, -- 2203.03463 Hierarchical Sketch Induction for Paraphrase Generation
        8210, -- 2203.05843 An Interpretable Neuro-Symbolic Reasoning Framework for Task-Oriented
        8279, -- 2203.08243 Unified Visual Transformer Compression
        8357, -- 2203.10897 Unified Multivariate Gaussian Mixture for Efficient Neural Image Compr
        8409, -- 2203.13131 Make-A-Scene: Scene-Based Text-to-Image Generation with Human Priors
        8414, -- 2203.13344 Linking Emergent and Natural Languages via Corpus Transfer
        8424, -- 2203.13920 Canary Extraction in Natural Language Understanding Models
        8425, -- 2203.13922 AutoML for Deep Recommender Systems: A Survey
        8502, -- 2203.16708 Task Adaptive Parameter Sharing for Multi-Task Learning
        8674, -- 2204.05419 A Wav2vec2-Based Experimental Study on Self-Supervised Learning Method
        8894, -- 2205.00305 AdapterBias: Parameter-efficient Token-dependent Representation Shift
        9099, -- 2205.10643 Self-Supervised Speech Representation Learning: A Review
        9189, -- 2205.12701 Eliciting and Understanding Cross-Task Skills with Task-Level Mixture-
        9348, -- 2206.01665 BaCaDI: Bayesian Causal Discovery with Unknown Interventions
        9352, -- 2206.01720 Revisiting the "Video" in Video-Language Understanding
        9405, -- 2206.03597 Meta-Learning Parameterized Skills
        9451, -- 2206.05922 From Perception to Programs: Regularize, Overparameterize, and Amortiz
        9625, -- 2206.13654 Wav2Vec-Aug: Improved self-supervised training with limited data
        9727, -- 2207.04044 kMaX-DeepLab: k-means Mask Transformer
        10046, -- 2208.07097 Efficient Task-Oriented Dialogue Systems with Response Selection as an
        10066, -- 2208.08080 Multimodal Lecture Presentations Dataset: Understanding Multimodality
        10535, -- 2210.01338 Learning to Collocate Visual-Linguistic Neural Modules for Image Capti
        10782, -- 2210.07011 Variational Graph Generator for Multi-View Graph Clustering
        10870, -- 2210.09461 Token Merging: Your ViT But Faster
        10897, -- 2210.10340 The Devil in Linear Transformer
        10904, -- 2210.10592 DyTed: Disentangled Representation Learning for Discrete-time Dynamic
        10973, -- 2210.12461 Towards Efficient Dialogue Pre-training with Transferable and Interpre
        11012, -- 2210.12977 Language-free Training for Zero-shot Video Grounding
        11027, -- 2210.13438 High Fidelity Neural Audio Compression
        11050, -- 2210.13942 Entity Divider with Language Grounding in Multi-Agent Reinforcement Le
        11100, -- 2210.15458 Arithmetic Sampling: Parallel Diverse Decoding for Large Language Mode
        11251, -- 2211.03831 Multi-Head Adapter Routing for Cross-Task Generalization
        11413, -- 2211.09761 Efficient Transformers with Dynamic Token Pooling
        11488, -- 2211.11446 SMAUG: Sparse Masked Autoencoder for Efficient Video-Language Pre-trai
        11602, -- 2211.13854 ComCLIP: Training-Free Compositional Image and Text Matching
        11644, -- 2211.14813 SegCLIP: Patch Aggregation with Learnable Centers for Open-Vocabulary
        11681, -- 2211.15897 Learning Antidote Data to Individual Unfairness
        11758, -- 2212.00785 Learning to Generate Text-grounded Mask for Open-world Semantic Segmen
        11890, -- 2212.04761 Leveraging Spatio-Temporal Dependency for Skeleton-Based Action Recogn
        11943, -- 2212.06458 HS-Diffusion: Semantic-Mixing Diffusion for Head Swapping
        12149, -- 2212.10547 Semantically-informed Hierarchical Event Modeling
        12227, -- 2212.13185 Generalized Differentiable RANSAC
        12276, -- 2301.00557 Learning to Maximize Mutual Information for Dynamic Feature Selection
        12343, -- 2301.03046 STPrivacy: Spatio-Temporal Privacy-Preserving Action Recognition
        12532, -- 2301.10909 Optimizing Feature Set for Click-Through Rate Prediction
        12840, -- 2302.02241 Feature Representation Learning for Click-through Rate Prediction: A R
        13040, -- 2302.05917 Vector Quantized Wasserstein Auto-Encoder
        13043, -- 2302.05981 MarioGPT: Open-Ended Text2Level Generation through Large Language Mode
        13184, -- 2302.09368 Natural Language-conditioned Reinforcement Learning with Inside-out Ta
        13226, -- 2302.10607 Differentiable Multi-Target Causal Bayesian Experimental Design
        13230, -- 2302.10798 Learning a Consensus Sub-Network with Polarization Regularization and
        13255, -- 2302.11529 Modular Deep Learning
        13412, -- 2303.00566 Structured Pruning for Deep Convolutional Neural Networks: A survey
        13517, -- 2303.03284 The Wasserstein Believer: Learning Belief Updates for Partially Observ
        13565, -- 2303.04381 Automatically Auditing Large Language Models via Discrete Optimization
        13572, -- 2303.04664 Centroid-centered Modeling for Efficient Vision Transformer Pre-traini
        13597, -- 2303.05078 Efficient Transformer-based 3D Object Detection with Dynamic Token Hal
        13731, -- 2303.07624 I3D: Transformer architectures with input-dependent dynamic depth for
        13884, -- 2303.10446 Content Adaptive Front End For Audio Classification
        13918, -- 2303.11114 SeiT: Storage-Efficient Vision Training with Tokens Using 1% of Pixel
        14004, -- 2303.12370 Weakly Supervised Video Representation Learning with Unaligned Text fo
        14132, -- 2303.14526 Selective Structured State-Spaces for Long-Form Video Understanding
        14494, -- 2304.02841 Learning Neural Eigenfunctions for Unsupervised Semantic Segmentation
        14592, -- 2304.04820 Binary Latent Diffusion
        15062, -- 2304.14997 Towards Automated Circuit Discovery for Mechanistic Interpretability
        15136, -- 2305.01520 Conditional Graph Information Bottleneck for Molecular Relational Lear
        15177, -- 2305.02187 CLUSTSEG: Clustering for Universal Segmentation
        15344, -- 2305.04934 Generative Pretrained Autoregressive Transformer Graph Neural Network
        15417, -- 2305.06176 Fine-tuning Language Models with Generative Adversarial Reward Modelli
        15576, -- 2305.08842 Straightening Out the Straight-Through Estimator: Overcoming Optimizat
        15777, -- 2305.11603 Attributable and Scalable Opinion Summarization
        15787, -- 2305.11718 Towards Accurate Image Coding: Improved Autoregressive Image Generatio
        15958, -- 2305.13516 Scaling Speech Technology to 1,000+ Languages
        16193, -- 2305.15033 SmartTrim: Adaptive Tokens and Attention Pruning for Efficient Vision-
        16378, -- 2305.16958 MixCE: Training Autoregressive Language Models by Mixing Forward and R
        16410, -- 2305.17235 COMCAT: Towards Efficient Compression and Customization of Attention-B
        16654, -- 2305.19744 Neural Markov Jump Processes
        16680, -- 2305.19999 Beam Tree Recursive Cells
        16770, -- 2306.00751 Differentiable Tree Operations Promote Compositional Generalization
        16820, -- 2306.01128 Learning Transformer Programs
        16897, -- 2306.01920 Context-Aware Bayesian Network Actor-Critic Methods for Cooperative Mu
        17050, -- 2306.03745 Soft Merging of Experts with Adaptive Routing
        17150, -- 2306.05067 Improving Visual Prompt Tuning for Self-supervised Vision Transformers
        17441, -- 2306.08757 InfoDiffusion: Representation Learning Using Information Maximizing Di
        17576, -- 2306.10606 Decongestion by Representation: Learning to Improve Economic Welfare i
        17580, -- 2306.10715 Maximum Entropy Heterogeneous-Agent Reinforcement Learning
        17604, -- 2306.11197 Sparse Modular Activation for Efficient Sequence Modeling
        17759, -- 2306.14393 Constraint-aware and Ranking-distilled Token Pruning for Efficient Tra
        17978, -- 2307.01226 vONTSS: vMF based semi-supervised neural topic modeling with optimal t
        17994, -- 2307.01715 Align With Purpose: Optimize Desired Properties in CTC Models with a G
        18095, -- 2307.03838 RADAR: Robust AI-Text Detection via Adversarial Learning
        18116, -- 2307.04246 Convex Decomposition of Indoor Scenes
        18302, -- 2307.08300 ShiftNAS: Improving One-shot NAS via Probability Shift
        18354, -- 2307.09065 Learning Adaptive Neighborhoods for Graph Neural Networks
        18378, -- 2307.09437 Grounded Object Centric Learning
        18569, -- 2307.12577 PRIOR: Prototype Representation Joint Learning from Medical Images and
        18913, -- 2308.02080 Causality Guided Disentanglement for Cross-Platform Hate Speech Detect
        18952, -- 2308.02840 Learning Unified Decompositional and Compositional NeRF for Editable N
        18972, -- 2308.03188 Automatically Correcting Large Language Models: Surveying the landscap
        18993, -- 2308.03409 DiT: Efficient Vision Transformers with Dynamic Token Routing
        19066, -- 2308.04657 Which Tokens to Use? Investigating Token Reduction in Vision Transform
        19393, -- 2308.09322 Audio-Visual Glance Network for Efficient Video Recognition
        19516, -- 2308.10315 Improving Adversarial Robustness of Masked Autoencoders via Test-time
        19753, -- 2308.12963 MapPrior: Bird's-Eye View Map Layout Estimation with Generative Models
        19868, -- 2308.14616 VoroMesh: Learning Watertight Surface Meshes with Voronoi Diagrams
        20005, -- 2309.00233 Object-Centric Multiple Object Tracking
        20023, -- 2309.00723 Contextual Biasing of Named-Entities with Large Language Models
        20135, -- 2309.02527 A skeletonization algorithm for gradient-based optimization
        20176, -- 2309.03473 Temporal Collection and Distribution for Referring Video Object Segmen
        20279, -- 2309.05281 Class-Incremental Grouping Network for Continual Audio-Visual Learning
        20367, -- 2309.06978 Differentiable JPEG: The Devil is in the Details
        20663, -- 2309.11132 Contrastive Pseudo Learning for Open-World DeepFake Attribution
        20702, -- 2309.11661 Neural Image Compression Using Masked Sparse Visual Representation
        20820, -- 2309.13235 M$^3$CS: Multi-Target Masked Point Modeling with Learnable Codebook an
        20886, -- 2309.14174 Only 5\% Attention Is All You Need: Efficient Long-range Document-leve
        20989, -- 2309.15848 SHACIRA: Scalable HAsh-grid Compression for Implicit Neural Representa
        21064, -- 2309.16984 Consistency Models as a Rich and Efficient Policy Class for Reinforcem
        21098, -- 2309.17343 Neural Lithography: Close the Design-to-Manufacturing Gap in Computati
        21190, -- 2310.00811 Sparse Backpropagation for MoE Training
        21232, -- 2310.01267 Cooperative Graph Neural Networks
        21277, -- 2310.01647 Equivariant Adaptation of Large Pretrained Models
        21330, -- 2310.02156 Probabilistically Rewired Message-Passing Neural Networks
        21352, -- 2310.02409 Dodo: Dynamic Contextual Compression for Decoder-only LMs
        21413, -- 2310.03084 Discovering Knowledge-Critical Subnetworks in Pretrained Language Mode
        21472, -- 2310.03734 Leveraging Unpaired Data for Vision-Language Generative Models via Cyc
        21509, -- 2310.04407 Policy-Gradient Training of Language Models for Ranking
        21614, -- 2310.05400 Efficient-VQGAN: Towards High-Resolution Image Generation with Efficie
        21730, -- 2310.06763 FABind: Fast and Accurate Protein-Ligand Binding
        21803, -- 2310.07588 Accurate Use of Label Dependency in Multi-Label Text Classification Th
        22213, -- 2310.12690 Neurosymbolic Grounding for Compositional World Models
        22434, -- 2310.15263 One-hot Generalized Linear Model for Switching Brain State Discovery
        22467, -- 2310.15654 A Survey on Detection of LLMs-Generated Content
        22488, -- 2310.15978 Graph Deep Learning for Time Series Forecasting
        22579, -- 2310.16986 Probabilistic Integral Circuits
        22686, -- 2310.18384 MicroNAS: Memory and Latency Constrained Hardware-Aware Neural Archite
        22715, -- 2310.18882 Differentiable Learning of Generalized Structured Matrices for Efficie
        22790, -- 2310.20082 Efficient Subgraph GNNs by Learning Effective Selection Policies
        22820, -- 2310.20679 Latent Field Discovery In Interacting Dynamical Systems With Neural Fi
        22916, -- 2311.01460 Implicit Chain of Thought Reasoning via Knowledge Distillation
        23031, -- 2311.04056 Multi-View Causal Representation Learning with Partial Observability
        23032, -- 2311.04066 Can CLIP Help Sound Source Localization?
        23046, -- 2311.04193 Selective Visual Representations Improve Convergence and Generalizatio
        23076, -- 2311.04453 Lewis's Signaling Game as beta-VAE For Natural Word Lengths and Segmen
        23255, -- 2311.07587 Frontier Language Models are not Robust to Adversarial Arithmetic, or
        23681, -- 2311.13627 Vamos: Versatile Action Models for Video Understanding
        23928, -- 2311.17135 TLControl: Trajectory and Language Control for Human Motion Synthesis
        24341, -- 2312.03248 Customizable Combination of Parameter-Efficient Modules for Multi-Task
        24535, -- 2312.05479 Exploring Sparsity in Graph Transformers
        24582, -- 2312.06173 Concrete Subspace Learning based Interference Elimination for Multi-ta
        24701, -- 2312.07551 Language Model Alignment with Elastic Reset
        24713, -- 2312.07886 Modality Plug-and-Play: Elastic Modality Adaptation in Multimodal LLMs
        24737, -- 2312.08367 ViLA: Efficient Video-Language Alignment for Video Question Answering
        24867, -- 2312.10193 Adaptive Computation Modules: Granular Conditional Computation For Eff
        25028, -- 2312.12791 Model-Based Control with Sparse Neural Dynamics
        25782, -- 2401.06829 Cross-Attention Watermarking of Large Language Models
        25978, -- 2401.09786 Adaptive Self-training Framework for Fine-grained Scene Graph Generati
        26002, -- 2401.10189 Chem-FINESE: Validating Fine-Grained Few-shot Entity Extraction throug
        26208, -- 2401.13051 PA-SAM: Prompt Adapter SAM for High-Quality Image Segmentation
        26457, -- 2401.16656 Gradient-Based Language Model Red Teaming
        26577, -- 2402.00637 Fisheye Camera and Ultrasonic Sensor Fusion For Near-Field Obstacle Pe
        26687, -- 2402.01702 Fluent dreaming for language models
        26980, -- 2402.04717 InstructScene: Instruction-Driven 3D Indoor Scene Synthesis with Seman
        27170, -- 2402.07220 KVQ: Kwai Video Quality Assessment for Short-form Videos
        27253, -- 2402.08345 Conditional Information Gain Trellis
        27401, -- 2402.10434 Parametric Augmentation for Time Series Contrastive Learning
        27449, -- 2402.10896 PaLM2-VAdapter: Progressively Aligned Language Model Makes a Strong Vi
        27655, -- 2402.12874 Skill or Luck? Return Decomposition via Advantage Functions
        27773, -- 2402.14160 Recursive Speculative Decoding: Accelerating LLM Inference via Samplin
        28238, -- 2403.00435 Hierarchical Indexing for Retrieval-Augmented Opinion Summarization
        28745, -- 2403.07816 Branch-Train-MiX: Mixing Expert LLMs into a Mixture-of-Experts LLM
        28875, -- 2403.09629 Quiet-STaR: Language Models Can Teach Themselves to Think Before Speak
        29038, -- 2403.11808 Dynamic Tuning Towards Parameter and Inference Efficiency for ViT Adap
        29095, -- 2403.12459 Non-negative Contrastive Learning
        29159, -- 2403.13179 Predictive, scalable and interpretable knowledge tracing on structured
        29486, -- 2403.17814 D-PAD: Deep-Shallow Multi-Frequency Patterns Disentangling for Time Se
        29716, -- 2404.00579 A Review of Modern Recommender Systems Using Generative Models (Gen-Re
        29799, -- 2404.01340 From Similarity to Superiority: Channel Clustering for Time Series For
        30555, -- 2404.12493 EnriCo: Enriched Representation and Globally Constrained Inference for
        30637, -- 2404.13968 Protecting Your LLMs with Information Bottleneck
        30719, -- 2404.15501 Killkan: The Automatic Speech Recognition Dataset for Kichwa with Morp
        30729, -- 2404.15677 CharacterFactory: Sampling Consistent Characters with GANs for Diffusi
        31315, -- 2405.09308 TimeX++: Learning Time-Series Explanations with Information Bottleneck
        32031, -- 2405.19677 Large Language Model Watermark Stealing With Mixed Integer Programming
        32464, -- 2406.04344 Verbalized Machine Learning: Revisiting Machine Learning with Language
        32550, -- 2406.05551 Autoregressive Diffusion Transformer for Text-to-Speech Synthesis
        32620, -- 2406.06367 MVGamba: Unify 3D Content Generation as State Space Sequence Modeling
        32752, -- 2406.07812 To be Continuous, or to be Discrete, Those are Bits of Questions
        32909, -- 2406.09459 Ad Auctions for LLMs via Retrieval Augmented Generation
        33197, -- 2406.12042 Not All Prompts Are Made Equal: Prompt-based Pruning of Text-to-Image
        33860, -- 2406.20078 GM-DF: Generalized Multi-Scenario Deepfake Detection
        34203, -- 2407.04538 PDiscoFormer: Relaxing Part Discovery Constraints with Vision Transfor
        34483, -- 2407.08415 Parallelizing Autoregressive Generation with Variational State Space M
        34523, -- 2407.08818 MAGNET: Improving the Multilingual Fairness of Language Models with Ad
        35002, -- 2407.14937 Operationalizing a Threat Model for Red-Teaming Large Language Models
        35262, -- 2407.19342 Parameter-Efficient Fine-Tuning via Circular Convolution
        35322, -- 2407.20485 A2SF: Accumulative Attention Scoring with Forgetting Factor for Token
        35330, -- 2407.20595 Harvesting Textual and Structured Data from the HAL Publication Reposi
        35741, -- 2408.05939 UniPortrait: A Unified Framework for Identity-Preserving Single- and M
        35754, -- 2408.06261 Open-Source Molecular Processing Pipeline for Generating Molecules
        35892, -- 2408.08585 OptDist: Learning Optimal Distribution for Customer Lifetime Value Pre
        36123, -- 2408.12185 Rank and Align: Towards Effective Source-free Graph Domain Adaptation
        36588, -- 2409.02908 Masked Diffusion Models are Secretly Time-Agnostic Masked Models and E
        36912, -- 2409.09891 Acquiring Pronunciation Knowledge from Transcribed Speech Audio via Mu
        37030, -- 2409.11923 Agglomerative Token Clustering
        37228, -- 2409.15278 PixWizard: Versatile Image-to-Image Visual Assistant with Open-Languag
        37323, -- 2409.17027 Counterfactual Token Generation in Large Language Models
        37736, -- 2410.02231 SEAL: SEmantic-Augmented Imitation Learning via Language Model
        37804, -- 2410.02745 AVG-LLaVA: A Large Multimodal Model with Adaptive Visual Granularity
        37930, -- 2410.04074 On Eliciting Syntax from Language Models via Hashing
        38028, -- 2410.05318 Improving LLM Reasoning through Scaling Inference Computation with Col
        38119, -- 2410.06424 Restructuring Vector Quantization with the Rotation Trick
        38279, -- 2410.08207 DICE: Discrete Inversion Enabling Controllable Editing for Multinomial
        38889, -- 2410.15618 Erasing Undesirable Concepts in Diffusion Models with Adversarial Pres
        38922, -- 2410.16124 MNIST-Nd: a set of naturalistic datasets to benchmark clustering acros
        39114, -- 2410.18572 Taipan: Efficient and Expressive State Space Language Models with Sele
        39423, -- 2410.23608 Context-Aware Token Selection and Packing for Enhanced Vision Transfor
        39496, -- 2411.00382 Communication Learning in Multi-Agent Systems from Graph Modeling Pers
        39572, -- 2411.01593 High-Fidelity Virtual Try-on with Large-Scale Unpaired Learning
        39588, -- 2411.02038 Addressing Representation Collapse in Vector Quantized Models with One
        39885, -- 2411.07180 Gumbel Counterfactual Generation From Language Models
        40342, -- 2411.15269 MambaIRv2: Attentive State Space Restoration
        40346, -- 2411.15370 Deep Policy Gradient Methods Without Batch Updates, Target Networks, o
        40452, -- 2411.16720 Importance-Based Token Merging for Efficient Image and Video Generatio
        40693, -- 2411.19556 Differentiable Causal Discovery For Latent Hierarchical Causal Models
        40698, -- 2411.19628 Accelerating Multimodal Large Language Models via Dynamic Visual-Token
        40795, -- 2412.00876 Dynamic-LLaVA: Efficient Multimodal Large Language Models via Dynamic
        40815, -- 2412.01199 TinyFusion: Diffusion Transformers Learned Shallow
        41664, -- 2412.11863 GeoX: Geometric Problem Solving Through Unified Formalized Vision-Lang
        41872, -- 2412.14426 All-in-One Tuning and Structural Pruning for Domain-Specific LLMs
        42157, -- 2412.18275 Learning to engineer protein flexibility
        42913, -- 2501.09503 AnyStory: Towards Unified Single and Multiple Subject Personalization
        42965, -- 2501.10105 Universal Actions for Enhanced Embodied Foundation Models
        43136, -- 2501.13428 Softplus Attention with Re-weighting Boosts Length Extrapolation in La
        43249, -- 2501.15316 ToMoE: Converting Dense Large Language Models to Mixture-of-Experts th
        43277, -- 2501.15638 A Comprehensive Survey on Self-Interpretable Neural Networks
        43296, -- 2501.16142 Towards General-Purpose Model-Free Reinforcement Learning
        43402, -- 2501.18154 Mixed-Precision Graph Neural Quantization for Low Bit Large Language M
        43564, -- 2502.01384 Fine-Tuning Discrete Diffusion Models with Policy Gradient Methods
        43891, -- 2502.05874 MMGDreamer: Mixed-Modality Graph for Geometry-Controllable 3D Indoor S
        44538, -- 2502.13251 Neural Attention Search
        44611, -- 2502.13991 Learning to Discover Regulatory Elements for Gene Expression Predictio
        45407, -- 2503.02379 Teaching Metric Distance to Autoregressive Multimodal Foundational Mod
        45495, -- 2503.03651 DoraCycle: Domain-Oriented Adaptation of Unified Generative Model in M
        45765, -- 2503.07154 Ideas in Inference-time Scaling can Benefit Generative Pre-training Al
        45838, -- 2503.08026 In Prospect and Retrospect: Reflective Memory Management for Long-term
        46001, -- 2503.09790 Constrained Language Generation with Discrete Diffusion Models
        46110, -- 2503.10905 Learning to Inference Adaptively for Multimodal Large Language Models
        48167, -- 2504.19062 Versatile Framework for Song Generation with Prompt-based Control
        48223, -- 2504.20630 ISDrama: Immersive Spatial Drama Generation through Multimodal Prompti
        48498, -- 2505.04622 PrimitiveAnything: Human-Crafted 3D Primitive Assembly Generation with
        48762, -- 2505.10202 VQ-Logits: Compressing the Output Bottleneck of Large Language Models
        48922, -- 2505.12079 SepPrune: Structured Pruning for Efficient Deep Speech Separation
        49691, -- 2505.19147 Shifting AI Efficiency From Model-Centric to Data-Centric Compression
        50173, -- 2505.23844 Enabling Flexible Multi-LLM Integration for Scalable Knowledge Aggrega
        50311, -- 2506.00413 Accelerating Diffusion LLMs via Adaptive Parallel Decoding
        50586, -- 2506.04462 Watermarking Degrades Alignment in Language Models: Analysis and Mitig
        50603, -- 2506.04708 Accelerated Test-Time Scaling with Model-Free Speculative Sampling
        51374, -- 2506.18623 Efficient and Generalizable Speaker Diarization via Structured Pruning
        51794, -- 2507.07006 GNN-ViTCap: GNN-Enhanced Multiple Instance Learning with Vision Transf
        51800, -- 2507.07104 Vision-Language-Vision Auto-Encoder: Scalable Knowledge Distillation
        51820, -- 2507.07955 Dynamic Chunking for End-to-End Hierarchical Sequence Modeling
        52391, -- 2508.11548 Copyright Protection for Large Language Models: A Survey of Methods,
        53269, -- 2510.04162 Drax: Speech Recognition with Discrete Flow Matching
        55290, -- 2601.09088 Distribution-Aligned Sequence Distillation for Superior Long-CoT Reaso
        55796, -- 2602.05000 EntRGi: Entropy Aware Reward Guidance for Diffusion Language Models
        55939, -- 2602.07090 Concept-Aware Privacy Mechanisms for Defending Embedding Inversion Att
        56082, -- 2602.10585 Neural Additive Experts: Context-Gated Experts for Controllable Model
        56283, -- 2602.21185 The Diffusion Duality, Chapter II: Ψ-Samplers and Efficient Curriculum
        56480, -- 2603.03282 MIBURI: Towards Expressive Interactive Gesture Synthesis
        56530, -- 2603.04948 nabla-Reasoner: LLM Reasoning via Test-Time Gradient Descent in Latent
        56658, -- 2603.12267 EVATok: Adaptive Length Video Tokenization for Efficient Visual Autore
        56798, -- 2603.15854 FlashSampling: Fast and Memory-Efficient Exact Sampling
        57350, -- 2604.07394 Flux Attention: Context-Aware Hybrid Attention for Efficient LLMs Infe
        57520, -- 2604.14268 HY-World 2.0: A Multi-Modal World Model for Reconstructing, Generating
        57545, -- 2211.16780 An Optimal Transport-driven Approach for Cultivating Latent Space in O
        58545, -- 2603.21852 All elementary functions from a single binary operator
        58937, -- 2603.28796 GaloisSAT: Differentiable Boolean Satisfiability Solving via Finite Fi
        59043, -- 2509.26469 DiVeQ: Differentiable Vector Quantization Using the Reparameterization
        59363, -- 2603.14785 SkipOPU: An FPGA-based Overlay Processor for Large Language Models wit
        59611, -- 2603.10225 Rethinking the Harmonic Loss via Non-Euclidean Distance Layers
        60398, -- 2602.20427 GauS: Differentiable Scheduling Optimization via Gaussian Reparameteri
        60541, -- 2603.00104 Alpha-RF: Automated RF-Filter-Circuit Design with Neural Simulator and
        61161, -- 2602.05605 Shiva-DiT: Residual-Based Differentiable Top-k Selection for Efficient
        61807, -- 2601.21768 Zonkey: A Hierarchical Diffusion Language Model with Differentiable To
        62365, -- 2601.12719 S2DiT: Sandwich Diffusion Transformer for Mobile Streaming Video Gener
        62514, -- 2601.09269 RISER: Orchestrating Latent Reasoning Skills for Adaptive Activation S
        62727, -- 2601.05770 Weights to Code: Extracting Interpretable Algorithms from the Discrete
        63307, -- 2512.21683 Contrastive Graph Modeling for Cross-Domain Few-Shot Medical Image Seg
        63518, -- 2512.17452 KV Admission: Learning What to Write for Efficient Long-Context Infere
        65202, -- 2511.08133 OTSNet: A Neurocognitive-Inspired Observation-Thinking-Spelling Pipeli
        65667, -- 2510.25674 Mechanistic Interpretability of RNNs emulating Hidden Markov Models
        65753, -- 2510.24105 Enhancing Pre-trained Representation Classifiability can Boost its   I
        65859, -- 2510.22450 SmartMixed: A Two-Phase Training Strategy for Adaptive Activation Func
        66134, -- 2510.18080 MEG-GPT: A transformer-based foundation model for magnetoencephalograp
        66574, -- 2510.10693 High-Dimensional Learning Dynamics of Quantized Models with Straight-T
        66653, -- 2510.09175 Beyond Pairwise Connections: Extracting High-Order Functional Brain Ne
        66705, -- 2510.08470 Looking to Learn: Token-wise Dynamic Gating for Low-Resource   Vision-
        67088, -- 2510.02291 Test-Time Anchoring for Discrete Diffusion Posterior Sampling
        67334, -- 2509.25918 Bringing Emerging Architectures to Sequence Labeling in NLP
        67588, -- 2509.23410 PATCH: Learnable Tile-level Hybrid Sparsity for LLMs
        67793, -- 2509.21164 Mixture of Thoughts: Learning to Aggregate What Experts Think, Not Jus
        68358, -- 2509.12179 Co-Alignment: Rethinking Alignment as Bidirectional Human-AI Cognitive
        68379, -- 2509.11815 SpecVLM: Fast Speculative Decoding in Vision-Language Models
        68672, -- 2509.05656 OptiProxy-NAS: Optimization Proxy based End-to-End Neural Architecture
        68759, -- 2509.03733 Differentiable Entropy Regularization for Geometry and Neural Networks
        69101, -- 2508.19754 FastAvatar: Towards Unified Fast High-Fidelity 3D Avatar Reconstructio
        69248, -- 2508.17434 TinySR: Pruning Diffusion for Real-World Image Super-Resolution
        69663, -- 2508.10684 MDNS: Masked Diffusion Neural Sampler via Stochastic Optimal Control
        69840, -- 2508.08404 Generating Query-Relevant Document Summaries via Reinforcement Learnin
        70124, -- 2508.04369 TSPO: Temporal Sampling Policy Optimization for Long-form Video Langua
        70653, -- 2507.20498 Mixture of Length and Pruning Experts for Knowledge Graphs Reasoning
        70667, -- 2507.20327 TADT-CSA: Temporal Advantage Decision Transformer with Contrastive Sta
        70929, -- 2507.22920 Discrete Tokenization for Multimodal LLMs: A Comprehensive Survey
        70998, -- 2507.14468 BioGraphFusion: Graph Knowledge Embedding for Biological Completion an
        71121, -- 2507.11579 SketchDNN: Joint Continuous-Discrete Diffusion for CAD Sketch Generati
        71692, -- 2506.22139 Q-Frame: Query-aware Frame Selection and Multi-Resolution Adaptation f
        72189, -- 2506.06446 Tokenization Multiplicity Leads to Arbitrary Price Variation in LLM-as
        72271, -- 2506.04174 FlexGS: Train Once, Deploy Everywhere with Many-in-One Flexible 3D   G
        72951, -- 2505.13737 Causal Head Gating: A Framework for Interpreting Roles of Attention He
        73558, -- 2504.08966 PACT: Pruning and Clustering-Based Token Reduction for Faster Visual L
        74360, -- 2503.00831 Waste Not, Want Not; Recycled Gumbel Noise Improves Consistency
        74615, -- 2502.12751 Architect of the Bits World: Masked Autoregressive Modeling for Circui
        74947, -- 2502.01416 Categorical Schrödinger Bridge Matching
        75027, -- 2502.00075 BTS: Harmonizing Specialized Experts into a Generalist LLM
        75127, -- 2501.12040 Select2Drive: Pragmatic Communications for Real-Time Collaborative   A
        75484, -- 2412.10275 TIV-Diffusion: Towards Object-Centric Movement for Text-driven Image t
        75493, -- 2412.09758 Toward Foundation Model for Multivariate Wearable Sensing of Physiolog
        75671, -- 2412.10381 Supervised Learning-enhanced Multi-Group Actor Critic for Live Stream
        76039, -- 2410.12261 CATCH: Channel-Aware multivariate Time Series Anomaly Detection via
        76087, -- 2410.08631 CryoFM: A Flow-based Foundation Model for Cryo-EM Densities
        76244, -- 2409.19660 All-in-One Image Coding for Joint Human-Machine Vision with Multi-Path
        76252, -- 2409.19258 VecLSTM: Trajectory Data Processing and Management for Activity Recogn
        76575, -- 2408.05822 Sampling Foundational Transformer: A Theoretical Perspective
        76697, -- 2407.16424 ESOD: Efficient Small Object Detection on High-Resolution Images
        76985, -- 2406.11037 NAST: Noise Aware Speech Tokenization for Speech Language Models
        77534, -- 2404.00532 LLMs are Good Action Recognizers
        77640, -- 2403.08654 An Efficient End-to-End Approach to Noise Invariant Speech Features vi
        78379, -- 2310.09382 LL-VQ-VAE: Learnable Lattice Vector-Quantization For Efficient Represe
        78528, -- 2309.07967 iHAS: Instance-wise Hierarchical Architecture Search for Deep Learning
        78648, -- 2308.16160 Occ^2Net: Robust Image Matching Based on 3D Occupancy Estimation for
        78836, -- 2306.17525 MeLM, a generative pretrained language modeling framework that solves
        78931, -- 2306.02109 Encoding Time-Series Explanations through Self-Supervised Model Behavi
        79104, -- 2304.12400 Generative Discovery of Novel Chemical Designs using Diffusion Modelin
        79111, -- 2304.10716 Joint Token Pruning and Squeezing Towards More Aggressive Compression
        79125, -- 2304.08612 Bridging Discrete and Backpropagation: Straight-Through and Beyond
        79468, -- 2212.12393 A-NeSI: A Scalable Approximate Method for Probabilistic Neurosymbolic
        79500, -- 2212.05178 State-Regularized Recurrent Neural Networks to Extract Automata and Ex
        79707, -- 2209.15179 Physical Adversarial Attack meets Computer Vision: A Decade Survey
        79714, -- 2209.13959 Dynamic MDETR: A Dynamic Multimodal Transformer Decoder for Visual Gro
        79743, -- 2209.06589 Towards Better Generalization with Flexible Representation of   Multi-
        79786, -- 2208.07458 Learnable Filters for Geometric Scattering Modules
        79891, -- 2201.12987 Interpretable and Generalizable Graph Learning via Stochastic Attentio
        79965, -- 2205.11179 Online Hybrid Lightweight Representations Learning: Its Application to
        80147, -- 2203.05789 FLAG: Flow-based 3D Avatar Generation from Sparse Observations
        80190, -- 2108.12659 DKM: Differentiable K-Means Clustering Layer for Neural Network Compre
        80224, -- 2202.02195 Deep End-to-end Causal Inference
        80238, -- 2201.12569 Bellman Meets Hawkes: Model-Based Reinforcement Learning via Temporal
        80261, -- 2201.05020 Automatic Sparse Connectivity Learning for Neural Networks
        80685, -- 2106.04053 Discriminative Triad Matching and Reconstruction for Weakly Referring
        80788, -- 2104.02726 Creativity and Machine Learning: A Survey
        80971, -- 2012.05529 Recurrence of Optimum for Training Weight and Activation Quantized   N
        81061, -- 2008.13535 DCN V2: Improved Deep & Cross Network and Practical Lessons for Web-sc
        81224, -- 2007.03898 NVAE: A Deep Hierarchical Variational Autoencoder
        81446, -- 2002.08111 Hierarchical Quantized Autoencoders
        81588, -- 1909.12127 Intensity-Free Learning of Temporal Point Processes
        81610, -- 1909.06312 Neural Oblivious Decision Ensembles for Deep Learning on Tabular Data
        81681, -- 1907.00503 Modeling Tabular data using Conditional GAN
        81749, -- 1904.11132 TreeGrad: Transferring Tree Ensembles to Neural Networks
        81806, -- 1902.09393 Cooperative Learning of Disjoint Syntax and Semantics
        81835, -- 1901.02739 Dirichlet Variational Autoencoder
        82162, -- 1710.09483 Multimodal Probabilistic Model-Based Planning for Human-Robot Interact
        83180, -- 2605.06554 Long Context Pre-Training with Lighthouse Attention
        83692, -- 2605.21195 RankE: End-to-End Post-Training for Discrete Text-to-Image Generation
        84078, -- 2508.05423 Negative Binomial Variational Autoencoders for Overdispersed Latent Mo
        84253, -- 2511.20721 Foundry: Distilling 3D Foundation Models for the Edge
        84294, -- 2512.00489 Learning What Helps: Task-Aligned Context Selection for Vision Tasks
        84557, -- 2602.19565 DICArt: Advancing Category-level Articulated Object Pose Estimation in
        84655, -- 2602.24136 Prune Wisely, Reconstruct Sharply: Compact 3D Gaussian Splatting via A
        84678, -- 2603.00906 ShiftLUT: Spatial Shift Enhanced Look-Up Tables for Efficient Image Re
        84963, -- 2603.17979 AdaRadar: Rate Adaptive Spectral Compression for Radar-based Perceptio
        85023, -- 2603.21208 JANUS: A Lightweight Framework for Jailbreaking Text-to-Image Models v
        85244, -- 2604.02093 GroundVTS: Visual Token Sampling in Multimodal Large Language Models f
        85380, -- 2604.14563 Revisiting Token Compression for Accelerating ViT-based Sparse Multi-V
        85551, -- 2605.13316 Test-time Sparsity for Extreme Fast Action Diffusion
        85557, -- 2605.14110 SToRe3D: Sparse Token Relevance in ViTs for Efficient Multi-View 3D Ob
        85595, -- 2605.22061 Distributed Image Compression with Multimodal Side Information at Extr
        85735, -- 2501.19182 A compressive-expressive communication framework for compositional rep
        85749, -- 2409.16953 PASS: Path-selective State Space Model for Event-based Recognition
        85811, -- 2506.04749 Amortized Variational Transdimensional Inference
        85813, -- 2502.03366 Rethinking Approximate Gaussian Inference in Classification
        85906, -- 2509.21930 DynaNav: Dynamic Feature and Layer Selection for Efficient Visual Navi
        86033, -- 2504.13787 Probabilistic Stability Guarantees for Feature Attributions
        86191, -- 2502.06536 Sample-efficient Learning of Concepts with Theoretical Guarantees: fro
        86413, -- 2510.03944 On the Empirical Power of Goodness-of-Fit Tests in Watermark Detection
        86429, -- 2509.16606 Bayesian Ego-graph inference for Networked Multi-Agent Reinforcement L
        86495, -- 2505.22441 Can NeRFs See without Cameras?
        86508, -- 2509.12227 Learning to Route: Per-Sample Adaptive Routing for Multimodal Multitas
        86525, -- 2505.21817 ALTER: All-in-One Layer Pruning and Temporal Expert Routing for Effici
        86747, -- 2510.14741 DEXTER: Diffusion-Guided EXplanations with TExtual Reasoning for Visio
        86829, -- 2505.18051 LookWhere? Efficient Visual Recognition by Learning Where to Look and
        86842, -- 2502.11420 Training-Free Guidance Beyond Differentiability: Scalable Path Steerin
        86978, -- 2506.09891 Causal Climate Emulation with Bayesian Filtering
        87354, -- 2506.23068 Curious Causality-Seeking Agents Learn Meta Causal World
        87361, -- 2506.07673 How Benchmark Prediction from Fewer Data Misses the Mark
        87376, -- 2502.15283 BundleFlow: Deep Menus for Combinatorial Auctions by Diffusion-Based O
        87439, -- 2508.08450 Differentiable Cyclic Causal Discovery Under Unmeasured Confounders
        87766, -- 2507.22553 RainbowPrompt: Diversity-Enhanced Prompt-Evolving for Continual Learni
        87901, -- 2506.21080 EgoAdapt: Adaptive Multisensory Distillation and Policy Learning for E
        87933, -- 2507.14915 Music-Aligned Holistic 3D Dance Generation via Hierarchical Motion Mod
        88161, -- 2508.01835 Diffusion-based 3D Hand Motion Recovery with Intuitive Physics
        88194, -- 2508.00697 On-Device Diffusion Transformer Policy for Efficient Robot Manipulatio
        88261, -- 2501.12263 mmCooper: A Multi-agent Multi-stage Communication-efficient and Collab
        88406, -- 2507.21703 Semantic versus Identity: A Divide-and-Conquer Approach towards Adjust
        88459, -- 2405.05846 An Inversion-based Measure of Memorization for Diffusion Models
        88753, -- 2505.00663 Wasserstein Policy Optimization
        88767, -- 2502.15794 Self-Supervised Transformers as Iterative Solution Improvers for Const
        88973, -- 2410.08976 Learning Representations of Instruments for Partial Identification of
        89120, -- 2402.11628 Discrete Neural Algorithmic Reasoning
        89133, -- 2410.03208 SPHINX: Structural Prediction using Hypergraph Inference Network
        89175, -- 2410.07441 Zero Shot Generalization of Vision-Based RL Without Data Augmentation
        89796, -- 2411.14003 Generative Intervention Models for Causal Perturbation Modeling
        89823, -- 2506.17718 Learning Time-Aware Causal Representation for Model Generalization in
        90230, -- 2503.01899 FASTer: Focal token Acquiring-and-Scaling Transformer for Long-term 3D
        90411, -- 2504.03587 AutoSSVH: Exploring Automated Frame Sampling for Efficient Self-Superv
        90566, -- 2412.20522 MaskGaussian: Adaptive 3D Gaussian Representation from Probabilistic M
        90804, -- 2504.08449 Ego4o: Egocentric Human Motion Capture and Understanding from Multi-Mo
        91093, -- 2410.14673 Self-supervised contrastive learning performs non-linear system identi
        91290, -- 2409.02335 What Do You See in Common? Learning Hierarchical Prototypes over Tree-
        91568, -- 2407.00957 Expressivity of Neural Networks with Random Weights and Learned Biases
        91667, -- 2310.13391 Learning Successor Features with Distributed Hebbian Temporal Memory
        91708, -- 2402.02933 Intrinsic User-Centric Interpretability through Global Mixture of Expe
        91764, -- 2402.18213 Multi-objective Differentiable Neural Architecture Search
        91781, -- 2502.01084 Continuous Autoregressive Modeling with Stochastic Monotonic Alignment
        92227, -- 2503.00653 Discrete Codebook World Models for Continuous Control
        92392, -- 2502.19227 Enhancing the Scalability and Applicability of Kohn-Sham Hamiltonians
        92478, -- 2606.03911 Bootstrap Your Generator: Unpaired Visual Editing with Flow Matching
        92662, -- 2503.06084 Exploring Interpretability for Visual Prompt Tuning with Cross-layer C
        92901, -- 2506.14913 Winter Soldier: Backdooring Language Models at Pre-Training with Indir
        92930, -- 2506.16608 Distributions as Actions: A Unified Framework for Diverse Action Space
        93001, -- 2509.22445 Bridging Kolmogorov Complexity and Deep Learning: Asymptotically Optim
        93046, -- 2605.18204 Forward-Learned Discrete Diffusion: Learning how to noise to denoise f
        93100, -- 2505.21813 Optimizing Data Augmentation through Bayesian Model Selection
        93185, -- 2510.13704 Simplicial Embeddings Improve Sample Efficiency in Actor–Critic Agents
        93209, -- 2509.24716 Discrete Variational Autoencoding via Policy Search
        93758, -- 2505.22524 Inference-Time Scaling of Discrete Diffusion Models via Importance Wei
        93784, -- 2510.01274 TRACEDET: HALLUCINATION DETECTION FROM THE DECODING TRACE OF DIFFUSION
        93964, -- 2603.21612 Towards Multimodal Time Series Anomaly Detection with Semantic Alignme
        94133, -- 2509.24245 Prompt and Parameter Co-Optimization for Large Language Models
        94198, -- 2603.22216 Gumbel Distillation for Parallel Text Generation
        94296, -- 2505.16790 Learning Flexible Forward Trajectories for Masked Molecular Diffusion
        94309, -- 2604.03674 DiffSparse: Accelerating Diffusion Transformers with Learned Token Spa
        94587, -- 2510.05725 Improving Discrete Diffusion Unmasking Policies Beyond Explicit Refere
        94611, -- 2602.01428 Improving the Trade-off Between Watermark Strength and Speculative Sam
        94823, -- 2507.11019 Relative Entropy Pathwise Policy Optimization
        94834, -- 2601.19175 A Scalable Inter-edge Correlation Modeling in CopulaGNN for Link Sign
        94849, -- 2512.01116 Structural Prognostic Event Modeling for Multimodal Cancer Survival An
        95056, -- 2509.22925 Soft-Di[M]O: Improving One-Step Discrete Image Generation with Soft Em
        95101, -- 2606.06447 Latent Reasoning with Normalizing Flows
        95865, -- 2602.11656 SToRM: Supervised Token Reduction for Multi-Modal LLMs Toward Efficien
        97888, -- 2509.11116 SVR-GS: Spatially Variant Regularization for Probabilistic Masks in 3D
        98258, -- 2606.12303 From 2D Grids to 1D Tokens: Reforming Shared Representations for Multi
        98723, -- 2606.20010 Self-Adaptive Scale Handling for Forecasting Time Series with Scale He
        98771, -- 2204.10939 Unified Pretraining Framework for Document Understanding
        99498, -- 2512.16904 How Good is Post-Hoc Watermarking With Language Model Rephrasing?
        99766, -- 2601.12894 Sparse ActionGen: Accelerating Diffusion Policy with Real-time Pruning
        99886, -- 2605.19822 ST-TGExplainer: Disentangling Stability and Transition Patterns for Te
        100862, -- 2510.06952 OBJVanish: Prompt-Driven Generation of Physically Realizable 3D LiDAR-
        101087, -- 2606.01509 ProbMoE: Differentiable Probabilistic Routing for Mixture-of-Experts
        101089, -- 2602.13155 Learning to Approximate Uniform Facility Location via Graph Neural Net
        101456, -- 2606.06303 Plug-and-Play Guidance for Discrete Diffusion Models via Gradient-Info
        101519, -- 2509.24728 Beyond Softmax: A Natural Parameterization for Categorical Random Vari
        101822, -- 2511.17380 Non-Parametric Probabilistic Robustness: A Conservative Risk Estimator
        101827, -- 2605.14632 DRL-STAF: A Deep Reinforcement Learning Framework for State-Aware Fore
        102057, -- 2603.08824 SoftJAX & SoftTorch: Empowering Automatic Differentiation Libraries wi
        102675, -- 2401.06312 Video Super-Resolution Transformer with Masked Inter&Intra-Frame Atten
        102791, -- 2603.14228 Not All Directions Matter: Towards Structured and Task-Aware Low-Rank
        102919, -- 2604.15188 VisPCO: Visual Token Pruning Configuration Optimization via Budget-Awa
        102949, -- 2604.19398 GRASPrune: Global Gating for Budgeted Structured Pruning of Large Lang
        103969, -- 2412.14444 GenHMR: Generative Human Mesh Recovery
        104361, -- 2006.04240 Improving Inference for Neural Image Compression
        104365, -- 2104.05168 Soft then Hard: Rethinking the Quantization in Neural Image Compressio
        104770, -- 2602.08642 Forget Superresolution, Sample Adaptively (when Path Tracing)
        105487, -- 2501.10814 No More Sliding Window: Efficient 3D Medical Image Segmentation with D
        106029, -- 2607.29684 Toward Robust and 3D-Aware RGB-NIR Imaging in the Dark
        106053, -- 2605.22967 Learned Relay Representations for Forward-Thinking Discrete Diffusion
        106059, -- 2608.02023 SwanTale: Unified Multi-Speaker Speech and Audio Generation for Instru
        106260, -- 2607.20475 SonicSampler: Unified Tile-Aware Kernels for LLM Sampling and Speculat
        107756, -- 2512.12667 Open-World Deepfake Attribution via Confidence-Aware Asymmetric Learni
        108529, -- 2407.18929 Disturbance-based Discretization, Differentiable IDS Channel, and an I
        108694, -- 2605.23346 Contrastive Distribution Matching for Amortized Sequential Monte Carlo
        108766, -- 2605.06455 PrefixGuard: From LLM-Agent Traces to Online Failure-Warning Monitors
        108878, -- 2606.09108 RAM: Reachability Across Morphologies
        110295, -- 2506.17784 AnyMAC: Cascading Flexible Multi-Agent Collaboration via Next-Agent Pr
        110699, -- 2510.03467 Searching for the Most Human-like Emergent Language
        110795, -- 2510.12474 SMEC:Rethinking Matryoshka Representation Learning for Retrieval Embed
        111349, -- 2505.16207 Differentiable K-means for Fully-optimized Discrete Token-based ASR
        111481, -- 2505.18860 Context-Driven Dynamic Pruning for Large Speech Foundation Models
        112134, -- 2410.24177 DC-Spin: A Speaker-invariant Speech Tokenizer for Spoken Language Mode
        112608, -- 2404.15014 OccGen: Generative Multi-modal 3D Occupancy Prediction for Autonomous
        112628, -- 2312.06729 RGNet: A Unified Clip Retrieval and Grounding Network for Long Videos
        112707, -- 2409.04820 FreeAugment: Data Augmentation Search Across All Degrees of Freedom
        113001, -- 2407.15111 D4-VTON: Dynamic Semantics Disentangling for Differential Diffusion ba
        113181, -- 2407.07003 Learning to Complement and to Defer to Multiple Users
        113257, -- 2409.15557 Mixture of Efficient Diffusion Experts Through Automatic Interval and
        113456, -- 2407.15554 Decomposition of Neural Discrete Representations for Large-Scale 3D Ma
        113670, -- 2406.10600 SparseRadNet: Sparse Perception Neural Network on Subsampled Radar Dat
        113687, -- 2303.07223 PromptFusion: Decoupling Stability and Plasticity for Continual Learni
        113822, -- 2608.24293 Keep-or-Drop? Adaptive Tokenizer for Compact Video Representation
        114085, -- 2609.10355 Why Is Video Still So Expensive? A Survey of Inference-Efficiency Mech
        115525, -- 2406.09196 Adaptive Slot Attention: Object Discovery with Dynamic Slot Number
        115662, -- 2306.00519 DiffInDScene: Diffusion-based High-Quality 3D Indoor Scene Generation
        115934, -- 2304.05440 PixelRNN: In-pixel Recurrent Neural Networks for End-to-end-optimized
        115936, -- 2403.14729 Auto-Train-Once: Controller Network Guided Automatic Network Pruning f
        116622, -- 2403.01300 Causal Mode Multiplexer: A Novel Framework for Unbiased Multispectral
        116821, -- 2404.06337 Matching 2D Images in 3D: Metric Relative Pose from Metric Corresponde
        116878, -- 2311.18168 Probabilistic Speech-Driven 3D Facial Motion Synthesis: New Benchmarks
        116982, -- 2404.00973 Language-aware Visual Semantic Distillation for Video Question Answeri
        117104, -- 2311.18129 Mixed-Precision Quantization for Federated Learning on Resource-Constr
        117138, -- 2403.01773 Improving Out-of-Distribution Generalization in Graphs via Hierarchica
        117211, -- 2303.17783 Uncertainty-Aware Source-Free Adaptive Image Super-Resolution with Wav
        117307, -- 2405.19569 Improved Convex Decomposition with Ensembling and Negative Primitives
        117560, -- 2509.25603 GaussianLens: Localized High-Resolution Reconstruction via On-Demand G
        117620, -- 2605.21121 ROAR-3D: Routing Arbitrary Views for High-Fidelity 3D Generation
        117820, -- 2606.21910 Fidelity- and Perception-Aware Local Implicit Attention for Arbitrary-
        118144, -- 2606.27784 Improving Adversarial Robustness via Activation Amplification and Atte
        118294, -- 2607.04930 MemPose: Category-level Object Pose Estimation with Memory
        118356, -- 2606.27905 There and Back Again: A Flexible-Frame Transformer for Multi-Exposure
        118599, -- 2607.06609 D2PO: Optimizing Diffusion Samplers via Dynamic Preference
        118627, -- 2606.31225 A First Exploration of Neuromorphic OT-CFM for Multi-Speaker VSR
        118946, -- 2512.10244 Solving Semi-Supervised Few-Shot Learning from an Auto-Annotation Pers
        119120, -- 2607.04711 Learning Probabilistic Prompt for Continual Learning
        119229, -- 2608.15141 HOIMask: Towards Generative Masked Modeling for Human Object Interacti
        119350, -- 2607.03825 Q-TriM: Question-Guided Tri-Modal Attention for Audio–Visual Question
        119443, -- 2509.00030 SignBind-LLM: Multi-Stage Modality Fusion for Sign Language Translatio
        119525, -- 2608.25736 Moving Beyond More Views: Redundancy-Aware Ego–Exo Fusion for Proficie
        119548, -- 2607.20357 Look Less, Think Faster: Joint Token-Compute Adaptation for Multimodal
        120134, -- 2506.23623 Revisiting Audio-Visual Segmentation with Vision-Centric Transformer
        120787, -- 2505.20967 RF4D:Neural Radar Fields for Novel View Synthesis in Outdoor Dynamic S
        121916, -- 2604.03716 CGHair: Compact Gaussian Hair Reconstruction with Card Clustering
        121987, -- 2609.18487 ActionPiece: Rethinking Action Tokenization for Autoregressive Vision-
        122144, -- 2609.26774 StableVQ: Practical Guidelines for Stable Vector-Quantized Tokenizer T
        122303, -- 2609.33591 Pretraining Transformers with Quantized Softmax in Attention
        122611, -- 2609.37533 E-MoE: Enhanced Mixture-of-Experts for Non-Factorized Diffusion Langua
        122712, -- 2610.04198 ALoDLM: Adaptively Looped Diffusion Language Models
        122822, -- 2609.32921 Adaptive Latent Capacity for World Models
        123382, -- 2610.14726 LightVAE: Towards Compact and Efficient Video Autoencoders
        124212, -- external Youdunit: Single-Call Counterfactual Necessity in Multi-Agent LLM Syst
        124949, -- 2609.07049 Large Discrete Policy: Advancing Explicit Behavior Modeling with Stoch
        124970, -- 2606.24286 AVOC: Enhancing Hour-Level Audio-Video Understanding in Omni-Modal LLM
        124980, -- 2509.10656 Self-Supervised Goal-Reaching Results in Multi-Agent Cooperation and E
        125024, -- 2510.01632 BioBlobs: Unsupervised Discovery of Functional Substructures for Prote
        125167, -- 2610.04860 Invisible Ink, Visible Lies: How Production Watermarking Causes LLMs t
        125520, -- 2606.09853 SynIB: Informational Bottleneck for Maximizing Synergy in Multimodal L
        125861, -- 2610.19050 Focus, Align, and Diffuse: Time-Series-Aware Keyframe Diffusion for Ca
        126061, -- 2605.12278 Hypernetworks for Dynamic Feature Selection
        126255, -- 2503.17915 Learning Where and What to Restore for Composite Image Restoration
        126415, -- 2610.12094 Differentiable Systematic Resampling for Variational Sequential Monte
        126660, -- 2610.07505 MARS: Multi-resolution Adaptive Routing for Sequential Recommendation
        127745, -- 2605.07193 Coupling Models for One-Step Discrete Generation
        128535, -- 2605.13554 Self-Supervised On-Policy Reinforcement Learning via Contrastive Proxi
        129150, -- 2512.05865 Intrinsically Interpretable Attention via Sparse Post-Training
        130214, -- 2503.06684 PixelPonder: Dynamic Patch Adaptation for Enhanced Multi-Conditional T
        130246, -- 2606.27866 FlexMoE: One-for-All Nested Intra-Expert Pruning for MoE Language Mode
        130628, -- 2605.06315 End-to-End Identifiable and Consistent Recurrent Switching Dynamical S
        130804, -- 2605.12456 TextSeal: A Localized LLM Watermark for Provenance & Distillation Prot
        130917, -- 2609.33695 Geometric Inductive Biases for Semi-Supervised Equalization: The Const
        131110, -- 2606.29223 Depth Exploration for LLM Decoding
        131146, -- external Iterative Gumbel Planning for Continuous Control
        131278, -- 2608.03967 Information-Geometric Forward Policy Training in GFlowNets
        131997  -- 2611.08290 AutoCompress: Automated Hardware-Guided Model Compression
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: other sense, or a contrastive or passing mention'
FROM gumbel_softmax_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gumbel_softmax_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gumbel_softmax_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- Hero image credits (images imported with import_entity_image.py).
UPDATE methods SET image_credit = '[How transferable are features in deep neural networks?](/paper/1411.1792)' WHERE slug = 'transfer-learning';
UPDATE methods SET image_credit = '[An Overview of Multi-Task Learning in Deep Neural Networks](/paper/1706.05098)' WHERE slug = 'multi-task-learning';
UPDATE methods SET image_credit = '[Explaining and Harnessing Adversarial Examples](/paper/1412.6572)' WHERE slug = 'adversarial-training';
UPDATE methods SET image_credit = '[Score-Based Generative Modeling through Stochastic Differential Equations](/paper/2011.13456)' WHERE slug = 'score-matching';
UPDATE methods SET image_credit = '[Sinkhorn Distances: Lightspeed Computation of Optimal Transportation Distances](/paper/1306.0895)' WHERE slug = 'optimal-transport';
UPDATE methods SET image_credit = '[Generative Modeling by Estimating Gradients of the Data Distribution](/paper/1907.05600)' WHERE slug = 'langevin-dynamics';
UPDATE methods SET image_credit = '[Categorical Reparameterization with Gumbel-Softmax](/paper/1611.01144)' WHERE slug = 'gumbel-softmax';
