# Clean code formulas

Short rules for code you write or touch in a card. They keep the project small and easy to extend. Apply them to the files of this card only; never start a repo-wide cleanup without a card of its own.

## The formulas

| Rule | Limit |
|---|---|
| One function does one thing | about 30 lines |
| One file has one reason to change | about 300 lines; split by responsibility, not by size alone |
| Parameters | 3 or fewer; more → pass one object |
| Nesting | 3 levels or fewer; use early `return` |
| Repetition | the third copy becomes a shared function; two copies stay (do not guess early) |
| Names | say what, not how (`overdueInvoices`, not `list2`); no abbreviations the glossary does not know |
| Comments | only the *why*; delete comments that repeat the code |
| Dead code | delete it (git remembers); never comment code out |
| New dependency | only if it replaces more than ~50 lines you would write and keep; mention it in `spec.md` `## Decisions` |
| Extension | add a new file or a new entry in a list, not a new `if` inside a long function |

## Safety floor (shorter must never mean weaker)

Cleaning removes repetition and dead code. It never removes any of these, even if the code gets longer:

- **Tests.** If the card changes behaviour, add or keep at least one automated test using the project's own tools. Only if the project has no test tool, say so in `- Verified:` and do a documented manual run.
- **Checks on outside input** (arguments, files, forms) with a clear message. Never drop extra input silently: reject it or say what was ignored.
- **Safe failure.** A broken data file gives a plain message, not a stack trace, and is never overwritten. Writes to user data are atomic (write a temp file, then rename).
- **Right numbers.** Money in whole cents (no float sums). Dates in the user's local time, not UTC.

Common traps to look for in your own diff: silently truncated input, UTC dates, float money, a write that can leave half a file, a raw crash on bad data.

## Order of work (every card)

1. Make it work (R-rules pass).
2. Read your own diff once. Apply the formulas above to what you changed.
3. Remove what is now unused: imports, variables, files, docs that describe the removed behaviour.
4. Match the surrounding style (naming, comment density, error handling). Do not reformat code you did not change.
5. Re-run the checks and the tests. Cleaning must not change behaviour, and must keep the safety floor above.
6. Tick the card's `Cleanup done` step and write `- Cleaned: <what you simplified, or "nothing needed">` in Progress notes.

## Boundaries

- A cleanup that touches files outside the card's `scope.allowed` is a new card (SKILL.md "Scope").
- If a formula forces a large rewrite, do not do it silently: write `- Out of scope: <refactor> → new card` and tell the user.
- Prefer deleting over adding. The best change is the one with fewer lines for the same behaviour.
