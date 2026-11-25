"""Install the pinned MiniLM tokenizer and quantized ONNX artifact."""

from __future__ import annotations

import argparse
import shutil
import tempfile
import urllib.request
from pathlib import Path

from scholarql.retrieval import (
    MODEL_REVISION,
    MODEL_VARIANTS,
    TOKENIZER_SHA256,
    _sha256,
    model_directory,
)

BASE = f"https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/{MODEL_REVISION}/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=model_directory())
    parser.add_argument(
        "--portable", action="store_true", help="Use the larger unquantized, portable version."
    )
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    path = "onnx/model.onnx" if args.portable else next(iter(MODEL_VARIANTS))
    sha = MODEL_VARIANTS.get(path)
    for remote, name, digest in [
        (path, "model.onnx", sha),
        ("tokenizer.json", "tokenizer.json", TOKENIZER_SHA256),
    ]:
        target = args.directory / name
        if target.exists() and digest and _sha256(target) == digest:
            print(f"Verified {target}")
            continue
        request = urllib.request.Request(BASE + remote, headers={"User-Agent": "ScholarQL/1.0"})
        with tempfile.NamedTemporaryFile(dir=args.directory, delete=False) as output:
            stage = Path(output.name)
        try:
            with urllib.request.urlopen(request, timeout=45) as source, stage.open("wb") as output:
                shutil.copyfileobj(source, output)
            if digest and _sha256(stage) != digest:
                raise ValueError(f"SHA-256 verification failed for {remote}")
            if stage.stat().st_size < 100_000:
                raise ValueError(f"Incomplete model artifact: {remote}")
            stage.replace(target)
        finally:
            stage.unlink(missing_ok=True)
        print(f"Installed {target}")


if __name__ == "__main__":
    main()
