# Repository guidance for coding agents

This file defines repository-specific working rules for AI/code agents. Follow it together with the user's request and any more specific instructions in files you edit.

## Project snapshot

- Product: early-stage, unofficial local Weiß Schwarz probability calculator.
- Runtime: Python 3.10+ standard library only; no dependency installation is needed for source execution or end users of the EXE.
- Windows packaging: Python 3.11 build venv, pinned tools in `requirements-build.txt`, PyInstaller spec `s_tcg.spec`, script `build_windows.ps1`.
- UI: one native HTML/CSS/JavaScript page in `frontend/index.html`.
- HTTP/API: `ws_tcg/web.py`; calculation model and validation: `ws_tcg/model.py`; exact engine: `ws_tcg/engine.py`.
- Local source of working rules: `docs/ws_rule.md`. Model decisions and known assumptions: `docs/WS斩杀概率计算器开发计划.md` and README.
- Tests: `python -m unittest discover -s tests -v`.

## Before changing code

1. Read the relevant implementation, tests, and rule/model docs before editing.
2. Establish whether the requested change affects official text, a working-rule summary, a model assumption, or only UI/engineering behavior. Keep these categories separate.
3. Do not use the internet unless the user explicitly requests it. Never silently turn an unverified interpretation into an official ruling.
4. Keep unrelated user changes intact. Do not stage, commit, push, or alter Git configuration unless explicitly requested.

## Architecture and correctness constraints

- Keep `ws_tcg/engine.py` deterministic and independent of HTTP/UI. Use exact `Fraction` arithmetic for random branches.
- Preserve probability mass: `level_defeat + refresh_defeat + survival == 1` for every valid complete calculation.
- Distinguish chance nodes from decision nodes. Current defaults: randomness is exact; defense-side level-up choice maximizes survival; Mocha-side choices maximize opponent defeat.
- Damage cards are revealed first. Only after the damage is confirmed as a hit are its ordinary cards placed into clock one at a time; check the 7-card clock threshold after each placement. A climax cancels the damage and sends revealed cards to the waiting room.
- Refresh handling follows the local rule summary plus the explicitly documented model assumption. Do not change its timing without updating tests and assumptions returned to users.
- Mocha (`摩卡x`) reveals up to `x` existing deck cards without refreshing. After observing them, the attacker may move 0..x revealed cards to the waiting room and choose the order of the retained known deck-top cards. The current supported `x` range is 1..10.
- Bottom-mill actions are `掏底条件x-y` and `掏底计次x-z`. x is 1..5; conditional y is 1..4; per-climax z is 1..50. Per-climax damage resolves once for each climax actually milled, so the number of hits is bounded by x (maximum five), with no separate four-hit cap.
- Bottom-milled cards enter the waiting room as they are sent. If the deck empties mid-action, refresh the current waiting room (including already milled cards), put the refresh point into clock and check level-up; that refresh point is the one rule-required refresh damage, so do not resolve a duplicate extra damage check. Then resume the remaining bottom-mill count. A card washed back and milled again contributes again as a separate card event.
- State must keep known top cards separate from the unordered random deck pool. Do not double-count cards after Mocha, cancellation, refresh, or level-up.
- Preserve backward compatibility for legacy pure damage text/JSON where practical. Current mixed text examples: `2-2-3-4`, `摩卡2-3-摩卡3`.
- Validate inputs at the model boundary. User input errors should become readable HTTP 400 `INVALID_INPUT` responses, not tracebacks.

## Change workflow

1. Make a focused change and add/update tests in the same change.
2. For probability logic, add deterministic boundary cases and, where practical, a small-deck exhaustive oracle independent from the engine implementation.
3. Run:

   ```bash
   python -m unittest discover -s tests -v
   python -m compileall -q ws_tcg tests run.py
   ```

4. If UI/API behavior changed, add or update HTTP/API tests and verify the page endpoint.
5. If model semantics, supported inputs, or public API changed, update README, `CONTRIBUTING.md`, relevant design docs, version constants, and `/api/ws/rules` as appropriate.
6. For packaging changes, run the Windows build script and smoke-test the produced executable, not only the source entry point.
7. Report exactly which tests/checks ran and disclose any unverified rule assumptions.

## Coding style

- Prefer standard-library solutions; do not add dependencies without a demonstrated need and user/maintainer approval.
- Use immutable dataclasses for inputs and engine states where practical.
- Keep user-facing validation and explanatory text in Chinese; code identifiers and comments may use concise English.
- Avoid broad refactors, generated artifacts, and unrelated formatting changes.
- Add a comment when subtle state/probability semantics would otherwise be easy to break.

## Open-source hygiene

- The repository currently has no license file. Do not claim a particular license or add one without maintainer authorization.
- Do not add third-party WS card images, rules, or card databases without checking provenance and licensing requirements.
- Avoid committing secrets, local caches, generated bytecode, personal data, and machine-specific paths.
- This project is unofficial; do not imply endorsement by Bushiroad or other rights holders.
