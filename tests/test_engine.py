from __future__ import annotations

import unittest
from fractions import Fraction
from itertools import combinations, permutations

from ws_tcg import (
    BottomConditional,
    BottomPerClimax,
    CalculationInput,
    Damage,
    InputError,
    Mocha,
    calculate,
)
from ws_tcg.engine import PLACE_HIT, State, _add_clock_card


def request(
    *,
    deck_count: int,
    deck_climax: int = 0,
    waiting_count: int = 0,
    waiting_climax: int = 0,
    level: int = 0,
    clock: int = 0,
    clock_climax: int = 0,
    damage: tuple[int, ...] = (1,),
) -> CalculationInput:
    return CalculationInput.from_values(
        deck_count=deck_count,
        deck_climax=deck_climax,
        waiting_count=waiting_count,
        waiting_climax=waiting_climax,
        level=level,
        clock=clock,
        clock_climax=clock_climax,
        damage_sequence=damage,
    )


def simulate_fixed_order(cards: tuple[str, ...], damage: tuple[int, ...]) -> bool:
    """Independent no-refresh/no-level-up simulator; True means all survive."""
    cursor = 0
    for points in damage:
        normals = 0
        canceled = False
        hit = False
        while cursor < len(cards):
            card = cards[cursor]
            cursor += 1
            if card == "C":
                canceled = True
                break
            normals += 1
            if normals == points:
                hit = True
                break
        if not (canceled or hit):
            # The fixed deck ended before enough normals were revealed.
            return False
    return True


class EngineTests(unittest.TestCase):
    def test_user_example_clock_overflow_resumes_in_new_clock(self) -> None:
        result = calculate(request(deck_count=5, level=1, clock=4, damage=(5,)))
        self.assertEqual(result.defeat, 0)
        self.assertEqual(result.survival, 1)

        # Five normals are hit. The first two fill clock to six; the third
        # causes level-up and sends six remaining clock cards to waiting;
        # the two unplaced hit cards become the new clock.
        state = State(0, PLACE_HIT, 5, 5, 0, 0, (), 0, 0, 4, 0, 1)
        for remaining in range(4, -1, -1):
            continuation = State(
                0,
                PLACE_HIT,
                5,
                remaining,
                0,
                0,
                (),
                state.waiting_n,
                state.waiting_c,
                state.clock_n,
                state.clock_c,
                state.level,
            )
            successors, defeated = _add_clock_card(state, False, continuation)
            self.assertFalse(defeated)
            self.assertEqual(len(successors), 1)
            state = successors[0]
        self.assertEqual((state.level, state.clock_n + state.clock_c), (2, 2))
        self.assertEqual(state.waiting_n + state.waiting_c, 6)
        self.assertEqual(state.pending_normals, 0)

    def test_one_hit_can_trigger_multiple_clock_upgrades(self) -> None:
        state = State(0, PLACE_HIT, 8, 8, 0, 0, (), 0, 0, 6, 0, 1)
        for remaining in range(7, -1, -1):
            continuation = State(
                0,
                PLACE_HIT,
                8,
                remaining,
                0,
                0,
                (),
                state.waiting_n,
                state.waiting_c,
                state.clock_n,
                state.clock_c,
                state.level,
            )
            successors, defeated = _add_clock_card(state, False, continuation)
            self.assertFalse(defeated)
            self.assertEqual(len(successors), 1)
            state = successors[0]
        self.assertEqual(state.level, 3)
        self.assertEqual(state.clock_n + state.clock_c, 0)
        self.assertEqual(state.waiting_n + state.waiting_c, 12)

    def test_hit_at_level_three_causes_immediate_defeat(self) -> None:
        result = calculate(request(deck_count=1, level=3, clock=6, damage=(1, 4)))
        self.assertEqual(result.level_defeat, 1)
        self.assertEqual(result.refresh_defeat, 0)
        self.assertEqual(result.survival, 0)

    def test_empty_deck_and_waiting_room_is_refresh_defeat(self) -> None:
        result = calculate(request(deck_count=0, damage=(1,)))
        self.assertEqual(result.refresh_defeat, 1)
        self.assertEqual(result.defeat, 1)

    def test_climax_only_deck_cancels_and_allows_next_damage(self) -> None:
        result = calculate(
            request(deck_count=2, deck_climax=1, waiting_count=0, damage=(1, 1))
        )
        self.assertEqual(result.defeat + result.survival, 1)
        # The first reveal may be a climax (cancel) or normal (hit); both are
        # valid paths and exact probability must be conserved.
        self.assertGreaterEqual(result.survival, 0)

    def test_refresh_climax_does_not_cancel_damage(self) -> None:
        result = calculate(
            request(
                deck_count=0,
                waiting_count=2,
                waiting_climax=1,
                damage=(2,),
            )
        )
        self.assertEqual(result.defeat + result.survival, 1)
        # If the climax refresh point incorrectly canceled damage, both
        # refresh outcomes would survive. Correctly, C as refresh point leads
        # to an empty-room defeat after the remaining normal is revealed.
        self.assertEqual(result.refresh_defeat, Fraction(1, 2))
        self.assertEqual(result.survival, Fraction(1, 2))

    def test_exact_cancel_probability_matches_hypergeometric_baseline(self) -> None:
        # With level 3 and clock 6, a hit immediately levels out; a climax
        # cancels damage. For N=2 ordinary and C=1 climax, P(hit)=1/3.
        result = calculate(
            request(deck_count=3, deck_climax=1, level=3, clock=6, damage=(2,))
        )
        self.assertEqual(result.level_defeat, Fraction(1, 3))
        self.assertEqual(result.refresh_defeat, 0)
        self.assertEqual(result.survival, Fraction(2, 3))

    def test_probabilities_are_exact_and_sum_to_one(self) -> None:
        result = calculate(
            request(
                deck_count=8,
                deck_climax=2,
                waiting_count=3,
                waiting_climax=1,
                level=2,
                clock=5,
                clock_climax=1,
                damage=(2, 2, 3),
            )
        )
        self.assertIsInstance(result.defeat, Fraction)
        self.assertEqual(
            result.level_defeat + result.refresh_defeat + result.survival, 1
        )

    def test_initially_defeated_level_is_one_hundred_percent(self) -> None:
        result = calculate(request(deck_count=0, level=4, damage=(1,)))
        self.assertEqual(result.level_defeat, 1)

    def test_rejects_inconsistent_counts_and_bad_damage(self) -> None:
        with self.assertRaises(InputError):
            request(deck_count=2, deck_climax=3)
        with self.assertRaises(InputError):
            request(deck_count=0, clock=7)
        with self.assertRaises(InputError):
            request(deck_count=1, damage=(0,))
        with self.assertRaises(InputError):
            request(deck_count=1, damage=())

    def test_small_deck_fixed_orders_match_independent_enumeration(self) -> None:
        cards = ("N", "N", "C")
        damage = (1, 1)
        orders = set(permutations(cards))
        surviving_orders = sum(simulate_fixed_order(order, damage) for order in orders)
        expected_survival = Fraction(surviving_orders, len(orders))
        result = calculate(request(deck_count=3, deck_climax=1, damage=damage))
        self.assertEqual(result.survival, expected_survival)

    def test_exhaustive_small_decks_match_all_fixed_orders(self) -> None:
        damage_sequences = ((1,), (2,), (1, 1), (1, 2), (2, 1))
        for normal_count in range(0, 6):
            for climax_count in range(0, 3):
                deck_count = normal_count + climax_count
                if deck_count == 0:
                    continue
                cards = ("N",) * normal_count + ("C",) * climax_count
                orders = set(permutations(cards))
                for damage in damage_sequences:
                    # This independent oracle intentionally covers only
                    # no-refresh paths; refresh behavior has dedicated tests.
                    if sum(damage) > deck_count:
                        continue
                    with self.subTest(
                        normals=normal_count, climaxes=climax_count, damage=damage
                    ):
                        expected = Fraction(
                            sum(
                                simulate_fixed_order(order, damage) for order in orders
                            ),
                            len(orders),
                        )
                        result = calculate(
                            request(
                                deck_count=deck_count,
                                deck_climax=climax_count,
                                damage=damage,
                            )
                        )
                        self.assertEqual(result.survival, expected)

    def test_mocha_can_remove_observed_climax_to_make_damage_hit(self) -> None:
        request_with_mocha = CalculationInput.from_values(
            deck_count=2,
            deck_climax=1,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(Mocha(2), Damage(1)),
        )
        result = calculate(request_with_mocha)
        self.assertEqual(result.level_defeat, 1)
        self.assertEqual(result.refresh_defeat, 0)
        self.assertEqual(result.survival, 0)

    def test_mocha_is_a_decision_after_random_observation(self) -> None:
        # If the first card is a climax, discard it and leave the normal on
        # top; if first is normal, keep it. Either observed branch guarantees
        # the following 1-damage action hits and causes level-up defeat.
        request_with_mocha = CalculationInput.from_values(
            deck_count=2,
            deck_climax=1,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(Mocha(2), Damage(1)),
        )
        self.assertEqual(calculate(request_with_mocha).defeat, 1)

    def test_mocha_does_not_refresh_an_empty_deck(self) -> None:
        request_with_mocha = CalculationInput.from_values(
            deck_count=0,
            deck_climax=0,
            waiting_count=1,
            waiting_climax=0,
            level=0,
            clock=0,
            clock_climax=0,
            operation_sequence=(Mocha(2),),
        )
        result = calculate(request_with_mocha)
        self.assertEqual(result.defeat, 0)
        self.assertEqual(result.survival, 1)

    def test_mocha_known_top_order_controls_next_damage(self) -> None:
        # There is one climax and one normal. If both are retained, the
        # attacker can place the climax first; level 3 then loses immediately
        # only if the damage is not canceled, so keeping the normal on top is
        # the maximizing choice and guarantees defeat.
        request_with_mocha = CalculationInput.from_values(
            deck_count=2,
            deck_climax=1,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(Mocha(2), Damage(1)),
        )
        self.assertEqual(calculate(request_with_mocha).level_defeat, 1)

    def test_structured_and_text_operations_are_equivalent(self) -> None:
        structured = CalculationInput.from_values(
            deck_count=7,
            deck_climax=2,
            waiting_count=2,
            waiting_climax=1,
            level=1,
            clock=4,
            clock_climax=0,
            operation_sequence=(Mocha(2), Damage(2), Mocha(1), Damage(3)),
        )
        from ws_tcg.web import _parse_operations

        parsed_operations = _parse_operations("摩卡2-2-摩卡1-3")
        parsed = CalculationInput.from_values(
            deck_count=7,
            deck_climax=2,
            waiting_count=2,
            waiting_climax=1,
            level=1,
            clock=4,
            clock_climax=0,
            operation_sequence=parsed_operations,
        )
        self.assertEqual(calculate(structured), calculate(parsed))

    def test_mocha_small_deck_matches_ordered_deck_enumeration(self) -> None:
        # With two cards (N,C), Mocha 2 may remove up to two and reorder all
        # retained cards. The attacker always keeps/orders a normal on top so
        # the following 1 damage is uncanceled against level 3 + clock 6.
        request_with_mocha = CalculationInput.from_values(
            deck_count=2,
            deck_climax=1,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(Mocha(2), Damage(1)),
        )
        physical_orders = set(permutations((0, 1)))
        expected_defeat = Fraction(0)
        for order in physical_orders:
            # The perfect-information decision can discard the climax or
            # retain it below the normal. Every order admits a guaranteed hit.
            observed = tuple(order)
            choices: list[bool] = []
            for discard_count in range(3):
                for indices in combinations(range(2), discard_count):
                    kept = [card for i, card in enumerate(observed) if i not in indices]
                    choices.append(not kept or kept[0] == 0)
            expected_defeat += Fraction(int(any(choices)), len(physical_orders))
        self.assertEqual(expected_defeat, 1)
        self.assertEqual(calculate(request_with_mocha).level_defeat, expected_defeat)

    def test_mixed_operation_sequence_conserves_exact_probability(self) -> None:
        request_with_mocha = CalculationInput.from_values(
            deck_count=12,
            deck_climax=3,
            waiting_count=5,
            waiting_climax=1,
            level=2,
            clock=4,
            clock_climax=1,
            operation_sequence=(
                Mocha(2),
                Damage(3),
                Mocha(3),
                Damage(2),
                Mocha(2),
                Damage(3),
            ),
        )
        result = calculate(request_with_mocha)
        self.assertEqual(
            result.level_defeat + result.refresh_defeat + result.survival, 1
        )

    def test_mocha_look_limit_is_validated(self) -> None:
        with self.assertRaises(InputError):
            CalculationInput.from_values(
                deck_count=1,
                deck_climax=0,
                waiting_count=0,
                waiting_climax=0,
                level=0,
                clock=0,
                clock_climax=0,
                operation_sequence=(Mocha(11),),
            )

    def test_bottom_conditional_only_damages_if_milled_climax_exists(self) -> None:
        no_climax = CalculationInput.from_values(
            deck_count=2,
            deck_climax=0,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(BottomConditional(2, 4),),
        )
        has_climax = CalculationInput.from_values(
            deck_count=2,
            deck_climax=1,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(BottomConditional(2, 4),),
        )
        self.assertEqual(calculate(no_climax).defeat, 0)
        # Both cards are milled; if a climax is among them, 4 damage is dealt.
        self.assertEqual(calculate(has_climax).level_defeat, 1)

    def test_bottom_per_climax_deals_one_damage_per_climax(self) -> None:
        request_with_bottom = CalculationInput.from_values(
            deck_count=3,
            deck_climax=2,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(BottomPerClimax(3, 1),),
        )
        result = calculate(request_with_bottom)
        # All three bottom cards include two climaxes; at least one 1-damage
        # hit guarantees level-up from level 3 + clock 6.
        self.assertEqual(result.level_defeat, 1)

    def test_bottom_mill_refresh_penalty_and_resume(self) -> None:
        request_with_bottom = CalculationInput.from_values(
            deck_count=2,
            deck_climax=0,
            waiting_count=2,
            waiting_climax=0,
            level=0,
            clock=0,
            clock_climax=0,
            operation_sequence=(BottomConditional(4, 4),),
        )
        result = calculate(request_with_bottom)
        self.assertEqual(
            result.level_defeat + result.refresh_defeat + result.survival, 1
        )
        # The refresh point is the single refresh damage and the remaining
        # requested cards can still be milled; no extra penalty check occurs.
        self.assertEqual(result.refresh_defeat, 0)
        self.assertEqual(result.level_defeat, 0)
        self.assertEqual(result.survival, 1)

    def test_bottom_refresh_point_is_not_followed_by_duplicate_penalty(self) -> None:
        request_with_bottom = CalculationInput.from_values(
            deck_count=1,
            deck_climax=0,
            waiting_count=1,
            waiting_climax=0,
            level=3,
            clock=5,
            clock_climax=0,
            operation_sequence=(BottomConditional(2, 1),),
        )
        result = calculate(request_with_bottom)
        # The single refresh point moves clock 5 -> 6. A duplicated extra
        # damage would hit with the remaining normal and cause level 4.
        self.assertEqual(result.level_defeat, 0)
        self.assertEqual(result.refresh_defeat, 0)
        self.assertEqual(result.survival, 1)

    def test_bottom_refresh_point_level_up_can_end_game_immediately(self) -> None:
        request_with_bottom = CalculationInput.from_values(
            deck_count=1,
            deck_climax=0,
            waiting_count=1,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(BottomConditional(2, 1),),
        )
        result = calculate(request_with_bottom)
        self.assertEqual(result.level_defeat, 1)
        self.assertEqual(result.refresh_defeat, 0)
        self.assertEqual(result.survival, 0)

    def test_bottom_conditional_counts_climaxes_across_refresh(self) -> None:
        # Two normals are milled before refresh; the waiting room then
        # contributes a climax among the next two bottom-milled cards.
        request_with_bottom = CalculationInput.from_values(
            deck_count=2,
            deck_climax=0,
            waiting_count=2,
            waiting_climax=1,
            level=3,
            clock=5,
            clock_climax=0,
            operation_sequence=(BottomConditional(4, 1),),
        )
        # After the refresh point, the climax must be among the two milled
        # cards (1/2); the remaining card is then normal and the 1-damage hit
        # levels from level 3 + clock 6 to level 4.
        self.assertEqual(calculate(request_with_bottom).level_defeat, Fraction(1, 2))

    def test_user_bottom_four_example_counts_cards_across_refresh(self) -> None:
        # Start with two normals in deck and a waiting room of N,N,C.
        # Mill the two deck cards, shuffle five cards, use one as refresh
        # point, then mill two more. Only the two bottom-milled cards can
        # satisfy the condition after the initial two normals.
        request_with_bottom = CalculationInput.from_values(
            deck_count=2,
            deck_climax=0,
            waiting_count=3,
            waiting_climax=1,
            level=3,
            clock=5,
            clock_climax=0,
            operation_sequence=(BottomConditional(4, 1),),
        )
        result = calculate(request_with_bottom)
        # Across a uniform shuffle of N,N,N,N,C, the climax is among the
        # bottom two with probability 2/5. The next damage reveals a normal
        # first and therefore causes immediate level-4 defeat from level 3.
        self.assertEqual(result.level_defeat, Fraction(2, 5))
        self.assertEqual(result.refresh_defeat, 0)
        self.assertEqual(result.survival, Fraction(3, 5))

    def test_bottom_per_climax_can_resolve_five_hits(self) -> None:
        request_with_bottom = CalculationInput.from_values(
            deck_count=10,
            deck_climax=5,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=2,
            clock_climax=0,
            operation_sequence=(BottomPerClimax(5, 1),),
        )
        result = calculate(request_with_bottom)
        # With probability 1/C(10,5), all five climaxes are milled and the
        # remaining five normals land as five separate hits. The fifth hit
        # reaches level four, proving there is no separate four-hit cap.
        self.assertGreaterEqual(result.level_defeat, Fraction(1, 252))
        self.assertEqual(
            result.level_defeat + result.refresh_defeat + result.survival, 1
        )

    def test_canceled_per_climax_hit_does_not_cancel_later_hits(self) -> None:
        request_with_bottom = CalculationInput.from_values(
            deck_count=4,
            deck_climax=1,
            waiting_count=0,
            waiting_climax=0,
            level=3,
            clock=6,
            clock_climax=0,
            operation_sequence=(BottomPerClimax(4, 2),),
        )
        result = calculate(request_with_bottom)
        # The one climax cancels one of the two 2-damage checks. The other
        # check is all-normal and still causes an immediate level-4 defeat.
        self.assertEqual(result.level_defeat, 1)

    def test_text_and_structured_bottom_operations_match(self) -> None:
        from ws_tcg.web import _parse_operations

        structured = CalculationInput.from_values(
            deck_count=6,
            deck_climax=2,
            waiting_count=3,
            waiting_climax=1,
            level=1,
            clock=3,
            clock_climax=0,
            operation_sequence=(BottomConditional(4, 2), BottomPerClimax(3, 1)),
        )
        parsed = CalculationInput.from_values(
            deck_count=6,
            deck_climax=2,
            waiting_count=3,
            waiting_climax=1,
            level=1,
            clock=3,
            clock_climax=0,
            operation_sequence=_parse_operations(
                "\u638f\u5e95\u6761\u4ef64-2-\u638f\u5e95\u8ba1\u6b213-1"
            ),
        )
        self.assertEqual(calculate(structured), calculate(parsed))

    def test_bottom_mill_empty_deck_and_waiting_room_defeats(self) -> None:
        request_with_bottom = CalculationInput.from_values(
            deck_count=0,
            deck_climax=0,
            waiting_count=0,
            waiting_climax=0,
            level=0,
            clock=0,
            clock_climax=0,
            operation_sequence=(BottomConditional(2, 4),),
        )
        self.assertEqual(calculate(request_with_bottom).refresh_defeat, 1)

    def test_bottom_limits_are_validated(self) -> None:
        for operation in (
            BottomConditional(6, 1),
            BottomConditional(1, 5),
            BottomPerClimax(0, 1),
            BottomPerClimax(1, 51),
        ):
            with self.subTest(operation=operation), self.assertRaises(InputError):
                CalculationInput.from_values(
                    deck_count=1,
                    deck_climax=0,
                    waiting_count=0,
                    waiting_climax=0,
                    level=0,
                    clock=0,
                    clock_climax=0,
                    operation_sequence=(operation,),
                )


if __name__ == "__main__":
    unittest.main()
