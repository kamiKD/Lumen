"""Compat: antigo modulo NVIDIA-only, hoje delega ao detector generico.

Mantido para nao quebrar imports existentes (`nvidia_controller.summarize()`,
`get_nvidia_gpus()`, `nvapi_dll_present()`). Codigo novo deve usar
`gpu_detector` (AMD / Intel / NVIDIA / video integrado / sem GPU).
"""
from __future__ import annotations

from . import gpu_detector


def _run_nvidia_smi() -> str:
    return gpu_detector._run_nvidia_smi()


def get_nvidia_gpus() -> list[dict]:
    """Apenas GPUs NVIDIA (subconjunto de gpu_detector.get_gpus())."""
    return [g for g in gpu_detector.get_gpus() if g.get("vendor") == "NVIDIA"]


def nvapi_dll_present() -> tuple[bool, str]:
    return gpu_detector.nvapi_dll_present()


def summarize() -> dict:
    """Resumo generico (AMD/Intel/NVIDIA/integrado) + campos legados."""
    s = gpu_detector.summarize()
    # Campos que o app antigo esperava quando so havia NVIDIA:
    s.setdefault("note", "")
    return s
