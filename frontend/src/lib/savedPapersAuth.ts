import { hfLoginUrl } from "./apiUrl";

export const SAVED_PAPERS_AUTHORIZED_PARAM = "saved_papers_authorized";

export function savedPapersAuthorizationUrl(resumeBookmark = false): string {
  const returnUrl = new URL(window.location.href);
  if (resumeBookmark) {
    returnUrl.searchParams.set(SAVED_PAPERS_AUTHORIZED_PARAM, "1");
  }
  return hfLoginUrl(`${returnUrl.pathname}${returnUrl.search}${returnUrl.hash}`, {
    authorizeBucket: true,
    bucketCreate: true,
  });
}
