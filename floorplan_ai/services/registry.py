"""Model registry: resolves and lazily loads ONNX weights from disk.

Weights are not shipped in the repo (see .gitignore). On first run the
registry downloads from the configured mirror and verifies the SHA-256 in
models/manifest.yaml. Everything is cached under ~/.floorplan-gen/weights.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import onnxruntime as ort
import yaml

from floorplan_ai.models.registry import LoadedModel

logger = logging.getLogger("floorplan_ai.services.registry")


class ModelRegistry:
    def __init__(self, model_dir: Path) -> None:
        self._model_dir = model_dir
        self._cache: dict[str, LoadedModel] = {}
        self._manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        manifest_path = self._model_dir / "manifest.yaml"
        if not manifest_path.exists():
            logger.warning("no manifest at %s; model loads will fail", manifest_path)
            return {"models": {}}
        with manifest_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def load(self, name: str) -> LoadedModel:
        if name in self._cache:
            return self._cache[name]

        entry = self._manifest.get("models", {}).get(name)
        if entry is None:
            raise KeyError(f"model '{name}' not in manifest")

        path = self._resolve_path(name, entry)
        self._verify(path, entry["sha256"])
        session = ort.InferenceSession(
            str(path),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        model = LoadedModel(
            name=name,
            session=session,
            latent_dim=int(entry.get("latent_dim", 128)),
            version=str(entry.get("version", "unknown")),
        )
        self._cache[name] = model
        logger.info("loaded model %s v%s", name, model.version)
        return model

    def _resolve_path(self, name: str, entry: dict) -> Path:
        local = self._model_dir / f"{name}.onnx"
        if local.exists():
            return local
        cache = Path.home() / ".floorplan-gen" / "weights" / f"{name}.onnx"
        if cache.exists():
            return cache
        raise FileNotFoundError(
            f"weights for '{name}' missing; run `floorplan-gen --fetch-models`"
        )

    @staticmethod
    def _verify(path: Path, expected: str) -> None:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        actual = h.hexdigest()
        if actual != expected:
            raise ValueError(f"checksum mismatch for {path.name}: {actual} != {expected}")