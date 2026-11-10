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
    'gumbel-softmax', 'Gumbel-Softmax', 'Gumbel-Softmax',
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
        18, 149, 190, 197, 505, 525, 702, 714, 857, 881, 984, 1057, 1116, 1161, 1191, 1229,
        1233, 1238, 1255, 1333, 1373, 1411, 1441, 1454, 1468, 1475, 1561, 1573, 1677, 1738, 1769, 1803,
        1855, 1856, 1898, 1938, 2028, 2050, 2055, 2096, 2104, 2126, 2132, 2151, 2162, 2187, 2255, 2257,
        2285, 2326, 2340, 2367, 2373, 2439, 2463, 2497, 2586, 2598, 2626, 2673, 2704, 2715, 2718, 2735,
        2785, 2788, 2799, 2840, 2850, 2910, 2928, 2929, 2931, 2942, 2950, 3009, 3157, 3187, 3189, 3267,
        3270, 3282, 3294, 3298, 3320, 3332, 3337, 3355, 3356, 3378, 3414, 3420, 3467, 3489, 3495, 3499,
        3507, 3510, 3512, 3515, 3523, 3562, 3576, 3581, 3606, 3633, 3707, 3769, 3772, 3803, 3833, 3849,
        3856, 3905, 3906, 3925, 3949, 4015, 4019, 4086, 4098, 4120, 4151, 4271, 4293, 4298, 4314, 4325,
        4407, 4410, 4424, 4450, 4505, 4510, 4637, 4735, 4780, 4833, 4858, 4894, 4913, 4916, 4922, 5004,
        5038, 5068, 5172, 5178, 5195, 5223, 5235, 5246, 5259, 5381, 5384, 5400, 5463, 5489, 5519, 5538,
        5570, 5620, 5635, 5653, 5664, 5782, 5860, 5880, 5909, 5911, 5954, 5968, 5985, 6039, 6047, 6094,
        6246, 6293, 6330, 6360, 6435, 6450, 6473, 6517, 6549, 6558, 6594, 6713, 6720, 6739, 6763, 6804,
        6808, 6854, 6861, 6872, 6900, 6941, 7018, 7022, 7059, 7071, 7093, 7113, 7137, 7161, 7164, 7165,
        7184, 7191, 7235, 7243, 7244, 7254, 7256, 7262, 7272, 7282, 7284, 7293, 7313, 7489, 7498, 7505,
        7547, 7554, 7564, 7598, 7615, 7621, 7629, 7713, 7739, 7741, 7751, 7763, 7821, 7844, 7845, 7926,
        7933, 7958, 7969, 8004, 8026, 8030, 8036, 8102, 8111, 8188, 8251, 8361, 8366, 8377, 8412, 8444,
        8455, 8489, 8619, 8705, 8719, 8725, 8755, 8869, 8915, 9031, 9046, 9055, 9122, 9150, 9180, 9327,
        9373, 9462, 9542, 9639, 9650, 9716, 9723, 9770, 9809, 9831, 9845, 9858, 9926, 10090, 10147, 10149,
        10244, 10320, 10408, 10424, 10448, 10623, 10760, 10794, 10814, 10968, 10998, 11002, 11125, 11184, 11254, 11266,
        11343, 11345, 11506, 11508, 11630, 11662, 11673, 11715, 11721, 11831, 11836, 11850, 12032, 12043, 12107, 12170,
        12280, 12308, 12347, 12348, 12424, 12425, 12489, 12583, 12618, 12898, 12917, 12945, 12993, 12997, 13019, 13071,
        13104, 13192, 13255, 13269, 13357, 13367, 13436, 13504, 13560, 13577, 13650, 13750, 13845, 13854, 13895, 13961,
        13980, 14008, 14092, 14152, 14236, 14358, 14369, 14378, 14388, 14583, 14598, 14599, 14625, 14668, 14676, 14824,
        14908, 14921, 15128, 15160, 15198, 15260, 15322, 15328, 15623, 15641, 15646, 15779, 15797, 15808, 15951, 16240,
        16409, 16414, 16646, 16655, 16711, 16774, 16843, 16868, 16873, 16874, 16959, 17051, 17103, 17123, 17200, 17215,
        17241, 17292, 17327, 17382, 17540, 17619, 17684, 17751, 17767, 17809, 17820, 18242, 18246, 18303, 18335, 18362,
        18537, 18621, 18665, 18668, 18775, 19146, 19180, 19266, 19424, 19434, 19468, 19491, 19498, 19603, 19626, 19752,
        19787, 19852, 19863, 19888, 19895, 19918, 20071, 20131, 20269, 20339, 20405, 20432, 20478, 20637, 20838, 21041,
        21227, 21416, 21535, 21541, 21575, 21613, 21704, 21717, 22143, 22189, 22265, 22567, 22733, 22756, 22883, 22904,
        22981, 23066, 23145, 23168, 23174, 23183, 23220, 23507, 23508, 23511, 23633, 24002, 24220, 24341, 24373, 24570,
        24656, 24673, 24778, 24817, 24893, 24898, 24939, 25148, 25183, 25240, 25330, 25404, 25578, 25688, 25749, 26029,
        26128, 26146, 26192, 26264, 26310, 26490, 26504, 26550, 26596, 26684, 26822, 26890, 26928, 27014, 27218, 27237,
        27442, 27719, 27887, 27990, 28014, 28112, 28127, 28361, 28647, 28704, 28934, 28962, 29033, 29168, 29333, 29375,
        29503, 29699, 29706, 29741, 29742, 29744, 29793, 29883, 29944, 30053, 30141, 30166, 30176, 30222, 30270, 30293,
        30468, 31008, 31131, 31144, 31163, 31195, 31316, 31380, 31424, 31605, 31752, 31786, 31952, 32020, 32275, 32537,
        32704, 32924, 33193, 33214, 33272, 33760, 33792, 33843, 33909, 33919, 34026, 34178, 34189, 34379, 34420, 34989,
        35190, 35341, 35397, 35468, 35503, 35605, 35607, 35610, 35664, 35706, 35813, 35943, 36066, 36165, 36246, 36878,
        37264, 37352, 37452, 37747, 38585, 38604, 38859, 39205, 39361, 40006, 40142, 40263, 40281, 40453, 40561, 40568,
        41099, 41339, 41437, 41704, 41834, 42320, 42539, 42576, 42649, 42858, 42878, 43011, 43133, 43191, 43266, 43268,
        43322, 43609, 43611, 43894, 43912, 43925, 43985, 44089, 44374, 44469, 44492, 44524, 44850, 45227, 45469, 45508,
        45516, 45578, 45617, 45627, 45637, 45881, 46761, 46854, 47192, 47398, 47484, 47554, 47761, 47900, 47905, 48308,
        48722, 48757, 49226, 49576, 49603, 50150, 50305, 50898, 50910, 52094, 53096, 55882, 56353, 56417, 57492, 57751,
        57901, 57958, 57964, 58674, 58841, 58877, 58996, 59380, 60031, 60278, 60407, 60518, 60689, 60906, 61888, 62776,
        63134, 63298, 63378, 63795, 63838, 64444, 64981, 65175, 65649, 65694, 66085, 66465, 66549, 66752, 66790, 67197,
        67862, 67884, 68016, 68416, 68497, 68597, 68615, 68630, 68975, 69131, 69278, 69521, 69530, 69687, 69914, 70088,
        70328, 70491, 70692, 70859, 70949, 70985, 71005, 71342, 71396, 71442, 71588, 71622, 71646, 71764, 72049, 72078,
        72134, 72327, 72332, 72476, 72853, 73259, 73335, 73405, 73413, 73561, 73617, 73697, 73874, 73943, 73975, 74037,
        74080, 74123, 74168, 74189, 74230, 74354, 74850, 74855, 74913, 74961, 74978, 75011, 75033, 75391, 75420, 75455,
        75722, 75811, 75845, 76041, 76203, 76354, 76836, 76987, 76995, 77079, 77089, 77117, 77162, 77240, 77368, 77509,
        77604, 77699, 77702, 77817, 77857, 78111, 78149, 78384, 78503, 78573, 78631, 78785, 78808, 78919, 78954, 78969,
        78992, 79089, 79120, 79158, 79352, 79353, 79354, 79467, 79699, 79779, 79825, 79864, 79890, 79903, 79988, 80029,
        80218, 80376, 80479, 80596, 80711, 80712, 80793, 80890, 80986, 81035, 81046, 81158, 81234, 81257, 81267, 81322,
        81330, 81353, 81357, 81376, 81411, 81421, 81435, 81477, 81489, 81525, 81551, 81597, 81771, 81795, 81832, 81872,
        81940, 81981, 82024, 82155, 82186, 83982, 85329, 85523, 85751, 86015, 86042, 86272, 86308, 86380, 86439, 86463,
        86487, 86507, 86524, 86600, 86617, 86917, 86930, 87056, 87137, 87200, 87274, 87536, 87870, 88047, 88095, 88144,
        88333, 88560, 88640, 88846, 89029, 89248, 89317, 89413, 89415, 89453, 89531, 89585, 89622, 89778, 89821, 89855,
        89869, 90043, 90265, 90455, 90665, 90704, 90783, 90989, 91013, 91416, 91719, 91789, 91896, 92047, 92083, 92086,
        92446, 92576, 92638, 92915, 92968, 93076, 93125, 93615, 93979, 93984, 94450, 95017, 96284, 96433, 96853, 97508,
        97838, 97991, 98359, 98637, 98733, 99780, 100238, 100283, 100978, 101226, 101985, 102100, 102286, 102502, 102744, 103785,
        104086, 104101, 104103, 104141, 104144, 104258, 104270, 104616, 104970, 104986, 105008, 105231, 105402, 105728, 105773, 105898,
        106901, 106971, 107629, 107663, 107815, 108225, 108450, 109217, 109677, 110029, 110599, 110699, 110732, 110920, 111226, 111231,
        111495, 111716, 112539, 112617, 112726, 112803, 112883, 112937, 112962, 112964, 112993, 113079, 113163, 113440, 113441, 113451,
        113543, 113644, 113669, 113678, 114351, 114386, 114395, 114413, 114855, 114943, 114944, 114995, 115102, 115142, 115235, 115328,
        115365, 115531, 115568, 115569, 115840, 115894, 115938, 116037, 116164, 116349, 116421, 116463, 116556, 116649, 116722, 116946,
        116992, 116993, 117197, 117411, 118173, 119847, 119920, 119981, 120027, 120335, 121413, 121746, 122612, 123072, 123226, 123646,
        123647, 123648, 123649, 123651, 124534, 125926, 125946, 126283, 126735, 126969, 127482, 127579, 128384, 128596, 128607, 128615,
        129813, 129821, 130160, 130388, 130389, 130679, 130762, 131123, 131342, 131520
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
        3534, 18226, 40369
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
        421, 625, 641, 719, 818, 954, 984, 1271, 1354, 1545, 1621, 1676, 1728, 2024, 2041, 2065,
        2105, 2375, 2456, 2470, 2555, 2668, 2711, 2719, 2749, 2766, 2939, 3013, 3144, 3160, 3282, 3473,
        3489, 3510, 3653, 3730, 3780, 3851, 4019, 4242, 4325, 4434, 4557, 4597, 4871, 4913, 4947, 4989,
        5068, 5077, 5307, 5384, 5685, 5751, 5770, 5905, 5917, 6057, 6391, 6429, 6479, 6504, 6535, 6618,
        6792, 6841, 6878, 6968, 7011, 7078, 7100, 7156, 7268, 7272, 7600, 7955, 8026, 8096, 8102, 8155,
        8365, 8502, 8512, 8596, 8613, 8678, 8683, 8738, 8743, 8837, 8846, 8861, 9010, 9062, 9068, 9128,
        9341, 9363, 9451, 9622, 9648, 9681, 9705, 9845, 9855, 9921, 10018, 10204, 10208, 10462, 10581, 10639,
        10771, 10873, 10892, 11047, 11079, 11241, 11381, 11420, 11597, 11604, 11639, 11697, 11716, 11784, 11824, 11904,
        12309, 12329, 12403, 12424, 12589, 12878, 12912, 13053, 13131, 13304, 13504, 13690, 13842, 13845, 14008, 14023,
        14252, 14296, 14352, 14361, 14600, 14722, 14806, 15001, 15083, 15166, 15419, 15539, 15869, 16077, 16140, 16553,
        16593, 16732, 17094, 17141, 17200, 17377, 17585, 17723, 17834, 17900, 17984, 18075, 18174, 18398, 18730, 18740,
        18790, 19148, 19211, 19312, 19673, 19701, 19712, 19749, 19847, 20158, 20440, 20454, 20785, 20975, 21060, 21205,
        21227, 21349, 21366, 21501, 21760, 21797, 21928, 21974, 22143, 22258, 22291, 22340, 22438, 22534, 22659, 22786,
        22933, 22955, 23174, 23462, 23532, 24096, 24114, 24341, 24346, 24542, 24578, 25151, 25248, 25357, 25535, 25647,
        25724, 25986, 26135, 26530, 26788, 27077, 27118, 27256, 27496, 27806, 28020, 28184, 28457, 28836, 28944, 29118,
        29168, 29183, 29433, 29584, 29679, 29881, 29944, 29958, 30328, 30701, 30937, 31120, 31346, 31786, 32045, 32359,
        32833, 32987, 33098, 33403, 33574, 33628, 33878, 34282, 34456, 35146, 35468, 35709, 35715, 35811, 35844, 36124,
        36912, 37548, 37764, 37906, 38096, 38149, 38361, 38465, 38817, 39658, 39820, 39899, 40119, 40130, 40612, 40718,
        40923, 41427, 41447, 41759, 42208, 42411, 42576, 42873, 43035, 43236, 43648, 43716, 43742, 43979, 44452, 44502,
        44977, 45610, 45679, 45763, 45789, 45839, 46211, 46608, 46735, 46829, 46913, 47051, 48485, 48772, 49651, 49888,
        50747, 50908, 51103, 51246, 51252, 51625, 51893, 52092, 52623, 53733, 53911, 53924, 54170, 54636, 54855, 58046,
        58203, 58839, 58889, 59890, 60637, 60857, 61298, 61450, 61554, 61574, 61590, 61908, 62107, 62295, 62994, 64096,
        64118, 64127, 64316, 64479, 65080, 65454, 65542, 65658, 65694, 65788, 66159, 66264, 66601, 67284, 67408, 67480,
        68059, 68595, 68800, 68815, 69050, 69337, 69420, 69427, 69610, 69772, 69971, 70023, 70065, 70087, 70379, 70621,
        70731, 70763, 70858, 71110, 71261, 71344, 71530, 72026, 72200, 72298, 72556, 72568, 72594, 72611, 74180, 74299,
        74704, 75066, 75151, 75359, 75512, 75617, 75679, 75931, 76238, 76379, 76382, 76519, 76629, 77317, 77473, 77640,
        77820, 77925, 77930, 78038, 78079, 78524, 78925, 79073, 79097, 79107, 79220, 79350, 79776, 79919, 79995, 80012,
        80090, 80246, 80299, 80334, 80577, 80596, 80691, 80716, 80906, 81068, 81308, 81366, 81450, 81872, 82122, 82143,
        82158, 82223, 82440, 82566, 82855, 83791, 84036, 84224, 84252, 84288, 84353, 84737, 85001, 86830, 87213, 87248,
        87329, 87473, 87476, 87593, 87632, 87694, 87986, 88092, 88167, 88885, 89103, 89117, 89636, 89804, 90431, 90665,
        91009, 91207, 91218, 91247, 91248, 91561, 91663, 91695, 91870, 92070, 92110, 92740, 92923, 92979, 93772, 95017,
        95018, 95405, 96433, 97252, 97362, 97438, 97732, 97990, 98367, 98385, 98424, 99217, 99684, 99700, 99746, 99779,
        100676, 101084, 101547, 101620, 101665, 101773, 102075, 102772, 103132, 103940, 104026, 104082, 104095, 104436, 104641, 104697,
        104920, 104937, 104995, 105189, 105408, 105427, 105504, 105552, 105642, 105740, 105839, 106948, 107327, 107707, 107815, 107879,
        108260, 108272, 108398, 108451, 108974, 108984, 109216, 109323, 109399, 109431, 110304, 110529, 111100, 111273, 111408, 111451,
        111506, 111553, 111561, 111886, 111946, 111952, 111953, 111959, 112015, 112078, 112086, 112093, 112129, 112434, 112441, 112795,
        112829, 113577, 114111, 114363, 114428, 114864, 114914, 114959, 115038, 115139, 115142, 115144, 115163, 115681, 116259, 116388,
        116579, 116638, 116798, 116803, 116841, 116904, 117077, 117145, 117678, 118198, 118203, 118204, 118231, 119312, 119893, 119902,
        120006, 120045, 120058, 120165, 120383, 120405, 120552, 120820, 121299, 121305, 121386, 123732, 124191, 124457, 124512, 125342,
        125720, 126582, 126842, 127473, 127499, 127681, 128893, 128958, 129691, 130267, 130509, 131418
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
        837, 12098, 108673, 127563
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
        830, 1253, 2048, 2687, 2743, 3103, 3202, 3450, 3834, 4025, 4567, 5215, 5220, 5350, 5689, 5832,
        7514, 7725, 7855, 7936, 7958, 8026, 8569, 8655, 9901, 9921, 10648, 10844, 10890, 11075, 11211, 11409,
        11664, 11978, 12214, 12219, 12298, 12310, 12592, 12674, 12770, 13112, 13608, 14092, 14373, 15012, 15268, 15370,
        16787, 18189, 18767, 18982, 19316, 19335, 19425, 19495, 19668, 19697, 20210, 21766, 22228, 22456, 23355, 23642,
        23909, 24092, 24425, 26776, 27308, 27693, 28334, 28701, 28920, 29059, 29655, 29726, 29944, 30730, 31276, 31441,
        31525, 32074, 32174, 33381, 34013, 34040, 34104, 34141, 34309, 34626, 36761, 37107, 37181, 38103, 38594, 38725,
        39318, 39378, 39453, 39692, 40095, 40574, 40775, 42027, 42270, 42644, 42651, 42706, 42720, 43648, 43889, 44048,
        44665, 44957, 44976, 45474, 45519, 45648, 45970, 46134, 46219, 46329, 46525, 46577, 47152, 47168, 47288, 47378,
        47394, 47626, 48043, 48341, 48598, 48681, 48791, 48987, 49019, 49072, 49147, 49245, 49399, 49402, 49530, 49854,
        50036, 50324, 50338, 50439, 50650, 51034, 51310, 51500, 51763, 51863, 51999, 52046, 52192, 52325, 52332, 52701,
        53121, 53469, 53646, 53725, 53735, 54079, 54132, 54199, 54323, 54450, 54482, 54646, 54875, 55206, 55424, 55480,
        55859, 56022, 56067, 56265, 56466, 56964, 57125, 57265, 58395, 58718, 58811, 58923, 58970, 59375, 59479, 59577,
        59634, 59678, 60137, 60290, 60355, 60727, 61191, 61434, 61812, 61918, 62055, 62262, 62298, 62446, 62907, 63257,
        63741, 63985, 64132, 64171, 64281, 64782, 65149, 65185, 65692, 66230, 66487, 66821, 67178, 67353, 67420, 67542,
        67706, 68176, 68415, 68873, 69167, 69363, 69365, 69625, 69873, 70108, 70234, 70272, 70974, 71162, 71203, 71305,
        71396, 71436, 71533, 71934, 72029, 72213, 72499, 72596, 73784, 73883, 73885, 74411, 74492, 74538, 74831, 75359,
        76445, 76602, 77578, 78033, 79388, 80025, 80873, 81380, 81472, 81595, 83425, 84214, 84445, 84488, 84821, 85087,
        85288, 85479, 85537, 87050, 87745, 89740, 89843, 89860, 89949, 90042, 90838, 90882, 92243, 92367, 92619, 92866,
        93155, 93878, 94610, 94790, 94947, 95400, 95754, 95817, 95879, 96184, 96367, 96684, 97122, 97166, 97342, 97374,
        97807, 97870, 98553, 98675, 98686, 98951, 98993, 99185, 99862, 100618, 101198, 101323, 102144, 102187, 102266, 102942,
        103210, 103345, 103407, 103476, 104409, 105020, 106003, 106059, 106129, 107239, 107611, 107796, 108158, 108629, 108709, 108973,
        109161, 110073, 110236, 110353, 110518, 110973, 111088, 111136, 111501, 111517, 111561, 111594, 111652, 111696, 111710, 111839,
        112060, 113162, 113789, 114322, 114353, 114356, 115216, 115496, 116948, 117345, 117774, 118756, 119006, 119214, 119242, 119271,
        119321, 120226, 121435, 122558, 123746, 124718, 124823, 125356, 126099, 126615, 127184, 129589, 130001, 130227, 130441, 130765,
        132122
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
        228, 563, 818, 826, 1798, 2108, 2784, 2814, 2824, 2876, 3091, 3111, 3739, 3798, 4030, 4070,
        4091, 4105, 4468, 4694, 4856, 4916, 4979, 5068, 5165, 5437, 5446, 6086, 6116, 6186, 6203, 6228,
        6290, 6440, 6459, 6705, 6707, 6775, 7096, 7228, 7238, 7305, 7383, 7419, 7495, 7762, 7881, 8268,
        8310, 8319, 8417, 8968, 9126, 9988, 10018, 10126, 10529, 10579, 10597, 10634, 10774, 10994, 11197, 11238,
        11508, 11592, 11754, 11945, 12369, 12409, 12513, 12593, 13092, 13103, 13169, 13286, 13495, 13950, 14178, 14267,
        14545, 14902, 15198, 15314, 15436, 16321, 16325, 16687, 17042, 17107, 17454, 17540, 17824, 17942, 18089, 18092,
        18275, 18549, 19600, 20304, 20433, 21563, 21576, 22362, 22801, 22975, 23193, 23452, 23514, 23790, 24666, 25265,
        25812, 25869, 25954, 25979, 26325, 27092, 27127, 27239, 27889, 27957, 28179, 28299, 28307, 28503, 30056, 30084,
        30558, 30731, 32869, 32949, 34255, 35243, 35861, 37004, 38245, 38703, 39767, 40095, 41203, 41290, 43859, 44370,
        44697, 45296, 45995, 47214, 47535, 47692, 48406, 48481, 50344, 50535, 50827, 51764, 52621, 54538, 54706, 54708,
        55151, 55413, 57887, 58688, 59623, 63678, 64335, 64388, 64611, 66127, 67040, 68030, 68346, 70045, 70063, 70836,
        71391, 71583, 72066, 72134, 73413, 74785, 75012, 75032, 75094, 75116, 75728, 76479, 76494, 76535, 78053, 78205,
        78381, 78523, 78651, 78905, 79487, 80237, 80528, 80650, 81075, 81193, 81212, 81235, 81277, 81443, 81772, 82264,
        83442, 83678, 83966, 84276, 84455, 84528, 84806, 84837, 85026, 85107, 85540, 86013, 86105, 86791, 87060, 87167,
        87611, 87832, 88064, 88698, 88757, 88769, 88784, 88926, 89706, 89741, 90306, 90666, 90754, 90818, 90880, 91176,
        91177, 92162, 92191, 92360, 92409, 92741, 93563, 94243, 95162, 95642, 95935, 96158, 96331, 96673, 96966, 97030,
        99007, 100276, 100344, 100361, 100419, 100431, 100511, 101207, 101499, 101578, 101579, 101655, 102343, 102448, 102501, 103082,
        104134, 104917, 105062, 105071, 105089, 105496, 105501, 105502, 105676, 105694, 105704, 105733, 105818, 107033, 107703, 107751,
        108211, 108365, 108563, 110018, 110758, 110812, 111575, 112571, 112830, 113016, 113034, 113250, 113628, 113637, 114084, 114350,
        114353, 114360, 114440, 115182, 115264, 115536, 116118, 116138, 116199, 116897, 117338, 117953, 118328, 119022, 120432, 122185,
        123231, 123307, 124321, 124806, 124823, 125142, 125309, 125503, 125955, 126286, 127145, 127200, 127602, 128805, 129039, 129102,
        129360, 129401, 129654, 129772, 129951, 130133, 130260, 130349, 130841, 131115
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
        67061, 125388
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
        138, 381, 664, 956, 1458, 1616, 1921, 1993, 2270, 2731, 2843, 3151, 3181, 3344, 3528, 3668,
        3708, 3730, 3732, 4159, 4207, 4229, 4790, 4907, 5342, 5403, 5422, 5502, 5517, 5680, 5784, 5847,
        6152, 6216, 6326, 6392, 6533, 6839, 7148, 7455, 7651, 7874, 8023, 8228, 8341, 8390, 8563, 8577,
        8589, 8920, 9029, 9244, 9263, 9402, 9853, 9881, 9994, 10019, 10188, 10437, 10734, 10778, 11155, 11727,
        11960, 12345, 12648, 12723, 12878, 12980, 13435, 13482, 13560, 13716, 13810, 13814, 14018, 14283, 14328, 14797,
        15116, 15827, 16018, 16420, 16883, 17074, 17233, 17309, 17546, 17596, 17692, 17845, 18039, 18240, 18399, 18424,
        18718, 18773, 18827, 18900, 18939, 19028, 19484, 19742, 19959, 20018, 20111, 21166, 21681, 21932, 22011, 22625,
        25674, 26100, 26175, 26343, 26430, 26855, 26933, 27115, 27536, 28142, 28560, 28892, 28902, 29155, 29857, 30264,
        31190, 31671, 31697, 31748, 31757, 32448, 33296, 33491, 33885, 34342, 34776, 35051, 35511, 35716, 35747, 37351,
        38806, 39374, 41289, 41428, 42153, 43442, 43465, 43613, 43866, 44722, 44909, 47159, 47305, 49464, 50165, 50223,
        58420, 60592, 62784, 63369, 63691, 63835, 64020, 64682, 64812, 66493, 67676, 68571, 69094, 69769, 69964, 71272,
        72449, 72527, 72998, 73503, 73634, 73853, 73911, 74110, 74924, 76417, 77825, 78485, 78507, 78594, 80105, 80146,
        80356, 80396, 81096, 82948, 83981, 84018, 84083, 84271, 84444, 84568, 85159, 85205, 85459, 85552, 86333, 86630,
        87666, 87676, 87868, 88638, 89041, 89059, 89387, 89487, 90022, 90207, 90226, 90233, 90344, 90671, 90764, 91516,
        91610, 91641, 91669, 91812, 91813, 91904, 91909, 91936, 91950, 91997, 92245, 92296, 92431, 92821, 93028, 93190,
        93206, 93265, 93417, 93979, 94001, 94197, 94703, 95033, 96660, 98164, 99888, 99902, 100583, 100704, 101471, 101778,
        101975, 102777, 105268, 106294, 106809, 107026, 107089, 107791, 108060, 108365, 110901, 111422, 111492, 112401, 112630, 112727,
        112944, 113006, 113333, 113517, 113538, 113612, 115257, 115444, 115750, 115751, 115831, 115865, 115940, 115955, 115974, 116191,
        116460, 116465, 116521, 116782, 116785, 116993, 118138, 119097, 119105, 119136, 119143, 119847, 119946, 120061, 120146, 120337,
        120672, 120877, 121041, 121437, 121555, 121679, 121832, 122814, 124186, 124242, 124549, 125540, 125996, 126587, 127568, 127582,
        129307, 129653, 129675, 129697, 130054, 130368, 130796
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
        191, 894, 1051, 1147, 1181, 1187, 1277, 1589, 1643, 1933, 1975, 2068, 2115, 2304, 2320, 2711,
        2813, 3194, 3282, 3355, 3356, 3392, 4268, 4468, 5456, 5775, 6327, 6823, 7212, 7315, 7319, 7551,
        7633, 7930, 7954, 7996, 8255, 8529, 8981, 9196, 9504, 9729, 9998, 10524, 11046, 11048, 12245, 12736,
        12738, 12788, 12870, 13009, 13224, 14173, 14249, 14290, 15417, 15599, 16560, 16965, 17189, 17230, 17352, 18095,
        18272, 18970, 19686, 19731, 20793, 21348, 21370, 22335, 23429, 23516, 25582, 25603, 25644, 26279, 27287, 27964,
        28514, 28670, 28944, 29362, 29714, 30392, 31211, 31674, 32213, 32224, 32267, 32351, 32437, 32454, 32876, 33216,
        33462, 33913, 34716, 35277, 36404, 36440, 37041, 37164, 38694, 40875, 42044, 42957, 43861, 45097, 45501, 46709,
        46803, 48773, 50622, 50920, 51224, 52821, 53716, 54419, 54530, 54600, 55187, 57818, 57945, 59495, 59533, 60760,
        61610, 61816, 64330, 64539, 64743, 65498, 67673, 67774, 68546, 68999, 69138, 70255, 71677, 71943, 74048, 75423,
        75811, 78709, 80485, 80677, 80986, 81276, 81323, 81351, 82033, 82899, 84427, 84525, 85774, 88182, 88973, 89886,
        89989, 90616, 91605, 91959, 92417, 92737, 93776, 94482, 94586, 95056, 95117, 95542, 95796, 101408, 101793, 102615,
        104159, 104342, 104932, 105025, 105418, 105659, 106163, 107934, 110319, 111059, 111133, 111377, 111985, 112436, 112666, 114495,
        115027, 115060, 115171, 116381, 116539, 116575, 116712, 117137, 120552, 120625, 120803, 122274, 123425, 124002, 124288, 125624,
        125648, 125675, 128568, 129001, 130381, 130906, 130934, 131525, 131898
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
        422, 2153, 2182, 3944, 4347, 4921, 5730, 5904, 6034, 6041, 6100, 6834, 6877, 7349, 7811, 7999,
        8527, 8809, 9321, 9400, 9439, 9568, 10491, 10541, 10545, 10621, 10832, 10925, 11037, 11063, 11086, 11119,
        11180, 11253, 11312, 12497, 12638, 12673, 12716, 12754, 12781, 12822, 12893, 12937, 12955, 12989, 13052, 13090,
        13131, 13303, 13340, 13352, 13442, 13562, 13651, 13995, 14416, 15144, 15151, 15331, 15341, 15400, 15418, 16061,
        16257, 16307, 16819, 16866, 17009, 17156, 17166, 17206, 17643, 18101, 18288, 18485, 19607, 20339, 20714, 21121,
        21269, 21732, 21787, 22072, 22377, 22455, 22578, 23727, 23805, 25311, 25924, 26070, 27142, 27154, 27794, 28338,
        28814, 29085, 29246, 30316, 31100, 35710, 37602, 38437, 38837, 39707, 39805, 41141, 41288, 41428, 42290, 42585,
        42776, 43447, 43536, 43820, 43875, 43925, 44618, 44762, 45095, 45483, 45846, 46185, 46828, 47152, 47198, 47902,
        48078, 48132, 48162, 48999, 51739, 51902, 52110, 52366, 52833, 52838, 53260, 55406, 55939, 57804, 58119, 58508,
        58786, 60080, 60433, 60445, 61148, 61904, 61970, 64996, 65345, 65545, 65759, 68289, 68334, 68509, 68755, 69916,
        69969, 70401, 70910, 71114, 71289, 71399, 71542, 72286, 72462, 72473, 74215, 74336, 74640, 75032, 75233, 75353,
        75413, 75507, 75771, 76259, 76698, 76937, 77294, 77494, 77649, 78143, 78273, 78567, 78739, 78756, 78865, 79099,
        79341, 79385, 79494, 79645, 79702, 80011, 80024, 80084, 80322, 80343, 80349, 80403, 80473, 80518, 81460, 81532,
        82041, 84002, 84368, 84567, 84728, 85475, 85920, 85965, 86048, 86173, 86198, 86228, 86237, 86290, 86319, 86335,
        86352, 86371, 86373, 86395, 86449, 86463, 86494, 86528, 86545, 86626, 86639, 86749, 86838, 86883, 86900, 86963,
        86968, 86988, 87023, 87065, 87144, 87149, 87316, 87323, 87340, 87341, 87401, 88237, 88471, 88565, 88589, 88631,
        88725, 88733, 88758, 88808, 88855, 88899, 88927, 88965, 88971, 88985, 89013, 89075, 89191, 89230, 89246, 89261,
        89276, 89287, 89334, 89341, 89392, 89414, 89465, 89478, 89578, 89665, 89834, 89883, 89916, 89928, 89977, 89999,
        90007, 90010, 91203, 91251, 91302, 91331, 91374, 91524, 91539, 91567, 91573, 91692, 91804, 92002, 92017, 92029,
        92030, 92034, 92035, 92235, 92306, 92349, 92356, 92605, 92715, 92755, 92944, 92967, 93031, 93036, 93120, 93538,
        93592, 93663, 93805, 93808, 93853, 93883, 93947, 93984, 94386, 94427, 94605, 94725, 94907, 98583, 98776, 99269,
        99858, 99906, 100013, 100057, 100095, 100104, 100144, 100233, 100234, 100252, 100259, 100300, 100349, 100398, 100792, 100891,
        100903, 100925, 101109, 101192, 101680, 101681, 101835, 101889, 101934, 101941, 101998, 102023, 102055, 102072, 102076, 102115,
        102206, 102232, 102251, 102671, 102881, 103618, 103652, 104380, 105149, 106355, 106373, 106542, 106548, 106609, 106721, 106810,
        106945, 107122, 107396, 107397, 107417, 107687, 107842, 108155, 108526, 108551, 110061, 110213, 110397, 110761, 112436, 112821,
        115669, 116032, 119089, 120705, 121550, 124010, 124244, 124351, 124520, 124523, 124535, 124721, 124722, 124909, 124918, 124934,
        125088, 125327, 125508, 125849, 126117, 126137, 126248, 126316, 126725, 126918, 126942, 126995, 127561, 127733, 127781, 127806,
        127969, 127987, 127995, 128215, 128249, 128421, 128501, 128520, 128532, 128642, 128654, 128932, 128993, 129042, 129107, 129223,
        129235, 129320, 129367, 129597, 129749, 129768, 129850, 130000, 130334, 130409, 130518, 130685, 130801, 130810, 130904, 130938,
        131031, 131042, 131230, 131242
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
        22, 2338, 3764, 4095, 4441, 4628, 5717, 5805, 7219, 7429, 7872, 7879, 8435, 8510, 8524, 9394,
        9438, 9484, 10135, 10241, 10415, 11204, 11223, 11567, 11717, 12236, 12341, 12867, 12931, 12986, 13011, 13229,
        13418, 13465, 13468, 13793, 14477, 14586, 14901, 14968, 15121, 15690, 16227, 16487, 16569, 16582, 16755, 16997,
        16999, 18010, 20164, 20575, 20611, 20654, 20846, 21061, 21064, 21145, 21293, 21348, 21946, 21989, 22194, 22571,
        22787, 23522, 23822, 24883, 25190, 25493, 25596, 26376, 26537, 27233, 27271, 27885, 28066, 28302, 28475, 29282,
        30930, 31401, 31778, 32541, 32776, 33216, 34450, 36903, 36957, 37999, 39293, 39449, 41028, 42503, 43504, 44964,
        45329, 45434, 45849, 45857, 46554, 48077, 50375, 51020, 51197, 53211, 53993, 54362, 54377, 57098, 57462, 57839,
        59562, 59899, 61754, 66863, 68856, 69285, 70470, 71059, 71673, 72628, 73101, 73407, 75919, 77920, 78917, 80680,
        80879, 82899, 84031, 85800, 85843, 85988, 86090, 86154, 86215, 86229, 86277, 86402, 86478, 86726, 86876, 87085,
        87100, 87336, 87346, 87828, 88289, 88343, 88532, 88546, 88572, 88583, 88606, 88645, 88761, 88842, 89070, 89163,
        89289, 89553, 89782, 90012, 90921, 90949, 91149, 91213, 91237, 91370, 91632, 91819, 91832, 92012, 92215, 92377,
        92803, 93015, 93067, 93077, 93148, 93268, 93458, 93912, 94127, 94292, 94402, 95284, 96564, 98873, 99210, 99415,
        99524, 99555, 100161, 100487, 100588, 100760, 100779, 100888, 100994, 101015, 101351, 101437, 101478, 101513, 101855, 101944,
        101945, 102056, 102117, 103934, 104774, 105006, 105534, 107180, 107458, 107805, 107987, 108029, 108106, 111594, 112098, 113483,
        113772, 114452, 115044, 115661, 115892, 116698, 116712, 117768, 118517, 118618, 120911, 120926, 121869, 122747, 124172, 124236,
        124257, 124502, 124807, 124927, 125076, 125104, 125413, 125418, 125515, 125567, 125583, 125896, 125991, 126074, 126105, 126219,
        126340, 126719, 127151, 127691, 127869, 128104, 128898, 129358, 129510, 129581, 129642, 129656, 129870, 129896, 129959, 130018,
        130099, 130712, 130816, 132048, 132063
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
        105168
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
        1207, 1760, 1886, 2364, 2593, 2667, 2808, 2866, 3805, 4146, 4218, 4595, 5019, 6002, 6312, 6465,
        6815, 6880, 7087, 7226, 7294, 7836, 8075, 8237, 8283, 8322, 8623, 8856, 9270, 9282, 9440, 9653,
        10233, 10406, 10450, 10486, 10586, 10608, 10676, 10768, 10894, 11066, 11183, 11435, 12200, 12469, 12554, 12589,
        12658, 12685, 12751, 12903, 12947, 13000, 14051, 14094, 14650, 14948, 15639, 16221, 16334, 16441, 16558, 16843,
        16930, 16948, 17045, 17079, 17269, 17409, 17968, 17978, 18031, 18110, 18317, 18494, 18892, 19375, 20131, 21221,
        21314, 21370, 21553, 21638, 21673, 21839, 22420, 23755, 23816, 23920, 24029, 25538, 25937, 26154, 26462, 26766,
        27210, 27398, 27571, 27866, 28024, 28104, 28343, 29237, 29633, 29751, 29938, 30364, 31584, 32580, 32614, 33197,
        33235, 34049, 34573, 35043, 36042, 36118, 36365, 36737, 37586, 39388, 40128, 40756, 41924, 42154, 43569, 43610,
        44875, 45042, 45246, 45378, 46082, 46145, 49059, 49332, 49584, 49622, 49952, 50692, 51479, 51701, 51839, 52544,
        53295, 54165, 54419, 55670, 55893, 55957, 56452, 56610, 56781, 56885, 56911, 57543, 57545, 58678, 59891, 60201,
        60234, 60399, 60422, 61169, 61878, 62224, 62392, 62411, 62699, 63003, 63115, 63544, 64028, 64428, 64539, 64877,
        64896, 64950, 64960, 65131, 65478, 65884, 65923, 66065, 66562, 67598, 68706, 69504, 70271, 70424, 70559, 70641,
        70876, 71253, 71446, 72279, 72592, 73139, 73670, 73891, 74167, 74849, 74941, 75026, 75636, 75851, 76507, 77164,
        77443, 77901, 78407, 79410, 80127, 80626, 81124, 81233, 82096, 83542, 83759, 84043, 84077, 84212, 84666, 84855,
        84860, 84861, 84881, 85298, 85399, 85435, 85502, 86004, 86190, 86214, 86253, 86354, 86447, 86484, 86531, 86543,
        86563, 86632, 86713, 86761, 86917, 86989, 87101, 87156, 87209, 87331, 87426, 87441, 87566, 87780, 87794, 87808,
        87833, 87857, 88075, 88156, 88163, 88197, 88351, 88392, 88479, 88505, 88522, 88534, 88560, 88606, 88749, 88762,
        88830, 88903, 88935, 88941, 88999, 89039, 89075, 89082, 89089, 89124, 89171, 89181, 89415, 89437, 89570, 89577,
        89584, 89781, 89810, 89898, 89914, 89975, 90145, 90339, 90396, 90721, 90745, 90797, 90835, 90836, 90861, 90986,
        91073, 91074, 91135, 91170, 91207, 91312, 91315, 91358, 91408, 91415, 91503, 91537, 91585, 91589, 91603, 91676,
        91736, 91784, 91857, 91901, 91971, 92170, 92432, 92720, 92845, 92861, 92971, 93026, 93286, 93345, 93385, 93633,
        93634, 93746, 93776, 93806, 93809, 93877, 93909, 94011, 94040, 94224, 94260, 94280, 94313, 94575, 94664, 94707,
        94754, 94885, 94887, 94967, 94972, 95054, 95315, 96053, 96836, 98000, 98091, 99128, 99152, 99284, 99372, 99395,
        99399, 99462, 99550, 99567, 99573, 99584, 99618, 99673, 99756, 99771, 99846, 99887, 99905, 99914, 100085, 100122,
        100388, 100413, 100441, 100499, 100545, 100675, 100682, 100738, 100751, 100795, 100828, 100836, 100883, 100926, 101042, 101219,
        101235, 101303, 101530, 101654, 101721, 101756, 101793, 101818, 101905, 101935, 101971, 102005, 102057, 102241, 102260, 102262,
        102319, 102357, 102390, 102501, 102593, 103244, 103914, 104413, 104944, 104998, 105433, 105435, 105621, 105623, 106324, 106413,
        106422, 106537, 106571, 106704, 106857, 106883, 107310, 107351, 107435, 107456, 107592, 107640, 107760, 107938, 108215, 108540,
        108842, 109351, 109721, 110095, 110165, 110239, 110342, 110981, 111371, 111716, 111911, 112211, 112314, 112383, 112400, 112457,
        112806, 112835, 112906, 113302, 113504, 114920, 115146, 115344, 115409, 115454, 115530, 115538, 115827, 115973, 116197, 116479,
        116939, 116944, 117397, 117576, 118157, 118443, 118623, 118627, 118642, 118711, 118725, 118742, 118747, 118758, 118763, 118847,
        118972, 119904, 119987, 120027, 120076, 120087, 120242, 120342, 120350, 120363, 120382, 120443, 120759, 120807, 120879, 120929,
        120942, 120975, 121024, 121255, 121295, 121377, 121546, 121563, 121597, 121646, 122370, 122549, 122622, 123159, 123280, 123476,
        123910, 124126, 124216, 124376, 124455, 124620, 124653, 124681, 124691, 124757, 124779, 124856, 124913, 124960, 125009, 125099,
        125113, 125120, 125166, 125239, 125245, 125255, 125267, 125359, 125522, 125526, 125767, 125815, 125816, 125825, 125948, 125963,
        126084, 126190, 126204, 126217, 126259, 126288, 126305, 126353, 126549, 126801, 126898, 126991, 127000, 127339, 127386, 127408,
        127425, 127546, 127683, 127715, 128008, 128127, 128195, 128211, 128293, 128325, 128376, 128399, 128564, 128685, 128692, 128754,
        128787, 128797, 128842, 128917, 129072, 129166, 129237, 129465, 129587, 129588, 129632, 129652, 129653, 129673, 129795, 129816,
        129835, 129852, 129940, 130002, 130023, 130031, 130182, 130348, 130372, 130395, 130500, 130558, 130657, 130658, 130748, 130761,
        130771, 130810, 130925, 130932, 131088, 131143, 131160, 131270, 132023, 132129, 132132
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
        45767, 128922, 131071
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
        69, 188, 485, 592, 950, 1097, 1386, 1526, 1601, 1638, 1797, 1910, 2238, 2414, 2840, 2973,
        3226, 3381, 3915, 4536, 5682, 6276, 6582, 7133, 7836, 8142, 8293, 8374, 8729, 9030, 9125, 9195,
        9273, 9348, 9595, 9786, 10086, 10349, 10442, 10572, 10751, 11010, 11303, 11584, 12553, 12564, 12643, 13063,
        13206, 13379, 13684, 13888, 14426, 14623, 14901, 16654, 16888, 16937, 16959, 17086, 17519, 17527, 17668, 17968,
        18845, 19068, 20966, 21926, 22238, 22962, 22998, 23603, 23763, 26020, 27242, 27458, 29374, 30479, 30858, 32502,
        33516, 33692, 34310, 34496, 35085, 36570, 41181, 41534, 43578, 45238, 46803, 47335, 52957, 53895, 54890, 60752,
        60849, 63957, 70183, 71662, 73917, 75592, 78181, 78402, 78549, 78713, 79276, 79625, 79998, 80444, 80637, 80677,
        81524, 81802, 81891, 82028, 82149, 82487, 82569, 83151, 83514, 85811, 85814, 85927, 86171, 86265, 86389, 86429,
        86503, 86510, 86553, 86646, 86714, 86858, 86877, 86903, 86977, 87005, 87122, 87200, 87333, 87469, 88392, 88535,
        88593, 88881, 88995, 89032, 89147, 89524, 89568, 89603, 89812, 89858, 89931, 89985, 91057, 91064, 91127, 91240,
        91259, 91363, 91522, 91672, 91718, 91777, 91987, 91990, 92228, 92379, 92425, 92921, 93065, 93382, 93891, 94382,
        94478, 96378, 96894, 97303, 97759, 97795, 99209, 99251, 99435, 99456, 99617, 99774, 100049, 100138, 100475, 100824,
        101003, 101147, 101540, 101545, 101618, 101672, 101743, 101769, 101876, 101982, 102521, 104361, 104966, 105684, 105745, 105868,
        107246, 108523, 111334, 113384, 114016, 116157, 116242, 117856, 120645, 120853, 123303, 123934, 124664, 125112, 125404, 125568,
        125735, 126127, 126378, 126393, 127346, 127510, 128104, 128332, 128402, 128426, 128429, 128618, 129156, 129230, 129280, 129290,
        129704, 129970, 130019, 130401, 130451, 130585, 130780, 130813, 130905, 131047, 131235, 131270, 132131
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
        22, 29, 390, 853, 1654, 1737, 2709, 2973, 3106, 3399, 4615, 5669, 5967, 6276, 6571, 7220,
        7391, 9030, 9447, 10442, 10451, 10471, 11303, 11996, 12306, 12716, 12755, 12778, 12801, 12973, 12988, 13206,
        13256, 13651, 16135, 16293, 16489, 16635, 16648, 16685, 17300, 17336, 17663, 17829, 17946, 18010, 20268, 21615,
        22377, 23077, 24243, 25966, 26389, 29158, 30359, 32151, 33344, 40439, 45003, 47312, 50212, 53131, 53814, 55585,
        59559, 59724, 61542, 62136, 65166, 66493, 66662, 67251, 69197, 69399, 72089, 73698, 74664, 75062, 75211, 75678,
        75732, 76118, 77124, 77292, 78138, 78297, 78549, 78560, 78806, 79199, 80684, 80879, 81138, 81252, 81874, 82148,
        82235, 82288, 82538, 82551, 82622, 84201, 84214, 85740, 86028, 86474, 86547, 86553, 86608, 86717, 86870, 87052,
        87163, 87211, 87419, 87591, 88559, 88596, 88738, 88855, 88915, 89222, 89263, 89284, 89412, 89535, 89568, 89776,
        89931, 89996, 91138, 91243, 91303, 91540, 91557, 91590, 91717, 91798, 91990, 92104, 92132, 92425, 92657, 92772,
        93004, 93045, 93435, 93685, 94023, 94217, 94537, 97960, 98284, 99122, 99209, 99448, 100008, 100261, 100757, 101012,
        101167, 101483, 101587, 101621, 101666, 101668, 101672, 101982, 101994, 102025, 102341, 102348, 104836, 107806, 109057, 109117,
        109997, 112202, 113663, 115697, 117397, 117523, 118242, 121822, 123297, 123323, 124276, 124857, 125170, 125278, 125333, 125337,
        125354, 125604, 126165, 126400, 127119, 127350, 127960, 128123, 129236, 129274, 130089, 130481, 130749, 130839, 130967, 131015,
        132131
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
        12888, 89011, 101905
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
        29, 497, 2338, 3106, 3399, 3764, 6276, 6571, 7457, 8046, 9555, 9733, 10086, 10451, 12867, 13465,
        14993, 16293, 16489, 16635, 17336, 17416, 17663, 18010, 21293, 21451, 21678, 21835, 24169, 25238, 27273, 27865,
        29148, 29158, 30359, 32013, 35920, 37983, 40677, 43489, 43714, 45024, 45393, 46915, 47884, 50212, 50375, 50778,
        51907, 53211, 56810, 57366, 57462, 58773, 59797, 65166, 66417, 66493, 68876, 69399, 71191, 76071, 76210, 77292,
        79065, 79275, 80703, 80910, 81571, 81874, 82636, 82709, 82816, 85923, 86285, 86478, 86608, 86717, 87163, 87318,
        87414, 88578, 88686, 88693, 88855, 88943, 89008, 89144, 89148, 89289, 89776, 89791, 89904, 91138, 91323, 91499,
        91590, 91827, 91857, 91864, 92104, 92273, 92688, 93018, 93067, 93249, 93458, 93922, 94023, 94402, 96164, 99122,
        99291, 99691, 99880, 100617, 100736, 100821, 100994, 101069, 101083, 101223, 101290, 101587, 101591, 101605, 101621, 101762,
        101792, 101968, 101982, 102025, 102056, 102115, 102430, 106788, 107588, 110316, 115697, 117208, 117397, 120600, 120937, 123251,
        124172, 124444, 124473, 124651, 125041, 125170, 125418, 125515, 126115, 126219, 126267, 126747, 127373, 129232, 129290, 129415,
        129471, 130237, 130749, 130758, 130762, 130919, 131079, 131125, 131270, 132034
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
        74695, 77163, 100604, 106949
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
        493, 2666, 3653, 4600, 4899, 5528, 6631, 8068, 14127, 17753, 22511, 29925, 37352, 38720, 42089, 46508,
        46554, 48006, 51748, 54117, 54627, 55040, 55285, 56584, 57270, 58032, 58048, 61962, 63953, 65071, 66525, 70184,
        70198, 72141, 72173, 74882, 80914, 81709, 81851, 93637, 94022, 96323, 97518, 100321, 101540, 101571, 101747, 101844,
        105416, 106785, 107336, 107532, 107811, 107877, 108635, 111117, 116088, 119778, 125130, 127802, 129200, 131465, 132127
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
        640, 745, 951, 985, 1197, 1386, 1400, 1537, 1691, 1738, 1760, 2015, 2019, 2037, 2128, 2219,
        2387, 2449, 2466, 2680, 2723, 2772, 2899, 2996, 3026, 3065, 3108, 3263, 3629, 3643, 3669, 3773,
        3797, 3834, 3857, 3913, 3915, 3956, 3962, 4054, 4058, 4122, 4126, 4165, 4324, 4406, 4680, 4731,
        4735, 4743, 4756, 4788, 4820, 4913, 4929, 4961, 5018, 5081, 5086, 5088, 5117, 5133, 5139, 5161,
        5205, 5272, 5301, 5359, 5775, 5795, 5806, 5846, 5905, 5943, 5958, 6003, 6143, 6232, 6253, 6319,
        6351, 6506, 6582, 6637, 6640, 6653, 6713, 6878, 6887, 6898, 7024, 7076, 7155, 7241, 7261, 7314,
        7335, 7367, 7397, 7454, 7552, 7607, 7614, 7622, 7753, 7759, 8001, 8021, 8036, 8096, 8142, 8160,
        8210, 8279, 8357, 8409, 8414, 8424, 8425, 8502, 8674, 8894, 9099, 9189, 9348, 9352, 9405, 9451,
        9625, 9727, 10046, 10066, 10535, 10782, 10870, 10897, 10904, 10973, 11012, 11027, 11050, 11100, 11251, 11413,
        11488, 11602, 11644, 11681, 11758, 11890, 11943, 12149, 12227, 12276, 12343, 12532, 12840, 13040, 13043, 13184,
        13226, 13230, 13255, 13412, 13517, 13565, 13572, 13597, 13731, 13884, 13918, 14004, 14132, 14494, 14592, 15062,
        15136, 15177, 15344, 15417, 15576, 15777, 15787, 15958, 16193, 16378, 16410, 16654, 16680, 16770, 16820, 16897,
        17050, 17150, 17441, 17576, 17580, 17604, 17759, 17978, 17994, 18095, 18116, 18302, 18354, 18378, 18569, 18913,
        18952, 18972, 18993, 19066, 19393, 19516, 19753, 19868, 20005, 20023, 20135, 20176, 20279, 20367, 20663, 20702,
        20820, 20886, 20989, 21064, 21098, 21190, 21232, 21277, 21330, 21352, 21413, 21472, 21509, 21614, 21730, 21803,
        22213, 22434, 22467, 22488, 22579, 22686, 22715, 22790, 22820, 22916, 23031, 23032, 23046, 23076, 23255, 23681,
        23928, 24341, 24535, 24582, 24701, 24713, 24737, 24867, 25028, 25782, 25978, 26002, 26208, 26457, 26577, 26687,
        26980, 27170, 27253, 27401, 27449, 27655, 27773, 28238, 28745, 28875, 29038, 29095, 29159, 29486, 29716, 29799,
        30555, 30637, 30719, 30729, 31315, 32031, 32464, 32550, 32620, 32752, 32909, 33197, 33860, 34203, 34483, 34523,
        35002, 35262, 35322, 35330, 35741, 35754, 35892, 36123, 36588, 36912, 37030, 37228, 37323, 37736, 37804, 37930,
        38028, 38119, 38279, 38889, 38922, 39114, 39423, 39496, 39572, 39588, 39885, 40342, 40346, 40452, 40693, 40698,
        40795, 40815, 41664, 41872, 42157, 42913, 42965, 43136, 43249, 43277, 43296, 43402, 43564, 43891, 44538, 44611,
        45407, 45495, 45765, 45838, 46001, 46110, 48167, 48223, 48498, 48762, 48922, 49691, 50173, 50311, 50586, 50603,
        51374, 51794, 51800, 51820, 52391, 53269, 55290, 55796, 55939, 56082, 56283, 56480, 56530, 56658, 56798, 57350,
        57520, 57545, 58545, 58937, 59043, 59363, 59611, 60398, 60541, 61161, 61807, 62365, 62514, 62727, 63307, 63518,
        65202, 65667, 65753, 65859, 66134, 66574, 66653, 66705, 67088, 67334, 67588, 67793, 68358, 68379, 68672, 68759,
        69101, 69248, 69663, 69840, 70124, 70653, 70667, 70929, 70998, 71121, 71692, 72189, 72271, 72951, 73558, 74360,
        74615, 74947, 75027, 75127, 75484, 75493, 75671, 76039, 76087, 76244, 76252, 76575, 76697, 76985, 77534, 77640,
        78379, 78528, 78648, 78836, 78931, 79104, 79111, 79125, 79468, 79500, 79707, 79714, 79743, 79786, 79891, 79965,
        80147, 80190, 80224, 80238, 80261, 80685, 80788, 80971, 81061, 81224, 81446, 81588, 81610, 81681, 81749, 81806,
        81835, 82162, 83180, 83692, 84078, 84253, 84294, 84557, 84655, 84678, 84963, 85023, 85244, 85380, 85551, 85557,
        85595, 85735, 85749, 85811, 85813, 85906, 86033, 86191, 86413, 86429, 86495, 86508, 86525, 86747, 86829, 86842,
        86978, 87354, 87361, 87376, 87439, 87766, 87901, 87933, 88161, 88194, 88261, 88406, 88459, 88753, 88767, 88973,
        89120, 89133, 89175, 89796, 89823, 90230, 90411, 90566, 90804, 91093, 91290, 91568, 91667, 91708, 91764, 91781,
        92227, 92392, 92478, 92662, 92901, 92930, 93001, 93046, 93100, 93185, 93209, 93758, 93784, 93964, 94133, 94198,
        94296, 94309, 94587, 94611, 94823, 94834, 94849, 95056, 95101, 95865, 97888, 98258, 98723, 98771, 99498, 99766,
        99886, 100862, 101087, 101089, 101456, 101519, 101822, 101827, 102057, 102675, 102791, 102919, 102949, 103969, 104361, 104365,
        104770, 105487, 106029, 106053, 106059, 106260, 107756, 108529, 108694, 108766, 108878, 110295, 110699, 110795, 111349, 111481,
        112134, 112608, 112628, 112707, 113001, 113181, 113257, 113456, 113670, 113687, 113822, 114085, 115525, 115662, 115934, 115936,
        116622, 116821, 116878, 116982, 117104, 117138, 117211, 117307, 117560, 117620, 117820, 118144, 118294, 118356, 118599, 118627,
        118946, 119120, 119229, 119350, 119443, 119525, 119548, 120134, 120787, 121916, 121987, 122144, 122303, 122611, 122712, 122822,
        123382, 124212, 124949, 124970, 124980, 125024, 125167, 125520, 125861, 126061, 126255, 126415, 126660, 127745, 128535, 129150,
        130214, 130246, 130628, 130804, 130917, 131110, 131146, 131278, 131997
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
