import claudeLight from "@/assets/agents/claude-light.svg";
import claudeDark from "@/assets/agents/claude-dark.svg";
import codexLight from "@/assets/agents/codex-light.svg";
import codexDark from "@/assets/agents/codex-dark.svg";
import cursorLight from "@/assets/agents/cursor-light.svg";
import cursorDark from "@/assets/agents/cursor-dark.svg";
import opencodeLight from "@/assets/agents/opencode-light.svg";
import opencodeDark from "@/assets/agents/opencode-dark.svg";

const logos = [
  { name: "Claude", light: claudeLight, dark: claudeDark },
  { name: "Codex", light: codexLight, dark: codexDark },
  { name: "Cursor", light: cursorLight, dark: cursorDark },
  { name: "OpenCode", light: opencodeLight, dark: opencodeDark },
];

export function AgentLogos() {
  return (
    <span className="ml-1 inline-flex shrink-0 items-center gap-1.5" aria-hidden="true">
      {logos.map(({ name, light, dark }) => (
        <span key={name} title={name} className="inline-flex h-[18px] w-[18px]">
          <img src={light} alt="" width={18} height={18} className="h-full w-full object-contain dark:hidden" />
          <img src={dark} alt="" width={18} height={18} className="hidden h-full w-full object-contain dark:block" />
        </span>
      ))}
    </span>
  );
}
