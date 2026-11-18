// Slim core build. Its omitted extensions (session replay, surveys, heatmaps,
// toolbar, exception capture) are all disabled in posthogPrivacyOptions, so
// the full build only added ~42 KB gzip to every page's entry chunk.
import posthog from "posthog-js/dist/module.slim";

import { posthogPrivacyOptions } from "./posthogPrivacy";

export function initPostHog(token: string | undefined): void {
  if (token) posthog.init(token, posthogPrivacyOptions);
}

export default posthog;
