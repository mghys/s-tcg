"""Exact probability propagation for WS damage and deck-disruption actions."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
from typing import TypeAlias

from .model import (
    BottomConditional,
    BottomPerClimax,
    CalculationInput,
    CalculationResult,
    Damage,
    Mocha,
)


Card: TypeAlias = int  # 0 normal, 1 climax
Outcome: TypeAlias = tuple[Fraction, Fraction, Fraction]
LEVEL_DEFEAT: Outcome = (Fraction(1), Fraction(0), Fraction(0))
REFRESH_DEFEAT: Outcome = (Fraction(0), Fraction(1), Fraction(0))
SURVIVAL: Outcome = (Fraction(0), Fraction(0), Fraction(1))
REVEAL = 0
PLACE_HIT = 1
BOTTOM_MILL = 2
BOTTOM_HIT = 4
BOTTOM_REFRESH = 5


@dataclass(frozen=True, slots=True)
class State:
    operation_index: int
    phase: int
    progress: int
    pending_normals: int
    deck_n: int
    deck_c: int
    # Cards already assigned to known positions at the top of the deck.
    top: tuple[Card, ...]
    waiting_n: int
    waiting_c: int
    clock_n: int
    clock_c: int
    level: int
    bottom_climaxes: int = 0
    resume_phase: int = REVEAL
    bottom_hits_left: int = 0


def _sum_outcomes(weighted: tuple[tuple[Fraction, Outcome], ...]) -> Outcome:
    return tuple(
        sum((weight * outcome[index] for weight, outcome in weighted), Fraction(0))
        for index in range(3)
    )  # type: ignore[return-value]


def _add_clock_card(
    state: State, add_climax: bool, continuation: State
) -> tuple[tuple[State, ...], bool]:
    clock_n = state.clock_n + (0 if add_climax else 1)
    clock_c = state.clock_c + (1 if add_climax else 0)
    if clock_n + clock_c < 7:
        return (
            State(
                continuation.operation_index,
                continuation.phase,
                continuation.progress,
                continuation.pending_normals,
                continuation.deck_n,
                continuation.deck_c,
                continuation.top,
                continuation.waiting_n,
                continuation.waiting_c,
                clock_n,
                clock_c,
                state.level,
                continuation.bottom_climaxes,
                continuation.resume_phase,
                continuation.bottom_hits_left,
            ),
        ), False

    new_level = state.level + 1
    if new_level >= 4:
        return (), True

    successors: list[State] = []
    if clock_n:
        successors.append(
            State(
                continuation.operation_index,
                continuation.phase,
                continuation.progress,
                continuation.pending_normals,
                continuation.deck_n,
                continuation.deck_c,
                continuation.top,
                continuation.waiting_n + clock_n - 1,
                continuation.waiting_c + clock_c,
                0,
                0,
                new_level,
                continuation.bottom_climaxes,
                continuation.resume_phase,
                continuation.bottom_hits_left,
            )
        )
    if clock_c:
        successors.append(
            State(
                continuation.operation_index,
                continuation.phase,
                continuation.progress,
                continuation.pending_normals,
                continuation.deck_n,
                continuation.deck_c,
                continuation.top,
                continuation.waiting_n + clock_n,
                continuation.waiting_c + clock_c - 1,
                0,
                0,
                new_level,
                continuation.bottom_climaxes,
                continuation.resume_phase,
                continuation.bottom_hits_left,
            )
        )
    return tuple(successors), False


def calculate(request: CalculationInput) -> CalculationResult:
    """Calculate exact outcome probabilities for a mixed ordered action list."""
    if request.level >= 4:
        return CalculationResult(Fraction(1), Fraction(0), Fraction(0))

    operations = request.operations
    initial = State(
        operation_index=0,
        phase=REVEAL,
        progress=0,
        pending_normals=0,
        deck_n=request.deck_count - request.deck_climax,
        deck_c=request.deck_climax,
        top=(),
        waiting_n=request.waiting_count - request.waiting_climax,
        waiting_c=request.waiting_climax,
        clock_n=request.clock - request.clock_climax,
        clock_c=request.clock_climax,
        level=request.level,
    )

    def next_operation(state: State) -> State:
        return State(
            state.operation_index + 1,
            REVEAL,
            0,
            0,
            state.deck_n,
            state.deck_c,
            state.top,
            state.waiting_n,
            state.waiting_c,
            state.clock_n,
            state.clock_c,
            state.level,
            state.bottom_climaxes,
            state.resume_phase,
            state.bottom_hits_left,
        )

    def after_clock_add(state: State, is_climax: bool, continuation: State) -> Outcome:
        successors, defeated = _add_clock_card(state, is_climax, continuation)
        if defeated:
            return LEVEL_DEFEAT
        candidates = tuple(solve(successor) for successor in successors)
        return max(candidates, key=lambda outcome: outcome[2])

    def draw_top(state: State) -> tuple[tuple[Fraction, Card, State], ...]:
        """Draw one card, with known top cards consumed before random cards."""
        if state.top:
            card = state.top[0]
            return (
                (
                    Fraction(1),
                    card,
                    State(
                        state.operation_index,
                        state.phase,
                        state.progress,
                        state.pending_normals,
                        state.deck_n,
                        state.deck_c,
                        state.top[1:],
                        state.waiting_n,
                        state.waiting_c,
                        state.clock_n,
                        state.clock_c,
                        state.level,
                    ),
                ),
            )
        deck_total = state.deck_n + state.deck_c
        branches: list[tuple[Fraction, Card, State]] = []
        if state.deck_n:
            branches.append(
                (
                    Fraction(state.deck_n, deck_total),
                    0,
                    State(
                        state.operation_index,
                        state.phase,
                        state.progress,
                        state.pending_normals,
                        state.deck_n - 1,
                        state.deck_c,
                        (),
                        state.waiting_n,
                        state.waiting_c,
                        state.clock_n,
                        state.clock_c,
                        state.level,
                    ),
                )
            )
        if state.deck_c:
            branches.append(
                (
                    Fraction(state.deck_c, deck_total),
                    1,
                    State(
                        state.operation_index,
                        state.phase,
                        state.progress,
                        state.pending_normals,
                        state.deck_n,
                        state.deck_c - 1,
                        (),
                        state.waiting_n,
                        state.waiting_c,
                        state.clock_n,
                        state.clock_c,
                        state.level,
                    ),
                )
            )
        return tuple(branches)

    def resolve_damage(
        state: State,
        damage_points: int,
        hit_continuation: State,
        cancel_continuation: State | None = None,
    ) -> Outcome:
        """Resolve a full damage check, then continue with its supplied state."""
        if state.phase == PLACE_HIT:
            if state.pending_normals == 0:
                return solve(hit_continuation)
            remaining = State(
                state.operation_index,
                PLACE_HIT,
                state.progress,
                state.pending_normals - 1,
                state.deck_n,
                state.deck_c,
                state.top,
                state.waiting_n,
                state.waiting_c,
                state.clock_n,
                state.clock_c,
                state.level,
                state.bottom_climaxes,
                state.resume_phase,
                state.bottom_hits_left,
            )
            return after_clock_add(state, False, remaining)

        if state.deck_n + state.deck_c == 0 and not state.top:
            if state.waiting_n + state.waiting_c == 0:
                return REFRESH_DEFEAT
            shuffled_n = state.waiting_n
            shuffled_c = state.waiting_c
            base = State(
                state.operation_index,
                state.phase,
                state.progress,
                0,
                shuffled_n,
                shuffled_c,
                (),
                0,
                0,
                state.clock_n,
                state.clock_c,
                state.level,
                state.bottom_climaxes,
                state.resume_phase,
                state.bottom_hits_left,
            )
            branches: list[tuple[Fraction, Outcome]] = []
            for probability, card, after_draw in draw_top(base):
                branches.append(
                    (probability, after_clock_add(base, bool(card), after_draw))
                )
            return _sum_outcomes(tuple(branches))

        branches_outcome: list[tuple[Fraction, Outcome]] = []
        if cancel_continuation is None:
            cancel_continuation = next_operation(state)
        for probability, card, after_draw in draw_top(state):
            if card == 1:
                canceled = State(
                    cancel_continuation.operation_index,
                    cancel_continuation.phase,
                    cancel_continuation.progress,
                    0,
                    after_draw.deck_n,
                    after_draw.deck_c,
                    after_draw.top,
                    cancel_continuation.waiting_n + state.progress,
                    cancel_continuation.waiting_c + 1,
                    cancel_continuation.clock_n,
                    cancel_continuation.clock_c,
                    cancel_continuation.level,
                    cancel_continuation.bottom_climaxes,
                    cancel_continuation.resume_phase,
                    cancel_continuation.bottom_hits_left,
                )
                branches_outcome.append((probability, solve(canceled)))
            else:
                progress = state.progress + 1
                phase = PLACE_HIT if progress == damage_points else REVEAL
                continuation = State(
                    state.operation_index,
                    phase,
                    progress,
                    progress if phase == PLACE_HIT else 0,
                    after_draw.deck_n,
                    after_draw.deck_c,
                    after_draw.top,
                    state.waiting_n,
                    state.waiting_c,
                    state.clock_n,
                    state.clock_c,
                    state.level,
                    state.bottom_climaxes,
                    state.resume_phase,
                    state.bottom_hits_left,
                )
                branches_outcome.append((probability, solve(continuation)))
        return _sum_outcomes(tuple(branches_outcome))

    def solve_damage_from_continuation(
        state: State,
        points: int,
        continuation: State,
        cancel_continuation: State | None = None,
    ) -> Outcome:
        reveal_state = State(
            state.operation_index,
            REVEAL,
            0,
            0,
            state.deck_n,
            state.deck_c,
            state.top,
            state.waiting_n,
            state.waiting_c,
            state.clock_n,
            state.clock_c,
            state.level,
            state.bottom_climaxes,
            continuation.resume_phase,
            continuation.bottom_hits_left,
        )
        return resolve_damage(reveal_state, points, continuation, cancel_continuation)

    def draw_bottom_card(state: State) -> Outcome:
        # Top-known cards have no known relationship to the deck bottom, so
        # bottom draws are sampled from the remaining unordered composition.
        deck_total = state.deck_n + state.deck_c
        if deck_total == 0 and state.top:
            card = state.top[-1]
            continuation = State(
                state.operation_index,
                BOTTOM_MILL,
                state.progress + 1,
                0,
                state.deck_n,
                state.deck_c,
                state.top[:-1],
                state.waiting_n + (1 if card == 0 else 0),
                state.waiting_c + (1 if card == 1 else 0),
                state.clock_n,
                state.clock_c,
                state.level,
                state.bottom_climaxes + (1 if card == 1 else 0),
                state.resume_phase,
                state.bottom_hits_left,
            )
            return solve(continuation)
        if deck_total <= 0:
            raise AssertionError("Bottom draw requires a non-empty deck.")
        branches: list[tuple[Fraction, Outcome]] = []
        if state.deck_n:
            continuation = State(
                state.operation_index,
                BOTTOM_MILL,
                state.progress + 1,
                0,
                state.deck_n - 1,
                state.deck_c,
                state.top,
                state.waiting_n + 1,
                state.waiting_c,
                state.clock_n,
                state.clock_c,
                state.level,
                state.bottom_climaxes,
                state.resume_phase,
                state.bottom_hits_left,
            )
            branches.append((Fraction(state.deck_n, deck_total), solve(continuation)))
        if state.deck_c:
            continuation = State(
                state.operation_index,
                BOTTOM_MILL,
                state.progress + 1,
                0,
                state.deck_n,
                state.deck_c - 1,
                state.top,
                state.waiting_n,
                state.waiting_c + 1,
                state.clock_n,
                state.clock_c,
                state.level,
                state.bottom_climaxes + 1,
                state.resume_phase,
                state.bottom_hits_left,
            )
            branches.append((Fraction(state.deck_c, deck_total), solve(continuation)))
        return _sum_outcomes(tuple(branches))

    def refresh_for_bottom_mill(
        state: State,
        resume_state: State,
    ) -> tuple[tuple[Fraction, State | None], ...] | None:
        """Return refresh-point branches, or None when refresh is impossible."""
        waiting_total = state.waiting_n + state.waiting_c
        if waiting_total == 0:
            return None
        base = State(
            resume_state.operation_index,
            BOTTOM_REFRESH,
            resume_state.progress,
            0,
            state.waiting_n,
            state.waiting_c,
            (),
            0,
            0,
            state.clock_n,
            state.clock_c,
            state.level,
            resume_state.bottom_climaxes,
            resume_state.resume_phase,
            resume_state.bottom_hits_left,
        )
        branches: list[tuple[Fraction, State | None]] = []
        for is_climax, count in ((False, base.deck_n), (True, base.deck_c)):
            if not count:
                continue
            after_refresh_draw = State(
                resume_state.operation_index,
                BOTTOM_REFRESH,
                base.progress,
                0,
                base.deck_n - (1 if not is_climax else 0),
                base.deck_c - (1 if is_climax else 0),
                (),
                0,
                0,
                base.clock_n,
                base.clock_c,
                base.level,
                resume_state.bottom_climaxes,
                resume_state.resume_phase,
                resume_state.bottom_hits_left,
            )
            successors, defeated = _add_clock_card(base, is_climax, after_refresh_draw)
            if defeated:
                branches.append(
                    (
                        Fraction(count, waiting_total),
                        None,
                    )
                )
            else:
                resumed_options = tuple(
                    State(
                        operation_index=successor.operation_index,
                        phase=BOTTOM_MILL,
                        progress=successor.progress,
                        pending_normals=0,
                        deck_n=successor.deck_n,
                        deck_c=successor.deck_c,
                        top=successor.top,
                        waiting_n=successor.waiting_n,
                        waiting_c=successor.waiting_c,
                        clock_n=successor.clock_n,
                        clock_c=successor.clock_c,
                        level=successor.level,
                        bottom_climaxes=successor.bottom_climaxes,
                        resume_phase=BOTTOM_MILL,
                    )
                    for successor in successors
                )
                chosen_resume = max(
                    resumed_options, key=lambda candidate: solve(candidate)[2]
                )
                branches.append((Fraction(count, waiting_total), chosen_resume))
        return tuple(branches)

    def resolve_bottom_refresh(state: State) -> Outcome:
        resume = State(
            state.operation_index,
            BOTTOM_MILL,
            state.progress,
            0,
            state.deck_n,
            state.deck_c,
            state.top,
            state.waiting_n,
            state.waiting_c,
            state.clock_n,
            state.clock_c,
            state.level,
            state.bottom_climaxes,
            BOTTOM_MILL,
            0,
        )
        refreshed = refresh_for_bottom_mill(state, resume)
        if refreshed is None:
            return REFRESH_DEFEAT
        outcomes: list[tuple[Fraction, Outcome]] = []
        for probability, after_refresh in refreshed:
            if after_refresh is None:
                outcomes.append((probability, LEVEL_DEFEAT))
                continue
            # The refresh point itself is the one refresh damage. Do not
            # resolve an additional ordinary damage check before milling.
            outcomes.append((probability, solve(after_refresh)))
        return _sum_outcomes(tuple(outcomes))

    @lru_cache(maxsize=None)
    def solve(state: State) -> Outcome:
        if state.level >= 4:
            return LEVEL_DEFEAT
        if state.operation_index >= len(operations):
            return SURVIVAL

        operation = operations[state.operation_index]

        if state.phase == BOTTOM_REFRESH:
            return resolve_bottom_refresh(state)

        if state.phase == BOTTOM_HIT:
            assert isinstance(operation, (BottomConditional, BottomPerClimax))
            if state.bottom_hits_left <= 0:
                return solve(next_operation(state))
            next_impact = State(
                state.operation_index,
                BOTTOM_HIT,
                0,
                0,
                state.deck_n,
                state.deck_c,
                state.top,
                state.waiting_n,
                state.waiting_c,
                state.clock_n,
                state.clock_c,
                state.level,
                state.bottom_climaxes,
                BOTTOM_HIT,
                state.bottom_hits_left - 1,
            )
            return solve_damage_from_continuation(
                state,
                operation.damage,
                next_impact,
                cancel_continuation=next_impact,
            )

        if isinstance(operation, Mocha):
            # Looking at the deck does not cause a refresh. If fewer than x
            # cards remain, inspect all available cards.
            look_count = min(
                operation.look, state.deck_n + state.deck_c + len(state.top)
            )
            observations: dict[tuple[int, int, State], Fraction] = {}

            def enumerate_observed(
                current: State,
                prefix: tuple[Card, ...],
                probability: Fraction,
                left: int,
            ) -> None:
                if left == 0:
                    key = (prefix.count(0), prefix.count(1), current)
                    observations[key] = observations.get(key, Fraction(0)) + probability
                    return
                if current.top or current.deck_n + current.deck_c:
                    for branch_probability, card, after_draw in draw_top(current):
                        enumerate_observed(
                            after_draw,
                            prefix + (card,),
                            probability * branch_probability,
                            left - 1,
                        )
                    return
                key = (prefix.count(0), prefix.count(1), current)
                observations[key] = observations.get(key, Fraction(0)) + probability

            enumerate_observed(state, (), Fraction(1), look_count)
            weighted: list[tuple[Fraction, Outcome]] = []
            for (
                revealed_normals,
                revealed_climaxes,
                after_look,
            ), probability in observations.items():
                # Up to x revealed cards may be moved to the waiting room;
                # the attacker also chooses the order of retained top cards.
                decisions: list[Outcome] = []
                for discard_n in range(revealed_normals + 1):
                    for discard_c in range(revealed_climaxes + 1):
                        kept_n = revealed_normals - discard_n
                        kept_c = revealed_climaxes - discard_c
                        kept_count = kept_n + kept_c
                        for normal_positions in combinations(range(kept_count), kept_n):
                            normal_position_set = set(normal_positions)
                            ordered_kept = tuple(
                                0 if index in normal_position_set else 1
                                for index in range(kept_count)
                            )
                            continuation = State(
                                state.operation_index + 1,
                                REVEAL,
                                0,
                                0,
                                after_look.deck_n,
                                after_look.deck_c,
                                ordered_kept + after_look.top,
                                state.waiting_n + discard_n,
                                state.waiting_c + discard_c,
                                state.clock_n,
                                state.clock_c,
                                state.level,
                            )
                            decisions.append(solve(continuation))
                # Attacker maximizes defeat probability (minimizes survival).
                weighted.append(
                    (probability, min(decisions, key=lambda outcome: outcome[2]))
                )
            return _sum_outcomes(tuple(weighted))

        if isinstance(operation, (BottomConditional, BottomPerClimax)):
            # Cards milled from the bottom are event-local until the full
            # requested count is reached. If the deck empties midway, normal
            # refresh applies to the existing waiting room. The refresh point
            # is the single rule-required damage; milling then resumes.
            if state.phase != BOTTOM_MILL:
                state = State(
                    state.operation_index,
                    BOTTOM_MILL,
                    0,
                    0,
                    state.deck_n,
                    state.deck_c,
                    state.top,
                    state.waiting_n,
                    state.waiting_c,
                    state.clock_n,
                    state.clock_c,
                    state.level,
                    0,
                    REVEAL,
                    0,
                )

            if state.progress >= operation.mill:
                # All milled cards now enter the waiting room as one completed
                # bottom-mill event; their climax count is retained separately
                # until the selected damage mode is evaluated.
                committed = State(
                    state.operation_index,
                    BOTTOM_MILL,
                    state.progress,
                    0,
                    state.deck_n,
                    state.deck_c,
                    state.top,
                    state.waiting_n,
                    state.waiting_c,
                    state.clock_n,
                    state.clock_c,
                    state.level,
                    state.bottom_climaxes,
                    REVEAL,
                    0,
                )
                if isinstance(operation, BottomConditional):
                    if state.bottom_climaxes:
                        continuation = State(
                            state.operation_index + 1,
                            REVEAL,
                            0,
                            0,
                            state.deck_n,
                            state.deck_c,
                            state.top,
                            committed.waiting_n,
                            committed.waiting_c,
                            state.clock_n,
                            state.clock_c,
                            state.level,
                        )
                        return solve_damage_from_continuation(
                            committed, operation.damage, continuation
                        )
                    return solve(
                        State(
                            state.operation_index + 1,
                            REVEAL,
                            0,
                            0,
                            state.deck_n,
                            state.deck_c,
                            state.top,
                            committed.waiting_n,
                            committed.waiting_c,
                            state.clock_n,
                            state.clock_c,
                            state.level,
                        )
                    )
                hit_count = min(state.bottom_climaxes, operation.mill)
                if hit_count == 0:
                    return solve(next_operation(committed))
                return solve(
                    State(
                        state.operation_index,
                        BOTTOM_HIT,
                        0,
                        0,
                        committed.deck_n,
                        committed.deck_c,
                        committed.top,
                        committed.waiting_n,
                        committed.waiting_c,
                        committed.clock_n,
                        committed.clock_c,
                        committed.level,
                        state.bottom_climaxes,
                        BOTTOM_HIT,
                        hit_count,
                    )
                )

            if state.deck_n + state.deck_c == 0 and not state.top:
                return resolve_bottom_refresh(state)

            return draw_bottom_card(state)

        # Damage action; draw until a climax cancels it or enough normals are
        # revealed. The current operation index is preserved through refresh.
        assert isinstance(operation, Damage)
        if state.phase != REVEAL:
            return resolve_damage(state, operation.points, next_operation(state))

        if state.deck_n + state.deck_c == 0 and not state.top:
            if state.waiting_n + state.waiting_c == 0:
                return REFRESH_DEFEAT
            shuffled_n = state.waiting_n
            shuffled_c = state.waiting_c
            total = shuffled_n + shuffled_c
            base = State(
                state.operation_index,
                REVEAL,
                state.progress,
                0,
                shuffled_n,
                shuffled_c,
                (),
                0,
                0,
                state.clock_n,
                state.clock_c,
                state.level,
            )
            branches: list[tuple[Fraction, Outcome]] = []
            for probability, card, after_draw in draw_top(base):
                branches.append(
                    (probability, after_clock_add(base, bool(card), after_draw))
                )
            return _sum_outcomes(tuple(branches))

        return resolve_damage(state, operation.points, next_operation(state))

    outcome = solve(initial)
    return CalculationResult(*outcome)
