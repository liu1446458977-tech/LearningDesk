"""Entry point for LearningDesk (python main.py or frozen exe)."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from app import run_app

    run_app()


if __name__ == "__main__":
    main()
