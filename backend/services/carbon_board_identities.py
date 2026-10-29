"""Reviewed upstream name -> catalog model identities, per board slug.

Generated 2026-10-29 from the hand-checked backfill rows on each board;
edit by hand when a leaderboard adds a model whose paper is ambiguous.
"""

from backend.services.live_leaderboard_sync import ModelIdentity

IDENTITIES: dict[str, dict[str, ModelIdentity]] = {
    "vals-index-v2-2": {
        "Claude Sonnet 5.5": ModelIdentity(
            "Claude Sonnet 5.5",
            source_url="https://www.anthropic.com/claude-sonnet-5-5",
        ),
        "Gemini 4 Carbon": ModelIdentity(
            "Gemini 4 Carbon",
            source_url="https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/",
        ),
        "Claude Opus 5.5": ModelIdentity(
            "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
        ),
        "Gemini 4 Argon": ModelIdentity(
            "Gemini 4 Argon",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/",
        ),
        "Wonder Full": ModelIdentity(
            "Muse Wonder Full", source_url="https://research.meta.ai/blog/muse-wonder"
        ),
        "GPT-6 Astra": ModelIdentity(
            "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
        ),
        "Wonder": ModelIdentity(
            "Muse Wonder", source_url="https://research.meta.ai/blog/muse-wonder"
        ),
        "GPT-6.1 Sol": ModelIdentity(
            "GPT-6.1 Sol",
            source_url="https://openai.com/index/introducing-gpt-6-1-sol/",
        ),
        "Kimi K3.1 Pro": ModelIdentity(
            "Kimi K3.1 Pro",
            source_url="https://www.kimi.com/blog/kimi-k3-1-pro",
            is_open=True,
        ),
        "DeepSeek V4.1 Flash 1017": ModelIdentity(
            "DeepSeek-V4.1-Flash-1017", arxiv_id="2609.19969", is_open=True
        ),
        "GPT-6.1 Terra": ModelIdentity(
            "GPT-6.1 Terra",
            source_url="https://openai.com/index/introducing-gpt-6-1-terra",
        ),
        "GLM 5.3": ModelIdentity(
            "GLM-5.3", source_url="https://z.ai/blog/glm-5.3", is_open=True
        ),
        "Qwen 3.8 Max 0902": ModelIdentity(
            "Qwen3.8-Max", source_url="https://qwen.ai/blog?id=qwen3.8", is_open=True
        ),
        "Claude Haiku 5.5": ModelIdentity(
            "Claude Haiku 5.5", source_url="https://www.anthropic.com/claude-haiku-5-5"
        ),
        "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
        "MiMo V2.6 Pro": ModelIdentity(
            "MiMo-V2.6-Pro", arxiv_id="2610.11959", is_open=True
        ),
        "Gemini 3.8 Flash": ModelIdentity(
            "Gemini 3.8 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
        ),
        "MiMo V2.6 Flash": ModelIdentity(
            "MiMo-V2.6-Flash", arxiv_id="2610.11959", is_open=True
        ),
        "MiniMax-M3.1-Flash": ModelIdentity(
            "MiniMax-M3.1-Flash",
            source_url="https://www.minimax.io/blog/minimax-m31f",
            is_open=True,
        ),
        "Hy4 Preview": ModelIdentity(
            "Hy4 Preview",
            source_url="https://github.com/Tencent-Hunyuan/Hy4-preview/blob/1296fab2674cb5a645ccfe53e9a8dc225dbe69f2/README.md",
            is_open=True,
        ),
        "DeepSeek V4 Pro 0813": ModelIdentity(
            "DeepSeek-V4-Pro", arxiv_id="2606.19348", is_open=True
        ),
        "Kimi K3": ModelIdentity("Kimi K3", arxiv_id="2607.24653", is_open=True),
        "GPT-6 Luna": ModelIdentity(
            "GPT-6 Luna",
            source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        ),
        "GLM 5.3 Flash": ModelIdentity(
            "GLM-5.3-Flash", source_url="https://z.ai/blog/glm-5.3-flash", is_open=True
        ),
        "Muse Spark Open": ModelIdentity(
            "Muse Spark Open",
            source_url="https://research.meta.ai/blog/muse-spark-open",
            is_open=True,
        ),
        "Beam 1.0": ModelIdentity(
            "Beam 1.0",
            source_url="https://reflection.ai/blog/introducing-beam",
            is_open=True,
        ),
        "Inkling": ModelIdentity(
            "Inkling",
            source_url="https://thinkingmachines.ai/news/introducing-inkling/",
            is_open=True,
        ),
        "Inkling Small": ModelIdentity(
            "Inkling Small",
            source_url="https://huggingface.co/thinkingmachines/Inkling-Small",
            is_open=True,
        ),
    },
    "swe-sweep": {
        "Sol 5.6 (xhigh)": ModelIdentity(
            "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Opus 5.5 (xhigh)": ModelIdentity(
            "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
        ),
        "Fable 5.1": ModelIdentity(
            "Claude Fable 5.1",
            source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
        ),
        "Luna 5.6 (xhigh)": ModelIdentity(
            "GPT-5.6 Luna", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Terra 5.6 (xhigh)": ModelIdentity(
            "GPT-5.6 Terra", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Luna 5.6 (high)": ModelIdentity(
            "GPT-5.6 Luna", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Opus 5 (xhigh)": ModelIdentity(
            "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
        ),
        "Kimi K3": ModelIdentity("Kimi K3", arxiv_id="2607.24653", is_open=True),
        "Luna 5.6": ModelIdentity(
            "GPT-5.6 Luna", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "GPT-5.4 Mini (high)": ModelIdentity(
            "GPT-5.4 Mini",
            source_url="https://openai.com/index/introducing-gpt-5-4-mini-and-nano/",
        ),
        "GPT-5.4 Mini": ModelIdentity(
            "GPT-5.4 Mini",
            source_url="https://openai.com/index/introducing-gpt-5-4-mini-and-nano/",
        ),
        "Gemini 3.5 Flash Lite": ModelIdentity(
            "Gemini 3.5 Flash-Lite",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
        ),
    },
    "vending-bench-2": {
        "Claude Fable 5 - High": ModelIdentity(
            "Claude Fable 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "Claude Fable 5 - Low": ModelIdentity(
            "Claude Fable 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "Claude Fable 5 - Max": ModelIdentity(
            "Claude Fable 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "Claude Fable 5 - Medium": ModelIdentity(
            "Claude Fable 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "Claude Fable 5 - None": ModelIdentity(
            "Claude Fable 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "Claude Fable 5.1": ModelIdentity(
            "Claude Fable 5.1",
            source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
        ),
        "Claude Haiku 4.5": ModelIdentity(
            "Claude Haiku 4.5", source_url="https://www.anthropic.com/claude/haiku"
        ),
        "Claude Haiku 5.5": ModelIdentity(
            "Claude Haiku 5.5", source_url="https://www.anthropic.com/claude-haiku-5-5"
        ),
        "Claude Opus 4.5": ModelIdentity(
            "Claude Opus 4.5",
            source_url="https://www.anthropic.com/news/claude-opus-4-5",
        ),
        "Claude Opus 4.6": ModelIdentity(
            "Claude Opus 4.6",
            source_url="https://www.anthropic.com/news/claude-opus-4-6",
        ),
        "Claude Opus 4.7": ModelIdentity(
            "Claude Opus 4.7",
            source_url="https://www.anthropic.com/news/claude-opus-4-7",
        ),
        "Claude Opus 4.8 - High": ModelIdentity(
            "Claude Opus 4.8",
            source_url="https://www.anthropic.com/news/claude-opus-4-8",
        ),
        "Claude Opus 4.8 - Max": ModelIdentity(
            "Claude Opus 4.8",
            source_url="https://www.anthropic.com/news/claude-opus-4-8",
        ),
        "Claude Opus 5": ModelIdentity(
            "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
        ),
        "Claude Opus 5.5": ModelIdentity(
            "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
        ),
        "Claude Sonnet 4.5": ModelIdentity(
            "Claude Sonnet 4.5",
            source_url="https://www.anthropic.com/news/claude-sonnet-4-5",
        ),
        "Claude Sonnet 4.6": ModelIdentity(
            "Claude Sonnet 4.6",
            source_url="https://www.anthropic.com/news/claude-sonnet-4-6",
        ),
        "Claude Sonnet 5": ModelIdentity(
            "Claude Sonnet 5",
            source_url="https://www.anthropic.com/news/claude-sonnet-5",
        ),
        "Claude Sonnet 5.5": ModelIdentity(
            "Claude Sonnet 5.5",
            source_url="https://www.anthropic.com/claude-sonnet-5-5",
        ),
        "DeepSeek-V3.2": ModelIdentity(
            "DeepSeek-V3.2", arxiv_id="2512.02556", is_open=True
        ),
        "Deepseek V4 Pro": ModelIdentity(
            "DeepSeek-V4-Pro", arxiv_id="2606.19348", is_open=True
        ),
        "GLM-4.7": ModelIdentity("GLM-4.7", arxiv_id="2508.06471", is_open=True),
        "GLM-5": ModelIdentity("GLM-5", arxiv_id="2602.15763", is_open=True),
        "GLM-5.1": ModelIdentity(
            "GLM-5.1", source_url="https://z.ai/blog/glm-5.1", is_open=True
        ),
        "GLM-5.2": ModelIdentity(
            "GLM-5.2", source_url="https://z.ai/blog/glm-5.2", is_open=True
        ),
        "GLM-5.3": ModelIdentity(
            "GLM-5.3", source_url="https://z.ai/blog/glm-5.3", is_open=True
        ),
        "GPT-5 mini": ModelIdentity(
            "GPT-5 mini", source_url="https://openai.com/index/introducing-gpt-5/"
        ),
        "GPT-5.2": ModelIdentity(
            "GPT-5.2", source_url="https://openai.com/index/introducing-gpt-5-2/"
        ),
        "GPT-5.3-Codex": ModelIdentity(
            "GPT-5.3-Codex",
            source_url="https://openai.com/index/introducing-gpt-5-3-codex/",
        ),
        "GPT-5.4": ModelIdentity(
            "GPT-5.4", source_url="https://openai.com/index/introducing-gpt-5-4/"
        ),
        "GPT-5.5": ModelIdentity(
            "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
        ),
        "GPT-5.6 Luna": ModelIdentity(
            "GPT-5.6 Luna", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "GPT-5.6 Sol": ModelIdentity(
            "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "GPT-5.6 Terra": ModelIdentity(
            "GPT-5.6 Terra", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "GPT-6 Astra": ModelIdentity(
            "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
        ),
        "GPT-6 Sol": ModelIdentity(
            "GPT-6 Sol",
            source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        ),
        "GPT-6.1 Terra": ModelIdentity(
            "GPT-6.1 Terra",
            source_url="https://openai.com/index/introducing-gpt-6-1-terra",
        ),
        "GPT-OSS-120b": ModelIdentity(
            "GPT-OSS-120b", arxiv_id="2508.10925", is_open=True
        ),
        "Gemini 2.5 Flash": ModelIdentity("Gemini 2.5 Flash", arxiv_id="2507.06261"),
        "Gemini 2.5 Pro": ModelIdentity("Gemini 2.5 Pro", arxiv_id="2507.06261"),
        "Gemini 3 Flash": ModelIdentity(
            "Gemini 3 Flash",
            source_url="https://blog.google/products-and-platforms/products/gemini/gemini-3-flash/",
        ),
        "Gemini 3 Pro": ModelIdentity(
            "Gemini 3 Pro",
            source_url="https://blog.google/products-and-platforms/products/gemini/gemini-3",
        ),
        "Gemini 3.1 Pro": ModelIdentity(
            "Gemini 3.1 Pro",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/",
        ),
        "Gemini 3.5 Flash": ModelIdentity(
            "Gemini 3.5 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
        ),
        "Gemini 3.8 Flash": ModelIdentity(
            "Gemini 3.8 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
        ),
        "Gemini 4 Argon": ModelIdentity(
            "Gemini 4 Argon",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/",
        ),
        "Gemini 4 Carbon": ModelIdentity(
            "Gemini 4 Carbon",
            source_url="https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/",
        ),
        "Grok 4.20": ModelIdentity(
            "Grok 4.20", source_url="https://docs.x.ai/developers/models/grok-4.20"
        ),
        "Grok 4.3": ModelIdentity(
            "Grok 4.3", source_url="https://docs.x.ai/developers/models/grok-4.3"
        ),
        "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
        "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
        "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
        "Kimi K2.5": ModelIdentity("Kimi K2.5", arxiv_id="2602.02276", is_open=True),
        "Kimi K2.6": ModelIdentity(
            "Kimi K2.6", source_url="https://www.kimi.com/blog/kimi-k2-6", is_open=True
        ),
        "Kimi K2.7 Code": ModelIdentity(
            "Kimi K2.7 Code",
            source_url="https://huggingface.co/moonshotai/Kimi-K2.7-Code",
            is_open=True,
        ),
        "Kimi K3 (Fireworks)": ModelIdentity(
            "Kimi K3", arxiv_id="2607.24653", is_open=True
        ),
        "Kimi K3 (Moonshot)": ModelIdentity(
            "Kimi K3", arxiv_id="2607.24653", is_open=True
        ),
        "MiniMax-M2": ModelIdentity("MiniMax-M2", arxiv_id="2605.26494", is_open=True),
        "MiniMax-M2.5": ModelIdentity(
            "MiniMax-M2.5",
            source_url="https://huggingface.co/MiniMaxAI/MiniMax-M2.5",
            is_open=True,
        ),
        "MiniMax-M3": ModelIdentity(
            "MiniMax-M3",
            source_url="https://www.minimax.io/blog/minimax-m3",
            is_open=True,
        ),
        "Muse Spark 1.1": ModelIdentity(
            "Muse Spark 1.1",
            source_url="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/",
        ),
        "Muse Wonder": ModelIdentity(
            "Muse Wonder", source_url="https://research.meta.ai/blog/muse-wonder"
        ),
        "Muse Wonder Full": ModelIdentity(
            "Muse Wonder Full", source_url="https://research.meta.ai/blog/muse-wonder"
        ),
        "Qwen 3.5 27B": ModelIdentity(
            "Qwen3.5-27B", source_url="https://qwen.ai/blog?id=qwen3.5", is_open=True
        ),
        "Qwen 3.5 35B A3B": ModelIdentity(
            "Qwen3.5-35B-A3B",
            source_url="https://qwen.ai/blog?id=qwen3.5",
            is_open=True,
        ),
        "Qwen 3.5 Plus": ModelIdentity(
            "Qwen3.5-Plus", source_url="https://qwen.ai/blog?id=qwen3.5"
        ),
        "Qwen 3.6 Plus": ModelIdentity(
            "Qwen3.6-Plus", source_url="https://qwen.ai/blog?id=qwen3.6"
        ),
        "Qwen3 235B A22B Thinking": ModelIdentity(
            "Qwen3 235B A22B Thinking", arxiv_id="2505.09388", is_open=True
        ),
    },
    "blueprint-bench-2": {
        "Gemini 4 Carbon": ModelIdentity(
            "Gemini 4 Carbon",
            source_url="https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/",
        ),
        "Gemini 4 Argon": ModelIdentity(
            "Gemini 4 Argon",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/",
        ),
        "Claude Opus 5.5": ModelIdentity(
            "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
        ),
        "GPT-6 Astra": ModelIdentity(
            "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
        ),
        "GPT-6.1 Terra": ModelIdentity(
            "GPT-6.1 Terra",
            source_url="https://openai.com/index/introducing-gpt-6-1-terra",
        ),
        "Claude Fable 5.1": ModelIdentity(
            "Claude Fable 5.1",
            source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
        ),
        "Claude Sonnet 5.5": ModelIdentity(
            "Claude Sonnet 5.5",
            source_url="https://www.anthropic.com/claude-sonnet-5-5",
        ),
        "Claude Fable 5": ModelIdentity(
            "Claude Fable 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "Gemini 3.8 Flash": ModelIdentity(
            "Gemini 3.8 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
        ),
        "GPT-6 Sol": ModelIdentity(
            "GPT-6 Sol",
            source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        ),
        "GPT-5.5": ModelIdentity(
            "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
        ),
        "Gemini 3.5 Flash": ModelIdentity(
            "Gemini 3.5 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
        ),
        "GPT-5.6 Sol": ModelIdentity(
            "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
        "Claude Haiku 5.5": ModelIdentity(
            "Claude Haiku 5.5", source_url="https://www.anthropic.com/claude-haiku-5-5"
        ),
        "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
        "Gemini 3.6 Flash": ModelIdentity(
            "Gemini 3.6 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
        ),
        "GPT-6 Luna": ModelIdentity(
            "GPT-6 Luna",
            source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        ),
        "GPT-5.6 Terra": ModelIdentity(
            "GPT-5.6 Terra", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Claude Opus 5": ModelIdentity(
            "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
        ),
        "Kimi K3": ModelIdentity("Kimi K3", arxiv_id="2607.24653", is_open=True),
        "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
        "GPT-5.4": ModelIdentity(
            "GPT-5.4", source_url="https://openai.com/index/introducing-gpt-5-4/"
        ),
        "Gemini 3.1 Pro": ModelIdentity(
            "Gemini 3.1 Pro",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/",
        ),
        "Claude Sonnet 5": ModelIdentity(
            "Claude Sonnet 5",
            source_url="https://www.anthropic.com/news/claude-sonnet-5",
        ),
        "Claude Opus 4.7": ModelIdentity(
            "Claude Opus 4.7",
            source_url="https://www.anthropic.com/news/claude-opus-4-7",
        ),
        "GPT-5.6 Luna": ModelIdentity(
            "GPT-5.6 Luna", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Claude Opus 4.8": ModelIdentity(
            "Claude Opus 4.8",
            source_url="https://www.anthropic.com/news/claude-opus-4-8",
        ),
        "Claude Sonnet 4.6": ModelIdentity(
            "Claude Sonnet 4.6",
            source_url="https://www.anthropic.com/news/claude-sonnet-4-6",
        ),
        "Kimi K2.6": ModelIdentity(
            "Kimi K2.6", source_url="https://www.kimi.com/blog/kimi-k2-6", is_open=True
        ),
    },
    "riemann-bench": {
        "GPT 5.6 Sol": ModelIdentity(
            "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "GPT 6 Astra": ModelIdentity(
            "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
        ),
        "Claude Opus 5.5": ModelIdentity(
            "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
        ),
        "Claude Opus 5": ModelIdentity(
            "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
        ),
        "GPT 5.6 Terra": ModelIdentity(
            "GPT-5.6 Terra", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Claude Fable 5.1": ModelIdentity(
            "Claude Fable 5.1",
            source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
        ),
        "GPT 6 Sol": ModelIdentity(
            "GPT-6 Sol",
            source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        ),
        "Claude Fable 5": ModelIdentity(
            "Claude Fable 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "GPT 6 Luna": ModelIdentity(
            "GPT-6 Luna",
            source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        ),
        "GPT 5.5": ModelIdentity(
            "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
        ),
        "Gemini 3.8 Flash": ModelIdentity(
            "Gemini 3.8 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
        ),
        "Claude Opus 4.8": ModelIdentity(
            "Claude Opus 4.8",
            source_url="https://www.anthropic.com/news/claude-opus-4-8",
        ),
        "GPT 5.4": ModelIdentity(
            "GPT-5.4", source_url="https://openai.com/index/introducing-gpt-5-4/"
        ),
        "Gemini 3.7 Flash": ModelIdentity(
            "Gemini 3.7 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-3-7-flash/",
        ),
        "DeepSeek V4 Pro": ModelIdentity(
            "DeepSeek-V4-Pro", arxiv_id="2606.19348", is_open=True
        ),
        "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
        "GPT 5.2": ModelIdentity(
            "GPT-5.2", source_url="https://openai.com/index/introducing-gpt-5-2/"
        ),
        "Kimi K3": ModelIdentity("Kimi K3", arxiv_id="2607.24653", is_open=True),
        "Gemini 3.5 Flash": ModelIdentity(
            "Gemini 3.5 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
        ),
        "Gemini 3.1 Pro": ModelIdentity(
            "Gemini 3.1 Pro",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/",
        ),
        "Claude Opus 4.7": ModelIdentity(
            "Claude Opus 4.7",
            source_url="https://www.anthropic.com/news/claude-opus-4-7",
        ),
        "Gemini 3.6 Flash": ModelIdentity(
            "Gemini 3.6 Flash",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
        ),
        "Muse Spark 1.3": ModelIdentity(
            "Muse Spark 1.3",
            source_url="https://research.meta.ai/blog/introducing-muse-spark-1-3",
        ),
        "Claude Opus 4.6": ModelIdentity(
            "Claude Opus 4.6",
            source_url="https://www.anthropic.com/news/claude-opus-4-6",
        ),
        "DeepSeek V4.1 Flash": ModelIdentity(
            "DeepSeek-V4.1-Flash", arxiv_id="2609.19969", is_open=True
        ),
        "Hy4 Preview": ModelIdentity(
            "Hy4 Preview",
            source_url="https://github.com/Tencent-Hunyuan/Hy4-preview/blob/1296fab2674cb5a645ccfe53e9a8dc225dbe69f2/README.md",
            is_open=True,
        ),
        "Muse Spark 1.2": ModelIdentity(
            "Muse Spark 1.2",
            source_url="https://developer.meta.com/ai/resources/blog/build-with-muse-code/",
        ),
        "Muse Spark 1.1": ModelIdentity(
            "Muse Spark 1.1",
            source_url="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/",
        ),
        "Qwen 3.7 Max": ModelIdentity(
            "Qwen3.7-Max", source_url="https://qwen.ai/blog?id=qwen3.7"
        ),
        "Qwen 3.8 Max": ModelIdentity(
            "Qwen3.8-Max", source_url="https://qwen.ai/blog?id=qwen3.8", is_open=True
        ),
        "Inkling": ModelIdentity(
            "Inkling",
            source_url="https://thinkingmachines.ai/news/introducing-inkling/",
            is_open=True,
        ),
        "Muse Glimmer 30B": ModelIdentity(
            "Muse Glimmer-30B", arxiv_id="2610.24628", is_open=True
        ),
        "GLM 5.3": ModelIdentity(
            "GLM-5.3", source_url="https://z.ai/blog/glm-5.3", is_open=True
        ),
        "Kimi K2.5": ModelIdentity("Kimi K2.5", arxiv_id="2602.02276", is_open=True),
        "Claude Opus 4.5": ModelIdentity(
            "Claude Opus 4.5",
            source_url="https://www.anthropic.com/news/claude-opus-4-5",
        ),
        "Gemini 3.5 Flash-Lite": ModelIdentity(
            "Gemini 3.5 Flash-Lite",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
        ),
        "DeepSeek V4 Flash": ModelIdentity(
            "DeepSeek-V4-Flash", arxiv_id="2606.19348", is_open=True
        ),
        "GLM 5.2": ModelIdentity(
            "GLM-5.2", source_url="https://z.ai/blog/glm-5.2", is_open=True
        ),
        "GLM 5.3 Flash": ModelIdentity(
            "GLM-5.3-Flash", source_url="https://z.ai/blog/glm-5.3-flash", is_open=True
        ),
        "DeepSeek V3.2": ModelIdentity(
            "DeepSeek-V3.2", arxiv_id="2512.02556", is_open=True
        ),
        "Kimi K2.6": ModelIdentity(
            "Kimi K2.6", source_url="https://www.kimi.com/blog/kimi-k2-6", is_open=True
        ),
        "DeepSeek V4 Pro (preview)": ModelIdentity(
            "DeepSeek-V4-Pro", arxiv_id="2606.19348", is_open=True
        ),
        "MAI Thinking 1": ModelIdentity(
            "MAI-Thinking-1",
            source_url="https://microsoft.ai/wp-content/uploads/2026/06/main_20260602_2.pdf",
        ),
    },
    "cwe-bench-v1": {
        "Gemini 4 Carbon": ModelIdentity(
            "Gemini 4 Carbon",
            source_url="https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/",
        ),
        "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
        "Gemini 4 Argon": ModelIdentity(
            "Gemini 4 Argon",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/",
        ),
        "GPT-6 Astra": ModelIdentity(
            "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
        ),
        "Claude Opus 5.5": ModelIdentity(
            "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
        ),
        "Claude Fable 5.1": ModelIdentity(
            "Claude Fable 5.1",
            source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
        ),
        "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
        "DeepSeek-V4.1-Flash": ModelIdentity(
            "DeepSeek-V4.1-Flash", arxiv_id="2609.19969", is_open=True
        ),
        "Muse Spark 1.3": ModelIdentity(
            "Muse Spark 1.3",
            source_url="https://research.meta.ai/blog/introducing-muse-spark-1-3",
        ),
        "Hy4 Preview": ModelIdentity(
            "Hy4 Preview",
            source_url="https://github.com/Tencent-Hunyuan/Hy4-preview/blob/1296fab2674cb5a645ccfe53e9a8dc225dbe69f2/README.md",
            is_open=True,
        ),
        "GPT-6 Sol": ModelIdentity(
            "GPT-6 Sol",
            source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        ),
        "Inkling": ModelIdentity(
            "Inkling",
            source_url="https://thinkingmachines.ai/news/introducing-inkling/",
            is_open=True,
        ),
    },
    "exploitgym": {
        "GPT-5.6 Sol": ModelIdentity(
            "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "Claude Mythos 5": ModelIdentity(
            "Claude Mythos 5",
            source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
        ),
        "Claude Opus 5": ModelIdentity(
            "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
        ),
        "Claude Opus 4.8": ModelIdentity(
            "Claude Opus 4.8",
            source_url="https://www.anthropic.com/news/claude-opus-4-8",
        ),
        "GLM-5.3": ModelIdentity(
            "GLM-5.3", source_url="https://z.ai/blog/glm-5.3", is_open=True
        ),
        "GLM-5.2": ModelIdentity(
            "GLM-5.2", source_url="https://z.ai/blog/glm-5.2", is_open=True
        ),
        "DeepSeek-V4.1-Flash": ModelIdentity(
            "DeepSeek-V4.1-Flash", arxiv_id="2609.19969", is_open=True
        ),
        "Claude Opus 5.5": ModelIdentity(
            "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
        ),
        "Claude Mythos 5.1": ModelIdentity(
            "Claude Mythos 5.1",
            source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
        ),
    },
    "cybergym": {
        # Upstream DeepSeek rows link the 0813 / 0731 checkpoints of the
        # DeepSeek-V4 report; the catalog names them by checkpoint and mode.
        "DeepSeek-V4-Pro": ModelIdentity(
            "DeepSeek-V4-Pro-0813 (Max)",
            arxiv_id="2606.19348",
            is_open=True,
            hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813",
        ),
        "DeepSeek-V4-Flash": ModelIdentity(
            "DeepSeek-V4-Flash-0731 (Max)",
            arxiv_id="2606.19348",
            is_open=True,
            hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731",
        ),
        "Gemini 3.8 Flash Cyber": ModelIdentity(
            "Gemini 3.8 Flash Cyber",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
        ),
        "GLM-5.3": ModelIdentity(
            "GLM-5.3",
            source_url="https://z.ai/blog/glm-5.3",
            is_open=True,
            hf_model_url="https://huggingface.co/zai-org/GLM-5.3",
        ),
        "GLM-5.2": ModelIdentity(
            "GLM-5.2",
            source_url="https://z.ai/blog/glm-5.2",
            is_open=True,
            hf_model_url="https://huggingface.co/zai-org/GLM-5.2",
        ),
        "GLM-5.1": ModelIdentity(
            "GLM-5.1",
            source_url="https://z.ai/blog/glm-5.1",
            is_open=True,
            hf_model_url="https://huggingface.co/zai-org/GLM-5.1",
        ),
        "GLM-5": ModelIdentity(
            "GLM-5",
            arxiv_id="2602.15763",
            is_open=True,
            hf_model_url="https://huggingface.co/zai-org/GLM-5",
        ),
        "GPT-5.5": ModelIdentity(
            "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
        ),
        "GPT-5.4": ModelIdentity(
            "GPT-5.4", source_url="https://openai.com/index/introducing-gpt-5-4/"
        ),
        "GPT-5": ModelIdentity(
            "GPT-5", source_url="https://openai.com/index/introducing-gpt-5/"
        ),
        "o4-mini": ModelIdentity(
            "o4-mini", source_url="https://openai.com/index/introducing-o3-and-o4-mini/"
        ),
        "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
        "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
        "Claude Opus 4.6": ModelIdentity(
            "Claude Opus 4.6",
            source_url="https://www.anthropic.com/news/claude-opus-4-6",
        ),
        "Claude Sonnet 4.6": ModelIdentity(
            "Claude Sonnet 4.6",
            source_url="https://www.anthropic.com/news/claude-sonnet-4-6",
        ),
        "Claude Opus 4.5": ModelIdentity(
            "Claude Opus 4.5",
            source_url="https://www.anthropic.com/news/claude-opus-4-5",
        ),
        "Claude Sonnet 4.5": ModelIdentity(
            "Claude Sonnet 4.5",
            source_url="https://www.anthropic.com/news/claude-sonnet-4-5",
        ),
        "Claude Opus 4.1": ModelIdentity(
            "Claude Opus 4.1",
            source_url="https://www.anthropic.com/news/claude-opus-4-1",
        ),
        "Claude Sonnet 4": ModelIdentity(
            "Claude Sonnet 4", source_url="https://www.anthropic.com/news/claude-4"
        ),
        "Claude Sonnet 3.7": ModelIdentity(
            "Claude 3.7 Sonnet",
            source_url="https://www.anthropic.com/news/claude-3-7-sonnet",
        ),
        "Gemini 3.1 Pro": ModelIdentity(
            "Gemini 3.1 Pro",
            source_url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/",
        ),
        "Gemini 2.5 Flash Preview": ModelIdentity(
            "Gemini 2.5 Flash Preview", arxiv_id="2507.06261"
        ),
        # The May 2026 safety report evaluates the original API model, not
        # the October open-weight Muse Spark Open release.
        "Muse Spark": ModelIdentity("Muse Spark", arxiv_id="2606.12429"),
        "Muse Spark 1.1 (helpful-only)": ModelIdentity(
            "Muse Spark 1.1 (helpful-only)",
            source_url="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/",
        ),
        "Kimi K2.5": ModelIdentity(
            "Kimi K2.5",
            arxiv_id="2602.02276",
            is_open=True,
            hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.5",
        ),
        "DeepSeek-V3": ModelIdentity(
            "DeepSeek-V3",
            arxiv_id="2412.19437",
            is_open=True,
            hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V3",
        ),
        "Qwen3-235B-A22B": ModelIdentity(
            "Qwen3-235B-A22B",
            arxiv_id="2505.09388",
            is_open=True,
            hf_model_url="https://huggingface.co/Qwen/Qwen3-235B-A22B",
        ),
        "R2E-Gym-32B": ModelIdentity(
            "R2E-Gym-32B", arxiv_id="2504.07164", is_open=True
        ),
        "SWE-Gym-32B": ModelIdentity(
            "SWE-Gym-32B", arxiv_id="2412.21139", is_open=True
        ),
    },
    "patcheval-verified": {
        "gpt-5.6-sol": ModelIdentity(
            "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
        ),
        "gpt-5.5": ModelIdentity(
            "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
        ),
        "gpt-5.4": ModelIdentity(
            "GPT-5.4", source_url="https://openai.com/index/introducing-gpt-5-4/"
        ),
        "DeepSeek-V4-Flash-0731": ModelIdentity(
            "DeepSeek-V4-Flash-0731",
            arxiv_id="2606.19348",
            is_open=True,
            hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731",
        ),
        "seed-2.1-turbo": ModelIdentity(
            "Seed2.1 Turbo",
            source_url="https://lf3-static.bytednsdoc.com/obj/eden-cn/lapzild-tss/ljhwZthlaukjlkulzlp/seed2.1/Seed2_1_Model_Card.pdf",
        ),
        "kimi-2.7-code": ModelIdentity(
            "Kimi K2.7 Code",
            source_url="https://huggingface.co/moonshotai/Kimi-K2.7-Code",
            is_open=True,
            hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.7-Code",
        ),
        "GLM 5.2": ModelIdentity(
            "GLM-5.2",
            source_url="https://z.ai/blog/glm-5.2",
            is_open=True,
            hf_model_url="https://huggingface.co/zai-org/GLM-5.2",
        ),
        "MiniMax-M3": ModelIdentity(
            "MiniMax-M3",
            source_url="https://www.minimax.io/blog/minimax-m3",
            is_open=True,
            hf_model_url="https://huggingface.co/MiniMaxAI/MiniMax-M3",
        ),
        "qwen3.7 plus": ModelIdentity(
            "Qwen3.7-Plus", source_url="https://www.qwencloud.com/models/qwen3.7-plus"
        ),
    },
}
