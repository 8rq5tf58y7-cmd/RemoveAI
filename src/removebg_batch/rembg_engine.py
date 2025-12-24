from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class RembgSession:
    model_name: str
    session: Any


def create_rembg_session(model_name: str, providers: list[str]) -> RembgSession:
    """
    Create a rembg session (optional dependency).
    """
    try:
        from rembg import new_session  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "rembg is not installed. Install the optional extra: pip install 'removebg-batch[rembg]'"
        ) from e

    sess = new_session(model_name=(model_name or "u2netp"), providers=providers)
    return RembgSession(model_name=(model_name or "u2netp"), session=sess)


def predict_mask_u8_with_rembg(
    sess: RembgSession,
    rgb_u8: np.ndarray,
    *,
    out_size: tuple[int, int],
    mask_max_size: int = 1024,
    alpha_matting: bool = False,
    am_fg_thresh: int = 240,
    am_bg_thresh: int = 10,
    am_erode_size: int = 10,
    post_process_mask: bool = False,
) -> np.ndarray:
    """
    Predict an 8-bit mask using rembg (optional).
    """
    try:
        from rembg import remove  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "rembg is not installed. Install the optional extra: pip install 'removebg-batch[rembg]'"
        ) from e

    pil = Image.fromarray(rgb_u8, mode="RGB")
    if mask_max_size and mask_max_size > 0:
        w, h = pil.size
        scale = min(mask_max_size / max(w, h), 1.0)
        if scale < 1.0:
            new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
            pil = pil.resize(new_size, resample=Image.Resampling.LANCZOS)

    mask_img = remove(
        pil,
        session=sess.session,
        only_mask=True,
        alpha_matting=alpha_matting,
        alpha_matting_foreground_threshold=am_fg_thresh,
        alpha_matting_background_threshold=am_bg_thresh,
        alpha_matting_erode_size=am_erode_size,
        post_process_mask=post_process_mask,
    )

    if not isinstance(mask_img, Image.Image):
        mask_img = Image.open(mask_img)  # type: ignore[arg-type]

    mask_img = mask_img.convert("L")
    if mask_img.size != out_size:
        mask_img = mask_img.resize(out_size, resample=Image.Resampling.LANCZOS)
    return np.asarray(mask_img, dtype=np.uint8)

