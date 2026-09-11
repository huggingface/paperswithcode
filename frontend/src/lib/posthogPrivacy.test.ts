import { describe, expect, it } from "vitest";

import { posthogPrivacyOptions } from "./posthogPrivacy";

describe("PostHog privacy initialization", () => {
  it("keeps pageviews while disabling automatic collection and remote reconfiguration", () => {
    expect(posthogPrivacyOptions).toMatchObject({
      autocapture: false,
      rageclick: false,
      capture_dead_clicks: false,
      capture_exceptions: false,
      capture_pageleave: false,
      capture_pageview: true,
      capture_performance: false,
      disable_session_recording: true,
      advanced_disable_flags: true,
      disable_external_dependency_loading: true,
      mask_all_text: true,
      mask_all_element_attributes: true,
    });
  });
});
