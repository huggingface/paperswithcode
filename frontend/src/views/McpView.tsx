import React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Check, Copy, ExternalLink, Github } from "lucide-react";

import { formatPageTitle } from "@/lib/latexPlainText";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { mcpEndpoint, mcpHealthQueryOptions } from "@/lib/mcp";

import "@/views/McpView.css";

const TOOLS = [
  ["search_papers", "Search by topic, title, author, or arXiv ID."],
  ["list_papers", "Filter and order papers by taxonomy, venue, date, or organization."],
  ["get_paper_info", "Read canonical metadata, authors, abstract, links, and resources."],
  ["read_paper", "Read stored paper Markdown with safe continuation for long papers."],
  ["list_recent_papers", "Browse the most recently indexed research."],
  ["get_related_papers", "Find related work already indexed in the catalogue."],
  ["list_trending_papers", "Discover papers with recent repository momentum."],
  ["get_paper_evaluations", "Inspect benchmark results reported by one paper."],
  ["get_paper_lineage", "Follow explicit predecessor and successor relationships."],
  ["list_tasks", "Search tasks and retrieve stable slugs for exact lookup."],
  ["get_task", "Inspect a research task and its benchmark coverage."],
  ["list_methods", "Search methods and retrieve stable slugs for exact lookup."],
  ["get_method", "Inspect a method, its source paper, and catalogue metadata."],
  ["list_conferences", "Browse conferences with imported papers."],
  ["get_conference", "Inspect one exact conference edition."],
  ["list_organizations", "Browse research organizations."],
  ["get_organization", "Inspect one exact research organization."],
  ["list_frameworks", "Browse frameworks by domain, category, or platform."],
  ["get_framework", "Inspect one exact research framework."],
  ["list_benchmarks", "Browse and filter benchmark leaderboards."],
  ["get_benchmark", "Read one benchmark, metrics, datasets, and leading results."],
] as const;

const RESOURCES = [
  "pwc://papers/{paper}",
  "pwc://papers/{paper}/markdown",
  "pwc://tasks/{task}",
  "pwc://benchmarks/{benchmark}",
] as const;

const EXAMPLES = [
  "Find recent papers on test-time compute and summarize the main approaches.",
  "Compare the methods and reported benchmarks in these three arXiv papers.",
  "What are the leading benchmarks for text-to-video generation?",
  "Trace the predecessor and successor papers for Mamba.",
] as const;

type ClientKey = "chatgpt" | "claude" | "claude-code" | "cursor" | "vscode" | "generic";

const CLIENTS: ReadonlyArray<{
  key: ClientKey;
  label: string;
  summary: string;
  code?: (endpoint: string) => string;
}> = [
  {
    key: "chatgpt",
    label: "ChatGPT",
    summary:
      "In workspace developer settings, add a custom MCP app and paste the server URL. Availability and admin approval vary by plan.",
  },
  {
    key: "claude",
    label: "Claude",
    summary:
      "Open Settings → Connectors → Add custom connector, paste the URL, then enable Papers With Code from Search and tools.",
  },
  {
    key: "claude-code",
    label: "Claude Code",
    summary: "Add the anonymous Streamable HTTP server from a terminal.",
    code: (endpoint) => `claude mcp add --transport http paperswithcode ${endpoint}`,
  },
  {
    key: "cursor",
    label: "Cursor",
    summary: "Add this entry to your project or user MCP configuration.",
    code: (endpoint) =>
      JSON.stringify({ mcpServers: { paperswithcode: { url: endpoint } } }, null, 2),
  },
  {
    key: "vscode",
    label: "VS Code",
    summary: "Add this Streamable HTTP server to .vscode/mcp.json.",
    code: (endpoint) =>
      JSON.stringify(
        { servers: { paperswithcode: { type: "http", url: endpoint } } },
        null,
        2,
      ),
  },
  {
    key: "generic",
    label: "Generic",
    summary:
      "Configure an anonymous, stateless Streamable HTTP server using the URL below. No API key or OAuth flow is required.",
  },
];

const CopyControl = ({ value, label }: { value: string; label: string }) => {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    if (!navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  };
  return (
    <button className="action-btn mcp-copy" type="button" onClick={() => void copy()} aria-label={label}>
      {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
};

const McpView: React.FC = () => {
  const endpoint = mcpEndpoint();
  const health = useQuery(mcpHealthQueryOptions());
  const [client, setClient] = React.useState<ClientKey>("chatgpt");
  const selected = CLIENTS.find((item) => item.key === client) ?? CLIENTS[0];

  useDocumentTitle(formatPageTitle("MCP Server"));

  return (
    <article className="page mcp-page">
      <a
        className="mcp-repo-banner"
        href="https://github.com/huggingface/pwc-cli"
        target="_blank"
        rel="noreferrer"
      >
        <Github size={20} aria-hidden />
        <span>
          <strong>huggingface/pwc-cli</strong>
          <span>Open-source MCP server and <code>pwc</code> command-line client</span>
        </span>
        <span className="mcp-repo-cta">
          View on GitHub <ArrowUpRight size={14} aria-hidden />
        </span>
      </a>
      <header className="mcp-hero">
        <div>
          <p className="sidebar-label mcp-kicker">Model Context Protocol</p>
          <h1 className="feed-title">Use Papers With Code in your AI assistant</h1>
          <p className="mcp-lede">
            Search research, inspect methods and benchmarks, and read complete papers
            through one anonymous, read-only MCP connection.
          </p>
          <div className="mcp-status" aria-live="polite">
            <span className={health.isSuccess ? "is-up" : "is-unknown"} aria-hidden />
            {health.isSuccess ? "Operational" : "Status unavailable"}
            {health.data ? ` · v${health.data.version}` : ""}
          </div>
        </div>
        <div className="mcp-endpoint-card">
          <span>Remote MCP URL</span>
          <code>{endpoint}</code>
          <CopyControl value={endpoint} label="Copy MCP server URL" />
        </div>
      </header>

      <section className="mcp-section" aria-labelledby="mcp-connect">
        <div className="mcp-section-heading">
          <p className="sidebar-label">Connect</p>
          <h2 id="mcp-connect">One URL, your preferred client</h2>
          <span>Setup matrix reviewed September 13, 2026; staging qualification pending.</span>
        </div>
        <div className="mcp-client-tabs" role="tablist" aria-label="MCP client setup">
          {CLIENTS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={client === item.key}
              onClick={() => setClient(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="mcp-setup" role="tabpanel">
          <p>{selected.summary}</p>
          {selected.code ? (
            <div className="mcp-code-row">
              <pre><code>{selected.code(endpoint)}</code></pre>
              <CopyControl value={selected.code(endpoint)} label={`Copy ${selected.label} setup`} />
            </div>
          ) : (
            <div className="mcp-code-row">
              <pre><code>{endpoint}</code></pre>
              <CopyControl value={endpoint} label={`Copy ${selected.label} endpoint`} />
            </div>
          )}
        </div>
      </section>

      <section className="mcp-section" aria-labelledby="mcp-capabilities">
        <div className="mcp-section-heading">
          <p className="sidebar-label">Capabilities</p>
          <h2 id="mcp-capabilities">Research context, structured for assistants</h2>
        </div>
        <div className="mcp-capability-grid">
          {[
            ["Discover", "Search recent and established work with catalogue filters."],
            ["Read", "Continue through long stored papers without presenting a partial document as complete."],
            ["Connect", "Explore related work, paper lineage, tasks, and methods."],
            ["Compare", "Inspect benchmarks, datasets, metrics, and reported evaluations."],
          ].map(([title, body]) => (
            <div key={title}>
              <h3>{title}</h3>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mcp-section" aria-labelledby="mcp-tools">
        <div className="mcp-section-heading">
          <p className="sidebar-label">Catalogue</p>
          <h2 id="mcp-tools">Twenty-one focused, read-only tools</h2>
        </div>
        <div className="mcp-tool-grid">
          {TOOLS.map(([name, description]) => (
            <div className="mcp-tool" key={name}>
              <code>{name}</code>
              <p>{description}</p>
            </div>
          ))}
        </div>
        <h3 className="mcp-subheading">Resource templates</h3>
        <div className="mcp-resource-list">
          {RESOURCES.map((resource) => <code key={resource}>{resource}</code>)}
        </div>
      </section>

      <section className="mcp-section" aria-labelledby="mcp-prompts">
        <div className="mcp-section-heading">
          <p className="sidebar-label">Try asking</p>
          <h2 id="mcp-prompts">Prompts that start useful research</h2>
        </div>
        <div className="mcp-prompt-list">
          {EXAMPLES.map((prompt) => (
            <div key={prompt}>
              <p>{prompt}</p>
              <CopyControl value={prompt} label="Copy example prompt" />
            </div>
          ))}
        </div>
      </section>

      <section className="mcp-section mcp-notes" aria-labelledby="mcp-limits">
        <div>
          <p className="sidebar-label mcp-kicker">Limits &amp; privacy</p>
          <h2 id="mcp-limits">Public by design</h2>
          <p>
            No account, API key, or write access. Fair-use limits are 60 total requests
            per minute, 10 semantic searches per minute, four concurrent requests per
            client, and 25 list results per call.
          </p>
          <p>
            MCP telemetry retains tool name, status, latency, response size, protocol,
            and server version—not prompts, paper IDs, cursors, resource URIs, raw IPs,
            authorization values, or bodies. Catalogue infrastructure has its own
            operational logging policy.
          </p>
        </div>
        <div>
          <p className="sidebar-label mcp-kicker">Protocol &amp; troubleshooting</p>
          <h2>Streamable HTTP</h2>
          <p>
            Primary protocol: {health.data?.protocol ?? "verified during connection setup"}. If setup fails,
            confirm your client supports remote Streamable HTTP, that custom servers are
            enabled by your workspace administrator, and that you pasted the URL exactly.
          </p>
          <nav className="mcp-links" aria-label="MCP documentation links">
            <a href="https://github.com/huggingface/pwc-cli" target="_blank" rel="noreferrer">CLI repository <ExternalLink size={13} /></a>
            <a href="https://modelcontextprotocol.io/docs/2026-07-28/learn/server-concepts" target="_blank" rel="noreferrer">MCP specification <ExternalLink size={13} /></a>
            <a href="/docs" target="_blank" rel="noreferrer">Public API <ExternalLink size={13} /></a>
            <a href="/mcp/schema" target="_blank" rel="noreferrer">MCP tool schema <ExternalLink size={13} /></a>
            <a href="/llms.txt" target="_blank" rel="noreferrer">llms.txt <ExternalLink size={13} /></a>
          </nav>
        </div>
      </section>
    </article>
  );
};

export default McpView;
