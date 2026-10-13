"""Main Qt window for the ai-floor-plan-generator desktop tool.

Layout: prompt pane (left), plan canvas (center), room inspector (right).
Generation runs on a QThread so the UI never blocks during the ~1.5s
inference pass on a mid-range CPU.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from floorplan_ai.config.settings import Settings
from floorplan_ai.core.generator import FloorPlanGenerator
from floorplan_ai.handlers.plan_canvas import PlanCanvas
from floorplan_ai.models.plan_ir import FloorPlan

logger = logging.getLogger("floorplan_ai.handlers.main_window")


class _GenerateWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, generator: FloorPlanGenerator, prompt: str, seed: int | None) -> None:
        super().__init__()
        self._generator = generator
        self._prompt = prompt
        self._seed = seed

    def run(self) -> None:
        try:
            plan = self._generator.generate(self._prompt, seed=self._seed)
        except Exception as exc:  # surfaced to the status bar, never swallowed
            logger.exception("generation failed")
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(plan)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._generator = FloorPlanGenerator(settings)
        self._worker: _GenerateWorker | None = None

        self.setWindowTitle("AI Floor Plan Generator")
        self.resize(1280, 820)

        prompt_row = QHBoxLayout()
        self._prompt_input = QLineEdit()
        self._prompt_input.setPlaceholderText(
            "3 bed 2 bath, open kitchen, 140 m2, single storey, garage"
        )
        self._generate_btn = QPushButton("Generate")
        self._generate_btn.clicked.connect(self._on_generate)
        prompt_row.addWidget(self._prompt_input, stretch=1)
        prompt_row.addWidget(self._generate_btn)

        prompt_pane = QWidget()
        prompt_layout = QVBoxLayout(prompt_pane)
        prompt_layout.addWidget(QLabel("Design brief"))
        prompt_layout.addLayout(prompt_row)
        prompt_layout.addStretch(1)

        self._canvas = PlanCanvas()
        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.addWidget(QLabel("Rooms"))
        inspector_layout.addStretch(1)

        splitter = QSplitter()
        splitter.addWidget(prompt_pane)
        splitter.addWidget(self._canvas)
        splitter.addWidget(inspector)
        splitter.setSizes([320, 680, 280])
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("Ready.")

    def _on_generate(self) -> None:
        prompt = self._prompt_input.text().strip()
        if not prompt:
            self.statusBar().showMessage("Enter a design brief first.")
            return
        self._generate_btn.setEnabled(False)
        self.statusBar().showMessage("Generating…")
        self._worker = _GenerateWorker(self._generator, prompt, seed=None)
        self._worker.finished_ok.connect(self._on_plan)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_plan(self, plan: FloorPlan) -> None:
        self._canvas.set_plan(plan)
        self._generate_btn.setEnabled(True)
        self.statusBar().showMessage(
            f"{len(plan.rooms)} rooms · {len(plan.walls)} walls · {len(plan.doors)} doors"
        )

    def _on_failed(self, message: str) -> None:
        self._generate_btn.setEnabled(True)
        self.statusBar().showMessage(f"Failed: {message}")