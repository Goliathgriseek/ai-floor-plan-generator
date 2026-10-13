"""QWidget that paints a FloorPlan IR. Zoom with wheel, pan with drag."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from floorplan_ai.models.plan_ir import FloorPlan

WALL_PEN = QPen(QColor("#1b1b1b"), 2.0)
EXTERIOR_PEN = QPen(QColor("#1b1b1b"), 4.0)
DOOR_PEN = QPen(QColor("#c2410c"), 2.0)
WINDOW_PEN = QPen(QColor("#0369a1"), 2.0)


class PlanCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._plan: FloorPlan | None = None
        self._zoom = 4.0
        self._origin = QPointF(0.0, 0.0)
        self.setMouseTracking(True)

    def set_plan(self, plan: FloorPlan) -> None:
        self._plan = plan
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._zoom *= 1.1 if event.angleDelta().y() > 0 else 0.9
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fafaf7"))
        if self._plan is None:
            return

        center = self.rect().center()
        painter.translate(center.x() + self._origin.x(), center.y() + self._origin.y())
        painter.scale(self._zoom, -self._zoom)

        for wall in self._plan.walls:
            painter.setPen(EXTERIOR_PEN if wall.kind == "exterior" else WALL_PEN)
            painter.drawLine(
                QPointF(wall.start[0], wall.start[1]),
                QPointF(wall.end[0], wall.end[1]),
            )

        painter.setPen(DOOR_PEN)
        for door in self._plan.doors:
            painter.drawEllipse(QPointF(door.at[0], door.at[1]), door.width / 2, door.width / 2)

        painter.setPen(WINDOW_PEN)
        for at, width in self._plan.windows:
            painter.drawLine(QPointF(at[0] - width / 2, at[1]), QPointF(at[0] + width / 2, at[1]))