"""Turns a solved Layout into a FloorPlan IR: walls, openings, labels.

Walls are derived from the union of room rectangles. Interior walls are
segments shared between two rooms; exterior walls are the boundary of the
union. Door openings are punched at the midpoint of each shared segment
that the constraint solver marked as connected.
"""
from __future__ import annotations

from shapely.geometry import box
from shapely.ops import unary_union

from floorplan_ai.models.plan_ir import (
    Door,
    FloorPlan,
    Layout,
    RoomProgram,
    WallSegment,
)


class PlanBuilder:
    def build(self, layout: Layout, program: RoomProgram) -> FloorPlan:
        polys = [box(r.cx - r.width / 2, r.cy - r.height / 2,
                     r.cx + r.width / 2, r.cy + r.height / 2) for r in layout.rects]
        shell = unary_union(polys)

        walls: list[WallSegment] = []
        doors: list[Door] = []

        for i, poly in enumerate(polys):
            for j in range(i + 1, len(polys)):
                shared = poly.boundary.intersection(polys[j].boundary)
                if shared.is_empty or shared.length < 0.4:
                    continue
                seg = self._to_segment(shared)
                walls.append(WallSegment(start=seg[0], end=seg[1], kind="interior"))
                mid = ((seg[0][0] + seg[1][0]) / 2, (seg[0][1] + seg[1][1]) / 2)
                doors.append(Door(at=mid, width=0.9, from_room=i, to_room=j))

        for ring in self._exterior_rings(shell):
            for k in range(len(ring) - 1):
                walls.append(WallSegment(start=ring[k], end=ring[k + 1], kind="exterior"))

        return FloorPlan(
            walls=walls,
            doors=doors,
            windows=self._place_windows(shell, layout),
            rooms=[(r.kind, (r.cx, r.cy, r.width, r.height)) for r in layout.rects],
            program=program,
        )

    @staticmethod
    def _to_segment(geom) -> tuple[tuple[float, float], tuple[float, float]]:
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
        (x0, y0), (x1, y1) = geom.coords[0], geom.coords[-1]
        return (x0, y0), (x1, y1)

    @staticmethod
    def _exterior_rings(shell) -> list[list[tuple[float, float]]]:
        rings = []
        geoms = shell.geoms if shell.geom_type == "MultiPolygon" else [shell]
        for poly in geoms:
            rings.append(list(poly.exterior.coords))
        return rings

    @staticmethod
    def _place_windows(shell, layout: Layout) -> list[tuple[tuple[float, float], float]]:
        # One window per 12 m^2 of exterior wall, placed on the longest run.
        windows = []
        total_ext = shell.length
        count = max(1, int(total_ext / 12))
        step = total_ext / count
        for k in range(count):
            pt = shell.exterior.interpolate(step * (k + 0.5))
            windows.append(((pt.x, pt.y), 1.2))
        return windows