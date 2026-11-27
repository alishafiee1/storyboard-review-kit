# Testing the output of a kit version (A/B test)

Use when someone asks "is the new kit version better than the old one?". Never answer from feeling: give the same job to fresh helpers, one per version, and compare what they wrote. One run proves nothing, so repeat it at least twice.

## 1. Fix the job (once, then never change it)

- One small scenario with a few hidden traps (a money value, a date, outside input, an error path). Write it as a plain request, 10 lines at most.
- Write the traps and the expected behaviour in a private score sheet. The helpers never see it.
- Keep the scenario text in `rodo/<project>/project/ab-scenario.md` so every later round uses the same words.

## 2. Prepare one empty repo per version

- Copy a clean starter repo once per version. Install that version in each copy: `npx rodo-spec@<version> init --method-only --yes-files`. Include one copy with no kit as the baseline.
- Name copies by version only (`v-2.4.0`, `v-2.5.1`, `none`). Do not tell the helper which version is newer.

## 3. Run fresh helpers

- One new helper per copy, same model, same scenario text, same time limit. It must not know about the test or the other copies.
- Tell each helper to work only inside its copy and to follow that copy's `AGENTS.md`.
- Save per run: lines of code, number of tests, time taken, tokens used (if the tool reports them).

## 4. Score the code yourself

Score each item 0 (missing), 1 (partly), 2 (right). Do not ask the helper to grade itself.

| Item | What to look at |
|---|---|
| Works | The scenario's main path runs; tests pass when you run them |
| Traps | Each hidden trap from the score sheet is handled |
| Safety floor | Tests exist; outside input is checked and never dropped silently; failure leaves data safe; money in whole cents; dates in local time (`clean.md`) |
| Small | No duplicated or unused code; files and functions near the limits in `clean.md` |
| Plain words | Card opening text and `simple.md` match what the code does (`rodo explain`) |
| Cost | Lines, tokens and time, compared with the other copies |

Add the points per copy. Report the table, then one sentence per copy on its biggest weakness.

## 5. Repeat and decide

- Run the whole round again with fresh helpers. If the winner changes between rounds, the result is noise: say so, do not publish a claim.
- Change the kit only for a weakness that showed up in both rounds, then test the changed version the same way.
- A version that gets shorter code by dropping tests or checks has lost, not won.

## 6. Record

Add a row to `rodo/<project>/MEMORY.md`: date, versions compared, the scenario file, scores, and the decision. Keep the helpers' repos only until the decision is written.

## Example result (rodo-spec, one scenario, two rounds)

- 2.5.0 gave the shortest code but skipped input checks and tests: lower safety score.
- 2.5.1 added the "safety floor" rule: in both rounds the traps were handled, at about 40% more code, 32% more tokens and twice the time.
- Meaning: the rule works, and its cost is real. Say both when you report.
