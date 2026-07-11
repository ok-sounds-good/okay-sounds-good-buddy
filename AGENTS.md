# Repository Instructions

- Use uv for the environment and dependencies. If setting `UV_CACHE_DIR`, choose an OS-appropriate location outside the repository.
- Keep the package architecture intact: CLI parsing and dispatch live in `src/oksg_buddy/cli.py`; workflows live in isolated `src/oksg_buddy/commands/` modules; shared utilities must not import commands, and command modules must not import one another.
- Preserve safety invariants: require explicit valid configuration before writes; validate ZIPs strictly; create exclusive, checksum-verified backups outside the shared folder; stage and verify MP4 output before ZIP rewrites; publish with hard-link atomic no-replace behavior; retain dry runs, transaction ordering, and failure cleanup. Do not add destructive bypasses.
- Isolate tests in temporary directories. Tests must never read or mutate a contributor's configuration, assets, working media, shared folders, or backups.
- Track public source, tests, setup scripts, documentation, metadata, the example config, and only `assets/.gitkeep`. Keep local config, repair backups, handoffs, creator assets, generated media, build output, virtual environments, and caches ignored.
- Make focused changes with regression coverage. Validate with `uv sync`, `uv run python -m unittest discover -v`, `uv run python -m compileall -q src tests`, `uv run oksg --help`, `uv run python -m oksg_buddy --help`, `uv build`, and `git diff --check`.

## Working Approach

- State material assumptions and surface ambiguous requirements before changing code.
- Prefer the smallest implementation that fully satisfies the request; avoid speculative abstractions and unrelated improvements.
- Keep changes surgical. Match existing patterns, preserve unrelated code, and remove only artifacts made obsolete by the current change.
- Define success in verifiable terms before implementation. Add regression coverage where appropriate, then run the relevant focused and full validation.
- If a requirement conflicts with repository safety invariants or existing behavior, stop and report the conflict instead of silently choosing a direction.
