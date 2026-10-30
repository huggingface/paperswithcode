import { authUrl } from "./apiUrl";
import { ApiError } from "./apiTransport";

/** Curation sections, as named by the API, with their reader-facing labels. */
export const PAPER_EDIT_SECTION_LABELS = {
  tasks: "tasks",
  methods: "methods",
  organizations: "organizations",
  repositories: "GitHub repositories",
  project_pages: "project pages",
  hf_artifacts: "Hugging Face artifacts",
  source_url: "source URL",
  x_threads: "X threads",
  evaluations: "evaluation results",
} as const;

/** A curation section; also the paper page's editor ID. */
export type PaperEditSection = keyof typeof PAPER_EDIT_SECTION_LABELS;

export function isPaperEditSection(value: string): value is PaperEditSection {
  return Object.prototype.hasOwnProperty.call(PAPER_EDIT_SECTION_LABELS, value);
}

/** Session key naming the editor to reopen after a fresh sign-in. */
export const FRESH_AUTH_EDIT_KEY = "pwc:fresh-auth-edit";

type Request = <T>(endpoint: string, options?: RequestInit) => Promise<T>;
type FreshAuthRecovery = (section: PaperEditSection) => void;

export interface FreshAuthMutationDraft {
  section: PaperEditSection;
  endpoint: string;
  payload: unknown;
  options: {
    method: string;
    body?: string;
    headers: Record<string, string>;
  };
}

const FRESH_AUTH_MUTATION_KEY = "pwc:fresh-auth-mutation";

function redirectToFreshAuth(section: PaperEditSection): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(FRESH_AUTH_EDIT_KEY, section);
  const login = authUrl("/api/v1/auth/hf/login");
  window.location.assign(`${login}?return_to=${encodeURIComponent(window.location.href)}`);
}

export class PaperCurationCoordinator {
  private paperLoads = new Map<string, Promise<{ sections: Record<string, string> }>>();
  private evaluationLoads = new Map<string, Promise<{ version: string }>>();

  constructor(
    private readonly request: Request,
    private readonly recoverFreshAuth: FreshAuthRecovery = redirectToFreshAuth,
  ) {}

  primePaper(
    paperId: string,
    force = false,
  ): Promise<{ sections: Record<string, string> }> {
    if (force) this.paperLoads.delete(paperId);
    let load = this.paperLoads.get(paperId);
    if (!load) {
      load = this.request<{ sections: Record<string, string> }>(
        `/papers/${paperId}/curation-state`,
      ).catch((error) => {
        this.paperLoads.delete(paperId);
        throw error;
      });
      this.paperLoads.set(paperId, load);
    }
    return load;
  }

  primeEvaluations(
    paperId: string,
    force = false,
  ): Promise<{ version: string }> {
    if (force) this.evaluationLoads.delete(paperId);
    let load = this.evaluationLoads.get(paperId);
    if (!load) {
      load = this.request<{ version: string }>(
        `/evaluations/curation-state?paper_id=${paperId}`,
      ).catch((error) => {
        this.evaluationLoads.delete(paperId);
        throw error;
      });
      this.evaluationLoads.set(paperId, load);
    }
    return load;
  }

  async mutatePaper<T>(
    paperId: string,
    section: Exclude<PaperEditSection, "evaluations">,
    payload: unknown,
    endpoint: string,
    options: RequestInit,
  ): Promise<T> {
    const load = this.paperLoads.get(paperId);
    if (!load) {
      throw new Error(
        "The catalog version was not loaded when this editor opened. Close and reopen the editor.",
      );
    }
    const version = (await load).sections[section];
    if (!version) throw new Error(`Missing curation version for ${section}`);
    return this.mutate(
      section,
      endpoint,
      payload,
      version,
      options,
      `paper:${paperId}:${section}`,
    );
  }

  async mutateEvaluations<T>(
    paperId: number,
    payload: unknown,
    endpoint: string,
    options: RequestInit,
  ): Promise<T> {
    const load = this.evaluationLoads.get(String(paperId));
    if (!load) {
      throw new Error(
        "The evaluation version was not loaded when this editor opened. Close and reopen the editor.",
      );
    }
    const version = (await load).version;
    return this.mutate(
      "evaluations",
      endpoint,
      payload,
      version,
      options,
      `paper:${paperId}:evaluations`,
    );
  }

  private async mutate<T>(
    section: PaperEditSection,
    endpoint: string,
    payload: unknown,
    version: string,
    options: RequestInit,
    scope: string,
  ): Promise<T> {
    const requestHeaders = new Headers(options.headers);
    Object.entries(this.idempotencyHeaders(scope, payload, version)).forEach(
      ([name, value]) => requestHeaders.set(name, value),
    );
    const requestOptions = { ...options, headers: requestHeaders };
    try {
      const result = await this.request<T>(endpoint, requestOptions);
      this.clearAttempt(requestOptions);
      return result;
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.status === 401 &&
        error.code === "fresh_auth_required"
      ) {
        this.saveFreshAuthMutation(section, endpoint, payload, requestOptions);
        this.recoverFreshAuth(section);
      } else if (error instanceof ApiError && error.status === 409) {
        this.clearAttempt(requestOptions);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("pwc:catalog-conflict", { detail: { endpoint } }));
        }
      }
      throw error;
    }
  }

  freshAuthMutationDraft(): FreshAuthMutationDraft | null {
    const serialized = sessionStorage.getItem(FRESH_AUTH_MUTATION_KEY);
    if (!serialized) return null;
    try {
      const draft = JSON.parse(serialized) as FreshAuthMutationDraft;
      if (
        !draft.endpoint.startsWith("/") ||
        draft.endpoint.startsWith("//") ||
        !["POST", "PUT", "PATCH", "DELETE"].includes(draft.options.method)
      ) {
        throw new Error("Invalid saved mutation draft");
      }
      return draft;
    } catch {
      sessionStorage.removeItem(FRESH_AUTH_MUTATION_KEY);
      return null;
    }
  }

  async resumeFreshAuthMutation<T>(): Promise<T> {
    const draft = this.freshAuthMutationDraft();
    if (!draft) throw new Error("No saved catalog edit is available.");
    const result = await this.request<T>(draft.endpoint, {
      method: draft.options.method,
      body: draft.options.body,
      headers: draft.options.headers,
    });
    this.clearAttempt({ headers: draft.options.headers });
    sessionStorage.removeItem(FRESH_AUTH_MUTATION_KEY);
    sessionStorage.removeItem(FRESH_AUTH_EDIT_KEY);
    return result;
  }

  private saveFreshAuthMutation(
    section: PaperEditSection,
    endpoint: string,
    payload: unknown,
    options: RequestInit,
  ): void {
    const headers = Object.fromEntries(new Headers(options.headers).entries());
    const body = typeof options.body === "string" ? options.body : undefined;
    sessionStorage.setItem(
      FRESH_AUTH_MUTATION_KEY,
      JSON.stringify({
        section,
        endpoint,
        payload,
        options: {
          method: (options.method ?? "POST").toUpperCase(),
          body,
          headers,
        },
      } satisfies FreshAuthMutationDraft),
    );
  }

  private idempotencyHeaders(
    scope: string,
    payload: unknown,
    version: string,
  ): Record<string, string> {
    const storageKey = `pwc:mutation:${scope}:${JSON.stringify(payload)}`;
    const existing = sessionStorage.getItem(storageKey);
    if (existing) {
      const attempt = JSON.parse(existing) as { key: string; version: string };
      return { "Idempotency-Key": attempt.key, "If-Match": attempt.version };
    }
    const key = crypto.randomUUID();
    sessionStorage.setItem(storageKey, JSON.stringify({ key, version }));
    sessionStorage.setItem(`pwc:mutation-key:${key}`, storageKey);
    return { "Idempotency-Key": key, "If-Match": version };
  }

  private clearAttempt(options: RequestInit): void {
    const key = new Headers(options.headers).get("Idempotency-Key");
    if (!key) return;
    const storageKey = sessionStorage.getItem(`pwc:mutation-key:${key}`);
    if (storageKey) sessionStorage.removeItem(storageKey);
    sessionStorage.removeItem(`pwc:mutation-key:${key}`);
    this.paperLoads.clear();
    this.evaluationLoads.clear();
  }
}
