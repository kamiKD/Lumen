"""Deteccao generica de GPU: NVIDIA, AMD, Intel, Microsoft Basic ou sem GPU discreta.

O controle real de gamma usa SetDeviceGammaRamp (GDI), que e vendor-agnostic:
funciona com qualquer GPU/driver/monitor no Windows. Este modulo apenas
identifica o hardware para exibicao/diagnostico — nunca bloqueia o uso.
"""
from __future__ import annotations

import ctypes
import re
import shutil
import subprocess

# Impede que cada subprocesso abra uma janela de console que so pisca.
# No .exe (subsistema GUI) um wmic/powershell/nvidia-smi sem esta flag cria
# um console proprio que aparece por ~200ms e some. CREATE_NO_WINDOW = 0x08000000.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _run(argv, timeout: int) -> str:
    """Saida de um comando externo, sem janela de console e sem stderr."""
    return subprocess.check_output(
        argv, text=True, timeout=timeout,
        stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)


def classify_vendor(name: str) -> str:
    n = (name or "").lower()
    if not n:
        return "Desconhecido"
    if "nvidia" in n or "geforce" in n or "quadro" in n or "tesla" in n:
        return "NVIDIA"
    if re.search(r"\bamd\b|radeon|rx |vega|athlon.*radeon|ryzen.*radeon|firepro|advantech.*amd", n):
        return "AMD"
    # "Arc", "UHD Graphics", "Iris", "HD Graphics" sao Intel
    if "intel" in n or "uhd graphics" in n or "iris" in n or "hd graphics" in n or " arc" in n or n.strip().startswith("arc "):
        return "Intel"
    if "microsoft" in n and ("basic" in n or "hyper-v" in n or "remote" in n):
        return "Microsoft (basico)"
    if "vmware" in n or "virtualbox" in n or "virtio" in n or "llvmpipe" in n:
        return "Virtual"
    if "qualcomm" in n or "snapdragon" in n or "adreno" in n:
        return "Qualcomm"
    return "Outro"


def _run_nvidia_smi() -> str:
    exe = shutil.which("nvidia-smi")
    candidates = ([exe] if exe else []) + [
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]
    for p in candidates:
        if not p:
            continue
        try:
            out = _run([p, "--query-gpu=name,driver_version",
                        "--format=csv,noheader"], timeout=10)
            if out and out.strip():
                return out.strip()
        except Exception:
            continue
    return ""


def _nvml_gpus() -> list[dict]:
    """GPUs NVIDIA via NVML (pynvml e opcional — so existe em maquina NVIDIA)."""
    gpus: list[dict] = []
    try:
        import pynvml
        pynvml.nvmlInit()
        try:
            n = pynvml.nvmlDeviceGetCount()
            ver = pynvml.nvmlSystemGetDriverVersion()
            if isinstance(ver, bytes):
                ver = ver.decode(errors="ignore")
            for i in range(n):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode(errors="ignore")
                gpus.append({"name": name, "vendor": "NVIDIA",
                             "driver": ver, "source": "NVML"})
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
    except Exception:
        pass
    return gpus


def _wmi_video_controllers() -> list[dict]:
    """Lista TODOS os adaptadores de video via WMI (AMD/Intel/NVIDIA/Microsoft).

    Tenta `wmic` (legado) e cai para PowerShell Get-CimInstance quando o wmic
    nao existe (Windows 11 recente removeu o wmic).
    """
    gpus: list[dict] = []

    def _push(name: str, driver: str, source: str):
        name = (name or "").strip()
        if not name:
            return
        gpus.append({"name": name,
                     "vendor": classify_vendor(name),
                     "driver": (driver or "").strip(),
                     "source": source})

    # 1) wmic (formato csv: Node,DriverVersion,Name)
    try:
        out = _run(["wmic", "path", "win32_VideoController",
                    "get", "name,DriverVersion", "/format:csv"], timeout=15)
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("Node"):
                continue
            cols = [c.strip() for c in line.split(",")]
            if len(cols) >= 3:
                _push(cols[2], cols[1], "WMI")
        if gpus:
            return gpus
    except Exception:
        pass

    # 2) PowerShell Get-CimInstance (sem wmic)
    try:
        ps = ("Get-CimInstance Win32_VideoController | "
              "Select-Object Name,DriverVersion | "
              "ForEach-Object { $_.Name + '|' + $_.DriverVersion }")
        out = _run(["powershell", "-NoProfile", "-NonInteractive",
                    "-WindowStyle", "Hidden", "-Command", ps], timeout=20)
        for line in out.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            name, _, driver = line.partition("|")
            _push(name, driver, "WMI")
        if gpus:
            return gpus
    except Exception:
        pass
    return gpus


def nvapi_dll_present() -> tuple[bool, str]:
    """Presenca de NVAPI (informativo; gamma nao depende dela)."""
    for dll in ("nvapi64.dll", "nvapi.dll"):
        try:
            ctypes.WinDLL(dll)
            return True, dll
        except Exception:
            continue
    return False, ""


def get_gpus() -> list[dict]:
    """Detecta qualquer GPU: AMD, Intel, NVIDIA, Microsoft basico ou outras.

    Ordem: WMI (todas) -> enriquece NVIDIA com nvidia-smi/NVML quando presente.
    Nunca retorna erro — retorna [] se nada for detectado.
    """
    gpus = _wmi_video_controllers()

    # Enriquece/completa NVIDIA com nvidia-smi (driver exato por GPU)
    smi = _run_nvidia_smi()
    if smi:
        for line in smi.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0]:
                continue
            name = parts[0]
            driver = parts[1] if len(parts) > 1 else ""
            # Evita duplicar o que o WMI ja trouxe
            if not any(g["name"].lower() == name.lower() for g in gpus):
                gpus.append({"name": name, "vendor": "NVIDIA",
                             "driver": driver, "source": "nvidia-smi"})
            else:
                for g in gpus:
                    if (g["name"].lower() == name.lower()
                            and not g.get("driver") and driver):
                        g["driver"] = driver
                        g["source"] = g.get("source", "WMI") + "+nvidia-smi"

    # NVML como ultimo recurso (ex.: WMI vazio mas driver NVIDIA presente)
    if not any(g["vendor"] == "NVIDIA" for g in gpus):
        gpus.extend(_nvml_gpus())

    # Deduplica por nome (mantem primeira ocorrencia)
    seen: set[str] = set()
    uniq: list[dict] = []
    for g in gpus:
        key = g["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(g)
    return uniq


def summarize() -> dict:
    """Resumo vendor-agnostic para a UI (nunca bloqueia o uso do app)."""
    gpus = get_gpus()
    present, dll = nvapi_dll_present()
    if gpus:
        primary = gpus[0]
        vendors = sorted({g.get("vendor", "?") for g in gpus})
        label = "; ".join(
            f'{g["name"]} ({g.get("vendor", "?")})' for g in gpus)
    else:
        primary = {"name": "Nenhuma GPU dedicada detectada "
                           "(video integrado / driver basico)",
                   "vendor": "Desconhecido", "driver": ""}
        vendors = []
        label = primary["name"]
    return {
        "found": bool(gpus),
        "gpus": gpus,
        "primary_name": primary.get("name", ""),
        "vendor": primary.get("vendor", ""),
        "vendors": vendors,
        "label": label,
        "driver": primary.get("driver", ""),
        "nvapi_dll": dll if present else "",
        "has_nvidia": any(g.get("vendor") == "NVIDIA" for g in gpus),
        "note": ("Controle real via SetDeviceGammaRamp (GDI do Windows) — "
                 "funciona com AMD, Intel, NVIDIA e video integrado; "
                 "NVAPI nao expoe rampa de gamma de monitor."),
    }
