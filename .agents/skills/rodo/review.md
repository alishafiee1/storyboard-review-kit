# Review checklists

Use before closing a MAJOR card (recommended) or whenever the user asks for a review. A review reads the diff; it never replaces tests. Report findings in plain words, most serious first, and fix them (FIX → VERIFY).

## 1. Simplify (always)

- Anything duplicated, over-built, or unused in the diff?
- Could a simpler existing function or library call replace new code?
- Follow `clean.md`, including its safety floor: a shorter diff that dropped tests, input checks or safe failure is a defect.

## 2. Correctness

- Does each R-rule of `spec.md` have code and, if tests are used, a test?
- Edge cases: empty input, missing value, very large input, two things happening at once.
- Errors: are they handled or reported, never swallowed?

## 3. Security (quick pass)

- No secrets in code, config, logs, cards or commit messages.
- Input from outside (forms, URLs, files, env) is checked before use; no string-built SQL, shell commands or HTML.
- Access: every new route or action checks who is calling.
- New dependencies: known, maintained, and necessary.

## 4. Plain words

- Does the card's opening text (what the user gets) and `simple.md` still describe what the code now does? Run `rodo explain <card>` and read it as if you were not a developer.

## Optional external skills

`rodo init` offers Graphify (code map; fewer tokens) and project-map (one-page visual map) and installs them on a yes. If the project or the user's tools already provide them, you may use `simplify`, `code-review`, `security-review` or Graphify (code map). Never install them yourself; RODO works without them. Treat their output as advice and verify it before acting.
