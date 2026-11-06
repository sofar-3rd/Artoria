"""Download the bge models into the model directory.

Run this with the SYSTEM python, not `uv run`:

    python3 -m venv /tmp/hfv && /tmp/hfv/bin/pip install huggingface_hub
    /tmp/hfv/bin/python backend/scripts/download_models.py [--dir backend/models]

On the machine this was developed on, the Python that `uv run` uses fails the TLS handshake with
huggingface.co ("record layer failure") while the system Python works. Only the files needed at run time
are fetched (no ONNX copies), about 4.5 GB in total.
"""

import argparse
import sys
import time

MODELS = [
    (
        "BAAI/bge-m3",
        "bge-m3",
        [
            "config.json",
            "tokenizer*",
            "sentencepiece.bpe.model",
            "special_tokens_map.json",
            "modules.json",
            "sentence_bert_config.json",
            "1_Pooling/*",
            "config_sentence_transformers.json",
            "pytorch_model.bin",
        ],
    ),
    (
        "BAAI/bge-reranker-v2-m3",
        "bge-reranker-v2-m3",
        [
            "config.json",
            "tokenizer*",
            "sentencepiece.bpe.model",
            "special_tokens_map.json",
            "model.safetensors",
        ],
    ),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the RAG models")
    parser.add_argument("--dir", default="./models", help="target directory (default ./models)")
    args = parser.parse_args(argv)
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub is not installed: pip install huggingface_hub", file=sys.stderr)
        return 2
    for repo, name, allow in MODELS:
        started = time.time()
        print(f"downloading {repo} ...", flush=True)
        snapshot_download(repo, local_dir=f"{args.dir}/{name}", allow_patterns=allow)
        print(f"done {repo} in {time.time() - started:.0f}s", flush=True)
    print("all models are in place")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
