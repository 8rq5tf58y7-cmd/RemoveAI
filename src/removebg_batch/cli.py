from __future__ import annotations

import argparse
import os
from pathlib import Path

from .pipeline import RunConfig, default_workers, run_batch


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="removebg-batch",
        description="Local batch background removal with TIFF-compatible output (RGBA TIFF).",
    )
    p.add_argument("--input", required=True, help="Input folder containing images.")
    p.add_argument("--output", required=True, help="Output folder for cutouts (TIFF).")

    p.add_argument(
        "--extensions",
        default=".tif,.tiff,.jpg,.jpeg,.png,.webp,.bmp",
        help="Comma-separated list of input extensions to include.",
    )
    p.add_argument("--no-recursive", action="store_true", help="Do not scan input folder recursively.")

    p.add_argument(
        "--engine",
        default="onnx",
        help='Mask engine: "onnx" (default, easy install) or "rembg" (optional extra with more features).',
    )
    p.add_argument(
        "--model",
        default="u2netp",
        help="Model name (fast: u2netp; higher quality: u2net).",
    )
    p.add_argument(
        "--provider",
        default="auto",
        help='ONNX provider: "auto" (default), "cpu", "cuda", "coreml", or a raw provider name.',
    )

    p.add_argument(
        "--workers",
        type=int,
        default=0,
        help=f"Parallel workers (default: {default_workers()}). Use 1 to disable multiprocessing.",
    )
    p.add_argument(
        "--mask-max-size",
        type=int,
        default=1024,
        help="Max dimension for mask inference (smaller = faster). 0 disables downscaling.",
    )

    p.add_argument("--alpha-matting", action="store_true", help="Enable alpha matting (slower, cleaner edges).")
    p.add_argument("--am-fg-thresh", type=int, default=240, help="Alpha matting foreground threshold.")
    p.add_argument("--am-bg-thresh", type=int, default=10, help="Alpha matting background threshold.")
    p.add_argument("--am-erode-size", type=int, default=10, help="Alpha matting erode size.")
    p.add_argument(
        "--post-process-mask",
        action="store_true",
        help="Enable small post-processing on the mask (can help edge speckles).",
    )

    p.add_argument(
        "--compression",
        default="deflate",
        help='TIFF compression: "deflate" (default), "lzw", "zstd", or "none".',
    )

    p.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files whose output already exists (faster re-runs).",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    exts = tuple(e.strip() for e in str(args.extensions).split(",") if e.strip())

    cfg = RunConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        recursive=not args.no_recursive,
        extensions=exts,
        engine=str(args.engine),
        model=str(args.model),
        provider=str(args.provider),
        workers=int(args.workers),
        mask_max_size=int(args.mask_max_size),
        alpha_matting=bool(args.alpha_matting),
        am_fg_thresh=int(args.am_fg_thresh),
        am_bg_thresh=int(args.am_bg_thresh),
        am_erode_size=int(args.am_erode_size),
        post_process_mask=bool(args.post_process_mask),
        compression=str(args.compression),
        overwrite=bool(args.overwrite),
        skip_existing=bool(args.skip_existing),
    )

    stats = run_batch(cfg)
    prov = stats.provider_choice

    print("")
    print("Done.")
    print(f"Files found:     {stats.total}")
    print(f"Processed:       {stats.processed}")
    print(f"Skipped:         {stats.skipped}")
    print(f"Failed:          {stats.failed}")
    print(f"Seconds:         {stats.seconds:.2f}")
    print(f"Provider req:    {prov.requested}")
    if prov.available:
        print(f"Provider avail:  {', '.join(prov.available)}")
    print(f"Provider used:   {', '.join(prov.providers)}")


if __name__ == "__main__":
    # Required for Windows multiprocessing when running as a script/module.
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    main()

