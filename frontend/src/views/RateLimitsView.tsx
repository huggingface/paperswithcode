import { useQuery } from "@tanstack/react-query";

import { accountQueries } from "@/lib/api/queries";

const RateLimitsView = () => {
  const query = useQuery(accountQueries.rateLimitPolicy());
  const policy = query.data;
  return (
    <div className="page" style={{ maxWidth: 760 }}>
      <h1>Submission and rate-limit policy</h1>
      {policy ? (
        <>
          <p>Each account may have up to {policy.active_pending} active submissions.</p>
          <p>New submissions are limited to {policy.subject_per_hour} per account and {policy.ip_per_hour} per source network in a rolling hour.</p>
        </>
      ) : <p>Loading current limits…</p>}
      <p>Duplicate, no-op, and idempotently replayed requests do not consume creation quota.</p>
      <p>Rate-limited responses use HTTP 429 with Retry-After, RateLimit, and RateLimit-Policy headers.</p>
      <p>Good-faith contributors who are blocked should contact the Papers with Code maintainers with their Hugging Face username.</p>
    </div>
  );
};

export default RateLimitsView;
