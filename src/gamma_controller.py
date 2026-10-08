"""Lumen - controle real de gamma/brilho/contraste via rampa do Windows.

Vendor-agnostic: funciona com AMD, Intel, NVIDIA, video integrado e driver
basico da Microsoft, pois usa SetDeviceGammaRamp() (GDI) por monitor.

Nota tecnica honesta (investigacao NVAPI R590 + NvAPIWrapper):
- Nao existe funcao NVAPI para rampa de gamma de monitor. NvAPI_VIO_SetGamma
  refere-se a placas de captura VIO, nao a displays.
- O proprio Painel de Controle NVIDIA (e os equivalentes AMD Adrenalin /
  Intel Graphics) alteram gamma via SetDeviceGammaRamp() do Windows.
- NVAPI moderna possui NvAPI_Disp_ColorControl (NV_COLOR_DATA) para formato de
  cor/BPC/HDR, mas nao substitui a rampa de gamma classica.
- Conclusao: deteccao via WMI/nvidia-smi/NVML (informativa) + aplicacao real
  via SetDeviceGammaRamp (mesmo caminho dos paineis dos fabricantes).
  Sem overlay/filtro, sem exigir GPU dedicada.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
from abc import ABC, abstractmethod

# Carrega com use_last_error=True para que ctypes.get_last_error() reflita o
# GetLastError() real do Windows logo apos a chamada GDI que falhou. Sem
# isso, o codigo de erro retornado e lixo e o diagnostico (HDR? driver AMD?
# handle truncado?) fica impossivel.
_user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32.dll", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

# Aliases publicos (mantidos p/ compatibilidade com imports externos).
user32 = _user32
gdi32 = _gdi32

# ---------------------------------------------------------------- Prototipos ctypes
# Sem argtypes/restype o ctypes assume c_int (32 bits) para tudo. Em x64 o
# HDC tem 64 bits: handles com bits altos eram truncados e Get/SetDevice-
# GammaRamp falhava de forma intermitente — exatamente o que usuarios AMD
# relataram ("Gamma nao suportado" / "Falha ao aplicar" aleatorios ou
# constantes dependendo do valor do handle). Tambem trocamos CreateDCA
# (ANSI) por CreateDCW (Unicode): o nome do monitor ("\\.\\DISPLAY1") e
# wide string; via ANSI ele podia ser convertido errado e o DC vinha de um
# dispositivo inexistente -> "monitor desconectado" fantasma.
try:
    _gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
                                 wintypes.LPCWSTR, wintypes.LPVOID]
    _gdi32.CreateDCW.restype = wintypes.HDC
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32.DeleteDC.restype = wintypes.BOOL
    _gdi32.GetDeviceGammaRamp.argtypes = [wintypes.HDC, wintypes.LPVOID]
    _gdi32.GetDeviceGammaRamp.restype = wintypes.BOOL
    _gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, wintypes.LPVOID]
    _gdi32.SetDeviceGammaRamp.restype = wintypes.BOOL
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.ReleaseDC.restype = ctypes.c_int
    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = wintypes.DWORD
except Exception:
    pass

# Ultimo erro Win32 da operacao de gamma (0 = ultima op teve sucesso ou ainda
# nao houve falha). Usado pelas mensagens de diagnostico na UI.
_last_gamma_error: int = 0


def get_last_gamma_error() -> int:
    """Codigo GetLastError() da ultima operacao de gamma que falhou (0 = ok)."""
    return _last_gamma_error


def _capture_error() -> int:
    global _last_gamma_error
    try:
        _last_gamma_error = int(ctypes.get_last_error() or 0)
    except Exception:
        _last_gamma_error = 0
    return _last_gamma_error


def _mark_ok() -> None:
    global _last_gamma_error
    _last_gamma_error = 0

# ---------------------------------------------------------------- LUT (estilo paineis NVIDIA/AMD/Intel)
# Formula equivalente a usada pelos paineis dos fabricantes / NvAPIWrapper.CalculateLUT.

def calculate_lut(gamma: float = 1.0, brightness_pct: float = 50.0,
                  contrast_pct: float = 50.0) -> list[int]:
    """Retorna LUT de 256 entradas (0..65535) combinando gamma+brilho+contraste.

    brightness_pct / contrast_pct: 0..100 (50 = neutro).
    gamma: 0.10..5.00 (1.0 = neutro). Fora da faixa e clampado p/ seguranca.
    """
    data_points = 256
    gamma = min(max(gamma, 0.10), 5.00)
    contrast = (min(max(contrast_pct, 0.0), 100.0) / 100.0 - 0.5) * 2.0  # -1..1
    brightness = (min(max(brightness_pct, 0.0), 100.0) / 100.0 - 0.5) * 2.0

    offset = contrast * -25.4 if contrast > 0 else contrast * -32.0
    rng = (data_points - 1) + offset * 2.0
    offset += brightness * (rng / 5.0)

    out: list[int] = []
    for i in range(data_points):
        factor = (i + offset) / rng if rng != 0 else 0.0
        factor = math.pow(max(factor, 0.0), 1.0 / gamma) if gamma != 0 else 0.0
        factor = min(max(factor, 0.0), 1.0)
        out.append(int(round(factor * 65535)))
    return out


def build_gamma_ramp(gamma: float, brightness_pct: float,
                     contrast_pct: float) -> (ctypes.Array, list[int]):
    """Constroi o buffer ctypes de 768 WORDs (R+G+B identicos)."""
    lut = calculate_lut(gamma, brightness_pct, contrast_pct)
    ramp = (wintypes.WORD * 768)()
    for i, v in enumerate(lut):
        ramp[i] = v            # R
        ramp[256 + i] = v      # G
        ramp[512 + i] = v      # B
    return ramp, lut


# ---------------------------------------------------------------- API Windows (ctypes)

def _create_dc_for_device(device: str | None):
    """Cria HDC via CreateDCW para o monitor. Retorna (hdc, True) ou (None, False)."""
    if not device:
        return None, False
    try:
        hdc = _gdi32.CreateDCW(None, device, None, None)
    except Exception:
        return None, False
    if not hdc:
        _capture_error()
        return None, False
    return hdc, True


def _get_screen_dc():
    """HDC da tela (fallback quando o DC por-monitor falha)."""
    try:
        hdc = _user32.GetDC(None)
    except Exception:
        return None, False
    if not hdc:
        _capture_error()
        return None, False
    return hdc, False


def _get_dc(device: str | None):
    """Estrategia em cascata (corrige o "monitor desconectado" fantasma):

    1. CreateDCW(device) quando um monitor especifico foi pedido;
    2. GetDC(NULL) como fallback (tela principal / driver que nao suporta
       DC por dispositivo, comum em iGPU AMD + dGPU / USB-C / dock).
    """
    if device:
        hdc, created = _create_dc_for_device(device)
        if hdc:
            return hdc, created
    hdc, created = _get_screen_dc()
    return hdc, created


def _iter_candidate_dcs(device: str | None):
    """Gera (hdc, needs_delete, label) na ordem de tentativa.

    Permite que Get/Set tente o DC do monitor e, se falhar, repita no DC
    da tela antes de desistir — sem vazar HDC (o chamador deve liberar).
    """
    tried_primary = False
    if device:
        hdc, created = _create_dc_for_device(device)
        if hdc:
            yield hdc, created, f"CreateDCW({device})"
            tried_primary = True
    hdc, created = _get_screen_dc()
    if hdc:
        # Evita duplicar quando device era None (so ha o screen DC).
        yield hdc, created, "GetDC(NULL)"
    elif not tried_primary:
        # Nenhum DC disponivel: o erro ja foi capturado em _get_screen_dc.
        return


def _release_dc(hdc, is_created: bool):
    if not hdc:
        return
    try:
        if is_created:
            _gdi32.DeleteDC(hdc)
        else:
            _user32.ReleaseDC(None, hdc)
    except Exception:
        pass


def _get_ramp_on_hdc(hdc) -> list[int] | None:
    ramp = (wintypes.WORD * 768)()
    try:
        ctypes.set_last_error(0)
    except Exception:
        pass
    ok = _gdi32.GetDeviceGammaRamp(hdc, ramp)
    if not ok:
        _capture_error()
        return None
    _mark_ok()
    return list(ramp)


def _set_ramp_on_hdc(hdc, ramp) -> bool:
    try:
        ctypes.set_last_error(0)
    except Exception:
        pass
    ok = bool(_gdi32.SetDeviceGammaRamp(hdc, ramp))
    if not ok:
        _capture_error()
    else:
        _mark_ok()
    return ok


def get_device_gamma_ramp(device: str | None = None) -> list[int] | None:
    got_any_dc = False
    for hdc, created, _label in _iter_candidate_dcs(device):
        got_any_dc = True
        try:
            ramp = _get_ramp_on_hdc(hdc)
            if ramp is not None:
                return ramp
        finally:
            _release_dc(hdc, created)
    if not got_any_dc:
        # _capture_error() ja rodou dentro de _create/_get_screen_dc.
        pass
    return None


def set_device_gamma_ramp(gamma: float, brightness_pct: float,
                          contrast_pct: float,
                          device: str | None = None) -> bool:
    ramp, _ = build_gamma_ramp(gamma, brightness_pct, contrast_pct)
    return set_raw_ramp(list(ramp), device)


def set_raw_ramp(ramp_values: list[int] | tuple, device: str | None = None) -> bool:
    if len(ramp_values) != 768:
        raise ValueError("rampa precisa de 768 valores")
    ramp = (wintypes.WORD * 768)(*ramp_values)
    got_any_dc = False
    for hdc, created, _label in _iter_candidate_dcs(device):
        got_any_dc = True
        try:
            if _set_ramp_on_hdc(hdc, ramp):
                return True
        finally:
            _release_dc(hdc, created)
        # Falhou neste DC: tenta o proximo (fallback monitor -> tela).
        continue
    if not got_any_dc:
        pass
    return False


def is_gamma_supported(device: str | None = None) -> bool:
    """Testa leitura da rampa (HDR ativo faz o Windows ignorar Set...)."""
    return get_device_gamma_ramp(device) is not None


def win32_error_text(code: int) -> str:
    """Texto amigavel para os GetLastError() mais comuns no gamma."""
    table = {
        0: "sucesso",
        5: "acesso negado (ERROR_ACCESS_DENIED)",
        6: "handle invalido (ERROR_INVALID_HANDLE)",
        87: "parametro invalido (ERROR_INVALID_PARAMETER)",
        115: "recurso protegido / HDR ou driver bloqueou (ERROR_PROTECTION_FAILED)",
        116: "dispositivo inexistente (ERROR_INVALID_DEVICE)",
        142: "driver do monitor bloqueou a rampa (DWM/HDR?)",
        1008: "o driver nao suporta a rampa neste modo (ERROR_NO_TOKEN)",
    }
    if code in table:
        return table[code]
    try:
        buf = ctypes.create_unicode_buffer(256)
        n = ctypes.WinDLL("kernel32.dll", use_last_error=True).FormatMessageW(
            0x00001000 | 0x00000200 | 0x00000100, None, code, 0,
            buf, len(buf), None)
        if n:
            return buf.value.strip()
    except Exception:
        pass
    return f"codigo Win32 {code}"


def diagnose_gamma_failure(device: str | None = None) -> str:
    """Linha unica de diagnostico p/ UI e logs (HDR, DC, driver, Win32)."""
    parts: list[str] = []
    code = get_last_gamma_error()
    if code:
        parts.append(f"Win32={code} ({win32_error_text(code)})")
    # HDR real (nao mais o stub que sempre dizia False).
    try:
        from . import display_manager as _dm
        hdr = None
        for m in _dm.list_monitors():
            if device is None or m.get("device") == device:
                hdr = m.get("hdr")
                break
        if hdr:
            parts.append("HDR ATIVO — desligue p/ a rampa valer")
    except Exception:
        pass
    # Vendor do driver (dica AMD-especifica).
    try:
        from . import gpu_detector as _gd
        s = _gd.summarize()
        vendors = ",".join(s.get("vendors", []) or [s.get("vendor", "")])
        if vendors:
            parts.append(f"GPU={vendors}")
    except Exception:
        pass
    if device:
        parts.append(f"monitor={device}")
    return "; ".join(parts) if parts else "sem detalhe Win32 (tente o monitor primario)"


# ---------------------------------------------------------------- Interfaces / controllers

class IGammaController(ABC):
    @abstractmethod
    def apply(self, gamma: float, brightness: float, contrast: float,
              device: str | None = None) -> bool: ...
    @abstractmethod
    def restore(self, device: str | None = None) -> bool: ...
    @abstractmethod
    def backup_original(self, device: str | None = None) -> None: ...
    @property
    @abstractmethod
    def backend_name(self) -> str: ...


class WindowsGammaController(IGammaController):
    """Backend real: rampa de gamma do display (AMD / Intel / NVIDIA / integrado)."""

    def __init__(self):
        self._original: dict[str, list[int]] = {}

    @property
    def backend_name(self) -> str:
        return ("WindowsGamma (SetDeviceGammaRamp — AMD / Intel / NVIDIA / "
                "video integrado)")

    def backup_original(self, device: str | None = None) -> None:
        key = device or "default"
        if key not in self._original:
            ramp = get_device_gamma_ramp(device)
            if ramp is not None:
                self._original[key] = ramp

    def apply(self, gamma: float, brightness: float, contrast: float,
              device: str | None = None) -> bool:
        self.backup_original(device)
        return set_device_gamma_ramp(gamma, brightness, contrast, device)

    def restore(self, device: str | None = None) -> bool:
        key = device or "default"
        orig = self._original.get(key)
        if orig is not None:
            return set_raw_ramp(orig, device)
        # fallback: rampa identidade (gamma 1.0 / 50% / 50%)
        return set_device_gamma_ramp(1.0, 50.0, 50.0, device)

    def restore_all(self) -> None:
        for dev in list(self._original.keys()):
            d = None if dev == "default" else dev
            try:
                set_raw_ramp(self._original[dev], d)
            except Exception:
                pass

    @property
    def last_error(self) -> int:
        return get_last_gamma_error()

    def diagnose(self, device: str | None = None) -> str:
        return diagnose_gamma_failure(device)


class UniversalGammaController(IGammaController):
    """Controller vendor-agnostic (AMD / Intel / NVIDIA / sem GPU dedicada).

    A aplicacao real e sempre SetDeviceGammaRamp (GDI). A presenca de
    nvapi64.dll e apenas informativa — nunca bloqueia o uso.
    """

    def __init__(self):
        self._win = WindowsGammaController()
        self.nvapi_available = False
        self.nvapi_error = ""
        try:
            self._nvapi = ctypes.WinDLL("nvapi64.dll")
            self.nvapi_available = True
        except Exception as e:  # noqa: BLE001
            try:
                self._nvapi = ctypes.WinDLL("nvapi.dll")
                self.nvapi_available = True
            except Exception as e2:  # noqa: BLE001
                self.nvapi_error = str(e2)

    @property
    def backend_name(self) -> str:
        base = ("WindowsGamma (SetDeviceGammaRamp — AMD / Intel / NVIDIA / "
                "integrado)")
        if self.nvapi_available:
            return base + " + deteccao NVAPI"
        return base

    def backup_original(self, device=None) -> None:
        self._win.backup_original(device)

    def apply(self, gamma, brightness, contrast, device=None) -> bool:
        return self._win.apply(gamma, brightness, contrast, device)

    def restore(self, device=None) -> bool:
        return self._win.restore(device)

    def restore_all(self) -> None:
        self._win.restore_all()

    @property
    def last_error(self) -> int:
        return get_last_gamma_error()

    def diagnose(self, device=None) -> str:
        return diagnose_gamma_failure(device)


# Alias historico: mantido para compatibilidade com codigo/configs antigas.
class NvidiaGammaController(UniversalGammaController):
    """Alias de UniversalGammaController (era NVIDIA-only; hoje generico)."""

    def backup_original(self, device=None) -> None:
        self._win.backup_original(device)

    def apply(self, gamma, brightness, contrast, device=None) -> bool:
        return self._win.apply(gamma, brightness, contrast, device)

    def restore(self, device=None) -> bool:
        return self._win.restore(device)

    def restore_all(self) -> None:
        self._win.restore_all()
