"""Top-level generation pipeline: prompt -> program -> layout -> validated plan.

Pipeline stages, in order:
  1. ProgramParser    prompt text -> RoomProgram (typed room demands)
  2. LayoutSynthesizer  RoomProgram -> raw Layout (rectangles + adjacency)
  3. ConstraintSolver   Layout -> code-compliant Layout (egress, min areas)
  4. PlanBuilder        Layout -> FloorPlan IR (walls, doors, windows)

Each stage is pure and side-effect free except for logging. The generator
holds no per-run mutable state, so instances are safe to share across threads
(though the ONNX session inside the synthesizer is not; see its docstring).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from floorplan_ai.config.settings import Settings
from floorplan_ai.core.constraints import ConstraintSolver
from floorplan_ai.core.plan_builder import PlanBuilder
from floorplan_ai.core.synthesizer import LayoutSynthesizer
from floorplan_ai.models.plan_ir import FloorPlan
from floorplan_ai.services.prompt_parser import ProgramParser
from floorplan_ai.services.registry import ModelRegistry

logger = logging.getLogger("floorplan_ai.core.generator")


@dataclass(slots=True)
class GenerationStats:
    rooms: int
    wall_segments: int
    solve_iterations: int


class FloorPlanGenerator:
    """Orchestrates the four-stage pipeline. One instance per app session."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        registry = ModelRegistry(settings.model_dir)
        self._parser = ProgramParser()
        self._synth = LayoutSynthesizer(registry.load("layout-diffusion"))
        self._solver = ConstraintSolver(settings.building_code)
        self._builder = PlanBuilder()

    def generate(self, prompt: str, seed: int | None = None) -> FloorPlan:
        program = self._parser.parse(prompt)
        logger.info("parsed program: %d rooms", len(program.rooms))

        layout = self._synth.synthesize(program, seed=seed)
        layout, iterations = self._solver.solve(layout, program)
        logger.info("constraints settled after %d iterations", iterations)

        plan = self._builder.build(layout, program)
        logger.info("plan: %d wall segments", len(plan.wall_segments))
        return plan

    def export(self, plan: FloorPlan, out_dir: Path) -> list[Path]:
        """Write DXF + SVG + PNG + JSON sidecar. Returns written paths."""
        from floorplan_ai.services.exporter import PlanExporter

        return PlanExporter(self._settings).export_all(plan, out_dir)