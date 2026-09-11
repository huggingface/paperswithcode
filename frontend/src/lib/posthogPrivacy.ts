import type { PostHogConfig } from "posthog-js";

export const posthogPrivacyOptions = {
  api_host: import.meta.env.VITE_POSTHOG_HOST,
  defaults: "2026-05-30",
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
} satisfies Partial<PostHogConfig>;
