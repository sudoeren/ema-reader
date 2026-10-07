import sys
import types

import ema


def fake_torch(cuda, mps):
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: cuda)
    torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps))
    return torch


def test_the_fastest_device_is_chosen(monkeypatch):
    for cuda, mps, expected in [(True, False, "cuda"), (False, True, "mps"), (False, False, "cpu")]:
        monkeypatch.setitem(sys.modules, "torch", fake_torch(cuda, mps))
        assert ema.best_device() == expected
