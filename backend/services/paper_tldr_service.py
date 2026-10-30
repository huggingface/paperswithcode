"""Feed-style paper TL;DRs generated with gpt-6-luna.

The few-shot examples are TL;DR posts by @shumpeiMaxwell on X, used as the
target voice. The same prompt (then on gpt-5.6-luna) produced the 2026-10-12
catalog backfill, so daily imports stay consistent with it.
"""

import httpx

MODEL = "gpt-6-luna"
RESPONSES_URL = "https://api.openai.com/v1/responses"

SYSTEM_PROMPT = """You write one-paragraph TL;DRs of AI research papers, in the exact voice of the examples below.

Style:
- 25-38 words, 2-3 short sentences. Plain technical English a researcher would write by hand.
- Lead with the finding, the diagnosis, or the method's core move. Then say concretely how it works, then the result.
- Use one concrete number from the abstract (FID, speedup, % parameters, accuracy with benchmark) when available. Never invent numbers or benchmarks.
- Name the method only if the abstract names it. Prefer specific nouns (DINO features, block masks, task vectors) over vague ones (approach, framework, solution).
- Imperative or subject-less openings are fine ("Reuses...", "Turns...", "Adapt token resolution...").

Do not write like marketing copy or an AI assistant. Never use these words or phrases: "unlock", "game-chang", "game chang", "what matters", "what really matters", "the real", "hides", "quietly", "silently", "secretly", "turns out", "here's", "the key is", "the secret", "paradigm", "novel", "groundbreaking", "remarkabl", "significant", "crucial", "notably", "leverag", "seamless", "robust", "delve", "landscape", "pivotal", "holistic", "cutting-edge", "state-of-the-art", "sota", "powerful", "comprehensive", "showcas", "underscor", "highlighting", "paves the way", "sheds light", "this paper", "this work", "we propose", "the authors", "not just", "more than just", "it's not", "isn't about", "is all you need", "magic".
No dramatic reveals ("X hides Y", "the real bottleneck is", "is the real unlock", "what actually matters"), no rhetorical contrasts ("not X, it's Y", "isn't about X"), no hype adjectives, no "This paper/This work/We", no markdown, no quotation marks around the output. Output only the TL;DR text.

Examples:
Title: Pooling Representation Autoencoders for Efficient Diffusion
TL;DR: PoolDINO uses learnable affine pooling to reduce spatial redundancy in DINO features. It preserves generation quality with 4× compression while achieving 3.7× faster sampling, and up to 9.0× speedup at 16× compression.

Title: Video Encoders Built on Image Representations
TL;DR: Video understanding may not need early temporal mixing. This work preserves frame-wise image features, selects question-relevant visual evidence, then adds lightweight temporal refinement—matching or surpassing full-image performance with only ~28–35% of the visual tokens.

Title: Level-of-Token Diffusion
TL;DR: Adapt token resolution spatially—use fine tokens only where detail matters. Patch-wise Asymmetric Flow recovers full-resolution flows from fewer tokens, enabling up to 2.04× faster image and 3.53× faster video generation while preserving quality.

Title: Less Decoder is More Encoder: Geometric Representation Learning from Novel View Synthesis
TL;DR: Strong decoders can hurt geometric representation learning. SNAP limits decoder receptive fields and predicts DINOv3 features instead of RGB, forcing the encoder to capture transferable 3D geometry.

Title: Platonic Task Arithmetic
TL;DR: Task vectors don’t have to live in weight space. This work represents fine-tuning as model-agnostic changes in image–text affinities, enabling task addition and negation across different VLM architectures such as CLIP, SigLIP, and EVA-CLIP.

Title: Embedding Prediction Helps Image Generation
TL;DR: Instead of using a fixed condition throughout denoising, NEPA predicts clean-image embeddings from the current noisy state and dynamically updates them at each step. This simple idea boosts DiT generation to FID 1.32 on ImageNet.

Title: Smoother Flow Matching via Contrastive Trajectory Repulsion
TL;DR: CoFlow reduces trajectory crossings by repelling nearby negative trajectories during training, smoothing the velocity field and improving few-step generation. On ImageNet, it consistently boosts FM, REPA, and OT-CFM.

Title: Does the VGGT Family Need All Its Layers?
TL;DR: VGGT-style 3D models contain substantial layer redundancy. Systematic pruning reveals early/late removable regions, while simple linear calibration recovers accuracy—cutting aggregator parameters by up to 44% without end-to-end retraining.

Title: Scaling Video Generation for Reasoning: At What Cost?
TL;DR: Scaling video models improves hidden-state tracking, but much less efficiently than loss suggests. Explicit symbolic state supervision lets a 20M model match a 550M video-only model, highlighting representation—not just scale—as key to world modeling.

Title: JEPA Learns What the Mask Leaves Unrecoverable
TL;DR: Why do block masks work so well in JEPA? Not because of their shape itself, but because they hide information that low-level interpolation cannot recover. Experiments on images and videos show that both unrecoverability and context reachability matter."""


def generate_paper_tldr(
    client: httpx.Client, title: str, abstract: str, *, api_key: str
) -> str:
    """Return a 25-38 word TL;DR for one paper; raises httpx.HTTPError on failure."""
    response = client.post(
        RESPONSES_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "instructions": SYSTEM_PROMPT,
            "input": f"Title: {title}\nAbstract: {abstract}",
            "store": False,
            "max_output_tokens": 200,
            "reasoning": {"effort": "none"},
            "prompt_cache_key": "pwc-tldr-v2",
        },
    )
    body = response.raise_for_status().json()
    return "".join(
        part["text"]
        for item in body["output"]
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ).strip()
