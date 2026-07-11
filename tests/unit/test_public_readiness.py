from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class PublicReadinessTests(unittest.TestCase):
    def test_project_metadata_and_console_script(self):
        metadata = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        project = metadata["project"]
        self.assertEqual(project["version"], "0.1.0")
        self.assertEqual(project["readme"], "README.md")
        self.assertEqual(project["license"], "MIT")
        self.assertEqual(project["requires-python"], ">=3.14")
        self.assertEqual(project["scripts"]["oksg"], "oksg_buddy.cli:main")
        for name in ("README.md", "LICENSE"):
            self.assertTrue((REPO / name).is_file())

    def test_readme_uses_package_native_clean_setup_commands(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        for command in (
            "./setup.sh",
            "./setup.ps1",
            "uv sync",
            "uv run oksg",
            "uv run python -m oksg_buddy",
            "oksg configure",
            "oksg doctor",
        ):
            self.assertIn(command, readme)
        self.assertNotIn("cd tools", readme)
        self.assertNotIn("oksg.py", readme)
        self.assertNotIn("setup.py", readme)

    def test_ci_has_platform_matrix_and_required_commands(self):
        workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for value in (
            "ubuntu-latest",
            "macos-latest",
            "windows-latest",
            "actions/checkout@v7",
            "astral-sh/setup-uv@v8",
            "ruff format --check .",
            "ruff check .",
            "python -m unittest discover -v",
            "python -m compileall -q src tests",
            "oksg --help",
            "python -m oksg_buddy --help",
        ):
            self.assertIn(value, workflow)

    def test_pre_commit_runs_the_project_formatter_and_linter(self):
        hooks = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        self.assertIn("uv run ruff check --fix", hooks)
        self.assertIn("uv run ruff format", hooks)

    def test_tracked_document_relative_links_resolve(self):
        documents = [REPO / "README.md", REPO / "CONTRIBUTING.md", *(REPO / "docs").glob("*.md")]
        markdown_link = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
        for document in documents:
            for target in markdown_link.findall(document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith(("#", "mailto:")):
                    continue
                path = target.split("#", 1)[0]
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / path).resolve().exists())

    def test_private_and_generated_paths_are_ignored(self):
        ignore = (REPO / ".gitignore").read_text(encoding="utf-8")
        for pattern in (
            ".config.toml",
            ".repair-backups/",
            "docs/handoffs/",
            ".venv/",
            ".uv-cache/",
            "__pycache__/",
            "assets/*",
            "!assets/.gitkeep",
            "*.zip",
            "*.mp4",
            "Thumbnail.png",
            "OKSG_STATUS.md",
            "YOUTUBE.md",
        ):
            self.assertIn(pattern, ignore)


if __name__ == "__main__":
    unittest.main()
