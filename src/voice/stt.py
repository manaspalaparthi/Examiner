from __future__ import annotations

import asyncio
import logging
import platform
import tempfile
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


class ParakeetSTT:
    """Wraps NVIDIA Parakeet TDT.

    On Apple Silicon, uses `parakeet-mlx` for native MLX inference.
    Elsewhere falls back to NeMo's Parakeet checkpoint on CPU/GPU.
    Inference is serialized through an asyncio.Lock — Parakeet is not
    thread-safe and concurrent transcribe calls would interleave state.
    """

    SAMPLE_RATE = 16_000

    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or self._default_model_id()
        self._impl = None
        self._kind: str | None = None
        self._lock = asyncio.Lock()
        self._loaded = asyncio.Event()

    @staticmethod
    def _default_model_id() -> str:
        if _is_apple_silicon():
            return "mlx-community/parakeet-tdt-0.6b-v2"
        return "nvidia/parakeet-tdt-0.6b-v2"

    @property
    def loaded(self) -> bool:
        return self._loaded.is_set()

    async def load(self) -> None:
        if self._loaded.is_set():
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_sync)
        self._loaded.set()

    def _load_sync(self) -> None:
        if _is_apple_silicon():
            from parakeet_mlx import from_pretrained  # type: ignore[import-not-found]

            log.info("stt: loading parakeet-mlx %s", self._model_id)
            self._impl = from_pretrained(self._model_id)
            self._kind = "mlx"
        else:
            from nemo.collections.asr.models import (  # type: ignore[import-not-found]
                EncDecRNNTBPEModel,
            )

            log.info("stt: loading NeMo %s", self._model_id)
            model = EncDecRNNTBPEModel.from_pretrained(self._model_id)
            model.eval()
            self._impl = model
            self._kind = "nemo"

    async def transcribe(self, audio_f32: np.ndarray) -> str:
        if not self._loaded.is_set():
            await self.load()
        if audio_f32.size == 0:
            return ""
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._transcribe_sync, audio_f32)

    def _transcribe_sync(self, audio_f32: np.ndarray) -> str:
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = Path(f.name)
        try:
            sf.write(tmp, audio_f32.astype(np.float32), self.SAMPLE_RATE, subtype="FLOAT")
            if self._kind == "mlx":
                result = self._impl.transcribe(str(tmp))  # type: ignore[union-attr]
                text = getattr(result, "text", None) or str(result)
            else:
                hyps = self._impl.transcribe([str(tmp)], batch_size=1)  # type: ignore[union-attr]
                if isinstance(hyps, tuple):
                    hyps = hyps[0]
                text = hyps[0] if hyps else ""
                if not isinstance(text, str):
                    text = getattr(text, "text", str(text))
            return text.strip()
        finally:
            tmp.unlink(missing_ok=True)


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"
