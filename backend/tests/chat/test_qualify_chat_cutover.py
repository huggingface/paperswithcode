import pytest

from backend.scripts.qualify_chat_cutover import (
    CONFIRMATION,
    DEFAULT_ROUNDS,
    DEFAULT_TURNS,
    MAX_ROUNDS,
    MAX_TURNS,
    parser,
    validate_rounds,
    validate_turns,
)


def test_cutover_qualifier_parser_requires_explicit_release_and_confirmation(tmp_path):
    release = tmp_path / "release"
    args = parser().parse_args(
        [
            "--turns",
            str(DEFAULT_TURNS),
            "--rounds",
            str(DEFAULT_ROUNDS),
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
        ]
    )

    assert args.turns == DEFAULT_TURNS
    assert args.rounds == DEFAULT_ROUNDS
    assert args.release_dir == release
    assert args.confirm == CONFIRMATION


@pytest.mark.parametrize("turns", [0, MAX_TURNS + 1])
def test_cutover_qualifier_rejects_unbounded_parallelism(turns):
    with pytest.raises(SystemExit, match=f"--turns must be 1-{MAX_TURNS}"):
        validate_turns(turns)


def test_cutover_qualifier_accepts_bounded_parallelism():
    for turns in range(1, MAX_TURNS + 1):
        validate_turns(turns)


@pytest.mark.parametrize("rounds", [0, MAX_ROUNDS + 1])
def test_cutover_qualifier_rejects_unbounded_rounds(rounds):
    with pytest.raises(SystemExit, match=f"--rounds must be 1-{MAX_ROUNDS}"):
        validate_rounds(rounds)


def test_cutover_qualifier_accepts_bounded_rounds():
    for rounds in range(1, MAX_ROUNDS + 1):
        validate_rounds(rounds)
