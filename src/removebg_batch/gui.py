from __future__ import annotations

import threading
import tkinter as tk
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pipeline import RunConfig, default_workers, run_batch


@dataclass(frozen=True)
class UiState:
    input_dir: Path
    output_dir: Path
    engine: str
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
    engine_var = tk.StringVar(value="onnx")
    model_var = tk.StringVar(value="u2netp")
    provider_var = tk.StringVar(value="auto")
    workers_var = tk.IntVar(value=default_workers())
    mask_var = tk.IntVar(value=1024)

    log = tk.Text(frm, height=10, width=80)
    log.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    frm.rowconfigure(8, weight=1)

    def _log(msg: str) -> None:
        # Tk widgets must only be updated from the main thread.
        def _do():
            log.insert("end", msg + "\n")
            log.see("end")

        root.after(0, _do)

    def _set_run_enabled(enabled: bool) -> None:
        def _do():
            btn_run.config(state="normal" if enabled else "disabled")

        root.after(0, _do)

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

        engine = (engine_var.get().strip() or "onnx").lower()
        if engine == "rembg":
            # Make this failure friendly: rembg is an optional install and often lives in a separate venv.
            try:
                import rembg  # type: ignore  # noqa: F401
            except Exception:
                messagebox.showerror(
                    "rembg not installed",
                    "You selected engine=rembg, but rembg isn't installed in this environment.\n\n"
                    "Install it with the rembg installer and launch the GUI from that venv:\n"
                    "  ./scripts/install_mac_linux_rembg.sh\n"
                    "  ./.venv-rembg/bin/removebg-batch-gui\n",
                )
                return

        model = model_var.get().strip() or "u2netp"
        provider = provider_var.get().strip() or "auto"
        workers = int(workers_var.get())
        mask_max_size = int(mask_var.get())

        _set_run_enabled(False)
        _log("Starting… (this can take several minutes)")

        def _work() -> None:
            try:
                # Run the CLI in a subprocess to avoid UI freezes from multiprocessing
                # and to keep all heavy work outside the Tk process.
                cmd = [
                    sys.executable,
                    "-m",
                    "removebg_batch.cli",
                    "--input",
                    in_dir,
                    "--output",
                    out_dir,
                    "--engine",
                    engine,
                    "--model",
                    model,
                    "--provider",
                    provider,
                    "--workers",
                    str(workers),
                    "--mask-max-size",
                    str(mask_max_size),
                    "--compression",
                    "deflate",
                    "--skip-existing",
                ]

                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                env["REMOVEBG_BATCH_NO_PROGRESS"] = "1"

                _log("Command:")
                _log("  " + " ".join(cmd))
                _log("")

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    _log(line.rstrip("\n"))

                rc = proc.wait()
                if rc != 0:
                    _log(f"[fatal] process exited with code {rc}")
            except Exception as e:
                _log(f"[fatal] {e}")
            finally:
                _set_run_enabled(True)

        threading.Thread(target=_work, daemon=True).start()

    ttk.Label(frm, text="Input folder").grid(row=0, column=0, sticky="w")
    ttk.Entry(frm, textvariable=input_var).grid(row=0, column=1, sticky="ew", padx=8)
    ttk.Button(frm, text="Browse…", command=choose_input).grid(row=0, column=2, sticky="e")

    ttk.Label(frm, text="Output folder").grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(frm, textvariable=output_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
    ttk.Button(frm, text="Browse…", command=choose_output).grid(row=1, column=2, sticky="e", pady=(8, 0))

    ttk.Label(frm, text="Engine").grid(row=2, column=0, sticky="w", pady=(8, 0))
    engine_combo = ttk.Combobox(frm, textvariable=engine_var, values=("onnx", "rembg"), state="readonly", width=10)
    engine_combo.grid(row=2, column=1, sticky="w", padx=8, pady=(8, 0))
    ttk.Label(frm, text='onnx = easiest install; rembg = optional extra').grid(row=2, column=2, sticky="w", pady=(8, 0))

    ttk.Label(frm, text="Model").grid(row=3, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(frm, textvariable=model_var).grid(row=3, column=1, sticky="ew", padx=8, pady=(8, 0))
    ttk.Label(frm, text='e.g. "u2netp", "u2net"').grid(row=3, column=2, sticky="w", pady=(8, 0))

    ttk.Label(frm, text="Provider").grid(row=4, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(frm, textvariable=provider_var).grid(row=4, column=1, sticky="ew", padx=8, pady=(8, 0))
    ttk.Label(frm, text='e.g. "auto", "cpu", "cuda", "coreml"').grid(row=4, column=2, sticky="w", pady=(8, 0))

    ttk.Label(frm, text="Workers").grid(row=5, column=0, sticky="w", pady=(8, 0))
    ttk.Spinbox(frm, from_=1, to=128, textvariable=workers_var, width=8).grid(
        row=5, column=1, sticky="w", padx=8, pady=(8, 0)
    )

    ttk.Label(frm, text="Mask max size").grid(row=6, column=0, sticky="w", pady=(8, 0))
    ttk.Spinbox(frm, from_=0, to=8192, textvariable=mask_var, width=8).grid(
        row=6, column=1, sticky="w", padx=8, pady=(8, 0)
    )
    ttk.Label(frm, text="(smaller = faster)").grid(row=6, column=2, sticky="w", pady=(8, 0))

    btn_run = ttk.Button(frm, text="Run", command=run_clicked)
    btn_run.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 0))

    _log("Tip: for speed use model=u2netp and a smaller mask max size (e.g. 768–1024).")
    root.minsize(780, 420)
    root.mainloop()


if __name__ == "__main__":
    main()

