from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ProviderChoice:
    requested: str
    providers: list[str]
    available: list[str]


def choose_onnx_providers(requested: str) -> ProviderChoice:
    """
    Pick ONNX Runtime execution providers.

    requested:
      - "auto": prefer GPU accel if available
      - "cpu" | "cuda" | "coreml"
      - or a raw provider name (e.g. "CUDAExecutionProvider")
    """

    try:
        import onnxruntime as ort  # type: ignore

        available = list(ort.get_available_providers())
    except Exception:
        # If ORT can't be imported, we still return a CPU provider list and let the caller fail later.
        available = []

    req = (requested or "auto").strip()
    req_l = req.lower()

    def _best_auto(avail: Sequence[str]) -> list[str]:
        # Order matters.
        preferred = [
            "CUDAExecutionProvider",
            "CoreMLExecutionProvider",
            "DmlExecutionProvider",  # DirectML (some Windows builds)
            "CPUExecutionProvider",
        ]
        chosen = [p for p in preferred if p in avail]
        return chosen if chosen else ["CPUExecutionProvider"]

    if req_l == "auto":
        providers = _best_auto(available)
    elif req_l == "cpu":
        providers = ["CPUExecutionProvider"]
    elif req_l == "cuda":
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    elif req_l == "coreml":
        providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    else:
        # Allow passing a raw ORT provider name.
        providers = [req]
        if req != "CPUExecutionProvider":
            providers.append("CPUExecutionProvider")

    return ProviderChoice(requested=req, providers=providers, available=available)

