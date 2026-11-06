import sys
import types

import pytest

from app.rag.inference.device import resolve_device


@pytest.mark.parametrize("value,expected", [("cpu", "cpu"), ("CPU", "cpu"), (" cuda:1 ", "cuda:1"), ("mps", "mps"), ("", "cpu")])
def test_explicit_values_are_used_as_given(value, expected):
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
