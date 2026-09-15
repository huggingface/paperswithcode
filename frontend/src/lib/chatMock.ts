/**
 * Scripted mock for the chat SSE stream (see `chat.ts`).
 *
 * Replays a canned assistant turn — reasoning → search_papers → reasoning →
 * search_papers → cited answer — with realistic pacing, emitting hits in the
 * live transport shape (`route_id` + bounded `content` + structured
 * `metadata`, no score). One hit is an external (non-arXiv) resource with a
 * numeric route_id to exercise that path. Used by builds without
 * `VITE_CHAT_LIVE=1` (see the `isChatLive()` switch in `chat.ts`).
 */

import type { ChatEvent, ChatPaperHit, ChatPaperMetadata } from "@/lib/chat";

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(finish, ms);
    function finish() {
      signal?.removeEventListener("abort", finish);
      clearTimeout(timer);
      resolve();
    }
    signal?.addEventListener("abort", finish);
  });

const meta = (m: Partial<ChatPaperMetadata>): ChatPaperMetadata => ({
  arxiv_id: null,
  source: "arxiv",
  source_url: null,
  thumbnail_url: null,
  authors: [],
  published: null,
  conference: null,
  citation_count: null,
  tasks: [],
  methods: [],
  repositories: [],
  project_pages: [],
  ...m,
});

const OBJECT_DETECTION = { name: "Object Detection", slug: "object-detection" };
const REAL_TIME = { name: "Real-Time Object Detection", slug: "real-time-object-detection" };

/** Every paper the scripted turn can return or cite, keyed by route_id. */
const PAPERS: Record<string, ChatPaperHit> = {
  "2502.12524": {
    route_id: "2502.12524",
    title: "YOLOv12: Attention-Centric Real-Time Object Detectors",
    content:
      "Enhancing the network architecture of the YOLO framework has been crucial for a long time. This work introduces an attention-centric YOLO framework, namely YOLOv12, built around area attention and residual efficient layer aggregation networks (R-ELAN). YOLOv12-N reaches 40.6 mAP at 1.64 ms on a T4 GPU, closing the gap to attention-based detectors without the usual latency penalty and surpassing YOLOv10/YOLOv11 by +1.2–1.6 mAP at matched latency.",
    content_truncated: false,
    metadata: meta({
      arxiv_id: "2502.12524",
      authors: [{ name: "Y. Tian" }, { name: "Q. Ye" }, { name: "D. Doermann" }],
      published: "2025-02-18",
      citation_count: 412,
      tasks: [OBJECT_DETECTION, REAL_TIME],
      methods: [{ name: "Area Attention", slug: "area-attention" }],
      repositories: [{ url: "https://github.com/sunsmarterjie/yolov12", stars: 18700 }],
    }),
  },
  "2407.17140": {
    route_id: "2407.17140",
    title: "RT-DETRv2: Improved Baseline with Bag-of-Freebies for Real-Time Detection",
    content:
      "RT-DETRv2 improves the real-time DETR baseline with selective multi-scale feature extraction, a discrete sampling operator to ease deployment, and training-only 'bag-of-freebies' that add no inference cost. RT-DETRv2-R18/R50/R101 reach 47.9 / 53.4 / 54.3 mAP on COCO at 217 / 108 / 74 FPS on T4 TensorRT FP16, remaining NMS-free end to end.",
    content_truncated: false,
    metadata: meta({
      arxiv_id: "2407.17140",
      authors: [{ name: "W. Lv" }, { name: "Y. Zhao" }, { name: "J. Chang" }],
      published: "2024-07-24",
      citation_count: 268,
      tasks: [OBJECT_DETECTION, REAL_TIME],
      methods: [{ name: "DETR", slug: "detr" }],
      repositories: [{ url: "https://github.com/lyuwenyu/RT-DETR", stars: 9400 }],
    }),
  },
  "2410.13842": {
    route_id: "2410.13842",
    title: "D-FINE: Redefining Regression as Fine-grained Distribution Refinement",
    content:
      "D-FINE reformulates bounding-box regression in DETR-style detectors as iterative refinement of probability distributions (FDR) and adds a localization self-distillation scheme (GO-LSD). D-FINE-L reaches 54.0 mAP at ~9 ms and D-FINE-X 55.8 mAP on COCO while staying real-time on modern GPUs, dominating RT-DETRv2 and YOLOv10 on the accuracy–latency Pareto front.",
    content_truncated: false,
    metadata: meta({
      arxiv_id: "2410.13842",
      authors: [{ name: "Y. Peng" }, { name: "H. Li" }, { name: "P. Wu" }],
      published: "2024-10-17",
      conference: "ICLR 2025",
      citation_count: 187,
      tasks: [OBJECT_DETECTION, REAL_TIME],
      methods: [{ name: "Knowledge Distillation", slug: "knowledge-distillation" }],
      repositories: [{ url: "https://github.com/Peterande/D-FINE", stars: 12100 }],
    }),
  },
  "2406.03459": {
    route_id: "2406.03459",
    title: "LW-DETR: A Transformer Replacement to YOLO for Real-Time Detection",
    content:
      "LW-DETR pairs a plain ViT encoder with a lightweight DETR decoder and shows the combination outperforms YOLOv8 and YOLO-NAS at comparable latency, arguing transformer detectors are viable even at the fast end of the accuracy–latency curve. Uses multi-level feature aggregation, window-attention interleaving, and IoU-aware classification.",
    content_truncated: false,
    metadata: meta({
      arxiv_id: "2406.03459",
      authors: [{ name: "Q. Chen" }, { name: "X. Su" }, { name: "X. Zhang" }],
      published: "2024-06-05",
      citation_count: 94,
      tasks: [OBJECT_DETECTION, REAL_TIME],
      methods: [{ name: "Vision Transformer", slug: "vision-transformer" }],
      repositories: [{ url: "https://github.com/Atten4Vis/LW-DETR", stars: 5200 }],
    }),
  },
  "2304.08069": {
    route_id: "2304.08069",
    title: "DETRs Beat YOLOs on Real-time Object Detection",
    content:
      "RT-DETR is the first real-time end-to-end object detector, built on an efficient hybrid encoder that decouples intra-scale interaction and cross-scale fusion, plus IoU-aware query selection. RT-DETR-R50 achieves 53.1 mAP at 108 FPS on COCO, beating comparably sized YOLO detectors in both speed and accuracy while eliminating NMS entirely; its Figure 1 accuracy–latency plot became the reference for later real-time detectors.",
    content_truncated: false,
    metadata: meta({
      arxiv_id: "2304.08069",
      authors: [{ name: "Y. Zhao" }, { name: "W. Lv" }, { name: "S. Xu" }],
      published: "2023-04-17",
      conference: "CVPR 2024",
      citation_count: 2310,
      tasks: [OBJECT_DETECTION, REAL_TIME],
      methods: [{ name: "DETR", slug: "detr" }],
      repositories: [{ url: "https://github.com/lyuwenyu/RT-DETR", stars: 9400 }],
    }),
  },
  "2405.14458": {
    route_id: "2405.14458",
    title: "YOLOv10: Real-Time End-to-End Object Detection",
    content:
      "YOLOv10 removes NMS from the YOLO pipeline via consistent dual assignments during training and applies a holistic efficiency–accuracy driven design across the architecture. YOLOv10-S is 1.8x faster than RT-DETR-R18 at similar COCO accuracy; the family spans 46.3–54.4 mAP with substantially lower end-to-end latency than prior YOLOs because post-processing disappears.",
    content_truncated: false,
    metadata: meta({
      arxiv_id: "2405.14458",
      authors: [{ name: "A. Wang" }, { name: "H. Chen" }, { name: "L. Liu" }],
      published: "2024-05-23",
      conference: "NeurIPS 2024",
      citation_count: 1650,
      tasks: [OBJECT_DETECTION, REAL_TIME],
      methods: [{ name: "NMS-free Training", slug: "nms-free-training" }],
      repositories: [{ url: "https://github.com/THU-MIG/yolov10", stars: 44200 }],
    }),
  },
  "2401.17270": {
    route_id: "2401.17270",
    title: "YOLO-World: Real-Time Open-Vocabulary Object Detection",
    content:
      "YOLO-World extends the YOLO paradigm to open-vocabulary detection through vision-language modeling with a re-parameterizable vision-language path aggregation network (RepVL-PAN) and region-text contrastive pretraining. It detects categories never seen at training time while running at 35+ FPS, and its prompt-then-detect deployment re-parameterizes text embeddings for zero runtime text-encoder cost.",
    content_truncated: false,
    metadata: meta({
      arxiv_id: "2401.17270",
      authors: [{ name: "T. Cheng" }, { name: "L. Song" }, { name: "Y. Ge" }],
      published: "2024-01-30",
      conference: "CVPR 2024",
      citation_count: 890,
      tasks: [
        { name: "Open-Vocabulary Object Detection", slug: "open-vocabulary-object-detection" },
        OBJECT_DETECTION,
      ],
      methods: [{ name: "Contrastive Learning", slug: "contrastive-learning" }],
      repositories: [{ url: "https://github.com/AILab-CVC/YOLO-World", stars: 16800 }],
    }),
  },
  // External resource (no arXiv ID): numeric internal route_id.
  "158342": {
    route_id: "158342",
    title: "Ultralytics YOLO: real-time detection framework and model zoo",
    content:
      "Official Ultralytics framework release covering YOLO11 and YOLOv12 deployment: pretrained COCO checkpoints from nano to x-large, TensorRT/ONNX/CoreML export paths, and reproducible latency benchmarks on T4, Jetson Orin, and CPU targets. Widely used as the practical baseline for real-time detection deployments.",
    content_truncated: false,
    metadata: meta({
      source: "external",
      source_url: "https://docs.ultralytics.com/models/",
      authors: [{ name: "Ultralytics" }],
      published: "2025-01-02",
      tasks: [OBJECT_DETECTION, REAL_TIME],
      repositories: [{ url: "https://github.com/ultralytics/ultralytics", stars: 46000 }],
      project_pages: [{ url: "https://docs.ultralytics.com" }],
    }),
  },
};

const results = (ids: string[]): ChatPaperHit[] => ids.map((id) => PAPERS[id]);

const FIRST_SEARCH = results([
  "2502.12524",
  "2407.17140",
  "2410.13842",
  "2406.03459",
  "2304.08069",
  "2405.14458",
  "2401.17270",
  "158342",
]);

const SECOND_SEARCH = results([
  "2410.13842",
  "2502.12524",
  "2407.17140",
  "2405.14458",
  "2304.08069",
]);

const REASONING_1 =
  "The user wants the current state-of-the-art for real-time object detection. That's a moving target split across two lineages — the YOLO family (fast CNN one-stage detectors) and the DETR family (transformer, end-to-end, NMS-free). I should ground the answer in recent papers benchmarked on COCO with reported latency or FPS, not just accuracy. Let me start with a broad hybrid search, see which papers surface, then run a second, narrower query to pin down the head-to-head COCO mAP vs latency trade-offs before I write anything.";

const REASONING_2 =
  "Good — both lineages are well represented. YOLOv12, YOLOv10 and RT-DETRv2 / D-FINE keep coming up. To actually rank them I need the accuracy-vs-latency numbers side by side on the same COCO val2017 protocol, so let me narrow the query to the benchmark comparison specifically.";

const ANSWER = `There isn't a single winner — real-time object detection in 2026 is a two-horse race between the [YOLO family](paper:2502.12524) (fast one-stage CNNs) and the end-to-end [DETR family](paper:2304.08069) (NMS-free transformers). Which one is “SOTA” depends entirely on where you sit on the accuracy-vs-latency curve.

**At the fast / edge end**, [YOLOv12](paper:2502.12524) is the current leader. Its area-attention design pushes attention into the YOLO backbone without the usual latency hit — YOLOv12-N reaches 40.6 mAP at ~1.6 ms on a T4, roughly +1.5 mAP over [YOLOv10](paper:2405.14458) at matched speed. [YOLOv10](paper:2405.14458) is still very relevant because it made the YOLO head NMS-free, cutting real end-to-end latency.

**At the high-accuracy end**, the transformer detectors win. [D-FINE](paper:2410.13842) currently holds the accuracy-latency Pareto front, reporting 55.8 mAP by reformulating box regression as fine-grained distribution refinement with self-distillation. It builds on [RT-DETRv2](paper:2407.17140), which hardened the [original RT-DETR](paper:2304.08069) recipe (the paper that first showed DETRs beating YOLOs in real time) with training-only “bag-of-freebies” that add no inference cost.

**My recommendation:** for edge or high-FPS deployment, start with [YOLOv12](paper:2502.12524) — the [Ultralytics framework](paper:158342) has ready-made checkpoints and export paths. If you have GPU headroom and want maximum accuracy while staying real-time, use [D-FINE](paper:2410.13842) or [RT-DETRv2](paper:2407.17140). And if you need open-vocabulary detection rather than fixed COCO classes, [YOLO-World](paper:2401.17270) is the one to look at.`;

const FOLLOWUPS = [
  "How do these compare on edge devices like Jetson?",
  "Show me open-vocabulary detectors",
  "What about small-object detection?",
];

/**
 * Replay the scripted turn. The user's question is echoed into the first
 * tool call so the demo tracks whatever was asked, but reasoning/answer
 * content is fixed.
 */
export async function* mockChatStream(
  question: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const aborted = () => signal?.aborted === true;
  const q = question.trim().slice(0, 90) || "state-of-the-art real-time object detection";

  yield { type: "stream_start", request_id: "req_mock", session_id: null };

  await sleep(350, signal);
  if (aborted()) return;

  // -- reasoning pass 1
  yield { type: "reasoning_start" };
  for (let i = 0; i < REASONING_1.length; i += 6) {
    await sleep(14, signal);
    if (aborted()) return;
    yield { type: "reasoning_delta", text: REASONING_1.slice(i, i + 6) };
  }
  await sleep(400, signal);
  if (aborted()) return;
  yield { type: "reasoning_end" };
  await sleep(300, signal);
  if (aborted()) return;

  // -- broad search
  yield {
    type: "tool_call",
    id: "call_1",
    name: "search_papers",
    args: { query: q, top_k: 8 },
  };
  await sleep(1100, signal);
  if (aborted()) return;
  yield { type: "tool_result", id: "call_1", hits: FIRST_SEARCH.length, took_ms: 214, results: FIRST_SEARCH };
  await sleep(350, signal);
  if (aborted()) return;

  // -- reasoning pass 2
  yield { type: "reasoning_start" };
  for (let i = 0; i < REASONING_2.length; i += 6) {
    await sleep(14, signal);
    if (aborted()) return;
    yield { type: "reasoning_delta", text: REASONING_2.slice(i, i + 6) };
  }
  await sleep(350, signal);
  if (aborted()) return;
  yield { type: "reasoning_end" };
  await sleep(300, signal);
  if (aborted()) return;

  // -- narrow benchmark search
  yield {
    type: "tool_call",
    id: "call_2",
    name: "search_papers",
    args: { query: "RT-DETR vs YOLOv12 COCO mAP latency FPS T4 TensorRT comparison", top_k: 5 },
  };
  await sleep(900, signal);
  if (aborted()) return;
  yield { type: "tool_result", id: "call_2", hits: SECOND_SEARCH.length, took_ms: 176, results: SECOND_SEARCH };
  await sleep(400, signal);
  if (aborted()) return;

  // -- final answer
  for (let i = 0; i < ANSWER.length; i += 4) {
    await sleep(11, signal);
    if (aborted()) return;
    yield { type: "answer_delta", text: ANSWER.slice(i, i + 4) };
  }
  yield { type: "done", followups: FOLLOWUPS, finish_reason: "success" };
}
