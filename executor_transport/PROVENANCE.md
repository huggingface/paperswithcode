# Persistent executor transport provenance

Task 0 freezes the source boundary before any transport port. No upstream code
is copied in this milestone.

## Upstream pin

- Repository: `https://github.com/openai/codex`
- Commit: `c62d191c4c8c0cab7045fca6efc399197334bb6c`
- License: Apache-2.0 (`LICENSE` at the pinned commit)
- Security profile: `noise_hybrid_ik_v1`
- Upstream Rust dependency lock SHA-256:
  `5591e039ef19dd7e2569efa1060d263e5169af86b6012d3a0e84e7ca54d8d155`
- Local interoperability vectors:
  `executor_transport/vectors/bootstrap_v1.json` at SHA-256
  `9db33156d64742c2510604064b7e5b8733b196c8c9611d0755e889aafa5e0743`

The upstream `codex-rs/Cargo.lock` is the dependency-closure record that was
reviewed. The smaller local `Cargo.lock` is independently pinned at SHA-256
`22e0789ed26c4bf074f623c073de12ef174e302a4bd6cdd28f19106bf5022cd2`;
the upstream lock is not a substitute for it.

## Reviewed source boundary

| Upstream path | Git blob | Task 1 disposition |
| --- | --- | --- |
| `codex-rs/exec-server/src/noise_channel.rs` | `cde2aae4eeb1ccedf3d3617bd1e7fa2ba2e21796` | Narrow attributed Task 0 adaptation of the Hybrid IK identity, transcript, and transport wrapper. |
| `codex-rs/exec-server/src/remote.rs` | `0d2711b7a8a4c4284220cc2e296dd04e678cc879` | Study registry client, profile check, and connection lifecycle; reimplement the Papers With Code bootstrap. |
| `codex-rs/exec-server/src/remote/registration_retry.rs` | `1a2dc989da947393a1191ea4200ab8346825925c` | Study bounded retry behavior; replace authentication with the generation-bound state machine. |
| `codex-rs/exec-server/src/noise_relay/message_framing.rs` | `af9fbd49986f0e23da32acf44ecee4ac377f536c` | Candidate for a narrow attributed port. |
| `codex-rs/exec-server/src/noise_relay/ordered_ciphertext.rs` | `92bbd291d72f8130881a9364e43323a5566571ad` | Candidate for a narrow attributed port. |
| `codex-rs/exec-server/src/noise_relay/stream_handler.rs` | `b0c610933c09d3b98bfe10fa6f7e5e2e744b7131` | Candidate for a narrow attributed port after buffer and resume review. |
| `codex-rs/exec-server/src/noise_relay/executor_stream.rs` | `612cc9781f1f607c58d72832073187275713d73c` | Candidate for a narrow attributed port after command-envelope removal. |
| `codex-rs/exec-server/src/noise_relay/harness.rs` | `793f7c1e12e9816e58606b3ffeaf9a1b009f5b2a` | Study Hybrid IK construction and readiness; adapt to turn-scoped authorization. |
| `codex-rs/exec-server/src/relay.rs` | `40afbf0e288895451c07f04de89d33c651fb50f8` | Study harness-key validation; do not import its service assumptions. |

Upstream test blobs are reviewed with their matching modules, especially
`remote/noise_tests.rs`, `noise_relay/message_framing_tests.rs`,
`noise_relay/ordered_ciphertext_tests.rs`, and
`noise_relay/stream_handler_tests.rs`. Their vectors are not treated as proof
of interoperability with the Papers With Code envelope.

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
stage timings. It is a feasibility artifact, not a production daemon or a
substitute for the process-separated rendezvous and recovery gates.
