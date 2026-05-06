"""Download Kokoro v1.0 model + voices into the working directory.

Kokoro-ONNX needs `kokoro-v1.0.onnx` (~310 MB) and `voices-v1.0.bin` (~27 MB);
the kokoro-onnx package itself does not bundle them.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


def _progress(name: str):
    last = [0]

    def hook(block_num: int, block_size: int, total: int):
        done = block_num * block_size
        pct = 100 * done / total if total > 0 else 0
        if int(pct) != last[0]:
            last[0] = int(pct)
            sys.stdout.write(f"\r{name}: {pct:5.1f}% ({done / 1e6:6.1f} / {total / 1e6:6.1f} MB)")
            sys.stdout.flush()

    return hook


def main() -> int:
    out_dir = Path.cwd()
    for name, url in FILES.items():
        target = out_dir / name
        if target.exists():
            print(f"{name}: already present, skipping")
            continue
        print(f"{name}: downloading from {url}")
        urllib.request.urlretrieve(url, target, _progress(name))
        print()
    print("done. Files in:", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
