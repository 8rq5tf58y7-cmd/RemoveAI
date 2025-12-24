from __future__ import annotations

import threading
import tkinter as tk
import os
import subprocess
import sys
import signal
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

    progress_var = tk.IntVar(value=0)
    progress_text = tk.StringVar(value="")
    progress = ttk.Progressbar(frm, mode="indeterminate")
    progress.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    ttk.Label(frm, textvariable=progress_text).grid(row=9, column=0, columnspan=3, sticky="w")

    log = tk.Text(frm, height=10, width=80)
    log.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
    frm.rowconfigure(10, weight=1)

    current_proc: subprocess.Popen[str] | None = None
    current_proc_lock = threading.Lock()

    def _log(msg: str) -> None:
        # Tk widgets must only be updated from the main thread.
        def _do():
            log.insert("end", msg + "\n")
            log.see("end")

        root.after(0, _do)

    def _set_run_enabled(enabled: bool) -> None:
        def _do():
            btn_run.config(state="normal" if enabled else "disabled")
            btn_stop.config(state="disabled" if enabled else "normal")

        root.after(0, _do)

    def _progress_init_unknown() -> None:
        def _do():
            progress.config(mode="indeterminate", maximum=100)
            progress.start(10)
            progress_text.set("Starting…")

        root.after(0, _do)

    def _progress_init_total(total: int) -> None:
        def _do():
            progress.stop()
            progress.config(mode="determinate", maximum=max(1, total), variable=progress_var)
            progress_var.set(0)
            progress_text.set(f"0 / {total}")

        root.after(0, _do)

    def _progress_update(done: int, total: int, processed: int, skipped: int, failed: int) -> None:
        def _do():
            progress_var.set(done)
            progress_text.set(f"{done} / {total}  (ok={processed}, skipped={skipped}, failed={failed})")

        root.after(0, _do)

    def _progress_done() -> None:
        def _do():
            progress.stop()

        root.after(0, _do)

    def stop_clicked() -> None:
        def _stop_worker() -> None:
            nonlocal current_proc
            with current_proc_lock:
                proc = current_proc

            if proc is None or proc.poll() is not None:
                return

            _log("Stop requested…")
            try:
                if os.name == "posix":
                    # Subprocess is started in a new session; proc.pid is the process group id.
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    try:
                        proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                    except Exception:
                        proc.terminate()
            except Exception as e:
                _log(f"[warn] failed to signal process: {e}")

            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except Exception as e:
                    _log(f"[warn] failed to kill process: {e}")

        threading.Thread(target=_stop_worker, daemon=True).start()

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
        _progress_init_unknown()
        _log("Starting… (this can take several minutes)")

        def _work() -> None:
            nonlocal current_proc
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
                env["REMOVEBG_BATCH_PROGRESS"] = "1"
                # If the user set this env var (e.g. to an external drive), keep it for the subprocess.
                # Otherwise the default cache location is used.

                _log("Command:")
                _log("  " + " ".join(cmd))
                _log("")

                popen_kwargs: dict[str, object] = {}
                if os.name == "posix":
                    popen_kwargs["start_new_session"] = True
                elif os.name == "nt":
                    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

                proc = subprocess.Popen(  # type: ignore[type-var]
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                    **popen_kwargs,
                )
                with current_proc_lock:
                    current_proc = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    s = line.rstrip("\n")
                    if s.startswith("__TOTAL__ "):
                        try:
                            total = int(s.split(" ", 1)[1].strip())
                            _progress_init_total(total)
                        except Exception:
                            pass
                        continue
                    if s.startswith("__PROGRESS__ "):
                        try:
                            parts = s.split()
                            done = int(parts[1])
                            total = int(parts[2])
                            processed = int(parts[3])
                            skipped = int(parts[4])
                            failed = int(parts[5])
                            _progress_update(done, total, processed, skipped, failed)
                        except Exception:
                            pass
                        continue
                    _log(s)

                rc = proc.wait()
                if rc != 0:
                    _log(f"[fatal] process exited with code {rc}")
            except Exception as e:
                _log(f"[fatal] {e}")
            finally:
                with current_proc_lock:
                    current_proc = None
                _progress_done()
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

    actions = ttk.Frame(frm)
    actions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 0))
    actions.columnconfigure(0, weight=1)

    btn_run = ttk.Button(actions, text="Run", command=run_clicked)
    btn_run.grid(row=0, column=0, sticky="ew")

    btn_stop = ttk.Button(actions, text="Stop", command=stop_clicked, state="disabled")
    btn_stop.grid(row=0, column=1, sticky="e", padx=(8, 0))

    _log("Tip: for speed use model=u2netp and a smaller mask max size (e.g. 768–1024).")
    root.minsize(780, 420)
    root.mainloop()


if __name__ == "__main__":
    main()

