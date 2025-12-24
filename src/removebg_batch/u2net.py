from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as ort
import requests
from PIL import Image
from platformdirs import user_cache_dir


@dataclass(frozen=True)
class ModelSpec:
    name: str
    url: str
    sha256: Optional[str]
    input_size: int  # U2Net family commonly uses 320


# Small + fast (good default)
U2NETP = ModelSpec(
    name="u2netp",
    url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
    sha256=None,
    input_size=320,
)

# Larger (higher quality, slower)
U2NET = ModelSpec(
    name="u2net",
    url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
    sha256=None,
    input_size=320,
)

MODEL_SPECS: dict[str, ModelSpec] = {
    "u2netp": U2NETP,
    "u2net": U2NET,
}


def _models_dir() -> Path:
    override = os.environ.get("REMOVEBG_BATCH_MODEL_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(user_cache_dir("removebg-batch", "removebg-batch")) / "models"


def _acquire_lock(lock_path: Path, *, timeout_s: float = 300.0) -> None:
    """
    Simple cross-process lock using an exclusive lock file.
    """
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            # Stale lock safeguard (e.g. crashed process). 1 hour.
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > 3600:
                    lock_path.unlink(missing_ok=True)
                    continue
            except Exception:
                pass
            if time.time() - start > timeout_s:
                raise TimeoutError(f"Timed out waiting for model download lock: {lock_path}")
            time.sleep(0.2)


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_model_file(model: ModelSpec) -> Path:
    d = _models_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{model.name}.onnx"
    if path.exists():
        if model.sha256:
            got = _sha256_file(path)
            if got.lower() != model.sha256.lower():
                path.unlink(missing_ok=True)
            else:
                return path
        else:
            return path

    # Download (guarded so multiple workers don't race-download the same file)
    lock = path.with_suffix(".onnx.lock")
    _acquire_lock(lock)
    try:
        # Another process may have finished while we waited.
        if path.exists():
            return path

        tmp = path.with_suffix(".onnx.part")
        with requests.get(model.url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        tmp.replace(path)
    finally:
        _release_lock(lock)

    if model.sha256:
        got = _sha256_file(path)
        if got.lower() != model.sha256.lower():
            path.unlink(missing_ok=True)
            raise RuntimeError(f"Model hash mismatch for {model.name}")

    return path


@dataclass(frozen=True)
class U2NetSession:
    model_name: str
    input_name: str
    session: ort.InferenceSession
    input_size: int


def create_u2net_session(model_name: str, providers: list[str]) -> U2NetSession:
    name = (model_name or "u2netp").strip().lower()
    spec = MODEL_SPECS.get(name)
    if spec is None:
        raise ValueError(f"Unknown model '{model_name}'. Supported: {', '.join(sorted(MODEL_SPECS))}")

    model_path = ensure_model_file(spec)
    sess = ort.InferenceSession(str(model_path), providers=providers)
    input_name = sess.get_inputs()[0].name
    return U2NetSession(model_name=spec.name, input_name=input_name, session=sess, input_size=spec.input_size)


def _u2net_preprocess(rgb_u8: np.ndarray, size: int) -> np.ndarray:
    """
    Convert HxWx3 uint8 RGB to 1x3xSxS float32 normalized tensor.
    Uses ImageNet mean/std which is commonly used for U2Net ONNX exports.
    """
    if rgb_u8.dtype != np.uint8:
        rgb_u8 = rgb_u8.astype(np.uint8, copy=False)

    im = Image.fromarray(rgb_u8, mode="RGB").resize((size, size), Image.Resampling.LANCZOS)
    arr = np.asarray(im).astype(np.float32) / 255.0  # HWC
    # mean/std
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    chw = np.transpose(arr, (2, 0, 1))  # CHW
    return chw[None, ...].astype(np.float32)


def _u2net_postprocess(outputs: list[np.ndarray]) -> np.ndarray:
    """
    Pick the primary output and normalize to 0..1.
    Many exports return multiple outputs; first output is usually fine.
    """
    pred = outputs[0]
    pred = np.asarray(pred)
    pred = np.squeeze(pred)
    # Normalize robustly
    mn = float(np.min(pred))
    mx = float(np.max(pred))
    if mx - mn < 1e-8:
        return np.zeros_like(pred, dtype=np.float32)
    out = (pred - mn) / (mx - mn)
    return out.astype(np.float32)


def _resize_mask(mask01: np.ndarray, out_size: tuple[int, int]) -> np.ndarray:
    """
    Resize mask (float32 0..1) to (W,H) using PIL for quality.
    """
    h, w = mask01.shape[:2]
    im = Image.fromarray(np.clip(np.round(mask01 * 255.0), 0, 255).astype(np.uint8), mode="L")
    im = im.resize(out_size, Image.Resampling.LANCZOS)
    return np.asarray(im, dtype=np.uint8)


def predict_mask_u8(
    sess: U2NetSession,
    rgb_u8: np.ndarray,
    *,
    out_size: tuple[int, int],
    mask_max_size: int = 1024,
) -> np.ndarray:
    """
    Predict an 8-bit alpha mask (0..255) for the given RGB image.

    For speed, we optionally downscale the *input image* before inference (keeping aspect ratio),
    then resize the predicted mask back to out_size.
    """
    rgb_u8 = np.asarray(rgb_u8)
    if rgb_u8.ndim != 3 or rgb_u8.shape[2] != 3:
        raise ValueError("rgb_u8 must be HxWx3")

    oh, ow = int(rgb_u8.shape[0]), int(rgb_u8.shape[1])
    target_w, target_h = int(out_size[0]), int(out_size[1])
    if (ow, oh) != (target_w, target_h):
        # caller should pass original size; but allow mismatch
        ow, oh = target_w, target_h

    # Optional speed downscale before we square-resize to model input
    if mask_max_size and mask_max_size > 0:
        scale = min(mask_max_size / max(rgb_u8.shape[0], rgb_u8.shape[1]), 1.0)
        if scale < 1.0:
            new_w = max(1, int(round(rgb_u8.shape[1] * scale)))
            new_h = max(1, int(round(rgb_u8.shape[0] * scale)))
            rgb_small = np.asarray(
                Image.fromarray(rgb_u8, mode="RGB").resize((new_w, new_h), Image.Resampling.LANCZOS),
                dtype=np.uint8,
            )
        else:
            rgb_small = rgb_u8
    else:
        rgb_small = rgb_u8

    inp = _u2net_preprocess(rgb_small, sess.input_size)
    out_names = [o.name for o in sess.session.get_outputs()]
    raw = sess.session.run(out_names, {sess.input_name: inp})
    mask01 = _u2net_postprocess(raw)
    # mask01 is SxS; resize to original requested output size
    return _resize_mask(mask01, (target_w, target_h))

