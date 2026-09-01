export type PaperReceiptOperation = "create" | "begin-edit" | "draft" | "repair";

export interface PwcPaperCommand {
  receiptOperation?: PaperReceiptOperation;
}

const UNSAFE_SHELL = /[\\\r\n;&|<>()`$*?\[\]{}!~]/u;

function hasUnsafeShellSyntax(command: string): boolean {
  let quoted: "'" | '"' | undefined;
  for (const character of command) {
    if (quoted) {
      if (character === quoted) {
        quoted = undefined;
      } else if (quoted === '"' && /[\\`$]/u.test(character)) {
        return true;
      }
      continue;
    }
    if (character === "'" || character === '"') {
      quoted = character;
    } else if (UNSAFE_SHELL.test(character)) {
      return true;
    }
  }
  return quoted !== undefined;
}

function splitQuotedArguments(command: string): string[] | undefined {
  if (hasUnsafeShellSyntax(command)) return undefined;

  const arguments_: string[] = [];
  let current = "";
  let quoted: "'" | '"' | undefined;
  let inArgument = false;
  for (const character of command) {
    if (quoted) {
      if (character === quoted) {
        quoted = undefined;
      } else {
        current += character;
      }
      continue;
    }
    if (character === "'" || character === '"') {
      quoted = character;
      inArgument = true;
      continue;
    }
    if (/\s/u.test(character)) {
      if (inArgument) {
        arguments_.push(current);
        current = "";
        inArgument = false;
      }
      continue;
    }
    current += character;
    inArgument = true;
  }
  if (quoted) return undefined;
  if (inArgument) arguments_.push(current);
  return arguments_;
}

function hasExactArguments(
  arguments_: string[],
  flags: readonly string[],
): boolean {
  if (arguments_.length !== 2 + flags.length * 2) return false;
  const seen = new Set<string>();
  for (let index = 2; index < arguments_.length; index += 2) {
    const flag = arguments_[index] ?? "";
    const value = arguments_[index + 1] ?? "";
    if (!flags.includes(flag) || seen.has(flag) || !value || value.startsWith("--")) {
      return false;
    }
    seen.add(flag);
  }
  return seen.size === flags.length;
}

/**
 * Recognize only a single, direct invocation documented in PAPER_AUTHORING.md.
 * The returned receipt operation binds a broker receipt to the command that
 * produced it; repair-context gets its longer timeout but cannot emit one.
 */
export function parsePwcPaperCommand(command: string): PwcPaperCommand | undefined {
  const arguments_ = splitQuotedArguments(command);
  if (!arguments_ || arguments_[0] !== "pwc-paper") return undefined;
  switch (arguments_[1]) {
    case "create":
      return hasExactArguments(arguments_, ["--title"])
        ? { receiptOperation: "create" }
        : undefined;
    case "begin-edit":
      return arguments_.length === 2 ? { receiptOperation: "begin-edit" } : undefined;
    case "draft":
      return hasExactArguments(arguments_, [
        "--directory",
        "--artifact-id",
        "--expected-parent-version-id",
      ])
        ? { receiptOperation: "draft" }
        : undefined;
    case "repair":
      return hasExactArguments(arguments_, [
        "--directory",
        "--artifact-id",
        "--expected-parent-version-id",
      ])
        ? { receiptOperation: "repair" }
        : undefined;
    case "repair-context":
      return hasExactArguments(arguments_, ["--directory"]) ? {} : undefined;
    default:
      return undefined;
  }
}
