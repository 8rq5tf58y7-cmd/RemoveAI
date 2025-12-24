from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pipeline import RunConfig, default_workers, run_batch


@dataclass(frozen=True)
class UiState:
    input_dir: Path
    output_dir: Path
    model: str
    provider: str
    workers: int
    mask_max_size: int


def main() -> None:
    root = tk.Tk()
    root.title("RemoveBG Batch (local)")

    frm = ttk.Frame(root, padding=12)
    frm.grid(row=0, column=0, sticky="nsew")

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frm.columnconfigure(1, weight=1)

    input_var = tk.StringVar(value="")
    output_var = tk.StringVar(value="")
    model_var = tk.StringVar(value="u2netp")
    provider_var = tk.StringVar(value="auto")
    workers_var = tk.IntVar(value=default_workers())
    mask_var = tk.IntVar(value=1024)

    log = tk.Text(frm, height=10, width=80)
    log.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    frm.rowconfigure(7, weight=1)

    def _log(msg: str) -> None:
        log.insert("end", msg + "\n")
        log.see("end")

    def choose_input() -> None:
        d = filedialog.askdirectory(title="Select input folder")
        if d:
            input_var.set(d)

    def choose_output() -> None:
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            output_var.set(d)

    def run_clicked() -> None:
        in_dir = input_var.get().strip()
        out_dir = output_var.get().strip()
        if not in_dir or not out_dir:
            messagebox.showerror("Missing folders", "Please select both input and output folders.")
            return

        cfg = RunConfig(
            input_dir=Path(in_dir),
            output_dir=Path(out_dir),
            recursive=True,
            extensions=(".tif", ".tiff", ".jpg", ".jpeg", ".png", ".webp", ".bmp"),
            model=model_var.get().strip() or "u2netp",
            provider=provider_var.get().strip() or "auto",
            workers=int(workers_var.get()),
            mask_max_size=int(mask_var.get()),
            alpha_matting=False,
            am_fg_thresh=240,
            am_bg_thresh=10,
            am_erode_size=10,
            post_process_mask=False,
            compression="deflate",
            overwrite=False,
            skip_existing=True,
        )

        btn_run.config(state="disabled")
        _log("Starting… (this can take several minutes)")

        def _work() -> None:
            try:
                stats = run_batch(cfg)
                _log("")
                _log("Done.")
                _log(f"Files found: {stats.total}")
                _log(f"Processed:   {stats.processed}")
                _log(f"Skipped:     {stats.skipped}")
                _log(f"Failed:      {stats.failed}")
                _log(f"Seconds:     {stats.seconds:.2f}")
                _log(f"Provider:    {', '.join(stats.provider_choice.providers)}")
            except Exception as e:
                _log(f"[fatal] {e}")
            finally:
                btn_run.config(state="normal")

        threading.Thread(target=_work, daemon=True).start()

    ttk.Label(frm, text="Input folder").grid(row=0, column=0, sticky="w")
    ttk.Entry(frm, textvariable=input_var).grid(row=0, column=1, sticky="ew", padx=8)
    ttk.Button(frm, text="Browse…", command=choose_input).grid(row=0, column=2, sticky="e")

    ttk.Label(frm, text="Output folder").grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(frm, textvariable=output_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
    ttk.Button(frm, text="Browse…", command=choose_output).grid(row=1, column=2, sticky="e", pady=(8, 0))

    ttk.Label(frm, text="Model").grid(row=2, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(frm, textvariable=model_var).grid(row=2, column=1, sticky="ew", padx=8, pady=(8, 0))
    ttk.Label(frm, text='e.g. "u2netp", "isnet-general-use"').grid(row=2, column=2, sticky="w", pady=(8, 0))

    ttk.Label(frm, text="Provider").grid(row=3, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(frm, textvariable=provider_var).grid(row=3, column=1, sticky="ew", padx=8, pady=(8, 0))
    ttk.Label(frm, text='e.g. "auto", "cpu", "cuda", "coreml"').grid(row=3, column=2, sticky="w", pady=(8, 0))

    ttk.Label(frm, text="Workers").grid(row=4, column=0, sticky="w", pady=(8, 0))
    ttk.Spinbox(frm, from_=1, to=128, textvariable=workers_var, width=8).grid(
        row=4, column=1, sticky="w", padx=8, pady=(8, 0)
    )

    ttk.Label(frm, text="Mask max size").grid(row=5, column=0, sticky="w", pady=(8, 0))
    ttk.Spinbox(frm, from_=0, to=8192, textvariable=mask_var, width=8).grid(
        row=5, column=1, sticky="w", padx=8, pady=(8, 0)
    )
    ttk.Label(frm, text="(smaller = faster)").grid(row=5, column=2, sticky="w", pady=(8, 0))

    btn_run = ttk.Button(frm, text="Run", command=run_clicked)
    btn_run.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))

    _log("Tip: for speed use model=u2netp and a smaller mask max size (e.g. 768–1024).")
    root.minsize(780, 420)
    root.mainloop()


if __name__ == "__main__":
    main()

