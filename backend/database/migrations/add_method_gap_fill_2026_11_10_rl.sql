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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'actor-critic', 'Actor-Critic', 'Actor-Critic',
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'a3c', 'A3C',
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'trpo', 'TRPO',
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'ddpg', 'DDPG',
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'td3', 'TD3',
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
        158, 200, 239, 611, 745, 804, 881, 892, 894, 955, 1021, 1620, 2184, 2551, 2708, 2830,
        3037, 3049, 3196, 3792, 3801, 4769, 4842, 4885, 6017, 6582, 8063, 8740, 9333, 9771, 9829, 10452,
        10531, 11015, 11394, 12132, 12534, 12698, 12795, 12820, 13144, 13309, 13540, 15073, 15835, 15939, 15998, 16123,
        16219, 16332, 16395, 16598, 16670, 16690, 16892, 16897, 17515, 17629, 18194, 18290, 18452, 18611, 18856, 18918,
        21132, 21289, 21373, 21381, 21509, 21777, 22297, 22675, 22824, 23036, 23298, 23315, 23741, 24550, 25759, 26249,
        26769, 27822, 28271, 30213, 30572, 30784, 30906, 33422, 33790, 34072, 34367, 34886, 35537, 36459, 37803, 38229,
        40346, 40697, 42277, 43564, 43624, 44329, 45668, 47234, 47733, 47790, 48220, 48235, 48637, 48956, 48966, 49049,
        49170, 49245, 49333, 49526, 49682, 49766, 50020, 50322, 50379, 50417, 50437, 51790, 51860, 52068, 52631, 52656,
        52734, 52783, 52792, 52973, 53077, 53179, 53207, 53248, 53281, 53382, 53418, 53457, 53473, 53489, 53516, 53548,
        53745, 53848, 53908, 54117, 54388, 54444, 54649, 54894, 55079, 55813, 55814, 55825, 55831, 56009, 56167, 56301,
        56506, 56629, 57495, 57543, 57583, 57779, 57974, 58383, 58546, 58566, 58775, 59105, 59106, 59393, 59473, 59507,
        59789, 59805, 59813, 59975, 60002, 60075, 60448, 60474, 60573, 60806, 60896, 61010, 61202, 61303, 61323, 61329,
        61399, 61528, 62022, 62240, 63185, 64262, 64392, 64983, 66719, 66731, 66858, 66980, 67020, 67195, 67207, 67383,
        67415, 67681, 67706, 67773, 68861, 69308, 69664, 70090, 70127, 70520, 70595, 70625, 71079, 71913, 73089, 73186,
        73873, 75093, 75546, 76486, 76998, 77102, 77594, 77814, 77976, 78704, 78963, 79235, 79358, 79493, 79996, 80400,
        80645, 80925, 81214, 81718, 81832, 82033, 82124, 82311, 82871, 82882, 82892, 82909, 82921, 82977, 82997, 83120,
        83182, 83424, 83582, 83773, 83779, 83781, 83843, 84195, 84580, 85087, 85193, 85721, 85727, 85963, 86356, 86415,
        86959, 87067, 87071, 87337, 87445, 88748, 88753, 88838, 88839, 89072, 89083, 89116, 89163, 89176, 89298, 89424,
        89436, 89480, 89770, 91266, 91297, 91584, 91932, 91990, 92106, 92155, 92430, 92466, 92543, 92606, 92926, 92930,
        93029, 93162, 93185, 93310, 93323, 93407, 93798, 93918, 93988, 94116, 94149, 94496, 94574, 94675, 94745, 94823,
        95101, 95982, 96152, 96210, 97145, 97226, 98187, 98225, 98467, 98468, 98519, 99031, 99055, 99275, 99559, 99587,
        99594, 99896, 99897, 99903, 100228, 100258, 100383, 100401, 100408, 100559, 100661, 100673, 100744, 100783, 100900, 100913,
        100919, 100951, 101009, 101193, 101241, 101388, 101618, 101658, 101687, 101726, 101732, 101733, 101923, 101936, 102148, 102185,
        102268, 102283, 102528, 102609, 103881, 104079, 104509, 106179, 106376, 106415, 106483, 106606, 106746, 106862, 107275, 107368,
        107394, 107670, 108031, 108937, 109492, 109676, 109714, 111059, 112238, 112399, 114026, 114255, 114359, 115694, 116475, 120420,
        121010, 121886, 122164, 122246, 122259, 122692, 122732, 122861, 122884, 123410, 123684, 124367, 124387, 124589, 124711, 124745,
        124756, 124761, 124930, 124951, 125074, 125156, 125310, 125424, 125484, 125874, 126151, 126560, 126589, 126637, 126965, 127090,
        127300, 127388, 127411, 127530, 127661, 127803, 128036, 128197, 128224, 128366, 128443, 128646, 128669, 128710, 128760, 128837,
        128978, 128982, 129045, 129070, 129122, 129135, 129200, 129250, 129381, 129428, 129600, 129717, 129748, 129880, 130027, 130279,
        130375, 130397, 130505, 130677, 130978, 130990, 131016, 131029, 131083, 131129, 131215, 131245, 131262
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
        5857, 6957, 10038, 78878, 82263, 108650, 129053
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
        239, 301, 395, 567, 745, 1128, 2985, 3809, 5976, 6281, 6726, 7753, 9050, 9155, 9829, 11233,
        12179, 12609, 12816, 12912, 13088, 13540, 15835, 16109, 16218, 16598, 16897, 17158, 17538, 18005, 18386, 19001,
        19370, 20889, 21064, 21101, 23315, 23642, 23694, 24550, 25041, 25797, 26594, 26856, 27042, 27809, 28209, 28360,
        30286, 30430, 31522, 34469, 34930, 35772, 36611, 37864, 38324, 38763, 40583, 42158, 42176, 42277, 44075, 44208,
        44891, 45907, 46382, 48458, 48492, 50696, 51123, 52236, 52325, 52631, 52840, 53401, 55797, 56101, 57009, 61329,
        61616, 61787, 62644, 63099, 63911, 64531, 64758, 66135, 66758, 68217, 69049, 69116, 69526, 70386, 70686, 71417,
        73499, 74276, 75546, 75671, 76451, 76737, 78963, 78967, 79013, 79113, 79340, 79755, 80142, 80565, 81009, 81214,
        81294, 81893, 83259, 83781, 85696, 85721, 85764, 86001, 86705, 86816, 87067, 87136, 87247, 87445, 88274, 88624,
        88753, 88754, 88793, 88955, 89109, 89163, 89194, 89663, 89675, 89734, 91528, 91791, 92007, 92290, 92390, 92743,
        92930, 93185, 93213, 93247, 93917, 94129, 94739, 94848, 95563, 96019, 96258, 96530, 96749, 96799, 96981, 97105,
        98264, 98534, 99459, 99790, 99862, 100086, 100401, 100771, 101218, 101238, 101274, 101923, 102138, 102339, 102355, 103878,
        103881, 103885, 103893, 103894, 106746, 107705, 108031, 108332, 110549, 114100, 114253, 119695, 120254, 121294, 121337, 122164,
        123322, 124872, 125509, 126027, 126055, 126153, 126387, 126668, 126788, 126927, 127090, 127449, 127682, 127752, 127933, 128406,
        128590, 128669, 129358, 129381, 129739, 130557, 130672, 130737, 130746, 131399
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
        98129
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
        301, 1021, 68773, 80603, 81294, 81893
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
        395, 569, 571, 597, 605, 656, 754, 759, 779, 784, 804, 847, 892, 896, 903, 960,
        988, 1018, 1037, 1040, 1086, 1124, 1128, 1134, 1145, 1201, 1216, 1257, 1289, 1385, 1393, 1508,
        1580, 1624, 1634, 1702, 1704, 1731, 1739, 1792, 2080, 2316, 2381, 2458, 2551, 2562, 2679, 2830,
        2892, 2930, 2936, 2985, 3039, 3277, 3358, 3435, 3565, 3599, 3709, 3774, 3779, 3809, 3873, 4026,
        4053, 4103, 4378, 4488, 4580, 4597, 4631, 5059, 5346, 5397, 5528, 5561, 5687, 5898, 5924, 6005,
        6067, 6076, 6201, 6281, 6433, 6511, 6772, 6781, 6808, 6822, 7107, 7108, 7378, 7403, 7428, 7476,
        7677, 7688, 7862, 7892, 7959, 8026, 8194, 8197, 8367, 8425, 8485, 9050, 9333, 9586, 9661, 9680,
        9805, 9944, 9973, 10330, 10417, 10445, 10452, 10531, 10719, 10994, 11015, 11287, 11440, 11937, 12204, 12443,
        12528, 12609, 12631, 12659, 12802, 12816, 13122, 13515, 13517, 13550, 13551, 14712, 15310, 15381, 15486, 15593,
        15956, 15998, 16278, 16316, 16420, 16513, 16586, 16598, 16754, 16921, 17039, 17158, 17370, 17395, 17647, 17728,
        17985, 18144, 18201, 18348, 18472, 18753, 18899, 18918, 19363, 19582, 19854, 20025, 20092, 21015, 21085, 21118,
        21132, 21148, 21261, 21351, 21376, 21381, 21713, 22165, 22470, 22661, 22805, 22818, 23076, 23298, 23463, 23690,
        24046, 25340, 25714, 25726, 25797, 25811, 25833, 26086, 26249, 26442, 26477, 26525, 26633, 26813, 26856, 27063,
        27316, 27417, 27498, 27606, 27655, 28086, 28212, 28377, 28487, 28638, 28722, 28792, 28875, 28907, 28938, 29590,
        29752, 29842, 29970, 30033, 30213, 30430, 30752, 30784, 31455, 31553, 31991, 32005, 32579, 33438, 33620, 33804,
        34362, 34469, 34886, 35207, 35424, 35537, 35664, 35795, 37179, 38498, 38547, 38663, 38814, 38887, 39085, 39487,
        39530, 40346, 40933, 42651, 42943, 43391, 43769, 43935, 45231, 46323, 46393, 46671, 47981, 48067, 48126, 48668,
        48955, 49444, 49611, 49624, 49628, 50020, 50192, 50417, 50852, 51543, 52325, 52954, 53917, 54289, 54574, 55115,
        55235, 55300, 55512, 56186, 57402, 57996, 59145, 60075, 60489, 60490, 60732, 61360, 61543, 62378, 62644, 63178,
        63624, 64452, 65149, 65444, 66495, 66590, 66829, 67420, 67873, 67973, 68189, 69049, 69192, 69526, 70038, 70217,
        70287, 70625, 70893, 71079, 71417, 71543, 71913, 72806, 73089, 73928, 74060, 74258, 74951, 75044, 75782, 76096,
        76451, 76506, 76802, 78152, 78157, 78704, 78963, 79228, 79318, 79434, 79444, 79580, 79632, 79727, 80142, 80235,
        80301, 80466, 80665, 80675, 80724, 80936, 81009, 81069, 81417, 81458, 81463, 81523, 81570, 81604, 81616, 81748,
        81806, 81820, 81859, 81925, 81955, 81956, 82071, 82222, 82238, 82263, 82276, 82297, 82380, 82382, 82919, 82991,
        83120, 83843, 84408, 85492, 86021, 86060, 86130, 86356, 86583, 86959, 87004, 87137, 87328, 87445, 87826, 88241,
        88370, 88754, 89019, 89069, 89096, 89104, 89300, 89591, 89663, 89770, 89857, 89860, 89921, 90781, 90951, 91265,
        91266, 91498, 91517, 91583, 91584, 91646, 91861, 92106, 92313, 92364, 92430, 92642, 92791, 92874, 92930, 93010,
        93034, 93042, 93196, 93550, 93643, 93765, 93770, 93988, 94476, 94766, 95024, 95324, 96654, 97165, 97344, 98111,
        98417, 99275, 99696, 99790, 99882, 99895, 99903, 100243, 100383, 101440, 101687, 101923, 102528, 102694, 103546, 103880,
        103881, 103886, 103894, 103943, 104308, 106234, 106483, 106654, 106975, 107477, 107959, 108031, 108393, 109503, 110549, 116589,
        117115, 121918, 122056, 122331, 122336, 123028, 123303, 125074, 125509, 126187, 127388, 127934, 128267, 128451, 128535, 128718,
        129111, 130829, 130990
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
        158, 741, 804, 3599, 12568, 21653, 22805, 24530, 26408, 26533, 51181, 52450, 58029, 59675, 66719, 67005,
        68844, 69219, 81417, 81832, 89096, 89436, 89770, 92660, 93078, 99536, 100744, 101376, 101719, 130490
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
        200, 239, 301, 397, 565, 569, 611, 754, 799, 812, 830, 903, 1021, 1037, 1040, 1109,
        1128, 1134, 1201, 1209, 1508, 1563, 1634, 1702, 1731, 1739, 1764, 2259, 2551, 2562, 2719, 2984,
        2985, 3058, 3146, 3186, 3277, 3437, 3518, 3565, 3608, 3779, 3835, 4028, 4488, 4567, 4580, 4597,
        4931, 4967, 5434, 5465, 5849, 5937, 5976, 6005, 6076, 6201, 6361, 6587, 6772, 6808, 6957, 7107,
        7227, 7677, 7945, 8164, 8283, 8602, 8822, 9083, 9465, 9525, 9534, 9892, 10294, 10307, 10531, 10539,
        10719, 10762, 10841, 11015, 11233, 11318, 11683, 12132, 12215, 12219, 12534, 12698, 12735, 12784, 12820, 12870,
        13157, 13275, 13551, 13556, 13826, 14914, 14994, 15092, 15310, 15338, 15517, 15750, 15922, 15939, 15998, 16341,
        16420, 16670, 16690, 16715, 16802, 16892, 16921, 17023, 17039, 17250, 17428, 17515, 17589, 17640, 18144, 18290,
        18348, 18602, 18611, 18918, 18961, 19681, 19854, 20139, 20341, 21063, 21118, 21132, 21373, 21457, 21506, 21686,
        21793, 21819, 22470, 22818, 23002, 23095, 23298, 23315, 23529, 23874, 24046, 24505, 24555, 24701, 25340, 25485,
        25582, 25833, 26038, 26045, 26090, 26091, 26119, 26249, 26813, 26835, 26913, 27065, 27246, 27655, 27809, 27822,
        28283, 28796, 28938, 29970, 30285, 30367, 30424, 30500, 30784, 30786, 31361, 31553, 31574, 32054, 33174, 33213,
        33597, 34434, 34891, 34893, 35124, 35357, 37463, 37673, 37728, 37737, 37803, 37966, 38498, 38814, 39085, 39326,
        39569, 39682, 39710, 41102, 41551, 42651, 42917, 43296, 43564, 45002, 45039, 45259, 45263, 45806, 45973, 46469,
        46949, 47063, 47096, 47370, 47784, 47981, 48067, 48189, 48681, 48882, 48887, 48955, 48958, 49149, 49444, 49526,
        49574, 49624, 49664, 49876, 50020, 50107, 50168, 50192, 50696, 50749, 51519, 51543, 51709, 51790, 52303, 52656,
        52709, 52710, 52726, 52746, 52917, 53033, 53105, 53109, 53135, 53167, 53169, 53231, 53266, 53473, 53812, 53895,
        54031, 54079, 54128, 54174, 54394, 54504, 54606, 54726, 54856, 54931, 55337, 55443, 55542, 55554, 55614, 55767,
        55832, 55839, 55931, 56009, 56057, 56167, 56222, 56361, 56376, 56451, 56522, 56874, 56902, 56918, 56931, 56939,
        57199, 57495, 57574, 57996, 58213, 58398, 59105, 59106, 59145, 59207, 59318, 59393, 60075, 60111, 60611, 60695,
        60722, 60760, 60767, 60872, 61326, 61360, 61399, 61468, 61515, 61543, 61836, 61881, 62644, 62726, 62877, 62936,
        62971, 63030, 63258, 63624, 64041, 64112, 64374, 65321, 65623, 65950, 66077, 66113, 66127, 66721, 66953, 67020,
        67196, 67207, 67383, 67551, 67773, 67781, 67873, 68100, 68358, 68861, 69308, 69682, 69861, 70047, 70217, 70625,
        71854, 71913, 72584, 72681, 72913, 73033, 73079, 73086, 73179, 73441, 74358, 74490, 74609, 76091, 76802, 77033,
        78157, 78414, 78418, 78519, 78704, 79228, 79340, 79434, 79580, 79719, 79727, 79907, 80122, 80645, 80650, 80675,
        80918, 81195, 81458, 81570, 81609, 81820, 81824, 81907, 81973, 82028, 82071, 82186, 82260, 82263, 82266, 82382,
        83290, 83523, 83699, 83876, 84056, 84195, 84227, 85193, 85676, 85727, 85761, 85967, 86021, 86067, 86130, 86324,
        86415, 86592, 86816, 86831, 86886, 86957, 87004, 87028, 87040, 87182, 87280, 87328, 88624, 88753, 88754, 89025,
        89083, 89163, 89424, 89443, 89480, 89553, 89562, 89734, 89753, 89860, 89979, 89991, 91070, 91201, 91205, 91233,
        91297, 91350, 91367, 91414, 91464, 91518, 91584, 91629, 91682, 92048, 92074, 92123, 92138, 92313, 92528, 92629,
        92664, 92836, 93010, 93042, 93057, 93149, 93188, 93209, 93213, 93310, 93498, 93539, 93550, 93798, 93854, 93971,
        93988, 94021, 94039, 94149, 94158, 94441, 94476, 94582, 94729, 94823, 94841, 94957, 94975, 95024, 95040, 95392,
        95434, 95733, 96210, 96232, 96853, 97042, 97316, 97969, 98133, 98135, 98147, 98225, 98290, 98367, 98436, 98467,
        98798, 98894, 99078, 99140, 99275, 99559, 99611, 99696, 99896, 99903, 99933, 99984, 100001, 100134, 100159, 100175,
        100228, 100301, 100336, 100339, 100467, 100524, 100559, 100573, 100578, 100581, 100609, 100783, 100900, 100913, 100990, 101029,
        101111, 101218, 101399, 101403, 101464, 101525, 101651, 101658, 101659, 101726, 101923, 101924, 101947, 101954, 102159, 102295,
        102338, 102498, 102505, 102547, 102716, 103492, 103546, 103628, 103822, 103881, 103893, 103894, 104446, 104486, 104509, 105618,
        106179, 106510, 106654, 106746, 107275, 107384, 107477, 109676, 109719, 109967, 111019, 113811, 113967, 119604, 119821, 122215,
        122295, 122327, 122585, 122770, 122787, 122970, 123557, 124136, 124137, 124156, 124170, 124183, 124186, 124978, 125175, 125342,
        125432, 126028, 126055, 126151, 126187, 126486, 126589, 126947, 126971, 127175, 127300, 127411, 127601, 127881, 128394, 128535,
        128591, 128718, 128837, 129045, 129357, 129577, 129600, 129656, 129741, 130099, 130181, 130519, 130773, 131081, 131129, 131138,
        131255, 131376, 131540, 131710, 131740
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
        239, 741, 892, 2708, 7045, 8346, 15835, 16219, 21653, 24550, 30572, 34367, 66719, 69308, 73089, 75093,
        76020, 80400, 80974, 81009, 81832, 88753, 92930, 95982, 96152, 96241, 97226, 97343, 107670, 121861
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
        5220, 5434, 5465, 5528, 5738, 5793, 5937, 5976, 6005, 6076, 6120, 6166, 6203, 6281, 6354, 6361,
        6379, 6511, 6634, 6726, 6781, 6795, 6808, 6848, 6864, 7107, 7108, 7155, 7167, 7233, 7234, 7373,
        7428, 7620, 7677, 7688, 7692, 7731, 7753, 7836, 7862, 7915, 8164, 8194, 8402, 8609, 8828, 9083,
        9371, 9433, 9441, 9534, 9556, 9653, 9687, 9892, 10186, 10294, 10402, 10452, 10719, 10762, 10769, 10798,
        11018, 11200, 11213, 11408, 11583, 11662, 11668, 11683, 11918, 11920, 11937, 12192, 12204, 12273, 12363, 12574,
        12672, 12708, 12735, 12784, 12816, 12817, 12882, 12883, 13302, 13313, 13412, 13449, 13540, 13551, 13879, 14019,
        14409, 14576, 14944, 15310, 15321, 15338, 15517, 15750, 15998, 16155, 16218, 16316, 16449, 16586, 16670, 16690,
        16754, 16855, 17000, 17039, 17158, 17324, 17450, 17508, 17589, 17591, 17647, 17728, 17875, 18073, 18188, 18194,
        18290, 18472, 18633, 18772, 18946, 19624, 19854, 20179, 20341, 20370, 20413, 20950, 20981, 21045, 21103, 21284,
        21439, 21678, 21819, 21950, 22008, 22568, 22639, 22661, 22720, 22739, 22763, 22776, 23298, 23431, 23642, 23655,
        23818, 24396, 24505, 24524, 24801, 25194, 25329, 25797, 25908, 26038, 26080, 26086, 26090, 26119, 26249, 26656,
        26856, 27126, 27163, 27237, 27246, 27583, 27752, 28051, 28245, 28283, 28360, 28762, 28963, 30213, 30286, 30869,
        31522, 31553, 31656, 32279, 33213, 33620, 33966, 34434, 34469, 34502, 34891, 34893, 34995, 35476, 35731, 36459,
        36935, 37648, 37966, 38319, 38324, 38385, 38814, 38861, 39083, 39085, 40346, 41075, 41121, 41701, 41750, 42651,
        43296, 43391, 43490, 43769, 44746, 45263, 46906, 47026, 47981, 48955, 49444, 49944, 50107, 50165, 50696, 51186,
        51276, 51543, 51834, 51944, 52747, 52800, 53135, 54394, 54504, 55087, 55927, 56517, 56604, 57419, 57521, 59320,
        60111, 60194, 60760, 61399, 61974, 63099, 63220, 63624, 63846, 64112, 64155, 64596, 64646, 67307, 67383, 67921,
        68149, 71827, 71981, 73179, 74490, 74609, 74929, 75546, 75671, 76451, 76864, 77075, 77509, 77895, 78054, 78920,
        78963, 79100, 79580, 79727, 79854, 80197, 80240, 80377, 80429, 80498, 80563, 80662, 80675, 80822, 82947, 83259,
        85696, 85739, 85761, 85763, 85764, 85822, 86021, 86100, 86355, 86511, 86613, 86652, 86845, 86886, 86957, 87071,
        87409, 87462, 87705, 88893, 89025, 89083, 89098, 89358, 89382, 89562, 89565, 89770, 89816, 90021, 90051, 91204,
        91345, 91383, 91398, 91418, 91629, 91777, 91847, 91908, 92183, 92196, 92241, 92390, 92606, 92781, 92801, 92891,
        92897, 92956, 93017, 93034, 93042, 93126, 93143, 93185, 93446, 93668, 93862, 93918, 93988, 94050, 94116, 94138,
        94376, 94820, 94823, 94841, 94957, 95028, 95062, 95156, 95187, 95276, 95324, 95732, 95780, 96210, 96327, 96654,
        96707, 96981, 97163, 97250, 97269, 97540, 97683, 97742, 98129, 98570, 98829, 99043, 99140, 99153, 99862, 99977,
        100239, 100241, 100346, 100559, 100609, 100633, 100771, 100900, 100933, 101464, 101501, 101549, 101607, 101721, 101727, 101870,
        101909, 101932, 102138, 103050, 103887, 106524, 106835, 106946, 106975, 107034, 107275, 107386, 108332, 115632, 116641, 116750,
        119597, 120812, 122052, 122056, 123260, 123322, 123426, 124183, 124687, 125250, 125342, 125637, 126387, 127053, 127558, 128224,
        128718, 129709, 129741, 130572, 130828, 130879, 131045, 132060
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
        1128, 4102, 5976, 7045, 16690, 21653, 28249, 50023, 50696, 67688, 77075, 81009, 85764, 85835, 89073, 92930,
        93143, 94820, 96152, 96241, 96659, 97226, 102138, 107670, 131918
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
        57364, 57836, 83259, 83560, 92528, 93165, 93315, 97269, 98129, 98225, 98922, 99153, 99724, 99977, 99988, 100159,
        100370, 100600, 100609, 100965, 101526, 101549, 102104, 102259, 102268, 109767, 122096, 122123, 123426, 124829, 126349, 126446,
        126810, 127601, 128224, 128406, 128543, 128590, 128718, 129053, 129358, 129466, 129709, 130201, 130572, 130773, 130879, 131196,
        131482
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
        1124, 3433, 4770, 5406, 6701, 7180, 7201, 7206, 7557, 7804, 7862, 9577, 9653, 10487, 10756, 11369,
        11548, 12228, 12521, 14576, 14994, 15999, 16096, 16424, 16729, 16791, 17321, 17460, 17729, 17999, 18472, 18681,
        18759, 18832, 19001, 19986, 21263, 21686, 21687, 22120, 22597, 22667, 23636, 24277, 24555, 24990, 25469, 25935,
        26045, 26124, 26307, 26941, 26957, 27042, 27217, 27237, 27914, 28436, 28797, 32994, 33174, 33771, 33867, 34228,
        34270, 34434, 34446, 35006, 35124, 35763, 35819, 36485, 36821, 37056, 38036, 39345, 39783, 40151, 40667, 40917,
        42745, 43024, 43870, 43959, 44032, 44630, 45395, 45417, 46202, 46380, 47297, 48619, 49407, 49450, 50107, 50265,
        50382, 50642, 50766, 50992, 51276, 51944, 52800, 54004, 54018, 54660, 55114, 55180, 56113, 56244, 56417, 56956,
        56959, 57474, 57744, 58398, 58597, 59852, 59861, 60756, 61630, 63499, 64155, 64263, 65072, 65930, 66200, 66439,
        66975, 67215, 67373, 67390, 70013, 70342, 71312, 71517, 73189, 74259, 75357, 75937, 76120, 76883, 78428, 79252,
        80452, 82980, 84185, 85696, 85956, 86730, 86981, 87468, 87799, 88587, 89048, 89067, 89349, 89607, 90442, 91498,
        92345, 92391, 92492, 92617, 92801, 92840, 92876, 93126, 93176, 93182, 93917, 94069, 94141, 94364, 94843, 94870,
        95219, 95423, 95561, 95575, 95863, 96127, 96142, 97008, 97044, 97209, 97226, 97255, 97269, 97289, 97343, 97696,
        97708, 98129, 98225, 98388, 98441, 99084, 101163, 101195, 101315, 101616, 101679, 101863, 101929, 102339, 102378, 102404,
        102424, 103887, 104479, 105987, 106982, 107333, 108322, 108688, 108870, 109039, 109526, 110361, 113760, 116995, 117017, 117168,
        118085, 118098, 122050, 122405, 122472, 123007, 123030, 123138, 123358, 123976, 124064, 124521, 124547, 125030, 125156, 125249,
        125282, 125937, 126105, 126551, 126615, 126744, 127435, 127892, 127945, 128048, 128098, 128489, 128919, 128926, 129173, 129378,
        129494, 129832, 129886, 130015, 130123, 130249, 130641, 131375
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
        32351, 91233, 91297, 93017
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
        397, 1833, 4028, 4228, 8579, 9653, 9670, 9932, 12551, 14141, 14950, 15747, 16760, 20022, 20341, 21793,
        28673, 29061, 31704, 36504, 38094, 38611, 39634, 39682, 39783, 41566, 41611, 45558, 51953, 52734, 56417, 57950,
        61246, 66109, 67121, 70069, 71644, 77801, 79908, 81458, 82899, 86814, 86937, 87722, 88716, 88944, 89063, 89386,
        91233, 91297, 93972, 94841, 95972, 96973, 97652, 97669, 99471, 100467, 100541, 101250, 101915, 107055, 107333, 124170,
        125053, 127447, 128944, 129359, 130505, 130622, 131179
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
        15004, 20687, 21686, 26845, 43353, 52293, 64141, 102148
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
        787, 1731, 2259, 3768, 5700, 7444, 7625, 8654, 9214, 9892, 10762, 11216, 12634, 13477, 13680, 13862,
        14139, 14151, 15967, 15999, 16426, 18242, 18287, 19517, 19931, 20213, 20824, 21375, 26993, 27007, 28178, 28533,
        30211, 30286, 30600, 36045, 36953, 38590, 38609, 38814, 40346, 41576, 45400, 46671, 48146, 49390, 49524, 50735,
        50918, 51813, 52980, 53097, 53265, 53889, 54079, 54470, 56460, 56746, 56986, 57419, 58761, 59207, 60116, 60447,
        60693, 61528, 62483, 63846, 65444, 66878, 67330, 67398, 67613, 68408, 70040, 70045, 70321, 71303, 71690, 72240,
        74490, 75148, 76802, 77142, 77880, 80417, 82423, 83259, 84183, 84849, 85775, 85895, 87312, 89058, 89098, 89209,
        89605, 89833, 90612, 91075, 93227, 93264, 94116, 94397, 94680, 94820, 94979, 96320, 96748, 97063, 97403, 97704,
        98225, 98388, 98468, 98519, 100339, 100395, 101184, 101501, 102754, 102961, 104087, 106202, 106977, 107034, 107589, 107938,
        112759, 113689, 115363, 115904, 116070, 118977, 119604, 120831, 121065, 124403, 124709, 124750, 124897, 124966, 125202, 125377,
        126304, 127104, 127414, 127856, 128036, 128797, 128872, 130635, 130829
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
        16574, 21242, 61149, 72116, 82276, 91660, 93296, 94823, 102278, 107879, 113525, 116942, 128535
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
        1873, 2976, 3835, 5171, 8740, 9546, 10294, 11018, 12528, 13078, 20687, 20753, 21358, 21909, 22086, 22722,
        24550, 26589, 29123, 37082, 37648, 38229, 40116, 41846, 43092, 43705, 44208, 45039, 46903, 48070, 48126, 48805,
        49308, 49323, 49600, 51562, 51787, 52076, 52527, 52793, 52810, 53264, 53456, 53462, 53512, 54180, 55026, 55079,
        55477, 55930, 56151, 56279, 56469, 56557, 56953, 57402, 57482, 58160, 59587, 60002, 60242, 60313, 60426, 60630,
        61227, 61266, 61600, 61651, 61687, 61704, 61793, 62642, 62665, 63316, 63394, 63411, 63647, 63984, 64035, 64389,
        64406, 64728, 64860, 65352, 65444, 65620, 66118, 66135, 67284, 67307, 67353, 67433, 67437, 68316, 69027, 69161,
        69670, 70126, 70428, 72739, 75351, 76160, 77102, 78152, 83464, 83807, 85564, 85956, 86188, 86507, 86571, 86615,
        86951, 87080, 87468, 88127, 88673, 88850, 89363, 89833, 89860, 91187, 91517, 91635, 92572, 92861, 92981, 93946,
        94472, 94752, 95403, 96049, 96123, 96732, 96919, 97214, 97677, 98062, 99154, 99845, 99862, 101162, 101616, 102127,
        103187, 106141, 106651, 107895, 109146, 110629, 113885, 113967, 118741, 120869, 121624, 121660, 122018, 122964, 123277, 123941,
        124200, 124250, 124379, 124698, 124792, 124909, 125053, 125839, 126035, 126175, 126989, 127532, 127626, 127677, 128128, 128322,
        128548, 129407, 129679, 129781, 130333, 130338, 130463
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
        12219, 21223, 47826, 49133, 49868, 62577, 68341, 71338, 94165, 96471, 116119, 127186, 128385, 130641
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

-- Source evidence protects each Introduced link from automated removal.
INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('a3c', 'trpo', 'ddpg', 'td3')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
