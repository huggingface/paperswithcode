//! Bounded persistent-executor transport core.
//!
//! The cryptographic construction is a narrow, attributed adaptation of
//! `openai/codex`'s remote exec-server Noise channel at the commit recorded in
//! `PROVENANCE.md`. Product-specific authorization and lifecycle state remain
//! in Papers With Code.

pub mod admission;
pub mod local_socket;
pub mod noise;
pub mod postgres_registry;
pub mod protocol;
pub mod registry;
pub mod scheduler;
