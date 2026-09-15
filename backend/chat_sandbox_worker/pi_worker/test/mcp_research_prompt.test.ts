import assert from "node:assert/strict";
import test from "node:test";
import { renderMcpResearchPrompt } from "../src/mcp_research_prompt.js";
import { renderPrompt } from "../src/prompt.js";

const source = `The available tools for a normal research turn are Bash, Read, and search_web.
<cli_usage>For SOTA first run \`pwc task --name TASK\`, then \`pwc benchmark list --task TASK\`.</cli_usage>
Use \`pwc paper list --organization NAME --order-by date_published --order-dir
desc\` then \`pwc paper info\` for recent families.
Budget: 12 tool calls, 4 searches. Respect 429 and output limits.
# pwc CLI skill
Run pwc search with Bash.
# s2 CLI skill
Use s2 refs for references.
# restricted hf CLI skill
Anonymous only. Never authenticate.
`;

test("MCP research replaces CLI-first workflows and retains other tools and limits", () => {
  const rendered = renderMcpResearchPrompt(source);
  assert.doesNotMatch(rendered, /<cli_usage>|# pwc CLI skill|`pwc\s|Run pwc search/u);
  for (const tool of ["pwc_get_task", "pwc_list_benchmarks", "pwc_get_benchmark", "pwc_list_papers", "pwc_get_paper_info"]) assert.ok(rendered.includes(tool));
  assert.match(rendered, /12 tool calls, 4 searches/u);
  assert.match(rendered, /Use s2 refs for references/u);
  assert.match(rendered, /Anonymous only. Never authenticate/u);
  assert.match(rendered, /Bash\/executor failure does not mean the MCP catalog is unavailable/u);
});

test("only enabled MCP catalog turns replace the legacy workflow", async () => {
  const old = process.env.PWC_CHAT_PWC_MCP_ENABLED;
  try {
    const options = { source, model: "test", hfUsername: "test", webSearchEnabled: false, readerMode: false };
    process.env.PWC_CHAT_PWC_MCP_ENABLED = "true";
    const enabled = await renderPrompt({ ...options, catalogToolsEnabled: true });
    assert.doesNotMatch(enabled, /<cli_usage>|# pwc CLI skill/u);
    const unavailable = await renderPrompt({ ...options, catalogToolsEnabled: false });
    assert.match(unavailable, /<cli_usage>/u);
    process.env.PWC_CHAT_PWC_MCP_ENABLED = "false";
    const disabled = await renderPrompt({ ...options, catalogToolsEnabled: true });
    assert.match(disabled, /<cli_usage>/u);
  } finally {
    if (old === undefined) delete process.env.PWC_CHAT_PWC_MCP_ENABLED;
    else process.env.PWC_CHAT_PWC_MCP_ENABLED = old;
  }
});
