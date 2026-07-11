# Contributing

Install [uv](https://docs.astral.sh/uv/), clone the repository, and run:

```text
UV_CACHE_DIR=/tmp/oksg-uv-cache uv sync
UV_CACHE_DIR=/tmp/oksg-uv-cache uv run pre-commit install
UV_CACHE_DIR=/tmp/oksg-uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/oksg-uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/oksg-uv-cache uv run python -m unittest discover -v
UV_CACHE_DIR=/tmp/oksg-uv-cache uv run python -m compileall -q src tests
git diff --check
```

Ruff is the project formatter and linter. Run `uv run ruff format .` to format changes and
`uv run ruff check --fix .` for safe automatic lint fixes. Git pre-commit hooks run both checks;
CI repeats them as the authoritative gate.

Public modules and classes require concise docstrings. Public methods require docstrings when
their purpose is not already captured by the class contract. Functions that implement safety,
transaction, side-effect, or failure behavior should document that contract rather than restating
their signature. Private and self-explanatory helpers do not need docstrings.

Tests must create all configuration, shared folders, backups, media, and other state in temporary directories. They must never read or modify a contributor's `.config.toml`, creator assets, real karaoke tree, or shared folder.

Keep command orchestration in `src/oksg_buddy/commands/`. Command modules may depend on package utilities; package utilities must not depend on command modules, and command modules must not import one another. Route CLI behavior through `src/oksg_buddy/cli.py` and preserve the `oksg_buddy.cli:main` console entry point.

Changes must preserve explicit configuration before writes, strict ZIP validation, exclusive checksum-verified backups outside the shared folder, MP4 staging and verification before ZIP rewrite, hard-link no-replace publication, dry runs, atomic transaction order, and failure cleanup. Never add a destructive no-backup bypass.

Pull requests should be focused, explain user-visible and safety effects, include regression coverage, and pass the full validation above. Keep the uv cache outside the repository. Do not commit local configuration, creator assets, generated media, repair backups, caches, or handoff material.
