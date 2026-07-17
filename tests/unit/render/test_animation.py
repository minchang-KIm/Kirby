"""Animation contracts for render-cadence-only state."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from windsprig.render.animation import AnimationBank, AnimationClip, AnimationCursor


def test_animation_advances_once_per_render_delta_and_emits_markers_once() -> None:
    clip = AnimationClip("attack", (20, 21, 22), (80, 80, 120), False, ((1, "swing"),))

    advanced, markers = AnimationCursor.start(clip).advance(170)

    assert (advanced.frame_id, advanced.elapsed_in_frame_ms, markers) == (22, 10, ("swing",))


def test_looping_animation_emits_every_crossed_marker_in_chronological_order() -> None:
    clip = AnimationClip(
        "pulse",
        (7, 8),
        (10, 20),
        True,
        ((0, "cycle"), (1, "beat")),
    )

    advanced, markers = AnimationCursor.start(clip).advance(65)

    assert (advanced.frame_id, advanced.elapsed_in_frame_ms, advanced.finished) == (7, 5, False)
    assert markers == ("beat", "cycle", "beat", "cycle")


def test_terminal_animation_freezes_without_repeating_final_marker() -> None:
    clip = AnimationClip("hurt", (4, 5), (10, 10), False, ((1, "impact"),))
    terminal, first_markers = AnimationCursor.start(clip).advance(10_000)

    unchanged, repeated_markers = terminal.advance(10_000)

    assert terminal == AnimationCursor(clip, 1, 0, True)
    assert first_markers == ("impact",)
    assert unchanged is terminal
    assert repeated_markers == ()


def test_zero_delta_leaves_animation_cursor_unchanged() -> None:
    cursor = AnimationCursor.start(AnimationClip("idle", (0,), (80,), True))

    advanced, markers = cursor.advance(0)

    assert advanced is cursor
    assert markers == ()


@pytest.mark.parametrize(
    ("arguments", "exception"),
    [
        (("", (0,), (80,), True), ValueError),
        ((True, (0,), (80,), True), TypeError),
        (("idle", (), (), True), ValueError),
        (("idle", (0, 0), (80, 80), True), ValueError),
        (("idle", (True,), (80,), True), TypeError),
        (("idle", (0,), (0,), True), ValueError),
        (("idle", (0,), (True,), True), TypeError),
        (("idle", (0,), (80,), 1), TypeError),
        (("idle", (0,), (80,), True, ((1, "late"),)), ValueError),
        (("idle", (0,), (80,), True, ((0, ""),)), ValueError),
        (("idle", (0,), (80,), True, ((0, "tick"), (0, "tick"))), ValueError),
    ],
)
def test_animation_clip_rejects_malformed_identity_duration_and_markers(
    arguments: tuple[object, ...],
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        AnimationClip(*arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("delta", [-1, True, 1.5])
def test_animation_cursor_rejects_invalid_render_delta(delta: object) -> None:
    cursor = AnimationCursor.start(AnimationClip("idle", (0,), (80,), True))

    with pytest.raises((TypeError, ValueError)):
        cursor.advance(delta)  # type: ignore[arg-type]


def test_animation_bank_is_deeply_immutable_and_uses_documented_idle_fallback() -> None:
    idle = AnimationClip("idle", (0,), (80,), True)
    run = AnimationClip("run", (1, 2), (60, 60), True)
    caller_owned = {"run": run, "idle": idle}
    bank = AnimationBank(caller_owned)
    caller_owned["idle"] = run

    assert isinstance(bank.clips, MappingProxyType)
    assert tuple(bank.clips) == ("idle", "run")
    assert bank.clip_for("RUN") is run
    assert bank.clip_for("unsupported_actor_state") is idle
    with pytest.raises(TypeError):
        bank.clips["idle"] = run  # type: ignore[index]
    with pytest.raises(ValueError, match="actor state"):
        bank.clip_for("")
