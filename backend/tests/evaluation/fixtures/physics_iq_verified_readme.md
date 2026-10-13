<p align="center">
  <img src="assets/joint_duck.png" width="60%" alt="Physics-IQ and Physics-IQ Verified logos">
</p>

[Leaderboard](#leaderboard) | [Quick Start](#quick-start) | [Physics-IQ Verified Workflow](#physics-iq-verified-workflow) | [Citation](#citation) | [License](#license-and-disclaimer)

# Physics-IQ and Physics-IQ Verified: Benchmarking physical understanding in generative video models

Physics-IQ is a high-quality, realistic, and comprehensive benchmark dataset for evaluating physical understanding in generative video models.
Building on this foundation, Physics-IQ Verified contains improvements w.r.t. prompt and metric quality.

This repository contains the workflow for both Physics-IQ Verified (recommended benchmark variant) and the original Physics-IQ benchmark.

Original Physics-IQ website: [physics-iq.github.io](https://physics-iq.github.io/)<br>
Physics-IQ Verified website: [physics-iq-verified.anates.ai](https://physics-iq-verified.anates.ai)

### Key Features:
- **Real-world videos**: All videos are captured with high-quality cameras, not rendered.
- **Diverse scenarios**: Covers a wide range of physical phenomena, including collisions, fluid dynamics, gravity, material properties, light, shadows, magnetism, and more.
- **Multiple perspectives**: Each scenario is filmed from 3 different angles.
- **Variations**: Each scenario is recorded twice to capture natural physical variations, with some intended exceptions (see [here](https://github.com/google-deepmind/physics-IQ-benchmark/issues/84)).
- **High resolution and frame rate**: Videos are recorded at 3840 × 2160 resolution and 30 frames per second.

<p align="center">
  <img src="assets/teaser1.gif" width="23%" alt="Teaser 1">
  <img src="assets/teaser2.gif" width="23%" alt="Teaser 2">
  <img src="assets/teaser3.gif" width="23%" alt="Teaser 3">
  <img src="assets/teaser4.gif" width="23%" alt="Teaser 4">
  <img src="assets/teaser5.gif" width="23%" alt="Teaser 5">
  <img src="assets/teaser6.gif" width="23%" alt="Teaser 6">
  <img src="assets/teaser7.gif" width="23%" alt="Teaser 7">
  <img src="assets/teaser8.gif" width="23%" alt="Teaser 8">
</p>

---
## Leaderboard
The best possible score on Physics-IQ is 100.0%, this score would be achieved by physically realistic videos that differ only in physical randomness but adhere to all tested principles of physics.
### Physics-IQ Verified Leaderboard
If you test your model on Physics-IQ Verified and would like your score/paper/model to be featured here in this table, feel free to open a pull request that adds a row to the table and we'll be happy to include it!

The leaderboard is also hosted at: [physics-iq-verified.anates.ai](https://physics-iq-verified.anates.ai)

Note: the test data must under no circumstances be used to improve a submission score - not for BoN selection, and not by a prompt rewriter. E.g., we've seen frontier models independently download the test data when asked to optimize prompts. If using a frontier LLM prompt rewriter, disable internet access and make sure it doesn't have or gain access to the test data.

| # | Model | input type | Physics-IQ verified | date added (YYYY-MM-DD) |
|---|---|---|---|---|
| 1 | [Odyssey-3 Pro](https://odyssey.systems) + best-of-8 ([WMReward](https://arxiv.org/abs/2601.10553) + MBR consensus, rank-sum) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | multiframe (v2v) | **66.10** <br> 🥇 v2v | 2026-10-08 |
| 2 | [Odyssey-3](https://odyssey.systems) + best-of-8 ([WMReward](https://arxiv.org/abs/2601.10553) + MBR consensus, rank-sum) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | multiframe (v2v) | **64.43** <br> 🥈 v2v | 2026-10-08 |
| 3 | [FLUX 3 \[large\]](https://bfl.ai/models/flux-3-video) <small>(Claude Opus 5.5 prompts)</small> + [WMReward](https://arxiv.org/abs/2601.10553) + consensus (BoN) reported [here](https://github.com/felifri/flux3-physics-iq-prompts) | multiframe (v2v) | **64.35** <small>± 0.22</small> <br> 🥉 v2v | 2026-10-06 |
| 4 | [Odyssey-3 Pro](https://odyssey.systems) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | multiframe (v2v) | 63.37 <small>± 0.63</small> | 2026-10-08 |
| 5 | [Odyssey-3](https://odyssey.systems) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | multiframe (v2v) | 61.56 <small>± 1.20</small> | 2026-10-08 |
| 6 | [FLUX 3 \[large\]](https://bfl.ai/models/flux-3-video) <small>(Claude Opus 5.5 prompts)</small> reported [here](https://github.com/felifri/flux3-physics-iq-prompts) | multiframe (v2v) | 61.11 <small>± 0.55</small> | 2026-10-06 |
| 7 | [Magi-1 24B](https://arxiv.org/abs/2505.13211) + [GeoPhys (BoN)](https://christianinterno.github.io/GeoPhys/) <small>(op)</small> reported [here](https://christianinterno.github.io/GeoPhys/) | multiframe (v2v) | 58.2 <small>± 1.8</small> | 2026-06-19 |
| 8 | [FLUX 3 \[large\]](https://bfl.ai/models/flux-3-video) <small>(Claude Opus 5.5 prompts)</small> + [WMReward](https://arxiv.org/abs/2601.10553) + consensus (BoN) reported [here](https://github.com/felifri/flux3-physics-iq-prompts) | i2v | 54.70 <small>± 0.41</small> <br> 🥇 i2v | 2026-10-06 |
| 9 | [Odyssey-3 Pro](https://odyssey.systems) + best-of-8 ([WMReward](https://arxiv.org/abs/2601.10553) + MBR consensus, rank-sum) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | i2v | 54.69 <br> 🥈 i2v | 2026-10-08 |
| 10 | [Odyssey-3](https://odyssey.systems) + best-of-8 ([WMReward](https://arxiv.org/abs/2601.10553) + MBR consensus, rank-sum) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | i2v | 52.83 <br> 🥉 i2v | 2026-10-08 |
| 11 | [Physical Registry + PRS (BoN=8, Cosmos 3 Nano 16B)](https://huggingface.co/datasets/GrainSack/WPM-PhysicsIQ/tree/main/prs/v2v) <small>(bpp)</small> reported [here](https://grainsack.github.io/physics-IQ-benchmark/documentation/anonymous_manuscript.pdf) | multiframe (v2v) | 51.86 | 2026-10-06 |
| 12 | [Odyssey-3](https://odyssey.systems) <small>(bpp)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | multiframe (v2v) | 51.76 <small>± 0.69</small> | 2026-10-08 |
| 13 | [FLUX 3 \[large\]](https://bfl.ai/models/flux-3-video) <small>(Claude Opus 5.5 prompts)</small> reported [here](https://github.com/felifri/flux3-physics-iq-prompts) | i2v | 51.11 <small>± 0.44</small> | 2026-10-06 |
| 14 | [Cosmos3-Super](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/82) | multiframe (v2v) | 50.8 <small>± 2.2</small> | 2026-09-22 |
| 15 | [Physical Registry (Cosmos 3 Nano 16B)](https://huggingface.co/datasets/GrainSack/WPM-PhysicsIQ/tree/main/plain/v2v) <small>(bpp)</small> reported [here](https://grainsack.github.io/physics-IQ-benchmark/documentation/anonymous_manuscript.pdf) | multiframe (v2v) | 50.17 <small>± 0.72</small> | 2026-10-06 |
| 16 | [Odyssey-3 Pro](https://odyssey.systems) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | i2v | 49.99 <small>± 0.42</small> | 2026-10-08 |
| 17 | [Odyssey-3](https://odyssey.systems) <small>(custom prompts)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | i2v | 48.83 <small>± 0.78</small> | 2026-10-08 |
| 18 | [Magi-1 24B](https://arxiv.org/abs/2505.13211) <small>(op)</small> reported [here](https://christianinterno.github.io/GeoPhys/) | multiframe (v2v) | 48.4 <small>± 1.1</small> | 2026-06-19 |
| 19 | [Physis-Lang (Cosmos3 Super)](https://github.com/Physis-Intelligence/Physis-Lang/blob/main/assets/Physis-Lang_arxiv.pdf) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/83) | i2v | 48.2 <small>± 1.4</small> | 2026-09-28 |
| 20 | [Physical Registry + PRS (BoN=8, Cosmos 3 Nano 16B)](https://huggingface.co/datasets/GrainSack/WPM-PhysicsIQ/tree/main/prs/i2v) <small>(bpp)</small> reported [here](https://grainsack.github.io/physics-IQ-benchmark/documentation/anonymous_manuscript.pdf) | i2v | 46.66 | 2026-10-06 |
| 21 | [StrucPhysVideo-TI2V](https://arxiv.org/abs/2609.18430) reported [here](https://arxiv.org/abs/2609.18430) | i2v | 45.5 <small>± 0.4</small> | 2026-10-01 |
| 22 | [Physical Registry (Cosmos 3 Nano 16B)](https://huggingface.co/datasets/GrainSack/WPM-PhysicsIQ/tree/main/plain/i2v) <small>(bpp)</small> reported [here](https://grainsack.github.io/physics-IQ-benchmark/documentation/anonymous_manuscript.pdf) | i2v | 44.00 <small>± 0.60</small> | 2026-10-06 |
| 23 | [Physis-Lang (Cosmos3 Nano)](https://github.com/Physis-Intelligence/Physis-Lang/blob/main/assets/Physis-Lang_arxiv.pdf) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/83) | i2v | 43.3 <small>± 1.5</small> | 2026-09-28 |
| 24 | [Cosmos3-Nano](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/82) | multiframe (v2v) | 43.0 <small>± 2.0</small> | 2026-09-22 |
| 25 | [Cosmos3-Super-Image2Video](https://huggingface.co/nvidia/Cosmos3-Super-Image2Video) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/issues/75) | i2v | 42.7 <small>± 0.8</small> | 2026-09-04 |
| 26 | [Seedance 2.5](https://seed.bytedance.com/en/seedance2_5) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/85) | i2v | 42.43 <small>± 0.76</small> | 2026-09-27 |
| 27 | [Odyssey-3](https://odyssey.systems) <small>(bpp)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/90) | i2v | 40.99 <small>± 0.84</small> | 2026-10-08 |
| 28 | [MiniMax H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) <small>(FL2VA)</small> reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/80) | i2v | 39.8 <small>± 0.4</small> | 2026-09-04 |
| 29 | [Cosmos3-Nano](https://huggingface.co/nvidia/Cosmos3-Nano) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/issues/75) | i2v | 37.3 <small>± 0.9</small> | 2026-09-04 |
| 30 | [MiniMax H3 Max](https://fal.ai/models/minimax/h3-max/image-to-video) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/80) | i2v | 36.2 <small>± 0.7</small> | 2026-09-04 |
| 31 | [Gemini Omni 1.1 Flash](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-omni-1-1-flash/) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/85) | i2v | 35.34 <small>± 0.44</small> | 2026-09-27 |
| 32 | [Grok Imagine Video](https://x.ai/news/grok-imagine-api) reported [here](https://arxiv.org/abs/2606.18943) | i2v | 34.8 <small>± 0.6</small> | 2026-06-17 |
| 33 | [Magi-1 24B](https://arxiv.org/abs/2505.13211) + [GeoPhys (BoN)](https://christianinterno.github.io/GeoPhys/) <small>(op)</small> reported [here](https://christianinterno.github.io/GeoPhys/) | i2v | 33.7 <small>± 1.4</small> | 2026-06-19 |
| 34 | [Hunyuan Video 1.5](https://arxiv.org/abs/2511.18870) reported [here](https://arxiv.org/abs/2606.18943) | i2v | 33.4 <small>± 0.8</small> | 2026-06-17 |
| 35 | [Gemini Omni Flash Preview](https://deepmind.google/models/gemini-omni/) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/85) | i2v | 33.36 <small>± 0.19</small> | 2026-09-27 |
| 36 | [Cosmos3-Edge](https://huggingface.co/nvidia/Cosmos3-Edge) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/issues/76) | i2v | 32.7 <small>± 1.1</small> | 2026-08-31 |
| 37 | [Wan 2.2 14B](https://github.com/Wan-Video/Wan2.2) reported [here](https://arxiv.org/abs/2606.18943) | i2v | 32.2 <small>± 0.6</small> | 2026-06-17 |
| 38 | [Veo 3.1 Lite](https://deepmind.google/models/model-cards/veo-3-1-lite/) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/85) | i2v | 31.83 <small>± 0.32</small> | 2026-09-27 |
| 39 | [CogVideoX-5B](https://huggingface.co/zai-org/CogVideoX-5b-I2V) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/80) | i2v | 31.8 <small>± 1.5</small> | 2026-09-04 |
| 40 | [Kandinsky-WM 1.0](https://huggingface.co/kandinskylab/Kandinsky-WM-1.0-I2V-5s-PH) reported [here](https://huggingface.co/datasets/Messimm/Kandinsky-WM-1.0-Physics-IQ-Verified) | i2v | 30.8 <small>± 0.9</small> | 2026-08-04 |
| 41 | [Magi-1 24B](https://arxiv.org/abs/2505.13211) <small>(op)</small> reported [here](https://christianinterno.github.io/GeoPhys/) | i2v | 30.2 <small>± 1.1</small> | 2026-06-19 |
| 42 | [Veo 3.1 Fast](https://deepmind.google/models/veo/) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/85) | i2v | 29.96 <small>± 0.53</small> | 2026-09-27 |
| 43 | [Wan 2.2 5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/pull/80) | i2v | 27.7 <small>± 0.9</small> | 2026-09-04 |
| 44 | [Sora 2](https://openai.com/index/sora-2/) reported [here](https://arxiv.org/abs/2606.18943) | i2v | 26.5 <small>± 0.8</small> | 2026-06-17 |
| 45 | [P-Video](https://www.pruna.ai/p-video) reported [here](https://arxiv.org/abs/2606.18943) | i2v | 25.3 <small>± 1.8</small> | 2026-06-17 |

For details on the Physics-IQ Verified metrics, see the [arXiv report](https://arxiv.org/abs/2606.18943).

Unless specified by `op` for original prompt in the entry, all reported scores use best-practice-prompts (`bpp`) based on a custom templater for each specific model.
> Rules:
>1. One run is sufficient to be included on the verified leaderboard. In general, we recommend to use 4 runs reporting mean and standard deviation. To claim SOTA (on i2v and/or v2v), reporting standard deviation across 4 runs is required.
>2. Leaderboard entries need to link a tech report / reproducible github repo or some other form of documentation that enables others to read and understand the methodological details of your approach.
>3. Since Physics-IQ Original and Verified share scenarios, you must not use signal from one to improve scores on the other.


### Physics-IQ Original Leaderboard

If you test your model on Physics-IQ Original and would like your score/paper/model to be featured here in this table, feel free to open a pull request that adds a row to the table and we'll be happy to include it!

| **#** | **Model** | **input type** | **Physics-IQ score** | **date added (YYYY-MM-DD)** |
| -- | --- | --- | --- | --- |
| 1 | [Magi-1 + GeoPhys (BoN)](https://christianinterno.github.io/GeoPhys/) reported [here](https://christianinterno.github.io/GeoPhys/) | multiframe (v2v) | **64.5 %** :1st_place_medal: v2v | 2026-06-17 |
| 2 | [Cosmos3-Super + WMReward (BoN)](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | multiframe (v2v) | **63.4 %** :2nd_place_medal: v2v | 2026-05-26 |
| 3 | [Magi-1 + WMReward (BoN)](https://arxiv.org/abs/2601.10553) reported [here](https://arxiv.org/abs/2601.10553) | multiframe (v2v) | **62.6 %** :3rd_place_medal: v2v | 2025-10-28 |
| 4 | [Cosmos3-Super](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | multiframe (v2v) | 59.7 % | 2026-05-26 |
| 5 | [Cosmos3-Nano + WMReward (BoN)](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | multiframe (v2v) | 57.7 % | 2026-05-26 |
| 6 | [Magi-1](https://arxiv.org/abs/2505.13211) reported [here](https://arxiv.org/pdf/2505.13211) | multiframe (v2v) | 56.0 % | 2025-04-21 |
| 7 | [Cosmos3-Nano](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | multiframe (v2v) | 50.2 % | 2026-05-26 |
| 8 | [Cosmos3-Super + WMReward (BoN)](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | i2v | 48.9 % :1st_place_medal: i2v | 2026-05-26 |
| 9 | [Sora2 + WMReward (BoN)](https://arxiv.org/abs/2601.10553) reported [here](https://arxiv.org/abs/2601.10553) | i2v | 46.4 % :2nd_place_medal: i2v | 2026-04-01 |
| 10 | [Wan2.2 + WMReward (BoN)](https://arxiv.org/abs/2601.10553) reported [here](https://arxiv.org/abs/2601.10553) | i2v | 44.4 % :3rd_place_medal: i2v | 2026-04-01 |
| 11 | [Cosmos3-Super](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | i2v | 43.8 % | 2026-05-26 |
| 12 | [Cosmos3-Nano + WMReward (BoN)](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | i2v | 43.8 % | 2026-05-26 |
| 13 | [Sora2](https://openai.com/index/sora-2/) reported [here](https://arxiv.org/abs/2601.10553) | i2v | 42.3 % | 2026-04-01 |
| 14 | [Cosmos3-Nano](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) reported [here](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) | i2v | 40.2 % | 2026-05-26 |
| 15 | [Magi-1 + GeoPhys (BoN)](https://christianinterno.github.io/GeoPhys/) reported [here](https://christianinterno.github.io/GeoPhys/) | i2v | 38.6 % | 2026-06-17 |
| 16 | [Wan2.2](https://github.com/Wan-Video/Wan2.2) reported [here](https://arxiv.org/abs/2601.10553) | i2v | 38.3 % | 2026-04-01 |
| 17 | [Magi-1 + WMReward (BoN)](https://arxiv.org/abs/2601.10553) reported [here](https://arxiv.org/abs/2601.10553) | i2v | 36.9 % | 2025-10-28 |
| 18 | [Video-GPT](https://arxiv.org/abs/2505.12489) reported [here](https://arxiv.org/abs/2505.12489) | multiframe (v2v) | 35.0 % | 2025-05-22 |
| 19 | [CogVideoX-5B + GeoPhys (BoN)](https://christianinterno.github.io/GeoPhys/) reported [here](https://christianinterno.github.io/GeoPhys/) | i2v | 34.1 % | 2026-06-17 |
| 20 | [Cosmos3-Edge](https://huggingface.co/nvidia/Cosmos3-Edge) reported [here](https://github.com/google-deepmind/physics-IQ-benchmark/issues/76) | i2v | 34.1 % | 2026-08-31 |
| 21 | [Wan2.1 14B + GeoPhys (BoN)](https://christianinterno.github.io/GeoPhys/) reported [here](https://christianinterno.github.io/GeoPhys/) | i2v | 34.0 % | 2026-06-17 |
| 22 | [Magi-1 4.5B + GeoPhys (BoN)](https://christianinterno.github.io/GeoPhys/) reported [here](https://christianinterno.github.io/GeoPhys/) | i2v | 34.0 % | 2026-06-17 |
| 23 | [CogVideoX-5b](https://github.com/ved015/CogVideoX-5b-Physics_iq_benchmarking) reported [here](https://github.com/ved015/CogVideoX-5b-Physics_iq_benchmarking) | i2v | 32.3 % | 2026-01-06 |
| 24 | [Magi-1](https://arxiv.org/abs/2505.13211) reported [here](https://arxiv.org/pdf/2505.13211) | i2v | 30.2 % | 2025-04-21 |
| 25 | [VideoPoet](https://arxiv.org/abs/2312.14125) reported [here](https://arxiv.org/abs/2501.09038) | multiframe (v2v) | 29.5 % | 2025-02-19 |
| 26 | [Lumiere](https://arxiv.org/abs/2401.12945) reported [here](https://arxiv.org/abs/2501.09038) | multiframe (v2v) | 23.0 % | 2025-02-19 |
| 27 | [Runway Gen 3](https://runwayml.com/research/introducing-gen-3-alpha) reported [here](https://arxiv.org/abs/2501.09038) | i2v | 22.8 % | 2025-02-19 |
| 28 | [VideoPoet](https://arxiv.org/abs/2312.14125) reported [here](https://arxiv.org/abs/2501.09038) | i2v | 20.3 % | 2025-02-19 |
| 29 | [Lumiere](https://arxiv.org/abs/2401.12945) reported [here](https://arxiv.org/abs/2501.09038) | i2v | 19.0 % | 2025-02-19 |
| 30 | [Stable Video Diffusion](https://arxiv.org/abs/2311.15127) reported [here](https://arxiv.org/abs/2501.09038) | i2v | 14.8 % | 2025-02-19 |
| 31 | [Pika](https://pika.art/) reported [here](https://arxiv.org/abs/2501.09038) | i2v | 13.0 % | 2025-02-19 |
| 32 | [Sora](https://openai.com/sora/) reported [here](https://arxiv.org/abs/2501.09038) | i2v | 10.0 % | 2025-02-19 |

</details>

---
