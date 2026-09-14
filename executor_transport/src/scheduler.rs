//! Deterministic reconnect scheduling and invalid pre-authentication limits.

use std::collections::{HashMap, VecDeque};

pub const HANDSHAKES_PER_SECOND: usize = 250;
pub const MIN_RECONNECT_DELAY_MS: u64 = 50;
pub const MAX_RECONNECT_DELAY_MS: u64 = 2_000;
pub const BACKOFF_RESET_MS: u64 = 30_000;
pub const ACTIVE_RESERVATION_DENOMINATOR: u64 = 4;
pub const BLANK_MAX_AGE_MS: u64 = 4_000;
pub const ASSIGNED_MAX_AGE_MS: u64 = 2_000;
pub const PER_SOURCE_INVALID_RATE: u64 = 10;
pub const PER_SOURCE_INVALID_BURST: usize = 20;
pub const GLOBAL_INVALID_RATE: u64 = 100;
pub const GLOBAL_INVALID_BURST: usize = 200;
pub const MAX_TRACKED_INVALID_SOURCES: usize = 1_024;
pub const MAX_PREAUTH_SOCKETS: usize = 512;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReconnectClass {
    ActiveClaim,
    AssignedIdle,
    BlankPool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Contender {
    pub id: u64,
    pub class: ReconnectClass,
    pub waiting_since_ms: u64,
}

impl Contender {
    pub fn new(id: u64, class: ReconnectClass, waiting_since_ms: u64) -> Self {
        Self {
            id,
            class,
            waiting_since_ms,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScheduleDecision {
    Started(Contender),
    Retry { after_ms: u64 },
    Empty,
}

#[derive(Debug, Default)]
pub struct ReconnectScheduler {
    starts: VecDeque<u64>,
    issued_tokens: u64,
}

impl ReconnectScheduler {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn try_start<I>(&mut self, contenders: I, now_ms: u64, entropy: u64) -> ScheduleDecision
    where
        I: IntoIterator<Item = Contender>,
    {
        while self
            .starts
            .front()
            .is_some_and(|started| now_ms.saturating_sub(*started) >= 1_000)
        {
            self.starts.pop_front();
        }
        if self.starts.len() >= HANDSHAKES_PER_SECOND {
            return ScheduleDecision::Retry {
                after_ms: bounded_jitter(entropy, MAX_RECONNECT_DELAY_MS),
            };
        }
        let contenders: Vec<_> = contenders.into_iter().collect();
        if contenders.is_empty() {
            return ScheduleDecision::Empty;
        }
        let active_reserved = self
            .issued_tokens
            .is_multiple_of(ACTIVE_RESERVATION_DENOMINATOR);
        let selected = if active_reserved {
            contenders
                .iter()
                .copied()
                .find(|item| item.class == ReconnectClass::ActiveClaim)
                .or_else(|| select_shared(&contenders, now_ms))
        } else {
            select_shared(&contenders, now_ms)
        };
        let Some(selected) = selected else {
            return ScheduleDecision::Empty;
        };
        self.starts.push_back(now_ms);
        self.issued_tokens = self.issued_tokens.wrapping_add(1);
        ScheduleDecision::Started(selected)
    }
}

fn select_shared(contenders: &[Contender], now_ms: u64) -> Option<Contender> {
    contenders.iter().copied().min_by_key(|item| {
        let waited = now_ms.saturating_sub(item.waiting_since_ms);
        let priority = match item.class {
            ReconnectClass::BlankPool if waited >= BLANK_MAX_AGE_MS => 0,
            ReconnectClass::AssignedIdle if waited >= ASSIGNED_MAX_AGE_MS => 0,
            ReconnectClass::ActiveClaim => 0,
            ReconnectClass::AssignedIdle => 1,
            ReconnectClass::BlankPool => 2,
        };
        (priority, item.waiting_since_ms, item.id)
    })
}

#[derive(Debug, Default)]
pub struct ReconnectBackoff {
    attempts: u32,
    connected_at_ms: Option<u64>,
    reset: bool,
}

impl ReconnectBackoff {
    pub fn new() -> Self {
        Self {
            reset: true,
            ..Self::default()
        }
    }

    pub fn next_delay_ms(&mut self, entropy: u64) -> u64 {
        let exponent = self.attempts.min(6);
        let cap = MIN_RECONNECT_DELAY_MS
            .saturating_mul(1_u64 << exponent)
            .min(MAX_RECONNECT_DELAY_MS);
        self.attempts = self.attempts.saturating_add(1);
        self.reset = false;
        bounded_jitter(entropy, cap)
    }

    pub fn connected(&mut self, now_ms: u64) {
        self.connected_at_ms = Some(now_ms);
    }

    pub fn disconnected(&mut self, now_ms: u64) {
        if self
            .connected_at_ms
            .is_some_and(|connected| now_ms.saturating_sub(connected) >= BACKOFF_RESET_MS)
        {
            self.attempts = 0;
            self.reset = true;
        } else {
            self.reset = false;
        }
        self.connected_at_ms = None;
    }

    pub fn is_reset(&self) -> bool {
        self.reset
    }
}

fn bounded_jitter(entropy: u64, cap: u64) -> u64 {
    MIN_RECONNECT_DELAY_MS + entropy % (cap - MIN_RECONNECT_DELAY_MS + 1)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum InvalidDecision {
    Reject,
    SilentClose,
    AdmitValid,
}

#[derive(Debug)]
struct TokenBucket {
    milli_tokens: u64,
    capacity_milli_tokens: u64,
    refill_per_ms: u64,
    updated_at_ms: u64,
}

impl TokenBucket {
    fn new(rate: u64, burst: usize, now_ms: u64) -> Self {
        Self {
            milli_tokens: burst as u64 * 1_000,
            capacity_milli_tokens: burst as u64 * 1_000,
            refill_per_ms: rate,
            updated_at_ms: now_ms,
        }
    }

    fn available(&mut self, now_ms: u64) -> bool {
        let elapsed = now_ms.saturating_sub(self.updated_at_ms);
        self.milli_tokens = self
            .milli_tokens
            .saturating_add(elapsed.saturating_mul(self.refill_per_ms))
            .min(self.capacity_milli_tokens);
        self.updated_at_ms = now_ms;
        self.milli_tokens >= 1_000
    }

    fn consume(&mut self) {
        self.milli_tokens -= 1_000;
    }
}

#[derive(Debug)]
pub struct InvalidAttemptGate {
    global: TokenBucket,
    sources: HashMap<String, TokenBucket>,
    overflow: TokenBucket,
}

impl InvalidAttemptGate {
    pub fn new(now_ms: u64) -> Self {
        Self {
            global: TokenBucket::new(GLOBAL_INVALID_RATE, GLOBAL_INVALID_BURST, now_ms),
            sources: HashMap::new(),
            overflow: TokenBucket::new(PER_SOURCE_INVALID_RATE, PER_SOURCE_INVALID_BURST, now_ms),
        }
    }

    pub fn invalid(&mut self, source: &str, now_ms: u64) -> InvalidDecision {
        let source_bucket = if self.sources.contains_key(source) {
            self.sources.get_mut(source).expect("source checked")
        } else if self.sources.len() < MAX_TRACKED_INVALID_SOURCES {
            self.sources.entry(source.into()).or_insert_with(|| {
                TokenBucket::new(PER_SOURCE_INVALID_RATE, PER_SOURCE_INVALID_BURST, now_ms)
            })
        } else {
            &mut self.overflow
        };
        if !self.global.available(now_ms) || !source_bucket.available(now_ms) {
            return InvalidDecision::SilentClose;
        }
        self.global.consume();
        source_bucket.consume();
        InvalidDecision::Reject
    }

    pub fn valid(&mut self, _source: &str, _now_ms: u64) -> InvalidDecision {
        InvalidDecision::AdmitValid
    }

    pub fn tracked_sources(&self) -> usize {
        self.sources.len()
    }
}

#[derive(Debug, Default)]
pub struct PreauthCapacity {
    open: usize,
}

impl PreauthCapacity {
    pub fn try_open(&mut self) -> bool {
        if self.open >= MAX_PREAUTH_SOCKETS {
            return false;
        }
        self.open += 1;
        true
    }

    pub fn close(&mut self) {
        self.open = self.open.saturating_sub(1);
    }
}
