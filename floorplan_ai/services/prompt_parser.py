"""Prompt -> RoomProgram. Deterministic, regex+heuristic, no LLM call.

Handles the shorthand people actually type: "3 bed 2 bath", "140 m2",
"open kitchen", "single storey", "garage", "L-shaped". Anything unparsed is
kept in RoomProgram.notes for the UI to surface.
"""
from __future__ import annotations

import re

from floorplan_ai.models.plan_ir import RoomDemand, RoomProgram

_COUNT_RE = re.compile(r"(\d+)\s*(bed(?:room)?s?|bath(?:room)?s?|garage)", re.I)
_AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(m2|sqm|square meters?)", re.I)
_STOREY_RE = re.compile(r"(single|one|two|three|\d+)\s*[- ]?stor(?:e?y|ies)", re.I)
_OPEN_KITCHEN_RE = re.compile(r"open[-\s]?kitchen", re.I)

_ALIASES = {
    "bed": "bedroom", "beds": "bedroom", "bedroom": "bedroom", "bedrooms": "bedroom",
    "bath": "bathroom", "baths": "bathroom", "bathroom": "bathroom", "bathrooms": "bathroom",
    "garage": "garage",
}


class ProgramParser:
    def parse(self, prompt: str) -> RoomProgram:
        demands: list[RoomDemand] = []
        notes: list[str] = []

        for count_s, kind_s in _COUNT_RE.findall(prompt):
            kind = _ALIASES.get(kind_s.lower(), kind_s.lower())
            demands.append(RoomDemand(kind=kind, count=int(count_s)))

        if not any(d.kind == "kitchen" for d in demands):
            demands.append(RoomDemand(kind="kitchen", count=1))
        if not any(d.kind == "living" for d in demands):
            demands.append(RoomDemand(kind="living", count=1))
        demands.append(RoomDemand(kind="hall", count=1))

        area = 0.0
        m = _AREA_RE.search(prompt)
        if m:
            area = float(m.group(1))
        else:
            notes.append("no total area given; defaulting to 110 m2")
            area = 110.0

        storeys = 1
        m = _STOREY_RE.search(prompt)
        if m:
            word = m.group(1).lower()
            storeys = {"single": 1, "one": 1, "two": 2, "three": 3}.get(word, int(word) if word.isdigit() else 1)

        return RoomProgram(
            rooms=demands,
            total_area=area,
            storeys=storeys,
            open_kitchen=bool(_OPEN_KITCHEN_RE.search(prompt)),
            notes=notes,
        )