## Batch background removal (local, TIFF-safe)

This repo contains a **local** (offline) batch background-removal app designed for **1000+ images** with **TIFF-compatible** input/output and a focus on **minimizing data loss**.

### What it does

- **Batch process a folder** (recursively optional)
- **Fast**: parallel workers + a lightweight local segmentation model (via ONNX)
- **TIFF output**: writes **RGBA TIFF** (original RGB preserved as much as possible; alpha is the computed cutout mask)
- **Data-loss minimizing**: keeps original **bit depth** when possible (e.g. 16-bit TIFF stays 16-bit), preserves common metadata like ICC profile when available
- **Offline**: uses a local AI model (not a cloud API)

### Quick start (macOS / Linux)

```bash
chmod +x ./scripts/install_mac_linux.sh
./scripts/install_mac_linux.sh
./.venv/bin/removebg-batch --help
```

### Optional: install rembg engine (macOS / Linux)

This enables `--engine rembg` (more features/models, but heavier dependencies).

```bash
chmod +x ./scripts/install_mac_linux_rembg.sh
./scripts/install_mac_linux_rembg.sh
./.venv-rembg/bin/removebg-batch --engine rembg --help
```

### GUI

- Run (default ONNX engine):

```bash
./.venv/bin/removebg-batch-gui
```

- Run (rembg engine available in rembg venv):

```bash
./.venv-rembg/bin/removebg-batch-gui
```

The GUI has an **Engine** dropdown (`onnx` / `rembg`).

### Quick start (Windows PowerShell)

```powershell
.\scripts\install_windows.ps1
.\.venv\Scripts\removebg-batch --help
```

### Optional: install rembg engine (Windows PowerShell)

```powershell
.\scripts\install_windows_rembg.ps1
.\.venv-rembg\Scripts\removebg-batch --engine rembg --help
```

### Example usage

```bash
removebg-batch \
  --input "/path/to/input_folder" \
  --output "/path/to/output_folder" \
  --engine onnx \
  --model u2netp \
  --workers 8 \
  --mask-max-size 1024 \
  --compression deflate
```

### Notes on performance targets

Getting **1000+ photos under 10 minutes** depends on CPU/GPU, image resolution, and settings:

- Use `--model u2netp` (fastest default)
- Increase `--workers` (but avoid oversubscription; start around half your logical cores)
- Use `--mask-max-size 1024` (or smaller) for speed
- If you have a compatible GPU, install GPU runtime and use `--provider cuda`:
  - Windows/Linux (CUDA): `pip install "removebg-batch[gpu]"`

### Building a self-contained binary (optional)

You can package a standalone executable with PyInstaller:

```bash
python -m pip install -U pyinstaller
pyinstaller --noconfirm --clean -n removebg-batch -F -m removebg_batch.cli
```

The resulting binary appears in `dist/`.

### macOS note (Python 3.13)

This project uses a small ONNX model + ONNX Runtime and is pinned to **Python 3.10–3.12**. The installer will automatically install **Python 3.12** via `uv`.

### Uninstall / cleanup (macOS)

- Remove project virtual environments:

```bash
rm -rf .venv .venv-rembg
```

- If you accidentally ran an installer with `sudo` and `.venv` is owned by root:

```bash
sudo rm -rf .venv .venv-rembg
```

- If you installed packages globally by mistake (not recommended), you can uninstall them:

```bash
python3 -m pip uninstall -y removebg-batch rembg pymatting numba llvmlite
```

