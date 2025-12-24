from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import tifffile
from PIL import Image


@dataclass(frozen=True)
class LoadedImage:
    """
    Represents the *original* pixels as loaded from disk.

    - rgb: HxWx3, dtype preserved where possible (uint8/uint16/float32)
    - alpha: optional HxW, dtype same as rgb (when source has alpha)
    """

    rgb: np.ndarray
    alpha: Optional[np.ndarray]
    dtype: np.dtype
    icc_profile: Optional[bytes]
    resolution: Optional[tuple[float, float]]  # (x, y) in pixels per unit
    resolution_unit: Optional[str]  # "inch" | "centimeter" | None


def _ensure_hwc(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return arr[:, :, None]
    return arr


def _split_rgb_alpha(arr: np.ndarray) -> tuple[np.ndarray, Optional[np.ndarray]]:
    arr = _ensure_hwc(arr)
    if arr.shape[2] == 4:
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3]
        return rgb, alpha
    if arr.shape[2] == 3:
        return arr, None
    if arr.shape[2] == 1:
        # grayscale -> replicate to RGB
        rgb = np.repeat(arr, 3, axis=2)
        return rgb, None
    # If it's something unusual (e.g. CMYK), fall back to PIL conversion path.
    raise ValueError(f"Unsupported channel count: {arr.shape[2]}")


def load_image(path: Path) -> LoadedImage:
    """
    Load an image from disk.

    TIFF: read with tifffile to preserve dtype/bit-depth when possible.
    Non-TIFF: read with PIL (typically uint8).
    """

    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in {".tif", ".tiff"}:
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            arr = page.asarray()
            arr = np.asarray(arr)

            # ICC profile (TIFF tag 34675), if present.
            icc: Optional[bytes] = None
            try:
                icc_tag = page.tags.get("ICCProfile")
                if icc_tag is not None:
                    icc = icc_tag.value
            except Exception:
                icc = None

            # Resolution (if present)
            resolution = None
            resolution_unit = None
            try:
                xres = page.tags.get("XResolution")
                yres = page.tags.get("YResolution")
                resunit = page.tags.get("ResolutionUnit")
                if xres is not None and yres is not None:
                    # tifffile exposes rationals as (num, den) tuples
                    def _to_float(v):
                        if isinstance(v, tuple) and len(v) == 2 and v[1] != 0:
                            return float(v[0]) / float(v[1])
                        return float(v)

                    resolution = (_to_float(xres.value), _to_float(yres.value))
                if resunit is not None:
                    unit = resunit.value
                    if unit == 2:
                        resolution_unit = "inch"
                    elif unit == 3:
                        resolution_unit = "centimeter"
            except Exception:
                pass

        rgb, alpha = _split_rgb_alpha(arr)
        return LoadedImage(
            rgb=rgb,
            alpha=alpha,
            dtype=rgb.dtype,
            icc_profile=icc,
            resolution=resolution,
            resolution_unit=resolution_unit,
        )

    # Non-TIFF: PIL
    with Image.open(path) as im:
        icc = im.info.get("icc_profile")
        # Convert to RGBA to reliably get alpha if present
        rgba = im.convert("RGBA")
        arr = np.asarray(rgba)
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3]
        return LoadedImage(
            rgb=rgb,
            alpha=alpha,
            dtype=rgb.dtype,
            icc_profile=icc,
            resolution=None,
            resolution_unit=None,
        )


def _dtype_max(dtype: np.dtype) -> float:
    dt = np.dtype(dtype)
    if np.issubdtype(dt, np.floating):
        return 1.0
    if np.issubdtype(dt, np.integer):
        return float(np.iinfo(dt).max)
    raise TypeError(f"Unsupported dtype: {dtype}")


def alpha_from_mask(mask_u8: np.ndarray, dtype: np.dtype) -> np.ndarray:
    """
    Convert an 8-bit mask (0..255) to the target dtype range.
    """
    if mask_u8.dtype != np.uint8:
        mask_u8 = mask_u8.astype(np.uint8, copy=False)
    maxv = _dtype_max(dtype)
    if np.issubdtype(np.dtype(dtype), np.floating):
        return (mask_u8.astype(np.float32) / 255.0).astype(dtype)
    # integer
    return np.round(mask_u8.astype(np.float32) * (maxv / 255.0)).astype(dtype)


def save_rgba_tiff(
    path: Path,
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    icc_profile: Optional[bytes] = None,
    resolution: Optional[tuple[float, float]] = None,
    resolution_unit: Optional[str] = None,
    compression: str = "deflate",
) -> None:
    """
    Save RGBA TIFF.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rgb = np.asarray(rgb)
    alpha = np.asarray(alpha)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"rgb must be HxWx3, got {rgb.shape}")
    if alpha.ndim != 2 or alpha.shape[0] != rgb.shape[0] or alpha.shape[1] != rgb.shape[1]:
        raise ValueError("alpha must be HxW matching rgb")

    rgba = np.concatenate([rgb, alpha[:, :, None]], axis=2)

    extratags = []
    if icc_profile:
        # TIFF ICC Profile tag (34675)
        extratags.append((34675, "B", len(icc_profile), icc_profile, False))

    tiff_kwargs = {}
    if resolution is not None:
        tiff_kwargs["resolution"] = resolution
    if resolution_unit in {"inch", "centimeter"}:
        tiff_kwargs["resolutionunit"] = resolution_unit

    comp = compression.lower()
    if comp in {"none", "no", "off"}:
        comp = None

    tifffile.imwrite(
        path,
        rgba,
        photometric="rgb",
        compression=comp,
        planarconfig="contig",
        extratags=extratags if extratags else None,
        **tiff_kwargs,
    )

