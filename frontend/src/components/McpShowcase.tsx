import { Link } from "react-router-dom";

import { AgentLogos } from "@/components/paper-detail/AgentLogos";

interface McpShowcaseProps {
  className?: string;
  canNavigate?: () => boolean;
}

export function McpShowcase({ className = "", canNavigate }: McpShowcaseProps) {
  return (
    <div className={`sidebar-section sidebar-section-tools ${className}`.trim()}>
      <div className="sidebar-label">Use PwC with your agent</div>
      <Link
        to="/mcp"
        className="action-btn sidebar-tools-mcp"
        title="Connect Claude, Codex, Cursor, or OpenCode to the PwC MCP server"
        onClick={(event) => {
          if (canNavigate && !canNavigate()) event.preventDefault();
        }}
      >
        MCP server
        <AgentLogos />
      </Link>
      <p className="sidebar-tools-copy">
        Search papers, benchmarks, and leaderboards from any MCP client, or from the
        terminal with the{" "}
        <a href="https://github.com/huggingface/pwc-cli" target="_blank" rel="noreferrer">
          <code>pwc</code> CLI
        </a>
        .
      </p>
    </div>
  );
}
