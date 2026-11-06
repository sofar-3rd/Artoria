def resolve_device(setting: str) -> str:
    """Turn the `rag_device` setting into a torch device name, refusing one this machine cannot use.

    "auto" picks the fastest device that exists: CUDA, then Apple's MPS, then the CPU. An explicit value
    ("cpu", "cuda", "cuda:1", "mps") is validated: the reranker's failures are absorbed by a fall-back to
    the fused order, so a device that cannot work would switch reranking off for good with only a log line.
    Failing at start-up makes the mistake visible. torch is imported here, not at module level.
    """
    value = (setting or "cpu").strip().lower()
    if value == "cpu":
        return "cpu"
    import torch

    cuda_ok = torch.cuda.is_available()
    mps_ok = bool(getattr(torch.backends, "mps", None)) and torch.backends.mps.is_available()
    if value == "auto":
        return "cuda" if cuda_ok else "mps" if mps_ok else "cpu"
    if value.split(":")[0] == "cuda" and not cuda_ok:
        raise ValueError(f"RAG_DEVICE={setting!r} but CUDA is not available on this machine; use auto, cpu or mps")
    if value == "mps" and not mps_ok:
        raise ValueError(f"RAG_DEVICE={setting!r} but MPS is not available on this machine; use auto or cpu")
    if value.split(":")[0] not in ("cuda", "mps"):
        raise ValueError(f"RAG_DEVICE={setting!r} is not a device this code knows; use auto, cpu, cuda or mps")
    return value
