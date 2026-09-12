use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, PendingResponderHandshake, prologue,
};

#[test]
fn hybrid_ik_authenticates_both_static_keys_and_encrypts_transport() {
    let harness = NoiseIdentity::generate().unwrap();
    let environment = NoiseIdentity::generate().unwrap();
    let transcript = prologue("environment-7", "registration-11", "stream-13");

    let (initiator, request) = InitiatorHandshake::start(
        &harness,
        &environment.public_key(),
        &transcript,
        b"authorization-17",
    )
    .unwrap();
    let responder =
        PendingResponderHandshake::read_request(&environment, &transcript, &request).unwrap();
    assert_eq!(responder.initiator_public_key(), &harness.public_key());
    assert_eq!(responder.authorization(), b"authorization-17");

    let (mut environment_transport, response) = responder.complete().unwrap();
    let mut harness_transport = initiator.finish(&response).unwrap();
    let ciphertext = harness_transport.encrypt(b"pwd").unwrap();

    assert_ne!(ciphertext, b"pwd");
    assert_eq!(environment_transport.decrypt(&ciphertext).unwrap(), b"pwd");
}

#[test]
fn prologue_prevents_cross_stream_handshake_splicing() {
    let harness = NoiseIdentity::generate().unwrap();
    let environment = NoiseIdentity::generate().unwrap();
    let original = prologue("environment-7", "registration-11", "stream-13");
    let spliced = prologue("environment-7", "registration-11", "stream-14");
    let (_, request) = InitiatorHandshake::start(
        &harness,
        &environment.public_key(),
        &original,
        b"authorization-17",
    )
    .unwrap();

    assert!(PendingResponderHandshake::read_request(&environment, &spliced, &request).is_err());
}

#[test]
fn transport_rejects_modified_ciphertext() {
    let harness = NoiseIdentity::generate().unwrap();
    let environment = NoiseIdentity::generate().unwrap();
    let transcript = prologue("environment-7", "registration-11", "stream-13");
    let (initiator, request) = InitiatorHandshake::start(
        &harness,
        &environment.public_key(),
        &transcript,
        b"authorization-17",
    )
    .unwrap();
    let responder =
        PendingResponderHandshake::read_request(&environment, &transcript, &request).unwrap();
    let (mut environment_transport, response) = responder.complete().unwrap();
    let mut harness_transport = initiator.finish(&response).unwrap();
    let mut ciphertext = harness_transport.encrypt(b"pwd").unwrap();
    let last = ciphertext.len() - 1;
    ciphertext[last] ^= 1;

    assert!(environment_transport.decrypt(&ciphertext).is_err());
}
