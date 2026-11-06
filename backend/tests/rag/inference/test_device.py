import sys
import types

import pytest

from app.rag.inference.device import resolve_device


@pytest.mark.parametrize("value,expected", [("cpu", "cpu"), ("CPU", "cpu"), (" cpu ", "cpu"), ("", "cpu")])
def test_cpu_needs_no_torch_and_is_always_valid(value, expected):
    assert resolve_device(value) == expected


def fake_torch(monkeypatch, cuda: bool, mps: bool):
    torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: cuda),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps)),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)


@pytest.mark.parametrize("cuda,mps,expected", [(True, True, "cuda"), (True, False, "cuda"), (False, True, "mps"), (False, False, "cpu")])
def test_auto_picks_the_fastest_available_device(monkeypatch, cuda, mps, expected):
    fake_torch(monkeypatch, cuda, mps)
    assert resolve_device("auto") == expected
    assert resolve_device(" AUTO ") == expected


def test_auto_without_an_mps_backend_attribute_falls_back_to_cpu(monkeypatch):
    torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False), backends=types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert resolve_device("auto") == "cpu"


@pytest.mark.parametrize("value,cuda,mps", [("cuda", True, False), (" CUDA:1 ", True, False), ("mps", False, True)])
def test_an_explicit_device_that_exists_is_used_as_given(monkeypatch, value, cuda, mps):
    fake_torch(monkeypatch, cuda, mps)
    assert resolve_device(value) == value.strip().lower()


@pytest.mark.parametrize("value,cuda,mps,fragment", [("cuda", False, True, "CUDA is not available"), ("cuda:0", False, False, "CUDA is not available"), ("mps", True, False, "MPS is not available")])
def test_an_explicit_device_that_does_not_exist_is_refused(monkeypatch, value, cuda, mps, fragment):
    fake_torch(monkeypatch, cuda, mps)
    with pytest.raises(ValueError, match=fragment):
        resolve_device(value)


@pytest.mark.parametrize("value", ["gpu", "tpu", "cudaa", "cuda0", "xpu"])
def test_an_unknown_device_name_is_refused(monkeypatch, value):
    fake_torch(monkeypatch, True, True)
    with pytest.raises(ValueError, match="not a device this code knows"):
        resolve_device(value)
