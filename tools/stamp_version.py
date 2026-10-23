"""Écrit razerlite/_build.py pendant le build automatique : numéro de version et dépôt GitHub."""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
init = (ROOT / "razerlite" / "__init__.py").read_text(encoding="utf-8")
major, minor = re.search(r'__version__ = "(\d+)\.(\d+)', init).groups()
version = f"{major}.{minor}.{os.environ['GITHUB_RUN_NUMBER']}"
repo = os.environ["GITHUB_REPOSITORY"]
(ROOT / "razerlite" / "_build.py").write_text(f'VERSION = "{version}"\nREPO = "{repo}"\n', encoding="utf-8")
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
    out.write(f"version={version}\n")
print(version, repo)
