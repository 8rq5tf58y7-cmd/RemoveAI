from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tqdm import tqdm

from .providers import ProviderChoice, choose_onnx_providers
from .worker import WorkItem, WorkResult, WorkerConfig, init_worker, process_one


@dataclass(frozen=True)
class RunConfig:
    input_dir: Path
    output_dir: Path
    recursive: bool
    extensions: tuple[str, ...]
    engine: str
    model: str
    provider: str
    workers: int
    mask_max_size: int
    alpha_matting: bool
    am_fg_thresh: int
    am_bg_thresh: int
    am_erode_size: int
    post_process_mask: bool
    compression: str
    overwrite: bool
    skip_existing: bool


@dataclass(frozen=True)
class RunStats:
    total: int
    processed: int
    skipped: int
    failed: int
    seconds: float
    provider_choice: ProviderChoice


def iter_input_files(input_dir: Path, *, recursive: bool, extensions: tuple[str, ...]) -> Iterable[Path]:
    input_dir = Path(input_dir)
    exts = {e.lower() for e in extensions}
    if recursive:
        it = input_dir.rglob("*")
    else:
        it = input_dir.glob("*")
    for p in it:
        if not p.is_file():
            continue
        if p.suffix.lower() in exts:
            yield p


def default_workers() -> int:
    cpu = os.cpu_count() or 4
    # ONNX inference is CPU-heavy; start conservative.
    return max(1, cpu // 2)


def _normalize_exts(exts: Iterable[str]) -> tuple[str, ...]:
    out = []
    for e in exts:
        e = e.strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        out.append(e)
    return tuple(dict.fromkeys(out))  # stable unique


def run_batch(config: RunConfig) -> RunStats:
    input_dir = Path(config.input_dir)
    output_dir = Path(config.output_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Avoid over-threading when we parallelize at the process level.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

    provider_choice = choose_onnx_providers(config.provider)
    worker_cfg = WorkerConfig(
        engine=str(config.engine),
        model=config.model,
        providers=tuple(provider_choice.providers),
        mask_max_size=int(config.mask_max_size),
        alpha_matting=bool(config.alpha_matting),
        am_fg_thresh=int(config.am_fg_thresh),
        am_bg_thresh=int(config.am_bg_thresh),
        am_erode_size=int(config.am_erode_size),
        post_process_mask=bool(config.post_process_mask),
        compression=str(config.compression),
    )

    extensions = _normalize_exts(config.extensions)
    files = list(iter_input_files(input_dir, recursive=config.recursive, extensions=extensions))
    total = len(files)

    # Used by GUI to render a progress bar without parsing tqdm.
    emit_progress = os.environ.get("REMOVEBG_BATCH_PROGRESS", "").strip().lower() in {"1", "true", "yes"}
    if emit_progress:
        print(f"__TOTAL__ {total}", flush=True)

    # Build work items with preserved relative paths.
    items: list[WorkItem] = []
    for src in files:
        rel = src.relative_to(input_dir)
        dst = output_dir / rel
        # Ensure TIFF output, even if input isn't.
        dst = dst.with_suffix(".tif")
        if config.skip_existing and dst.exists() and not config.overwrite:
            items.append(WorkItem(str(src), str(dst), overwrite=False))
        else:
            items.append(WorkItem(str(src), str(dst), overwrite=config.overwrite))

    start = time.perf_counter()
    processed = 0
    skipped = 0
    failed = 0
    done = 0

    show_progress = os.environ.get("REMOVEBG_BATCH_NO_PROGRESS", "").strip().lower() not in {"1", "true", "yes"}

    # Windows requires spawn-safe entrypoints; ProcessPoolExecutor handles this when called under __main__.
    from concurrent.futures import ProcessPoolExecutor, as_completed

    workers = int(config.workers) if config.workers and config.workers > 0 else default_workers()

    # Pre-download the ONNX model once (prevents process-pool crashes if workers race-download,
    # and produces a clearer error if disk is full).
    eng = (worker_cfg.engine or "onnx").strip().lower()
    if eng == "onnx":
        try:
            from .u2net import MODEL_SPECS, ensure_model_file

            name = (worker_cfg.model or "u2netp").strip().lower()
            spec = MODEL_SPECS.get(name)
            if spec is None:
                raise ValueError(f"Unknown model '{worker_cfg.model}'. Supported: {', '.join(sorted(MODEL_SPECS))}")
            ensure_model_file(spec)
        except OSError as e:
            if getattr(e, "errno", None) == 28:
                model_dir = os.environ.get("REMOVEBG_BATCH_MODEL_DIR", "").strip() or "(default cache)"
                raise OSError(
                    28,
                    "No space left on device while downloading the model. "
                    "Free disk space or set REMOVEBG_BATCH_MODEL_DIR to a folder on a drive with space "
                    f"(currently: {model_dir}).",
                ) from e
            raise

    # If only 1 worker, run inline (useful for debugging).
    if workers == 1:
        init_worker(worker_cfg)
        iterator = tqdm(items, total=len(items), unit="img") if show_progress else items
        for item in iterator:
            res = process_one(item, worker_cfg)
            if res.skipped:
                skipped += 1
            elif res.ok:
                processed += 1
            else:
                failed += 1
            done += 1
            if emit_progress:
                print(f"__PROGRESS__ {done} {total} {processed} {skipped} {failed}", flush=True)
        return RunStats(
            total=total,
            processed=processed,
            skipped=skipped,
            failed=failed,
            seconds=time.perf_counter() - start,
            provider_choice=provider_choice,
        )

    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=init_worker,
        initargs=(worker_cfg,),
    ) as ex:
        futs = [ex.submit(process_one, item, worker_cfg) for item in items]
        iterator = tqdm(as_completed(futs), total=len(futs), unit="img") if show_progress else as_completed(futs)
        for fut in iterator:
            res: WorkResult = fut.result()
            if res.skipped:
                skipped += 1
            elif res.ok:
                processed += 1
            else:
                failed += 1
                # Keep error output compact (but visible).
                print(f"[error] {res.src} -> {res.dst}: {res.error}", file=sys.stderr)
            done += 1
            if emit_progress:
                print(f"__PROGRESS__ {done} {total} {processed} {skipped} {failed}", flush=True)

    return RunStats(
        total=total,
        processed=processed,
        skipped=skipped,
        failed=failed,
        seconds=time.perf_counter() - start,
        provider_choice=provider_choice,
    )

