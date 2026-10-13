"""Layout synthesis: runs the diffusion model, decodes rectangles.

The ONNX session is NOT thread-safe; wrap calls in the session lock or
instantiate one synthesizer per worker thread. Batch size is fixed at 1 for
the desktop build because the model peaks at ~800MB RSS per inference.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

from floorplan_ai.models.plan_ir import Layout, RoomProgram, RoomRect
from floorplan_ai.models.registry import LoadedModel

logger = logging.getLogger("floorplan_ai.core.synthesizer")


class LayoutSynthesizer:
    def __init__(self, model: LoadedModel) -> None:
        self._model = model
        self._lock = threading.Lock()

    def synthesize(self, program: RoomProgram, seed: int | None = None) -> Layout:
        rng = np.random.default_rng(seed)
        # Program vector: [n_rooms, total_area, aspect, has_garage, storeys]
        cond = program.to_condition_vector()
        init = rng.standard_normal((1, self._model.latent_dim), dtype=np.float32)

        with self._lock:
            raw = self._model.session.run(
                ["rects"],
                {"condition": cond[None, :], "latent": init},
            )[0]

        rects = self._decode_rects(raw[0], program)
        logger.debug("decoded %d rects from latent", len(rects))
        return Layout(rects=rects, program=program)

    def _decode_rects(self, raw: np.ndarray, program: RoomProgram) -> list[RoomRect]:
        # raw is (N, 5): [cx, cy, w, h, label_logit]. Label assigned greedily
        # against the program's demand counts so we never emit more bedrooms
        # than requested.
        rects: list[RoomRect] = []
        remaining = program.demand_counts()
        for row in raw:
            cx, cy, w, h, label = (float(v) for v in row[:5])
            kind = self._assign_label(label, remaining)
            if kind is None:
                continue
            rects.append(RoomRect(cx=cx, cy=cy, width=w, height=h, kind=kind))
            remaining[kind] -= 1
        return rects

    @staticmethod
    def _assign_label(logit: float, remaining: dict[str, int]) -> str | None:
        order = ["living", "kitchen", "bedroom", "bathroom", "hall", "garage"]
        idx = int(round(logit)) % len(order)
        for offset in range(len(order)):
            kind = order[(idx + offset) % len(order)]
            if remaining.get(kind, 0) > 0:
                return kind
        return None