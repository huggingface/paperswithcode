-- Method gap fill 2026-11-10, group D (reinforcement learning): 10 methods.
-- TRPO (arXiv 1502.05477), DDPG (1509.02971), TD3 (1802.09477) and A3C
-- (1602.01783) have introducing papers. Policy gradient, actor-critic,
-- behavior cloning, inverse RL, experience replay and reward shaping grew out of
-- many earlier works (Williams 1992 / Sutton et al. 1999, Barto et al. 1983,
-- Pomerleau 1989, Ng & Russell 2000, Lin 1992, Ng et al. 1999), none on arXiv,
-- so they keep source_paper_id NULL (see add_neural_architecture_search_method.sql)
-- and their paper links below are reviewed title/abstract candidates.
-- A2C is an alias of the general actor-critic row; Prioritized Experience Replay
-- (1511.05952) stays a paper credited in the experience-replay description.
-- Hero images are imported separately with import_entity_image.py.
--
-- Keywords avoid bare abbreviations: "TD3" (would collide with TD3+BC, method
-- td3-bc), "BC", "IRL" (V-IRL, IRL-INR), "A2C" and "PG". IRL is judged in
-- abstracts for the same reason.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'policy-gradient',
    'Policy Gradient',
    'Policy Gradient Methods',
    'Policy gradient methods optimize a parameterized policy directly by gradient ascent on the expected return. The policy gradient theorem writes this gradient as an expectation of the score function ∇ log π(a|s) weighted by the action value or return, so it can be estimated from sampled trajectories without a model of the environment. Williams'' [REINFORCE](/methods/reinforce) (1992) introduced the likelihood-ratio Monte Carlo estimator, and Sutton, McAllester, Singh and Mansour (1999) proved the policy gradient theorem with function approximation. Subtracting a baseline, usually a learned value function, reduces variance and leads to [actor-critic](/methods/actor-critic) methods and advantage estimators such as [GAE](/paper/1506.02438). Natural-gradient and trust-region variants such as [TRPO](/methods/trpo) and [PPO](/methods/ppo) limit how far each update moves the policy, and deterministic policy gradients underlie [DDPG](/methods/ddpg) and [TD3](/methods/td3). Policy gradients handle continuous and stochastic action spaces and are the basis of reinforcement learning for language models, from [RLHF](/methods/rlhf) with PPO to [GRPO](/methods/grpo).',
    'policy gradient, policy-gradient',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://papers.nips.cc/paper/1713-policy-gradient-methods-for-reinforcement-learning-with-function-approximation',
    'Policy Gradient Methods for Reinforcement Learning with Function Approximation',
    NULL,
    NULL,
    NULL,
    'always',
    ARRAY['Policy Gradient Method']
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'actor-critic',
    'Actor-Critic',
    'Actor-Critic',
    'Actor-critic methods combine a policy, the actor, with a learned value function, the critic. The critic estimates state or action values, typically by temporal-difference learning, and the actor follows a [policy gradient](/methods/policy-gradient) in which the critic''s estimate, often an advantage A(s, a) = Q(s, a) − V(s), replaces the high-variance Monte Carlo return of [REINFORCE](/methods/reinforce). Barto, Sutton and Anderson (1983) used an adaptive actor and critic to balance a pole, and Konda and Tsitsiklis (2000) analyzed actor-critic algorithms with function approximation. Deep variants include [A3C](/methods/a3c) and its synchronous form A2C (advantage actor-critic), [IMPALA](/paper/1802.01561), the off-policy deterministic methods [DDPG](/methods/ddpg) and [TD3](/methods/td3), and [Soft Actor-Critic](/methods/soft-actor-critic); [PPO](/methods/ppo) is also usually trained as an actor-critic with a value network. Multi-agent methods such as [MADDPG](/paper/1706.02275) pair decentralized actors with a centralized critic.',
    'actor-critic, actor critic, advantage actor-critic, advantage actor critic',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://papers.nips.cc/paper/1786-actor-critic-algorithms',
    'Actor-Critic Algorithms',
    NULL,
    NULL,
    NULL,
    'always',
    ARRAY['Advantage Actor-Critic (A2C)']
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'a3c',
    'A3C',
    'Asynchronous Advantage Actor-Critic (A3C)',
    'Asynchronous Advantage Actor-Critic (A3C) runs many [actor-critic](/methods/actor-critic) agents in parallel, each with its own copy of the environment on a CPU thread, which compute n-step advantage policy gradients and value updates and apply them asynchronously to shared network parameters. Because the parallel actors explore different parts of the environment at once, their updates are less correlated, which stabilizes on-policy deep reinforcement learning without the [experience replay](/methods/experience-replay) buffer of [DQN](/methods/dqn); an entropy bonus on the policy encourages exploration. The paper also introduced asynchronous one-step and n-step Q-learning and Sarsa, and A3C, the best of these, surpassed the previous Atari state of the art in half the training time on a single multi-core CPU while also learning continuous motor control and 3D maze navigation. A2C, the synchronous batched variant popularized by OpenAI Baselines, performs as well while using GPUs more efficiently, and [IMPALA](/paper/1802.01561) scaled the distributed actor-learner design further.',
    'asynchronous advantage actor-critic, asynchronous advantage actor critic, A3C',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1602.01783'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Asynchronous Methods for Deep Reinforcement Learning',
    'https://github.com/openai/baselines/tree/master/baselines/a2c',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'trpo',
    'TRPO',
    'Trust Region Policy Optimization (TRPO)',
    'Trust Region Policy Optimization (TRPO) is a [policy gradient](/methods/policy-gradient) method that improves a policy by maximizing a surrogate objective, the importance-weighted advantage of the new policy under the old policy''s state distribution, subject to a limit on the average [KL divergence](/methods/kl-divergence) between the old and new policies. Schulman et al. derived it from a lower bound that guarantees monotonic improvement, and solve each constrained step approximately with conjugate gradient on Fisher-vector products followed by a line search, a practical natural policy gradient for large neural network policies. With little hyperparameter tuning, TRPO learned simulated swimming, hopping and walking gaits and played Atari games from raw pixels. Its constrained update inspired [PPO](/methods/ppo), which replaces the hard KL constraint with a clipped objective that needs only first-order optimization, and it served as the policy optimizer in [GAE](/paper/1506.02438) and [GAIL](/methods/gail).',
    'trust region policy optimization, trust region policy optimisation, trust-region policy optimization, TRPO',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2015,
    (SELECT id FROM papers WHERE arxiv_id = '1502.05477'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Trust Region Policy Optimization',
    'https://github.com/openai/baselines/tree/master/baselines/trpo_mpi',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'ddpg',
    'DDPG',
    'Deep Deterministic Policy Gradient (DDPG)',
    'Deep Deterministic Policy Gradient (DDPG) is a model-free, off-policy [actor-critic](/methods/actor-critic) algorithm for continuous action spaces. It combines the deterministic policy gradient of Silver et al. (2014), in which a deterministic actor μ(s) moves along the gradient of the critic''s Q(s, μ(s)), with the ingredients that stabilized [DQN](/methods/dqn): an [experience replay](/methods/experience-replay) buffer and slowly updated target copies of the actor and critic, plus [batch normalization](/methods/batch-normalization) and temporally correlated exploration noise. With one algorithm, network architecture and set of hyperparameters it solved more than 20 simulated physics tasks, including cartpole swing-up, dexterous manipulation, legged locomotion and car driving, many directly from pixels. DDPG overestimates Q-values and is sensitive to hyperparameters, which [TD3](/methods/td3) addresses; it remains a common continuous-control baseline and was extended to multi-agent settings by [MADDPG](/paper/1706.02275).',
    'deep deterministic policy gradient, DDPG',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2015,
    (SELECT id FROM papers WHERE arxiv_id = '1509.02971'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Continuous control with deep reinforcement learning',
    'https://github.com/openai/baselines/tree/master/baselines/ddpg',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'td3',
    'TD3',
    'Twin Delayed Deep Deterministic Policy Gradient (TD3)',
    'Twin Delayed Deep Deterministic Policy Gradient (TD3) is an off-policy [actor-critic](/methods/actor-critic) algorithm for continuous control that fixes the value overestimation of [DDPG](/methods/ddpg). Fujimoto, van Hoof and Meger showed that function approximation error makes actor-critic critics overestimate values, as in Q-learning, and made three changes: clipped double Q-learning, which trains two critics and uses the smaller estimate in the target; delayed policy updates, which update the actor and target networks less often than the critics; and target policy smoothing, which adds clipped noise to the target action. TD3 outperformed DDPG and contemporary methods on every MuJoCo locomotion task it was tested on and, with [Soft Actor-Critic](/methods/soft-actor-critic), became a standard continuous-control baseline. Its offline variant [TD3+BC](/methods/td3-bc) adds a [behavior cloning](/methods/behavior-cloning) term to the actor loss.',
    'twin delayed deep deterministic policy gradient, twin delayed DDPG, twin-delayed DDPG',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2018,
    (SELECT id FROM papers WHERE arxiv_id = '1802.09477'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Addressing Function Approximation Error in Actor-Critic Methods',
    'https://github.com/sfujim/TD3',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'behavior-cloning',
    'Behavior Cloning',
    'Behavior Cloning (BC)',
    'Behavior cloning (BC) is the simplest form of [imitation learning](/methods/imitation-learning): it treats expert demonstrations as a supervised dataset of observation-action pairs and trains a policy to predict the expert''s action, with no reward signal and no further interaction with the environment. Pomerleau''s ALVINN (1989) learned to steer a vehicle this way, Michie, Sammut and colleagues named the approach behavioural cloning in the early 1990s, and NVIDIA''s [end-to-end driving network](/paper/1604.07316) is a well-known deep example. Because the policy''s own mistakes lead it to states the expert never visited, errors compound over the horizon; [DAgger](/methods/dagger) counters this covariate shift with interactive expert labels, while [GAIL](/methods/gail) and [inverse reinforcement learning](/methods/inverse-reinforcement-learning) match the expert''s state distribution instead. Modern visuomotor robot policies such as [ACT](/methods/act), [Diffusion Policy](/methods/diffusion-policy) and many [VLA](/methods/vla) models are trained largely by behavior cloning on teleoperated demonstrations, and BC terms regularize offline RL methods such as [TD3+BC](/methods/td3-bc). [Codevilla et al.](/paper/1904.08980) analyze its limitations for autonomous driving.',
    'behavior cloning, behavioral cloning, behaviour cloning, behavioural cloning, behavior-cloning, behavioral-cloning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://papers.nips.cc/paper/95-alvinn-an-autonomous-land-vehicle-in-a-neural-network',
    'ALVINN: An Autonomous Land Vehicle in a Neural Network',
    NULL,
    NULL,
    NULL,
    'always',
    ARRAY['Behavioral Cloning', 'Behaviour Cloning']
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'inverse-reinforcement-learning',
    'Inverse Reinforcement Learning',
    'Inverse Reinforcement Learning (IRL)',
    'Inverse reinforcement learning (IRL) recovers a reward function that explains observed expert behavior, the reverse of reinforcement learning, which learns behavior from a given reward. Russell (1998) posed the problem and Ng and Russell (2000) gave the first algorithms, noting that it is ill-posed because many rewards, including trivial ones, make the same behavior optimal. Apprenticeship learning (Abbeel and Ng, 2004) matched the expert''s feature expectations, and maximum-entropy IRL (Ziebart et al., 2008) resolved the ambiguity with a probabilistic model of near-optimal trajectories, which later deep methods such as guided cost learning and adversarial IRL (AIRL) extended to neural network rewards. A recovered reward can be optimized with standard reinforcement learning and often transfers to new dynamics better than a policy learned by [behavior cloning](/methods/behavior-cloning). IRL is a branch of [imitation learning](/methods/imitation-learning) closely related to [GAIL](/methods/gail), which matches the expert''s occupancy measure without an explicit reward, and to learning a [reward model](/methods/reward-model) from human preferences in [RLHF](/methods/rlhf).',
    'inverse reinforcement learning, inverse-reinforcement learning, inverse RL',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://ai.stanford.edu/~ang/papers/icml00-irl.pdf',
    'Algorithms for Inverse Reinforcement Learning',
    NULL,
    NULL,
    NULL,
    'judge',
    ARRAY['Inverse RL']
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'experience-replay',
    'Experience Replay',
    'Experience Replay',
    'Experience replay stores an agent''s past transitions (state, action, reward, next state) in a buffer and trains on minibatches sampled from it, instead of learning only from the latest transition. Reusing each experience many times improves sample efficiency, and sampling at random breaks the strong correlation between consecutive transitions, which stabilizes the training of neural network value functions. Lin (1992) introduced the idea for reinforcement learning agents, and [DQN](/methods/dqn) made it, together with target networks, a core ingredient of deep RL. It requires an off-policy learner such as [Q-learning](/methods/q-learning), [DDPG](/methods/ddpg), [TD3](/methods/td3) or [Soft Actor-Critic](/methods/soft-actor-critic). Variants sample transitions in proportion to their TD error ([Prioritized Experience Replay](/paper/1511.05952)), relabel the goals of failed episodes ([Hindsight Experience Replay](/paper/1707.01495)) or share one buffer among many distributed actors. The same idea of replaying stored examples from earlier tasks is a standard defense against catastrophic forgetting in continual learning.',
    'experience replay, replay buffer',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1007/BF00992699',
    'Self-improving reactive agents based on reinforcement learning, planning and teaching',
    NULL,
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'reward-shaping',
    'Reward Shaping',
    'Reward Shaping',
    'Reward shaping adds extra reward terms to a reinforcement learning problem to guide the agent toward the intended behavior faster, typically when the task reward is sparse or delayed, for example by rewarding progress toward a goal. Poorly chosen shaping rewards can change which policy is optimal and invite [reward hacking](/methods/reward-hacking); Ng, Harada and Russell (1999) proved that potential-based shaping, which adds F(s, s'') = γΦ(s'') − Φ(s) for a potential function Φ over states, is the only form that leaves the optimal policies of every MDP unchanged. Later work extended potential-based shaping to state-action and time-varying potentials, learned shaping functions, and intrinsic exploration rewards such as [curiosity](/paper/1705.05363) and [random network distillation](/paper/1810.12894). In language model post-training, shaping terms for format, length or intermediate steps are added to outcome rewards from a [reward model](/methods/reward-model) or verifier in methods such as [GRPO](/methods/grpo).',
    'reward shaping, reward-shaping',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf',
    'Policy Invariance Under Reward Transformations: Theory and Application to Reward Shaping',
    NULL,
    NULL,
    NULL,
    'always',
    ARRAY['Potential-Based Reward Shaping']
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Introduced banners for the four methods with a source paper.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'a3c' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'trpo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'ddpg' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'td3' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;


-- Reviewed paper links (2026-11-10). Candidates: bounded title/abstract regex
-- matches of each name and its long form, plus, for the four sourced methods,
-- local Semantic Scholar citers of the source paper. Positives use, extend,
-- analyze, survey or compare against the method; regex hits that only contrast
-- with it, or use the abbreviation in another sense, and citers whose title and
-- abstract do not name the method become durable exclusions so the keyword and
-- reference backfills do not re-link them.

-- policy-gradient: 477 links, 7 exclusions.
CREATE TEMP TABLE policy_gradient_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'policy-gradient'
  AND p.id IN (
        158, -- 1502.05477 Trust Region Policy Optimization
        200, -- 1506.02438 High-Dimensional Continuous Control Using Generalized Advantage Estima
        239, -- 1509.02971 Continuous control with deep reinforcement learning
        611, -- 1703.03400 Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks
        745, -- 1706.02275 Multi-Agent Actor-Critic for Mixed Cooperative-Competitive Environment
        804, -- 1707.06347 Proximal Policy Optimization Algorithms
        881, -- 1709.06030 N2N Learning: Network to Network Compression via Policy Gradient Reinf
        892, -- 1709.08430 Towards continuous control of flippers for a multi-terrain robot using
        894, -- 1709.08624 Long Text Generation via Adversarial Training with Leaked Information
        955, -- 1711.02281 Non-Autoregressive Neural Machine Translation
        1021, -- 1712.06567 Deep Neuroevolution: Genetic Algorithms Are a Competitive Alternative
        1620, -- 1811.05869 Large-scale Interactive Recommendation with Tree-structured Policy Gra
        2184, -- 1906.00549 Know More about Each Other: Evolving Dialogue Strategy via Compound As
        2551, -- 1909.07373 Policy Prediction Network: Model-Free Behavior Policy with Model-Based
        2708, -- 1910.09434 Towards a Reinforcement Learning Environment Toolbox for Intelligent E
        2830, -- 1911.08647 Deep Reinforcement Learning in Cryptocurrency Market Making
        3037, -- 2001.10382 Selective Weak Supervision for Neural Information Retrieval
        3049, -- 2001.12004 Neural MMO v1.3: A Massively Multiagent Game Environment for Training
        3196, -- 2003.03983 Pseudo-Convolutional Policy Gradient for Sequence-to-Sequence Lip-Read
        3792, -- 2006.13566 DISK: Learning local features with policy gradient
        3801, -- 2006.14171 A Closer Look at Invalid Action Masking in Policy Gradient Algorithms
        4769, -- 2012.11635 A Distributional Approach to Controlled Text Generation
        4842, -- 2101.00336 Neural Architecture Search via Combinatorial Multi-Armed Bandit
        4885, -- 2101.04229 Implicit Unlikelihood Training: Improving Neural Text Generation with
        6017, -- 2106.08942 Revisiting the Weaknesses of Reinforcement Learning for Neural Machine
        6582, -- 2109.04325 Learning Opinion Summarizers by Selecting Informative Reviews
        8063, -- 2202.12847 Building a 3-Player Mahjong AI using Deep Reinforcement Learning
        8740, -- 2204.07615 TabNAS: Rejection Sampling for Neural Architecture Search on Tabular D
        9333, -- 2206.01153 Multi-View Active Fine-Grained Recognition
        9771, -- 2207.05742 Reactive Exploration to Cope with Non-Stationarity in Lifelong Reinfor
        9829, -- 2207.09090 Actor-Critic based Improper Reinforcement Learning
        10452, -- 2209.14610 Dynamic Prompt Learning via Policy Gradient for Semi-structured Mathem
        10531, -- 2210.01241 Is Reinforcement Learning (Not) for Natural Language Processing: Bench
        11015, -- 2210.13011 On Many-Actions Policy Gradient
        11394, -- 2211.09120 AdaMAE: Adaptive Masking for Efficient Spatiotemporal Learning with Ma
        12132, -- 2212.10439 Policy Gradient in Robust MDPs with Global Convergence Guarantee
        12534, -- 2301.10932 On the Global Convergence of Risk-Averse Policy Gradient Methods with
        12698, -- 2301.13362 Optimizing DDPM Sampling with Shortcut Fine-Tuning
        12795, -- 2302.01399 Accelerating Policy Gradient by Estimating Value Function from Prior C
        12820, -- 2302.01734 Stochastic Policy Gradient Methods: Improved Sample Complexity for Fis
        13144, -- 2302.08215 Aligning Language Models with Preferences through f-divergence Minimiz
        13309, -- 2302.12822 Automatic Prompt Augmentation and Selection with Chain-of-Thought from
        13540, -- 2303.03832 MAP-Elites with Descriptor-Conditioned Gradients and Archive Distillat
        15073, -- 2305.00303 A Coupled Flow Approach to Imitation Learning
        15835, -- 2305.12239 Off-Policy Average Reward Actor-Critic with Deterministic Policy Searc
        15939, -- 2305.13301 Training Diffusion Models with Reinforcement Learning
        15998, -- 2305.13795 Proximal Policy Gradient Arborescence for Quality Diversity Reinforcem
        16123, -- 2305.14718 Leftover Lunch: Advantage-based Offline Reinforcement Learning for Lan
        16219, -- 2305.15193 Adaptive Policy Learning to Additional Tasks
        16332, -- 2305.16381 DPOK: Reinforcement Learning for Fine-tuning Text-to-Image Diffusion M
        16395, -- 2305.17083 A Policy Gradient Method for Confounded POMDPs
        16598, -- 2305.19044 Exploring the Promise and Limits of Real-Time Recurrent Learning
        16670, -- 2305.19922 Representation-Driven Reinforcement Learning
        16690, -- 2305.20081 Efficient Diffusion Policies for Offline Reinforcement Learning
        16892, -- 2306.01854 Reinforcement Learning with General Utilities: Simpler Variance Reduct
        16897, -- 2306.01920 Context-Aware Bayesian Network Actor-Critic Methods for Cooperative Mu
        17515, -- 2306.09554 Low-Switching Policy Gradient with Exploration via Online Sensitivity
        17629, -- 2306.11626 Soft Robust MDPs and Risk-Sensitive MDPs: Equivalence, Policy Gradient
        18194, -- 2307.06175 Learning Decentralized Partially Observable Mean Field Control for Art
        18290, -- 2307.08168 Enabling Efficient, Reliable Real-World Reinforcement Learning with Ap
        18452, -- 2307.10710 Reparameterized Policy Learning for Multimodal Trajectory Optimization
        18611, -- 2307.13372 Submodular Reinforcement Learning
        18856, -- 2308.01194 Improving Generalization in Visual Reinforcement Learning via Conflict
        18918, -- 2308.02151 Retroformer: Retrospective Large Language Agents with Policy Gradient
        21132, -- 2310.00212 Pairwise Proximal Policy Optimization: Harnessing Relative Feedback fo
        21289, -- 2310.01737 Blending Imitation and Reinforcement Learning for Robust Policy Improv
        21373, -- 2310.02671 Beyond Stationarity: Convergence Analysis of Stochastic Softmax Policy
        21381, -- 2310.02782 Discovering General Reinforcement Learning Algorithms with Adversarial
        21509, -- 2310.04407 Policy-Gradient Training of Language Models for Ranking
        21777, -- 2310.07297 Score Regularized Policy Optimization through Diffusion Behavior
        22297, -- 2310.13639 Contrastive Preference Learning: Learning from Human Feedback without
        22675, -- 2310.18338 Small Language Models Fine-tuned to Coordinate Larger Language Models
        22824, -- 2310.20703 Vanishing Gradients in Reinforcement Finetuning of Language Models
        23036, -- 2311.04082 Time-Efficient Reinforcement Learning with Stochastic Stateful Policie
        23298, -- 2311.08290 On-Policy Policy Gradient Reinforcement Learning Without On-Policy Sam
        23315, -- 2311.08384 Offline Data Enhanced On-Policy Policy Gradient with Provable Guarante
        23741, -- 2311.14768 AdaDiff: Adaptive Step Selection for Fast Diffusion Models
        24550, -- 2312.05674 Position control of an acoustic cavitation bubble by reinforcement lea
        25759, -- 2401.06604 Identifying Policy Gradient Subspaces
        26249, -- 2401.13662 The Definitive Guide to Policy Gradients in Deep Reinforcement Learnin
        26769, -- 2402.02479 BRAIn: Bayesian Reward-conditioned Amortized Inference for natural lan
        27822, -- 2402.14688 Q-Probe: A Lightweight Approach to Reward Maximization for Language Mo
        28271, -- 2403.00858 Direct Alignment of Draft Model for Speculative Decoding with Chat-Fin
        30213, -- 2404.07525 Enhancing Policy Gradient with the Polyak Step-Size Adaption
        30572, -- 2404.12754 Adaptive Regularization of Representation Rank as an Implicit Constrai
        30784, -- 2404.16767 REBEL: Reinforcement Learning via Regressing Relative Rewards
        30906, -- 2404.18988 Markovian Transformers for Informative Language Modeling
        33422, -- 2406.14568 Policy Gradient-Driven Noise Mask
        33790, -- 2406.19185 Contrastive Policy Gradient: Aligning LLMs on sequence-level scores in
        34072, -- 2407.02759 Multi-Scenario Combination Based on Multi-Agent Reinforcement Learning
        34367, -- 2407.06642 Powerful and Flexible: Personalized Text-to-Image Generation via Reinf
        34886, -- 2407.13146 PG-Rainbow: Using Distributional Reinforcement Learning in Policy Grad
        35537, -- 2408.02295 Generalized Gaussian Temporal Difference Error for Uncertainty-aware R
        36459, -- 2409.00588 Diffusion Policy Policy Optimization
        37803, -- 2410.02743 MA-RLHF: Reinforcement Learning from Human Feedback with Macro Actions
        38229, -- 2410.07745 StepTool: A Step-grained Reinforcement Learning Framework for Tool Lea
        40346, -- 2411.15370 Deep Policy Gradient Methods Without Batch Updates, Target Networks, o
        40697, -- 2411.19583 Solving Rubik's Cube Without Tricky Sampling
        42277, -- 2412.20367 Enhancing Code LLMs with Reinforcement Learning in Code Generation: A
        43564, -- 2502.01384 Fine-Tuning Discrete Diffusion Models with Policy Gradient Methods
        43624, -- 2502.02014 Analytical Lyapunov Function Discovery: An RL-based Generative Approac
        44329, -- 2502.11433 FLAG-Trader: Fusion LLM-Agent with Gradient-based Reinforcement Learni
        45668, -- 2503.06171 ROCM: RLHF on consistency models
        47234, -- 2504.02546 GPG: A Simple and Strong Reinforcement Learning Baseline for Model Rea
        47733, -- 2504.11343 A Minimalist Approach to LLM Reasoning: from Rejection Sampling to Rei
        47790, -- 2504.12216 d1: Scaling Reasoning in Diffusion Large Language Models via Reinforce
        48220, -- 2504.20571 Reinforcement Learning for Reasoning in Large Language Models with One
        48235, -- 2504.20834 Token-Efficient RL for LLM Reasoning
        48637, -- 2505.07538 Selftok: Discrete Visual Tokens of Autoregression, by Diffusion, and f
        48956, -- 2505.12370 Enhancing Visual Grounding for GUI Agents via Self-Evolutionary Reinfo
        48966, -- 2505.12504 CPGD: Toward Stable Rule-based Reinforcement Learning for Language Mod
        49049, -- 2505.13308 Seek in the Dark: Reasoning via Test-Time Instance-Level Policy Gradie
        49170, -- 2505.14403 Unearthing Gems from Stones: Policy Optimization with Negative Sample
        49245, -- 2505.14970 Self-Evolving Curriculum for LLM Reasoning
        49333, -- 2505.15809 MMaDA: Multimodal Large Diffusion Language Models
        49526, -- 2505.17508 On the Design of KL-Regularized Policy Gradient Algorithms for LLM Rea
        49682, -- 2505.19094 SATORI-R1: Incentivizing Multimodal Reasoning with Spatial Grounding a
        49766, -- 2505.19731 Accelerating Nash Learning from Human Feedback via Mirror Prox
        50020, -- 2505.22617 The Entropy Mechanism of Reinforcement Learning for Reasoning Language
        50322, -- 2506.00539 ARIA: Training Language Agents with Intention-Driven Reward Aggregatio
        50379, -- 2506.01347 The Surprising Effectiveness of Negative Reinforcement in LLM Reasonin
        50417, -- 2506.01939 Beyond the 80/20 Rule: High-Entropy Minority Tokens Drive Effective Re
        50437, -- 2506.02208 KDRL: Post-Training Reasoning LLMs via Unified Knowledge Distillation
        51790, -- 2507.06892 Squeeze the Soaked Sponge: Efficient Off-policy Reinforcement Finetuni
        51860, -- 2507.09104 CompassJudger-2: Towards Generalist Judge Model via Verifiable Rewards
        52068, -- 2507.19457 GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learnin
        52631, -- 2509.02522 Implicit Actor Critic Coupling via a Supervised Learning Framework for
        52656, -- 2509.04419 Towards a Unified View of Large Language Model Post-Training
        52734, -- 2509.09265 Harnessing Uncertainty: Entropy-Modulated Policy Gradients for Long-Ho
        52783, -- 2509.13232 Single-stream Policy Optimization
        52792, -- 2509.21268 MMR1: Enhancing Multimodal Reasoning with Variance-Aware Sampling and
        52973, -- 2509.22624 SPARK: Synergistic Policy And Reward Co-Evolving Framework
        53077, -- 2509.22613 Benefits and Pitfalls of Reinforcement Learning for Language Model Pla
        53179, -- 2509.26313 One-Token Rollout: Guiding Supervised Fine-Tuning of LLMs with Policy
        53207, -- 2510.01132 A Practitioner's Guide to Multi-turn Agentic Reinforcement Learning
        53248, -- 2510.04072 Slow-Fast Policy Optimization: Reposition-Before-Update for LLM Reason
        53281, -- 2510.04506 GRACE: Generative Representation Learning via Contrastive Policy Optim
        53382, -- 2510.08425 Reinforcing Diffusion Models by Direct Group Preference Optimization
        53418, -- 2510.08696 Don't Waste Mistakes: Leveraging Negative RL-Groups via Confidence Rew
        53457, -- 2510.09285 Spotlight on Token Perception for Multimodal Reinforcement Learning
        53473, -- 2510.09541 SPG: Sandwiched Policy Gradient for Masked Diffusion Language Models
        53489, -- 2510.07624 From Data to Rewards: a Bilevel Optimization Perspective on Maximum Li
        53516, -- 2510.12635 Memory as Action: Autonomous Context Curation for Long-Horizon Agentic
        53548, -- 2510.06727 Scaling LLM Multi-turn RL with End-to-end Summarization-based Context
        53745, -- 2510.18927 BAPO: Stabilizing Off-Policy Reinforcement Learning for LLMs via Balan
        53848, -- 2510.23393 The Best of N Worlds: Aligning Reinforcement Learning with Best-of-N S
        53908, -- 2510.22319 GRPO-Guard: Mitigating Implicit Over-Optimization in Flow Matching via
        54117, -- 2511.06411 SofT-GRPO: Surpassing Discrete-Token LLM Reinforcement Learning via Gu
        54388, -- 2511.21395 Monet: Reasoning in Latent Visual Space Beyond Images and Language
        54444, -- 2512.01374 Stabilizing Reinforcement Learning with LLMs: Formulation and Practice
        54649, -- 2512.06791 Small-Gain Nash: Certified Contraction to Nash Equilibria in Different
        54894, -- 2512.12623 Reasoning Within the Mind: Dynamic Multimodal Interleaving in Latent S
        55079, -- 2512.22955 Diversity or Precision? A Deep Dive into Next Token Prediction
        55813, -- 2602.05327 ProAct: Agentic Lookahead in Interactive Environments
        55814, -- 2602.05885 Dr. Kernel: Reinforcement Learning Done Right for Triton Kernel Genera
        55825, -- 2602.04884 Reinforced Attention Learning
        55831, -- 2602.05547 Multi-Task GRPO: Reliable LLM Reasoning Across Tasks
        56009, -- 2602.10609 Online Causal Kalman Filtering for Stable and Effective Policy Optimiz
        56167, -- 2602.15620 STAPO: Stabilizing Reinforcement Learning for LLMs by Silencing Rare S
        56301, -- 2602.21534 ARLArena: A Unified Framework for Stable Agentic Reinforcement Learnin
        56506, -- 2602.23440 Truncated Step-Level Sampling with Process Rewards for Retrieval-Augme
        56629, -- 2603.10848 V_{0.5}: Generalist Value Model as a Prior for Sparse RL Rollouts
        57495, -- 2604.06159 Target Policy Optimization
        57543, -- 2604.14265 Reinforcement Learning via Value Gradient Flow
        57583, -- 2604.14258 GFT: From Imitation to Reward Fine-Tuning with Unbiased Group Advantag
        57779, -- 2604.23380 V-GRPO: Online Reinforcement Learning for Denoising Generative Models
        57974, -- 2604.20328 Hybrid Latent Reasoning with Decoupled Policy Optimization
        58383, -- 2604.08423 Synthetic Data for any Differentiable Target
        58546, -- 2603.11321 Hindsight-Anchored Policy Optimization: Turning Failure into Feedback
        58566, -- 2604.02986 Mitigating Reward Hacking in RLHF via Advantage Sign Robustness
        58775, -- 2603.28120 MedLoc-R1: Performance-Aware Curriculum Reward Scheduling for GRPO-Bas
        59105, -- 2603.20526 Does This Gradient Spark Joy?
        59106, -- 2603.20521 Delightful Distributed Policy Gradient
        59393, -- 2603.14608 Delightful Policy Gradient
        59473, -- 2603.12554 Reinforcement Learning for Diffusion LLMs with Entropy-Guided Step Sel
        59507, -- 2603.12248 Matching Features, Not Tokens: Energy-Based Fine-Tuning of Language Mo
        59789, -- 2603.06138 Partial Policy Gradients for RL in LLMs
        59805, -- 2603.05995 TADPO: Reinforcement Learning Goes Off-road
        59813, -- 2603.05923 Learning Next Action Predictors from Human-Computer Interaction
        59975, -- 2603.02701 Graph-GRPO: Stabilizing Multi-Agent Topology Learning via Group Relati
        60002, -- 2510.02692 Fine-Tuning Diffusion Models via Intermediate Distribution Shaping
        60075, -- 2603.01162 Demystifying Group Relative Policy Optimization: Its Policy Gradient i
        60448, -- 2603.06619 Not all tokens are needed(NAT): token efficient reinforcement learning
        60474, -- 2602.17616 Stable Asynchrony: Variance-Controlled Off-Policy RL for LLMs
        60573, -- 2602.15515 The Obfuscation Atlas: Mapping Where Honesty Emerges in RLVR with Dece
        60806, -- 2602.11596 MAPLE: Modality-Aware Post-training and Learning Ecosystem
        60896, -- 2602.10019 ADORA: Training Reasoning Models with Dynamic Advantage Estimation on
        61010, -- 2602.08104 Interpretable Failure Analysis in Multi-Agent Reinforcement Learning S
        61202, -- 2602.05717 Anchored Policy Optimization: Mitigating Exploration Collapse Via Supp
        61303, -- 2602.03940 Autonomous AI Agents for Real-Time Affordable Housing Site Selection:
        61323, -- 2602.03688 TodyComm: Task-Oriented Dynamic Communication for Multi-Round LLM-base
        61329, -- 2602.03584 V_0: A Generalist Value Model for Any Policy at State Zero
        61399, -- 2602.02710 Maximum Likelihood Reinforcement Learning
        61528, -- 2602.02597 ContextEvolve: Multi-Agent Context Compression for Systems Code Optimi
        62022, -- 2601.18795 Reuse your FLOPs: Scaling RL on Hard Problems by Conditioning on Very
        62240, -- 2601.15158 Outcome-Based RL Provably Leads Transformers to Reason, but Only With
        63185, -- 2512.24265 Joint Selection for Large-Scale Pre-Training Data via Policy Gradient-
        64262, -- 2512.17918 QAISim: A Toolkit for Modeling and Simulation of AI in Quantum Cloud C
        64392, -- 2511.23310 OBLR-PO: A Theoretical Framework for Stable Reinforcement Learning
        64983, -- 2511.12033 EARL: Entropy-Aware RL Alignment of LLMs for Reliable RTL Code Generat
        66719, -- 2510.08270 Evaluation of a Robust Control System in Real-World Cable-Driven Paral
        66731, -- 2510.08141 Arbitrary Entropy Policy Optimization: Entropy Is Controllable in Rein
        66858, -- 2510.06214 Stratified GRPO: Handling Structural Heterogeneity in Reinforcement Le
        66980, -- 2510.04182 Thinking on the Fly: Test-Time Reasoning Enhancement via Latent Though
        67020, -- 2510.03515 RAPID: An Efficient Reinforcement Learning Algorithm for Small Languag
        67195, -- 2510.00915 Reinforcement Learning with Verifiable yet Noisy Rewards under Imperfe
        67207, -- 2510.00819 Stabilizing Policy Gradients for Sample-Efficient Reinforcement Learni
        67383, -- 2509.25424 Polychromic Objectives for Reinforcement Learning
        67415, -- 2509.25050 Advantage Weighted Matching: Aligning RL with Pretraining in Diffusion
        67681, -- 2509.22761 MILR: Improving Multimodal Image Generation via Test-Time Latent Reaso
        67706, -- 2509.22115 Learning More with Less: A Dynamic Dual-Level Down-Sampling Framework
        67773, -- 2509.21474 d2: Improved Techniques for Training Reasoning Diffusion Language Mode
        68861, -- 2509.01684 Reinforcement Learning for Machine Learning Engineering Agents
        69308, -- 2508.16474 Reinforcement Learning-based Control via Y-wise Affine Neural Networks
        69664, -- 2508.10608 Variance Reduced Policy Gradient Method for Multi-Objective Reinforcem
        70090, -- 2508.04660 Multi-module GRPO: Composing Policy Gradients and Prompt Optimization
        70127, -- 2508.04334 Data Scheduling Algorithm for Scalable and Efficient IoT Sensing in Cl
        70520, -- 2507.22844 RLVMR: Reinforcement Learning with Verifiable Meta-Reasoning Rewards f
        70595, -- 2507.21745 Few-Shot Vision-Language Reasoning for Satellite Imagery via Verifiabl
        70625, -- 2507.21053 Flow Matching Policy Gradients
        71079, -- 2507.12189 BenchRL-QAS: Benchmarking reinforcement learning algorithms for quantu
        71913, -- 2506.15051 Sequential Policy Gradient for Adaptive Hyperparameter Optimization
        73089, -- 2505.09012 Deep Reinforcement Learning for Power Grid Multi-Stage Cascading Failu
        73186, -- 2505.03075 Direct Retrieval-augmented Optimization: Synergizing Knowledge Selecti
        73873, -- 2503.19612 RL-finetuning LLMs from on- and off-policy data with a single algorith
        75093, -- 2501.14488 Breaking the Pre-Planning Barrier: Adaptive Real-Time Coordination of
        75546, -- 2412.06685 Policy Agnostic RL: Offline RL and Online RL Fine-Tuning of Any Class
        76486, -- 2405.10830 CTS: Concurrent Teacher-Student Reinforcement Learning for Legged Loco
        76998, -- 2406.10576 Bypass Back-propagation: Optimization-based Structural Pruning for Lar
        77102, -- 2406.01575 Contextual Bilevel Reinforcement Learning for Incentive Alignment
        77594, -- 2403.14589 ReAct Meets ActRe: When Language Agents Enjoy Training Data Autonomy
        77814, -- 2402.08552 Confronting Reward Overoptimization for Diffusion Models: A Perspectiv
        77976, -- 2401.06800 Reinforcement Learning for Optimizing RAG for Domain Chatbots
        78704, -- 2210.07184 Towards Multi-Agent Reinforcement Learning driven Over-The-Counter Mar
        78963, -- 2305.18501 DoMo-AC: Doubly Multi-step Off-policy Actor-Critic Algorithm
        79235, -- 2303.09500 Enabling First-Order Gradient-Based Learning for Equilibrium Computati
        79358, -- 2302.07320 Policy gradient learning methods for stochastic control with exit time
        79493, -- 2212.06663 Quantum Policy Gradient Algorithm with Optimized Action Decoding
        79996, -- 2205.05138 Efficient Risk-Averse Reinforcement Learning
        80400, -- 2111.05969 PowerGridworld: A Framework for Multi-Agent Reinforcement Learning in
        80645, -- 2106.13125 Unifying Gradient Estimators for Meta-Reinforcement Learning via Off-P
        80925, -- 2101.04808 MLGO: a Machine Learning Guided Compiler Optimizations Framework
        81214, -- 2007.06159 Implicit Distributional Reinforcement Learning
        81718, -- 1905.13200 Exploiting Uncertainty of Loss Landscape for Stochastic Optimization
        81832, -- 1901.04772 Transfer Learning for Prosthetics Using Imitation Learning
        82033, -- 1804.08473 Beyond Narrative Description: Generating Poetry from Images by Multi-A
        82124, -- 1712.08290 CSGNet: Neural Shape Parser for Constructive Solid Geometry
        82311, -- 1611.07507 Variational Intrinsic Control
        82871, -- 2605.06507 MARBLE: Multi-Aspect Reward Balance for Diffusion RL
        82882, -- 2605.04647 ReflectDrive-2: Reinforcement-Learning-Aligned Self-Editing for Discre
        82892, -- 2605.04077 Balanced Aggregation: Understanding and Fixing Aggregation Bias in GRP
        82909, -- 2605.06139 Listwise Policy Optimization: Group-based RLVR as Target-Projection on
        82921, -- 2605.05997 4DThinker: Thinking with 4D Imagery for Dynamic Spatial Understanding
        82977, -- 2605.08354 Auto-Rubric as Reward: From Implicit Preferences to Explicit Multimoda
        82997, -- 2605.09262 Reinforcing Multimodal Reasoning Against Visual Degradation
        83120, -- 2605.07865 KL for a KL: On-Policy Distillation with Control Variate Baseline
        83182, -- 2605.15055 DiffusionOPD: A Unified Perspective of On-Policy Distillation in Diffu
        83424, -- 2605.08472 Mid-Training with Self-Generated Data Improves Reinforcement Learning
        83582, -- 2605.21467 DelTA: Discriminative Token Credit Assignment for Reinforcement Learni
        83773, -- 2605.26108 Reinforcing Few-step Generators via Reward-Tilted Distribution Matchin
        83779, -- 2605.24517 ECHO: Terminal Agents Learn World Models for Free
        83781, -- 2604.13517 Representation over Routing: Overcoming Surrogate Hacking in Multi-Tim
        83843, -- 2605.28293 ProRL: Effective Reinforcement Learning for Proactive Recommendation v
        84195, -- 2511.16955 Neighbor GRPO: Contrastive ODE Policy Optimization Aligns Flow Models
        84580, -- 2602.20630 From Pairs to Sequences: Track-Aware Policy Gradients for Keypoint Det
        85087, -- 2603.24322 Heuristic Self-Paced Learning for Domain Adaptive Semantic Segmentatio
        85193, -- 2603.28718 Stepwise Credit Assignment for GRPO on Flow-Matching Models
        85721, -- 2505.19986 Regret Analysis of Average-Reward Unichain MDPs via an Actor-Critic Ap
        85727, -- 2411.04913 Structure Matters: Dynamic Policy Gradient
        85963, -- 2509.04661 Flexible inference of learning rules from de novo learning data using
        86356, -- 2412.04233 HyperMARL: Adaptive Hypernetworks for Multi-Agent RL
        86415, -- 2410.19933 Enhancing Safety in Reinforcement Learning with Human Feedback via Rec
        86959, -- 2505.16732 Sequential Monte Carlo for Policy Optimization in Continuous POMDPs
        87067, -- 2509.15392 Learning in Stackelberg Mean Field Games: A Non-Asymptotic Analysis
        87071, -- 2505.10646 Accelerating Visual-Policy Learning through Parallel Differentiable Si
        87337, -- 2508.17696 Fair Cooperation in Mixed-motive Games via Conflict-Aware Gradient Adj
        87445, -- 2509.01720 Succeed or Learn Slowly: Sample Efficient Off-Policy Reinforcement Lea
        88748, -- 2504.20887 Return Capping: Sample Efficient CVaR Policy Gradient Optimisation
        88753, -- 2505.00663 Wasserstein Policy Optimization
        88838, -- 2501.16243 Accelerating Quantum Reinforcement Learning with a Quantum Natural Pol
        88839, -- 2506.16120 Solving Zero-Sum Convex Markov Games
        89072, -- 2502.17254 REINFORCE Adversarial Attacks on Large Language Models: An Adaptive, D
        89083, -- 2506.00962 Reinforcement Learning with Random Time Horizons
        89116, -- 2301.13236 Policy Gradient with Tree Expansion
        89163, -- 2502.00361 Efficient Online Reinforcement Learning for Diffusion Policy
        89176, -- 2502.01694 Metastable Dynamics of Chain-of-Thought Reasoning: Provable Benefits o
        89298, -- 2503.00229 Armijo Line-search Can Make (Stochastic) Gradient Descent Provably Fas
        89424, -- 2505.01336 Enhancing Diversity In Parallel Agents: A Maximum State Entropy Explor
        89436, -- 2411.02957 Embedding Safety into RL: A New Take on Trust Region Methods
        89480, -- 2403.06323 A Reductions Approach to Risk-Sensitive Reinforcement Learning with Op
        89770, -- 2505.19247 Improving Value Estimation Critically Enhances Vanilla Policy Gradient
        91266, -- 2410.18636 Multi-agent cooperation through learning-aware policy gradients
        91297, -- 2411.07007 Non-Adversarial Inverse Reinforcement Learning via Successor Feature M
        91584, -- 2402.05187 Learning mirror maps in policy mirror descent
        91932, -- 2409.17401 Zeroth-Order Policy Gradient for Reinforcement Learning from Human Fee
        91990, -- 2502.08696 Scalable Discrete Diffusion Samplers: Combinatorial Optimization and S
        92106, -- 2404.08003 Asynchronous Federated Reinforcement Learning with Policy Gradient Upd
        92155, -- 2408.16286 Near-Optimal Policy Identification in Robust Constrained Markov Decisi
        92430, -- 2408.08761 Mitigating Information Loss in Tree-Based Reinforcement Learning via D
        92466, -- 2606.01249 Trust Region On-Policy Distillation
        92543, -- 2606.04036 Self-Distilled Policy Gradient
        92606, -- 2509.22566 From Parameters to Behaviors: Unsupervised Compression of the Policy S
        92926, -- 2502.10862 Accelerated co-design of robots through morphological pretraining
        92930, -- 2506.16608 Distributions as Actions: A Unified Framework for Diverse Action Space
        93029, -- 2506.12876 MaskPro: Linear-Space Probabilistic Learning for Strict (N:M)-Sparsity
        93162, -- 2601.12604 Beyond Softmax and Entropy: Convergence Rates of Policy Gradients with
        93185, -- 2510.13704 Simplicial Embeddings Improve Sample Efficiency in Actor–Critic Agents
        93310, -- 2603.01741 Rethinking Policy Diversity in Ensemble Policy Gradient in Large-Scale
        93323, -- 2505.16053 Learning from Algorithm Feedback: One-Shot SAT Solver Guidance with GN
        93407, -- 2604.18161 Does “Do Differentiable Simulators Give Better Policy Gradients?” Give
        93798, -- 2603.11682 Entropy-preserving reinforcement learning
        93918, -- 2602.16548 RIDER: 3D RNA Inverse Design with Reinforcement Learning-Guided Diffus
        93988, -- 2512.01228 On the Tension Between Optimality and Adversarial Robustness in Policy
        94116, -- 2512.04559 Diffusion Fine-Tuning via Reparameterized Policy Gradient of the Soft
        94149, -- 2502.08938 Reevaluating Policy Gradient Methods for Imperfect-Information Games
        94496, -- 2509.25774 PCPO: Proportionate Credit Policy Optimization for Preference Alignmen
        94574, -- 2509.21826 ResT: Reshaping Token-Level Policy Gradients for Tool-Use Large Langua
        94675, -- 2509.24305 Asynchronous Policy Gradient Aggregation for Efficient Distributed Rei
        94745, -- 2512.11391 Mitigating the Safety Alignment Tax with Null-Space Constrained Policy
        94823, -- 2507.11019 Relative Entropy Pathwise Policy Optimization
        95101, -- 2606.06447 Latent Reasoning with Normalizing Flows
        95982, -- external Second Order Sliding Mode Control of Flying Wing Aircraft Based on Fee
        96152, -- 2602.23972 Learning Robust Control Policies for Inverted Pose on Miniature Blimp
        96210, -- 2510.09976 Reinforcement Fine-Tuning of Flow-Matching Policies for Vision-Languag
        97145, -- external STAGE: Structure-Adaptive Graph-Encoded Multi-Agent Policy Gradient fo
        97226, -- external Behavior Cloning-Enhanced Deep Reinforcement Learning for Robot Naviga
        98187, -- 2606.09076 Beyond Scalar Rewards by Internalizing Reasoning into Score Distributi
        98225, -- 2605.03065 OGPO: Sample Efficient Full-Finetuning of Generative Control Policies
        98467, -- 2606.16154 A Gradient Perspective on RLVR Stability and Winner Advantage Policy O
        98468, -- 2606.18216 Zone of Proximal Policy Optimization: Teacher in Prompts, Not Gradient
        98519, -- 2606.19047 RODS: Reward-Driven Online Data Synthesis for Multi-Turn Tool-Use Agen
        99031, -- 2606.32017 TRIAGE: Role-Typed Credit Assignment for Agentic Reinforcement Learnin
        99055, -- 2607.00407 Personalization as Inverse Planning: Learning Latent Design Intents fo
        99275, -- 2605.18591 Randomized Advantage Transformation (RAT): Computing Natural Policy Gr
        99559, -- 2602.04663 Rethinking the Design Space of Reinforcement Learning for Diffusion Mo
        99587, -- 2605.26385 Credit-assigned Policy Gradient for Early Stage Retrieval in Two-stage
        99594, -- 2602.02847 Causal Flow Q-Learning for Robust Offline Reinforcement Learning
        99896, -- 2508.06214 Reparameterization Proximal Policy Optimization
        99897, -- 2602.03501 Reparameterization Flow Policy Optimization
        99903, -- 2512.20576 Performative Policy Gradient: Optimality in Performative Reinforcement
        100228, -- 2509.24050 Bridging On-Device and Cloud LLMs for Collaborative Reasoning: A Unifi
        100258, -- 2606.07400 Generative Modeling of Discrete Latent Structures via Dynamic Policy G
        100383, -- 2602.00482 AReaL-DTA: Dynamic Tree Attention for Efficient Reinforcement Learning
        100401, -- 2509.26000 Informed Asymmetric Actor-Critic: Leveraging Privileged Signals Beyond
        100408, -- 2605.20277 Regulating Anatomy-Aware Rewards via Trajectory-Integral Feedback for
        100559, -- 2604.19033 Intentional Updates for Streaming Reinforcement Learning
        100661, -- 2603.06957 Post-Training with Policy Gradients: Optimality and the Base Model Bar
        100673, -- 2511.03710 Shrinking the Variance: Shrinkage Baselines for Reinforcement Learning
        100744, -- 2512.23075 Trust Region Masking for Long-Horizon LLM Reinforcement Learning
        100783, -- 2605.31228 EchoRL: Reinforcement Learning via Rollout Echoing
        100900, -- 2602.01460 Non-Uniform Noise-to-Signal Ratio in the REINFORCE Policy-Gradient Est
        100913, -- 2506.06178 Reusing Trajectories in Policy Gradients Enables Fast Convergence
        100919, -- 2605.26654 Bilevel Optimization over Saddle Points of Zero-Sum Markov Games
        100951, -- 2602.20141 Recurrent Structural Policy Gradient for Partially Observable Mean Fie
        101009, -- 2603.03741 Learning Human-Robot Collaboration via Heterogeneous-Agent Lyapunov Po
        101193, -- 2605.30648 Convergence of Steepest Descent and Adam under Non-Uniform Smoothness
        101241, -- 2512.07248 Distinguishing Imitation Error from Intrinsic Motion Learning Difficul
        101388, -- 2506.05308 Estimation of Treatment Effects Under Nonstationarity via the Truncate
        101618, -- 2605.15417 $f$-Trajectory Balance: A Loss Family for Tuning GFlowNets, Generative
        101658, -- 2510.01824 Black-Box Combinatorial Optimization with Order-Invariant Reinforcemen
        101687, -- 2509.00338 Scalable Option Learning in High-Throughput Environments
        101726, -- 2510.04280 A KL-regularization framework for learning to plan with adaptive prior
        101732, -- 2601.22100 Boosting CVaR Policy Optimization with Quantile Gradients
        101733, -- 2510.26752 The Oversight Game: Learning to Cooperatively Balance an AI Agent's Sa
        101923, -- 2605.24357 Refined Analysis of Entropy-Regularized Actor-Critic
        101936, -- 2603.17145 REAL: Regression-Aware Reinforcement Learning for LLM-as-a-Judge
        102148, -- 2602.00424 Open Materials Generation with Inference-Time Reinforcement Learning
        102185, -- 2603.06981 Diffusion Controller: Framework, Algorithms and Parameterization
        102268, -- 2605.25867 CINOC: Cardinality-Invariant Neural Operator Policies for Scalable PDE
        102283, -- 2510.04019 Simple Policy Gradients for Reasoning with Diffusion Language Models
        102528, -- 2606.00151 Emergence of Exploration in Policy Gradient Reinforcement Learning via
        102609, -- 2607.03748 Bridging Interleaved Multi-Modal Reasoning as a Unified Decision Proce
        103881, -- 2009.04416 Phasic Policy Gradient
        104079, -- 1808.08615 Online Human Activity Recognition using Low-Power Wearable Devices
        104509, -- 2607.10848 Predictive Divergence Masks for LLM RL
        106179, -- 2607.15200 Mask-Aware Policy Gradients for Diffusion Language Models
        106376, -- 2602.21492 GradAlign: Gradient-Aligned Data Selection for LLM Reinforcement Learn
        106415, -- 2511.22406 Improving Stochastic Action-Constrained Reinforcement Learning via Tru
        106483, -- 2511.10843 Behaviour Policy Optimization: Provably Lower Variance Return Estimate
        106606, -- 2511.08339 LPPG-RL: Lexicographically Projected Policy Gradient Reinforcement Lea
        106746, -- 2602.07202 Risk-Sensitive Exponential Actor Critic
        106862, -- 2502.10012 Unlocking Efficient Vehicle Dynamics Modeling via Analytic World Model
        107275, -- 2511.16629 Stabilizing Policy Gradient Methods via Reward Profiling
        107368, -- 2509.03817 Learning to Deliberate: Meta-policy Collaboration for Agentic LLMs wit
        107394, -- 2411.07484 DiffOP: Reinforcement Learning of Optimization-Based Control Policies
        107670, -- 2505.12340 DIMM: Decoupled Multi-hierarchy Kalman Filter via Reinforcement Learni
        108031, -- 2601.21389 Learning to Optimize Job Shop Scheduling Under Structural Uncertainty
        108937, -- 2506.06323 Composite Reward Design in PPO-Driven Adaptive Filtering
        109492, -- 2608.17393 LEGO-RL: Harness-Native Reinforcement Learning for Coding Agents
        109676, -- 2608.23311 Beyond the Stability-Exploration Dilemma: Environmental Regularization
        109714, -- 2608.24696 On-policy Distillation with Verifiable Reward
        111059, -- external Image Difference Captioning via Adversarial Preference Optimization
        112238, -- external CFC: Simulating Character-Fluid Coupling using a Two-Level World Model
        112399, -- external DySeT: a Dynamic Masked Self-distillation Approach for Robust Trajecto
        114026, -- 2609.08798 Eliciting Weak-to-Strong Generalization with On-Policy Reverse Distill
        114255, -- 2605.04470 CRAFT: Counterfactual-to-Interactive Reinforcement Fine-Tuning for Dri
        114359, -- 2403.06516 Advancing Text-Driven Chest X-Ray Generation with Policy-Based Reinfor
        115694, -- external Training Diffusion Models Towards Diverse Image Generation with Reinfo
        116475, -- external Improving Unsupervised Hierarchical Representation with Reinforcement
        120420, -- external HeMoRa: Unsupervised Heuristic Consensus Sampling for Robust Point Clo
        121010, -- external RebRL: Reinforcing Discrete Visual Diffusion Models with Rebalanced Ti
        121886, -- external NS-Diff: Fluid Navier-Stokes Guided Video Diffusion via Reinforcement
        122164, -- 2609.26355 PACT: From Credit Assignment to Critic Alignment
        122246, -- 2609.37868 Learning Beyond What You Sample: Off-Policy-Aware Cross-Model Trajecto
        122259, -- 2609.36802 EasyPPO: Stabilizing the Critic Is Key
        122692, -- 2610.02179 From Gradients to Capabilities: Understanding Multi-Teacher On-Policy
        122732, -- 2610.06648 Representation-Space MMD for Diffusion Language Models
        122861, -- 2610.07043 TRIAGE: Direction-Aware Mismatch Stabilization of Native NVFP4 Reinfor
        122884, -- 2610.07226 Minimal Witness Reinforcement Learning
        123410, -- 2610.18738 Enabling Token-wise Importance Sampling in Off-Policy RLVR with Proxim
        123684, -- 2610.23181 Tree-Aware Posterior Distillation for Long-Horizon Agentic Reinforceme
        124367, -- external From Outcome to Representation: Tracing Reasoning Mechanisms through I
        124387, -- external Federated Distributionally Robust Neural Combinatorial Optimization wi
        124589, -- external Computational Dynamic Mechanism Design
        124711, -- external Submodular Multi-Agent Reinforcement Learning for Effective Online Dis
        124745, -- 2605.18185 The Dynamics of Policy Gradient in Social Dilemmas with Partner Select
        124756, -- external GCD: Correcting Hidden-State Bias in Off-Policy Agentic RL
        124761, -- external Safe Offline Reinforcement Learning using Behavior Regularisation and
        124930, -- 2605.14297 Policy Optimization in Hybrid Discrete-Continuous Action Spaces via Mi
        124951, -- external Rethinking Credit Assignment in Cooperative MARL via Interventional Re
        125074, -- 2609.30258 Temporal Gradient Inversion for Private Trajectory Reconstruction in E
        125156, -- external Compose Your Oracles: Off Policy Improvement with Aggregated Guidance
        125310, -- external Feasible Policy Optimization for Safe Reinforcement Learning
        125424, -- external State-Action Selection in General Stochastic Games under Regularized P
        125484, -- 2509.23209 Context Value Informed In-Context Reinforcement Learning
        125874, -- 2605.10716 What should post-training optimize? A test-time scaling law perspectiv
        126151, -- 2604.28020 Cost-Aware Learning
        126560, -- external Mind the Gap: Information Disadvantage as a Learning Signal in Coopera
        126589, -- 2605.20865 Multi-Step Likelihood-Ratio Correction for Reinforcement Learning with
        126637, -- external Breaking the Synthesis Barrier for AI-Designed DNA Libraries
        126965, -- external \texttt{FEROM}: Frontier Endogenous Reveal-Order Marginal Policy Optim
        127090, -- 2512.04601 Natural Language Actor-Critic: Scalable Off-Policy Learning in Languag
        127300, -- 2603.00963 Stabilizing Policy Optimization via Logits Convexity
        127388, -- 2606.05800 SALT: When More Rollouts Don’t Help in Group-Based Policy Optimization
        127411, -- 2605.10671 Natural Policy Gradient as Doubly Smoothed Policy Iteration: A Bellman
        127530, -- external Contrastive Pretraining Scales Agentic Exploration
        127661, -- external Auto-Rubric as Reward: From Implicit Preference to Explicit Generative
        127803, -- external DRILL: Training World Models to Improve Policies, Not Predict Pixels
        128036, -- 2610.15888 Variance-Optimal State Resampling for Reinforcement Learning with Veri
        128197, -- 2603.17685 Flow Matching Policy Optimization with Mirror Descent and Entropy Cons
        128224, -- 2605.14022 Policy-DRIFT: Dynamic Reward-Informed Flow Trajectory Steering
        128366, -- 2603.08518 Breaking the Bias Barrier in Concave Multi-Objective Reinforcement Lea
        128443, -- 2608.11746 Epiplexity Guided Data Selection and Generation for Out-of-Distributio
        128646, -- 2607.01490 Don’t Let Gains FADE: Breaking Down Policy Gradient Weights in RL
        128669, -- 2604.03641 Delayed homomorphic reinforcement learning for environments with delay
        128710, -- 2604.28144 Global Optimality for Constrained Exploration via Penalty Regularizati
        128760, -- external Towards Convergence of PPO: An Approximate Descent Approach
        128837, -- 2607.02292 One More Time: Revisiting Neural Quantum States from a Reinforcement L
        128978, -- 2605.06516 Learning to Cut: Reinforcement Learning for Benders Decomposition
        128982, -- external Differentiating Network Design Objectives for Balancing Cost and Dista
        129045, -- 2602.18003 Policy Gradient Algorithms in Average-Reward Multichain MDPs
        129070, -- 2603.12612 FastDSAC: Unlocking the Potential of Maximum Entropy RL in High-Dimens
        129122, -- 2608.14430 Designing Reinforcement Learning for Diffusion Models: A Unified Path-
        129135, -- external Safe-PG-LQR: Provably Safe, Convergent and Optimal Model-Free Linear Q
        129200, -- external On Reparameterizing the Score Function
        129250, -- external Instability of Meta-Learning Intrinsic Rewards for Policy Gradient Rei
        129381, -- external A Refined Sample-Complexity Analysis of Robust Policy Optimization und
        129428, -- 2606.21086 ReFPO: Reflow Regularization for Flow Matching Policy Gradients
        129600, -- 2602.06462 Diffusion-State Policy Optimization for Masked Diffusion Language Mode
        129717, -- 2605.12112 When Policy Entropy Constraint Fails: Preserving Diversity in Flow-bas
        129748, -- 2605.04266 Explaining and Preventing Alignment Collapse in Iterative RLHF
        129880, -- external Reasoning via Test-Time Instance-Level Policy Gradient in Latent Space
        130027, -- external Test Time Search Requires Training for Diversity
        130279, -- external Beyond difficulties: Insights for provably efficient design of autocur
        130375, -- 2605.24939 Global linear convergence of entropy-regularized softmax policy gradie
        130397, -- external Latency-Conditioned Selection Bias in RLHF
        130505, -- 2602.08689 Learning to Sample From Diffusion Models via Inverse Reinforcement Lea
        130677, -- external Anatomy of Off-Policy Policy Gradient: Importance Sampling, KL Regular
        130978, -- external Why Pass@k Optimization Can Degrade Pass@1: Prompt Interference in LLM
        130990, -- 2603.26097 Dynamic Tokenization via Reinforcement Patching: End-to-end Training a
        131016, -- external A New Framework for Quantum Reinforcement Learning
        131029, -- 2609.30856 Learning Chance-Constrained MDPs with Bellman Distributional Certifica
        131083, -- 2604.17693 COSAC: Counterfactual Credit Assignment in Sequential Cooperative Team
        131129, -- 2605.08686 Iterative Critique-and-Routing Controller for Multi-Agent Systems with
        131215, -- external High Entropy Regularization Leads to Symmetry Equivariant Policies in
        131245, -- external Action-Level Behavior Policy Optimization for Variance-Reduced Policy
        131262  -- 2605.09212 Rethinking Ratio-Based Trust Regions for Policy Optimization in Multi-
  );

DELETE FROM paper_method_exclusions x
USING policy_gradient_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM policy_gradient_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM policy_gradient_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE policy_gradient_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'policy-gradient'
  AND p.id IN (
        5857, -- 2106.01345 Decision Transformer: Reinforcement Learning via Sequence Modeling
        6957, -- 2110.07985 On-Policy Model Errors in Reinforcement Learning
        10038, -- 2208.06448 RLang: A Declarative Language for Describing Partial World Knowledge t
        78878, -- 2306.11246 Deep Reinforcement Learning for Inventory Networks: Toward Reliable Po
        82263, -- 1703.03864 Evolution Strategies as a Scalable Alternative to Reinforcement Learni
        108650, -- 2608.03316 Any-OPD: Heterogeneous On-Policy Distillation for Flow-Matching Models
        129053  -- 2609.35615 Behavioral Foundation Models for Quality Diversity
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions policy gradients only in contrast or passing, without using or studying them'
FROM policy_gradient_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING policy_gradient_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING policy_gradient_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- actor-critic: 218 links, 1 exclusions.
CREATE TEMP TABLE actor_critic_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'actor-critic'
  AND p.id IN (
        239, -- 1509.02971 Continuous control with deep reinforcement learning
        301, -- 1602.01783 Asynchronous Methods for Deep Reinforcement Learning
        395, -- 1606.03152 Policy Networks with Two-Stage Training for Dialogue Systems
        567, -- 1701.06049 Interactive Learning from Policy-Dependent Human Feedback
        745, -- 1706.02275 Multi-Agent Actor-Critic for Mixed Cooperative-Competitive Environment
        1128, -- 1802.09477 Addressing Function Approximation Error in Actor-Critic Methods
        2985, -- 2001.02811 Distributional Soft Actor-Critic: Off-Policy Reinforcement Learning fo
        3809, -- 2006.14978 Online 3D Bin Packing with Constrained Deep Reinforcement Learning
        5976, -- 2106.06842 Recomposing the Reinforcement Learning Building Blocks with Hypernetwo
        6281, -- 2107.09645 Mastering Visual Continuous Control: Improved Data-Augmented Reinforce
        6726, -- 2109.12425 L$^{2}$NAS: Learning to Optimize Neural Architectures via Continuous-A
        7753, -- 2201.09522 Accelerated Intravascular Ultrasound Imaging using Deep Reinforcement
        9050, -- 2205.09123 A2C is a special case of PPO
        9155, -- 2205.12258 History Compression via Language Models in Reinforcement Learning
        9829, -- 2207.09090 Actor-Critic based Improper Reinforcement Learning
        11233, -- 2211.03032 Decentralized Policy Optimization
        12179, -- 2212.10938 Critic-Guided Decoding for Controlled Text Generation
        12609, -- 2301.12083 Beyond Exponentially Fast Mixing in Average-Reward Reinforcement Learn
        12816, -- 2302.01680 Two-Stage Constrained Actor-Critic for Short Video Recommendation
        12912, -- 2302.03328 Multi-Task Recommendations with Reinforcement Learning
        13088, -- 2302.06884 Conservative State Value Estimation for Offline Reinforcement Learning
        13540, -- 2303.03832 MAP-Elites with Descriptor-Conditioned Gradients and Archive Distillat
        15835, -- 2305.12239 Off-Policy Average Reward Actor-Critic with Deterministic Policy Searc
        16109, -- 2305.14637 Learning UI-to-Code Reverse Generator Using Visual Critic Without Rend
        16218, -- 2305.15188 Optimal Control of Nonlinear Systems with Unknown Dynamics
        16598, -- 2305.19044 Exploring the Promise and Limits of Real-Time Recurrent Learning
        16897, -- 2306.01920 Context-Aware Bayesian Network Actor-Critic Methods for Cooperative Mu
        17158, -- 2306.05167 Decision S4: Efficient Sequence-Based RL via State Spaces Layers
        17538, -- 2306.09884 Jumanji: a Diverse Suite of Scalable Reinforcement Learning Environmen
        18005, -- 2307.01938 Physics-based Motion Retargeting from Sparse Inputs
        18386, -- 2307.09631 Deep Reinforcement Learning for ESG financial portfolio management
        19001, -- 2308.03526 AlphaStar Unplugged: Large-Scale Offline Reinforcement Learning
        19370, -- 2308.09138 Semantic Consistency for Assuring Reliability of Large Language Models
        20889, -- 2309.14236 MoDem-V2: Visuo-Motor World Models for Real-World Robot Manipulation
        21064, -- 2309.16984 Consistency Models as a Rich and Efficient Policy Class for Reinforcem
        21101, -- 2309.17382 Reason for Future, Act for Now: A Principled Framework for Autonomous
        23315, -- 2311.08384 Offline Data Enhanced On-Policy Policy Gradient with Provable Guarante
        23642, -- 2311.13081 Learning to Fly in Seconds
        23694, -- 2311.13884 Controlling Large Language Model-based Agents for Large-Scale Decision
        24550, -- 2312.05674 Position control of an acoustic cavitation bubble by reinforcement lea
        25041, -- 2312.13108 ASSISTGUI: Task-Oriented Desktop Graphical User Interface Automation
        25797, -- 2401.07043 Quantum Advantage Actor-Critic for Reinforcement Learning
        26594, -- 2402.00823 SLIM: Skill Learning with Multiple Critics
        26856, -- 2402.03479 DRED: Zero-Shot Transfer in Reinforcement Learning via Data-Regularise
        27042, -- 2402.05546 Offline Actor-Critic Reinforcement Learning Scales to Large Models
        27809, -- 2402.14528 ACE : Off-Policy Actor-Critic with Causality-Aware Entropy Regularizat
        28209, -- 2402.19446 ArCHer: Training Language Model Agents via Hierarchical Multi-Turn RL
        28360, -- 2403.02107 Iterated $Q$-Network: Beyond One-Step Bellman Updates in Deep Reinforc
        30286, -- 2404.08513 Adversarial Imitation Learning via Boosting
        30430, -- 2404.10719 Is DPO Superior to PPO for LLM Alignment? A Comprehensive Study
        31522, -- 2405.13629 Maximum Entropy Reinforcement Learning via Energy-Based Normalizing Fl
        34469, -- 2407.08250 Gradient Boosting Reinforcement Learning
        34930, -- 2407.13752 LogoSticker: Inserting Logos into Diffusion Models for Customized Gene
        35772, -- 2408.06506 TacSL: A Library for Visuotactile Sensor Simulation and Learning
        36611, -- 2409.03402 Game On: Towards Language Models as RL Experimenters
        37864, -- 2410.03303 SELU: Self-Learning Embodied MLLMs in Unknown Environments
        38324, -- 2410.08979 Overcoming Slow Decision Frequencies in Continuous Control: Model-Base
        38763, -- 2410.13882 Articulate-Anything: Automatic Modeling of Articulated Objects via a V
        40583, -- 2411.18203 Critic-V: VLM Critics Help Catch VLM Errors in Multimodal Reasoning
        42158, -- 2412.18279 Improving Multi-Step Reasoning Abilities of Large Language Models with
        42176, -- 2412.18563 A Deep Reinforcement Learning Framework for Dynamic Portfolio Optimiza
        42277, -- 2412.20367 Enhancing Code LLMs with Reinforcement Learning in Code Generation: A
        44075, -- 2502.08047 WorldGUI: An Interactive Benchmark for Desktop GUI Automation from Any
        44208, -- 2502.10325 Process Reward Models for LLM Agents: Practical Framework and Directio
        44891, -- 2502.16944 Lean and Mean: Decoupled Value Policy Optimization with Global Value G
        45907, -- 2503.08683 CoLMDriver: LLM-based Negotiation Benefits Cooperative Autonomous Driv
        46382, -- 2503.15172 Multi-Agent Actor-Critic with Harmonic Annealing Pruning for Dynamic S
        48458, -- 2505.03710 Actor-Critics Can Achieve Optimal Sample Efficiency
        48492, -- 2505.04553 Risk-sensitive Reinforcement Learning Based on Convex Scoring Function
        50696, -- 2506.05968 Gradual Transition from Bellman Optimality Operator to Bellman Operato
        51123, -- 2506.12851 KungfuBot: Physics-Based Humanoid Whole-Body Control for Learning High
        52236, -- 2508.04280 Enhancing Vision-Language Model Training with Reinforcement Learning i
        52325, -- 2508.08665 Aryabhata: An exam-focused language model for JEE Math
        52631, -- 2509.02522 Implicit Actor Critic Coupling via a Supervised Learning Framework for
        52840, -- 2509.13761 THOR: Tool-Integrated Hierarchical Optimization via RL for Mathematica
        53401, -- 2510.02590 Use the Online Network If You Can: Towards Fast and Stable Reinforceme
        55797, -- 2602.04651 SAFE: Stable Alignment Finetuning with Entropy-Aware Predictive Contro
        56101, -- 2602.12829 FLAC: Maximum Entropy RL via Kinetic Energy Regularized Bridge Matchin
        57009, -- 2603.24157 CarePilot: A Multi-Agent Framework for Long-Horizon Computer Task Auto
        61329, -- 2602.03584 V_0: A Generalist Value Model for Any Policy at State Zero
        61616, -- 2602.00606 Actor-Dual-Critic Dynamics for Zero-sum and Identical-Interest Stochas
        61787, -- 2601.21972 Learning Decentralized LLM Collaboration with Multi-Agent Actor Critic
        62644, -- 2601.07142 Dynamics of Multi-Agent Actor-Critic Learning in Stochastic Games: fro
        63099, -- 2601.00737 Stochastic Actor-Critic: Mitigating Overestimation via Temporal Aleato
        63911, -- 2512.17929 Reinforcement Learning for Monetary Policy Under Macroeconomic Uncerta
        64531, -- 2511.20468 DRAFT-RL: Multi-Agent Chain-of-Draft Reasoning for Reinforcement Learn
        64758, -- 2511.16900 When Motion Learns to Listen: Diffusion-Prior Lyapunov Actor-Critic Fr
        66135, -- 2510.18072 Fine-tuning Flow Matching Generative Models with Intermediate Feedback
        66758, -- 2510.07730 DEAS: DEtached value learning with Action Sequence for Scalable Offlin
        68217, -- 2509.15262 Hybrid Learning and Optimization methods for solving Capacitated Vehic
        69049, -- 2508.20467 QTMRL: An Agent for Quantitative Trading Decision-Making Based on Mult
        69116, -- 2509.10474 Generalizable Pareto-Optimal Offloading with Reinforcement Learning in
        69526, -- 2508.12943 OPTIC-ER: A Reinforcement Learning Framework for Real-Time Emergency R
        70386, -- 2508.01060 Connectivity Management in Satellite-Aided Vehicular Networks with Mul
        70686, -- 2507.19969 Text2Vis: A Challenging and Diverse Benchmark for Generating Multimoda
        71417, -- 2507.04136 A Technical Survey of Reinforcement Learning Techniques for Large Lang
        73499, -- 2504.11009 MMC: Iterative Refinement of VLM Reasoning via MCTS-based Multimodal C
        74276, -- 2411.00053 ACC-Collab: An Actor-Critic Approach to Multi-Agent LLM Collaboration
        75546, -- 2412.06685 Policy Agnostic RL: Offline RL and Online RL Fine-Tuning of Any Class
        75671, -- 2412.10381 Supervised Learning-enhanced Multi-Group Actor Critic for Live Stream
        76451, -- 2409.03996 Goal-Reaching Policy Learning from Non-Expert Observations via Effecti
        76737, -- 2407.12254 COKE: Causal Discovery with Chronological Order and Expert Knowledge i
        78963, -- 2305.18501 DoMo-AC: Doubly Multi-step Off-policy Actor-Critic Algorithm
        78967, -- 2305.17568 Scalable Primal-Dual Actor-Critic Method for Safe Multi-Agent RL with
        79013, -- 2305.12872 Byzantine Robust Cooperative Multi-Agent Reinforcement Learning as a B
        79113, -- 2304.10573 IDQL: Implicit Q-Learning as an Actor-Critic Method with Diffusion Pol
        79340, -- 2302.11312 Behavior Proximal Policy Optimization
        79755, -- 2209.02801 6D (2,0) Bootstrap with soft-Actor-Critic
        80142, -- 2203.07092 The Multi-Agent Pickup and Delivery Problem: MAPF, MARL and Its Wareho
        80565, -- 2108.08859 Solving Conformal Field Theories with Artificial Intelligence
        81009, -- 2011.09607 FinRL: A Deep Reinforcement Learning Library for Automated Stock Tradi
        81214, -- 2007.06159 Implicit Distributional Reinforcement Learning
        81294, -- 2005.13857 Deep Reinforcement learning for real autonomous mobile robot navigatio
        81893, -- 1810.11211 Deep-Reinforcement-Learning-Based Distributed Vehicle Position Control
        83259, -- 2605.11711 Debiased Model-based Representations for Sample-efficient Continuous C
        83781, -- 2604.13517 Representation over Routing: Overcoming Surrogate Hacking in Multi-Tim
        85696, -- 2506.21427 Flow-Based Single-Step Completion for Efficient and Expressive Policy
        85721, -- 2505.19986 Regret Analysis of Average-Reward Unichain MDPs via an Actor-Critic Ap
        85764, -- 2406.01423 Value Improved Actor Critic Algorithms
        86001, -- 2506.22401 Exploration from a Primal-Dual Lens: Value-Incentivized Actor-Critic M
        86705, -- 2505.15138 Global Convergence for Average Reward Constrained MDPs with Primal-Dua
        86816, -- 2410.08868 On the Convergence of Single-Timescale Actor-Critic
        87067, -- 2509.15392 Learning in Stackelberg Mean Field Games: A Non-Asymptotic Analysis
        87136, -- 2505.19053 Structured Reinforcement Learning for Combinatorial Decision-Making
        87247, -- 2409.18893 HM3: Hierarchical Multi-Objective Model Merging for Pretrained Models
        87445, -- 2509.01720 Succeed or Learn Slowly: Sample Efficient Off-Policy Reinforcement Lea
        88274, -- 2503.23219 AURELIA: Test-time Reasoning Distillation in Audio-Visual LLMs
        88624, -- 2501.19116 A Theoretical Justification for Asymmetric Actor-Critic Algorithms
        88753, -- 2505.00663 Wasserstein Policy Optimization
        88754, -- 2405.17618 Symmetric Reinforcement Learning Loss for Robust Learning on Diverse T
        88793, -- 2506.08379 Reinforce LLM Reasoning through Multi-Agent Reflection
        88955, -- 2407.18878 A Sharper Global Convergence Analysis for Average Reward Reinforcement
        89109, -- 2502.04778 Behavior-Regularized Diffusion Policy Optimization for Offline Reinfor
        89163, -- 2502.00361 Efficient Online Reinforcement Learning for Diffusion Policy
        89194, -- 2506.06376 Enhancing Decision-Making of Large Language Models via Actor-Critic
        89663, -- 2505.18433 Finite-Time Global Optimality Convergence in Deep Neural Actor-Critic
        89675, -- 2502.19859 IL-SOAR : Imitation Learning with Soft Optimistic Actor cRitic
        89734, -- 2506.16753 Off-Policy Actor-Critic for Adversarial Observation Robustness: Virtua
        91528, -- 2405.17486 eQMARL: Entangled Quantum Multi-Agent Reinforcement Learning for Distr
        91791, -- 2502.18955 Fewer May Be Better: Enhancing Offline Reinforcement Learning with Red
        92007, -- 2503.06343 Studying the Interplay Between the Actor and Critic Representations in
        92290, -- 2502.21186 Scalable Decision-Making in Stochastic Environments through Learned Te
        92390, -- 2412.12089 Stabilizing Reinforcement Learning in Differentiable Multiphysics Simu
        92743, -- 2510.09951 Emergence of Spatial Representation in an Actor-Critic Agent with Hipp
        92930, -- 2506.16608 Distributions as Actions: A Unified Framework for Diverse Action Space
        93185, -- 2510.13704 Simplicial Embeddings Improve Sample Efficiency in Actor–Critic Agents
        93213, -- 2510.14898 Convergence of an actor-critic gradient flow for entropy regularised M
        93247, -- 2602.18015 Flow Actor-Critic for Offline Reinforcement Learning
        93917, -- 2506.07822 Accelerating Diffusion Planners in Offline RL via Reward-Aware Consist
        94129, -- 2603.01047 Evaluating GFlowNet from partial episodes for stable and flexible poli
        94739, -- 2603.14245 GoldenStart: Q-Guided Priors and Entropy Control for Distilling Flow P
        94848, -- 2509.25174 XQC: Well-conditioned Optimization Accelerates Deep Reinforcement Lear
        95563, -- external Exploring History-Aware Online Actor-Critic for Smart Manufacturing Ta
        96019, -- external Disturbance-Adaptive Differentiable MPC for Underwater Structure Inspe
        96258, -- external Efficient Hierarchical Reinforcement Learning with Dynamic Kolmogorov–
        96530, -- 2504.09021 A Champion-Level Vision-Based Reinforcement Learning Agent for Competi
        96749, -- external SwarmNav: Swarm Robotics Navigation in Dynamic and Dense Environments
        96799, -- 2509.25402 Parallel Heuristic Search As Inference for Actor-Critic Reinforcement
        96981, -- 2507.04140 Learning Humanoid Arm Motion Via Centroidal Momentum Regularized Multi
        97105, -- external Learning Cooperative Strategies for Drone Swarms Using Multi-Agent Rei
        98264, -- 2606.13572 ArogyaSutra: A Multi-Agent Framework for Multimodal Medical Reasoning
        98534, -- 2606.18531 When Does Trajectory-Level Supervision Permit Efficient Offline Reinfo
        99459, -- 2512.05291 SHAP-Guided Kernel Actor-Critic for Explainable Reinforcement Learning
        99790, -- 2601.11401 Factored Value Functions for Graph-Based Multi-Agent Reinforcement Lea
        99862, -- 2510.12334 Finite-time Convergence Analysis of Actor-Critic with Evolving Reward
        100086, -- 2605.20996 Beyond the Bellman Recursion: A Pontryagin-Guided Framework for Non-Ex
        100401, -- 2509.26000 Informed Asymmetric Actor-Critic: Leveraging Privileged Signals Beyond
        100771, -- 2601.22970 Stabilizing the Q-Gradient Field for Policy Smoothness in Actor-Critic
        101218, -- 2502.03854 Mirror Descent Actor Critic via Bounded Advantage Learning
        101238, -- 2602.12386 Provably Convergent Actor-Critic for MARL through Risk-aversion
        101274, -- 2605.31172 Convergence of Two-Timescale Markovian Stochastic Approximations with
        101923, -- 2605.24357 Refined Analysis of Entropy-Regularized Actor-Critic
        102138, -- 2602.17632 SMAC: Score-Matched Actor-Critics for Robust Offline-to-Online Transfe
        102339, -- 2510.02695 RAMAC: Multimodal Risk-Aware Offline Reinforcement Learning and the Ro
        102355, -- 2605.24547 RL with Learnable Textual Feedback: A Bilevel Approach
        103878, -- 1903.03176 MinAtar: An Atari-Inspired Testbed for Thorough and Reproducible Reinf
        103881, -- 2009.04416 Phasic Policy Gradient
        103885, -- 2006.04779 Conservative Q-Learning for Offline Reinforcement Learning
        103893, -- 2006.12862 Automatic Data Augmentation for Generalization in Deep Reinforcement L
        103894, -- 2102.10330 Decoupling Value and Policy for Generalization in Reinforcement Learni
        106746, -- 2602.07202 Risk-Sensitive Exponential Actor Critic
        107705, -- 2511.08640 Predict and Resist: Long-Term Accident Anticipation Under Sensor Noise
        108031, -- 2601.21389 Learning to Optimize Job Shop Scheduling Under Structural Uncertainty
        108332, -- 2508.11143 Actor-Critic for Continuous Action Chunks: A Reinforcement Learning Fr
        110549, -- 2411.12736 ACING: Actor-Critic for Instruction Learning in Black-Box LLMs
        114100, -- 2609.11042 T1: Terminal Agent Reinforcement Learning for Long-Horizon Tasks
        114253, -- 2510.15446 VDRive: Leveraging Reinforced VLA and Diffusion Policy for End-to-end
        119695, -- 2607.23605 Hybrid Advantage Estimation with Unified Critic for VLM Agentic Reinfo
        120254, -- external Stabilizing and Accelerating Autofocus with Expert Trajectory Regulari
        121294, -- external Learning to Diversify and Focus: A Reinforcement Framework for Open-Vo
        121337, -- external TSTM: Temporal Segmentation for Task-relevant Mask in Visual Reinforce
        122164, -- 2609.26355 PACT: From Credit Assignment to Critic Alignment
        123322, -- 2105.08664 Deep Graph Convolutional Reinforcement Learning for Financial Portfoli
        124872, -- 2605.05755 Transformers Provably Implement In-Context Reinforcement Learning with
        125509, -- 2609.34553 Verifying Neural Networks with Reinforcement Learning
        126027, -- external Finite-Sample Convergence in Networked Average Reward MARL: Decentrali
        126055, -- 2602.10838 Mirror descent actor-critic methods for entropy regularised MDPs in ge
        126153, -- 2605.12655 Robust Instruction Compliance in Cooperative Multi-Agent Reinforcement
        126387, -- 2603.26741 Language-Conditioned World Modeling for Visual Navigation
        126668, -- external Unlearning Diffusion Policies via Relative Fisher Forgetting
        126788, -- 2609.04698 LookThere! Sparse Vision by Reinforced Selection
        126927, -- external GEAR: Bridging the Planner-Actor Gap via Gradient-Aligned Policy Extra
        127090, -- 2512.04601 Natural Language Actor-Critic: Scalable Off-Policy Learning in Languag
        127449, -- external Bootstrapped Bipartite Actor-Critic for Diffusion RL
        127682, -- external CRESiST: Self-Enhancing Exploritive Policy Learning for Simultaneous S
        127752, -- 2605.08733 Generative Actor-Critic with Soft Bridge Policies
        127933, -- external Kernel Value Regression in Offline Reinforcement Learning
        128406, -- 2606.05555 Representation Learning Enables Scalable Multitask Deep Reinforcement
        128590, -- 2605.08946 A Single Deep Preference-Conditioned Policy for Learning Pareto Covera
        128669, -- 2604.03641 Delayed homomorphic reinforcement learning for environments with delay
        129358, -- 2609.33337 Safe Score Matching: Diffusion Policies with Hamilton-Jacobi Reachabil
        129381, -- external A Refined Sample-Complexity Analysis of Robust Policy Optimization und
        129739, -- 2511.03724 Outbidding and Outbluffing Elite Humans: Mastering Liar’s Poker via Se
        130557, -- external Amortizing Generative Guidance for Model-Based Reinforcement Learning
        130672, -- external StylePlan: Style-Conditioned Intent Planning for Zero-Shot Coordinatio
        130737, -- 2601.21477 Mean-Field Control on Sparse Graphs: From Local Limits to GNNs via Nei
        130746, -- external Simulation-aided Reinforcement Learning with Control Variates
        131399  -- 2610.35518 S3AC: Stabilized, Selective, and Scalable Actor-Critic for LLM Reasoni
  );

DELETE FROM paper_method_exclusions x
USING actor_critic_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM actor_critic_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM actor_critic_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE actor_critic_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'actor-critic'
  AND p.id IN (
        98129  -- 2606.11087 Test-Time Gradient Guidance of Flow Policies in Reinforcement Learning
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions actor-critic only in contrast, without using it'
FROM actor_critic_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING actor_critic_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING actor_critic_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- a3c: 6 links, 499 exclusions. Semantic Scholar returned 9999 citers of the source, 505 local.
CREATE TEMP TABLE a3c_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'a3c'
  AND p.id IN (
        301, -- 1602.01783 Asynchronous Methods for Deep Reinforcement Learning
        1021, -- 1712.06567 Deep Neuroevolution: Genetic Algorithms Are a Competitive Alternative
        68773, -- 2509.03493 On Entropy Control in LLM-RL Algorithms
        80603, -- 2107.09996 MarsExplorer: Exploration of Unknown Terrains via Deep Reinforcement L
        81294, -- 2005.13857 Deep Reinforcement learning for real autonomous mobile robot navigatio
        81893  -- 1810.11211 Deep-Reinforcement-Learning-Based Distributed Vehicle Position Control
  );

DELETE FROM paper_method_exclusions x
USING a3c_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM a3c_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM a3c_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE a3c_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'a3c'
  AND p.id IN (
        395, -- 1606.03152 Policy Networks with Two-Stage Training for Dialogue Systems
        569, -- 1701.07274 Deep Reinforcement Learning: An Overview
        571, -- 1701.07875 Wasserstein GAN
        597, -- 1703.00420 Virtual-to-real Deep Reinforcement Learning: Continuous Control of Mob
        605, -- 1703.02018 Combining Self-Supervised Learning and Imitation for Vision-Based Rope
        656, -- 1704.02254 Recurrent Environment Simulators
        754, -- 1706.03741 Deep reinforcement learning from human preferences
        759, -- 1706.04208 Hybrid Reward Architecture for Reinforcement Learning
        779, -- 1706.09520 Neural SLAM: Learning to Explore with External Memory
        784, -- 1706.10059 A Deep Reinforcement Learning Framework for the Financial Portfolio Ma
        804, -- 1707.06347 Proximal Policy Optimization Algorithms
        847, -- 1708.04782 StarCraft II: A New Challenge for Reinforcement Learning
        892, -- 1709.08430 Towards continuous control of flippers for a multi-terrain robot using
        896, -- 1709.10163 Deep TAMER: Interactive Agent Shaping in High-Dimensional State Spaces
        903, -- 1710.02298 Rainbow: Combining Improvements in Deep Reinforcement Learning
        960, -- 1711.03938 CARLA: An Open Urban Driving Simulator
        988, -- 1711.09846 Population Based Training of Neural Networks
        1018, -- 1712.05889 Ray: A Distributed Framework for Emerging AI Applications
        1037, -- 1801.00690 DeepMind Control Suite
        1040, -- 1801.01290 Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learn
        1086, -- 1802.01561 IMPALA: Scalable Distributed Deep-RL with Importance Weighted Actor-Le
        1124, -- 1802.08802 Reinforcement Learning on Web Interfaces Using Workflow-Guided Explora
        1128, -- 1802.09477 Addressing Function Approximation Error in Actor-Critic Methods
        1134, -- 1803.01164 The History Began from AlexNet: A Comprehensive Survey on Deep Learnin
        1145, -- 1803.03835 Kickstarting Deep Reinforcement Learning
        1201, -- 1804.00379 Recall Traces: Backtracking Models for Efficient Reinforcement Learnin
        1216, -- 1804.03599 Understanding disentangling in $β$-VAE
        1257, -- 1805.01109 AGI Safety Literature Review
        1289, -- 1805.07470 Solving the Rubik's Cube Without Human Knowledge
        1385, -- 1807.03748 Representation Learning with Contrastive Predictive Coding
        1393, -- 1807.04742 Visual Reinforcement Learning with Imagined Goals
        1508, -- 1809.08267 Neural Approaches to Conversational AI
        1580, -- 1810.12894 Exploration by Random Network Distillation
        1624, -- 1811.06521 Reward learning from human preferences and demonstrations in Atari
        1634, -- 1811.07871 Scalable agent alignment via reward modeling: a research direction
        1702, -- 1812.05905 Soft Actor-Critic Algorithms and Applications
        1704, -- 1812.06162 An Empirical Model of Large-Batch Training
        1731, -- 1901.00137 A Theoretical Analysis of Deep Q-Learning
        1739, -- 1901.01753 Paired Open-Ended Trailblazer (POET): Endlessly Generating Increasingl
        1792, -- 1901.10995 Go-Explore: a New Approach for Hard-Exploration Problems
        2080, -- 1905.03030 Meta-learning of Sequential Strategies
        2316, -- 1907.01475 Generalizing from a few environments in safety-critical reinforcement
        2381, -- 1907.13440 MineRL: A Large-Scale Dataset of Minecraft Demonstrations
        2458, -- 1908.09453 OpenSpiel: A Framework for Reinforcement Learning in Games
        2551, -- 1909.07373 Policy Prediction Network: Model-Free Behavior Policy with Model-Based
        2562, -- 1909.08072 Adversarial Attacks and Defenses in Images, Graphs and Text: A Review
        2679, -- 1910.06764 Stabilizing Transformers for Reinforcement Learning
        2830, -- 1911.08647 Deep Reinforcement Learning in Cryptocurrency Market Making
        2892, -- 1912.01603 Dream to Control: Learning Behaviors by Latent Imagination
        2930, -- 1912.06680 Dota 2 with Large Scale Deep Reinforcement Learning
        2936, -- 1912.07768 Generative Teaching Networks: Accelerating Neural Architecture Search
        2985, -- 2001.02811 Distributional Soft Actor-Critic: Off-Policy Reinforcement Learning fo
        3039, -- 2001.10913 MEMO: A Deep Network for Flexible Combination of Episodic Memories
        3277, -- 2003.14089 Leverage the Average: an Analysis of KL Regularization in RL
        3358, -- 2004.06985 Extending Deep Reinforcement Learning Frameworks in Cryptocurrency Mar
        3435, -- 2004.13649 Image Augmentation Is All You Need: Regularizing Deep Reinforcement Le
        3565, -- 2005.05719 Smooth Exploration for Robotic Reinforcement Learning
        3599, -- 2005.09814 Mirror Descent Policy Optimization
        3709, -- 2006.07733 Bootstrap your own latent: A new approach to self-supervised Learning
        3774, -- 2006.11485 Generating Adjacency-Constrained Subgoals in Hierarchical Reinforcemen
        3779, -- 2006.11751 Sample Factory: Egocentric 3D Control from Pixels at 100000 FPS with A
        3809, -- 2006.14978 Online 3D Bin Packing with Constrained Deep Reinforcement Learning
        3873, -- 2007.04309 Self-Supervised Policy Adaptation during Deployment
        4026, -- 2008.06693 Explainability in Deep Reinforcement Learning
        4053, -- 2008.09685 Model-Free Episodic Control with State Aggregation
        4103, -- 2009.01719 Grounded Language Learning Fast and Slow
        4378, -- 2010.09954 Improving Dialog Systems for Negotiation with Personality Modeling
        4488, -- 2011.00702 Fast Reinforcement Learning with Incremental Gaussian Mixture Models
        4580, -- 2011.09533 Is Independent Learning All You Need in the StarCraft Multi-Agent Chal
        4597, -- 2011.11012 Distributed Deep Reinforcement Learning: An Overview
        4631, -- 2011.13922 A Recurrent Vision-and-Language BERT for Navigation
        5059, -- 2102.09407 Adaptive Rational Activations to Boost Deep Reinforcement Learning
        5346, -- 2104.00442 Touch-based Curiosity for Sparse-Reward Tasks
        5397, -- 2104.03807 A Bayesian Approach to Reinforcement Learning of Vision-Based Vehicula
        5528, -- 2104.09122 Probabilistic Mixture-of-Experts for Efficient Deep Reinforcement Lear
        5561, -- 2104.10995 A learning gap between neuroscience and reinforcement learning
        5687, -- 2105.04387 Recent Advances in Deep Learning Based Dialogue Systems: A Systematic
        5898, -- 2106.03374 RegMix: Data Mixing Augmentation for Regression
        5924, -- 2106.04615 Vector Quantized Models for Planning
        6005, -- 2106.08272 Deep Reinforcement Learning for Conservation Decisions
        6067, -- 2106.11086 Analytically Tractable Bayesian Deep Q-Learning
        6076, -- 2106.11420 Policy Smoothing for Provably Robust Reinforcement Learning
        6201, -- 2107.03759 Analytically Tractable Hidden-States Inference in Bayesian Neural Netw
        6281, -- 2107.09645 Mastering Visual Continuous Control: Improved Data-Augmented Reinforce
        6433, -- 2108.07124 Using Cyber Terrain in Reinforcement Learning for Penetration Testing
        6511, -- 2108.13264 Deep Reinforcement Learning at the Edge of the Statistical Precipice
        6772, -- 2110.00641 Batch size-invariance for policy optimization
        6781, -- 2110.01307 Collective eXplainable AI: Explaining Cooperative Strategies and Agent
        6808, -- 2110.02639 On The Transferability of Deep-Q Networks
        6822, -- 2110.03262 Situated Dialogue Learning through Procedural Environment Generation
        7107, -- 2111.00210 Mastering Atari Games with Limited Data
        7108, -- 2111.00213 Adjacency constraint for efficient hierarchical reinforcement learning
        7378, -- 2112.01021 Fighting Fire with Fire: Contrastive Debiasing without Bias-free Data
        7403, -- 2112.02095 Intelligent Trading Systems: A Sentiment-Aware Reinforcement Learning
        7428, -- 2112.03636 Godot Reinforcement Learning Agents
        7476, -- 2112.05779 Quantum Architecture Search via Continual Reinforcement Learning
        7677, -- 2201.03916 Automated Reinforcement Learning (AutoRL): A Survey and Open Problems
        7688, -- 2201.05000 Automated Reinforcement Learning: An Overview
        7862, -- 2202.01771 Pre-Trained Language Models for Interactive Decision-Making
        7892, -- 2202.03286 Red Teaming Language Models with Language Models
        7959, -- 2202.06828 On the Convergence of SARSA with Linear Function Approximation
        8026, -- 2202.10222 Robots Learn Increasingly Complex Tasks with Intrinsic Motivation and
        8194, -- 2203.04955 Temporal Difference Learning for Model Predictive Control
        8197, -- 2203.05227 Faithfulness in Natural Language Generation: A Systematic Survey of An
        8367, -- 2203.11147 Teaching language models to support answers with verified quotes
        8425, -- 2203.13922 AutoML for Deep Recommender Systems: A Survey
        8485, -- 2203.16219 Acknowledging the Unknown for Multi-label Learning with Single Positiv
        9050, -- 2205.09123 A2C is a special case of PPO
        9333, -- 2206.01153 Multi-View Active Fine-Grained Recognition
        9586, -- 2206.11795 Video PreTraining (VPT): Learning to Act by Watching Unlabeled Online
        9661, -- 2207.00046 Performative Reinforcement Learning
        9680, -- 2207.01206 WebShop: Towards Scalable Real-World Web Interaction with Grounded Lan
        9805, -- 2207.07790 BCRLSP: An Offline Reinforcement Learning Framework for Sequential Tar
        9944, -- 2208.00553 Search for or Navigate to? Dual Adaptive Thinking for Object Navigatio
        9973, -- 2208.02294 Dynamic Planning in Open-Ended Dialogue using Reinforcement Learning
        10330, -- 2209.08660 Learn the Time to Learn: Replay Scheduling in Continual Learning
        10417, -- 2209.12782 Learning GFlowNets from partial episodes for improved convergence and
        10445, -- 2209.14375 Improving alignment of dialogue agents via targeted human judgements
        10452, -- 2209.14610 Dynamic Prompt Learning via Policy Gradient for Semi-structured Mathem
        10531, -- 2210.01241 Is Reinforcement Learning (Not) for Natural Language Processing: Bench
        10719, -- 2210.05639 Discovered Policy Optimisation
        10994, -- 2210.12765 Multi-Objective GFlowNets
        11015, -- 2210.13011 On Many-Actions Policy Gradient
        11287, -- 2211.05311 When is Realizability Sufficient for Off-Policy Reinforcement Learning
        11440, -- 2211.10550 Debiasing Meta-Gradient Reinforcement Learning by Learning the Outer V
        11937, -- 2212.06225 Reinforced Approximate Exploratory Data Analysis
        12204, -- 2212.12207 Investigation of reinforcement learning for shape optimization of prof
        12443, -- 2301.07799 A Domain-Agnostic Approach for Characterization of Lifelong Learning S
        12528, -- 2301.10886 Automatic Intrinsic Reward Shaping for Exploration in Deep Reinforceme
        12609, -- 2301.12083 Beyond Exponentially Fast Mixing in Average-Reward Reinforcement Learn
        12631, -- 2301.12477 StriderNET: A Graph Reinforcement Learning Approach to Optimize Atomic
        12659, -- 2301.12842 Direct Preference-based Policy Optimization without Reward Modeling
        12802, -- 2302.01520 Multiple Thinking Achieving Meta-Ability Decoupling for Object Navigat
        12816, -- 2302.01680 Two-Stage Constrained Actor-Critic for Short Video Recommendation
        13122, -- 2302.07842 Augmented Language Models: a Survey
        13515, -- 2303.03196 Population-based Evaluation in Repeated Rock-Paper-Scissors as a Bench
        13517, -- 2303.03284 The Wasserstein Believer: Learning Belief Updates for Partially Observ
        13550, -- 2303.04077 Meta-Explore: Exploratory Hierarchical Vision-and-Language Navigation
        13551, -- 2303.04129 Foundation Models for Decision Making: Problems, Methods, and Opportun
        14712, -- 2304.07297 Language Instructed Reinforcement Learning for Human-AI Coordination
        15310, -- 2305.04361 Truncating Trajectories in Monte Carlo Reinforcement Learning
        15381, -- 2305.05586 RLocator: Reinforcement Learning for Bug Localization
        15486, -- 2305.07440 Optimizing Memory Mapping Using Deep Reinforcement Learning
        15593, -- 2305.09129 Graph Reinforcement Learning for Network Control via Bi-Level Optimiza
        15956, -- 2305.13504 Neural Machine Translation for Code Generation
        15998, -- 2305.13795 Proximal Policy Gradient Arborescence for Quality Diversity Reinforcem
        16278, -- 2305.15801 Lucy-SKG: Learning to Play Rocket League Efficiently Using Deep Reinfo
        16316, -- 2305.16291 Voyager: An Open-Ended Embodied Agent with Large Language Models
        16420, -- 2305.17342 Rethinking Adversarial Policies: A Generalized Attack Formulation and
        16513, -- 2305.18388 The Statistical Benefits of Quantile Temporal-Difference Learning for
        16586, -- 2305.18951 Subequivariant Graph Reinforcement Learning in 3D Environments
        16598, -- 2305.19044 Exploring the Promise and Limits of Real-Time Recurrent Learning
        16754, -- 2306.00577 TorchRL: A data-driven decision-making library for PyTorch
        16921, -- 2306.02231 Fine-Tuning Language Models with Advantage-Induced Policy Alignment
        17039, -- 2306.03530 RLtools: A Fast, Portable Deep Reinforcement Learning Library for Cont
        17158, -- 2306.05167 Decision S4: Efficient Sequence-Based RL via State Spaces Layers
        17370, -- 2306.07929 Large Language Models Are Semi-Parametric Reinforcement Learning Agent
        17395, -- 2306.08107 AutoML in the Age of Large Language Models: Current Challenges, Future
        17647, -- 2306.11941 Efficient Dynamics Modeling in Interactive Environments with Koopman T
        17728, -- 2306.13812 Maintaining Plasticity in Deep Continual Learning
        17985, -- 2307.01403 Learning Multi-Agent Communication with Contrastive Learning
        18144, -- 2307.04964 Secrets of RLHF in Large Language Models Part I: PPO
        18201, -- 2307.06435 A Comprehensive Overview of Large Language Models
        18348, -- 2307.08962 REX: Rapid Exploration and eXploitation for AI Agents
        18472, -- 2307.10936 PASTA: Pretrained Action-State Transformer Agents
        18753, -- 2307.15833 Dialogue Shaping: Empowering Agents through NPC Interaction
        18899, -- 2308.01872 Thespian: Multi-Character Text Role-Playing Game Agents
        18918, -- 2308.02151 Retroformer: Retrospective Large Language Agents with Policy Gradient
        19363, -- 2308.08998 Reinforced Self-Training (ReST) for Language Modeling
        19582, -- 2308.10916 Diffusion Model as Representation Learner
        19854, -- 2308.14328 Reinforcement Learning for Generative AI: A Survey
        20025, -- 2309.00754 Efficient RLHF: Reducing the Memory Usage of PPO
        20092, -- 2309.01825 LoopTune: Optimizing Tensor Computations with Reinforcement Learning
        21015, -- 2309.16240 Beyond Reverse KL: Generalizing Direct Preference Optimization with Di
        21085, -- 2309.17207 Memory Gym: Towards Endless Tasks to Benchmark Memory Capabilities of
        21118, -- 2310.00036 Cleanba: A Reproducible and Efficient Distributed Reinforcement Learni
        21132, -- 2310.00212 Pairwise Proximal Policy Optimization: Harnessing Relative Feedback fo
        21148, -- 2310.00386 Order-Preserving GFlowNets
        21261, -- 2310.01444 Adapting LLM Agents with Universal Feedback in Communication
        21351, -- 2310.02368 Reinforcement Learning from Automatic Feedback for High-Quality Unit T
        21376, -- 2310.02710 Local Search GFlowNets
        21381, -- 2310.02782 Discovering General Reinforcement Learning Algorithms with Adversarial
        21713, -- 2310.06452 Understanding the Effects of RLHF on LLM Generalisation and Diversity
        22165, -- 2310.11971 Improving Generalization of Alignment with Human Preferences through G
        22470, -- 2310.15719 AGaLiTe: Approximate Gated Linear Transformers for Online Reinforcemen
        22661, -- 2310.18144 Improving Intrinsic Exploration by Creating Stationary Objectives
        22805, -- 2310.20380 Dropout Strategy in Reinforcement Learning: Limiting the Surrogate Obj
        22818, -- 2310.20663 Offline RL with Observation Histories: Analyzing and Improving Sample
        23076, -- 2311.04453 Lewis's Signaling Game as beta-VAE For Natural Word Lengths and Segmen
        23298, -- 2311.08290 On-Policy Policy Gradient Reinforcement Learning Without On-Policy Sam
        23463, -- 2311.10090 JaxMARL: Multi-Agent RL Environments and Algorithms in JAX
        23690, -- 2311.13743 FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory a
        24046, -- 2311.18736 Controlgym: Large-Scale Control Environments for Benchmarking Reinforc
        25340, -- 2401.00243 Uncertainty-Penalized Reinforcement Learning from Human Feedback with
        25714, -- 2401.06081 Improving Large Language Models via Fine-grained Reinforcement Learnin
        25726, -- 2401.06179 CNN-DRL for Scalable Actions in Finance
        25797, -- 2401.07043 Quantum Advantage Actor-Critic for Reinforcement Learning
        25811, -- 2401.07382 Beyond Sparse Rewards: Enhancing Reinforcement Learning with Language
        25833, -- 2401.07886 Learned Best-Effort LLM Serving
        26086, -- 2401.11349 Asynchronous Parallel Reinforcement Learning for Optimizing Propulsive
        26249, -- 2401.13662 The Definitive Guide to Policy Gradients in Deep Reinforcement Learnin
        26442, -- 2401.16444 Enhancing Human Experience in Human-Agent Collaboration: A Human-Cente
        26477, -- 2401.16979 Re3val: Reinforced and Reranked Generative Retrieval
        26525, -- 2401.17749 SwarmBrain: Embodied agent for real-time strategy game StarCraft II vi
        26633, -- 2402.01118 PokeLLMon: A Human-Parity Agent for Pokemon Battles with Large Languag
        26813, -- 2402.03046 Open RL Benchmark: Comprehensive Tracked Experiments for Reinforcement
        26856, -- 2402.03479 DRED: Zero-Shot Transfer in Reinforcement Learning via Data-Regularise
        27063, -- 2402.05808 Training Large Language Models for Reasoning through Reverse Curriculu
        27316, -- 2402.09240 Switch EMA: A Free Lunch for Better Flatness and Sharpness
        27417, -- 2402.10571 Direct Preference Optimization with an Offset
        27498, -- 2402.11427 OptEx: Expediting First-Order Optimization with Approximately Parallel
        27606, -- 2402.12366 A Critical Evaluation of AI Feedback for Aligning Large Language Model
        27655, -- 2402.12874 Skill or Luck? Return Decomposition via Advantage Functions
        28086, -- 2402.17760 Learning to Program Variational Quantum Circuits with Fast Weights
        28212, -- 2402.19464 Curiosity-driven Red-teaming for Large Language Models
        28377, -- 2403.02271 RIFF: Learning to Rephrase Inputs for Few-shot Fine-tuning of Language
        28487, -- 2403.03950 Stop Regressing: Training Value Functions via Classification for Scala
        28638, -- 2403.06328 Distributional Successor Features Enable Zero-Shot Policy Optimization
        28722, -- 2403.07559 Ensembling Prioritized Hybrid Policies for Multi-agent Pathfinding
        28792, -- 2403.08635 Human Alignment of Large Language Models through Online Preference Opt
        28875, -- 2403.09629 Quiet-STaR: Language Models Can Teach Themselves to Think Before Speak
        28907, -- 2403.10112 Single- and Multi-Agent Private Active Sensing: A Deep Neuroevolution
        28938, -- 2403.10553 Learning to Watermark LLM-generated Text via Reinforcement Learning
        29590, -- 2403.19159 Disentangling Length from Quality in Direct Preference Optimization
        29752, -- 2404.00929 A Survey on Multilingual Large Language Models: Corpora, Alignment, an
        29842, -- 2404.01911 VLRM: Vision-Language Models act as Reward Models for Image Captioning
        29970, -- 2404.03715 Direct Nash Optimization: Teaching Language Models to Self-Improve wit
        30033, -- 2404.04682 Compositional Conservatism: A Transductive Approach in Offline Reinfor
        30213, -- 2404.07525 Enhancing Policy Gradient with the Polyak Step-Size Adaption
        30430, -- 2404.10719 Is DPO Superior to PPO for LLM Alignment? A Comprehensive Study
        30752, -- 2404.16077 CompilerDream: Learning a Compiler World Model for General Code Optimi
        30784, -- 2404.16767 REBEL: Reinforcement Learning via Regressing Relative Rewards
        31455, -- 2405.12399 Diffusion for World Modeling: Visual Details Matter in Atari
        31553, -- 2405.14093 A Survey on Vision-Language-Action Models for Embodied AI
        31991, -- 2405.19107 Offline Regularised Reinforcement Learning for Large Language Models A
        32005, -- 2405.19320 Value-Incentivized Preference Optimization: A Unified Approach to Onli
        32579, -- 2406.05872 STARLING: Self-supervised Training of Text-based Reinforcement Learnin
        33438, -- 2406.14739 Learning to Retrieve Iteratively for In-Context Learning
        33620, -- 2406.16979 Understanding and Diagnosing Deep Reinforcement Learning
        33804, -- 2406.19320 Efficient World Models with Context-Aware Tokenization
        34362, -- 2407.06567 FinCon: A Synthesized LLM Multi-Agent System with Conceptual Verbal Re
        34469, -- 2407.08250 Gradient Boosting Reinforcement Learning
        34886, -- 2407.13146 PG-Rainbow: Using Distributional Reinforcement Learning in Policy Grad
        35207, -- 2407.18202 Differentiable Quantum Architecture Search in Asynchronous Quantum Rei
        35424, -- 2408.00386 What comes after transformers? -- A selective survey connecting ideas
        35537, -- 2408.02295 Generalized Gaussian Temporal Difference Error for Uncertainty-aware R
        35664, -- 2408.04498 Model-Based Transfer Learning for Contextual Reinforcement Learning
        35795, -- 2408.06818 Personalized Dynamic Difficulty Adjustment -- Imitation Learning Meets
        37179, -- 2409.14393 MaskedMimic: Unified Physics-Based Character Control Through Masked Mo
        38498, -- 2410.11020 Improving the Language Understanding Capabilities of Large Language Mo
        38547, -- 2410.11677 Understanding Likelihood Over-optimisation in Direct Alignment Algorit
        38663, -- 2410.13060 AERO: Softmax-Only LLMs for Efficient Private Inference
        38814, -- 2410.14606 Streaming Deep Reinforcement Learning Finally Works
        38887, -- 2410.15595 A Comprehensive Survey of Direct Preference Optimization: Datasets, Th
        39085, -- 2410.18252 Asynchronous RLHF: Faster and More Efficient Off-Policy RL for Languag
        39487, -- 2411.00252 IO Transformer: Evaluating SwinV2-Based Reward Models for Computer Vis
        39530, -- 2411.00782 TradExpert: Revolutionizing Trading with Mixture of Expert LLMs
        40346, -- 2411.15370 Deep Policy Gradient Methods Without Batch Updates, Target Networks, o
        40933, -- 2412.02818 From Mystery to Mastery: Failure Diagnosis for Improving Manipulation
        42651, -- 2501.04982 CuRLA: Curriculum Learning Based Deep Reinforcement Learning for Auton
        42943, -- 2501.09858 From Explainability to Interpretability: Interpretable Policies in Rei
        43391, -- 2501.17992 Reinforcement-Learning Portfolio Allocation with Dynamic Embedding of
        43769, -- 2502.04327 Value-Based Deep RL Scales Predictably
        43935, -- 2502.06533 Ignore the KL Penalty! Boosting Exploration on Critical Tokens to Enha
        45231, -- 2502.21321 LLM Post-Training: A Deep Dive into Reasoning Large Language Models
        46323, -- 2503.14286 Tapered Off-Policy REINFORCE: Stable and efficient reinforcement learn
        46393, -- 2503.15354 Optimizing Decomposition for Optimal Claim Verification
        46671, -- 2503.18929 Trajectory Balance with Asynchrony: Decoupling Exploration and Learnin
        47981, -- 2504.14945 Learning to Reason under Off-Policy Guidance
        48067, -- 2504.16129 MARFT: Multi-Agent Reinforcement Fine-Tuning
        48126, -- 2504.17838 CaRL: Learning Scalable Planning Policies with Simple Rewards
        48668, -- 2505.07903 SEM: Reinforcement Learning for Search-Efficient Large Language Models
        48955, -- 2505.12366 DisCO: Reinforcing Large Reasoning Models with Discriminative Constrai
        49444, -- 2505.16826 KTAE: A Model-Free Algorithm to Key-Tokens Advantage Estimation in Mat
        49611, -- 2505.18454 Hybrid Latent Reasoning via Reinforcement Learning
        49624, -- 2505.18536 Reinforcement Fine-Tuning Powers Reasoning Capability of Multimodal La
        49628, -- 2505.18573 Enhancing Efficiency and Exploration in Reinforcement Learning for LLM
        50020, -- 2505.22617 The Entropy Mechanism of Reinforcement Learning for Reasoning Language
        50192, -- 2505.24034 LlamaRL: A Distributed Asynchronous Reinforcement Learning Framework f
        50417, -- 2506.01939 Beyond the 80/20 Rule: High-Entropy Minority Tokens Drive Effective Re
        50852, -- 2506.08388 Reinforcement Learning Teachers of Test Time Scaling
        51543, -- 2506.21872 A Survey of Continual Reinforcement Learning
        52325, -- 2508.08665 Aryabhata: An exam-focused language model for JEE Math
        52954, -- 2509.22576 EPO: Entropy-regularized Policy Optimization for LLM Agents Reinforcem
        53917, -- 2112.04145 A Review for Deep Reinforcement Learning in Atari:Benchmarks, Challeng
        54289, -- 2511.15248 EntroPIC: Towards Stable Long-Term Training of LLMs via Entropy Stabil
        54574, -- 2512.04797 SIMA 2: A Generalist Embodied Agent for Virtual Worlds
        55115, -- 2601.03044 SOP: A Scalable Online Post-Training System for Vision-Language-Action
        55235, -- 2601.07055 Dr. Zero: Self-Evolving Search Agents without Training Data
        55300, -- 2601.08955 Imagine-then-Plan: Agent Learning from Adaptive Lookahead with World M
        55512, -- 2601.17067 A Mechanistic View on Video Generation as World Models: State and Dyna
        56186, -- 2602.16301 Multi-agent cooperation through in-context co-player inference
        57402, -- 2604.11297 The Past Is Not Past: Memory-Enhanced Dynamic Reward Shaping
        57996, -- 2604.19695 Planning in entropy-regularized Markov decision processes and games
        59145, -- 2603.18756 Are complicated loss functions necessary for teaching LLMs to reason?
        60075, -- 2603.01162 Demystifying Group Relative Policy Optimization: Its Policy Gradient i
        60489, -- 2602.17098 Deep Reinforcement Learning for Optimal Portfolio Allocation: A Compar
        60490, -- 2603.06608 Scaling Strategy, Not Compute: A Stand-Alone, Open-Source StarCraft II
        60732, -- 2602.12561 PLLM: Pseudo-Labeling Large Language Models for CAD Program Synthesis
        61360, -- 2602.03190 Prompt Augmentation Scales up GRPO Training on Mathematical Reasoning
        61543, -- 2602.01156 PolicyFlow: Policy Optimization with Continuous Normalizing Flow in Re
        62378, -- 2602.00035 Asynchronous MultiAgent Reinforcement Learning for 5G Routing under Si
        62644, -- 2601.07142 Dynamics of Multi-Agent Actor-Critic Learning in Stochastic Games: fro
        63178, -- 2512.24497 What Drives Success in Physical Planning with Joint-Embedding Predicti
        63624, -- 2512.15089 Beyond Fast and Slow: Cognitive-Inspired Elastic Reasoning for Large L
        64452, -- 2512.11816 Reinforcement Learning for Latent-Space Thinking in LLMs
        65149, -- 2511.08555 RESTL: Reinforcement Learning Guided by Multi-Aspect Rewards for Signa
        65444, -- 2501.15971 REINFORCE-ING Chemical Language Models for Drug Discovery
        66495, -- 2510.11345 Part II: ROLL Flash -- Accelerating RLVR and Agentic Training with Asy
        66590, -- 2510.10150 Rethinking Entropy Interventions in RLVR: An Entropy Change Perspectiv
        66829, -- 2510.06672 XRPO: Pushing the limits of GRPO with Targeted Exploration and Exploit
        67420, -- 2509.25004 CLPO: Curriculum Learning meets Policy Optimization for LLM Reasoning
        67873, -- 2510.00022 Learning to Lead Themselves: Agentic AI in MAS using MARL
        67973, -- 2509.18521 APRIL: Active Partial Rollouts in Reinforcement Learning to Tame Long-
        68189, -- 2509.15110 TDRM: Smooth Reward Models with Temporal Difference for LLM RL and Inf
        69049, -- 2508.20467 QTMRL: An Agent for Quantitative Trading Decision-Making Based on Mult
        69192, -- 2508.18258 ANO : Faster is Better in Noisy Landscape
        69526, -- 2508.12943 OPTIC-ER: A Reinforcement Learning Framework for Real-Time Emergency R
        70038, -- 2508.05402 DistillDrive: End-to-End Multi-Mode Autonomous Driving Distillation by
        70217, -- 2508.03772 GTPO: Trajectory-Based Policy Optimization in Large Language Models
        70287, -- 2508.02219 CO-RFT: Efficient Fine-Tuning of Vision-Language-Action Models through
        70625, -- 2507.21053 Flow Matching Policy Gradients
        70893, -- 2507.16253 Reinforce Lifelong Interaction Value of User-Author Pairs for Large-Sc
        71079, -- 2507.12189 BenchRL-QAS: Benchmarking reinforcement learning algorithms for quantu
        71417, -- 2507.04136 A Technical Survey of Reinforcement Learning Techniques for Large Lang
        71543, -- 2507.01152 SonoGym: High Performance Simulation for Challenging Surgical Tasks wi
        71913, -- 2506.15051 Sequential Policy Gradient for Adaptive Hyperparameter Optimization
        72806, -- 2505.17673 Rethinking Agent Design: From Top-Down Workflows to Bottom-Up Skill Ev
        73089, -- 2505.09012 Deep Reinforcement Learning for Power Grid Multi-Stage Cascading Failu
        73928, -- 2503.17267 Physical Plausibility-aware Trajectory Prediction via Locomotion Embod
        74060, -- 2503.12339 A Closer Look at Adversarial Suffix Learning for Jailbreaking LLMs: Au
        74258, -- 2503.04416 Learning Transformer-based World Models with Contrastive Predictive Co
        74951, -- 2502.01387 TeLL-Drive: Enhancing Autonomous Driving with Teacher LLM-Guided Deep
        75044, -- 2501.17842 From Sparse to Dense: Toddler-inspired Reward Transition in Goal-Orien
        75782, -- 2411.11609 VLN-Game: Vision-Language Equilibrium Search for Zero-Shot Semantic Na
        76096, -- 2410.07863 Learning to Balance Altruism and Self-interest Based on Empathy in Mix
        76451, -- 2409.03996 Goal-Reaching Policy Learning from Non-Expert Observations via Effecti
        76506, -- 2408.15332 What makes math problems hard for reinforcement learning: a case study
        76802, -- 2407.04811 Simplifying Deep Temporal Difference Learning
        78152, -- 2312.02976 SPOC: Imitating Shortest Paths in Simulation Enables Effective Navigat
        78157, -- 2312.02561 DanZero+: Dominating the GuanDan Game through Reinforcement Learning
        78704, -- 2210.07184 Towards Multi-Agent Reinforcement Learning driven Over-The-Counter Mar
        78963, -- 2305.18501 DoMo-AC: Doubly Multi-step Off-policy Actor-Critic Algorithm
        79228, -- 2303.10692 Boundary-aware Supervoxel-level Iteratively Refined Interactive 3D Ima
        79318, -- 2209.00588 Transformers are Sample-Efficient World Models
        79434, -- 2301.06512 DRL-VO: Learning to Navigate Through Crowded Dynamic Scenes Using Velo
        79444, -- 2301.03270 A Survey of Learning-based Automated Program Repair
        79580, -- 2211.06665 A Survey on Explainable Reinforcement Learning: Concepts, Algorithms,
        79632, -- 2210.14215 In-context Reinforcement Learning with Algorithm Distillation
        79727, -- 2209.10081 Revisiting Discrete Soft Actor-Critic
        80142, -- 2203.07092 The Multi-Agent Pickup and Delivery Problem: MAPF, MARL and Its Wareho
        80235, -- 2201.13259 Trajectory balance: Improved credit assignment in GFlowNets
        80301, -- 2109.08267 CompilerGym: Robust, Performant Compiler Optimization Environments for
        80466, -- 2110.03039 Optimized Recommender Systems with Deep Reinforcement Learning
        80665, -- 2106.09012 A learning agent that acquires social norms from public sanctions in d
        80675, -- 2106.06170 Taylor Expansion of Discount Factors
        80724, -- 2105.06323 Bootstrapping User and Item Representations for One-Class Collaborativ
        80936, -- 2101.02055 Geometric Entropic Exploration
        81009, -- 2011.09607 FinRL: A Deep Reinforcement Learning Library for Automated Stock Tradi
        81069, -- 2010.07777 A game-theoretic analysis of networked system control for common-pool
        81417, -- 2003.06259 Taylor Expansion Policy Optimization
        81458, -- 2002.00444 Deep Reinforcement Learning for Autonomous Driving: A Survey
        81463, -- 2001.09212 PCGRL: Procedural Content Generation via Reinforcement Learning
        81523, -- 1911.10334 Iteratively-Refined Interactive 3D Medical Image Segmentation with Mul
        81570, -- 1910.05865 Neural Program Synthesis By Self-Learning
        81604, -- 1909.08711 Segregation Dynamics with Reinforcement Learning and Agent Based Model
        81616, -- 1909.04840 A Deep Learning Approach to Grasping the Invisible
        81748, -- 1904.11694 Neural Logic Machines
        81806, -- 1902.09393 Cooperative Learning of Disjoint Syntax and Semantics
        81820, -- 1709.06560 Deep Reinforcement Learning that Matters
        81859, -- 1811.12354 Touchdown: Natural Language Navigation and Spatial Reasoning in Visual
        81925, -- 1809.03470 ViZDoom Competitions: Playing Doom from Pixels
        81955, -- 1808.00508 Neural Arithmetic Logic Units
        81956, -- 1804.02464 Differentiable plasticity: training plastic neural networks with backp
        82071, -- 1803.07055 Simple random search provides a competitive approach to reinforcement
        82222, -- 1706.05296 Value-Decomposition Networks For Cooperative Multi-Agent Learning
        82238, -- 1705.05363 Curiosity-driven Exploration by Self-supervised Prediction
        82263, -- 1703.03864 Evolution Strategies as a Scalable Alternative to Reinforcement Learni
        82276, -- 1702.03118 Sigmoid-Weighted Linear Units for Neural Network Function Approximatio
        82297, -- 1612.03801 DeepMind Lab
        82380, -- 1606.04671 Progressive Neural Networks
        82382, -- 1606.01540 OpenAI Gym
        82919, -- 2605.00425 AEM: Adaptive Entropy Modulation for Multi-Turn Agentic Reinforcement
        82991, -- 2604.26326 Addressing Performance Saturation for LLM RL via Precise Entropy Curve
        83120, -- 2605.07865 KL for a KL: On-Policy Distillation with Control Variate Baseline
        83843, -- 2605.28293 ProRL: Effective Reinforcement Learning for Proactive Recommendation v
        84408, -- 2512.15926 DSO: Direct Steering Optimization for Bias Mitigation
        85492, -- 2605.01736 Multi-Scale Gaussian-Language Map for Zero-shot Embodied Navigation an
        86021, -- 2505.15602 Deep learning for continuous-time stochastic control with jumps
        86060, -- 2508.14881 Compute-Optimal Scaling for Value-Based Deep RL
        86130, -- 2505.15544 A Temporal Difference Method for Stochastic Continuous Dynamics
        86356, -- 2412.04233 HyperMARL: Adaptive Hypernetworks for Multi-Agent RL
        86583, -- 2505.23150 Bigger, Regularized, Categorical: High-Capacity Value Functions are Ef
        86959, -- 2505.16732 Sequential Monte Carlo for Policy Optimization in Continuous POMDPs
        87004, -- 2509.18389 Towards Provable Emergence of In-Context Reinforcement Learning
        87137, -- 2506.07085 State Entropy Regularization for Robust Reinforcement Learning
        87328, -- 2505.19281 A Snapshot of Influence: A Local Data Attribution Framework for Online
        87445, -- 2509.01720 Succeed or Learn Slowly: Sample Efficient Off-Policy Reinforcement Lea
        87826, -- 2506.21037 Reinforcement Learning-Guided Data Selection via Redundancy Assessment
        88241, -- 2412.20977 UnrealZoo: Enriching Photo-realistic Virtual Worlds for Embodied AI
        88370, -- 2508.13503 AdaptiveAE: An Adaptive Exposure Strategy for HDR Capturing in Dynamic
        88754, -- 2405.17618 Symmetric Reinforcement Learning Loss for Robust Learning on Diverse T
        89019, -- 2405.19933 Learning Latent Graph Structures and their Uncertainty
        89069, -- 2503.19595 Optimizing Language Models for Inference Time Objectives using Reinfor
        89096, -- 2505.22781 Finite-Sample Convergence Bounds for Trust Region Policy Optimization
        89104, -- 2505.05262 Enhancing Cooperative Multi-Agent Reinforcement Learning with State Mo
        89300, -- 2506.03404 The Impact of On-Policy Parallelized Data Collection on Deep Reinforce
        89591, -- 2406.01939 Speeding up Policy Simulation in Supply Chain RL
        89663, -- 2505.18433 Finite-Time Global Optimality Convergence in Deep Neural Actor-Critic
        89770, -- 2505.19247 Improving Value Estimation Critically Enhances Vanilla Policy Gradient
        89857, -- 2506.00592 Mitigating Plasticity Loss in Continual Reinforcement Learning by Redu
        89860, -- 2505.06744 LineFlow: A Framework to Learn Active Control of Production Lines
        89921, -- 2502.07350 KABB: Knowledge-Aware Bayesian Bandits for Dynamic Expert Coordination
        90781, -- 2411.09176 Gazing at Rewards: Eye Movements as a Lens into Human and AI Decision-
        90951, -- 2504.02515 Exploration-Driven Generative Interactive Environments
        91265, -- 2412.14355 Enabling Realtime Reinforcement Learning at Scale with Staggered Async
        91266, -- 2410.18636 Multi-agent cooperation through learning-aware policy gradients
        91498, -- 2410.15910 Diverse Policies Recovering via Pointwise Mutual Information Weighted
        91517, -- 2409.05358 BAMDP Shaping: a Unified Framework for Intrinsic Motivation and Reward
        91583, -- 2410.14803 DistRL: An Asynchronous Distributed Reinforcement Learning Framework f
        91584, -- 2402.05187 Learning mirror maps in policy mirror descent
        91646, -- 2411.15014 On the Linear Speedup of Personalized Federated Reinforcement Learning
        91861, -- 2410.21794 Inverse Attention Agents for Multi-Agent Systems
        92106, -- 2404.08003 Asynchronous Federated Reinforcement Learning with Policy Gradient Upd
        92313, -- 2302.02182 Online Reinforcement Learning in Non-Stationary Context-Driven Environ
        92364, -- 2410.11689 BlendRL: A Framework for Merging Symbolic and Neural Policy Learning
        92430, -- 2408.08761 Mitigating Information Loss in Tree-Based Reinforcement Learning via D
        92642, -- 2510.16614 Count Counts: Motivating Exploration in LLM Reasoning with Count-based
        92791, -- 2505.13696 Building spatial world models from sparse transitional episodic memori
        92874, -- 2510.01540 Towards Better Optimization For Listwise Preference in Diffusion Model
        92930, -- 2506.16608 Distributions as Actions: A Unified Framework for Diverse Action Space
        93010, -- 2510.18460 Learning Boltzmann Generators via Constrained Mass Transport
        93034, -- 2602.12087 Geometry of Uncertainty: Learning Metric Spaces for Multimodal State E
        93042, -- 2510.06649 Local Reinforcement Learning with Action-Conditioned Root Mean Squared
        93196, -- 2510.00922 On Discovering Algorithms for Adversarial Imitation Learning
        93550, -- 2509.24116 Dual-Scale World Memory for LLM Agents towards Hard-Exploration Proble
        93643, -- 2602.17930 MIRA: Memory-Integrated Reinforcement Learning Agent with Limited LLM
        93765, -- 2503.14576 SocialJax: An Evaluation Suite for Multi-agent Reinforcement Learning
        93770, -- 2507.19234 Virne: A Comprehensive Benchmark for RL-based Network Resource Allocat
        93988, -- 2512.01228 On the Tension Between Optimality and Adversarial Robustness in Policy
        94476, -- 2509.23183 ZeroSiam: An Efficient Asymmetry for Test-Time Entropy Optimization wi
        94766, -- 2508.14893 Virtual Community: An Open World for Humans, Robots, and Society
        95024, -- 2503.03660 Chunking the Critic: A Transformer-based Soft Actor-Critic with N-Step
        95324, -- 2605.00159 E^2DT: Efficient and Effective Decision Transformer with Experience-Aw
        96654, -- 2510.15189 RM-RL: Role-Model Reinforcement Learning for Precise Robot Manipulatio
        97165, -- 2407.08626 RoboMorph: Evolving Robot Morphology Using Large Language Models
        97344, -- 2506.17564 Accelerating Residual Reinforcement Learning with Uncertainty Estimati
        98111, -- 2606.05597 AsyncWebRL: Efficient Multi-Step RL for Visual Web Agents
        98417, -- 2604.18401 StepPO: Step-Aligned Policy Optimization for Agentic Reinforcement Lea
        99275, -- 2605.18591 Randomized Advantage Transformation (RAT): Computing Natural Policy Gr
        99696, -- 2601.23075 RN-D: Discretized Categorical Actors for On-Policy Reinforcement Learn
        99790, -- 2601.11401 Factored Value Functions for Graph-Based Multi-Agent Reinforcement Lea
        99882, -- 2511.17852 Transformers with RL or SFT Provably Learn Sparse Boolean Functions, B
        99895, -- 2511.03100 Scaling Multi-Agent Environment Co-Design with Diffusion Models
        99903, -- 2512.20576 Performative Policy Gradient: Optimality in Performative Reinforcement
        100243, -- 2512.13727 RAST-MoE-RL: A Regime-Aware Spatio-Temporal MoE Framework for Deep Rei
        100383, -- 2602.00482 AReaL-DTA: Dynamic Tree Attention for Efficient Reinforcement Learning
        101440, -- 2411.19517 RL-SPH: Learning to Achieve Feasible Solutions for Integer Linear Prog
        101687, -- 2509.00338 Scalable Option Learning in High-Throughput Environments
        101923, -- 2605.24357 Refined Analysis of Entropy-Regularized Actor-Critic
        102528, -- 2606.00151 Emergence of Exploration in Policy Gradient Reinforcement Learning via
        102694, -- 2607.07508 Single-Rollout Asynchronous Optimization for Agentic Reinforcement Lea
        103546, -- 2507.02841 StepHint: Multi-level Stepwise Hints Enhance Reinforcement Learning to
        103880, -- 2004.12919 First return, then explore
        103881, -- 2009.04416 Phasic Policy Gradient
        103886, -- 1903.00374 Model-Based Reinforcement Learning for Atari
        103894, -- 2102.10330 Decoupling Value and Policy for Generalization in Reinforcement Learni
        103943, -- 2303.07109 Transformer-based World Models Are Happy With 100k Interactions
        104308, -- 2607.15161 On-Policy Delta Distillation
        106234, -- 2604.16259 Beyond Distribution Sharpening: The Importance of Task Rewards
        106483, -- 2511.10843 Behaviour Policy Optimization: Provably Lower Variance Return Estimate
        106654, -- 2512.18623 LLM-CAS: Dynamic Neuron Perturbation for Real-Time Hallucination Corre
        106975, -- 2511.14262 Object-Centric World Models for Causality-Aware Reinforcement Learning
        107477, -- 2508.01883 Proactive Constrained Policy Optimization with Preemptive Penalty
        107959, -- 2506.05577 Policy Search, Retrieval, and Composition via Task Similarity in Colla
        108031, -- 2601.21389 Learning to Optimize Job Shop Scheduling Under Structural Uncertainty
        108393, -- 2508.19926 FARM: Frame-Accelerated Augmentation and Residual Mixture-of-Experts f
        109503, -- 2608.16590 Zetta ζ: An Efficient Closed-Loop Embodied Harness for Self-Evolving P
        110549, -- 2411.12736 ACING: Actor-Critic for Instruction Learning in Black-Box LLMs
        116589, -- 2312.09337 Promptable Behaviors: Personalizing Multi-Objective Rewards from Human
        117115, -- 2311.13793 Evidential Active Recognition: Intelligent and Prudent Open-World Embo
        121918, -- 1511.07247 NetVLAD: CNN architecture for weakly supervised place recognition
        122056, -- 2111.08575 GRI: General Reinforced Imitation and its Application to Vision-Based
        122331, -- 2609.33781 Surprising Success, Repeated Failure: Entropy-Guided Credit Assignment
        122336, -- 2609.36246 Learning from Teacher Continuations at Student States
        123028, -- 1911.10868 End-to-End Model-Free Reinforcement Learning for Urban Driving using I
        123303, -- 1811.04551 Learning Latent Dynamics for Planning from Pixels
        125074, -- 2609.30258 Temporal Gradient Inversion for Private Trajectory Reconstruction in E
        125509, -- 2609.34553 Verifying Neural Networks with Reinforcement Learning
        126187, -- 2605.17862 $\boldsymbol{f}$-OPD: Stabilizing Long-Horizon On-Policy Distillation
        127388, -- 2606.05800 SALT: When More Rollouts Don’t Help in Group-Based Policy Optimization
        127934, -- 2505.23686 ROTATE: Regret-driven Open-ended Training for Ad Hoc Teamwork
        128267, -- 2605.05812 Long-Horizon Q-Learning: Accurate Value Learning via n-Step Inequaliti
        128451, -- 2603.22273 Decoupling Exploration and Policy Optimization: Uncertainty Guided Tre
        128535, -- 2605.13554 Self-Supervised On-Policy Reinforcement Learning via Contrastive Proxi
        128718, -- 2605.08315 Reflective Prompted Policy Optimization: Trajectory-Grounded Revision
        129111, -- 2605.24490 Market Regime Council for Dynamic Credit Assignment in Multi-Agent LLM
        130829, -- 2605.07775 POETS: Uncertainty-Aware LLM Optimization via Compute-Efficient Policy
        130990  -- 2603.26097 Dynamic Tokenization via Reinforcement Patching: End-to-end Training a
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the A3C paper without naming, using or comparing against A3C'
FROM a3c_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING a3c_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING a3c_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- trpo: 30 links, 661 exclusions. Semantic Scholar returned 8558 citers of the source, 681 local.
CREATE TEMP TABLE trpo_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'trpo'
  AND p.id IN (
        158, -- 1502.05477 Trust Region Policy Optimization
        741, -- 1706.01905 Parameter Space Noise for Exploration
        804, -- 1707.06347 Proximal Policy Optimization Algorithms
        3599, -- 2005.09814 Mirror Descent Policy Optimization
        12568, -- 2301.11476 Generalized Munchausen Reinforcement Learning using Tsallis KL Diverge
        21653, -- 2310.05858 Distributional Soft Actor-Critic with Three Refinements
        22805, -- 2310.20380 Dropout Strategy in Reinforcement Learning: Limiting the Surrogate Obj
        24530, -- 2312.05405 Guaranteed Trust Region Optimization via Two-Phase KL Penalization
        26408, -- 2401.16025 Simple Policy Optimization
        26533, -- 2401.17880 Graph Attention-based Reinforcement Learning for Trajectory Design and
        51181, -- 2506.13862 StaQ it! Growing neural networks for Policy Mirror Descent
        52450, -- 2508.15144 Mobile-Agent-v3: Fundamental Agents for GUI Automation
        58029, -- 2604.18578 Bounded Ratio Reinforcement Learning
        59675, -- 2603.08239 Fibration Policy Optimization
        66719, -- 2510.08270 Evaluation of a Robust Control System in Real-World Cable-Driven Paral
        67005, -- 2510.03817 TROLL: Trust Regions improve Reinforcement Learning for Large Language
        68844, -- 2509.04501 Understanding Reinforcement Learning for Model Training, and future di
        69219, -- 2508.17784 Proximal Supervised Fine-Tuning
        81417, -- 2003.06259 Taylor Expansion Policy Optimization
        81832, -- 1901.04772 Transfer Learning for Prosthetics Using Imitation Learning
        89096, -- 2505.22781 Finite-Sample Convergence Bounds for Trust Region Policy Optimization
        89436, -- 2411.02957 Embedding Safety into RL: A New Take on Trust Region Methods
        89770, -- 2505.19247 Improving Value Estimation Critically Enhances Vanilla Policy Gradient
        92660, -- 2509.24991 Sampling Complexity of TD and PPO in RKHS
        93078, -- 2601.00116 GRL-SNAM: Geometric Reinforcement Learning with Differential Hamiltoni
        99536, -- 2602.04620 QUATRO: Query-Adaptive Trust Region Policy Optimization for LLM Fine-t
        100744, -- 2512.23075 Trust Region Masking for Long-Horizon LLM Reinforcement Learning
        101376, -- 2606.17664 Temporal Preference Optimization for Unsupervised Retrieval
        101719, -- 2606.15260 Trust-Region Diffusion Policies for Massively Parallel On-Policy RL
        130490  -- 2606.03382 Local Guidance, Global Impact: Gaussian-Reshaped Trust Region Unlocks
  );

DELETE FROM paper_method_exclusions x
USING trpo_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM trpo_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM trpo_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE trpo_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'trpo'
  AND p.id IN (
        200, -- 1506.02438 High-Dimensional Continuous Control Using Generalized Advantage Estima
        239, -- 1509.02971 Continuous control with deep reinforcement learning
        301, -- 1602.01783 Asynchronous Methods for Deep Reinforcement Learning
        397, -- 1606.03476 Generative Adversarial Imitation Learning
        565, -- 1701.03940 Scalable and Incremental Learning of Gaussian Mixture Models
        569, -- 1701.07274 Deep Reinforcement Learning: An Overview
        611, -- 1703.03400 Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks
        754, -- 1706.03741 Deep reinforcement learning from human preferences
        799, -- 1707.04873 Efficient Architecture Search by Network Transformation
        812, -- 1707.07012 Learning Transferable Architectures for Scalable Image Recognition
        830, -- 1708.01354 CASSL: Curriculum Accelerated Self-Supervised Learning
        903, -- 1710.02298 Rainbow: Combining Improvements in Deep Reinforcement Learning
        1021, -- 1712.06567 Deep Neuroevolution: Genetic Algorithms Are a Competitive Alternative
        1037, -- 1801.00690 DeepMind Control Suite
        1040, -- 1801.01290 Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learn
        1109, -- 1802.06070 Diversity is All You Need: Learning Skills without a Reward Function
        1128, -- 1802.09477 Addressing Function Approximation Error in Actor-Critic Methods
        1134, -- 1803.01164 The History Began from AlexNet: A Comprehensive Survey on Deep Learnin
        1201, -- 1804.00379 Recall Traces: Backtracking Models for Efficient Reinforcement Learnin
        1209, -- 1804.02717 DeepMimic: Example-Guided Deep Reinforcement Learning of Physics-Based
        1508, -- 1809.08267 Neural Approaches to Conversational AI
        1563, -- 1810.10191 Making Sense of Vision and Touch: Self-Supervised Learning of Multimod
        1634, -- 1811.07871 Scalable agent alignment via reward modeling: a research direction
        1702, -- 1812.05905 Soft Actor-Critic Algorithms and Applications
        1731, -- 1901.00137 A Theoretical Analysis of Deep Q-Learning
        1739, -- 1901.01753 Paired Open-Ended Trailblazer (POET): Endlessly Generating Increasingl
        1764, -- 1901.07186 Towards Learning to Imitate from a Single Video Demonstration
        2259, -- 1906.05838 Goal-conditioned Imitation Learning
        2551, -- 1909.07373 Policy Prediction Network: Model-Free Behavior Policy with Model-Based
        2562, -- 1909.08072 Adversarial Attacks and Defenses in Images, Graphs and Text: A Review
        2719, -- 1910.10897 Meta-World: A Benchmark and Evaluation for Multi-Task and Meta Reinfor
        2984, -- 2001.02792 On Computation and Generalization of Generative Adversarial Imitation
        2985, -- 2001.02811 Distributional Soft Actor-Critic: Off-Policy Reinforcement Learning fo
        3058, -- 2002.00632 Effective Diversity in Population Based Reinforcement Learning
        3146, -- 2002.11564 Mid-flight Propeller Failure Detection and Control of Propeller-defici
        3186, -- 2003.03051 Cost-Sensitive Portfolio Selection via Deep Reinforcement Learning
        3277, -- 2003.14089 Leverage the Average: an Analysis of KL Regularization in RL
        3437, -- 2004.13796 TextGAIL: Generative Adversarial Imitation Learning for Text Generatio
        3518, -- 2005.01643 Offline Reinforcement Learning: Tutorial, Review, and Perspectives on
        3565, -- 2005.05719 Smooth Exploration for Robotic Reinforcement Learning
        3608, -- 2005.10696 Novel Policy Seeking with Constrained Optimization
        3779, -- 2006.11751 Sample Factory: Egocentric 3D Control from Pixels at 100000 FPS with A
        3835, -- 2006.16785 Lipschitzness Is All You Need To Tame Off-policy Generative Adversaria
        4028, -- 2008.06924 Inverse Reinforcement Learning with Natural Language Goals
        4488, -- 2011.00702 Fast Reinforcement Learning with Incremental Gaussian Mixture Models
        4567, -- 2011.08463 Meta Automatic Curriculum Learning
        4580, -- 2011.09533 Is Independent Learning All You Need in the StarCraft Multi-Agent Chal
        4597, -- 2011.11012 Distributed Deep Reinforcement Learning: An Overview
        4931, -- 2101.09459 Advances and Challenges in Conversational Recommender Systems: A Surve
        4967, -- 2102.00714 NeoRL: A Near Real-World Benchmark for Offline Reinforcement Learning
        5434, -- 2104.06303 Learning and Planning in Complex Action Spaces
        5465, -- 2104.07495 Curiosity-Driven Exploration via Latent Bayesian Surprise
        5849, -- 2106.01086 Learning to schedule job-shop problems: Representation and policy lear
        5937, -- 2106.05110 Self-Paced Context Evaluation for Contextual Reinforcement Learning
        5976, -- 2106.06842 Recomposing the Reinforcement Learning Building Blocks with Hypernetwo
        6005, -- 2106.08272 Deep Reinforcement Learning for Conservation Decisions
        6076, -- 2106.11420 Policy Smoothing for Provably Robust Reinforcement Learning
        6201, -- 2107.03759 Analytically Tractable Hidden-States Inference in Bayesian Neural Netw
        6361, -- 2108.01832 Offline Decentralized Multi-Agent Reinforcement Learning
        6587, -- 2109.04504 Bootstrapped Meta-Learning
        6772, -- 2110.00641 Batch size-invariance for policy optimization
        6808, -- 2110.02639 On The Transferability of Deep-Q Networks
        6957, -- 2110.07985 On-Policy Model Errors in Reinforcement Learning
        7107, -- 2111.00210 Mastering Atari Games with Limited Data
        7227, -- 2111.08397 CLARA: A Constrained Reinforcement Learning Based Resource Allocation
        7677, -- 2201.03916 Automated Reinforcement Learning (AutoRL): A Survey and Open Problems
        7945, -- 2202.06239 Supported Policy Optimization for Offline Reinforcement Learning
        8164, -- 2203.03580 The Unsurprising Effectiveness of Pre-Trained Vision Models for Contro
        8283, -- 2203.08382 Dual Diffusion Implicit Bridges for Image-to-Image Translation
        8602, -- 2204.03084 Knowledge Infused Decoding
        8822, -- 2204.10817 Reward Reports for Reinforcement Learning
        9083, -- 2205.10330 A Review of Safe Reinforcement Learning: Methods, Theory and Applicati
        9465, -- 2206.06614 Transformers are Meta-Reinforcement Learners
        9525, -- 2206.08896 Evolution through Large Models
        9534, -- 2206.09328 A Survey on Model-based Reinforcement Learning
        9892, -- 2207.12141 Live in the Moment: Learning Dynamics Model Adapted to Evolving Policy
        10294, -- 2209.07288 Optimistic Curiosity Exploration and Conservative Exploitation with Li
        10307, -- 2209.07676 Conservative Dual Policy Optimization for Efficient Model-Based Reinfo
        10531, -- 2210.01241 Is Reinforcement Learning (Not) for Natural Language Processing: Bench
        10539, -- 2210.01422 Time-Varying Propensity Score to Bridge the Gap between the Past and P
        10719, -- 2210.05639 Discovered Policy Optimisation
        10762, -- 2210.06479 Real World Offline Reinforcement Learning with Realistic Data Source
        10841, -- 2210.08607 The Impact of Task Underspecification in Evaluating Deep Reinforcement
        11015, -- 2210.13011 On Many-Actions Policy Gradient
        11233, -- 2211.03032 Decentralized Policy Optimization
        11318, -- 2211.06839 Out-of-Dynamics Imitation Learning from Multimodal Demonstrations
        11683, -- 2211.15956 Offline Reinforcement Learning with Closed-Form Policy Improvement Ope
        12132, -- 2212.10439 Policy Gradient in Robust MDPs with Global Convergence Guarantee
        12215, -- 2212.12735 An Adaptive Deep RL Method for Non-Stationary Environments with Piecew
        12219, -- 2212.12809 Understanding the Complexity Gains of Single-Task RL with a Curriculum
        12534, -- 2301.10932 On the Global Convergence of Risk-Averse Policy Gradient Methods with
        12698, -- 2301.13362 Optimizing DDPM Sampling with Shortcut Fine-Tuning
        12735, -- 2302.00141 Revisiting Bellman Errors for Offline Model Selection
        12784, -- 2302.01275 ReLOAD: Reinforcement Learning with Optimistic Ascent-Descent for Last
        12820, -- 2302.01734 Stochastic Policy Gradient Methods: Improved Sample Complexity for Fis
        12870, -- 2302.02607 Target-based Surrogates for Stochastic Optimization
        13157, -- 2302.08560 Dual RL: Unification and New Methods for Reinforcement and Imitation L
        13275, -- 2302.12120 Sequential Counterfactual Risk Minimization
        13551, -- 2303.04129 Foundation Models for Decision Making: Problems, Methods, and Opportun
        13556, -- 2303.04212 ConBaT: Control Barrier Transformer for Safe Policy Learning
        13826, -- 2303.09390 On the Interplay Between Misspecification and Sub-optimality Gap in Li
        14914, -- 2304.12187 TempoRL: laser pulse temporal shape optimization with Deep Reinforceme
        14994, -- 2304.13774 Distance Weighted Supervised Learning for Offline Interaction Data
        15092, -- 2305.00654 Representations and Exploration for Deep Reinforcement Learning using
        15310, -- 2305.04361 Truncating Trajectories in Monte Carlo Reinforcement Learning
        15338, -- 2305.04819 Local Optimization Achieves Global Optimality in Multi-Agent Reinforce
        15517, -- 2305.07911 Delay-Adapted Policy Optimization and Improved Regret for Adversarial
        15750, -- 2305.11340 Bayesian Reparameterization of Reward-Conditioned Reinforcement Learni
        15922, -- 2305.13185 Regularization and Variance-Weighted Regression Achieves Minimax Optim
        15939, -- 2305.13301 Training Diffusion Models with Reinforcement Learning
        15998, -- 2305.13795 Proximal Policy Gradient Arborescence for Quality Diversity Reinforcem
        16341, -- 2305.16554 Emergent Agentic Transformer from Chain of Hindsight Experience
        16420, -- 2305.17342 Rethinking Adversarial Policies: A Generalized Attack Formulation and
        16670, -- 2305.19922 Representation-Driven Reinforcement Learning
        16690, -- 2305.20081 Efficient Diffusion Policies for Offline Reinforcement Learning
        16715, -- 2306.00172 Learning for Edge-Weighted Online Bipartite Matching with Robustness G
        16802, -- 2306.00972 Improving and Benchmarking Offline Reinforcement Learning Algorithms
        16892, -- 2306.01854 Reinforcement Learning with General Utilities: Simpler Variance Reduct
        16921, -- 2306.02231 Fine-Tuning Language Models with Advantage-Induced Policy Alignment
        17023, -- 2306.03362 Boosting Offline Reinforcement Learning with Action Preference Query
        17039, -- 2306.03530 RLtools: A Fast, Portable Deep Reinforcement Learning Library for Cont
        17250, -- 2306.06265 Near-optimal Conservative Exploration in Reinforcement Learning under
        17428, -- 2306.08641 Towards AGI in Computer Vision: Lessons Learned from GPT and Large Lan
        17515, -- 2306.09554 Low-Switching Policy Gradient with Exploration via Online Sensitivity
        17589, -- 2306.10882 AdaStop: adaptive statistical testing for sound comparisons of Deep RL
        17640, -- 2306.11816 Learning to Generate Better Than Your LLM
        18144, -- 2307.04964 Secrets of RLHF in Large Language Models Part I: PPO
        18290, -- 2307.08168 Enabling Efficient, Reliable Real-World Reinforcement Learning with Ap
        18348, -- 2307.08962 REX: Rapid Exploration and eXploitation for AI Agents
        18602, -- 2307.13192 Counterfactual Explanation Policies in RL
        18611, -- 2307.13372 Submodular Reinforcement Learning
        18918, -- 2308.02151 Retroformer: Retrospective Large Language Agents with Policy Gradient
        18961, -- 2308.03028 Pre-Trained Large Language Models for Industrial Control
        19681, -- 2308.12030 Prompt-Based Length Controlled Generation with Reinforcement Learning
        19854, -- 2308.14328 Reinforcement Learning for Generative AI: A Survey
        20139, -- 2309.02632 Deep Reinforcement Learning from Hierarchical Preference Design
        20341, -- 2309.06553 Query-Dependent Prompt Evaluation and Optimization with Offline Invers
        21063, -- 2309.16973 Towards Robust Offline-to-Online Reinforcement Learning via Uncertaint
        21118, -- 2310.00036 Cleanba: A Reproducible and Efficient Distributed Reinforcement Learni
        21132, -- 2310.00212 Pairwise Proximal Policy Optimization: Harnessing Relative Feedback fo
        21373, -- 2310.02671 Beyond Stationarity: Convergence Analysis of Stochastic Softmax Policy
        21457, -- 2310.03646 TRAM: Bridging Trust Regions and Sharpness Aware Minimization
        21506, -- 2310.04373 Confronting Reward Model Overoptimization with Constrained RLHF
        21686, -- 2310.06147 Reinforcement Learning in the Era of LLMs: What is Essential? What is
        21793, -- 2310.07433 Imitation Learning from Observation with Automatic Discount Scheduling
        21819, -- 2310.07747 Accountability in Offline Reinforcement Learning: Explaining Decisions
        22470, -- 2310.15719 AGaLiTe: Approximate Gated Linear Transformers for Online Reinforcemen
        22818, -- 2310.20663 Offline RL with Observation Histories: Analyzing and Improving Sample
        23002, -- 2311.03351 Uni-O4: Unifying Online and Offline Deep Reinforcement Learning with M
        23095, -- 2311.04898 Two Complementary Perspectives to Continual Learning: Ask Not Only Wha
        23298, -- 2311.08290 On-Policy Policy Gradient Reinforcement Learning Without On-Policy Sam
        23315, -- 2311.08384 Offline Data Enhanced On-Policy Policy Gradient with Provable Guarante
        23529, -- 2311.11385 Multi-Task Reinforcement Learning with Mixture of Orthogonal Experts
        23874, -- 2311.16714 Embodied Multi-Modal Agent trained by an LLM from a Parallel TextWorld
        24046, -- 2311.18736 Controlgym: Large-Scale Control Environments for Benchmarking Reinforc
        24505, -- 2312.05162 A Review of Cooperation in Multi-agent Learning
        24555, -- 2312.05742 The Generalization Gap in Offline Reinforcement Learning
        24701, -- 2312.07551 Language Model Alignment with Elastic Reset
        25340, -- 2401.00243 Uncertainty-Penalized Reinforcement Learning from Human Feedback with
        25485, -- 2401.02349 A Survey Analyzing Generalization in Deep Reinforcement Learning
        25582, -- 2401.04056 A Minimaximalist Approach to Reinforcement Learning from Human Feedbac
        25833, -- 2401.07886 Learned Best-Effort LLM Serving
        26038, -- 2401.10568 CivRealm: A Learning and Reasoning Odyssey in Civilization for Decisio
        26045, -- 2401.10700 Safe Offline Reinforcement Learning with Feasibility-Guided Diffusion
        26090, -- 2401.11437 Open the Black Box: Step-based Policy Updates for Temporally-Correlate
        26091, -- 2401.11458 Linear Alignment: A Closed-form Solution for Aligning Human Preference
        26119, -- 2401.11963 Bridging Evolutionary Algorithms and Reinforcement Learning: A Compreh
        26249, -- 2401.13662 The Definitive Guide to Policy Gradients in Deep Reinforcement Learnin
        26813, -- 2402.03046 Open RL Benchmark: Comprehensive Tracked Experiments for Reinforcement
        26835, -- 2402.03284 Deal, or no deal (or who knows)? Forecasting Uncertainty in Conversati
        26913, -- 2402.03988 REBORN: Reinforcement-Learned Boundary Segmentation with Iterative Tra
        27065, -- 2402.05828 Discovering Temporally-Aware Reinforcement Learning Algorithms
        27246, -- 2402.08265 A Dense Reward View on Aligning Text-to-Image Diffusion with Preferenc
        27655, -- 2402.12874 Skill or Luck? Return Decomposition via Advantage Functions
        27809, -- 2402.14528 ACE : Off-Policy Actor-Critic with Causality-Aware Entropy Regularizat
        27822, -- 2402.14688 Q-Probe: A Lightweight Approach to Reward Maximization for Language Mo
        28283, -- 2403.00991 SELFI: Autonomous Self-Improvement with Reinforcement Learning for Soc
        28796, -- 2403.08694 TeaMs-RL: Teaching LLMs to Generate Better Instruction Datasets via Re
        28938, -- 2403.10553 Learning to Watermark LLM-generated Text via Reinforcement Learning
        29970, -- 2404.03715 Direct Nash Optimization: Teaching Language Models to Self-Improve wit
        30285, -- 2404.08495 Dataset Reset Policy Optimization for RLHF
        30367, -- 2404.09656 Learn Your Reference Model for Real Good Alignment
        30424, -- 2404.10642 Self-playing Adversarial Language Game Enhances LLM Reasoning
        30500, -- 2404.11999 Token-level Direct Preference Optimization
        30784, -- 2404.16767 REBEL: Reinforcement Learning via Regressing Relative Rewards
        30786, -- 2404.16779 DrS: Learning Reusable Dense Rewards for Multi-Stage Tasks
        31361, -- 2405.10292 Fine-Tuning Large Vision-Language Models as Decision-Making Agents via
        31553, -- 2405.14093 A Survey on Vision-Language-Action Models for Embodied AI
        31574, -- 2405.14314 Towards Efficient LLM Grounding for Embodied Multi-Agent Collaboration
        32054, -- 2405.19909 Adaptive Advantage-Guided Policy Regularization for Offline Reinforcem
        33174, -- 2406.11896 DigiRL: Training In-The-Wild Device-Control Agents with Autonomous Rei
        33213, -- 2406.12168 BPO: Staying Close to the Behavior LLM Creates Better Online LLM Align
        33597, -- 2406.16768 WARP: On the Benefits of Weight Averaged Rewarded Policies
        34434, -- 2407.07787 Continuous Control with Coarse-to-fine Reinforcement Learning
        34891, -- 2407.13221 Multimodal Label Relevance Ranking via Reinforcement Learning
        34893, -- 2407.13237 LLM-Empowered State Representation for Reinforcement Learning
        35124, -- 2407.16677 From Imitation to Refinement -- Residual RL for Precise Assembly
        35357, -- 2407.21075 Apple Intelligence Foundation Language Models
        37463, -- 2409.19256 HybridFlow: A Flexible and Efficient RLHF Framework
        37673, -- 2410.01679 VinePPO: Unlocking RL Potential For LLM Reasoning Through Refined Cred
        37728, -- 2410.02172 Abstract Reward Processes: Leveraging State Abstraction for Consistent
        37737, -- 2410.02236 C-MORL: Multi-Objective Reinforcement Learning through Efficient Disco
        37803, -- 2410.02743 MA-RLHF: Reinforcement Learning from Human Feedback with Macro Actions
        37966, -- 2410.04612 Regressing the Relative Future: Efficient Policy Optimization for Mult
        38498, -- 2410.11020 Improving the Language Understanding Capabilities of Large Language Mo
        38814, -- 2410.14606 Streaming Deep Reinforcement Learning Finally Works
        39085, -- 2410.18252 Asynchronous RLHF: Faster and More Efficient Off-Policy RL for Languag
        39326, -- 2410.21966 PrefPaint: Aligning Image Inpainting Diffusion Model with Human Prefer
        39569, -- 2411.01493 Sample-Efficient Alignment for LLMs
        39682, -- 2411.03817 From Novice to Expert: LLM Agent Policy Optimization via Step-wise Rei
        39710, -- 2411.04291 Unfair Alignment: Examining Safety Alignment Across Vision Encoder Lay
        41102, -- 2412.04628 SWEPO: Simultaneous Weighted Preference Optimization for Group Contras
        41551, -- 2412.10400 Reinforcement Learning Enhanced LLMs: A Survey
        42651, -- 2501.04982 CuRLA: Curriculum Learning Based Deep Reinforcement Learning for Auton
        42917, -- 2501.09620 Beyond Reward Hacking: Causal Rewards for Large Language Model Alignme
        43296, -- 2501.16142 Towards General-Purpose Model-Free Reinforcement Learning
        43564, -- 2502.01384 Fine-Tuning Discrete Diffusion Models with Policy Gradient Methods
        45002, -- 2502.18293 AMPO: Active Multi-Preference Optimization
        45039, -- 2502.18770 Reward Shaping to Mitigate Reward Hacking in RLHF
        45259, -- 2503.00499 Shaping Laser Pulses with Reinforcement Learning
        45263, -- 2503.00533 BodyGen: Advancing Towards Efficient Embodiment Co-Design
        45806, -- 2503.07572 Optimizing Test-Time Compute via Meta Reinforcement Fine-Tuning
        45973, -- 2503.09501 ReMA: Learning to Meta-think for LLMs with Multi-Agent Reinforcement L
        46469, -- 2503.16252 Fin-R1: A Large Language Model for Financial Reasoning through Reinfor
        46949, -- 2503.22677 DSO: Aligning 3D Generators with Simulation Feedback for Physical Soun
        47063, -- 2503.24289 Rec-R1: Bridging Generative Large Language Models and User-Centric Rec
        47096, -- 2504.00424 Hawkeye:Efficient Reasoning with Model Collaboration
        47370, -- 2504.05150 A Reinforcement Learning Method for Environments with Stochastic Varia
        47784, -- 2504.12083 Self-alignment of Large Video Language Models with Refined Regularized
        47981, -- 2504.14945 Learning to Reason under Off-Policy Guidance
        48067, -- 2504.16129 MARFT: Multi-Agent Reinforcement Fine-Tuning
        48189, -- 2504.19599 GVPO: Group Variance Policy Optimization for Large Language Model Post
        48681, -- 2505.08364 Learning Like Humans: Advancing LLM Reasoning Capabilities via Adaptiv
        48882, -- 2505.11595 Spectral Policy Optimization: Coloring your Incorrect Reasoning in GRP
        48887, -- 2505.11711 Reinforcement Learning Finetunes Small Subnetworks in Large Language M
        48955, -- 2505.12366 DisCO: Reinforcing Large Reasoning Models with Discriminative Constrai
        48958, -- 2505.12432 Observe-R1: Unlocking Reasoning Abilities of MLLMs with Dynamic Progre
        49149, -- 2505.14264 AAPO: Enhance the Reasoning Capabilities of LLMs with Advantage Moment
        49444, -- 2505.16826 KTAE: A Model-Free Algorithm to Key-Tokens Advantage Estimation in Mat
        49526, -- 2505.17508 On the Design of KL-Regularized Policy Gradient Algorithms for LLM Rea
        49574, -- 2505.18116 Bridging Supervised Learning and Reinforcement Learning in Math Reason
        49624, -- 2505.18536 Reinforcement Fine-Tuning Powers Reasoning Capability of Multimodal La
        49664, -- 2505.18917 Behavior Injection: Preparing Language Models for Reinforcement Learni
        49876, -- 2505.20359 Risk-aware Direct Preference Optimization under Nested Risk Measure
        50020, -- 2505.22617 The Entropy Mechanism of Reinforcement Learning for Reasoning Language
        50107, -- 2505.23458 Diffusion Guidance Is a Controllable Policy Improvement Operator
        50168, -- 2505.23816 A Course Correction in Steerability Evaluation: Revealing Miscalibrati
        50192, -- 2505.24034 LlamaRL: A Distributed Asynchronous Reinforcement Learning Framework f
        50696, -- 2506.05968 Gradual Transition from Bellman Optimality Operator to Bellman Operato
        50749, -- 2506.07160 GeometryZero: Improving Geometry Solving for LLM with Group Contrastiv
        51519, -- 2506.21495 Bridging Offline and Online Reinforcement Learning for LLMs
        51543, -- 2506.21872 A Survey of Continual Reinforcement Learning
        51709, -- 2507.04742 Activation Steering for Chain-of-Thought Compression
        51790, -- 2507.06892 Squeeze the Soaked Sponge: Efficient Off-policy Reinforcement Finetuni
        52303, -- 2508.07629 Klear-Reasoner: Advancing Reasoning Capability via Gradient-Preserving
        52656, -- 2509.04419 Towards a Unified View of Large Language Model Post-Training
        52709, -- 2509.07414 Language Self-Play For Data-Free Training
        52710, -- 2509.07430 The Choice of Divergence: A Neglected Key to Mitigating Diversity Coll
        52726, -- 2509.08755 AgentGym-RL: Training LLM Agents for Long-Horizon Decision Making thro
        52746, -- 2509.09674 SimpleVLA-RL: Scaling VLA Training via Reinforcement Learning
        52917, -- 2509.16591 From Uniform to Heterogeneous: Tailoring Policy Optimization to Every
        53033, -- 2509.22921 Rethinking Large Language Model Distillation: A Constrained Markov Dec
        53105, -- 2510.00977 It Takes Two: Your GRPO Is Secretly DPO
        53109, -- 2510.01180 BroRL: Scaling Reinforcement Learning via Broadened Exploration
        53135, -- 2510.02245 ExGRPO: Learning to Reason from Experience
        53167, -- 2509.24203 Group-Relative REINFORCE Is Secretly an Off-Policy Algorithm: Demystif
        53169, -- 2510.02272 Parallel Scaling Law: Unveiling Reasoning Generalization through A Cro
        53231, -- 2510.01161 Prosperity before Collapse: How Far Can Off-Policy RL Reach with Stale
        53266, -- 2510.05592 In-the-Flow Agentic System Optimization for Effective Planning and Too
        53473, -- 2510.09541 SPG: Sandwiched Policy Gradient for Masked Diffusion Language Models
        53812, -- 2510.21583 Sample By Step, Optimize By Chunk: Chunk-Level GRPO For Text-to-Image
        53895, -- 2510.23925 Latent Chain-of-Thought for Visual Reasoning
        54031, -- 2510.26491 Data-Efficient RLVR via Off-Policy Influence Guidance
        54079, -- 2511.03773 Scaling Agent Learning via Experience Synthesis
        54128, -- 2511.06449 FLEX: Continuous Agent Evolution via Forward Learning from Experience
        54174, -- 2511.10643 Black-Box On-Policy Distillation of Large Language Models
        54394, -- 2511.20633 Reinforcing Action Policies by Prophesying
        54504, -- 2512.02581 GoRL: An Algorithm-Agnostic Framework for Online Reinforcement Learnin
        54606, -- 2512.05591 Entropy Ratio Clipping as a Soft Global Constraint for Stable Reinforc
        54726, -- 2512.09756 MOA: Multi-Objective Alignment for Role-Playing Agents
        54856, -- 2512.14202 Understanding and Improving Hyperbolic Deep Reinforcement Learning
        54931, -- 2512.19682 GenEnv: Difficulty-Aligned Co-Evolution Between LLM Agents and Environ
        55337, -- 2601.10201 PRL: Process Reward Learning Improves LLMs' Reasoning Ability and Broa
        55443, -- 2601.15165 The Flexibility Trap: Why Arbitrary Order Limits Reasoning Potential i
        55542, -- 2601.19897 Self-Distillation Enables Continual Learning
        55554, -- 2601.20802 Reinforcement Learning via Self-Distillation
        55614, -- 2601.18005 Flow-based Extremal Mathematical Structure Discovery
        55767, -- 2602.04879 Rethinking the Trust Region in LLM Reinforcement Learning
        55832, -- 2602.05933 Approximation of Log-Partition Function in Policy Mirror Descent Induc
        55839, -- 2602.05494 A Unified Framework for Rethinking Policy Divergence Measures in GRPO
        55931, -- 2602.09782 Flexible Entropy Control in RLVR with Gradient-Preserving Perspective
        56009, -- 2602.10609 Online Causal Kalman Filtering for Stable and Effective Policy Optimiz
        56057, -- 2602.09021 χ_{0}: Resource-Aware Robust Manipulation via Taming Distributional In
        56167, -- 2602.15620 STAPO: Stabilizing Reinforcement Learning for LLMs by Silencing Rare S
        56222, -- 2602.10693 VESPO: Variational Sequence-Level Soft Policy Optimization for Stable
        56361, -- 2602.23881 LK Losses: Direct Acceptance Rate Optimization for Speculative Decodin
        56376, -- 2602.22495 Reinforcement-aware Knowledge Distillation for LLM Reasoning
        56451, -- 2603.01563 LFPO: Likelihood-Free Policy Optimization for Masked Diffusion Models
        56522, -- 2603.06743 Stabilizing Reinforcement Learning for Diffusion Language Models
        56874, -- 2603.16929 MHPO: Modulated Hazard-aware Policy Optimization for Stable Reinforcem
        56902, -- 2603.19987 Breaking the Capability Ceiling of LLM Post-Training by Reintroducing
        56918, -- 2603.19470 Adaptive Layerwise Perturbation: Unifying Off-Policy Corrections for L
        56931, -- 2603.21872 Manifold-Aware Exploration for Reinforcement Learning in Video Generat
        56939, -- 2603.21383 PivotRL: High Accuracy Agentic Post-Training at Low Compute Cost
        57199, -- 2604.02007 Apriel-Reasoner: RL Post-Training for General-Purpose and Efficient Re
        57495, -- 2604.06159 Target Policy Optimization
        57574, -- 2604.13902 DiPO: Disentangled Perplexity Policy Optimization for Fine-grained Exp
        57996, -- 2604.19695 Planning in entropy-regularized Markov decision processes and games
        58213, -- 2604.12632 Calibration-Aware Policy Optimization for Reasoning LLMs
        58398, -- 2604.07774 RoboAgent: Chaining Basic Capabilities for Embodied Task Planning
        59105, -- 2603.20526 Does This Gradient Spark Joy?
        59106, -- 2603.20521 Delightful Distributed Policy Gradient
        59145, -- 2603.18756 Are complicated loss functions necessary for teaching LLMs to reason?
        59207, -- 2603.17461 AR-CoPO: Align Autoregressive Video Generation with Contrastive Policy
        59318, -- 2603.15388 Efficient Morphology-Control Co-Design via Stackelberg Proximal Policy
        59393, -- 2603.14608 Delightful Policy Gradient
        60075, -- 2603.01162 Demystifying Group Relative Policy Optimization: Its Policy Gradient i
        60111, -- 2603.00730 MO-MIX: Multi-Objective Multi-Agent Cooperative Decision-Making With D
        60611, -- 2602.14697 Evolutionary System Prompt Learning for Reinforcement Learning in LLMs
        60695, -- 2602.13407 On-Policy Supervised Fine-Tuning for Efficient Reasoning
        60722, -- 2602.12642 Beyond Normalization: Rethinking the Partition Function as a Difficult
        60760, -- 2602.12155 FAIL: Flow Matching Adversarial Imitation Learning for Image Generatio
        60767, -- 2602.12063 VLAW: Iterative Co-Improvement of Vision-Language-Action Policy and Wo
        60872, -- 2602.10635 OmniSapiens: A Foundation Model for Social Behavior Processing via Het
        61326, -- 2602.03635 TRE: Encouraging Exploration in the Trust Region
        61360, -- 2602.03190 Prompt Augmentation Scales up GRPO Training on Mathematical Reasoning
        61399, -- 2602.02710 Maximum Likelihood Reinforcement Learning
        61468, -- 2602.01705 Beyond Mode Elicitation: Diversity-Preserving Reinforcement Learning v
        61515, -- 2602.03876 GOPO: Policy Optimization using Ranked Rewards
        61543, -- 2602.01156 PolicyFlow: Policy Optimization with Continuous Normalizing Flow in Re
        61836, -- 2601.21476 SOUP: Token-level Single-sample Mix-policy Reinforcement Learning for
        61881, -- 2601.21094 Safety Generalization Under Distribution Shift in Safe Reinforcement L
        62644, -- 2601.07142 Dynamics of Multi-Agent Actor-Critic Learning in Stochastic Games: fro
        62726, -- 2601.05787 From Off-Policy to On-Policy: Enhancing GUI Agents via Bi-level Expert
        62877, -- 2601.03723 ETR: Outcome-Guided Elastic Trust Regions for Policy Optimization
        62936, -- 2601.03320 Ratio-Variance Regularized Policy Optimization for Efficient LLM Fine-
        62971, -- 2510.26109 Do Not Step Into the Same River Twice: Learning to Reason from Trial a
        63030, -- 2601.01743 AI Agent Systems: Architectures, Applications, and Evaluation
        63258, -- 2512.22832 MARPO: A Reflective Policy Optimization for Multi Agent Reinforcement
        63624, -- 2512.15089 Beyond Fast and Slow: Cognitive-Inspired Elastic Reasoning for Large L
        64041, -- 2512.06547 A-3PO: Accelerating Asynchronous LLM Training with Staleness-aware Pro
        64112, -- 2512.04770 Embodied Co-Design for Rapidly Evolving Agents: Taxonomy, Frontiers, a
        64374, -- 2512.00319 RL-Struct: A Lightweight Reinforcement Learning Framework for Reliable
        65321, -- 2511.04800 Explore Data Left Behind in Reinforcement Learning for Reasoning Langu
        65623, -- 2510.26475 ReSpec: Towards Optimizing Speculative Decoding in Reinforcement Learn
        65950, -- 2510.20815 Generative Reasoning Recommendation via LLMs
        66077, -- 2510.18814 Online SFT for LLM Reasoning: Surprising Effectiveness of Self-Tuning
        66113, -- 2510.18913 ADPO: Anchored Direct Preference Optimization
        66127, -- 2506.07259 ALINE: Joint Amortization for Bayesian Inference and Active Data Acqui
        66721, -- 2510.08233 Enhancing Reasoning for Diffusion LLMs via Distribution Matching Polic
        66953, -- 2510.04474 DRPO: Efficient Reasoning via Decoupled Reward Policy Optimization
        67020, -- 2510.03515 RAPID: An Efficient Reinforcement Learning Algorithm for Small Languag
        67196, -- 2510.00911 RiskPO: Risk-based Policy Optimization via Verifiable Reward for LLM P
        67207, -- 2510.00819 Stabilizing Policy Gradients for Sample-Efficient Reinforcement Learni
        67383, -- 2509.25424 Polychromic Objectives for Reinforcement Learning
        67551, -- 2509.23753 Anchored Supervised Fine-Tuning
        67773, -- 2509.21474 d2: Improved Techniques for Training Reasoning Diffusion Language Mode
        67781, -- 2509.21282 It's Not You, It's Clipping: A Soft Trust-Region via Probability Smoot
        67873, -- 2510.00022 Learning to Lead Themselves: Agentic AI in MAS using MARL
        68100, -- 2509.16742 Sycophancy Mitigation Through Reinforcement Learning with Uncertainty-
        68358, -- 2509.12179 Co-Alignment: Rethinking Alignment as Bidirectional Human-AI Cognitive
        68861, -- 2509.01684 Reinforcement Learning for Machine Learning Engineering Agents
        69308, -- 2508.16474 Reinforcement Learning-based Control via Y-wise Affine Neural Networks
        69682, -- 2508.10409 AnalogSeeker: An Open-source Foundation Language Model for Analog Circ
        69861, -- 2508.07945 PCHands: PCA-based Hand Pose Synergy Representation on Manipulators wi
        70047, -- 2508.05242 CodeBoost: Boosting Code LLMs by Squeezing Knowledge from Code Snippet
        70217, -- 2508.03772 GTPO: Trajectory-Based Policy Optimization in Large Language Models
        70625, -- 2507.21053 Flow Matching Policy Gradients
        71854, -- 2503.23101 RL2Grid: Benchmarking Reinforcement Learning in Power Grid Operations
        71913, -- 2506.15051 Sequential Policy Gradient for Adaptive Hyperparameter Optimization
        72584, -- 2505.22257 Revisiting Group Relative Policy Optimization: Insights into On-Policy
        72681, -- 2505.20686 Accelerating RL for LLM Reasoning with Optimal Advantage Regression
        72913, -- 2505.14975 Flattening Hierarchies with Policy Bootstrapping
        73033, -- 2505.11289 Meta-World+: An Improved, Standardized, RL Benchmark
        73079, -- 2505.08988 Generalization in Monitored Markov Decision Processes (Mon-MDPs)
        73086, -- 2505.08376 Adaptive Diffusion Policy Optimization for Robotic Manipulation
        73179, -- 2505.03181 VLM Q-Learning: Aligning Vision-Language Models for Interactive Decisi
        73441, -- 2504.14305 Adversarial Locomotion and Motion Imitation for Humanoid Policy Learni
        74358, -- 2503.00897 A Simple and Effective Reinforcement Learning Method for Text-to-Image
        74490, -- 2502.17813 Safe Multi-Agent Navigation guided by Goal-Conditioned Safe Reinforcem
        74609, -- 2502.12862 RobotIQ: Empowering Mobile Robots with Human-Level Planning for Real-W
        76091, -- 2410.08315 Avoiding mode collapse in diffusion models fine-tuned with reinforceme
        76802, -- 2407.04811 Simplifying Deep Temporal Difference Learning
        77033, -- 2406.07541 CDSA: Conservative Denoising Score-based Algorithm for Offline Reinfor
        78157, -- 2312.02561 DanZero+: Dominating the GuanDan Game through Reinforcement Learning
        78414, -- 2310.04128 Reinforcement Learning with Fast and Forgetful Memory
        78418, -- 2310.03379 Safe Reinforcement Learning via Hierarchical Adaptive Chance-Constrain
        78519, -- 2309.09055 Exploring the impact of low-rank adaptation on the performance, effici
        78704, -- 2210.07184 Towards Multi-Agent Reinforcement Learning driven Over-The-Counter Mar
        79228, -- 2303.10692 Boundary-aware Supervoxel-level Iteratively Refined Interactive 3D Ima
        79340, -- 2302.11312 Behavior Proximal Policy Optimization
        79434, -- 2301.06512 DRL-VO: Learning to Navigate Through Crowded Dynamic Scenes Using Velo
        79580, -- 2211.06665 A Survey on Explainable Reinforcement Learning: Concepts, Algorithms,
        79719, -- 2209.12713 Multi-Agent Coordination via Multi-Level Communication
        79727, -- 2209.10081 Revisiting Discrete Soft Actor-Critic
        79907, -- 2206.04890 Adversarial Counterfactual Environment Model Learning
        80122, -- 2203.10910 Quad2Plane: An Intermediate Training Procedure for Online Exploration
        80645, -- 2106.13125 Unifying Gradient Estimators for Meta-Reinforcement Learning via Off-P
        80650, -- 2106.11609 Distributional Gradient Matching for Learning Uncertain Neural Dynamic
        80675, -- 2106.06170 Taylor Expansion of Discount Factors
        80918, -- 2102.00824 HAMMER: Multi-Level Coordination of Reinforcement Learning Agents via
        81195, -- 2007.12509 Monte-Carlo Tree Search as Regularized Policy Optimization
        81458, -- 2002.00444 Deep Reinforcement Learning for Autonomous Driving: A Survey
        81570, -- 1910.05865 Neural Program Synthesis By Self-Learning
        81609, -- 1909.06493 Flight Controller Synthesis Via Deep Reinforcement Learning
        81820, -- 1709.06560 Deep Reinforcement Learning that Matters
        81824, -- 1901.08652 Learning agile and dynamic motor skills for legged robots
        81907, -- 1810.03516 Safe-To-Explore State Spaces: Ensuring Safe Exploration in Policy Sear
        81973, -- 1806.08295 How Many Random Seeds? Statistical Power Analysis in Deep Reinforcemen
        82028, -- 1805.00909 Reinforcement Learning and Control as Probabilistic Inference: Tutoria
        82071, -- 1803.07055 Simple random search provides a competitive approach to reinforcement
        82186, -- 1709.04305 Automated Cloud Provisioning on AWS using Deep Reinforcement Learning
        82260, -- 1703.06907 Domain Randomization for Transferring Deep Neural Networks from Simula
        82263, -- 1703.03864 Evolution Strategies as a Scalable Alternative to Reinforcement Learni
        82266, -- 1703.02702 Robust Adversarial Reinforcement Learning
        82382, -- 1606.01540 OpenAI Gym
        83290, -- 2605.12058 Hölder Policy Optimisation
        83523, -- 2605.15113 Learning from Language Feedback via Variational Policy Distillation
        83699, -- 2605.19282 Rethinking Muon Beyond Pretraining: Spectral Failures and High-Pass Re
        83876, -- 2605.28184 Joint Training of Multi-Token Prediction in Reinforcement Learning via
        84056, -- 2507.07685 Rationale-Enhanced Decoding for Multi-modal Chain-of-Thought
        84195, -- 2511.16955 Neighbor GRPO: Contrastive ODE Policy Optimization Aligns Flow Models
        84227, -- 2511.18919 Learning What to Trust: Bayesian Prior-Guided Optimization for Visual
        85193, -- 2603.28718 Stepwise Credit Assignment for GRPO on Flow-Matching Models
        85676, -- 2605.29398 GDSD: Reinforcement Learning as Guided Denoiser Self-Distillation for
        85727, -- 2411.04913 Structure Matters: Dynamic Policy Gradient
        85761, -- 2505.18763 GenPO: Generative Diffusion Models Meet On-Policy Reinforcement Learni
        85967, -- 2505.13636 Incentivizing Truthful Language Models via Peer Elicitation Games
        86021, -- 2505.15602 Deep learning for continuous-time stochastic control with jumps
        86067, -- 2506.07171 RULE: Reinforcement UnLEarning Achieves Forget-retain Pareto Optimalit
        86130, -- 2505.15544 A Temporal Difference Method for Stochastic Continuous Dynamics
        86324, -- 2509.23846 Adversarial Diffusion for Robust Reinforcement Learning
        86415, -- 2410.19933 Enhancing Safety in Reinforcement Learning with Human Feedback via Rec
        86592, -- 2502.13177 KL Penalty Control via Perturbation for Direct Preference Optimization
        86816, -- 2410.08868 On the Convergence of Single-Timescale Actor-Critic
        86831, -- 2411.04625 Sharp Analysis for KL-Regularized Contextual Bandits and RLHF
        86886, -- 2404.15617 DPO: A Differential and Pointwise Control Approach to Reinforcement Le
        86957, -- 2507.11060 Personalized Exercise Recommendation with Semantically-Grounded Knowle
        87004, -- 2509.18389 Towards Provable Emergence of In-Context Reinforcement Learning
        87028, -- 2509.06782 Physics-informed Value Learner for Offline Goal-Conditioned Reinforcem
        87040, -- 2508.18312 What Matters in Data for DPO?
        87182, -- 2508.12511 Trust Region Constrained Measure Transport in Path Space for Stochasti
        87280, -- 2502.14704 Not All Data are Good Labels: On the Self-supervised Labeling for Time
        87328, -- 2505.19281 A Snapshot of Influence: A Local Data Attribution Framework for Online
        88624, -- 2501.19116 A Theoretical Justification for Asymmetric Actor-Critic Algorithms
        88753, -- 2505.00663 Wasserstein Policy Optimization
        88754, -- 2405.17618 Symmetric Reinforcement Learning Loss for Robust Learning on Diverse T
        89025, -- 2502.11033 Convergence of Policy Mirror Descent Beyond Compatible Function Approx
        89083, -- 2506.00962 Reinforcement Learning with Random Time Horizons
        89163, -- 2502.00361 Efficient Online Reinforcement Learning for Diffusion Policy
        89424, -- 2505.01336 Enhancing Diversity In Parallel Agents: A Maximum State Entropy Explor
        89443, -- 2506.08441 Time-Aware World Model for Adaptive Prediction and Control
        89480, -- 2403.06323 A Reductions Approach to Risk-Sensitive Reinforcement Learning with Op
        89553, -- 2502.01819 Score as Action: Fine Tuning Diffusion Generative Models by Continuous
        89562, -- 2506.05615 When Maximum Entropy Misleads Policy Optimization
        89734, -- 2506.16753 Off-Policy Actor-Critic for Adversarial Observation Robustness: Virtua
        89753, -- 2506.00388 CLARIFY: Contrastive Preference Reinforcement Learning for Untangling
        89860, -- 2505.06744 LineFlow: A Framework to Learn Active Control of Production Lines
        89979, -- 2505.06273 Policy-labeled Preference Learning: Is Preference Enough for RLHF?
        89991, -- 2502.07529 Training Deep Learning Models with Norm-Constrained LMOs
        91070, -- 2406.14662 Advantage Alignment Algorithms
        91201, -- 2411.05228 Solving hidden monotone variational inequalities with surrogate losses
        91205, -- 2412.08794 Latent Safety-Constrained Policy Approach for Safe Offline Reinforceme
        91233, -- 2503.13162 Efficient Imitation under Misspecification
        91297, -- 2411.07007 Non-Adversarial Inverse Reinforcement Learning via Successor Feature M
        91350, -- 2503.08241 HASARD: A Benchmark for Vision-Based Safe Reinforcement Learning in Em
        91367, -- 2503.05306 Adversarial Policy Optimization for Offline Preference-based Reinforce
        91414, -- 2410.05782 Reinforcement Learning from Imperfect Corrective Actions and Proxy Rew
        91464, -- 2403.00282 Conflict-Averse Gradient Aggregation for Constrained Multi-Objective R
        91518, -- 2412.07775 Efficient Diversity-Preserving Diffusion Alignment via Gradient-Inform
        91584, -- 2402.05187 Learning mirror maps in policy mirror descent
        91629, -- 2403.04453 Efficient Off-Policy Learning for High-Dimensional Action Spaces
        91682, -- 2412.03258 Learning on One Mode: Addressing Multi-modality in Offline Reinforceme
        92048, -- 2410.05106 Nonasymptotic Analysis of Stochastic Gradient Descent with the Richard
        92074, -- 2405.12001 Scrutinize What We Ignore: Reining In Task Representation Shift Of Con
        92123, -- 2410.04553 Bisimulation Metric for Model Predictive Control
        92138, -- 2502.19009 Distilling Reinforcement Learning Algorithms for In-Context Model-Base
        92313, -- 2302.02182 Online Reinforcement Learning in Non-Stationary Context-Driven Environ
        92528, -- 2605.27079 Trust Region Q Adjoint Matching
        92629, -- 2602.01601 Adaptive Rollout Allocation for Online Reinforcement Learning with Ver
        92664, -- 2511.03032 Leveraging Discrete Function Decomposability for Scientific Design
        92836, -- 2604.03489 Improving Feasibility via Fast Autoencoder-Based Projections
        93010, -- 2510.18460 Learning Boltzmann Generators via Constrained Mass Transport
        93042, -- 2510.06649 Local Reinforcement Learning with Action-Conditioned Root Mean Squared
        93057, -- 2506.10133 Statistical Guarantees for Offline Domain Randomization
        93149, -- 2512.12046 Goal Reaching with Eikonal-Constrained Hierarchical Quasimetric Reinfo
        93188, -- 2601.00898 Dichotomous Diffusion Policy Optimization
        93209, -- 2509.24716 Discrete Variational Autoencoding via Policy Search
        93213, -- 2510.14898 Convergence of an actor-critic gradient flow for entropy regularised M
        93310, -- 2603.01741 Rethinking Policy Diversity in Ensemble Policy Gradient in Large-Scale
        93498, -- 2506.08902 Intention-Conditioned Flow Occupancy Models
        93539, -- 2505.15418 Guided Policy Optimization under Partial Observability
        93550, -- 2509.24116 Dual-Scale World Memory for LLM Agents towards Hard-Exploration Proble
        93798, -- 2603.11682 Entropy-preserving reinforcement learning
        93854, -- 2603.00903 Principled Fast and Meta Knowledge Learners for Continual Reinforcemen
        93971, -- 2502.19544 Efficient Reinforcement Learning by Guiding World Models with Non-Cura
        93988, -- 2512.01228 On the Tension Between Optimality and Adversarial Robustness in Policy
        94021, -- 2508.10801 Object Fidelity Diffusion for Remote Sensing Image Generation
        94039, -- 2506.05154 Resisting Contextual Interference in RAG via Parametric-Knowledge Rein
        94149, -- 2502.08938 Reevaluating Policy Gradient Methods for Imperfect-Information Games
        94158, -- 2510.12312 Deep SPI: Safe Policy Improvement via World Models
        94441, -- 2507.08838 wd1: Weighted Policy Optimization for Reasoning in Diffusion Language
        94476, -- 2509.23183 ZeroSiam: An Efficient Asymmetry for Test-Time Entropy Optimization wi
        94582, -- 2601.19707 Scalable Exploration for High-Dimensional Continuous Control via Value
        94729, -- 2507.18059 Multi-Agent Guided Policy Optimization
        94823, -- 2507.11019 Relative Entropy Pathwise Policy Optimization
        94841, -- 2507.21533 Model Predictive Adversarial Imitation Learning for Planning from Obse
        94957, -- 2511.08234 Beyond Distributions: Geometric Action Control for Continuous Reinforc
        94975, -- 2602.11523 Unifying Stable Optimization and Reference Regularization in RLHF
        95024, -- 2503.03660 Chunking the Critic: A Transformer-based Soft Actor-Critic with N-Step
        95040, -- 2602.11902 Mitigating Mismatch within Reference-based Preference Optimization
        95392, -- 2503.07848 Safe Explicable Policy Search
        95434, -- 2603.04073 Swimming under Constraints: A Safe Reinforcement Learning Framework fo
        95733, -- 2509.20841 ImaginationPolicy: Towards Generalizable, Precise and Reliable End-To-
        96210, -- 2510.09976 Reinforcement Fine-Tuning of Flow-Matching Policies for Vision-Languag
        96232, -- 2510.14338 Risk-Aware Reinforcement Learning with Bandit-Based Adaptation for Qua
        96853, -- 2312.09436 Temporal Transfer Learning for Traffic Optimization with Coarse-Graine
        97042, -- 2507.23339 Learning to Drift with Individual Wheel Drive: Maneuvering Autonomous
        97316, -- 2504.13582 Hysteresis-Aware Neural Network Modeling and Whole-Body Reinforcement
        97969, -- 2606.05152 Reinforcement Learning from Rich Feedback with Distributional DAgger
        98133, -- 2606.11025 Flow-DPPO: Divergence Proximal Policy Optimization for Flow Matching M
        98135, -- 2606.09821 Rethinking the Divergence Regularization in LLM RL
        98147, -- 2605.22305 Chebyshev Policies and the Mountain Car Problem: Reinforcement Learnin
        98225, -- 2605.03065 OGPO: Sample Efficient Full-Finetuning of Generative Control Policies
        98290, -- 2606.10968 Beyond Uniform Token-Level Trust Region in LLM Reinforcement Learning
        98367, -- 1909.12271 RLBench: The Robot Learning Benchmark & Learning Environment
        98436, -- 2606.16771 GD^2PO: Mitigating Multi-Reward Conflicts via Group-Dynamic reward-Dec
        98467, -- 2606.16154 A Gradient Perspective on RLVR Stability and Winner Advantage Policy O
        98798, -- 2606.23991 Critique of Agent Model
        98894, -- 2606.22600 On the Position Bias of On-Policy Distillation
        99078, -- 2607.02291 Optimizing Visual Generative Models via Distribution-wise Rewards
        99140, -- 2601.21778 Error Amplification Limits ANN-to-SNN Conversion in Continuous Control
        99275, -- 2605.18591 Randomized Advantage Transformation (RAT): Computing Natural Policy Gr
        99559, -- 2602.04663 Rethinking the Design Space of Reinforcement Learning for Diffusion Mo
        99611, -- 2509.22963 Reinforcement Learning with Discrete Diffusion Policies for Combinator
        99696, -- 2601.23075 RN-D: Discretized Categorical Actors for On-Policy Reinforcement Learn
        99896, -- 2508.06214 Reparameterization Proximal Policy Optimization
        99903, -- 2512.20576 Performative Policy Gradient: Optimality in Performative Reinforcement
        99933, -- 2605.28030 SPARD: Defending Harmful Fine-Tuning Attack via Safety Projection with
        99984, -- 2605.22156 One-Way Policy Optimization for Self-Evolving LLMs
        100001, -- 2605.16030 Mind Dreamer: Untethering Imagination via Active Causal Intervention o
        100134, -- 2605.22703 Clipping Bottleneck: Stabilizing RLVR via Stochastic Recovery of Near-
        100159, -- 2605.26784 Ratio-Variance Regularized Policy Optimization
        100175, -- 2605.00408 Beyond Heuristics: Learnable Density Control for 3D Gaussian Splatting
        100228, -- 2509.24050 Bridging On-Device and Cloud LLMs for Collaborative Reasoning: A Unifi
        100301, -- 2602.10217 Temper-Then-Tilt: Principled Unlearning for Generative Models through
        100336, -- 2603.08398 Revealing Behavioral Plasticity in Large Language Models: A Token-Cond
        100339, -- 2603.03955 GIPO: Gaussian Importance Sampling Policy Optimization
        100467, -- 2605.11020 Trust Region Inverse Reinforcement Learning: Explicit Dual Ascent usin
        100524, -- 2606.14415 CSPO: Constraint-Sensitive Policy Optimization for Safe Reinforcement
        100559, -- 2604.19033 Intentional Updates for Streaming Reinforcement Learning
        100573, -- 2602.01603 Inference-Aware Meta-Alignment of LLMs via Non-Linear GRPO
        100578, -- 2605.15207 TeamTR: Trust-Region Fine-Tuning for Multi-Agent LLM Coordination
        100581, -- 2603.02196 Conformal Policy Control
        100609, -- 2604.14698 Mean Flow Policy Optimization
        100783, -- 2605.31228 EchoRL: Reinforcement Learning via Rollout Echoing
        100900, -- 2602.01460 Non-Uniform Noise-to-Signal Ratio in the REINFORCE Policy-Gradient Est
        100913, -- 2506.06178 Reusing Trajectories in Policy Gradients Enables Fast Convergence
        100990, -- 2606.11982 PAWS: Preference Learning with Advantage-Weighted Segments
        101029, -- 2503.06639 Reinforcement Learning with Verifiable Rewards: GRPO's Loss, Dynamics,
        101111, -- 2605.13025 Offline Two-Player Zero-Sum Markov Games with KL Regularization
        101218, -- 2502.03854 Mirror Descent Actor Critic via Bounded Advantage Learning
        101399, -- 2602.21565 Routing by Reaching: Composition of Pre-trained GFlowNets for Multi-Ob
        101403, -- 2601.18175 Success-Conditioning as Policy Improvement: The Optimization Problem S
        101464, -- 2511.11592 Mind Your Entropy: From Maximum Entropy to Trajectory Entropy-Constrai
        101525, -- 2605.26684 Beyond Trajectory-Level Attribution: Graph-Based Credit Assignment for
        101651, -- 2601.22823 Offline Reinforcement Learning of High-Quality Behaviors Under Robust
        101658, -- 2510.01824 Black-Box Combinatorial Optimization with Order-Invariant Reinforcemen
        101659, -- 2606.07950 The Easy, the Hard, and the Learnable: Confidence and Difficulty-Adapt
        101726, -- 2510.04280 A KL-regularization framework for learning to plan with adaptive prior
        101923, -- 2605.24357 Refined Analysis of Entropy-Regularized Actor-Critic
        101924, -- 2602.09533 Autoregressive Direct Preference Optimization
        101947, -- 2602.02250 Well-Posed KL-Regularized Control via Wasserstein and Kalman–Wasserste
        101954, -- 2602.00781 Fast Non-Episodic Finite-Horizon RL with K-Step Lookahead Thresholding
        102159, -- 2601.20076 Randomized Feasibility Methods for Constrained Optimization with Adapt
        102295, -- 2602.10894 Revisiting Regularized Policy Optimization for Stable and Efficient Re
        102338, -- 2601.22211 Latent Spherical Flow Policy for Reinforcement Learning with Combinato
        102498, -- 2606.14351 ForceForget: Reinforcement Concept Removal for Enhancing Safety in Tex
        102505, -- 2603.00530 Bridge Matching Sampler: Scalable Sampling via Generalized Fixed-Point
        102547, -- 2606.29526 The Mirage of Optimizing Training Policies: Monotonic Inference Polici
        102716, -- 2607.06987 UP: Unbounded Positive Asymmetric Optimization for Breaking the Explor
        103492, -- 2507.03069 ARF-RLHF: Adaptive Reward-Following for RLHF through Emotion-Driven Se
        103546, -- 2507.02841 StepHint: Multi-level Stepwise Hints Enhance Reinforcement Learning to
        103628, -- 2603.14389 From \log \pi to \pi: Taming Divergence in Soft Clipping via Bilateral
        103822, -- 2607.04751 Trust Region Policy Distillation
        103881, -- 2009.04416 Phasic Policy Gradient
        103893, -- 2006.12862 Automatic Data Augmentation for Generalization in Deep Reinforcement L
        103894, -- 2102.10330 Decoupling Value and Policy for Generalization in Reinforcement Learni
        104446, -- 2607.18722 Stale but Stable: Staleness-Adaptive Trust Regions for Stabilizing Asy
        104486, -- 2607.10169 Beyond Euclidean Clipping: Overcoming Exploration Collapse in LLM RL v
        104509, -- 2607.10848 Predictive Divergence Masks for LLM RL
        105618, -- 2503.15784 RL4Med-DDPO: Reinforcement Learning for Controlled Guidance Towards Di
        106179, -- 2607.15200 Mask-Aware Policy Gradients for Diffusion Language Models
        106510, -- 2511.11828 Conformal Constrained Policy Optimization for Cost-Effective LLM Agent
        106654, -- 2512.18623 LLM-CAS: Dynamic Neuron Perturbation for Real-Time Hallucination Corre
        106746, -- 2602.07202 Risk-Sensitive Exponential Actor Critic
        107275, -- 2511.16629 Stabilizing Policy Gradient Methods via Reward Profiling
        107384, -- 2508.02644 D²PPO: Diffusion Policy Policy Optimization with Dispersive Loss
        107477, -- 2508.01883 Proactive Constrained Policy Optimization with Preemptive Penalty
        109676, -- 2608.23311 Beyond the Stability-Exploration Dilemma: Environmental Regularization
        109719, -- 2608.23566 Best Practice Critic Optimization
        109967, -- 2505.14585 Context Reasoner: Incentivizing Reasoning Capability for Contextualize
        111019, -- 2511.12596 Group-Aware Reinforcement Learning for Output Diversity in Large Langu
        113811, -- 2608.29252 Dynamic Important Example Mining for Reinforcement Finetuning
        113967, -- 2609.00444 Group Adaptive Clipping Policy Optimization
        119604, -- 2608.26147 CARE: Causally-Aligned Reasoning Exploration for Medical Large Languag
        119821, -- 2309.07907 Physically Plausible Full-Body Hand-Object Interaction Synthesis
        122215, -- 2609.29050 SLCA-GRPO: Resolving Cross-Segment Credit Misattribution in Tool-Calli
        122295, -- 2609.32722 Scaling Properties of Same-Family On-Policy Distillation
        122327, -- 2609.33378 Recursive Harness Distillation across Agents for Robot Manipulation
        122585, -- 2610.00360 DexPolicy: Scheduled Exploration for Trajectory-Guided Dexterous Manip
        122770, -- 2610.01789 iADD: Improving Alignment and Diversity in Diffusion Policy Optimizati
        122787, -- 2610.06647 LoGRA: Scaling LLM Reinforcement Learning with Low-Rank Gradient Sketc
        122970, -- 2609.35433 ReSPO: Reshaped Sequence Policy Optimization for Gradient Starvation i
        123557, -- 2610.15368 ANTE: Anticipate, Then Execute -- Learning Internal World Models for C
        124136, -- 2602.08813 Robust Policy Optimization to Prevent Catastrophic Forgetting
        124137, -- 2605.14967 InfoSFT: Learn More and Forget Less with Information-Aware Token Weigh
        124156, -- 2602.00927 Beyond What Seems Necessary: Hidden Gains from Scaling Training-Time R
        124170, -- 2610.14041 A Geometric Perspective on Reward Function Updates in Inverse Reinforc
        124183, -- 2603.10199 Actor-Accelerated Policy Dual Averaging for Reinforcement Learning in
        124186, -- 2607.10630 World Models as Adversaries: Multi-Agent Self-Play Fine-Tuning for Rob
        124978, -- 2603.09542 NS-VLA: Towards Neuro-Symbolic Vision-Language-Action Models
        125175, -- 2605.05802 Selective Rollout: Mid-Trajectory Termination for Multi-Sample Agent R
        125342, -- 2603.05066 Reward-Conditioned Reinforcement Learning
        125432, -- 2610.02190 Trust the Direction, Search the Step: Zero-and-First-Order Methods for
        126028, -- 2602.21515 Training Generalizable Collaborative Agents via Strategic Risk Aversio
        126055, -- 2602.10838 Mirror descent actor-critic methods for entropy regularised MDPs in ge
        126151, -- 2604.28020 Cost-Aware Learning
        126187, -- 2605.17862 $\boldsymbol{f}$-OPD: Stabilizing Long-Horizon On-Policy Distillation
        126486, -- 2610.03642 On the Convergence of Success Conditioning for Policy Optimization
        126589, -- 2605.20865 Multi-Step Likelihood-Ratio Correction for Reinforcement Learning with
        126947, -- 2605.30749 FLAG: Flow Policy MaxEnt-RL by Latent Augmented Guidance
        126971, -- 2410.01212 Absolute State-wise Constrained Policy Optimization: High-Probability
        127175, -- 2610.04117 Sharp Convergence and Sample Complexity of Policy Mirror Descent for A
        127300, -- 2603.00963 Stabilizing Policy Optimization via Logits Convexity
        127411, -- 2605.10671 Natural Policy Gradient as Doubly Smoothed Policy Iteration: A Bellman
        127601, -- 2609.31066 Modeling quantum neural network gradient with reinforcement learning
        127881, -- 2604.26256 DORA: A Scalable Asynchronous Reinforcement Learning System for Langua
        128394, -- 2512.22545 Self-Rewarded Multimodal Coherent Reasoning Across Diverse Visual Doma
        128535, -- 2605.13554 Self-Supervised On-Policy Reinforcement Learning via Contrastive Proxi
        128591, -- 2605.25507 Credit Assignment with Resets in Language Model Reasoning
        128718, -- 2605.08315 Reflective Prompted Policy Optimization: Trajectory-Grounded Revision
        128837, -- 2607.02292 One More Time: Revisiting Neural Quantum States from a Reinforcement L
        129045, -- 2602.18003 Policy Gradient Algorithms in Average-Reward Multichain MDPs
        129357, -- 2503.06917 Sample-Efficient Optimization over Generative Priors via Coarse Learna
        129577, -- 2606.04503 Smart Picks in the Dark: Towards Efficient RLVR for Reasoning via Trac
        129600, -- 2602.06462 Diffusion-State Policy Optimization for Masked Diffusion Language Mode
        129656, -- 2606.22630 Scalable Maximum Entropy Reinforcement Learning for Diffusion Policies
        129741, -- 2601.21572 Signal-Adaptive Trust Regions for Gradient-Free Optimization of Recurr
        130099, -- 2604.17415 Reward Score Matching: Unifying Reward-based Fine-tuning for Flow and
        130181, -- 2610.14939 VC-OPD: Visual Counterfactual On-Policy Distillation for Grounded Visi
        130519, -- 2605.08427 The Attacker in the Mirror: Breaking Self-Consistency in Safety via An
        130773, -- 2610.03361 Follow the Winners: Conservative Policy Improvement with the Cross-Ent
        131081, -- 2605.18843 TEMPO: Temporal Enforcement via Mode-Separated Policy Optimization for
        131129, -- 2605.08686 Iterative Critique-and-Routing Controller for Multi-Agent Systems with
        131138, -- 2602.20457 Oracle-Robust Online Alignment for Large Language Models
        131255, -- 2605.09214 Fast Rates for Offline Contextual Bandits with Forward-KL Regularizati
        131376, -- 2610.19687 Function-Space Temporal Self-Distillation for Policy Optimization
        131540, -- 2610.35013 Multiscale Policy Optimization for Long-Horizon LLM Agents
        131710, -- 2610.42149 Latent Reasoning in Continuous Space for Unified Multimodal Models
        131740  -- 2610.40740 Certified Behavioral Retention for Continual Adaptation with Held-Out
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the TRPO paper without naming, using or comparing against TRPO'
FROM trpo_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING trpo_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING trpo_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- ddpg: 30 links, 456 exclusions. Semantic Scholar returned 9999 citers of the source, 470 local.
CREATE TEMP TABLE ddpg_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ddpg'
  AND p.id IN (
        239, -- 1509.02971 Continuous control with deep reinforcement learning
        741, -- 1706.01905 Parameter Space Noise for Exploration
        892, -- 1709.08430 Towards continuous control of flippers for a multi-terrain robot using
        2708, -- 1910.09434 Towards a Reinforcement Learning Environment Toolbox for Intelligent E
        7045, -- 2110.12628 Recurrent Off-policy Baselines for Memory-based Continuous Control
        8346, -- 2203.10494 MicroRacer: a didactic environment for Deep Reinforcement Learning
        15835, -- 2305.12239 Off-Policy Average Reward Actor-Critic with Deterministic Policy Searc
        16219, -- 2305.15193 Adaptive Policy Learning to Additional Tasks
        21653, -- 2310.05858 Distributional Soft Actor-Critic with Three Refinements
        24550, -- 2312.05674 Position control of an acoustic cavitation bubble by reinforcement lea
        30572, -- 2404.12754 Adaptive Regularization of Representation Rank as an Implicit Constrai
        34367, -- 2407.06642 Powerful and Flexible: Personalized Text-to-Image Generation via Reinf
        66719, -- 2510.08270 Evaluation of a Robust Control System in Real-World Cable-Driven Paral
        69308, -- 2508.16474 Reinforcement Learning-based Control via Y-wise Affine Neural Networks
        73089, -- 2505.09012 Deep Reinforcement Learning for Power Grid Multi-Stage Cascading Failu
        75093, -- 2501.14488 Breaking the Pre-Planning Barrier: Adaptive Real-Time Coordination of
        76020, -- 2410.13490 Novelty-based Sample Reuse for Continuous Robotics Control
        80400, -- 2111.05969 PowerGridworld: A Framework for Multi-Agent Reinforcement Learning in
        80974, -- 2012.05105 Com-DDPG: A Multiagent Reinforcement Learning-based Offloading Strateg
        81009, -- 2011.09607 FinRL: A Deep Reinforcement Learning Library for Automated Stock Tradi
        81832, -- 1901.04772 Transfer Learning for Prosthetics Using Imitation Learning
        88753, -- 2505.00663 Wasserstein Policy Optimization
        92930, -- 2506.16608 Distributions as Actions: A Unified Framework for Diverse Action Space
        95982, -- external Second Order Sliding Mode Control of Flying Wing Aircraft Based on Fee
        96152, -- 2602.23972 Learning Robust Control Policies for Inverted Pose on Miniature Blimp
        96241, -- external Learning to Throw Objects Safely in Multi-Obstacle Environments
        97226, -- external Behavior Cloning-Enhanced Deep Reinforcement Learning for Robot Naviga
        97343, -- 2502.11375 Robot Deformable Object Manipulation Via NMPC-Generated Demonstrations
        107670, -- 2505.12340 DIMM: Decoupled Multi-hierarchy Kalman Filter via Reinforcement Learni
        121861  -- external Beyond Rule-Based Agents: Active Markov Games for Realistic Multi-Agen
  );

DELETE FROM paper_method_exclusions x
USING ddpg_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ddpg_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ddpg_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE ddpg_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ddpg'
  AND p.id IN (
        5220, -- 2103.09815 TeachMyAgent: a Benchmark for Automatic Curriculum Learning in Deep RL
        5434, -- 2104.06303 Learning and Planning in Complex Action Spaces
        5465, -- 2104.07495 Curiosity-Driven Exploration via Latent Bayesian Surprise
        5528, -- 2104.09122 Probabilistic Mixture-of-Experts for Efficient Deep Reinforcement Lear
        5738, -- 2105.07983 Unknown-box Approximation to Improve Optical Character Recognition Per
        5793, -- 2105.13231 AndroidEnv: A Reinforcement Learning Platform for Android
        5937, -- 2106.05110 Self-Paced Context Evaluation for Contextual Reinforcement Learning
        5976, -- 2106.06842 Recomposing the Reinforcement Learning Building Blocks with Hypernetwo
        6005, -- 2106.08272 Deep Reinforcement Learning for Conservation Decisions
        6076, -- 2106.11420 Policy Smoothing for Provably Robust Reinforcement Learning
        6120, -- 2106.13687 Multi-Goal Reinforcement Learning environments for simulated Franka Em
        6166, -- 2107.00644 Stabilizing Deep Q-Learning with ConvNets and Vision Transformers unde
        6203, -- 2107.03792 Automated Gain Control Through Deep Reinforcement Learning for Downstr
        6281, -- 2107.09645 Mastering Visual Continuous Control: Improved Data-Augmented Reinforce
        6354, -- 2108.01295 MBDP: A Model-based Approach to Achieve both Robustness and Sample Eff
        6361, -- 2108.01832 Offline Decentralized Multi-Agent Reinforcement Learning
        6379, -- 2108.03298 What Matters in Learning from Offline Human Demonstrations for Robot M
        6511, -- 2108.13264 Deep Reinforcement Learning at the Edge of the Statistical Precipice
        6634, -- 2109.06728 Learning Density Distribution of Reachable States for Autonomous Syste
        6726, -- 2109.12425 L$^{2}$NAS: Learning to Optimize Neural Architectures via Continuous-A
        6781, -- 2110.01307 Collective eXplainable AI: Explaining Cooperative Strategies and Agent
        6795, -- 2110.02034 Dropout Q-Functions for Doubly Efficient Reinforcement Learning
        6808, -- 2110.02639 On The Transferability of Deep-Q Networks
        6848, -- 2110.04186 Medical Dead-ends and Learning to Identify High-risk States and Treatm
        6864, -- 2110.04830 MARVEL: Raster Manga Vectorization via Primitive-wise Deep Reinforceme
        7107, -- 2111.00210 Mastering Atari Games with Limited Data
        7108, -- 2111.00213 Adjacency constraint for efficient hierarchical reinforcement learning
        7155, -- 2111.02552 Is Bang-Bang Control All You Need? Solving Continuous Control with Ber
        7167, -- 2111.03788 d3rlpy: An Offline Deep Reinforcement Learning Library
        7233, -- 2111.08819 CleanRL: High-quality Single-file Implementations of Deep Reinforcemen
        7234, -- 2111.08857 SEIHAI: A Sample-efficient Hierarchical AI for the MineRL Competition
        7373, -- 2112.00874 Neural Stochastic Dual Dynamic Programming
        7428, -- 2112.03636 Godot Reinforcement Learning Agents
        7620, -- 2112.15034 Self Reward Design with Fine-grained Interpretability
        7677, -- 2201.03916 Automated Reinforcement Learning (AutoRL): A Survey and Open Problems
        7688, -- 2201.05000 Automated Reinforcement Learning: An Overview
        7692, -- 2201.05242 Neural Circuit Architectural Priors for Embodied Control
        7731, -- 2201.07779 Look Closer: Bridging Egocentric and Third-Person Views with Transform
        7753, -- 2201.09522 Accelerated Intravascular Ultrasound Imaging using Deep Reinforcement
        7836, -- 2202.00665 Tutorial on amortized optimization
        7862, -- 2202.01771 Pre-Trained Language Models for Interactive Decision-Making
        7915, -- 2202.04500 Contextualize Me -- The Case for Context in Reinforcement Learning
        8164, -- 2203.03580 The Unsurprising Effectiveness of Pre-Trained Vision Models for Contro
        8194, -- 2203.04955 Temporal Difference Learning for Model Predictive Control
        8402, -- 2203.12677 Vision-Based Manipulators Need to Also See from Their Hands
        8609, -- 2204.03421 Self-supervised learning for robust voice cloning
        8828, -- 2204.11142 Graph Neural Network based Agent in Google Research Football
        9083, -- 2205.10330 A Review of Safe Reinforcement Learning: Methods, Theory and Applicati
        9371, -- 2206.02380 Adaptive Rollout Length for Model-Based RL Using Model-Free Deep RL
        9433, -- 2206.04779 Challenges and Opportunities in Offline Reinforcement Learning from Vi
        9441, -- 2206.05266 Does Self-supervised Learning Really Improve Reinforcement Learning fr
        9534, -- 2206.09328 A Survey on Model-based Reinforcement Learning
        9556, -- 2206.10442 Robust Task Representations for Offline Meta-Reinforcement Learning vi
        9653, -- 2206.15469 Watch and Match: Supercharging Imitation with Regularized Optimal Tran
        9687, -- 2207.01780 CodeRL: Mastering Code Generation through Pretrained Models and Deep R
        9892, -- 2207.12141 Live in the Moment: Learning Dynamics Model Adapted to Evolving Policy
        10186, -- 2208.14928 Cell-Free Latent Go-Explore
        10294, -- 2209.07288 Optimistic Curiosity Exploration and Conservative Exploitation with Li
        10402, -- 2209.12016 Mastering the Unsupervised Reinforcement Learning Benchmark from Pixel
        10452, -- 2209.14610 Dynamic Prompt Learning via Policy Gradient for Semi-structured Mathem
        10719, -- 2210.05639 Discovered Policy Optimisation
        10762, -- 2210.06479 Real World Offline Reinforcement Learning with Realistic Data Source
        10769, -- 2210.06702 A Mixture of Surprises for Unsupervised Reinforcement Learning
        10798, -- 2210.07241 Visual Reinforcement Learning with Self-Supervised 3D Representations
        11018, -- 2210.13153 Reachability-Aware Laplacian Representation in Reinforcement Learning
        11200, -- 2211.01724 Learning Control by Iterative Inversion
        11213, -- 2211.02127 Scalable Multi-Agent Reinforcement Learning through Intelligent Inform
        11408, -- 2211.09702 Deep Reinforcement Learning Based Joint Downlink Beamforming and RIS C
        11583, -- 2211.13350 Choreographer: Learning and Adapting Skills in Imagination
        11662, -- 2211.15457 Hypernetworks for Zero-shot Transfer in Reinforcement Learning
        11668, -- 2211.15657 Is Conditional Generative Modeling all you need for Decision-Making?
        11683, -- 2211.15956 Offline Reinforcement Learning with Closed-Form Policy Improvement Ope
        11918, -- 2212.05698 MoDem: Accelerating Visual Model-Based Reinforcement Learning with Dem
        11920, -- 2212.05749 On Pre-Training for Visuo-Motor Control: Revisiting a Learning-from-Sc
        11937, -- 2212.06225 Reinforced Approximate Exploratory Data Analysis
        12192, -- 2212.11681 Variational Quantum Soft Actor-Critic for Robotic Arm Control
        12204, -- 2212.12207 Investigation of reinforcement learning for shape optimization of prof
        12273, -- 2301.00452 Human-in-the-loop Embodied Intelligence with Interactive Simulation En
        12363, -- 2301.04104 Mastering Diverse Domains through World Models
        12574, -- 2301.11518 Online Learning in Stackelberg Games with an Omniscient Follower
        12672, -- 2301.13087 Improved Regret for Efficient Online Reinforcement Learning with Linea
        12708, -- 2301.13616 Anti-Exploration by Random Network Distillation
        12735, -- 2302.00141 Revisiting Bellman Errors for Offline Model Selection
        12784, -- 2302.01275 ReLOAD: Reinforcement Learning with Optimistic Ascent-Descent for Last
        12816, -- 2302.01680 Two-Stage Constrained Actor-Critic for Short Video Recommendation
        12817, -- 2302.01687 Better Training of GFlowNets with Local Credit and Incomplete Trajecto
        12882, -- 2302.02948 Efficient Online Reinforcement Learning with Offline Data
        12883, -- 2302.02984 Robust Subtask Learning for Compositional Generalization
        13302, -- 2302.12537 Why Target Networks Stabilise Temporal Difference Methods
        13313, -- 2302.12902 The Dormant Neuron Phenomenon in Deep Reinforcement Learning
        13412, -- 2303.00566 Structured Pruning for Deep Convolutional Neural Networks: A survey
        13449, -- 2303.01469 Consistency Models
        13540, -- 2303.03832 MAP-Elites with Descriptor-Conditioned Gradients and Archive Distillat
        13551, -- 2303.04129 Foundation Models for Decision Making: Problems, Methods, and Opportun
        13879, -- 2303.10327 Hybrid Systems Neural Control with Region-of-Attraction Planner
        14019, -- 2303.12670 Correlational Image Modeling for Self-Supervised Visual Pre-Training
        14409, -- 2304.01203 Optimal Goal-Reaching Reinforcement Learning via Quasimetric Learning
        14576, -- 2304.04591 For Pre-Trained Vision Models in Motor Control, Not All Policy Learnin
        14944, -- 2304.12824 Contrastive Energy Prediction for Exact Energy-Guided Diffusion Sampli
        15310, -- 2305.04361 Truncating Trajectories in Monte Carlo Reinforcement Learning
        15321, -- 2305.04477 Behavior Contrastive Learning for Unsupervised Skill Discovery
        15338, -- 2305.04819 Local Optimization Achieves Global Optimality in Multi-Agent Reinforce
        15517, -- 2305.07911 Delay-Adapted Policy Optimization and Improved Regret for Adversarial
        15750, -- 2305.11340 Bayesian Reparameterization of Reward-Conditioned Reinforcement Learni
        15998, -- 2305.13795 Proximal Policy Gradient Arborescence for Quality Diversity Reinforcem
        16155, -- 2305.14859 Utility-Probability Duality of Neural Networks
        16218, -- 2305.15188 Optimal Control of Nonlinear Systems with Unknown Dynamics
        16316, -- 2305.16291 Voyager: An Open-Ended Embodied Agent with Large Language Models
        16449, -- 2305.17625 Cross-Domain Policy Adaptation via Value-Guided Data Filtering
        16586, -- 2305.18951 Subequivariant Graph Reinforcement Learning in 3D Environments
        16670, -- 2305.19922 Representation-Driven Reinforcement Learning
        16690, -- 2305.20081 Efficient Diffusion Policies for Offline Reinforcement Learning
        16754, -- 2306.00577 TorchRL: A data-driven decision-making library for PyTorch
        16855, -- 2306.01476 Hierarchical Reinforcement Learning for Modeling User Novelty-Seeking
        17000, -- 2306.03186 Flipping Coins to Estimate Pseudocounts for Exploration in Reinforceme
        17039, -- 2306.03530 RLtools: A Fast, Portable Deep Reinforcement Learning Library for Cont
        17158, -- 2306.05167 Decision S4: Efficient Sequence-Based RL via State Spaces Layers
        17324, -- 2306.07307 Online Prototype Alignment for Few-shot Policy Transfer
        17450, -- 2306.08888 ArchGym: An Open-Source Gymnasium for Machine Learning Assisted Archit
        17508, -- 2306.09466 Simplified Temporal Consistency Reinforcement Learning
        17589, -- 2306.10882 AdaStop: adaptive statistical testing for sound comparisons of Deep RL
        17591, -- 2306.10950 Benchmarking Robustness of Deep Reinforcement Learning approaches to O
        17647, -- 2306.11941 Efficient Dynamics Modeling in Interactive Environments with Koopman T
        17728, -- 2306.13812 Maintaining Plasticity in Deep Continual Learning
        17875, -- 2306.16857 ArrayBot: Reinforcement Learning for Generalizable Distributed Manipul
        18073, -- 2307.03353 A Survey of Deep Learning in Sports Applications: Perception, Comprehe
        18188, -- 2307.05979 Transformers in Reinforcement Learning: A Survey
        18194, -- 2307.06175 Learning Decentralized Partially Observable Mean Field Control for Art
        18290, -- 2307.08168 Enabling Efficient, Reliable Real-World Reinforcement Learning with Ap
        18472, -- 2307.10936 PASTA: Pretrained Action-State Transformer Agents
        18633, -- 2307.13813 How to Scale Your EMA
        18772, -- 2307.16348 Rating-based Reinforcement Learning
        18946, -- 2308.02585 PARL: A Unified Framework for Policy Alignment in Reinforcement Learni
        19624, -- 2308.11432 A Survey on Large Language Model based Autonomous Agents
        19854, -- 2308.14328 Reinforcement Learning for Generative AI: A Survey
        20179, -- 2309.03504 Stroke-based Neural Painting and Stylization with Dynamically Predicte
        20341, -- 2309.06553 Query-Dependent Prompt Evaluation and Optimization with Offline Invers
        20370, -- 2309.07038 Efficient Reinforcement Learning for Jumping Monopods
        20413, -- 2309.07675 Goal Space Abstraction in Hierarchical Reinforcement Learning via Set-
        20950, -- 2309.15178 Zero-Shot Reinforcement Learning from Low Quality Data
        20981, -- 2309.15762 Rapid Network Adaptation: Learning to Adapt Neural Networks Using Test
        21045, -- 2309.16663 HyperPPO: A scalable method for finding small policies for robotic con
        21103, -- 2309.17400 Directly Fine-Tuning Diffusion Models on Differentiable Rewards
        21284, -- 2310.01706 On Representation Complexity of Model-based and Model-free Reinforceme
        21439, -- 2310.03342 LESSON: Learning to Integrate Exploration Strategies for Reinforcement
        21678, -- 2310.06081 Ito Diffusion Approximation of Universal Ito Chains for Sampling, Opti
        21819, -- 2310.07747 Accountability in Offline Reinforcement Learning: Explaining Decisions
        21950, -- 2310.09091 Insightful analysis of historical sources at scales beyond human capab
        22008, -- 2310.09971 AMAGO: Scalable In-Context Reinforcement Learning for Adaptive Agents
        22568, -- 2310.16828 TD-MPC2: Scalable, Robust World Models for Continuous Control
        22639, -- 2310.17786 Understanding when Dynamics-Invariant Data Augmentations Benefit Model
        22661, -- 2310.18144 Improving Intrinsic Exploration by Creating Stationary Objectives
        22720, -- 2310.18966 Spacecraft Autonomous Decision-Planning for Collision Avoidance: a Rei
        22739, -- 2310.19308 Free from Bellman Completeness: Trajectory Stitching via Model-based R
        22763, -- 2310.19668 DrM: Mastering Visual Reinforcement Learning through Dormant Ratio Min
        22776, -- 2310.19805 Improving Offline-to-Online Reinforcement Learning with Q Conditioned
        23298, -- 2311.08290 On-Policy Policy Gradient Reinforcement Learning Without On-Policy Sam
        23431, -- 2311.09692 Augmenting Unsupervised Reinforcement Learning with Self-Reference
        23642, -- 2311.13081 Learning to Fly in Seconds
        23655, -- 2311.13231 Using Human Feedback to Fine-tune Diffusion Models without Any Reward
        23818, -- 2311.15951 Replay across Experiments: A Natural Extension of Off-Policy RL
        24396, -- 2312.03814 Pearl: A Production-ready Reinforcement Learning Agent
        24505, -- 2312.05162 A Review of Cooperation in Multi-agent Learning
        24524, -- 2312.05332 MPC-Inspired Reinforcement Learning for Verifiable Model-Free Control
        24801, -- 2312.09187 Vision-Language Models as a Source of Rewards
        25194, -- 2312.15730 Deep Reinforcement Learning for Quantitative Trading
        25329, -- 2401.00015 Distributional Reinforcement Learning-based Energy Arbitrage Strategie
        25797, -- 2401.07043 Quantum Advantage Actor-Critic for Reinforcement Learning
        25908, -- 2401.08898 Bridging State and History Representations: Understanding Self-Predict
        26038, -- 2401.10568 CivRealm: A Learning and Reasoning Odyssey in Civilization for Decisio
        26080, -- 2401.11237 Closing the Gap between TD Learning and Supervised Learning -- A Gener
        26086, -- 2401.11349 Asynchronous Parallel Reinforcement Learning for Optimizing Propulsive
        26090, -- 2401.11437 Open the Black Box: Step-based Policy Updates for Temporally-Correlate
        26119, -- 2401.11963 Bridging Evolutionary Algorithms and Reinforcement Learning: A Compreh
        26249, -- 2401.13662 The Definitive Guide to Policy Gradients in Deep Reinforcement Learnin
        26656, -- 2402.01391 StepCoder: Improve Code Generation with Reinforcement Learning from Co
        26856, -- 2402.03479 DRED: Zero-Shot Transfer in Reinforcement Learning via Data-Regularise
        27126, -- 2402.06552 Deceptive Path Planning via Reinforcement Learning with Graph Neural N
        27163, -- 2402.07127 Learning by Watching: A Review of Video-based Learning Approaches for
        27237, -- 2402.08112 A Competition Winning Deep Reinforcement Learning Agent in microRTS
        27246, -- 2402.08265 A Dense Reward View on Aligning Text-to-Image Diffusion with Preferenc
        27583, -- 2402.12181 Revisiting Data Augmentation in Deep Reinforcement Learning
        27752, -- 2402.13946 AttackGNN: Red-Teaming GNNs in Hardware Security Using Reinforcement L
        28051, -- 2402.17375 Impact of Computation in Integral Reinforcement Learning for Continuou
        28245, -- 2403.00564 EfficientZero V2: Mastering Discrete and Continuous Control with Limit
        28283, -- 2403.00991 SELFI: Autonomous Self-Improvement with Reinforcement Learning for Soc
        28360, -- 2403.02107 Iterated $Q$-Network: Beyond One-Step Bellman Updates in Deep Reinforc
        28762, -- 2403.07979 Do Agents Dream of Electric Sheep?: Improving Generalization in Reinfo
        28963, -- 2403.10929 Function-space Parameterization of Neural Networks for Sequential Lear
        30213, -- 2404.07525 Enhancing Policy Gradient with the Polyak Step-Size Adaption
        30286, -- 2404.08513 Adversarial Imitation Learning via Boosting
        30869, -- 2404.18231 From Persona to Personalization: A Survey on Role-Playing Language Age
        31522, -- 2405.13629 Maximum Entropy Reinforcement Learning via Energy-Based Normalizing Fl
        31553, -- 2405.14093 A Survey on Vision-Language-Action Models for Embodied AI
        31656, -- 2405.15083 MuDreamer: Learning Predictive World Models without Reconstruction
        32279, -- 2406.02081 FightLadder: A Benchmark for Competitive Multi-Agent Reinforcement Lea
        33213, -- 2406.12168 BPO: Staying Close to the Behavior LLM Creates Better Online LLM Align
        33620, -- 2406.16979 Understanding and Diagnosing Deep Reinforcement Learning
        33966, -- 2407.01418 RoboPack: Learning Tactile-Informed Dynamics Models for Dense Packing
        34434, -- 2407.07787 Continuous Control with Coarse-to-fine Reinforcement Learning
        34469, -- 2407.08250 Gradient Boosting Reinforcement Learning
        34502, -- 2407.08639 $β$-DPO: Direct Preference Optimization with Dynamic $β$
        34891, -- 2407.13221 Multimodal Label Relevance Ranking via Reinforcement Learning
        34893, -- 2407.13237 LLM-Empowered State Representation for Reinforcement Learning
        34995, -- 2407.14872 Adapt2Reward: Adapting Video-Language Models to Generalizable Robotic
        35476, -- 2408.01072 A Survey on Self-play Methods in Reinforcement Learning
        35731, -- 2408.05804 A Single Goal is All You Need: Skills and Exploration Emerge from Cont
        36459, -- 2409.00588 Diffusion Policy Policy Optimization
        36935, -- 2409.10277 Cognitive Kernel: An Open-source Agent System towards Generalist Autop
        37648, -- 2410.01458 From Reward Shaping to Q-Shaping: Achieving Unbiased Learning with LLM
        37966, -- 2410.04612 Regressing the Relative Future: Efficient Policy Optimization for Mult
        38319, -- 2410.08896 MAD-TD: Model-Augmented Data stabilizes High Update Ratio RL
        38324, -- 2410.08979 Overcoming Slow Decision Frequencies in Continuous Control: Model-Base
        38385, -- 2410.09754 SimBa: Simplicity Bias for Scaling Up Parameters in Deep Reinforcement
        38814, -- 2410.14606 Streaming Deep Reinforcement Learning Finally Works
        38861, -- 2410.15181 GUIDE: Real-Time Human-Shaped Agents
        39083, -- 2410.18238 CARLA2Real: a tool for reducing the sim2real gap in CARLA simulator
        39085, -- 2410.18252 Asynchronous RLHF: Faster and More Efficient Off-Policy RL for Languag
        40346, -- 2411.15370 Deep Policy Gradient Methods Without Batch Updates, Target Networks, o
        41075, -- 2412.04453 NaVILA: Legged Robot Vision-Language-Action Model for Navigation
        41121, -- 2412.04833 Wavelet Diffusion Neural Operator
        41701, -- 2412.12098 MaxInfoRL: Boosting exploration in reinforcement learning through info
        41750, -- 2412.12870 Towards Physically Interpretable World Models: Meaningful Weakly Super
        42651, -- 2501.04982 CuRLA: Curriculum Learning Based Deep Reinforcement Learning for Auton
        43296, -- 2501.16142 Towards General-Purpose Model-Free Reinforcement Learning
        43391, -- 2501.17992 Reinforcement-Learning Portfolio Allocation with Dynamic Embedding of
        43490, -- 2502.00288 Learning from Suboptimal Data in Continuous Control via Auto-Regressiv
        43769, -- 2502.04327 Value-Based Deep RL Scales Predictably
        44746, -- 2502.15280 Hyperspherical Normalization for Scalable Deep Reinforcement Learning
        45263, -- 2503.00533 BodyGen: Advancing Towards Efficient Embodiment Co-Design
        46906, -- 2503.21989 Bresa: Bio-inspired Reflexive Safe Reinforcement Learning for Contact-
        47026, -- 2503.23650 A Survey of Reinforcement Learning-Based Motion Planning for Autonomou
        47981, -- 2504.14945 Learning to Reason under Off-Policy Guidance
        48955, -- 2505.12366 DisCO: Reinforcing Large Reasoning Models with Discriminative Constrai
        49444, -- 2505.16826 KTAE: A Model-Free Algorithm to Key-Tokens Advantage Estimation in Mat
        49944, -- 2505.21432 Hume: Introducing System-2 Thinking in Visual-Language-Action Model
        50107, -- 2505.23458 Diffusion Guidance Is a Controllable Policy Improvement Operator
        50165, -- 2505.23803 MultiPhishGuard: An LLM-based Multi-Agent System for Phishing Email De
        50696, -- 2506.05968 Gradual Transition from Bellman Optimality Operator to Bellman Operato
        51186, -- 2506.13923 Adaptive Guidance Accelerates Reinforcement Learning of Reasoning Mode
        51276, -- 2506.15799 Steering Your Diffusion Policy with Latent Space Reinforcement Learnin
        51543, -- 2506.21872 A Survey of Continual Reinforcement Learning
        51834, -- 2507.08182 CTRLS: Chain-of-Thought Reasoning via Latent State-Transition
        51944, -- 2507.12856 Supervised Fine Tuning on Curated Data is Reinforcement Learning (and
        52747, -- 2509.09675 CDE: Curiosity-Driven Exploration for Efficient Reinforcement Learning
        52800, -- 2509.19301 Residual Off-Policy RL for Finetuning Behavior Cloning Policies
        53135, -- 2510.02245 ExGRPO: Learning to Reason from Experience
        54394, -- 2511.20633 Reinforcing Action Policies by Prophesying
        54504, -- 2512.02581 GoRL: An Algorithm-Agnostic Framework for Online Reinforcement Learnin
        55087, -- 2601.01425 DreamID-V:Bridging the Image-to-Video Gap for High-Fidelity Face Swapp
        55927, -- 2601.21363 Towards Bridging the Gap between Large-Scale Pretraining and Efficient
        56517, -- 2603.02083 π-StepNFT: Wider Space Needs Finer Steps in Online RL for Flow-based V
        56604, -- 2603.09400 Reward Prediction with Factorized World States
        57419, -- 2604.08706 Efficient RL Training for LLMs with Experience Replay
        57521, -- 2604.15308 RAD-2: Scaling Reinforcement Learning in a Generator-Discriminator Fra
        59320, -- 2603.15381 Why AI systems don't learn and what to do about it: Lessons on autonom
        60111, -- 2603.00730 MO-MIX: Multi-Objective Multi-Agent Cooperative Decision-Making With D
        60194, -- 2602.19362 LLMs Can Learn to Reason Via Off-Policy RL
        60760, -- 2602.12155 FAIL: Flow Matching Adversarial Imitation Learning for Image Generatio
        61399, -- 2602.02710 Maximum Likelihood Reinforcement Learning
        61974, -- 2601.19585 LLM-Enhanced Reinforcement Learning for Long-Term User Satisfaction in
        63099, -- 2601.00737 Stochastic Actor-Critic: Mitigating Overestimation via Temporal Aleato
        63220, -- 2512.23515 Alpha-R1: Alpha Screening with LLM Reasoning via Reinforcement Learnin
        63624, -- 2512.15089 Beyond Fast and Slow: Cognitive-Inspired Elastic Reasoning for Large L
        63846, -- 2512.10477 Symphony: A Heuristic Normalized Calibrated Advantage Actor and Critic
        64112, -- 2512.04770 Embodied Co-Design for Rapidly Evolving Agents: Taxonomy, Frontiers, a
        64155, -- 2512.03973 Guided Flow Policy: Learning from High-Value Actions in Offline Reinfo
        64596, -- 2511.19584 Learning Massively Multitask World Models for Continuous Control
        64646, -- 2511.18671 Multi-Agent Cross-Entropy Method with Monotonic Nonlinear Critic Decom
        67307, -- 2509.26209 Diversity-Incentivized Exploration for Versatile Reasoning
        67383, -- 2509.25424 Polychromic Objectives for Reinforcement Learning
        67921, -- 2509.19292 SOE: Sample-Efficient Robot Policy Self-Improvement via On-Manifold Ex
        68149, -- 2509.15733 GP3: A 3D Geometry-Aware Policy with Multi-View Images for Robotic Man
        71827, -- 2506.17204 Network Sparsity Unlocks the Scaling Potential of Deep Reinforcement L
        71981, -- 2506.12622 DR-SAC: Distributionally Robust Soft Actor-Critic for Reinforcement Le
        73179, -- 2505.03181 VLM Q-Learning: Aligning Vision-Language Models for Interactive Decisi
        74490, -- 2502.17813 Safe Multi-Agent Navigation guided by Goal-Conditioned Safe Reinforcem
        74609, -- 2502.12862 RobotIQ: Empowering Mobile Robots with Human-Level Planning for Real-W
        74929, -- 2502.01932 VolleyBots: A Testbed for Multi-Drone Volleyball Game Combining Motion
        75546, -- 2412.06685 Policy Agnostic RL: Offline RL and Online RL Fine-Tuning of Any Class
        75671, -- 2412.10381 Supervised Learning-enhanced Multi-Group Actor Critic for Live Stream
        76451, -- 2409.03996 Goal-Reaching Policy Learning from Non-Expert Observations via Effecti
        76864, -- 2407.00496 A Two-stage Reinforcement Learning-based Approach for Multi-entity Tas
        77075, -- 2406.04081 Bootstrapping Expectiles in Reinforcement Learning
        77509, -- 2404.02235 Is Exploration All You Need? Effective Exploration Characteristics for
        77895, -- 2401.14858 RESPRECT: Speeding-up Multi-fingered Grasping with Residual Reinforcem
        78054, -- 2312.13788 Open-Source Reinforcement Learning Environments Implemented in MuJoCo
        78920, -- 2306.03484 A Grasp Pose is All You Need: Learning Multi-fingered Grasping with De
        78963, -- 2305.18501 DoMo-AC: Doubly Multi-step Off-policy Actor-Critic Algorithm
        79100, -- 2304.13174 Dynamic Datasets and Market Environments for Financial Reinforcement L
        79580, -- 2211.06665 A Survey on Explainable Reinforcement Learning: Concepts, Algorithms,
        79727, -- 2209.10081 Revisiting Discrete Soft Actor-Critic
        79854, -- 2207.04296 TensorIR: An Abstraction for Automatic Tensorized Program Optimization
        80197, -- 2202.08417 Retrieval-Augmented Reinforcement Learning
        80240, -- 2201.12289 The Power of First-Order Smooth Optimization for Black-Box Non-Smooth
        80377, -- 2111.12045 Adaptive Multi-Goal Exploration
        80429, -- 2110.12654 Facilitating Database Tuning with Hyper-Parameter Optimization: A Comp
        80498, -- 2109.10813 A Workflow for Offline Model-Free Robotic Reinforcement Learning
        80563, -- 2108.09330 Conformal Bootstrap with Reinforcement Learning
        80662, -- 2106.09714 No-frills Dynamic Planning using Static Planners
        80675, -- 2106.06170 Taylor Expansion of Discount Factors
        80822, -- 2103.09575 Regularized Behavior Value Estimation
        82947, -- 2605.07079 Learning Visual Feature-Based World Models via Residual Latent Action
        83259, -- 2605.11711 Debiased Model-based Representations for Sample-efficient Continuous C
        85696, -- 2506.21427 Flow-Based Single-Step Completion for Efficient and Expressive Policy
        85739, -- 2509.19672 Memory-Augmented Potential Field Theory: A Framework for Adaptive Cont
        85761, -- 2505.18763 GenPO: Generative Diffusion Models Meet On-Policy Reinforcement Learni
        85763, -- 2509.24748 Robust Policy Expansion for Offline-to-Online RL under Diverse Data Co
        85764, -- 2406.01423 Value Improved Actor Critic Algorithms
        85822, -- 2502.08021 Model Selection for Off-policy Evaluation: New Algorithms and Experime
        86021, -- 2505.15602 Deep learning for continuous-time stochastic control with jumps
        86100, -- 2505.24161 Proxy Target: Bridging the Gap Between Discrete Spiking Neural Network
        86355, -- 2505.21665 Convergent Functions, Divergent Forms
        86511, -- 2505.18983 AmorLIP: Efficient Language-Image Pretraining via Amortization
        86613, -- 2506.06521 Sharp Gap-Dependent Variance-Aware Regret Bounds for Tabular MDPs
        86652, -- 2506.15544 Stable Gradients for Stable Learning at Scale in Deep Reinforcement Le
        86845, -- 2509.24804 DyMoDreamer: World Modeling with Dynamic Modulation
        86886, -- 2404.15617 DPO: A Differential and Pointwise Control Approach to Reinforcement Le
        86957, -- 2507.11060 Personalized Exercise Recommendation with Semantically-Grounded Knowle
        87071, -- 2505.10646 Accelerating Visual-Policy Learning through Parallel Differentiable Si
        87409, -- 2505.18005 Distances for Markov chains from sample streams
        87462, -- 2505.10947 Certifying Stability of Reinforcement Learning Policies using Generali
        87705, -- 2503.13217 Dense Policy: Bidirectional Autoregressive Learning of Actions
        88893, -- 2507.00518 Exploring Large Action Sets with Hyperspherical Embeddings using von M
        89025, -- 2502.11033 Convergence of Policy Mirror Descent Beyond Compatible Function Approx
        89083, -- 2506.00962 Reinforcement Learning with Random Time Horizons
        89098, -- 2506.13672 The Courage to Stop: Overcoming Sunk Cost Fallacy in Deep Reinforcemen
        89358, -- 2501.14372 Reinforcement Learning for Quantum Control under Physical Constraints
        89382, -- 2503.01885 Learning Policy Committees for Effective Personalization in MDPs with
        89562, -- 2506.05615 When Maximum Entropy Misleads Policy Optimization
        89565, -- 2507.06628 Goal-Oriented Skill Abstraction for Offline Multi-Task Reinforcement L
        89770, -- 2505.19247 Improving Value Estimation Critically Enhances Vanilla Policy Gradient
        89816, -- 2412.14312 Stealing That Free Lunch: Exposing the Limits of Dyna-Style Reinforcem
        90021, -- 2503.06893 Policy Regularization on Globally Accessible States in Cross-Dynamics
        90051, -- 2409.15128 The Number of Trials Matters in Infinite-Horizon General-Utility Marko
        91204, -- 2410.04988 Efficient Model-Based Reinforcement Learning Through Optimistic Thomps
        91345, -- 2409.16197 Second Order Bounds for Contextual Bandits with Function Approximation
        91383, -- 2410.07933 Offline Hierarchical Reinforcement Learning via Inverse Optimization
        91398, -- 2503.03989 Integrating Protein Dynamics into Structure-Based Drug Design via Full
        91418, -- 2410.07994 Neuroplastic Expansion in Deep Reinforcement Learning
        91629, -- 2403.04453 Efficient Off-Policy Learning for High-Dimensional Action Spaces
        91777, -- 2410.12730 Counterfactual Generative Modeling with Variational Causal Inference
        91847, -- 2503.04975 Energy-Weighted Flow Matching for Offline Reinforcement Learning
        91908, -- 2502.06919 Select before Act: Spatially Decoupled Action Repetition for Continuou
        92183, -- 2503.12932 Efficient Action-Constrained Reinforcement Learning via Acceptance-Rej
        92196, -- 2501.15085 Data Center Cooling System Optimization Using Offline Reinforcement Le
        92241, -- 2407.20651 Towards Generalizable Reinforcement Learning via Causality-Guided Self
        92390, -- 2412.12089 Stabilizing Reinforcement Learning in Differentiable Multiphysics Simu
        92606, -- 2509.22566 From Parameters to Behaviors: Unsupervised Compression of the Policy S
        92781, -- 2511.00091 Self-Improving Vision-Language-Action Models with Data Generation via
        92801, -- 2602.01789 RFS: Reinforcement learning with Residual flow steering for dexterous
        92891, -- 2511.07730 Scaling Goal-conditioned Reinforcement Learning with Multistep Quasime
        92897, -- 2512.15379 Remotely Detectable Robot Policy Watermarking
        92956, -- 2505.13150 Zero-Shot Adaptation of Behavioral Foundation Models to Unseen Dynamic
        93017, -- 2512.00536 Algorithmic Guarantees for Distilling Supervised and Offline RL Datase
        93034, -- 2602.12087 Geometry of Uncertainty: Learning Metric Spaces for Multimodal State E
        93042, -- 2510.06649 Local Reinforcement Learning with Action-Conditioned Root Mean Squared
        93126, -- 2506.10137 Self-Predictive Representations for Combinatorial Generalization in Be
        93143, -- 2510.11103 A Primer on SO(3) Action Representations in Deep Reinforcement Learnin
        93185, -- 2510.13704 Simplicial Embeddings Improve Sample Efficiency in Actor–Critic Agents
        93446, -- 2506.05980 AMPED: Adaptive Multi-objective Projection for balancing Exploration a
        93668, -- 2603.05440 Latent Wasserstein Adversarial Imitation Learning
        93862, -- 2505.15782 Solving General-Utility Markov Decision Processes in the Single-Trial
        93918, -- 2602.16548 RIDER: 3D RNA Inverse Design with Reinforcement Learning-Guided Diffus
        93988, -- 2512.01228 On the Tension Between Optimality and Adversarial Robustness in Policy
        94050, -- 2509.19800 Analysis of approximate linear programming solution to Markov decision
        94116, -- 2512.04559 Diffusion Fine-Tuning via Reparameterized Policy Gradient of the Soft
        94138, -- 2510.22512 Transitive RL: Value Learning via Divide and Conquer
        94376, -- 2407.01570 Ego-Foresight: Self-supervised Learning of Agent-Aware Representations
        94820, -- 2604.01913 The Rank and Gradient Lost in Non-stationarity: Sample Weight Decay fo
        94823, -- 2507.11019 Relative Entropy Pathwise Policy Optimization
        94841, -- 2507.21533 Model Predictive Adversarial Imitation Learning for Planning from Obse
        94957, -- 2511.08234 Beyond Distributions: Geometric Action Control for Continuous Reinforc
        95028, -- 2601.20765 Less Is More: Clustered Cross-Covariance Control for Offline RL
        95062, -- 2509.23791 CaRe-BN: Precise Moving Statistics for Stabilizing Spiking Neural Netw
        95156, -- 2502.06760 Infinite-Horizon Value Function Approximation for Model Predictive Con
        95187, -- 2510.17086 Learning to Design Soft Hands Using Reward Models
        95276, -- 2603.03137 RL-Based Coverage Path Planning for Deformable Objects on 3D Surfaces
        95324, -- 2605.00159 E^2DT: Efficient and Effective Decision Transformer with Experience-Aw
        95732, -- 2602.02831 Adaptive Linear Path Model-Based Diffusion
        95780, -- 2602.14726 ManeuverNet: A Soft Actor-Critic Framework for Precise Maneuvering of
        96210, -- 2510.09976 Reinforcement Fine-Tuning of Flow-Matching Policies for Vision-Languag
        96327, -- 2511.13459 Contact-Safe Reinforcement Learning with ProMP Reparameterization and
        96654, -- 2510.15189 RM-RL: Role-Model Reinforcement Learning for Precise Robot Manipulatio
        96707, -- 2509.19555 AnySafe: Adapting Latent Safety Filters at Runtime Via Safety Constrai
        96981, -- 2507.04140 Learning Humanoid Arm Motion Via Centroidal Momentum Regularized Multi
        97163, -- 2505.18899 Beyond Domain Randomization: Event-Inspired Perception for Visually Ro
        97250, -- 2509.14758 Designing Latent Safety Filters Using Pre-Trained Vision Models
        97269, -- 2603.27400 Rainbow-DemoRL: Combining Improvements in Demonstration-Augmented Rein
        97540, -- 2510.00425 Conflict-Based Search As a Protocol: A Multi-Agent Motion Planning Pro
        97683, -- 2406.09953 DAG-Plan: Generating Directed Acyclic Dependency Graphs for Dual-Arm C
        97742, -- 2503.01252 Diffusion Stabilizer Policy for Automated Surgical Robot Manipulations
        98129, -- 2606.11087 Test-Time Gradient Guidance of Flow Policies in Reinforcement Learning
        98570, -- 2602.05845 Self-Supervised Learning with a Multi-Task Latent Space Objective
        98829, -- 2606.21271 Reward-free Pretraining for Reinforcement Learning via Occupancy Cover
        99043, -- 2607.00917 Valdi: Value Diffusion World Models
        99140, -- 2601.21778 Error Amplification Limits ANN-to-SNN Conversion in Continuous Control
        99153, -- 2605.01968 AdamO: A Collapse-Suppressed Optimizer for Offline RL
        99862, -- 2510.12334 Finite-time Convergence Analysis of Actor-Critic with Evolving Reward
        99977, -- 2606.03698 $\texttt{Multi}^2$: Hierarchical Multi-Agent Decision-Making with LLM-
        100239, -- 2602.13700 Optimal Regret for Policy Optimization in Contextual Bandits
        100241, -- 2602.13706 Near-Optimal Regret for Policy Optimization in Contextual MDPs with Ge
        100346, -- 2605.14587 Angel or Demon: Investigating the Plasticity Interventions' Impact on
        100559, -- 2604.19033 Intentional Updates for Streaming Reinforcement Learning
        100609, -- 2604.14698 Mean Flow Policy Optimization
        100633, -- 2602.10539 What Makes Value Learning Efficient in Residual Reinforcement Learning
        100771, -- 2601.22970 Stabilizing the Q-Gradient Field for Policy Smoothness in Actor-Critic
        100900, -- 2602.01460 Non-Uniform Noise-to-Signal Ratio in the REINFORCE Policy-Gradient Est
        100933, -- 2508.02103 Instance-Dependent Continuous-Time Reinforcement Learning via Maximum
        101464, -- 2511.11592 Mind Your Entropy: From Maximum Entropy to Trajectory Entropy-Constrai
        101501, -- 2509.19771 Frictional Q-Learning
        101549, -- 2605.14026 R2R2: Robust Representation for Intensive Experience Reuse via Redunda
        101607, -- 2605.01702 Floating-Point Networks with Automatic Differentiation Can Represent A
        101721, -- 2606.16856 Video-Based Optimal Transport for Feedback-Efficient Offline Preferenc
        101727, -- 2509.25582 Safe In-Context Reinforcement Learning
        101870, -- 2602.16305 BAT: Better Audio Transformer Guided by Convex Gated Probing
        101909, -- 2602.03911 The Role of Target Update Frequencies in Q-Learning
        101932, -- 2601.21306 The Surprising Difficulty of Search in Model-Based Reinforcement Learn
        102138, -- 2602.17632 SMAC: Score-Matched Actor-Critics for Robust Offline-to-Online Transfe
        103050, -- 2601.00095 Adaptive Constraint Propagation: Scaling Structured Inference for Larg
        103887, -- 2106.06860 A Minimalist Approach to Offline Reinforcement Learning
        106524, -- 2511.16248 Revisiting Fairness-aware Interactive Recommendation: Item Lifecycle a
        106835, -- 2601.18479 Enhancing Control Policy Smoothness by Aligning Actions with Predictio
        106946, -- 2512.20831 Context-Sensitive Abstractions for Reinforcement Learning with Paramet
        106975, -- 2511.14262 Object-Centric World Models for Causality-Aware Reinforcement Learning
        107034, -- 2602.06227 Do It for HER: First-Order Temporal Logic Reward Specification in Rein
        107275, -- 2511.16629 Stabilizing Policy Gradient Methods via Reward Profiling
        107386, -- 2511.08086 Dynamic Sparsity: Challenging Common Sparsity Assumptions for Learning
        108332, -- 2508.11143 Actor-Critic for Continuous Action Chunks: A Reinforcement Learning Fr
        115632, -- 2404.01636 Learning to Control Camera Exposure via Reinforcement Learning
        116641, -- 2403.19490 Jointly Training and Pruning CNNs via Learnable Agent Guidance and Ali
        116750, -- 2405.14077 Learning to Transform Dynamically for Better Adversarial Transferabili
        119597, -- 2507.07445 StarDojo: Benchmarking Open-Ended Behaviors of Agentic Multimodal LLMs
        120812, -- 2604.01659 AURA: Multi-modal Shared Autonomy for Urban Navigation
        122052, -- 2105.00636 Learning to drive from a world on rails
        122056, -- 2111.08575 GRI: General Reinforced Imitation and its Application to Vision-Based
        123260, -- 2610.04851 CURIO: Curiosity-Driven Test-Time Learning for Open-Ended Discovery
        123322, -- 2105.08664 Deep Graph Convolutional Reinforcement Learning for Financial Portfoli
        123426, -- 2610.18677 Model-Based Online Decision Making via Generative Trajectory Planning
        124183, -- 2603.10199 Actor-Accelerated Policy Dual Averaging for Reinforcement Learning in
        124687, -- 2606.18697 Stealthy World Model Manipulation via Data Poisoning
        125250, -- 2609.16222 How I learned to stop worrying and love StopGrads: Stationarity, Conve
        125342, -- 2603.05066 Reward-Conditioned Reinforcement Learning
        125637, -- 2603.01891 SEAR: Sample Efficient Action Chunking Reinforcement Learning
        126387, -- 2603.26741 Language-Conditioned World Modeling for Visual Navigation
        127053, -- 2601.10471 DeFlow: Decoupling Behavior-Prior Modeling and Value Maximization for
        127558, -- 2607.07235 ORCAID: Oblique Rule-Based Continuous-Action Interpretation for Deep R
        128224, -- 2605.14022 Policy-DRIFT: Dynamic Reward-Informed Flow Trajectory Steering
        128718, -- 2605.08315 Reflective Prompted Policy Optimization: Trajectory-Grounded Revision
        129709, -- 2610.07899 Variance-Averse n-Step Offline Reinforcement Learning for Sparse Long-
        129741, -- 2601.21572 Signal-Adaptive Trust Regions for Gradient-Free Optimization of Recurr
        130572, -- 2605.10236 When Does Non-Uniform Replay Matter in Reinforcement Learning?
        130828, -- 2510.27329 Reinforcement Learning for Long-Horizon Unordered Tasks: From Boolean
        130879, -- 2603.29501 Target-Aligned Reinforcement Learning
        131045, -- 2605.24331 CurveRL: Principled Distribution-Aware Context Reweighting for LLM Rea
        132060  -- 2610.19080 Backpropagating Verifier Rewards Through Continuous Flow Language Mode
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the DDPG paper without naming, using or comparing against DDPG'
FROM ddpg_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ddpg_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ddpg_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- td3: 25 links, 49 exclusions. Semantic Scholar returned 1000 citers of the source, 51 local.
CREATE TEMP TABLE td3_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'td3'
  AND p.id IN (
        1128, -- 1802.09477 Addressing Function Approximation Error in Actor-Critic Methods
        4102, -- 2009.01555 Sample-Efficient Automated Deep Reinforcement Learning
        5976, -- 2106.06842 Recomposing the Reinforcement Learning Building Blocks with Hypernetwo
        7045, -- 2110.12628 Recurrent Off-policy Baselines for Memory-based Continuous Control
        16690, -- 2305.20081 Efficient Diffusion Policies for Offline Reinforcement Learning
        21653, -- 2310.05858 Distributional Soft Actor-Critic with Three Refinements
        28249, -- 2403.00673 Snapshot Reinforcement Learning: Leveraging Prior Trajectories for Eff
        50023, -- 2505.22642 FastTD3: Simple, Fast, and Capable Reinforcement Learning for Humanoid
        50696, -- 2506.05968 Gradual Transition from Bellman Optimality Operator to Bellman Operato
        67688, -- 2510.03257 Triple-BERT: Do We Really Need MARL for Order Dispatch on Ride-Sharing
        77075, -- 2406.04081 Bootstrapping Expectiles in Reinforcement Learning
        81009, -- 2011.09607 FinRL: A Deep Reinforcement Learning Library for Automated Stock Tradi
        85764, -- 2406.01423 Value Improved Actor Critic Algorithms
        85835, -- 2504.11453 A Clean Slate for Offline Reinforcement Learning
        89073, -- 2507.08387 Online Pre-Training for Offline-to-Online Reinforcement Learning
        92930, -- 2506.16608 Distributions as Actions: A Unified Framework for Diverse Action Space
        93143, -- 2510.11103 A Primer on SO(3) Action Representations in Deep Reinforcement Learnin
        94820, -- 2604.01913 The Rank and Gradient Lost in Non-stationarity: Sample Weight Decay fo
        96152, -- 2602.23972 Learning Robust Control Policies for Inverted Pose on Miniature Blimp
        96241, -- external Learning to Throw Objects Safely in Multi-Obstacle Environments
        96659, -- external Quantization of DRL Models for Embedded Microcontrollers
        97226, -- external Behavior Cloning-Enhanced Deep Reinforcement Learning for Robot Naviga
        102138, -- 2602.17632 SMAC: Score-Matched Actor-Critics for Robust Offline-to-Online Transfe
        107670, -- 2505.12340 DIMM: Decoupled Multi-hierarchy Kalman Filter via Reinforcement Learni
        131918  -- 2611.01139 World Models Need Not Be Right to Rank Policies Right: Relative Bounds
  );

DELETE FROM paper_method_exclusions x
USING td3_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM td3_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM td3_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE td3_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'td3'
  AND p.id IN (
        57364, -- 2604.06938 POS-ISP: Pipeline Optimization at the Sequence Level for Task-aware IS
        57836, -- 2605.00416 Learning while Deploying: Fleet-Scale Reinforcement Learning for Gener
        83259, -- 2605.11711 Debiased Model-based Representations for Sample-efficient Continuous C
        83560, -- 2605.12416 Aligning Flow Map Policies with Optimal Q-Guidance
        92528, -- 2605.27079 Trust Region Q Adjoint Matching
        93165, -- 2605.14779 Peng's Q($\lambda$) for Conservative Value Estimation in Offline Reinf
        93315, -- 2604.24532 A Reward-Free Viewpoint on Multi-Objective Reinforcement Learning
        97269, -- 2603.27400 Rainbow-DemoRL: Combining Improvements in Demonstration-Augmented Rein
        98129, -- 2606.11087 Test-Time Gradient Guidance of Flow Policies in Reinforcement Learning
        98225, -- 2605.03065 OGPO: Sample Efficient Full-Finetuning of Generative Control Policies
        98922, -- 2606.18953 Object-Centric Residual RL for Zero-Shot Sim-to-Real VLA Enhancement
        99153, -- 2605.01968 AdamO: A Collapse-Suppressed Optimizer for Offline RL
        99724, -- 2605.21822 Implicit Safety Alignment from Crowd Preferences
        99977, -- 2606.03698 $\texttt{Multi}^2$: Hierarchical Multi-Agent Decision-Making with LLM-
        99988, -- 2605.21168 ScenePilot: Controllable Boundary-Driven Critical Scenario Generation
        100159, -- 2605.26784 Ratio-Variance Regularized Policy Optimization
        100370, -- 2606.14192 DRIVE: Distributional and Retrieval-Augmented Bidding with Value Evalu
        100600, -- 2605.19592 Implicit Action Chunking for Smooth Continuous Control
        100609, -- 2604.14698 Mean Flow Policy Optimization
        100965, -- 2605.30056 Sample-Efficient Diffusion-based Reinforcement Learning with Critic Gu
        101526, -- 2605.29782 Hista and Numca: Estimate State Value Effectively for Large Language M
        101549, -- 2605.14026 R2R2: Robust Representation for Intensive Experience Reuse via Redunda
        102104, -- 2605.23551 Goal-Conditioned Agents that Learn Everything All at Once
        102259, -- 2604.25496 Improving Zero-Shot Offline RL via Behavioral Task Sampling
        102268, -- 2605.25867 CINOC: Cardinality-Invariant Neural Operator Policies for Scalable PDE
        109767, -- 2608.24479 WarpSAC: Towards the Pinnacle of Scalable Off-policy RL by Rethinking
        122096, -- 2609.21788 From Pretraining to Proficiency: Real-World Subtask RL for Long-Horizo
        122123, -- 2609.13231 ShieldVLA: Feasibility-Aware Safety Alignment for Vision-Language-Acti
        123426, -- 2610.18677 Model-Based Online Decision Making via Generative Trajectory Planning
        124829, -- 2604.18978 Low-Rank Adaptation for Critic Learning in Off-Policy Reinforcement Le
        126349, -- 2605.11665 Nautilus: From One Prompt to Plug-and-Play Robot Learning
        126446, -- 2606.21297 NASDAQ: Normalized Observation Space Dynamics-Augmented Q-Learning
        126810, -- 2610.20318 Efficient Test-Time Adaptation For Robot Policies
        127601, -- 2609.31066 Modeling quantum neural network gradient with reinforcement learning
        128224, -- 2605.14022 Policy-DRIFT: Dynamic Reward-Informed Flow Trajectory Steering
        128406, -- 2606.05555 Representation Learning Enables Scalable Multitask Deep Reinforcement
        128543, -- 2607.13498 Factorized Spectral Representations for Reinforcement Learning
        128590, -- 2605.08946 A Single Deep Preference-Conditioned Policy for Learning Pareto Covera
        128718, -- 2605.08315 Reflective Prompted Policy Optimization: Trajectory-Grounded Revision
        129053, -- 2609.35615 Behavioral Foundation Models for Quality Diversity
        129358, -- 2609.33337 Safe Score Matching: Diffusion Policies with Hamilton-Jacobi Reachabil
        129466, -- 2606.14029 Utility-Constrained Policy Optimization
        129709, -- 2610.07899 Variance-Averse n-Step Offline Reinforcement Learning for Sparse Long-
        130201, -- 2606.00350 Drift Q-Learning
        130572, -- 2605.10236 When Does Non-Uniform Replay Matter in Reinforcement Learning?
        130773, -- 2610.03361 Follow the Winners: Conservative Policy Improvement with the Cross-Ent
        130879, -- 2603.29501 Target-Aligned Reinforcement Learning
        131196, -- 2610.08989 LASER: Latent Space Adjoint Matching for Support Constrained Entropy R
        131482  -- 2610.36068 Rollback: Experience Backtracking in World Models for Policy Improveme
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the TD3 paper without naming, using or comparing against TD3'
FROM td3_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING td3_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING td3_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- behavior-cloning: 264 links, 4 exclusions.
CREATE TEMP TABLE behavior_cloning_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'behavior-cloning'
  AND p.id IN (
        1124, -- 1802.08802 Reinforcement Learning on Web Interfaces Using Workflow-Guided Explora
        3433, -- 2004.13529 Augmented Behavioral Cloning from Observation
        4770, -- 2012.11717 Social NCE: Contrastive Learning of Socially-aware Motion Representati
        5406, -- 2104.04258 Counter-Strike Deathmatch with Large-Scale Behavioural Cloning
        6701, -- 2109.10862 Recursively Summarizing Books with Human Feedback
        7180, -- 2111.04714 A Dataset Perspective on Offline Reinforcement Learning
        7201, -- 2111.06383 Distilling Motion Planner Augmented Policies into Visual Control Polic
        7206, -- 2111.06889 DriverGym: Democratising Reinforcement Learning for Autonomous Driving
        7557, -- 2112.09332 WebGPT: Browser-assisted question-answering with human feedback
        7804, -- 2201.12594 Robust Imitation Learning from Corrupted Demonstrations
        7862, -- 2202.01771 Pre-Trained Language Models for Interactive Decision-Making
        9577, -- 2206.11251 Behavior Transformers: Cloning $k$ modes with one stone
        9653, -- 2206.15469 Watch and Match: Supercharging Imitation with Regularized Optimal Tran
        10487, -- 2209.15469 Zero-Shot Retrieval with Search Agents and Hybrid Environments
        10756, -- 2210.06407 Interactive Language: Talking to Robots in Real Time
        11369, -- 2211.08416 Robot Learning on the Job: Human-in-the-Loop Autonomy and Learning Dur
        11548, -- 2211.12740 Masked Autoencoding for Scalable and Generalizable Decision Making
        12228, -- 2212.13326 Behavioral Cloning via Search in Video PreTraining Latent Space
        12521, -- 2301.10677 Imitating Human Behaviour with Diffusion Models
        14576, -- 2304.04591 For Pre-Trained Vision Models in Motor Control, Not All Policy Learnin
        14994, -- 2304.13774 Distance Weighted Supervised Learning for Offline Interaction Data
        15999, -- 2305.13804 OER: Offline Experience Replay for Continual Offline Reinforcement Lea
        16096, -- 2305.14550 When should we prefer Decision Transformers for Offline Reinforcement
        16424, -- 2305.17390 SwiftSage: A Generative Agent with Fast and Slow Thinking for Complex
        16729, -- 2306.00323 Thought Cloning: Learning to Think while Acting by Imitating Human Thi
        16791, -- 2306.00937 STEVE-1: A Generative Model for Text-to-Behavior in Minecraft
        17321, -- 2306.07290 Value function estimation using conditional diffusion models for contr
        17460, -- 2306.09082 Behavioral Cloning via Search in Embedded Demonstration Dataset
        17729, -- 2306.13818 AR2-D2:Training a Robot Without a Robot
        17999, -- 2307.01849 Crossway Diffusion: Improving Diffusion-based Visuomotor Policy via Se
        18472, -- 2307.10936 PASTA: Pretrained Action-State Transformer Agents
        18681, -- 2307.14535 Scaling Up and Distilling Down: Language-Guided Robot Skill Acquisitio
        18759, -- 2307.15980 Initial State Interventions for Deconfounded Imitation Learning
        18832, -- 2308.00398 DriveAdapter: Breaking the Coupling Barrier of Perception and Planning
        19001, -- 2308.03526 AlphaStar Unplugged: Large-Scale Offline Reinforcement Learning
        19986, -- 2308.16891 GNFactor: Multi-Task Real Robot Learning with Generalizable Neural Fea
        21263, -- 2310.01468 Probing the Multi-turn Planning Capabilities of LLMs via 20 Question G
        21686, -- 2310.06147 Reinforcement Learning in the Era of LLMs: What is Essential? What is
        21687, -- 2310.06171 Memory-Consistent Neural Networks for Imitation Learning
        22120, -- 2310.11428 Butterfly Effects of SGD Noise: Error Amplification in Behavior Clonin
        22597, -- 2310.17303 Demonstration-Regularized RL
        22667, -- 2310.18247 Guided Data Augmentation for Offline Reinforcement Learning and Imitat
        23636, -- 2311.12996 RLIF: Interactive Imitation Learning as Reinforcement Learning
        24277, -- 2312.02519 Creative Agents: Empowering Agents with Imagination for Creative Tasks
        24555, -- 2312.05742 The Generalization Gap in Offline Reinforcement Learning
        24990, -- 2312.12345 On the Effectiveness of Retrieval, Alignment, and Replay in Manipulati
        25469, -- 2401.02117 Mobile ALOHA: Learning Bimanual Mobile Manipulation with Low-Cost Whol
        25935, -- 2401.09243 DiffClone: Enhanced Behaviour Cloning in Robotics with Diffusion-Drive
        26045, -- 2401.10700 Safe Offline Reinforcement Learning with Feasibility-Guided Diffusion
        26124, -- 2401.12046 Fourier Transporter: Bi-Equivariant Robotic Manipulation in 3D
        26307, -- 2401.14403 Adaptive Mobile Manipulation for Articulated Objects In the Open World
        26941, -- 2402.04292 AdaFlow: Imitation Learning with Variance-Adaptive Flow-Based Policies
        26957, -- 2402.04494 Amortized Planning with Large-Scale Transformers: A Case Study on Ches
        27042, -- 2402.05546 Offline Actor-Critic Reinforcement Learning Scales to Large Models
        27217, -- 2402.07876 Policy Improvement using Language Feedback Models
        27237, -- 2402.08112 A Competition Winning Deep Reinforcement Learning Agent in microRTS
        27914, -- 2402.15567 Foundation Policies with Hilbert Representations
        28436, -- 2403.03141 Language Guided Exploration for RL Agents in Text Environments
        28797, -- 2403.08715 SOTOPIA-$π$: Interactive Learning of Socially Intelligent Language Age
        32994, -- 2406.10454 HumanPlus: Humanoid Shadowing and Imitation from Humans
        33174, -- 2406.11896 DigiRL: Training In-The-Wild Device-Control Agents with Autonomous Rei
        33771, -- 2406.18872 Efficacy of Language Model Self-Play in Non-Zero-Sum Games
        33867, -- 2406.20095 LLaRA: Supercharging Robot Learning Data for Vision-Language Policy
        34228, -- 2407.04856 Explorative Imitation Learning: A Path Signature Approach for Continuo
        34270, -- 2407.05530 This&That: Language-Gesture Controlled Video Generation for Robot Plan
        34434, -- 2407.07787 Continuous Control with Coarse-to-fine Reinforcement Learning
        34446, -- 2407.07875 Generative Image as Action Models
        35006, -- 2407.15002 GET-Zero: Graph Embodiment Transformer for Zero-shot Embodiment Genera
        35124, -- 2407.16677 From Imitation to Refinement -- Residual RL for Precise Assembly
        35763, -- 2408.06327 VisualAgentBench: Towards Large Multimodal Models as Visual Foundation
        35819, -- 2408.07199 Agent Q: Advanced Reasoning and Learning for Autonomous AI Agents
        36485, -- 2409.01083 Affordance-based Robot Manipulation with Flow Matching
        36821, -- 2409.08273 Hand-Object Interaction Pretraining from Videos
        37056, -- 2409.12192 DynaMo: In-Domain Dynamics Pretraining for Visuo-Motor Control
        38036, -- 2410.05434 Better than Your Teacher: LLM Agents that learn from Privileged AI Fee
        39345, -- 2410.22325 Robots Pre-train Robots: Manipulation-Centric Robotic Representation f
        39783, -- 2411.05273 Real-World Offline Reinforcement Learning from Vision Language Model F
        40151, -- 2411.12155 Coarse-to-fine Q-Network with Action Sequence for Data-Efficient Robot
        40667, -- 2411.19309 GRAPE: Generalizing Robot Policy via Preference Alignment
        40917, -- 2412.02676 Planning-Guided Diffusion Policy Learning for Generalizable Contact-Ri
        42745, -- 2501.06521 Fine-tuning Large Language Models for Improving Factuality in Legal Qu
        43024, -- 2501.11425 Agent-R: Training Language Model Agents to Reflect via Iterative Self-
        43870, -- 2502.05450 ConRFT: A Reinforced Fine-tuning Method for VLA Models via Consistency
        43959, -- 2502.06781 Exploring the Limit of Outcome Reward for Learning Mathematical Reason
        44032, -- 2502.07555 O1 Embedder: Let Retrievers Think Before Action
        44630, -- 2502.14276 STeCa: Step-level Trajectory Calibration for LLM Agent Learning
        45395, -- 2503.02197 ATLaS: Agent Tuning via Learning Critical Steps
        45417, -- 2503.02505 ROCKET-2: Steering Visuomotor Policy via Cross-View Goal Alignment
        46202, -- 2503.12532 STEVE: A Step Verification Pipeline for Computer-use Agent Training
        46380, -- 2503.15108 VIPER: Visual Perception and Explainable Reasoning for Sequential Deci
        47297, -- 2504.03597 Real-is-Sim: Bridging the Sim-to-Real Gap with a Dynamic Digital Twin
        48619, -- 2505.07096 X-Sim: Cross-Embodiment Learning via Real-to-Sim-to-Real
        49407, -- 2505.16421 WebAgent-R1: Training Web Agents via End-to-End Multi-Turn Reinforceme
        49450, -- 2505.16856 Efficient Online RL Fine Tuning with Offline Pre-trained Policy Only
        50107, -- 2505.23458 Diffusion Guidance Is a Controllable Policy Improvement Operator
        50265, -- 2505.24838 VideoCAD: A Large-Scale Video Dataset for Learning UI Interactions and
        50382, -- 2506.01413 Incentivizing Reasoning for Advanced Instruction-Following of Large La
        50642, -- 2506.05294 A Smooth Sea Never Made a Skilled $\texttt{SAILOR}$: Robust Imitation
        50766, -- 2506.07505 Reinforcement Learning via Implicit Imitation Guidance
        50992, -- 2506.10326 A Benchmark for Generalizing Across Diverse Team Strategies in Competi
        51276, -- 2506.15799 Steering Your Diffusion Policy with Latent Space Reinforcement Learnin
        51944, -- 2507.12856 Supervised Fine Tuning on Curated Data is Reinforcement Learning (and
        52800, -- 2509.19301 Residual Off-Policy RL for Finetuning Behavior Cloning Policies
        54004, -- 2510.20150 Rank-GRPO: Training LLM-based Conversational Recommender Systems with
        54018, -- 2510.27545 EBT-Policy: Energy Unlocks Emergent Physical Reasoning Capabilities
        54660, -- 2512.07843 ThreadWeaver: Adaptive Threading for Efficient Parallel Reasoning in L
        55114, -- 2601.02427 NitroGen: An Open Foundation Model for Generalist Gaming Agents
        55180, -- 2601.04575 Scaling Behavior Cloning Improves Causal Reasoning: An Open Model for
        56113, -- 2602.04315 GeneralVLA: Generalizable Vision-Language-Action Models with Knowledge
        56244, -- 2602.19313 TOPReward: Token Probabilities as Hidden Zero-Shot Rewards for Robotic
        56417, -- 2602.24121 Planning from Observation and Interaction
        56956, -- 2603.15136 Safe Flow Q-Learning: Offline Safe Reinforcement Learning with Reachab
        56959, -- 2603.20538 Understanding Behavior Cloning with Action Quantization
        57474, -- 2604.13015 Learning Versatile Humanoid Manipulation with Touch Dreaming
        57744, -- 2604.15574 Why Fine-Tuning Encourages Hallucinations and How to Fix It
        58398, -- 2604.07774 RoboAgent: Chaining Basic Capabilities for Embodied Task Planning
        58597, -- 2604.02523 Tune to Learn: How Controller Gains Shape Robot Policy Learning
        59852, -- 2603.05296 Latent Policy Steering through One-Step Flow Policies
        59861, -- 2603.04949 TimeWarp: Evaluating Web Agents by Revisiting the Past
        60756, -- 2602.12215 LDA-1B: Scaling Latent Dynamics Action Model via Universal Embodied Da
        61630, -- 2602.00528 How Far Are LLMs from Professional Poker Players? Revisiting Game-Theo
        63499, -- 2512.17853 AnyTask: an Automated Task and Data Generation Framework for Advancing
        64155, -- 2512.03973 Guided Flow Policy: Learning from High-Value Actions in Offline Reinfo
        64263, -- 2512.01809 Much Ado About Noising: Dispelling the Myths of Generative Robotic Con
        65072, -- 2511.10110 Learning a Thousand Tasks in a Day
        65930, -- 2510.21090 Self-Rewarding PPO: Aligning Large Language Models with Demonstrations
        66200, -- 2510.16774 Learning to play: A Multimodal Agent for 3D Game-Play
        66439, -- 2510.12392 Improving Generative Behavior Cloning via Self-Guidance and Adaptive C
        66975, -- 2510.04246 ContextVLA: Vision-Language-Action Model with Amortized Multi-Frame Co
        67215, -- 2510.00739 TD-JEPA: Latent-predictive Representations for Zero-Shot Reinforcement
        67373, -- 2510.01272 Modeling Others' Minds as Code
        67390, -- 2509.25358 SARM: Stage-Aware Reward Modeling for Long Horizon Robot Manipulation
        70013, -- 2508.05941 Latent Policy Barrier: Learning Robust Visuomotor Policies by Staying
        70342, -- 2508.01600 CLASS: Contrastive Learning via Action Sequence Supervision for Robot
        71312, -- 2507.06710 Spatial-Temporal Aware Visuomotor Diffusion Policy Learning
        71517, -- 2507.01679 Blending Supervised and Reinforcement Fine-Tuning with Prefix Sampling
        73189, -- 2505.02833 TWIST: Teleoperated Whole-Body Imitation System
        74259, -- 2503.05833 Refined Policy Distillation: From VLA Generalists to RL Experts
        75357, -- 2412.18907 EC-Diffuser: Multi-Object Manipulation via Entity-Centric Behavior Gen
        75937, -- 2410.21257 One-Step Diffusion Policy: Fast Visuomotor Policies via Diffusion Dist
        76120, -- 2410.06473 GRAPPA: Generalizing and Adapting Robot Policies via Online Agentic Gu
        76883, -- 2406.18915 Manipulate-Anything: Automating Real-World Robots using Vision-Languag
        78428, -- 2310.01957 Driving with LLMs: Fusing Object-Level Vector Modality for Explainable
        79252, -- 2303.08135 Manipulate by Seeing: Creating Manipulation Controllers from Pre-Train
        80452, -- 2110.06169 Offline Reinforcement Learning with Implicit Q-Learning
        82980, -- 2605.05765 X-OmniClaw Technical Report: A Unified Mobile Agent for Multimodal Und
        84185, -- 2511.15200 VIRAL: Visual Sim-to-Real at Scale for Humanoid Loco-Manipulation
        85696, -- 2506.21427 Flow-Based Single-Step Completion for Efficient and Expressive Policy
        85956, -- 2509.16965 Preference Distillation via Value based Reinforcement Learning
        86730, -- 2505.17610 Learning Equilibria from Data: Provably Efficient Multi-Agent Imitatio
        86981, -- 2505.10881 Prior-Guided Diffusion Planning for Offline Reinforcement Learning
        87468, -- 2509.15155 Self-Improving Embodied Foundation Models
        87799, -- 2504.12540 UniPhys: Unified Planner and Controller with Diffusion for Flexible Ph
        88587, -- 2503.21383 Controlling Large Language Model with Latent Action
        89048, -- 2505.19923 Learning to Trust Bellman Updates: Selective State-Adaptive Regulariza
        89067, -- 2410.05026 Active Fine-Tuning of Multi-Task Policies
        89349, -- 2507.09041 Behavioral Exploration: Learning to Explore via In-Context Adaptation
        89607, -- 2502.02853 Rethinking Latent Redundancy in Behavior Cloning: An Information Bottl
        90442, -- 2412.05334 Closed-Loop Supervised Fine-Tuning of Tokenized Traffic Models
        91498, -- 2410.15910 Diverse Policies Recovering via Pointwise Mutual Information Weighted
        92345, -- 2410.05063 Control-oriented Clustering of Visual Latent Representation
        92391, -- 2411.07223 Grounding Video Models to Actions through Goal Conditioned Exploration
        92492, -- 2606.04433 Stateful Visual Encoders for Vision-Language Models
        92617, -- 2507.11662 Let's Think in Two Steps: Mitigating Agreement Bias in MLLMs with Self
        92801, -- 2602.01789 RFS: Reinforcement learning with Residual flow steering for dexterous
        92840, -- 2602.21020 Matching Multiple Experts: On the Exploitability of Multi-Agent Imitat
        92876, -- 2506.08460 MOBODY: Model-Based Off-Dynamics Offline Reinforcement Learning
        93126, -- 2506.10137 Self-Predictive Representations for Combinatorial Generalization in Be
        93176, -- 2509.26605 Fine-tuning Behavioral Cloning Policies with Preference‑Based Reinforc
        93182, -- 2602.18025 Cross-Embodiment Offline Reinforcement Learning for Heterogeneous Robo
        93917, -- 2506.07822 Accelerating Diffusion Planners in Offline RL via Reward-Aware Consist
        94069, -- 2509.23619 Reasoning Scaffolding: Distilling the Flow of Thought from LLMs
        94141, -- 2507.09061 Action Chunking and Data Augmentation Yield Exponential Improvements i
        94364, -- 2602.05051 ReFORM: Reflected Flows for On-support Offline RL via Noise Manipulati
        94843, -- 2510.09096 When a Robot is More Capable than a Human: Learning from Constrained D
        94870, -- 2510.06913 DecompGAIL: Learning Realistic Traffic Behaviors with Decomposed Multi
        95219, -- external Multi-Modal Affordance Planner with Temporal-Context Action Policy for
        95423, -- 2510.01388 Ventura: Adapting Image Diffusion Models for Unified Task Conditioned
        95561, -- external Reinforcement Learning for Stair Locomotion of a Wheeled Bipedal Robot
        95575, -- 2510.02268 Do You Know Where Your Camera Is? View-Invariant Policy Learning with
        95863, -- external Efficient Active Search Via Amortized Path-Integral Policies
        96127, -- 2510.18085 R2BC: Multi-Agent Imitation Learning from Single-Agent Demonstrations
        96142, -- 2510.03885 Seeing the Bigger Picture: 3D Latent Mapping for Mobile Manipulation P
        97008, -- 2502.15679 BOSS: Benchmark for Observation Space Shift in Long-Horizon Task
        97044, -- 2502.13406 Generative Predictive Control: Flow Matching Policies for Dynamic, Dif
        97209, -- 2409.14896 Built Different: Tactile Perception to Overcome Cross-Embodiment Capab
        97226, -- external Behavior Cloning-Enhanced Deep Reinforcement Learning for Robot Naviga
        97255, -- 2511.18140 Observer–Actor: Active Vision Imitation Learning with Sparse-View Gaus
        97269, -- 2603.27400 Rainbow-DemoRL: Combining Improvements in Demonstration-Augmented Rein
        97289, -- 2511.18617 AutoFocus-IL: VLM-Based Saliency Maps for Data-Efficient Visual Imitat
        97343, -- 2502.11375 Robot Deformable Object Manipulation Via NMPC-Generated Demonstrations
        97696, -- 2511.03077 WorldPlanner: Monte Carlo Tree Search and MPC with Action-Conditioned
        97708, -- 2512.02011 Learning Dexterous Manipulation Skills from Imperfect Simulations
        98129, -- 2606.11087 Test-Time Gradient Guidance of Flow Policies in Reinforcement Learning
        98225, -- 2605.03065 OGPO: Sample Efficient Full-Finetuning of Generative Control Policies
        98388, -- 2603.03818 Pretrained Vision-Language-Action Models are Surprisingly Resistant to
        98441, -- 2606.17043 Hierarchical Advantage Weighting for Online RL Fine-Tuning of VLAs fro
        99084, -- 2607.02466 Learning to Move Before Learning to Do: Task-Agnostic pretraining for
        101163, -- 2512.16911 Posterior Behavioral Cloning: Pretraining BC Policies for Efficient RL
        101195, -- 2606.07568 A Systematic Study of Behavioral Cloning for Scientific Data Annotatio
        101315, -- 2605.27095 Adversarial Dual On-Policy Distillation from Expressive Teacher
        101616, -- 2606.22056 Provably Efficient Policy-Reward Co-Pretraining for Adversarial Imitat
        101679, -- 2605.03357 Population-Aware Imitation Learning in Mean-field Games with Common No
        101863, -- 2601.21718 When Does Predictive Inverse Dynamics Outperform Behavior Cloning?
        101929, -- 2602.02762 On the Sample Efficiency of Inverse Dynamics Models for Semi-Supervise
        102339, -- 2510.02695 RAMAC: Multimodal Risk-Aware Offline Reinforcement Learning and the Ro
        102378, -- 2605.27877 SPAR: Support-Preserving Action Rectification
        102404, -- 2603.22713 Non-Adversarial Imitation Learning Provably Free of Compounding Errors
        102424, -- 2606.01151 Lagrangian Perturbation Diffusion Steering: Latent Reinforcement Learn
        103887, -- 2106.06860 A Minimalist Approach to Offline Reinforcement Learning
        104479, -- 2607.13429 Generalizable VLA Finetuning via Representation Anchoring and Language
        105987, -- 2605.27919 Frequency-Guided Action Diffusion via Sub-Frequency Manifold Traversal
        106982, -- 2512.19737 Simulation-Driven Railway Delay Prediction: An Imitation Learning Appr
        107333, -- 2505.20335 Language Model Distillation: A Temporal Difference Imitation Learning
        108322, -- 2511.14396 Continuous Vision-Language-Action Co-Learning with Semantic-Physical A
        108688, -- 2605.27762 PEAM: Parametric Embodied Agent Memory through Contrastive Internaliza
        108870, -- 2607.04978 Qantara: Bridge-Flow Training for Multi-Paradigm JEPA Control
        109039, -- 2406.16862 Dreamitate: Real-World Visuomotor Policy Learning via Video Generation
        109526, -- 2608.19891 EXIMO: VLM Guided Exploration of VLA Policies
        110361, -- 2408.01147 Astra: Efficient Transformer Architecture and Contrastive Dynamics Lea
        113760, -- 2608.23478 Act with Intent: Distilling Behavior Intent for Vision-Language-Action
        116995, -- 2402.07739 Task-Conditioned Adaptation of Visual Features in Multi-Task Policy Le
        117017, -- 2404.02176 Versatile Navigation Under Partial Observability via Value-guided Diff
        117168, -- external Feedback-Guided Autonomous Driving
        118085, -- 2604.02714 ExploreVLA: Dense World Modeling and Exploration for End-to-End Autono
        118098, -- 2607.01651 One Demonstration Is Enough for Real-World Robotic Reinforcement Learn
        122050, -- 2306.10014 Coaching a Teachable Student
        122405, -- 2609.32146 Playing to Par: Reinforcement Learning for Provably Optimal Quadrilate
        122472, -- 2605.22493 Understanding Multimodality in Generative Behavioral Cloning
        123007, -- 2606.03335 A GPU-Parallel Framework for Heterogeneous Multi-Task Reinforcement Le
        123030, -- 1904.08980 Exploring the Limitations of Behavior Cloning for Autonomous Driving
        123138, -- 2610.12818 LeWAM: End-to-End World and Action Modeling with JEPAs
        123358, -- 2606.04130 CLAW: Learning Continuous Latent Action World Models via Adversarial L
        123976, -- 2610.29997 DONIC: Generalist Dexterous Bimanual Tracking Control from Human Demon
        124064, -- 2610.25376 TILDE: Teacher-in-the-Loop Distillation from Embodied Foundation Model
        124521, -- external Online Imitation Learning for Stabilizing Vlasov--Poisson Plasmas
        124547, -- external What Probing Reveals about Autonomous Driving: Better Predictions Lead
        125030, -- external Deployment-Time Online Imitation Learning from Corrective Demonstratio
        125156, -- external Compose Your Oracles: Off Policy Improvement with Aggregated Guidance
        125249, -- external Understanding Multimodal Failure in Action-Chunking Behavioral Cloning
        125282, -- 2601.23010 Automatic Constraint Policy Optimization based on Continuous Constrain
        125937, -- 2605.08434 Failing Forward: Adaptive Failure-Informed Learning for Vision-Languag
        126105, -- external Drifting Field Policy: Wasserstein Gradient Flow on Policy Space for O
        126551, -- 2605.12000 Split the Differences, Pool the Rest: Provably Efficient Multi-Objecti
        126615, -- external Skill-Level Effects in Behavioral Cloning: When Low-Skill Data Improve
        126744, -- 2606.30923 Behavior Cloning is Not All You Need: The Optimality of On-Policy Dist
        127435, -- 2610.10857 Self-Supervised Keyframe Discovery for Horizon-Invariant Behavior Clon
        127892, -- external When Does Interaction Help? Representational Tradeoffs in Value-Based
        127945, -- external Spectral Representations for Provably Robust Offline Meta-Reinforcemen
        128048, -- 2605.09183 Learning When to Stop: Selective Imitation Learning Under Arbitrary Dy
        128098, -- 2607.04574 A Few Teacher Steps Go a Long Way: Cost-Efficient On-Policy Data Augme
        128489, -- external Few-shot Task Learning via Compositional Concept Inference
        128919, -- external VISTA: Support-Anchored Value Targeting for Fast Flow-Based Vision-Lan
        128926, -- external ForesightFlow: Self-Guided Flow Matching for Improving Vision-Language
        129173, -- external Ad-Hoc Teamwork from Human Demonstrations
        129378, -- external Implicit Goal Conditioning via Value Disaggregation
        129494, -- 2609.30391 From Weak Data to Strong Policy: Q-Targets Enable Provable In-Context
        129832, -- 2605.21139 Distill to Think, Foresee to Act: Cognitive-Physical Reinforcement Lea
        129886, -- external Jump Start Your Policy Learning with Lessons from 145,000 Training Run
        130015, -- 2605.15536 SkiP: When to Skip and When to Refine for Efficient Robot Manipulation
        130123, -- 2606.10517 LAFP: Preserving Latent Action Structure in Latent Policy Learning via
        130249, -- 2606.01098 Implicit Drifting Policy: One-Step Action Generation via Conditional E
        130641, -- external ASH: Agents that Self-Hone via Embodied Learning
        131375  -- 2610.32093 DiscoDemo: Discovering Efficient and Diverse Robot Demonstrations for
  );

DELETE FROM paper_method_exclusions x
USING behavior_cloning_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM behavior_cloning_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM behavior_cloning_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE behavior_cloning_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'behavior-cloning'
  AND p.id IN (
        32351, -- 2406.02959 Adversarial Moment-Matching Distillation of Large Language Models
        91233, -- 2503.13162 Efficient Imitation under Misspecification
        91297, -- 2411.07007 Non-Adversarial Inverse Reinforcement Learning via Successor Feature M
        93017  -- 2512.00536 Algorithmic Guarantees for Distilling Supervised and Offline RL Datase
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions behavior cloning only as a contrast, without using or comparing against it'
FROM behavior_cloning_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING behavior_cloning_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING behavior_cloning_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- inverse-reinforcement-learning: 71 links, 8 exclusions.
CREATE TEMP TABLE inverse_reinforcement_learning_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'inverse-reinforcement-learning'
  AND p.id IN (
        397, -- 1606.03476 Generative Adversarial Imitation Learning
        1833, -- 1902.07742 From Language to Goals: Inverse Reinforcement Learning for Vision-Base
        4028, -- 2008.06924 Inverse Reinforcement Learning with Natural Language Goals
        4228, -- 2009.14715 Learning Rewards from Linguistic Feedback
        8579, -- 2204.02515 Inferring Rewards from Language in Context
        9653, -- 2206.15469 Watch and Match: Supercharging Imitation with Regularized Optimal Tran
        9670, -- 2207.00461 Lifelong Inverse Reinforcement Learning
        9932, -- 2207.14299 Graph Inverse Reinforcement Learning from Diverse Videos
        12551, -- 2301.11270 Principled Reinforcement Learning with Human Feedback from Pairwise or
        14141, -- 2303.14623 Inverse Reinforcement Learning without Reinforcement Learning
        14950, -- 2304.12966 Towards Theoretical Understanding of Inverse Reinforcement Learning
        15747, -- 2305.11290 Massively Scalable Inverse Reinforcement Learning in Google Maps
        16760, -- 2306.00629 Identifiability and Generalizability in Constrained Inverse Reinforcem
        20022, -- 2309.00711 Learning Shared Safety Constraints from Multi-task Demonstrations
        20341, -- 2309.06553 Query-Dependent Prompt Evaluation and Optimization with Offline Invers
        21793, -- 2310.07433 Imitation Learning from Observation with Automatic Discount Scheduling
        28673, -- 2403.06854 Quantifying the Sensitivity of Inverse Reinforcement Learning to Missp
        29061, -- 2403.12017 Supervised Fine-Tuning as Inverse Reinforcement Learning
        31704, -- 2405.15624 Inverse-RLignment: Large Language Model Alignment from Demonstrations
        36504, -- 2409.01369 Imitating Language via Scalable Inverse Reinforcement Learning
        38094, -- 2410.06151 Quality Diversity Imitation Learning
        38611, -- 2410.12491 Insights from the Inverse: Reconstructing LLM Training Goals Through I
        39634, -- 2411.02623 Learning to Assist Humans without Inferring Rewards
        39682, -- 2411.03817 From Novice to Expert: LLM Agent Policy Optimization via Step-wise Rei
        39783, -- 2411.05273 Real-World Offline Reinforcement Learning from Vision Language Model F
        41566, -- 2412.10529 Solving the Inverse Alignment Problem for Efficient RLHF
        41611, -- 2412.11360 Visual IRL for Human-Like Robotic Manipulation
        45558, -- 2503.04679 Multi-Agent Inverse Q-Learning from Demonstrations
        51953, -- 2507.13158 Inverse Reinforcement Learning Meets Large Language Model Post-Trainin
        52734, -- 2509.09265 Harnessing Uncertainty: Entropy-Modulated Policy Gradients for Long-Ho
        56417, -- 2602.24121 Planning from Observation and Interaction
        57950, -- 2604.20074 Maximum Entropy Semi-Supervised Inverse Reinforcement Learning
        61246, -- 2602.04518 Learning the Value Systems of Agents with Preference-based and Inverse
        66109, -- 2510.18353 Ranking-based Preference Optimization for Diffusion Models from Implic
        67121, -- 2510.01857 Learning Reasoning Reward Models from Expert Demonstration via Inverse
        70069, -- 2508.06571 IRL-VLA: Training an Vision-Language-Action Policy via Reward World Mo
        71644, -- 2506.23235 Generalist Reward Models: Found Inside Large Language Models
        77801, -- 2402.11367 Multi Task Inverse Reinforcement Learning for Common Sense Reward
        79908, -- 2206.04873 Imitation Learning via Differentiable Physics
        81458, -- 2002.00444 Deep Reinforcement Learning for Autonomous Driving: A Survey
        82899, -- 2605.00623 Recovering Hidden Reward in Diffusion-Based Policies
        86814, -- 2411.15046 On Feasible Rewards in Multi-Agent Inverse Reinforcement Learning
        86937, -- 2509.22807 MTRec: Learning to Align with User Preferences via Mental Reward Model
        87722, -- 2507.12083 Foresight in Motion: Reinforcing Trajectory Prediction with Reward Heu
        88716, -- 2411.18825 ELEMENTAL: Interactive Learning from Demonstrations and Vision-Languag
        88944, -- 2506.21121 GoIRL: Graph-Oriented Inverse Reinforcement Learning for Multimodal Tr
        89063, -- 2409.17355 Learning Utilities from Demonstrations in Markov Decision Processes
        89386, -- 2501.12633 Inverse Reinforcement Learning with Switching Rewards and History Depe
        91233, -- 2503.13162 Efficient Imitation under Misspecification
        91297, -- 2411.07007 Non-Adversarial Inverse Reinforcement Learning via Successor Feature M
        93972, -- 2510.06096 The Alignment Auditor: A Bayesian Framework for Verifying and Refining
        94841, -- 2507.21533 Model Predictive Adversarial Imitation Learning for Planning from Obse
        95972, -- 2407.19902 A Differential Dynamic Programming Framework for Inverse Reinforcement
        96973, -- external Better Than Diverse Demonstrators: Reward Decomposition from Suboptima
        97652, -- 2509.13579 TreeIRL: Safe Urban Driving with Tree Search and Inverse Reinforcement
        97669, -- 2511.14565 Masked IRL: LLM-Guided Reward Disambiguation from Demonstrations and L
        99471, -- 2505.20110 Beyond the Proxy: Trajectory-Distilled Guidance for Offline GFlowNet T
        100467, -- 2605.11020 Trust Region Inverse Reinforcement Learning: Explicit Dual Ascent usin
        100541, -- 2510.03013 Distributional Inverse Reinforcement Learning
        101250, -- 2602.07832 rePIRL: Learn PRM with Inverse RL for LLM Reasoning
        101915, -- 2510.17059 Consistent Zero-Shot Imitation with Contrastive Goal Inference
        107055, -- 2504.05585 TW-CRL: Time-Weighted Contrastive Reward Learning for Efficient Invers
        107333, -- 2505.20335 Language Model Distillation: A Temporal Difference Imitation Learning
        124170, -- 2610.14041 A Geometric Perspective on Reward Function Updates in Inverse Reinforc
        125053, -- external Reward-Estimated Hypergradient for Bilevel Reinforcement Learning with
        127447, -- external DiReCL: Learning Differentiable Reward Code with Inverse Reinforcement
        128944, -- external Loop-Free Inverse Reinforcement Learning via Sequential Value Recovery
        129359, -- external Inverse Linear Bandits via Linear Programs
        130505, -- 2602.08689 Learning to Sample From Diffusion Models via Inverse Reinforcement Lea
        130622, -- external Offline Inverse Reinforcement Learning with Unified Diffusion Planning
        131179  -- 2509.21172 Inverse Reinforcement Learning with Just Classification and a Few Regr
  );

DELETE FROM paper_method_exclusions x
USING inverse_reinforcement_learning_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM inverse_reinforcement_learning_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM inverse_reinforcement_learning_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE inverse_reinforcement_learning_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'inverse-reinforcement-learning'
  AND p.id IN (
        15004, -- 2304.13995 Rotation and Translation Invariant Representation Learning with Implic
        20687, -- 2309.11489 Text2Reward: Reward Shaping with Language Models for Reinforcement Lea
        21686, -- 2310.06147 Reinforcement Learning in the Era of LLMs: What is Essential? What is
        26845, -- 2402.03310 V-IRL: Grounding Virtual Intelligence in Real Life
        43353, -- 2501.17161 SFT Memorizes, RL Generalizes: A Comparative Study of Foundation Model
        52293, -- 2508.06944 AMFT: Aligning LLM Reasoners by Meta-Learning the Optimal Imitation-Ex
        64141, -- 2512.04302 Towards better dense rewards in Reinforcement Learning Applications
        102148  -- 2602.00424 Open Materials Generation with Inference-Time Reinforcement Learning
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: IRL here means something else (V-IRL, IRL-INR, inference-time RL) or is only contrasted or listed in passing'
FROM inverse_reinforcement_learning_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING inverse_reinforcement_learning_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING inverse_reinforcement_learning_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- experience-replay: 153 links, 13 exclusions.
CREATE TEMP TABLE experience_replay_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'experience-replay'
  AND p.id IN (
        787, -- 1707.01495 Hindsight Experience Replay
        1731, -- 1901.00137 A Theoretical Analysis of Deep Q-Learning
        2259, -- 1906.05838 Goal-conditioned Imitation Learning
        3768, -- 2006.11321 AutoOD: Automated Outlier Detection via Curiosity-guided Search and Se
        5700, -- 2105.05155 TAG: Task-based Accumulated Gradients for Lifelong learning
        7444, -- 2112.04213 Convergence Results For Q-Learning With Experience Replay
        7625, -- 2112.15402 Relational Experience Replay: Continual Learning by Adaptively Tuning
        8654, -- 2204.04799 DualPrompt: Complementary Prompting for Rehearsal-free Continual Learn
        9214, -- 2205.13452 Continual evaluation for lifelong learning: Identifying the stability
        9892, -- 2207.12141 Live in the Moment: Learning Dynamics Model Adapted to Evolving Policy
        10762, -- 2210.06479 Real World Offline Reinforcement Learning with Realistic Data Source
        11216, -- 2211.02222 The Benefits of Model-Based Generalization in Reinforcement Learning
        12634, -- 2301.12507 Distilling Internet-Scale Vision-Language Models into Embodied Agents
        13477, -- 2303.02135 Eventual Discounting Temporal Logic Counterfactual Experience Replay
        13680, -- 2303.06614 Synthetic Experience Replay
        13862, -- 2303.09914 Rehearsal-Free Domain Continual Face Anti-Spoofing: Generalize More an
        14139, -- 2303.14595 Preserving Linear Separability in Continual Learning by Backward Featu
        14151, -- 2303.14771 Prototype-Sample Relation Distillation: Towards Replay-Free Continual
        15967, -- 2305.13622 Continual Learning with Strong Experience Replay
        15999, -- 2305.13804 OER: Offline Experience Replay for Continual Offline Reinforcement Lea
        16426, -- 2305.17400 Query-Policy Misalignment in Preference-Based Reinforcement Learning
        18242, -- 2307.07280 Replay to Remember: Continual Layer-Specific Fine-tuning for German Sp
        18287, -- 2307.08114 Tangent Model Composition for Ensembling and Continual Fine-tuning
        19517, -- 2308.10328 A Comprehensive Empirical Evaluation on Online Continual Learning
        19931, -- 2308.15827 Introducing Language Guidance in Prompt-based Continual Learning
        20213, -- 2309.04081 UER: A Heuristic Bias Addressing Approach for Online Continual Learnin
        20824, -- 2309.13285 Collision Avoidance and Navigation for a Quadrotor Swarm Using End-to-
        21375, -- 2310.02699 Continual Contrastive Spoken Language Understanding
        26993, -- 2402.04858 CodeIt: Self-Improving Language Models with Prioritized Hindsight Repl
        27007, -- 2402.05098 Improved off-policy training of diffusion samplers
        28178, -- 2402.18865 Analyzing and Reducing Catastrophic Forgetting in Parameter Efficient
        28533, -- 2403.04746 LLMs in the Imaginarium: Tool Learning through Simulated Trial and Err
        30211, -- 2404.07470 Scalable Language Model with Generalized Continual Learning
        30286, -- 2404.08513 Adversarial Imitation Learning via Boosting
        30600, -- 2404.13148 BACS: Background Aware Continual Semantic Segmentation
        36045, -- 2408.11052 Accelerating Goal-Conditioned RL Algorithms and Research
        36953, -- 2409.10643 CaBaGe: Data-Free Model Extraction using ClAss BAlanced Generator Ense
        38590, -- 2410.12236 Enhancing LLM Agents for Code Generation with Possibility and Pass-rat
        38609, -- 2410.12481 SAC-GLAM: Improving Online RL for LLM agents with Soft Actor-Critic an
        38814, -- 2410.14606 Streaming Deep Reinforcement Learning Finally Works
        40346, -- 2411.15370 Deep Policy Gradient Methods Without Batch Updates, Target Networks, o
        41576, -- 2412.10713 RAT: Adversarial Attacks on Deep Reinforcement Agents for Targeted Beh
        45400, -- 2503.02269 Experience Replay with Random Reshuffling
        46671, -- 2503.18929 Trajectory Balance with Asynchrony: Decoupling Exploration and Learnin
        48146, -- 2504.18471 Action Flow Matching for Continual Robot Learning
        49390, -- 2505.16282 ARPO:End-to-End Policy Optimization for GUI Agents with Experience Rep
        49524, -- 2505.17496 Analyzing Mitigation Strategies for Catastrophic Forgetting in End-to-
        50735, -- 2506.06698 Contextual Experience Replay for Self-Improvement of Language Agents
        50918, -- 2506.09340 RePO: Replay-Enhanced Policy Optimization
        51813, -- 2507.07451 RLEP: Reinforcement Learning with Experience Replay for LLM Reasoning
        52980, -- 2509.22601 Learn the Ropes, Then Trust the Wins: Self-imitation with Progressive
        53097, -- 2509.25454 DeepSearch: Overcome the Bottleneck of Reinforcement Learning with Ver
        53265, -- 2509.24107 Fathom-DeepResearch: Unlocking Long Horizon Information Retrieval and
        53889, -- 2510.21978 Beyond Reasoning Gains: Mitigating General Capabilities Forgetting in
        54079, -- 2511.03773 Scaling Agent Learning via Experience Synthesis
        54470, -- 2512.01945 Agentic Policy Optimization via Instruction-Policy Co-Evolution
        56460, -- 2603.01655 Transform-Invariant Generative Ray Path Sampling for Efficient Radio P
        56746, -- 2603.15611 Code-A1: Adversarial Evolving of Code LLM and Test LLM via Reinforceme
        56986, -- 2603.17198 Abstraction as a Memory-Efficient Inductive Bias for Continual Learnin
        57419, -- 2604.08706 Efficient RL Training for LLMs with Experience Replay
        58761, -- 2603.28611 LACE: Loss-Adaptive Capacity Expansion for Continual Learning
        59207, -- 2603.17461 AR-CoPO: Align Autoregressive Video Generation with Contrastive Policy
        60116, -- 2603.00624 IDER: IDempotent Experience Replay for Reliable Continual Learning
        60447, -- 2602.18628 Non-Interfering Weight Fields: Treating Model Parameters as a Continuo
        60693, -- 2602.13440 Learning on the Fly: Replay-Based Continual Object Perception for Indo
        61528, -- 2602.02597 ContextEvolve: Multi-Agent Context Compression for Systems Code Optimi
        62483, -- 2601.10589 Be Your Own Red Teamer: Safety Alignment via Self-Play and Reflective
        63846, -- 2512.10477 Symphony: A Heuristic Normalized Calibrated Advantage Actor and Critic
        65444, -- 2501.15971 REINFORCE-ING Chemical Language Models for Drug Discovery
        66878, -- 2510.05921 Prompt reinforcing for long-term planning of large language models
        67330, -- 2509.25958 RoRecomp: Enhancing Reasoning Efficiency via Rollout Response Recompos
        67398, -- 2509.25171 TR2-D2: Tree Search Guided Trajectory-Aware Fine-Tuning for Discrete D
        67613, -- 2509.23232 SPEC-RL: Accelerating On-Policy Reinforcement Learning via Speculative
        68408, -- 2509.11414 Continually Adding New Languages to Multilingual Language Models
        70040, -- 2508.05387 Echo: Decoupling Inference and Training for Large-Scale RL Alignment o
        70045, -- 2508.05310 ASkDAgger: Active Skill-level Data Aggregation for Interactive Imitati
        70321, -- 2508.01908 Revisiting Replay and Gradient Alignment for Continual Pre-Training of
        71303, -- 2507.06822 Hierarchical Reinforcement Learning for Articulated Tool Manipulation
        71690, -- 2506.22200 EFRame: Deeper Reasoning via Exploration-Filter-Replay Reinforcement L
        72240, -- 2506.05316 Improving Data Efficiency for LLM Reinforcement Fine-tuning Through Di
        74490, -- 2502.17813 Safe Multi-Agent Navigation guided by Goal-Conditioned Safe Reinforcem
        75148, -- 2501.11140 CLOFAI: A Dataset of Real And Fake Image Classification Tasks for Cont
        76802, -- 2407.04811 Simplifying Deep Temporal Difference Learning
        77142, -- 2405.19961 Transition Path Sampling with Improved Off-Policy Training of Diffusio
        77880, -- 2401.16650 Augmenting Replay in World Models for Continual Reinforcement Learning
        80417, -- 2111.02156 Continual Adaptation of Semantic Segmentation using Complementary 2D-3
        82423, -- 1511.05952 Prioritized Experience Replay
        83259, -- 2605.11711 Debiased Model-based Representations for Sample-efficient Continuous C
        84183, -- 2511.15164 Multimodal Continual Instruction Tuning with Dynamic Gradient Guidance
        84849, -- 2603.10929 Lifelong Imitation Learning with Multimodal Latent Replay and Incremen
        85775, -- 2506.12811 Flow-Based Policy for Online Reinforcement Learning
        85895, -- 2507.11269 Turning Sand to Gold: Recycling Data to Bridge On-Policy and Off-Polic
        87312, -- 2507.07712 Class-wise Balancing Data Replay for Federated Class-Incremental Learn
        89058, -- 2406.09935 Predicting the Susceptibility of Examples to Catastrophic Forgetting
        89098, -- 2506.13672 The Courage to Stop: Overcoming Sunk Cost Fallacy in Deep Reinforcemen
        89209, -- 2507.02712 A Forget-and-Grow Strategy for Deep Reinforcement Learning Scaling in
        89605, -- 2505.19680 Cut out and Replay: A Simple yet Versatile Strategy for Multi-Label On
        89833, -- 2506.02522 Think Twice, Act Once: A Co-Evolution Framework of LLM and RL for Larg
        90612, -- 2504.00420 Think Small, Act Big: Primitive Prompt Learning for Lifelong Robot Man
        91075, -- 2410.18082 Prioritized Generative Replay
        93227, -- 2506.21039 Strict Subgoal Execution: Reliable Long-Horizon Planning in Hierarchic
        93264, -- 2506.18482 Reliability-Adjusted Prioritized Experience Replay
        94116, -- 2512.04559 Diffusion Fine-Tuning via Reparameterized Policy Gradient of the Soft
        94397, -- 2512.07400 Heads collapse, features stay: Why Replay needs big buffers
        94680, -- 2509.03810 Online time series prediction using feature adjustment
        94820, -- 2604.01913 The Rank and Gradient Lost in Non-stationarity: Sample Weight Decay fo
        94979, -- 2509.21016 RL Grokking Recipe: How Does RL Unlock and Transfer New Algorithms in
        96320, -- 2603.08531 CRED: Counterfactual Reasoning and Environment Design for Active Prefe
        96748, -- 2511.06202 ExpReS-VLA: Specializing Vision-Language-Action Models through Experie
        97063, -- external Demonstration-Augmented Deep Reinforcement Learning with Mixed Reality
        97403, -- external From Simulation to Deployment: Curriculum-Based Domain Adaptation for
        97704, -- 2604.02911 Learning Task-Invariant Properties Via Dreamer: Enabling Efficient Pol
        98225, -- 2605.03065 OGPO: Sample Efficient Full-Finetuning of Generative Control Policies
        98388, -- 2603.03818 Pretrained Vision-Language-Action Models are Surprisingly Resistant to
        98468, -- 2606.18216 Zone of Proximal Policy Optimization: Teacher in Prompts, Not Gradient
        98519, -- 2606.19047 RODS: Reward-Driven Online Data Synthesis for Multi-Turn Tool-Use Agen
        100339, -- 2603.03955 GIPO: Gaussian Importance Sampling Policy Optimization
        100395, -- 2510.11711 Reinforced Sequential Monte Carlo for Amortised Sampling
        101184, -- 2602.09396 Squeezing More from the Stream : Learning Representation Online for St
        101501, -- 2509.19771 Frictional Q-Learning
        102754, -- 2505.16067 How Memory Management Impacts LLM Agents: An Empirical Study of Experi
        102961, -- 2512.11013 PIAST: Rapid Prompting with In-context Augmentation for Scarce Trainin
        104087, -- 2406.01646 iKAN: Global Incremental Learning with KAN for Human Activity Recognit
        106202, -- 2411.16769 Red-Teaming Text-to-Image Models via In-Context Experience Replay and
        106977, -- 2502.00520 Variance Reduction via Resampling and Experience Replay
        107034, -- 2602.06227 Do It for HER: First-Order Temporal Logic Reward Specification in Rein
        107589, -- 2512.19355 First-Order Representation Languages for Goal-Conditioned RL
        107938, -- 2511.09392 Potent but Stealthy: Rethink Profile Pollution Against Sequential Reco
        112759, -- 2409.01128 Diffusion-Driven Data Replay: A Novel Approach to Combat Forgetting in
        113689, -- external Information Bottleneck Based Data Correction in Continual Learning
        115363, -- 2406.17575 Toward Universal Medical Image Registration via Sharpness-Aware Meta-C
        115904, -- 2406.07876 Small Scale Data-Free Knowledge Distillation
        116070, -- external Uncertainty-Guided Never-Ending Learning to Drive
        118977, -- 2605.24251 Rethinking Continual Anomaly Detection on the Edge: Benchmarking Under
        119604, -- 2608.26147 CARE: Causally-Aligned Reasoning Exploration for Medical Large Languag
        120831, -- external EE-RL: Vision Language Guided Reinforcement Learning with Explorer and
        121065, -- 2602.20871 GeCo-SRT: Geometry-aware Continual Adaptation for Cross-Task Sim-to-Re
        124403, -- external Adaptive Stepsizes for Eligibility Traces in Deep Reinforcement Learni
        124709, -- external Problem-Dependent Dynamic Regret over a Predictor Class with One-Gradi
        124750, -- external Replay-buffer engineering for noise-robust quantum circuit optimizatio
        124897, -- external DyJR: Preserving Local Policy Plasticity in Reinforcement Learning wit
        124966, -- external STABLE: A Continual Learning Optimizer with Adaptive Drift Control
        125202, -- external Efficient Gradient-Aware Asynchronous Reinforcement Learning for LLM P
        125377, -- 2605.20878 CIG: Exploration via Conditional Information Gain
        126304, -- 2605.03660 Stage Light is Sequence$^2$: Multi-Light Control via Imitation Learnin
        127104, -- external Boosting Off-Policy RLVR with Data-Centric Replay
        127414, -- 2610.02440 Bandits via Additive Quantized Representations
        127856, -- external A Surrogate Perspective on Convergence of Fixed-Target DQN
        128036, -- 2610.15888 Variance-Optimal State Resampling for Reinforcement Learning with Veri
        128797, -- external Mitigating Compounding Errors in Online Reinforcement Learning via Opt
        128872, -- external From Anti-Forgetting to Fast Adaptation: Continual Reinforcement Learn
        130635, -- 2602.01629 AdaptNC: Adaptive Nonconformity Scores for Conformal Prediction under
        130829  -- 2605.07775 POETS: Uncertainty-Aware LLM Optimization via Compute-Efficient Policy
  );

DELETE FROM paper_method_exclusions x
USING experience_replay_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM experience_replay_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM experience_replay_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE experience_replay_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'experience-replay'
  AND p.id IN (
        16574, -- 2305.18806 Prediction Error-based Classification for Class-Incremental Learning
        21242, -- 2310.01365 Elephant Neural Networks: Born to Be a Continual Learner
        61149, -- 2602.05832 UI-Mem: Self-Evolving Experience Memory for Online Reinforcement Learn
        72116, -- 2506.08255 SHIELD: Secure Hypernetworks for Incremental Expansion Learning Defens
        82276, -- 1702.03118 Sigmoid-Weighted Linear Units for Neural Network Function Approximatio
        91660, -- 2503.00677 Advancing Prompt-Based Methods for Replay-Independent General Continua
        93296, -- 2510.21175 Memory-Free Continual Learning with Null Space Adaptation for Zero-Sho
        94823, -- 2507.11019 Relative Entropy Pathwise Policy Optimization
        102278, -- 2601.22274 Server-Proximal Aggregation for Federated Domain-Incremental Learning
        107879, -- 2511.11676 Learning with Preserving for Continual Multitask Learning
        113525, -- 2407.13338 Learn to Memorize and to Forget: A Continual Learning Perspective of D
        116942, -- 2312.00598 Learning from One Continuous Video Stream
        128535  -- 2605.13554 Self-Supervised On-Policy Reinforcement Learning via Contrastive Proxi
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions experience replay or replay buffers only to say the method does without them'
FROM experience_replay_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING experience_replay_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING experience_replay_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- reward-shaping: 183 links, 14 exclusions.
CREATE TEMP TABLE reward_shaping_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'reward-shaping'
  AND p.id IN (
        1873, -- 1903.02020 Using Natural Language for Reward Shaping in Reinforcement Learning
        2976, -- 2001.00127 Reinforcement Learning with Goal-Distance Gradient
        3835, -- 2006.16785 Lipschitzness Is All You Need To Tame Off-policy Generative Adversaria
        5171, -- 2103.05825 ELLA: Exploration through Learned Language Abstraction
        8740, -- 2204.07615 TabNAS: Rejection Sampling for Neural Architecture Search on Tabular D
        9546, -- 2206.09674 EAGER: Asking and Answering Questions for Automatic Reward Shaping in
        10294, -- 2209.07288 Optimistic Curiosity Exploration and Conservative Exploitation with Li
        11018, -- 2210.13153 Reachability-Aware Laplacian Representation in Reinforcement Learning
        12528, -- 2301.10886 Automatic Intrinsic Reward Shaping for Exploration in Deep Reinforceme
        13078, -- 2302.06692 Guiding Pretraining in Reinforcement Learning with Large Language Mode
        20687, -- 2309.11489 Text2Reward: Reward Shaping with Language Models for Reinforcement Lea
        20753, -- 2309.12482 State2Explanation: Concept-Based Explanations to Benefit Agent Learnin
        21358, -- 2310.02456 Learning Optimal Advantage from Preferences and Mistaking it for Rewar
        21909, -- 2310.08581 Universal Visual Decomposer: Long-Horizon Manipulation Made Easy
        22086, -- 2310.10833 Proper Laplacian Representation Learning
        22722, -- 2310.19007 Behavior Alignment via Reward Function Optimization
        24550, -- 2312.05674 Position control of an acoustic cavitation bubble by reinforcement lea
        26589, -- 2402.00782 Dense Reward for Free in Reinforcement Learning from Human Feedback
        29123, -- 2403.12835 AnySkill: Learning Open-Vocabulary Physical Skill for Interactive Agen
        37082, -- 2409.12798 Assessing the Zero-Shot Capabilities of LLMs for Action Evaluation in
        37648, -- 2410.01458 From Reward Shaping to Q-Shaping: Achieving Unbiased Learning with LLM
        38229, -- 2410.07745 StepTool: A Step-grained Reinforcement Learning Framework for Tool Lea
        40116, -- 2411.11681 PSPO*: An Effective Process-supervised Policy Optimization for Reasoni
        41846, -- 2412.14135 Scaling of Search and Learning: A Roadmap to Reproduce o1 from Reinfor
        43092, -- 2501.12627 Deep Reinforcement Learning with Hybrid Intrinsic Reward Model
        43705, -- 2502.03373 Demystifying Long Chain-of-Thought Reasoning in LLMs
        44208, -- 2502.10325 Process Reward Models for LLM Agents: Practical Framework and Directio
        45039, -- 2502.18770 Reward Shaping to Mitigate Reward Hacking in RLHF
        46903, -- 2503.21949 Reward Design for Reinforcement Learning Agents
        48070, -- 2504.16272 Learning Explainable Dense Reward Shapes via Bayesian Optimization
        48126, -- 2504.17838 CaRL: Learning Scalable Planning Policies with Simple Rewards
        48805, -- 2505.10832 Learning When to Think: Shaping Adaptive Reasoning in R1-Style Models
        49308, -- 2505.15612 Learn to Reason Efficiently with Adaptive Length-based Reward Shaping
        49323, -- 2505.15776 ConvSearch-R1: Enhancing Query Reformulation for Conversational Search
        49600, -- 2505.18298 Thinking Fast and Right: Balancing Accuracy and Reasoning Length with
        51562, -- 2506.22832 Listener-Rewarded Thinking in VLMs for Image Preferences
        51787, -- 2507.06825 Artificial Generals Intelligence: Mastering Generals.io with Reinforce
        52076, -- 2507.20187 Diversity-Enhanced Reasoning for Subjective Questions
        52527, -- 2508.18773 ThinkDial: An Open Recipe for Controlling Reasoning Effort in Large La
        52793, -- 2509.21320 SciReasoner: Laying the Scientific Reasoning Ground Across Disciplines
        52810, -- 2509.19736 UserRL: Training Interactive User-Centric Agent via Reinforcement Lear
        53264, -- 2510.06217 TaTToo: Tool-Grounded Thinking PRM for Test-Time Scaling in Tabular Re
        53456, -- 2510.10201 RLFR: Extending Reinforcement Learning for LLMs with Flow Environment
        53462, -- 2510.11701 Demystifying Reinforcement Learning in Agentic Reasoning
        53512, -- 2510.12693 ERA: Transforming VLMs into Embodied Agents via Embodied Prior Learnin
        54180, -- 2511.10507 Rubric-Based Benchmarking and Reinforcement Learning for Advancing LLM
        55026, -- 2512.23703 Robo-Dopamine: General Process Reward Modeling for High-Precision Robo
        55079, -- 2512.22955 Diversity or Precision? A Deep Dive into Next Token Prediction
        55477, -- 2601.16276 GameTalk: Training LLMs for Strategic Conversation
        55930, -- 2602.06445 ECO: Energy-Constrained Optimization with Reinforcement Learning for H
        56151, -- 2602.10458 Found-RL: foundation model-enhanced reinforcement learning for autonom
        56279, -- 2602.20945 The Art of Efficient Reasoning: Data, Reward, and Optimization
        56469, -- 2603.04257 Memex(RL): Scaling Long-Horizon LLM Agents via Indexed Experience Memo
        56557, -- 2603.03825 From Narrow to Panoramic Vision: Attention-Guided Cold-Start Reshapes
        56953, -- 2603.21972 Demystifying Reinforcement Learning for Long-Horizon Tool-Using Agents
        57402, -- 2604.11297 The Past Is Not Past: Memory-Enhanced Dynamic Reward Shaping
        57482, -- 2604.10812 PokeRL: Reinforcement Learning for Pokemon Red
        58160, -- 2604.14564 MARS^2: Scaling Multi-Agent Tree Search via Reinforcement Learning for
        59587, -- 2603.22293 TIPS: Turn-Level Information-Potential Reward Shaping for Search-Augme
        60002, -- 2510.02692 Fine-Tuning Diffusion Models via Intermediate Distribution Shaping
        60242, -- 2602.22576 Search-P1: Path-Centric Reward Shaping for Stable and Efficient Agenti
        60313, -- 2602.21158 SELAUR: Self Evolving LLM Agent via Uncertainty-aware Rewards
        60426, -- 2602.19049 IAPO: Information-Aware Policy Optimization for Token-Efficient Reason
        60630, -- 2602.14468 LACONIC: Length-Aware Constrained Reinforcement Learning for LLM
        61227, -- 2602.17684 CodeScaler: Scaling Code LLM Training and Test-Time Inference via Exec
        61266, -- 2602.04265 Thickening-to-Thinning: Reward Shaping via Human-Inspired Learning Dyn
        61600, -- 2602.00760 APR: Penalizing Structural Redundancy in Large Reasoning Models via An
        61651, -- 2602.00401 ZEST: Zero-shot Embodied Skill Transfer for Athletic Robot Control
        61687, -- 2601.23058 From Absolute to Relative: Rethinking Reward Shaping in Group-Based Re
        61704, -- 2601.22803 CVeDRL: An Efficient Code Verifier via Difficulty-aware Reinforcement
        61793, -- 2601.21912 ProRAG: Process-Supervised Reinforcement Learning for Retrieval-Augmen
        62642, -- 2601.07149 Rewarding Creativity: A Human-Aligned Generative Reward Model for Rein
        62665, -- 2503.04472 DAST: Difficulty-Adaptive Slow-Thinking for Large Reasoning Models
        63316, -- 2512.21540 Leash: Adaptive Length Penalty and Reward Shaping for Efficient Large
        63394, -- 2512.20312 TableGPT-R1: Advancing Tabular Reasoning Through Reinforcement Learnin
        63411, -- 2512.20061 Scaling Reinforcement Learning for Content Moderation with Large Langu
        63647, -- 2512.14465 Context-Picker: Dynamic context selection using multi-stage reinforcem
        63984, -- 2512.07478 Enhancing Agentic RL with Progressive Reward Shaping and Value-based S
        64035, -- 2512.06653 LightSearcher: Efficient DeepSearch via Experiential Memory
        64389, -- 2511.23473 ThetaEvolve: Test-time Learning on Open Problems
        64406, -- 2511.23031 From Illusion to Intention: Visual Rationale Learning for Vision-Langu
        64728, -- 2511.17373 Agility Meets Stability: Versatile Humanoid Control with Heterogeneous
        64860, -- 2511.14846 Empowering Multi-Turn Tool-Integrated Reasoning with Group Turn Policy
        65352, -- 2511.04131 BFM-Zero: A Promptable Behavioral Foundation Model for Humanoid Contro
        65444, -- 2501.15971 REINFORCE-ING Chemical Language Models for Drug Discovery
        65620, -- 2510.26519 Think Outside the Policy: In-Context Steered Policy Optimization
        66118, -- 2510.18263 From Competition to Synergy: Unlocking Reinforcement Learning for Subj
        66135, -- 2510.18072 Fine-tuning Flow Matching Generative Models with Intermediate Feedback
        67284, -- 2509.26601 MENLO: From Preferences to Proficiency -- Evaluating and Modeling Nati
        67307, -- 2509.26209 Diversity-Incentivized Exploration for Versatile Reasoning
        67353, -- 2509.25779 Planner-R1: Reward Shaping Enables Efficient Agentic RL with Smaller L
        67433, -- 2509.24923 When Greedy Wins: Emergent Exploitation Bias in Meta-Bandit LLM Traini
        67437, -- 2509.24892 JuggleRL: Mastering Ball Juggling with a Quadrotor via Deep Reinforcem
        68316, -- 2509.13081 Shaping Explanations: Semantic Reward Modeling with Encoder-Only Trans
        69027, -- 2508.20900 OneRec-V2 Technical Report
        69161, -- 2508.18812 STARec: An Efficient Agent Framework for Recommender Systems via Auton
        69670, -- 2508.10548 Stabilizing Long-term Multi-turn Reinforcement Learning with Gated Rew
        70126, -- 2508.04349 GTPO and GRPO-S: Token and Sequence-Level Reward Shaping with Policy E
        70428, -- 2508.00410 Co-Reward: Self-supervised Reinforcement Learning for Large Language M
        72739, -- 2505.19196 Step-level Reward for Free in RL-based T2I Diffusion Model Fine-tuning
        75351, -- 2408.10215 Comprehensive Overview of Reward Engineering and Shaping in Advancing
        76160, -- 2410.03847 Enhancing Inverse Reinforcement Learning through Encoding Dynamic Info
        77102, -- 2406.01575 Contextual Bilevel Reinforcement Learning for Incentive Alignment
        78152, -- 2312.02976 SPOC: Imitating Shortest Paths in Simulation Enables Effective Navigat
        83464, -- 2605.09640 Overcoming Catastrophic Forgetting in Visual Continual Learning with R
        83807, -- 2605.26952 Efficient Agentic Reinforcement Learning with On-Policy Intrinsic Know
        85564, -- 2605.15951 From Failure to Feedback: Group Revision Unlocks Hard Cases in Object-
        85956, -- 2509.16965 Preference Distillation via Value based Reinforcement Learning
        86188, -- 2506.16396 GoalLadder: Incremental Goal Discovery with Vision-Language Models
        86507, -- 2505.16217 Reward-Aware Proto-Representations in Reinforcement Learning
        86571, -- 2504.04675 HYPRL: Reinforcement Learning of Control Policies for Hyperproperties
        86615, -- 2505.20218 Fine-grained List-wise Alignment for Generative Medication Recommendat
        86951, -- 2408.10858 Centralized Reward Agent for Knowledge Sharing and Transfer in Multi-T
        87080, -- 2505.13925 Time Reversal Symmetry for Efficient Robotic Manipulations in Deep Rei
        87468, -- 2509.15155 Self-Improving Embodied Foundation Models
        88127, -- 2508.11049 GenFlowRL: Shaping Rewards with Generative Object-Centric Flow in Visu
        88673, -- 2501.18858 BRiTE: Bootstrapping Reinforced Thinking Process to Enhance Language M
        88850, -- 2505.11478 Automatic Reward Shaping from Confounded Offline Data
        89363, -- 2505.12611 Action-Dependent Optimality-Preserving Reward Shaping
        89833, -- 2506.02522 Think Twice, Act Once: A Co-Evolution Framework of LLM and RL for Larg
        89860, -- 2505.06744 LineFlow: A Framework to Learn Active Control of Production Lines
        91187, -- 2410.13837 ORSO: Accelerating Reward Design via Online Reward Selection and Polic
        91517, -- 2409.05358 BAMDP Shaping: a Unified Framework for Intrinsic Motivation and Reward
        91635, -- 2408.03029 Highly Efficient Self-Adaptive Reward Shaping for Reinforcement Learni
        92572, -- 2606.03965 Agentic Chain-of-Thought Steering for Efficient and Controllable LLM R
        92861, -- 2604.20627 Occupancy Reward Shaping: Improving Credit Assignment for Offline Goal
        92981, -- 2506.10085 VITA: Zero-Shot Value Functions via Test-Time Adaptation of Vision–Lan
        93946, -- 2603.01694 MVR: Multi-view Video Reward Shaping for Reinforcement Learning
        94472, -- 2510.18060 SPACeR: Self-Play Anchoring with Centralized Reference Models
        94752, -- 2512.16917 Generative Adversarial Reasoner: Enhancing LLM Reasoning with Adversar
        95403, -- 2511.12751 A Case Study on LLM-Guided Reinforcement Learning for Decentralized Au
        96049, -- 2508.09354 CLF-RL: Control Lyapunov Function Guided Reinforcement Learning
        96123, -- 2502.00835 CAIMAN: Causal Action Influence Detection for Sample-Efficient Loco-Ma
        96732, -- external SRPO: Self-Reflection Policy Optimization for Stable and Robust Autono
        96919, -- 2605.24449 Vision-Guided Outdoor Flight and Obstacle Evasion Via Reinforcement Le
        97214, -- 2509.18466 RL-Augmented Adaptive Model Predictive Control for Bipedal Locomotion
        97677, -- 2509.14726 Beyond Reference Trajectories: A Waypoint-Based Model Predictive Path
        98062, -- 2606.07074 SlimSearcher: Training Efficiency-Aware Web Agents via Adaptive Reward
        99154, -- 2605.06078 Milestone-Guided Policy Learning for Long-Horizon Language Agents
        99845, -- 2602.02572 Reward Shaping for (Inference-Time) Alignment: A Stackelberg Game Pers
        99862, -- 2510.12334 Finite-time Convergence Analysis of Actor-Critic with Evolving Reward
        101162, -- 2603.03291 One Bias After Another: Mechanistic Reward Shaping and Persistent Bias
        101616, -- 2606.22056 Provably Efficient Policy-Reward Co-Pretraining for Adversarial Imitat
        102127, -- 2506.09276 Learning the Minimum Action Distance
        103187, -- 2604.07851 ReRec: Reasoning-Augmented LLM-based Recommendation Assistant via Rein
        106141, -- 2604.26355 Shorthand for Thought: Compressing LLM Reasoning via Entropy-Guided Su
        106651, -- 2509.16399 VORTEX: Aligning Task Utility and Human Preferences Through LLM-Guided
        107895, -- 2511.18958 Learning to Compress Graphs via Dual Agents for Consistent Topological
        109146, -- 2607.29211 Knowing When to Quit: Diagnosing and Training LLMs to Abort Futile Rea
        110629, -- external Reinforcement Learning for Large Language Models via Group Preference
        113885, -- 2609.02817 Cliff: Learning Process Rewards from the First Mistake
        113967, -- 2609.00444 Group Adaptive Clipping Policy Optimization
        118741, -- 2605.18603 Starve to Perceive: Taming Lazy Perception in VLMs with Constrained Vi
        120869, -- external CAD-Refiner: A Unified Framework for CAD Generation and Iterative Edit
        121624, -- external General Process Reward Modeling for Robotic Reinforcement Learning
        121660, -- external TableMix: Enhancing Multimodal Table Reasoning in MLLMs from a Data-Ce
        122018, -- 2609.19671 When2Think: Learning Difficulty-Aware Length Control for Efficient Hyb
        122964, -- 2610.12403 ViSkill: Reinforcing VLM Agents with Evolving Visual-Native Skills
        123277, -- 2610.18868 Tev: Scaling Long-Horizon Agentic Environments with Dense Progress Rew
        123941, -- 2610.16523 EAU: Environment-Agent-User Co-evolution for Training User-Centric Age
        124200, -- external VSPO: Vector-Steered Policy Optimization for Controllable Model Behavi
        124250, -- 2605.09287 PiCA: Pivot-Based Credit Assignment For Search Agentic Reinforcement L
        124379, -- external Behavior-Discriminative Reward Shaping for Reward-Robust Reinforcement
        124698, -- external Hearing the Unspoken: Simulator-Induced Asymmetric-View Policy Optimiz
        124792, -- external Multi-Stage Planning from Single-Stage Data: Reinforcement Learning He
        124909, -- external DP-EGGROLL: Centered Fitness-Vector Privatization for Backprop-Free Di
        125053, -- external Reward-Estimated Hypergradient for Bilevel Reinforcement Learning with
        125839, -- external CAFE: Causally-Guided Automated Feature Engineering with Multi-Agent R
        126035, -- external RAIL: Representation-Aligned Imitation Learning for Student-Compatible
        126175, -- 2601.22397 SAIR: Cost-Efficient Multi-Stage ML Pipeline Autoscaling via In-Contex
        126989, -- external PARI: Policy-Driven Active Residual Intervention for Weakly Supervised
        127532, -- external Imitation Dominates Reinforcement: Direct In-Context RL Is Closer to I
        127626, -- 2606.05464 Step-by-Step Optimization-like Reasoning in LLMs over Expanding Search
        127677, -- external Reward Shaping to Improve Language Model Query Generation
        128128, -- 2609.20548 Mitigating Retaliatory Algorithmic Collusion in Repeated Games
        128322, -- external Beyond the Dirac Delta: Mitigating Diversity Collapse in Reinforcement
        128548, -- 2605.05702 Knowledge-Graph Paths as Intermediate Supervision for Self-Evolving Se
        129407, -- external MaxIM: Maximally Informative Incremental Summarization via Reinforceme
        129679, -- external DiagSQL: A Diagnostic Validator for Text-to-SQL with Reward Allocation
        129781, -- external Temporal Behavior Trees for Reinforcement Learning: Specifications as
        130333, -- external A Subgoal-driven RL Framework for Improving Long-Horizon Web Agents
        130338, -- 2602.00403 DROGO: Default Representation Objective via Graph Optimization in Rein
        130463  -- 2602.04851 PDF-HR: Pose Distance Fields for Humanoid Robots
  );

DELETE FROM paper_method_exclusions x
USING reward_shaping_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM reward_shaping_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM reward_shaping_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE reward_shaping_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'reward-shaping'
  AND p.id IN (
        12219, -- 2212.12809 Understanding the Complexity Gains of Single-Task RL with a Curriculum
        21223, -- 2310.01207 Learn to Follow: Decentralized Lifelong Multi-agent Pathfinding via Pl
        47826, -- 2504.12609 Crossing the Human-Robot Embodiment Gap with Sim-to-Real RL using One
        49133, -- 2505.14157 Prior Prompt Engineering for Reinforcement Fine-Tuning
        49868, -- 2505.20315 Arctic-Text2SQL-R1: Simple Rewards, Strong Reasoning in Text-to-SQL
        62577, -- 2601.08731 Learning from Demonstrations via Capability-Aware Goal Sampling
        68341, -- 2509.12618 ActiveVLN: Towards Active Exploration via Multi-Turn RL in Vision-and-
        71338, -- 2507.06013 CogniSQL-R1-Zero: Lightweight Reinforced Reasoning for Efficient SQL G
        94165, -- 2602.11437 Distributionally Robust Cooperative Multi-agent Reinforcement Learning
        96471, -- 2601.16109 Efficiently Learning Robust Torque-Based Locomotion through Reinforcem
        116119, -- 2402.06559 Diffusion-ES: Gradient-free Planning with Diffusion for Autonomous and
        127186, -- external Hit Expansion via Localized Exploration of Synthesizable Chemical Spac
        128385, -- 2605.08323 The Reciprocity Gradient
        130641  -- external ASH: Agents that Self-Hone via Embodied Learning
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions reward shaping only to say the method does without it, or only in passing'
FROM reward_shaping_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING reward_shaping_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING reward_shaping_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- Hero image credits (images imported with import_entity_image.py).
UPDATE methods SET image_credit = '[Trust Region Policy Optimization](/paper/1502.05477)' WHERE slug = 'trpo';
UPDATE methods SET image_credit = '[Continuous control with deep reinforcement learning](/paper/1509.02971)' WHERE slug = 'ddpg';
UPDATE methods SET image_credit = '[Addressing Function Approximation Error in Actor-Critic Methods](/paper/1802.09477)' WHERE slug = 'td3';
UPDATE methods SET image_credit = '[Asynchronous Methods for Deep Reinforcement Learning](/paper/1602.01783)' WHERE slug = 'a3c';
UPDATE methods SET image_credit = '[End to End Learning for Self-Driving Cars](/paper/1604.07316)' WHERE slug = 'behavior-cloning';
