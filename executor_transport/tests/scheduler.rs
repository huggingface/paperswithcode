use pwc_persistent_executor_transport::scheduler::{
    Contender, GLOBAL_INVALID_BURST, HANDSHAKES_PER_SECOND, InvalidAttemptGate, InvalidDecision,
    MAX_PREAUTH_SOCKETS, MAX_TRACKED_INVALID_SOURCES, PER_SOURCE_INVALID_BURST, PreauthCapacity,
    ReconnectBackoff, ReconnectClass, ReconnectScheduler, ScheduleDecision,
};

#[test]
fn handshake_starts_are_capped_at_250_per_rolling_second() {
    let mut scheduler = ReconnectScheduler::new();
    for ordinal in 0..HANDSHAKES_PER_SECOND {
        assert!(matches!(
            scheduler.try_start(
                [Contender::new(ordinal as u64, ReconnectClass::BlankPool, 0)],
                1_000,
                ordinal as u64,
            ),
            ScheduleDecision::Started(_)
        ));
    }
    assert!(matches!(
        scheduler.try_start(
            [Contender::new(999, ReconnectClass::ActiveClaim, 0)],
            1_999,
            4,
        ),
        ScheduleDecision::Retry {
            after_ms: 50..=2_000
        }
    ));
    assert!(matches!(
        scheduler.try_start(
            [Contender::new(999, ReconnectClass::ActiveClaim, 0)],
            2_000,
            4,
        ),
        ScheduleDecision::Started(_)
    ));
}

#[test]
fn invalid_source_and_preauth_socket_memory_are_bounded() {
    let mut gate = InvalidAttemptGate::new(0);
    for ordinal in 0..MAX_TRACKED_INVALID_SOURCES + 100 {
        gate.invalid(&format!("source-{ordinal}"), ordinal as u64 * 1_000);
    }
    assert_eq!(gate.tracked_sources(), MAX_TRACKED_INVALID_SOURCES);

    let mut capacity = PreauthCapacity::default();
    for _ in 0..MAX_PREAUTH_SOCKETS {
        assert!(capacity.try_open());
    }
    assert!(!capacity.try_open());
    capacity.close();
    assert!(capacity.try_open());
}

#[test]
fn active_claims_receive_reserved_future_tokens_and_idle_capacity_is_borrowed() {
    let mut scheduler = ReconnectScheduler::new();
    let contenders = [
        Contender::new(1, ReconnectClass::BlankPool, 0),
        Contender::new(2, ReconnectClass::AssignedIdle, 0),
        Contender::new(3, ReconnectClass::ActiveClaim, 0),
    ];
    for ordinal in 0..4 {
        let decision = scheduler.try_start(contenders, ordinal, ordinal);
        if ordinal == 0 {
            assert_eq!(decision, ScheduleDecision::Started(contenders[2]));
        }
    }

    let mut borrowing = ReconnectScheduler::new();
    for ordinal in 0..8 {
        assert!(matches!(
            borrowing.try_start(
                [Contender::new(ordinal, ReconnectClass::BlankPool, 0)],
                ordinal,
                ordinal,
            ),
            ScheduleDecision::Started(_)
        ));
    }
}

#[test]
fn bounded_aging_prevents_blank_starvation_inside_five_seconds() {
    let mut scheduler = ReconnectScheduler::new();
    scheduler.try_start([Contender::new(0, ReconnectClass::ActiveClaim, 0)], 0, 0);
    let blank = Contender::new(1, ReconnectClass::BlankPool, 0);
    let decision = scheduler.try_start(
        [
            blank,
            Contender::new(2, ReconnectClass::AssignedIdle, 4_999),
            Contender::new(3, ReconnectClass::ActiveClaim, 4_999),
        ],
        4_999,
        0,
    );
    assert_eq!(decision, ScheduleDecision::Started(blank));
}

#[test]
fn full_jitter_backoff_honors_bounds_and_resets_only_after_stability() {
    let mut backoff = ReconnectBackoff::new();
    assert_eq!(backoff.next_delay_ms(0), 50);
    for attempt in 1..20 {
        assert!((50..=2_000).contains(&backoff.next_delay_ms(attempt)));
    }
    backoff.connected(1_000);
    backoff.disconnected(30_999);
    assert!(!backoff.is_reset());
    backoff.connected(40_000);
    backoff.disconnected(70_000);
    assert!(backoff.is_reset());
}

#[test]
fn invalid_limiters_are_separate_and_valid_tokens_always_bypass_them() {
    let mut gate = InvalidAttemptGate::new(0);
    for _ in 0..PER_SOURCE_INVALID_BURST {
        assert_eq!(gate.invalid("shared-egress", 0), InvalidDecision::Reject);
    }
    assert_eq!(
        gate.invalid("shared-egress", 0),
        InvalidDecision::SilentClose
    );
    assert_eq!(gate.valid("shared-egress", 0), InvalidDecision::AdmitValid);

    let mut global = InvalidAttemptGate::new(0);
    for ordinal in 0..GLOBAL_INVALID_BURST {
        assert_eq!(
            global.invalid(&format!("source-{ordinal}"), 0),
            InvalidDecision::Reject
        );
    }
    assert_eq!(
        global.invalid("new-source", 0),
        InvalidDecision::SilentClose
    );
    assert_eq!(global.valid("new-source", 0), InvalidDecision::AdmitValid);

    assert_eq!(gate.invalid("shared-egress", 100), InvalidDecision::Reject);
}
