window.FRSI = {
 "categories": [
  {
   "id": "pretrain",
   "name": "Pre-training",
   "blurb": "Optimizers, objectives, architectures and training of draft models, scored on held-out loss or latency."
  },
  {
   "id": "posttrain",
   "name": "Post-train and harness",
   "blurb": "Design RL data that teaches a small model multi-step coding, or improve the harness around a fixed worker model."
  },
  {
   "id": "inference",
   "name": "Inference and serving",
   "blurb": "Scheduling, routing, caching and batching for frozen-model serving, with exact greedy outputs."
  },
  {
   "id": "kernels",
   "name": "Kernels",
   "blurb": "Fast, numerically correct H100 kernels for attention, matrix products and sampling."
  }
 ],
 "tasks": [
  {
   "id": "model-shape-efficiency",
   "category": "pretrain",
   "title": "Choose a transformer shape",
   "metric": "total decode time (ms)",
   "digits": 1,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 522.2626717493768,
   "best_model": "Gemini 4 Carbon",
   "anchor_raw": 624.815046349795,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.75
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.5132510496750036
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.5
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.4620986787113236
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.3969627298434685
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.3952745351020036
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.25
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.25
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.25
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "language-model-optimizer",
   "category": "pretrain",
   "title": "Design the optimizer",
   "metric": "held-out loss (nats/token)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 4.120259951580749,
   "best_model": "Gemini 4 Carbon",
   "anchor_raw": 4.125242555379501,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.9497043589777413
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.9058696622572022
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.902130416130454
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.8890803766361502
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.8840433130442248
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.8520787693085853
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.8315243986479492
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.8062325356560447
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.8053704628339657
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.7897980320764878
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.6472314779685914
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.5776499464733382
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.215209950043117
    }
   ]
  },
  {
   "id": "training-objective-design",
   "category": "pretrain",
   "title": "Design the training objective",
   "metric": "held-out loss (nats/token)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 4.2501733916512645,
   "best_model": "Claude Opus 5.5",
   "anchor_raw": 4.2501733916512645,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.7330354299204378
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.6145356595895923
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.472064258479716
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.43210883022515206
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.24525712932717134
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.18580415664602484
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.06466755913751368
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.023682647550291515
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "long-sequence-computation",
   "category": "pretrain",
   "title": "Speed up long-context attention",
   "metric": "full-forward latency (ms)",
   "digits": 2,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 13.720738563260682,
   "best_model": "Gemini 4 Argon",
   "anchor_raw": 13.720738563260682,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.25
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "speculative-draft-training",
   "category": "pretrain",
   "title": "Train a speculative draft model",
   "metric": "decode time (ms/token)",
   "digits": 2,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 9.130249607180659,
   "best_model": "GPT-6.2 Astra",
   "anchor_raw": 9.878943214035342,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.8606790314021715
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.7477432711908889
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.27970120877860605
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.21647490563046204
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.20029643278055184
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.06199890750288663
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "pt-multifile-numpy-rl-qwen3-4b",
   "category": "posttrain",
   "title": "RL data: NumPy bug fixing",
   "metric": "hidden projects solved",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.8633,
   "best_model": "GPT-6 Astra",
   "anchor_raw": 0.6333,
   "hours": 8.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.5
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.22394599715774538
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.039594189167850874
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "pt-multifile-scipy-rl-qwen3-4b",
   "category": "posttrain",
   "title": "RL data: SciPy bug fixing",
   "metric": "hidden projects solved",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.8333,
   "best_model": "Kimi K3.1 Pro",
   "anchor_raw": 0.8333,
   "hours": 8.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "pt-chained-rl-qwen3-4b",
   "category": "posttrain",
   "title": "RL data: chained bugs",
   "metric": "hidden projects solved",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.4967,
   "best_model": "Gemini 4 Argon",
   "anchor_raw": 0.4967,
   "hours": 8.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.25
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.1659452385745923
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.1476746527078721
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.08189047714918467
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "pt-interfaceport-easy-rl-qwen3-4b",
   "category": "posttrain",
   "title": "RL data: interface porting",
   "metric": "hidden projects solved",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.5433,
   "best_model": "Claude Opus 5.5",
   "anchor_raw": 0.43,
   "hours": 8.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.75
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.6726744186046513
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.5
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.3255813953488373
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.25
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.25
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "pt-multifile-rl-qwen3-4b",
   "category": "posttrain",
   "title": "RL data: multi-file bug fixing",
   "metric": "hidden projects solved",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.85,
   "best_model": "Inkling 2 Small",
   "anchor_raw": 0.8267,
   "hours": 8.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.3487964194992137
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.2880125801378979
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.25
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.21975928389984273
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.17923672432563215
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.07853513971210851
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.03831498729889945
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.02803314382484577
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.02803314382484577
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "bfcl-harness",
   "category": "posttrain",
   "title": "Harness: BFCL v4 multi-turn",
   "metric": "held-out success",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.75,
   "best_model": "Gemini 4 Neon",
   "anchor_raw": 0.6666666666666666,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "A100-80",
   "models": [
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.49999999999999994
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.09375000000000008
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "swe-bench-harness",
   "category": "posttrain",
   "title": "Harness: SWE-bench Verified",
   "metric": "held-out success",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.75,
   "best_model": "Claude Opus 5.5",
   "anchor_raw": 0.6666666666666666,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "A100-80",
   "models": [
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "webarena-verified-harness",
   "category": "posttrain",
   "title": "Harness: WebArena-Verified",
   "metric": "held-out success",
   "digits": 3,
   "percent": true,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 0.5,
   "best_model": "Claude Opus 5.5",
   "anchor_raw": 0.5,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "A100-80",
   "models": [
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.041666666666666526
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.04166666666666652
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "bulk-inference",
   "category": "inference",
   "title": "Bulk inference",
   "metric": "throughput (output tokens/s)",
   "digits": 0,
   "percent": false,
   "suffix": "",
   "direction": "maximize",
   "best_raw": 6640.464162203749,
   "best_model": "GPT-6.2 Astra",
   "anchor_raw": 4454.419949047416,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.948846962869472
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.9466948422597194
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.75
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.210459457106796
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.11330483383558465
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "cache-aware-replica-routing",
   "category": "inference",
   "title": "Cache-aware replica routing",
   "metric": "speedup over the starter",
   "digits": 3,
   "percent": false,
   "suffix": "\u00d7",
   "direction": "maximize",
   "best_raw": 1.7306763131373926,
   "best_model": "Claude Fable 5.2",
   "anchor_raw": 1.716622137413676,
   "hours": 0.75,
   "gpus": 2,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.7681702092125022
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.4373387144503348
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.41240395800015595
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.34924400754807
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.2605993105264021
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.15760337099909477
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.13639086927219138
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.12573393813871758
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0971883127973893
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.007435451394348464
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "separated-prefill-and-decode",
   "category": "inference",
   "title": "Disaggregated prefill and decode",
   "metric": "stream duration (s)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 3.6879725226500057,
   "best_model": "GPT-6.2 Astra",
   "anchor_raw": 3.832830198025002,
   "hours": 4.0,
   "gpus": 2,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.75
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.7223575744111498
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.6345438007867732
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.5373254345033381
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.470974342277277
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.45977956495970823
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.4568524325923775
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.3918592171439625
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.34417828635445347
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.18898253175569527
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "adaptive-prefill-chunking",
   "category": "inference",
   "title": "Schedule prefill and decode",
   "metric": "speedup over the starter",
   "digits": 3,
   "percent": false,
   "suffix": "\u00d7",
   "direction": "maximize",
   "best_raw": 1.7654725881629019,
   "best_model": "GPT-6.2 Sol",
   "anchor_raw": 1.6713197051824389,
   "hours": 0.75,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.6984104299216042
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.6743830705155283
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.5994718011160676
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.5848767481088153
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.5605367640786078
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.547913017740956
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.4537144969272441
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.4134264300453441
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.37123265424675167
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.34760118240549415
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.331402834658783
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.27955159666638146
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.024604146295744596
    }
   ]
  },
  {
   "id": "branch-sharing-generation",
   "category": "inference",
   "title": "Shared-prompt branch generation",
   "metric": "workload time (s)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 1.018688812162577,
   "best_model": "Claude Fable 5.2",
   "anchor_raw": 1.0614567414500022,
   "hours": 4.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.6914165525779491
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "kernel-parameter-update",
   "category": "kernels",
   "title": "AdamW parameter update",
   "metric": "100-case sweep time (ms)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 2.9314239025115967,
   "best_model": "Kimi K3.1 Pro",
   "anchor_raw": 2.9314239025115967,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.8830381944034961
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.6387990418764661
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.5220697238119693
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.4971040926833487
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.43339185442091915
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.42798831877232935
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.41887579976809014
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.3669041005400203
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.33991094389612686
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.29189326101725377
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.18934924068034897
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.12850802214149942
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.09731490116982272
    }
   ]
  },
  {
   "id": "kernel-masked-attention",
   "category": "kernels",
   "title": "Block-masked attention, forward and backward",
   "metric": "100-case sweep time (ms)",
   "digits": 2,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 47.7825927734375,
   "best_model": "Gemini 4 Neon",
   "anchor_raw": 51.023841857910156,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.9805494245713499
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.9398843520519538
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.5579673882146838
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.5325409099588396
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.4601284436414559
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.4313131999969496
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.41397395136245874
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.1932936212029161
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.1642615834481816
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "kernel-causal-attention",
   "category": "kernels",
   "title": "Causal attention, forward and backward",
   "metric": "100-case sweep time (ms)",
   "digits": 2,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 96.30374145507812,
   "best_model": "Gemini 4 Carbon",
   "anchor_raw": 96.30374145507812,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.8064066440809446
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.746206464626811
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.6464135831536836
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.21535512065383003
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.20924328615598314
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.06340523249973579
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.053100622337935666
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.03803210384699835
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.027468833193215532
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "kernel-independent-matrix-workload",
   "category": "kernels",
   "title": "Grouped matrix products",
   "metric": "100-case sweep time (ms)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 5.817887783050537,
   "best_model": "Gemini 4 Neon",
   "anchor_raw": 6.593599796295166,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.9573695699982521
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.662516295998613
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.38785472882453076
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.2701343404267102
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.10545620081775946
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "kernel-projected-state-attention",
   "category": "kernels",
   "title": "Latent-projected attention",
   "metric": "100-case sweep time (ms)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 2.354048013687134,
   "best_model": "Claude Opus 5.5",
   "anchor_raw": 2.3540799617767334,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.5
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "kernel-fragmented-state-attention",
   "category": "kernels",
   "title": "Paged attention",
   "metric": "100-case sweep time (ms)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 0.521888017654419,
   "best_model": "GPT-6 Astra",
   "anchor_raw": 0.5534399747848511,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.5
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.25
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  },
  {
   "id": "kernel-rectangular-matrix-workload",
   "category": "kernels",
   "title": "Rectangular matrix products",
   "metric": "100-case sweep time (ms)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 3.332672119140625,
   "best_model": "GPT-6.1 Sol",
   "anchor_raw": 3.3855679035186768,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 1.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.9467904136738182
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.9439405395778523
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.9436005067851279
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.9293091471673336
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.9014709824951245
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.8900721199095697
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.8844149946539113
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.8321839929166701
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.7386101690403469
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.7121118539931511
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.6794460476020557
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.6147102052302305
    }
   ]
  },
  {
   "id": "kernel-single-query-attention",
   "category": "kernels",
   "title": "Single-query decode attention",
   "metric": "100-case sweep time (ms)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 9.045663833618164,
   "best_model": "Gemini 4 Carbon",
   "anchor_raw": 9.216575622558594,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.7168767616418397
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.6896831424586206
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.6892144836449273
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.6393031348429472
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.5311772837707514
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.5110144780573407
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.4931016071554214
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.4849770236375598
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.47749340871746243
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.47252462159622816
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.2806464371893193
    },
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.26770188777642995
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.17457477432359136
    }
   ]
  },
  {
   "id": "kernel-logit-selection",
   "category": "kernels",
   "title": "Top-k and top-p sampling",
   "metric": "100-case sweep time (ms)",
   "digits": 3,
   "percent": false,
   "suffix": "",
   "direction": "minimize",
   "best_raw": 1.8384640216827393,
   "best_model": "GPT-6.2 Astra",
   "anchor_raw": 1.9459840059280396,
   "hours": 2.0,
   "gpus": 1,
   "gpu_type": "H100",
   "models": [
    {
     "model": "GPT-6.2 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.2898072248651794
    },
    {
     "model": "Gemini 4 Carbon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.25
    },
    {
     "model": "Gemini 4 Neon",
     "harness": "Antigravity CLI",
     "effort": "xhigh",
     "avg": 0.25
    },
    {
     "model": "Claude Fable 5.2",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Claude Opus 5.5",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Kimi K3.1 Pro",
     "harness": "Claude Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.1 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6 Astra",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "GPT-6.2 Sol",
     "harness": "Codex",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Gemini 4 Argon",
     "harness": "Antigravity CLI",
     "effort": "high",
     "avg": 0.0
    },
    {
     "model": "Grok 4.7",
     "harness": "Grok Build",
     "effort": "xhigh",
     "avg": 0.0
    },
    {
     "model": "Muse Wonder 1.0",
     "harness": "Muse Code",
     "effort": "max",
     "avg": 0.0
    },
    {
     "model": "Inkling 2 Small",
     "harness": "mini-swe-agent",
     "effort": "max",
     "avg": 0.0
    }
   ]
  }
 ],
 "models": {
  "Claude Fable 5.2": {
   "color": "#D62F26",
   "lab": "Anthropic",
   "release": "2026-11-09"
  },
  "Claude Opus 5.5": {
   "color": "#F08A12",
   "lab": "Anthropic",
   "release": "2026-09-22"
  },
  "GPT-6.1 Sol": {
   "color": "#5FB3E6",
   "lab": "OpenAI",
   "release": "2026-09-29"
  },
  "GPT-6 Astra": {
   "color": "#1D4FC4",
   "lab": "OpenAI",
   "release": "2026-09-04"
  },
  "Gemini 4 Carbon": {
   "color": "#146B34",
   "lab": "Google",
   "release": "2026-11-10"
  },
  "Gemini 4 Argon": {
   "color": "#7FCF5A",
   "lab": "Google",
   "release": "2026-10-13"
  },
  "Kimi K3.1 Pro": {
   "color": "#7B3FC4",
   "lab": "Moonshot",
   "release": "2026-10-23"
  },
  "Muse Wonder 1.0": {
   "color": "#959595",
   "lab": "Meta",
   "release": "2026-10-12"
  },
  "Grok 4.7": {
   "color": "#111111",
   "lab": "xAI",
   "release": "2026-09-21"
  },
  "GPT-6.2 Sol": {
   "color": "#2BB3B1",
   "lab": "OpenAI",
   "release": "2026-11-17"
  },
  "GPT-6.2 Astra": {
   "color": "#23308F",
   "lab": "OpenAI",
   "release": "2026-11-17"
  },
  "Gemini 4 Neon": {
   "color": "#E8C21E",
   "lab": "Google",
   "release": "2026-11-18"
  },
  "Inkling 2 Small": {
   "color": "#D9548A",
   "lab": "Thinking Machines",
   "release": "2026-11-05"
  }
 },
 "stats": {
  "tasks": 27,
  "agent_trials": 1404,
  "agent_hours": 3753,
  "models": 13
 }
};
