"""Writes a FloorPlan to DXF (ezdxf), SVG, PNG (Pillow), and JSON sidecar."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import ezdxf
from PIL import Image, ImageDraw

from floorplan_ai.config.settings import Settings
from floorplan_ai.models.plan_ir import FloorPlan

logger = logging.getLogger("floorplan_ai.services.exporter")

_SCALE = 40  # px per meter for the raster preview


class PlanExporter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def export_all(self, plan: FloorPlan, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written = [
            self._write_dxf(plan, out_dir / "plan.dxf"),
            self._write_svg(plan, out_dir / "plan.svg"),
            self._write_png(plan, out_dir / "plan.png"),
            self._write_json(plan, out_dir / "plan.fp.json"),
        ]
        return written

    def _write_dxf(self, plan: FloorPlan, path: Path) -> Path:
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        walls_layer = doc.layers.add("WALLS")
        for wall in plan.walls:
            msp.add_line(wall.start, wall.end, dxfattribs={"layer": walls_layer.dxf.name})
        doc.saveas(path)
        return path

    def _write_svg(self, plan: FloorPlan, path: Path) -> Path:
        xs = [p for w in plan.walls for p in (w.start[0], w.end[0])]
        ys = [p for w in plan.walls for p in (w.start[1], w.end[1])]
        minx, maxx = min(xs) - 1, max(xs) +