# Persistent executor transport provenance

Task 0 froze the source boundary. Task 1 ports only the framing, ordering, and
Hybrid IK construction needed by the Papers With Code transport core. The
registry, rendezvous, daemon, command envelopes, and deployment lifecycle remain
locally owned and are not part of this port.

## Upstream pin

- Repository: `https://github.com/openai/codex`
- Commit: `c62d191c4c8c0cab7045fca6efc399197334bb6c`
- License: Apache-2.0 (`LICENSE` at the pinned commit), SHA-256
  `d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc`.
  Copyright remains with OpenAI and the upstream contributors; adapted files
  retain an attribution header and this provenance record.
- Security profile: `noise_hybrid_ik_v1`
- Upstream Rust dependency lock SHA-256:
  `5591e039ef19dd7e2569efa1060d263e5169af86b6012d3a0e84e7ca54d8d155`
- Local interoperability vectors:
  `executor_transport/vectors/bootstrap_v1.json` at SHA-256
  `9db33156d64742c2510604064b7e5b8733b196c8c9611d0755e889aafa5e0743`

The upstream `codex-rs/Cargo.lock` is the dependency-closure record that was
reviewed. The smaller Task 1 `Cargo.lock` is independently pinned at SHA-256
`082d16913f338657563a2a4a8b936618a324bd85c08b623c8f7c97442fdf2629`;
the upstream lock is not a substitute for it. Rust is pinned to 1.95.0.
`clatter` 2.2.0 supplies the reviewed Hybrid IK primitives; `ed25519-dalek`
2.2.0 signs the local authorization envelope, and `sha2` 0.10.9 derives
content-free public key identifiers. Exact transitive versions are in the lock.

## Reviewed source boundary

| Upstream path | Git blob | Task 1 disposition |
| --- | --- | --- |
| `codex-rs/exec-server/src/noise_channel.rs` | `cde2aae4eeb1ccedf3d3617bd1e7fa2ba2e21796` | Narrow attributed adaptation in `src/noise.rs`; private identities have no serialization, debug, clone, or secret-key accessor. |
| `codex-rs/exec-server/src/remote.rs` | `0d2711b7a8a4c4284220cc2e296dd04e678cc879` | Study registry client, profile check, and connection lifecycle; reimplement the Papers With Code bootstrap. |
| `codex-rs/exec-server/src/remote/registration_retry.rs` | `1a2dc989da947393a1191ea4200ab8346825925c` | Study bounded retry behavior; replace authentication with the generation-bound state machine. |
| `codex-rs/exec-server/src/noise_relay/message_framing.rs` | `af9fbd49986f0e23da32acf44ecee4ac377f536c` | Adapted its authenticated four-byte length prefix and bounded incremental decoding in `src/protocol.rs`; reduced the local message ceiling to 1 MiB and the record payload to 60 KiB. |
| `codex-rs/exec-server/src/noise_relay/ordered_ciphertext.rs` | `92bbd291d72f8130881a9364e43323a5566571ad` | Adapted its 64-record reorder window, duplicate suppression, checked sequence advance, and bounded pending bytes in `src/protocol.rs`. |
| `codex-rs/exec-server/src/noise_relay/stream_handler.rs` | `b0c610933c09d3b98bfe10fa6f7e5e2e744b7131` | Reviewed only. Its Tokio/JSON-RPC ownership and tracing assumptions are not copied. |
| `codex-rs/exec-server/src/noise_relay/executor_stream.rs` | `612cc9781f1f607c58d72832073187275713d73c` | Reviewed only. Its command envelope and hosted-relay assumptions are not copied. |
| `codex-rs/exec-server/src/noise_relay/harness.rs` | `793f7c1e12e9816e58606b3ffeaf9a1b009f5b2a` | Study Hybrid IK construction and readiness; adapt to turn-scoped authorization. |
| `codex-rs/exec-server/src/relay.rs` | `40afbf0e288895451c07f04de89d33c651fb50f8` | Study harness-key validation; do not import its service assumptions. |

Upstream test blobs are reviewed with their matching modules, especially
`remote/noise_tests.rs`, `noise_relay/message_framing_tests.rs`,
`noise_relay/ordered_ciphertext_tests.rs`, and
`noise_relay/stream_handler_tests.rs`. Their vectors are not treated as proof
of interoperability with the Papers With Code envelope.

## Frozen Task 1 wire and security contract

- Noise suite: `Noise_hybridIK_X25519+MLKEM768_AESGCM_SHA256`.
- Transcript domain: `pwc-persistent-executor-noise/v2`; the transcript binds
  environment, registration, stream, exact protocol version, schema digest,
  authorization-signing key ID, and both Noise public-key IDs.
- Relay header: magic `PWC1`, frame kind, 32-bit stream and operation IDs,
  64-bit sequence and cumulative `ack_next`, and a 32-bit payload length.
- Data records: at most 60 KiB. Control payloads: at most 4 KiB with 16 KiB of
  separately reserved in-flight capacity. Reordering is at most 64 records.
- Replay/data credit: 64 KiB per operation, 256 KiB per turn stream, and
  512 KiB per physical connection. A credit breach fails subsequent data on
  the shared stream while ACK, cancel, and terminal control remain deliverable.
- Detached replay state expires after 30,000 ms and never outlives its durable
  claim. ACKs are monotonic, bounded by the next sent sequence, and release
  replay capacity without permitting re-delivery.
- Request boundaries before encryption: 64 KiB UTF-8 command, 4 KiB UTF-8
  path, 30,000 ms Bash timeout, and 1 MiB read with non-negative, checked
  offset arithmetic.
- Routine compatibility is exactly current `N` plus `N-1` for at most 24
  hours. New registrations select only `N`; authorization signatures and the
  Noise transcript bind the selected version and schema digest. An
  incompatible/security release has no previous-version window.
- Verification contains exactly one current and optional immediately previous
  public authorization key. Unknown, inactive, expired, or revoked key IDs
  fail closed. Emergency revocation is rechecked for fresh, cached, detached,
  and previously acknowledged stream state.

Golden vectors are executable in `tests/protocol.rs`: the `PWC1` frame bytes,
the bound-prologue SHA-256, deterministic Ed25519 authorization signature,
version/schema downgrade cases, boundary inputs, credit edges, replay, and
expiry. `vectors/bootstrap_v1.json` remains the public Ed25519 registration and
recovery proof vector frozen by Task 0.

## Resolved prerequisites

First registration uses the Task 0 60-second single-use launch credential plus
proof of possession of the fresh environment identity; it never requires a
heartbeat token. A lost response or post-consumption handshake failure uses the
10-second, at-most-three-challenge recovery exchange for the same retained
attempt and identity. Heartbeat reconnect tokens last 45 seconds, use durable
single-use nonces, and do not extend the 30-second live-claim stream window.
Generation transitions require a new issuer authorization bound to the
existing identity and fence the old route.

Noise and replay state live only in the environment and harness processes.
Rendezvous loss is resumable while both peers and the durable claim survive.
Harness or environment process loss destroys private stream state, fences and
reconciles the turn, and never reconstructs or replays an uncertain command.

## Code that must be implemented locally

The upstream repository does not supply a deployable registry or rendezvous
service for this product. Papers With Code must implement and own:

- pending-environment provisioning and single-use launch credentials;
- proof-of-possession registration and bounded response-loss recovery;
- heartbeat token issuance, durable nonce consumption, and recovery after a
  consumed-token handshake failure;
- cell/shard/environment generations, liveness assertions, claims, fencing,
  drain, key epochs, and emergency revocation;
- the 250-start/s priority scheduler and invalid-pre-authentication limiters;
- the payload-blind, Unix-socket-only rendezvous service and nginx contract;
- operation identity, command policy, process execution, capability lifetime,
  cancellation, settlement, and reconciliation.

No upstream registry endpoint, OpenAI authentication mechanism, hosted relay,
telemetry route, command dispatcher, or local CLI sandbox policy is copied.

## Task 0 candidate

The candidate uses Rust 1.95.0, matching the pinned upstream
`codex-rs/rust-toolchain.toml`, and `clatter` 2.2.0 with only the reviewed
X25519, ML-KEM, AES-GCM, SHA, allocation, and secure-random features. The
`pwc-executor-environment --self-test` binary performs a real Hybrid IK
exchange with distinct static identities, verifies the authenticated
authorization payload, encrypts the `pwd` request and response, and reports
stage timings. The Modal candidate is compiled for
`x86_64-unknown-linux-musl` as a static executable so its runtime ABI does not
depend on the build host's glibc. It is a feasibility artifact, not a
production daemon or a substitute for the process-separated rendezvous and
recovery gates.
