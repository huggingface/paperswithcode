import React, { useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PaperCard } from "@/components";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { useInfinitePapers } from "@/hooks/usePapers";
import { DEFAULT_SITE_SUFFIX, formatPageTitle } from "@/lib/latexPlainText";
import { transformPaperForCard } from "@/lib/transform";

import "@/views/AstraForRoboticsView.css";

// Membership is data-driven: a paper joins this page when it is tagged with
// both the Robotics task and the GPT-6 Astra method. Curators add papers by
// tagging them, never by editing this file. The backend discovery page for
// crawlers (backend/services/discovery_page_service.py) uses the same pair.
const TASK_SLUG = "robotics";
const METHOD_SLUG = "gpt-6-astra";
const FRAMING_SOURCE_URL = "https://x.com/YuXiang_IRVL/status/2100395131924840570";

type OrderBy = "trending" | "date_published" | "citation_count";
const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

type XPost = { handle: string; author: string; summary: string; url: string };

// Hand-picked X posts for each family, in the order Yu Xiang's thread and the
// follow-up curation listed them. Summaries paraphrase each post.
const POLICY_POSTS: readonly XPost[] = [
  {
    handle: "Frame_Robotics",
    author: "Frame Robotics",
    summary: "Real-arm control that fixes grip angle and carry height on the next try after a miss.",
    url: "https://x.com/Frame_Robotics/status/2099900836273090614",
  },
  {
    handle: "qineng_wang",
    author: "Qineng Wang",
    summary: "Dual-ALOHA spatial-constraint puzzles: unlocking interlocked parts and threading a rope through three rings.",
    url: "https://x.com/qineng_wang/status/2099893504658866561",
  },
  {
    handle: "__Rhodium__",
    author: "Lucas",
    summary: "In-context learning of the controls and the workspace, reaching the task goal in three tries.",
    url: "https://x.com/__Rhodium__/status/2099521054678925534",
  },
  {
    handle: "SuveenE",
    author: "Suveen Ellawela",
    summary: "Picking up a pipette and fitting a 5 mm tip on a MolmoAct2 real-world eval, using the free hand for a better view.",
    url: "https://x.com/SuveenE/status/2099448450341605672",
  },
  {
    handle: "cdngdev",
    author: "thijs",
    summary: "A robot arm with a paintbrush painting the Golden Gate Bridge, improving across attempts from camera feedback.",
    url: "https://x.com/cdngdev/status/2097339677128982873",
  },
  {
    handle: "IsaacSin12",
    author: "Isaac Sin",
    summary: "Zero-shot sorting of irregularly shaped blocks into cups by color.",
    url: "https://x.com/IsaacSin12/status/2096715382166098302",
  },
  {
    handle: "chooi_jeq",
    author: "Jay Chooi",
    summary: "Robocurve's robot-control comparison: 95% task completion versus 40% for Fable 5.1 at lower cost.",
    url: "https://x.com/chooi_jeq/status/2096064315115839904",
  },
];

const AGENT_POSTS: readonly XPost[] = [
  {
    handle: "Lingjun_Mao",
    author: "Lingjun Mao",
    summary: "Adapting to a new embodiment to put a cake into an air fryer through CuRobo motion-planning tool APIs.",
    url: "https://x.com/Lingjun_Mao/status/2100294902672462176",
  },
  {
    handle: "walterzhu8",
    author: "Wentao Zhu",
    summary: "A day-and-a-half autonomous run that builds and trains pen spinning on a Sharpa hand in Isaac Lab.",
    url: "https://x.com/walterzhu8/status/2100212420840989112",
  },
  {
    handle: "mishig25",
    author: "Mishig",
    summary: "Painting the Eiffel Tower in MuJoCo with an SO-101 and a brush, with the full experiment shared on Hugging Face.",
    url: "https://x.com/mishig25/status/2099611674793668676",
  },
  {
    handle: "RunpeiDong",
    author: "Runpei Dong",
    summary: "Getting a humanoid into a Tesla in MuJoCo: learning from feedback, then reusing that experience with egocentric perception.",
    url: "https://x.com/RunpeiDong/status/2099604536327614717",
  },
  {
    handle: "frankzydou",
    author: "Zhiyang (Frank) Dou",
    summary: "A LeRobot SO-101 real-world pickup from a third-person RGB camera, where the arm has to bend back to reach the pen.",
    url: "https://x.com/frankzydou/status/2099338127915512297",
  },
  {
    handle: "Parvkpr",
    author: "Parv Kapoor",
    summary: "Real-to-sim: building an interactive simulation environment from a single image or video.",
    url: "https://x.com/Parvkpr/status/2098847963867238597",
  },
  {
    handle: "z_code68632",
    author: "code_z",
    summary: "One demo per task: unscrewing a bottle cap, inserting a plug, clearing obstacles, and imitating a dance on a real robot.",
    url: "https://x.com/z_code68632/status/2098397364725895387",
  },
];

const XPostList: React.FC<{ posts: readonly XPost[]; label: string }> = ({ posts, label }) => (
  <div className="astra-posts">
    <div className="astra-posts-label">{label}</div>
    <ul>
      {posts.map((post) => (
        <li key={post.url}>
          <a href={post.url} target="_blank" rel="noreferrer">
            @{post.handle}
          </a>
          <span className="astra-post-author"> {post.author}</span>
          <span className="astra-post-summary"> — {post.summary}</span>
        </li>
      ))}
    </ul>
  </div>
);

const parseOrderBy = (value: string | null): OrderBy =>
  value === "date_published" || value === "citation_count" ? value : "trending";

const AstraForRoboticsView: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";

  const papersQ = useInfinitePapers({
    task: TASK_SLUG,
    method: METHOD_SLUG,
    page_size: 12,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: true,
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
  });
  const { targetRef, isIntersecting } = useIntersectionObserver({
    rootMargin: "200px",
  });

  useEffect(() => {
    document.title = formatPageTitle("GPT-6 Astra for Robotics");
    return () => {
      document.title = DEFAULT_SITE_SUFFIX;
    };
  }, []);

  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  const cards = useMemo(
    () =>
      (papersQ.data?.pages ?? []).flatMap((page) =>
        page.results.map(transformPaperForCard),
      ),
    [papersQ.data],
  );
  const totalCount = papersQ.data?.pages[0]?.count ?? 0;

  const updateParam = (key: string, value: string | null) => {
    const updated = new URLSearchParams(searchParams);
    if (value === null) updated.delete(key);
    else updated.set(key, value);
    setSearchParams(updated);
  };

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <span> / </span>
        <span>GPT-6 Astra for Robotics</span>
      </nav>

      <header className="feed-header">
        <div>
          <div className="astra-eyebrow">Collection</div>
          <h1 className="feed-title">
            GPT-6 Astra <em>for Robotics</em>
          </h1>
          <div className="feed-subtitle">
            Papers, technical reports, and evaluations that put OpenAI&rsquo;s
            frontier model in control of real and simulated robots.
          </div>
          <p className="astra-lede">
            The GPT-6 Astra launch never mentioned robots, yet within days the
            model was driving arms, hands, and humanoids. As{" "}
            <a href={FRAMING_SOURCE_URL} target="_blank" rel="noreferrer">
              Yu Xiang
            </a>{" "}
            framed it, the work splits into two families: Astra acting as the
            robot policy itself, and Astra acting as an agent that orchestrates
            everything else.
          </p>
        </div>
      </header>

      <section className="astra-approaches" aria-label="How GPT-6 Astra is used for robots">
        <article className="astra-approach">
          <div className="astra-approach-num">01 / Robot policy</div>
          <h2>Astra as the policy, like a VLA</h2>
          <p>
            The model looks at camera frames and robot state and directly emits
            actions: end-effector poses, joint targets, or gripper commands,
            closing the control loop step by step with no task-specific
            training.
          </p>
          <XPostList posts={POLICY_POSTS} label="Seen on X" />
        </article>
        <article className="astra-approach">
          <div className="astra-approach-num">02 / Agent</div>
          <h2>Astra as the agent</h2>
          <p>
            The model reasons about the scene, writes and runs code, calls
            planners and tools, or delegates low-level motion to pretrained
            policies such as VLAs, and keeps the robot on task over long
            horizons.
          </p>
          <XPostList posts={AGENT_POSTS} label="Seen on X" />
        </article>
      </section>

      <p className="astra-note">
        Listing is automatic: any paper tagged with both the{" "}
        <Link to={`/tasks/${TASK_SLUG}`}>Robotics</Link> task and the{" "}
        <Link to={`/methods/${METHOD_SLUG}`}>GPT-6 Astra</Link> method appears
        here. Missing a report or preprint?{" "}
        <Link to="/submit">Submit it</Link>.
      </p>

      <div className="task-section-head" style={{ marginTop: 36 }}>
        <div className="task-section-eyebrow">Top trending · sort below</div>
        <div className="task-section-title">
          Papers <span className="meta">[{totalCount.toLocaleString()}]</span>
        </div>
      </div>

      <div className="sort-bar">
        <div className="paper-feed-toolbar-controls">
          <div className="sort-options">
            {SORT_OPTIONS.map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={`sort-btn ${orderBy === value ? "active" : ""}`}
                onClick={() =>
                  updateParam("order_by", value === "trending" ? null : value)
                }
              >
                {label}
              </button>
            ))}
          </div>
          <PaperFeedFilters
            hasCode={hasCode}
            hasHfArtifacts={hasHfArtifacts}
            onHasCodeChange={(active) => updateParam("has_code", active ? "true" : null)}
            onHasHfArtifactsChange={(active) =>
              updateParam("has_hf_artifacts", active ? "true" : null)
            }
          />
        </div>
      </div>

      {papersQ.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load the collection. Please try again.
          </AlertDescription>
        </Alert>
      ) : papersQ.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">No papers match this selection yet.</div>
      ) : (
        <>
          <div className="paper-list">
            {cards.map((paper, index) => (
              <PaperCard key={paper.id} paper={paper} rank={index + 1} />
            ))}
          </div>
          <div ref={targetRef} style={{ height: 1 }} />
          {papersQ.isFetchingNextPage && (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
              Loading more…
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default AstraForRoboticsView;
