/**
 * Account settings view (`/settings`).
 *
 * Houses research follows, the weekly email, display preferences, and chat
 * provider settings. Display preferences
 * persist server-side for signed-in users and remain session-local for guests.
 */

import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import HfSignInButton from "@/components/HfSignInButton";
import ResearchSettings from "@/components/ResearchSettings";
import { Switch } from "@/components/ui/switch";
import { chatApi } from "@/lib/api/chat";
import { ApiError } from "@/lib/apiTransport";
import { isChatEnabled } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import { formatPageTitle } from "@/lib/latexPlainText";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import {
  OPENROUTER_CREDENTIAL_QUERY_KEY,
  resetTimeLabels,
  useOpenRouterCredential,
  useOpenRouterUsage,
} from "@/lib/openrouter";
import { usePreferences } from "@/lib/preferences";

const OPENROUTER_KEY_SETTINGS_URL = "https://openrouter.ai/settings/keys";

function openRouterErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (
      typeof error.detail === "object"
      && error.detail !== null
      && "message" in error.detail
      && typeof error.detail.message === "string"
    ) return error.detail.message;
  }
  return error instanceof Error && !error.message.startsWith("API request failed:")
    ? error.message
    : fallback;
}

const SettingsView: React.FC = () => {
  const { user, isLoading: authLoading } = useAuth();
  const {
    preferences,
    setHideClosedSourceEvals,
    canPersist,
    isLoading: preferencesLoading,
  } = usePreferences();
  const { theme, setTheme } = useTheme();
  const selectedTheme = theme ?? "system";
  const chatEnabled = isChatEnabled();
  const [billingError, setBillingError] = React.useState("");
  const [openRouterError, setOpenRouterError] = React.useState("");
  const [openRouterErrorCode, setOpenRouterErrorCode] = React.useState("");
  const [openRouterKey, setOpenRouterKey] = React.useState("");
  const queryClient = useQueryClient();
  const modelsQuery = useQuery({
    queryKey: ["chat", "models", "settings"],
    enabled: chatEnabled && Boolean(user),
    queryFn: () => chatApi.getModels(),
  });
  const enabledProviders = new Set(
    (modelsQuery.data?.items ?? []).map((model) => model.provider),
  );
  const huggingFaceEnabled = enabledProviders.has("huggingface");
  const openRouterEnabled = enabledProviders.has("openrouter");
  const openAIEnabled = enabledProviders.has("openai");
  const billingQuery = useQuery({
    queryKey: ["inference-billing", user?.hf_subject],
    enabled: chatEnabled && Boolean(user) && huggingFaceEnabled,
    queryFn: () => chatApi.getInferenceBilling(),
  });
  const billing = billingQuery.data ?? null;
  const usageQuery = useOpenRouterUsage(
    chatEnabled && Boolean(user) && openRouterEnabled,
  );
  const credentialQuery = useOpenRouterCredential(
    chatEnabled && Boolean(user) && openRouterEnabled,
  );
  const usage = usageQuery.data;
  const credential = credentialQuery.data;
  const resetLabels = usage ? resetTimeLabels(usage.resets_at) : null;
  const providerDataLoading = chatEnabled && Boolean(user) && (
    modelsQuery.isLoading
    || (!modelsQuery.isError && (
      (huggingFaceEnabled && billingQuery.isLoading)
      || (openRouterEnabled && (usageQuery.isLoading || credentialQuery.isLoading))
    ))
  );
  const initialSettingsLoading = (
    authLoading || preferencesLoading || theme === undefined || providerDataLoading
  );
  const selectBillingAccountMutation = useMutation({
    mutationFn: (billTo: string | null) => (
      chatApi.selectInferenceBillingAccount(billTo)
    ),
    onSuccess: (status) => {
      queryClient.setQueryData(["inference-billing", user?.hf_subject], status);
      setBillingError("");
    },
    onError: (error) => {
      setBillingError(
        error instanceof Error
          ? error.message
          : "Could not change the billing account.",
      );
    },
  });
  const billingLoading = billingQuery.isLoading || selectBillingAccountMutation.isPending;
  const setOpenRouterMutationError = (error: unknown, fallback: string) => {
    setOpenRouterError(openRouterErrorMessage(error, fallback));
    setOpenRouterErrorCode(error instanceof ApiError ? error.code ?? "" : "");
  };
  const connectOpenRouterMutation = useMutation({
    mutationFn: (apiKey: string) => chatApi.connectOpenRouterCredential(apiKey),
    onSuccess: (status) => {
      queryClient.setQueryData(OPENROUTER_CREDENTIAL_QUERY_KEY, status);
      setOpenRouterKey("");
      setOpenRouterError("");
      setOpenRouterErrorCode("");
    },
    onError: (error) => setOpenRouterMutationError(
      error, "Could not connect the OpenRouter key.",
    ),
  });
  const fallbackMutation = useMutation({
    mutationFn: (enabled: boolean) => chatApi.setOpenRouterFallback(enabled),
    onSuccess: (status) => {
      queryClient.setQueryData(OPENROUTER_CREDENTIAL_QUERY_KEY, status);
      setOpenRouterError("");
      setOpenRouterErrorCode("");
    },
    onError: (error) => setOpenRouterMutationError(
      error, "Could not change paid fallback.",
    ),
  });
  const disconnectOpenRouterMutation = useMutation({
    mutationFn: () => chatApi.disconnectOpenRouterCredential(),
    onSuccess: () => {
      queryClient.setQueryData(OPENROUTER_CREDENTIAL_QUERY_KEY, {
        connected: false,
        verified_at: null,
        fallback_enabled: false,
      });
      setOpenRouterError("");
      setOpenRouterErrorCode("");
    },
    onError: (error) => setOpenRouterMutationError(
      error, "Could not disconnect the OpenRouter key.",
    ),
  });

  useDocumentTitle(formatPageTitle("Settings"));

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            <em>Settings</em>
          </h1>
          <div className="feed-subtitle">
            Manage what you follow, your weekly email, and how papers are displayed.
          </div>
        </div>
      </div>

      {initialSettingsLoading ? (
        <div className="settings-page-loading" role="status" aria-live="polite">
          <span className="sr-only">Loading settings…</span>
        </div>
      ) : <div className="settings-page-content">
      <ResearchSettings />
      {user && <section className="settings-section">
        <h2 className="settings-section-title">Catalog access</h2>
        <div className="settings-note settings-note-flush">
          <span>
            Role: <strong>{user.role ?? "community member"}</strong>.{" "}
            {user.can_directly_edit_catalog
              ? "You can apply catalog edits directly. Destructive changes require a recent sign-in."
              : "Your catalog suggestions are sent to the submissions queue for review."}
            {user.is_admin
              ? " You can also review submissions and use administrative maintenance tools."
              : " Submission review and maintenance tools remain admin-only."}
          </span>
        </div>
      </section>}

      {chatEnabled && <section className="settings-section">
        <h2 className="settings-section-title">Chat usage &amp; billing</h2>
        {!user ? (
          <div className="settings-note settings-note-flush">
            <span>
              Sign in to manage billing and credentials for the enabled chat providers.
            </span>
            <div className="settings-note-action">
              <HfSignInButton returnTo="/settings" authorizeInference />
            </div>
          </div>
        ) : modelsQuery.isError ? (
          <div className="settings-billing-loading" role="alert">
            Could not load the enabled chat providers.
          </div>
        ) : <div className="settings-provider-grid">
          {huggingFaceEnabled && <section className="settings-provider-card" aria-labelledby="inference-providers-heading">
            <div className="settings-provider-heading">
              <div>
                <h3 id="inference-providers-heading">Inference Providers</h3>
                <p>Hugging Face-billed model usage</p>
              </div>
              {billing?.connected && <span className="settings-connected-badge">Connected</span>}
            </div>
            {billingQuery.isError ? (
              <div className="settings-billing-loading" role="alert">
                Hugging Face billing is currently unavailable.
              </div>
            ) : billing?.connected ? <div className="settings-billing">
              <div className="settings-row-label">
                {billing.bill_to
                  ? `Organization · ${billing.bill_to}`
                  : `Personal account · @${user.username}`}
              </div>
              <p className="settings-row-desc">
                Usage for Hugging Face Inference Providers is billed by Hugging Face
                to your selected account. Included Hugging Face usage is applied first;
                pay-as-you-go billing follows your Hugging Face plan and billing settings.
                Papers With Code does not fund, meter, or reset these credits.
              </p>
              <label className="settings-token-label" htmlFor="hf-billing-account">
                Bill chat usage to
              </label>
              <select
                id="hf-billing-account"
                className="settings-billing-select"
                value={billing.bill_to ?? ""}
                onChange={(event) => {
                  setBillingError("");
                  selectBillingAccountMutation.mutate(event.target.value || null);
                }}
                disabled={billingLoading}
              >
                <option value="">Personal account (@{user.username})</option>
                {billing.organizations.map((organization) => (
                  <option key={organization.name} value={organization.name}>
                    {organization.display_name} ({organization.name})
                  </option>
                ))}
              </select>
              {billingError && <div className="settings-token-error">{billingError}</div>}
              <div className="settings-billing-actions">
                <a className="button button-primary" href={billing.usage_url} target="_blank" rel="noreferrer">
                  View Hugging Face usage &amp; billing <ExternalLink aria-hidden="true" />
                </a>
              </div>
            </div> : <div className="settings-billing-connect">
              <p className="settings-row-desc">
                Reconnect with Hugging Face to authorize Inference Providers. Hugging
                Face bills your personal account or the organization you select.
              </p>
              <div className="settings-billing-actions">
                <HfSignInButton returnTo="/settings" label="Re-sign in with Hugging Face" authorizeInference />
              </div>
            </div>}
          </section>}

          {openRouterEnabled && <section className="settings-provider-card" id="openrouter-byok" aria-labelledby="openrouter-heading">
            <div className="settings-provider-heading">
              <div>
                <h3 id="openrouter-heading">OpenRouter</h3>
                <p>Papers With Code-funded allowance and optional fallback</p>
              </div>
              {credential?.connected && <span className="settings-connected-badge">Key connected</span>}
            </div>
            <p className="settings-row-desc">
              Papers With Code pays for these OpenRouter requests and provides free but
              limited monthly usage. Your own key is available as an optional fallback.
            </p>
            {usage ? <div className="settings-usage-row">
              <div className="settings-usage-heading">
                <div>
                  <div className="settings-row-label">Monthly OpenRouter usage</div>
                  <div className="settings-row-desc">
                    Resets {resetLabels?.local} <span aria-label="UTC reset time">({resetLabels?.utc})</span>
                  </div>
                </div>
                <strong>{usage.available ? `${usage.remaining_percent}% left` : "Unavailable"}</strong>
              </div>
              <div
                className="settings-usage-track"
                role="progressbar"
                aria-label={`${usage.remaining_percent}% remaining; resets ${resetLabels?.local}; ${resetLabels?.utc}`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={usage.remaining_percent}
              >
                <span style={{ width: `${usage.remaining_percent}%` }} />
              </div>
              {!usage.available && <p className="settings-limit-note">
                {usage.unavailable_reason === "personal_allowance_exhausted"
                  ? "Your free monthly allowance is depleted."
                  : `The shared OpenRouter credits are currently unavailable. ${usage.remaining_percent}% of your personal allowance remains.`}
                {" DeepSeek V4 Flash is temporarily unavailable unless you enable your own key below."}
              </p>}
            </div> : <div className="settings-billing-loading">
              {usageQuery.isError || usage
                ? "OpenRouter usage is currently unavailable."
                : "Checking OpenRouter usage…"}
            </div>}

            <div className="settings-byok-controls">
              <div className="settings-row-label">Provide your own OpenRouter API key</div>
              {credential?.connected ? <>
                <p className="settings-row-desc">
                  Connected{credential.verified_at
                    ? ` · Last verified ${new Date(credential.verified_at).toLocaleString()}`
                    : ""}. Your API key is stored securely using AES-256 encryption.
                  It is never shown again.
                </p>
                <label className="settings-fallback-control">
                  <Switch
                    checked={credential.fallback_enabled}
                    disabled={fallbackMutation.isPending}
                    onCheckedChange={(checked) => fallbackMutation.mutate(Boolean(checked))}
                  />
                  <span>
                    <strong>Use my OpenRouter key when Papers With Code-funded OpenRouter access is unavailable</strong>
                    <small>
                      OpenRouter bills this usage to your own account. It is not
                      covered by Papers With Code.
                    </small>
                  </span>
                </label>
                <p className="settings-billing-help">
                  Disconnecting prevents new requests but cannot cancel a request
                  already sent to OpenRouter.
                </p>
                <div className="settings-billing-actions">
                  <button className="button" type="button" disabled={disconnectOpenRouterMutation.isPending} onClick={() => disconnectOpenRouterMutation.mutate()}>
                    Disconnect
                  </button>
                  <a className="button" href={OPENROUTER_KEY_SETTINGS_URL} target="_blank" rel="noreferrer">
                    Revoke or rotate at OpenRouter <ExternalLink aria-hidden="true" />
                  </a>
                </div>
              </> : <form onSubmit={(event) => {
                event.preventDefault();
                if (openRouterKey.trim()) connectOpenRouterMutation.mutate(openRouterKey.trim());
              }}>
                <label className="settings-token-label" htmlFor="openrouter-api-key">OpenRouter API key</label>
                <input
                  id="openrouter-api-key"
                  type="password"
                  autoComplete="off"
                  value={openRouterKey}
                  onChange={(event) => setOpenRouterKey(event.target.value)}
                  placeholder="sk-or-…"
                />
                <p className="settings-billing-help">
                  Connecting stores the key but does not authorize paid fallback.
                  Enable billing separately after it is verified.
                </p>
                <div className="settings-billing-actions">
                  <button className="button button-primary" type="submit" disabled={!openRouterKey.trim() || connectOpenRouterMutation.isPending}>
                    {connectOpenRouterMutation.isPending ? "Verifying…" : "Connect key"}
                  </button>
                </div>
              </form>}
              {openRouterError && <div className="settings-token-error">
                <p>{openRouterErrorCode === "fresh_auth_required"
                  ? "Your account is signed in, but adding or enabling an API key requires a Hugging Face sign-in from the last 15 minutes."
                  : openRouterError}</p>
                {openRouterErrorCode === "fresh_auth_required" && <div className="settings-billing-actions">
                  <HfSignInButton
                    returnTo="/settings#openrouter-byok"
                    label="Re-authenticate with Hugging Face"
                  />
                </div>}
              </div>}
            </div>
          </section>}
          {openAIEnabled && <div className="settings-note settings-note-flush" role="note">
            Direct OpenAI usage is provided by Papers With Code. No OpenAI API key or
            billing account is required from you.
          </div>}
        </div>}
      </section>}

      {chatEnabled && <section className="settings-section">
        <h2 className="settings-section-title">Chat privacy &amp; retention</h2>
        <div className="settings-note settings-note-flush">
          <span>
            Chats are private and retained until you delete them. You can keep up
            to 500 active chats and 100 MB of chat data. Archiving removes chats
            from the active list and frees active-chat quota, but does not delete
            them. Deleting a chat permanently removes its durable transcript,
            workspace reference, and any public share link after deletion is
            verified. You can deliberately share an unlisted snapshot, but no
            dedicated private-chat export format is currently offered.
          </span>
        </div>
      </section>}

      <section className="settings-section">
        <h2 className="settings-section-title">Appearance</h2>
        <div className="theme-options" aria-label="Color theme">
          {[
            {
              value: "system",
              label: "System",
              description: "Match your device",
              icon: Monitor,
            },
            {
              value: "light",
              label: "Light",
              description: "Always use light mode",
              icon: Sun,
            },
            {
              value: "dark",
              label: "Dark",
              description: "Always use dark mode",
              icon: Moon,
            },
          ].map((option) => {
            const Icon = option.icon;
            const isSelected = selectedTheme === option.value;
            return (
              <button
                key={option.value}
                type="button"
                className={`theme-option ${isSelected ? "is-selected" : ""}`}
                aria-pressed={isSelected}
                onClick={() => setTheme(option.value)}
              >
                <Icon aria-hidden="true" />
                <span className="theme-option-copy">
                  <span className="theme-option-label">{option.label}</span>
                  <span className="theme-option-desc">{option.description}</span>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">Evaluations</h2>
        <div className="settings-row">
          <label className="settings-row-text" htmlFor="hide-closed-source-evals">
            <span className="settings-row-label">Hide closed-source models</span>
            <span className="settings-row-desc">
              When enabled, evaluations of closed-source models (proprietary
              APIs and unreleased flagship models) are hidden from benchmark
              leaderboards and paper result tables.
            </span>
          </label>
          <Switch
            id="hide-closed-source-evals"
            checked={preferences.hide_closed_source_evals}
            onCheckedChange={(checked) => {
              setHideClosedSourceEvals(Boolean(checked));
            }}
          />
        </div>

        {!authLoading && !canPersist && !user && (
          <div className="settings-note">
            <span>
              You are browsing as a guest, so this choice only applies to the
              current session. Sign in to save it to your account.
            </span>
            <div className="settings-note-action">
              <HfSignInButton returnTo="/settings" />
            </div>
          </div>
        )}
      </section>
      </div>}
    </div>
  );
};

export default SettingsView;
