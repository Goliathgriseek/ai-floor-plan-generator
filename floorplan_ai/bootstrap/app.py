"""Process entry point for the ai-floor-plan-generator desktop tool.

Owns the Qt application lifecycle and the headless CLI path. The GUI path
spins up MainWindow; the CLI path (`--headless`) renders a plan to disk
without opening a window, which is what CI and batch scripts use.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from floorplan_ai.config.settings import load_settings
from floorplan_ai.core.generator import FloorPlanGenerator
from floorplan_ai.utils.logging import configure_logging

logger = logging.getLogger("floorplan_ai.bootstrap")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="floorplan-gen",
        description="Generate dimensioned residential floor plans from a text prompt.",
    )
    parser.add_argument("--prompt", type=str, default=None, help="Design brief.")
    parser.add_argument("--out", type=Path, default=Path("out"), help="Output directory.")
    parser.add_argument("--seed", type=int, default=None, help="Deterministic sampling seed.")
    parser.add_argument("--headless", action="store_true", help="Skip the GUI, run CLI render.")
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    settings = load_settings()
    configure_logging(level=logging.DEBUG if args.verbose else settings.log_level)

    if args.headless:
        if not args.prompt:
            logger.error("--headless requires --prompt")
            return 2
        gen = FloorPlanGenerator(settings)
        plan = gen.generate(args.prompt, seed=args.seed)
        outputs = gen.export(plan, args.out)
        for path in outputs:
            logger.info("wrote %s", path)
        return 0

    # GUI path. Imported lazily so headless installs don't pull Qt.
    from PySide6.QtWidgets import QApplication
    from floorplan_ai.handlers.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow(settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())