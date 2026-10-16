import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PWC_MCP_TOOLS } from "../src/pwc_mcp_tools.js";

const skill = readFileSync(new URL("../../PWC_MCP_SKILL.md", import.meta.url), "utf8");
import { adaptMcpSkill, renderMcpResearchPrompt } from "../src/mcp_research_prompt.js";
import { renderPrompt } from "../src/prompt.js";

const source = `You run inside a secure, disposable sandbox with a writable /workspace. Do not install packages.
The available tools for a normal research turn are Bash, Read, and search_web.
<cli_usage>For SOTA first run \`pwc task --name TASK\`, then \`pwc benchmark list --task TASK\`.</cli_usage>
Use \`pwc paper list --organization NAME --order-by date_published --order-dir
desc\` then \`pwc paper info\` for recent families. Check \`pwc conference list\` and \`pwc paper trending\`.
Budget: 12 tool calls, 4 searches across \`pwc search\` and \`s2 search\`. Respect 429 and output limits.
Each executed \`pwc search\` or \`s2 search\` process counts against the search ceiling, including commands launched by a loop; do not place multiple search executions in one Bash command.
Cite paper-specific claims as [title](paper:<route_id>) using route IDs returned by pwc. When an \`s2\` result is absent from PwC, cite the exact Semantic Scholar or arXiv HTTPS URL returned by \`s2\` instead. Cite every claim.
Never leave a paper title as unlinked plain text when \`pwc\` or \`s2\` supplied a stable destination.
# pwc CLI skill
Run pwc search with Bash.
# s2 CLI skill
Use s2 refs for references.
# restricted hf CLI skill
Anonymous only. Never authenticate.
# Turn metadata
<turn_metadata>{}</turn_metadata>`;

function withMcpEnabled<T>(value: string | undefined, run: () => Promise<T>): Promise<T> {
  const old = process.env.PWC_CHAT_PWC_MCP_ENABLED;
  if (value === undefined) delete process.env.PWC_CHAT_PWC_MCP_ENABLED;
  else process.env.PWC_CHAT_PWC_MCP_ENABLED = value;
  return run().finally(() => {
    if (old === undefined) delete process.env.PWC_CHAT_PWC_MCP_ENABLED;
    else process.env.PWC_CHAT_PWC_MCP_ENABLED = old;
  });
}

test("MCP research turns are sandbox-free and mention every registered tool", () => {
  const rendered = renderMcpResearchPrompt(source, skill);
  assert.doesNotMatch(rendered, /<cli_usage>|# pwc CLI skill|# s2 CLI skill|# restricted hf CLI skill|`pwc\s|Run pwc search|Use s2 refs|Anonymous only/u);
  assert.doesNotMatch(rendered, /disposable sandbox|`s2|one Bash command|returned by pwc\./u);
  for (const tool of PWC_MCP_TOOLS) assert.ok(rendered.includes(`pwc_${tool}`), tool);
  for (const tool of ["pwc_get_task", "pwc_list_papers", "pwc_get_paper_info", "pwc_list_conferences", "pwc_list_trending_papers"]) {
    assert.ok(rendered.includes(`\`${tool}\``), tool);
  }
  assert.match(rendered, /The available tools for a normal research turn are search_web and pwc_search_papers/u);
  assert.match(rendered, /Bash and Read are not available: there is no sandbox, shell, or CLI/u);
  assert.match(rendered, /You have no sandbox, shell, or CLI/u);
  assert.match(rendered, /max_parameters/u);
  assert.match(rendered, /include_evaluations/u);
  assert.match(rendered, /is or how it works, look it up before answering/u);
  assert.match(rendered, /When the method index lists it, call pwc_get_method with the index slug/u);
  assert.match(rendered, /for a general concept \(for example weight decay[^)]*\), call pwc_search_papers/u);
  assert.match(rendered, /After a pwc_get_method miss, use pwc_search_papers rather than retrying/u);
  assert.match(rendered, /inference engines, serving systems[^:]*are frameworks, not methods: never call pwc_get_method for them/u);
  assert.match(rendered, /Call pwc_get_framework with the framework index slug, or pwc_list_frameworks/u);
  for (const entry of ["vllm=vLLM", "sglang=SGLang", "llama-cpp=llama.cpp", "transformers=Transformers", "neuralforecast=NeuralForecast"]) {
    assert.ok(rendered.includes(entry), entry);
  }
  assert.doesNotMatch(rendered, /\$\{FRAMEWORK_INDEX\}/u);
  assert.match(rendered, /When a paper is in view[^.]*do not call pwc_get_method with the paper's title, model name, or acronym/u);
  assert.match(rendered, /When the method index does not list it, call pwc_get_method/u);
  assert.match(rendered, /When a conversation opens without a paper in view[^.]*call at least one catalog tool before answering/u);
  assert.match(rendered, /Read a bare topic or short phrase[^.]*as a request for the key and recent papers/u);
  assert.match(rendered, /# PwC MCP skill/u);
  assert.match(rendered, /next_cursor/u);
  assert.doesNotMatch(rendered, /pass `"next"` before any read/u);
  assert.match(rendered, /available_at/u);
  assert.match(rendered, /pwc_get_paper_evaluations/u);
  assert.match(rendered, /60 total requests/u);
  assert.match(rendered, /12 tool calls, 4 searches across `pwc_search_papers` and searched `pwc_list_papers`/u);
  assert.match(rendered, /Each pwc_search_papers call and each pwc_list_papers call with a search argument counts/u);
  assert.match(rendered, /route IDs returned by the PwC MCP tools\. Cite every claim\./u);
  assert.match(rendered, /when a PwC MCP tool supplied a stable destination/u);
  assert.match(rendered, /do not invoke the pwc CLI as a fallback/u);
  assert.match(rendered, /# Turn metadata\n<turn_metadata>/u);
});

test("poster and paper authoring turns keep the sandbox CLIs beside the MCP tools", () => {
  const rendered = renderMcpResearchPrompt(source, skill, { sandboxTools: true });
  assert.doesNotMatch(rendered, /<cli_usage>|# pwc CLI skill|`pwc\s/u);
  assert.match(rendered, /The available tools for this turn are Bash, Read, search_web, and pwc_search_papers/u);
  assert.match(rendered, /Bash and Read serve only poster or paper authoring work/u);
  assert.match(rendered, /# s2 CLI skill\nUse s2 refs for references/u);
  assert.match(rendered, /Anonymous only. Never authenticate/u);
  assert.match(rendered, /searched `pwc_list_papers`, and `s2 search`/u);
  assert.match(rendered, /restricted anonymous hf CLI only when/u);
});

test("the vendored skill is presented in terms of the registered tools", () => {
  const adapted = adaptMcpSkill(skill);
  assert.doesNotMatch(adapted, /\(`pwc |`pwc \.\.\. --json`|Use the separate `pwc` CLI/u);
  assert.match(adapted, /Those capabilities are unavailable in this chat\./u);
  assert.match(adapted, /Do not invent equivalent tools/u);
  for (const tool of PWC_MCP_TOOLS) assert.ok(adapted.includes(`\`pwc_${tool}(`), tool);
  assert.doesNotMatch(adapted, /(?<!pwc_)\bget_benchmark\(/u);
});

test("only enabled MCP catalog turns replace the legacy workflow", async () => {
  const options = { source, mcpSkill: skill, model: "test", hfUsername: "test", webSearchEnabled: false, readerMode: false };
  await withMcpEnabled("true", async () => {
    const enabled = await renderPrompt({ ...options, catalogToolsEnabled: true });
    assert.doesNotMatch(enabled, /<cli_usage>|# pwc CLI skill|# s2 CLI skill/u);
    assert.match(enabled, /Bash and Read are not available/u);
    const poster = await renderPrompt({ ...options, catalogToolsEnabled: true, posterlyEnabled: true });
    assert.match(poster, /Bash and Read serve only poster or paper authoring work/u);
    assert.match(poster, /# s2 CLI skill/u);
    const paper = await renderPrompt({ ...options, catalogToolsEnabled: true, paperArtifactsEnabled: true, paperGuide: "guide" });
    assert.match(paper, /Bash and Read serve only poster or paper authoring work/u);
    const unavailable = await renderPrompt({ ...options, catalogToolsEnabled: false });
    assert.match(unavailable, /<cli_usage>/u);
  });
  await withMcpEnabled("false", async () => {
    const disabled = await renderPrompt({ ...options, catalogToolsEnabled: true });
    assert.match(disabled, /<cli_usage>/u);
    assert.match(disabled, /pwc_search, pwc_paper_info, and pwc_paper_list/u);
  });
});

test("MCP turns load the packaged skill beside the canonical prompt asset", async () => {
  const directory = await mkdtemp(join(tmpdir(), "pwc-mcp-skill-"));
  try {
    await withMcpEnabled("true", async () => {
      const assetPath = join(directory, "pi-system-prompt.txt");
      await writeFile(assetPath, source);
      await writeFile(join(directory, "PWC_MCP_SKILL.md"), skill);
      const rendered = await renderPrompt({ assetPath, model: "test", hfUsername: "test", webSearchEnabled: false, readerMode: false, catalogToolsEnabled: true });
      assert.match(rendered, /# PwC MCP skill/u);
      assert.match(rendered, /pwc_read_paper/u);
      assert.doesNotMatch(rendered, /# pwc CLI skill/u);
      for (const tool of PWC_MCP_TOOLS) assert.ok(rendered.includes(`pwc_${tool}(`));
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
