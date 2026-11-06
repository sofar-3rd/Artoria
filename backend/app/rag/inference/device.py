def resolve_device(setting: str) -> str:
    """Turn the `rag_device` setting into a torch device name.

    "auto" picks the fastest device this machine has: CUDA, then Apple's MPS, then the CPU. Anything else
    is used as given ("cpu", "cuda", "cuda:1", "mps"). torch is imported here, not at module level, so
    importing this module stays cheap.
    """
    value = (setting or "cpu").strip().lower()
    if value != "auto":
        return value
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
