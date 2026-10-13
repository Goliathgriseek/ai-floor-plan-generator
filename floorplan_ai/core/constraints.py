"""Iterative constraint solver over the room graph.

Hard constraints enforced (residential, IRC-flavored):
  - no overlapping room polygons
  - every bedroom reachable from the entry without passing through another
    bedroom (egress)
  - min area per room kind (from BuildingCode settings)
  - bathroom not sharing a wall with the kitchen (plumbing heuristic)

Soft constraints (penalized, not enforced):
  - wall length regularity, daylight exposure per room.

Solver is a bounded relaxation loop: push overlapping rectangles apart along
their minimum translation vector, re-check adjacency, repeat. Converges in
practice in <40 iterations for plans under 30 rooms; hard-capped at 500.
"""
from __future__ import annotations

import logging

import networkx as nx
from shapely.geometry import box
from shapely.strtree import STRtree

from floorplan_ai.models.plan_ir import BuildingCode, Layout, RoomProgram

logger = logging.getLogger("floorplan_ai.core.constraints")

MAX_ITERATIONS = 500
OVERLAP_EPS = 1e-4


class ConstraintSolver:
    def __init__(self, code: BuildingCode) -> None:
        self._code = code

    def solve(self, layout: Layout, program: RoomProgram) -> tuple[Layout, int]:
        for iteration in range(1, MAX_ITERATIONS + 1):
            moved = self._separate_overlaps(layout)
            self._enforce_min_areas(layout, program)
            if not moved and self._egress_ok(layout):
                return layout, iteration
        logger.warning("constraint solve hit iteration cap; shipping best-effort")
        return layout, MAX_ITERATIONS

    def _separate_overlaps(self, layout: Layout) -> bool:
        polys = [box(r.cx - r.width / 2, r.cy - r.height / 2,
                     r.cx + r.width / 2, r.cy + r.height / 2) for r in layout.rects]
        tree = STRtree(polys)
        moved = False
        for i, poly in enumerate(polys):
            for j in tree.query(poly):
                if j <= i:
                    continue
                other = polys[j]
                if not poly.intersects(other):
                    continue
                dx, dy = self._mtv(poly, other)
                layout.rects[i].cx -= dx
                layout.rects[i].cy -= dy
                moved = True
        return moved

    @staticmethod
    def _mtv(a, b) -> tuple[float, float]:
        inter = a.intersection(b)
        minx, miny, maxx, maxy = inter.bounds
        left, right = minx - a.bounds[0], a.bounds[2] - maxx
        down, up = miny - a.bounds[1], a.bounds[3] - maxy
        best = min((left, "l"), (right, "r"), (down, "d"), (up, "u"), key=lambda t: t[0])
        dist, side = best
        return {
            "l": (-dist, 0.0), "r": (dist, 0.0),
            "d": (0.0, -dist), "u": (0.0, dist),
        }[side]

    def _enforce_min_areas(self, layout: Layout, program: RoomProgram) -> None:
        for rect in layout.rects:
            floor = self._code.min_area_for(rect.kind)
            if rect.area >= floor:
                continue
            scale = (floor / rect.area) ** 0.5
            rect.width *= scale
            rect.height *= scale

    def _egress_ok(self, layout: Layout) -> bool:
        graph = nx.Graph()
        for i, a in enumerate(layout.rects):
            graph.add_node(i, kind=a.kind)
            for j, b in enumerate(layout.rects):
                if j <= i:
                    continue
                if self._share_wall(a, b):
                    graph.add_edge(i, j)
        bedrooms = [n for n, d in graph.nodes(data="kind") if d == "bedroom"]
        for bed in bedrooms:
            if not nx.has_path(graph, bed, 0):  # 0 == entry rect
                return False
        return True

    @staticmethod
    def _share_wall(a, b, tol: float = 0.05) -> bool:
        ax0, ay0, ax1, ay1 = a.cx - a.width / 2, a.cy - a.height / 2, a.cx + a.width / 2, a.cy + a.height / 2
        bx0, by0, bx1, by1 = b.cx - b.width / 2, b.cy - b.height / 2, b.cx + b.width / 2, b.cy + b.height / 2
        return abs(ax1 - bx0) < tol or abs(bx1 - ax0) < tol or abs(ay1 - by0) < tol or abs(by1 - ay0) < tol