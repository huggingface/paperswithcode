# Public catalog API beta

The public reference at `/docs/api` describes a selected subset of the existing
`/api/v1` catalog. `backend/services/public_api_schema.py` owns that selection and
small example requests. `/api/v1/openapi.json` generates the response and parameter
schemas from the actual routes. `/openapi.json` remains the full application
schema. Discovery links advertise the public schema.

## Adding or changing an endpoint

1. Confirm the read has no user-specific data or side effects and uses a bounded
   response. Add a typed response model before documenting an opaque dictionary.
2. Add the route and a valid example to `PUBLIC_ENDPOINTS`. The public browser
   middleware matches the actual registered route, not just its URL shape.
3. Check request parameters and examples against the route. The public search
   contract requires explicit `mode=keyword`; existing search modes and defaults
   are unchanged for website and other clients.
4. Run `test_public_api.py`, `test_public_api_nginx.py`, and `ApiDocsView.test.tsx`.
   Verify actual responses and identifiers too: contract tests cannot establish
   that an example record still exists.
5. Record planned breaking changes in the docs changelog with announcement and
   effective dates at least 14 days apart. Urgent security or restoration fixes
   are exempt. Do not silently change documented behavior.

## Traffic controls

Both nginx templates contain shared per-IP zones: catalog GETs sustain 120/minute
with 60 excess burst slots; list/search GETs additionally sustain 60/minute with
20 excess burst slots. The identity is nginx's remote client address, never an
untrusted forwarding header. Browsing, scripts, and users behind a shared NAT
share the allowance. OPTIONS and mutations do not enter these zones.

These are initial operating limits, not a capacity guarantee. A bounded sample
of 50,000 pre-launch access-log lines contained 9,856 catalog IP/minute samples
(p99 22 requests) and 278 search IP/minute samples (p99 36). This sample includes
bots and scripts and does not characterize every user or expensive query.
Follow nginx's limit-exceeded log entries and API latency after launch. Adjust
rates and bursts together with the docs; avoid production load tests. A rejected
request receives JSON, no-store, a two-second Retry-After, and public CORS headers. The fixed, credential-independent error reflects an
Origin header and permits credentials so existing browser clients can read the
retry instruction; successful responses still use the application CORS policy.

The application CORS middleware grants anonymous cross-origin GET access only
to the explicitly selected operations and the public schema. It does not grant
credentialed access or change administrative/write CORS rules. Staging's nginx
access gate remains in place.

## Release dependency

This feature needs **both** the application release and the reviewed nginx
configuration. The exact `/docs/api` location serves the frontend; the existing
broad `/docs` proxy remains for backend docs. A direct backend request still has
the compact documentation fallback.

After PR integration, the publishing task must follow `pwc-deploy` and separately
apply the checked-in nginx template through `pwc-nginx` for the target environment.
An application deploy alone does not enable the limits or replace the old docs
page on direct navigation. Do not announce completion of the public launch until
both are active. Verify deep-link and footer navigation, the public schema, an
anonymous read with an Origin header, and normal site browsing. Keep production
and staging release identities separate.

Nginx integration tests use disposable directories, ephemeral ports, a synthetic
upstream, and an unprivileged nginx process, including its configuration check.
They isolate all five temporary directories, PID, lock, and logs. They do not
include host config, contact live services, or signal a live nginx process.
