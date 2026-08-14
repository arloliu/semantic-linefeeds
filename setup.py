"""Wheel build hook: stage registry payloads into the build tree.

setuptools reads pyproject.toml for everything declarative;
this file exists only to run the shared staging step after build_py,
so the wheel embeds every semlf/payloads/<id> member without a packaging copy ever being committed to the repository.
"""
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "cli"))


class build_py_with_payloads(build_py):
    def run(self):
        super().run()
        from semlf import registry
        registry.stage_payloads(Path(self.build_lib), repo=REPO)


setup(cmdclass={"build_py": build_py_with_payloads})
