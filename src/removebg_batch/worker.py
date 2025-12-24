from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from .rembg_engine import RembgSession, create_rembg_session, predict_mask_u8_with_rembg
from .u2net import U2NetSession, create_u2net_session, predict_mask_u8
from .tiff_io import alpha_from_mask, load_image, save_rgba_tiff


_SESSION = None
_SESSION_MODEL: Optional[str] = None
_SESSION_PROVIDERS: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class WorkerConfig:
    engine: str  # "onnx" | "rembg"
    model: str
    providers: tuple[str, ...]
    mask_max_size: int
    alpha_matting: bool
    am_fg_thresh: int
    am_bg_thresh: int
    am_erode_size: int
    post_process_mask: bool
    compression: str


@dataclass(frozen=True)
class WorkItem:
    src: str
    dst: str
    overwrite: bool


@dataclass(frozen=True)
class WorkResult:
    src: str
    dst: str
    ok: bool
    skipped: bool
    seconds: float
    error: Optional[str]


def _to_u8_rgb(arr: np.ndarray) -> np.ndarray:
    """
    Convert arbitrary numeric RGB array (HxWx3) to uint8 RGB for the segmentation model.
    """
    arr = np.asarray(arr)
    if arr.dtype == np.uint8:
        return arr
    if np.issubdtype(arr.dtype, np.integer):
        maxv = float(np.iinfo(arr.dtype).max)
        return np.clip(np.round(arr.astype(np.float32) * (255.0 / maxv)), 0, 255).astype(np.uint8)
    if np.issubdtype(arr.dtype, np.floating):
        return np.clip(np.round(arr.astype(np.float32) * 255.0), 0, 255).astype(np.uint8)
    raise TypeError(f"Unsupported dtype for conversion to uint8: {arr.dtype}")


def init_worker(config: WorkerConfig) -> None:
    """
    ProcessPool initializer: load the ONNX model session once per worker.
    """
    global _SESSION, _SESSION_MODEL, _SESSION_PROVIDERS

    # Reduce CPU oversubscription when using multiple processes.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

    eng = (config.engine or "onnx").strip().lower()
    if eng == "onnx":
        _SESSION = create_u2net_session(model_name=config.model, providers=list(config.providers))
    elif eng == "rembg":
        _SESSION = create_rembg_session(model_name=config.model, providers=list(config.providers))
    else:
        raise ValueError(f"Unknown engine: {config.engine}")
    _SESSION_MODEL = config.model
    _SESSION_PROVIDERS = config.providers


def process_one(item: WorkItem, config: WorkerConfig) -> WorkResult:
    start = time.perf_counter()
    src = Path(item.src)
    dst = Path(item.dst)
    try:
        if dst.exists() and not item.overwrite:
            return WorkResult(item.src, item.dst, ok=True, skipped=True, seconds=0.0, error=None)

        loaded = load_image(src)
        rgb = loaded.rgb

        # Build model input (uint8 PIL RGB), optionally downscaled for speed.
        u8_rgb = _to_u8_rgb(rgb)
        if _SESSION is None:
            raise RuntimeError("Model session not initialized in worker.")

        ow = int(rgb.shape[1])
        oh = int(rgb.shape[0])
        eng = (config.engine or "onnx").strip().lower()
        if eng == "onnx":
            if not isinstance(_SESSION, U2NetSession):
                raise RuntimeError("ONNX session not initialized in worker.")
            mask_u8 = predict_mask_u8(
                _SESSION,
                u8_rgb,
                out_size=(ow, oh),
                mask_max_size=int(config.mask_max_size),
            )
        elif eng == "rembg":
            if not isinstance(_SESSION, RembgSession):
                raise RuntimeError("rembg session not initialized in worker.")
            mask_u8 = predict_mask_u8_with_rembg(
                _SESSION,
                u8_rgb,
                out_size=(ow, oh),
                mask_max_size=int(config.mask_max_size),
                alpha_matting=bool(config.alpha_matting),
                am_fg_thresh=int(config.am_fg_thresh),
                am_bg_thresh=int(config.am_bg_thresh),
                am_erode_size=int(config.am_erode_size),
                post_process_mask=bool(config.post_process_mask),
            )
        else:
            raise ValueError(f"Unknown engine: {config.engine}")
        alpha = alpha_from_mask(mask_u8, loaded.dtype)

        # If source already has alpha, combine them (preserve existing transparency).
        if loaded.alpha is not None:
            a0 = loaded.alpha
            if np.issubdtype(loaded.dtype, np.floating):
                alpha = (alpha.astype(np.float32) * a0.astype(np.float32)).astype(loaded.dtype)
            else:
                maxv = float(np.iinfo(loaded.dtype).max)
                alpha = np.round((alpha.astype(np.float32) * a0.astype(np.float32)) / maxv).astype(loaded.dtype)

        # Ensure destination has .tif extension for TIFF-compatible output.
        if dst.suffix.lower() not in {".tif", ".tiff"}:
            dst = dst.with_suffix(".tif")

        save_rgba_tiff(
            dst,
            rgb=rgb,
            alpha=alpha,
            icc_profile=loaded.icc_profile,
            resolution=loaded.resolution,
            resolution_unit=loaded.resolution_unit,
            compression=config.compression,
        )

        return WorkResult(item.src, str(dst), ok=True, skipped=False, seconds=time.perf_counter() - start, error=None)
    except Exception as e:
        return WorkResult(item.src, item.dst, ok=False, skipped=False, seconds=time.perf_counter() - start, error=str(e))

