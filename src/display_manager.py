"""Enumeracao de monitores / resolucao / refresh / HDR / monitor principal."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32.dll", use_last_error=True)


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128)]


class DEVMODEW(ctypes.Structure):
    _fields_ = [("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmPositionX", ctypes.c_long),
                ("dmPositionY", ctypes.c_long),
                ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", wintypes.SHORT),
                ("dmDuplex", wintypes.SHORT),
                ("dmYResolution", wintypes.SHORT),
                ("dmTTOption", wintypes.SHORT),
                ("dmCollate", wintypes.SHORT),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD),
                ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD),
                ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD),
                ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD),
                ("dmPanningHeight", wintypes.DWORD)]


# ---------------------------------------------------------------- Prototipos
# Sem argtypes o ctypes trunca ponteiros/structs em x64 e a enumeracao de
# monitores podia retornar nomes errados (DISPLAYx trocado) — o que virava
# um falso "monitor desconectado" ao aplicar o gamma no device errado.
try:
    user32.EnumDisplayDevicesW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL
    user32.EnumDisplaySettingsW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    user32.EnumDisplaySettingsW.restype = wintypes.BOOL
except Exception:
    pass


# ---------------------------------------------------------------- HDR real via DisplayConfig
# O stub antigo sempre retornava False, entao a UI dizia
# "Desligado/desconhecido" mesmo com HDR ligado — e HDR ligado e a causa
# #1 de SetDeviceGammaRamp falhar (Windows ignora a rampa em advanced
# color). Agora consultamos DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO,
# a API oficial, por monitor (\\.\DISPLAYx).

class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD),
                ("HighPart", wintypes.LONG)]


class _PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [("adapterId", _LUID),
                ("id", wintypes.UINT),
                ("modeInfoIdx", wintypes.UINT),
                ("statusFlags", wintypes.UINT)]


class _RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", wintypes.UINT),
                ("Denominator", wintypes.UINT)]


class _PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [("adapterId", _LUID),
                ("id", wintypes.UINT),
                ("modeInfoIdx", wintypes.UINT),
                ("outputTechnology", wintypes.UINT),
                ("rotation", wintypes.UINT),
                ("scaling", wintypes.UINT),
                ("refreshRate", _RATIONAL),
                ("scanLineOrdering", wintypes.UINT),
                ("targetAvailable", wintypes.BOOL),
                ("statusFlags", wintypes.UINT)]


class _PATH_INFO(ctypes.Structure):
    _fields_ = [("sourceInfo", _PATH_SOURCE_INFO),
                ("targetInfo", _PATH_TARGET_INFO),
                ("flags", wintypes.UINT)]


class _MODE_INFO(ctypes.Structure):
    # DISPLAYCONFIG_MODE_INFO tem 64 bytes (union interna); so precisamos do
    # tamanho correto para QueryDisplayConfig preencher o buffer.
    _fields_ = [("infoType", wintypes.UINT),
                ("id", wintypes.UINT),
                ("adapterId", _LUID),
                ("_pad", ctypes.c_ubyte * 48)]


class _DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int),
                ("size", wintypes.UINT),
                ("adapterId", _LUID),
                ("id", wintypes.UINT)]


class _ADVANCED_COLOR_INFO(ctypes.Structure):
    _fields_ = [("header", _DEVICE_INFO_HEADER),
                ("value", wintypes.UINT),  # bit0=supported bit1=enabled
                ("colorEncoding", wintypes.UINT),
                ("bitsPerColorChannel", wintypes.UINT)]


class _SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [("header", _DEVICE_INFO_HEADER),
                ("viewGdiDeviceName", wintypes.WCHAR * 32)]


_QDC_ONLY_ACTIVE_PATHS = 0x00000002
_DEVICE_INFO_GET_SOURCE_NAME = 1
# DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO (wingdi.h). Verificado
# empiricamente: -2 retorna ERROR_INVALID_PARAMETER (87); 9 funciona.
_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
_ERROR_SUCCESS = 0

_hdr_cache: dict = {"ts": 0.0, "map": {}}


def _query_hdr_map() -> dict:
    """Retorna {device_name: bool_hdr} via DisplayConfig; {} se indisponivel."""
    now = time.monotonic()
    try:
        if now - _hdr_cache["ts"] < 5.0:
            return dict(_hdr_cache["map"])
    except Exception:
        pass
    result: dict = {}
    try:
        u32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        u32.GetDisplayConfigBufferSizes.argtypes = [
            wintypes.UINT, ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT)]
        u32.GetDisplayConfigBufferSizes.restype = wintypes.LONG
        u32.QueryDisplayConfig.argtypes = [
            wintypes.UINT, ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(_PATH_INFO), ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(_MODE_INFO), ctypes.c_void_p]
        u32.QueryDisplayConfig.restype = wintypes.LONG
        u32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.c_void_p]
        u32.DisplayConfigGetDeviceInfo.restype = wintypes.LONG

        n_path = wintypes.UINT(0)
        n_mode = wintypes.UINT(0)
        rc = u32.GetDisplayConfigBufferSizes(
            _QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_path), ctypes.byref(n_mode))
        if rc != _ERROR_SUCCESS or not n_path.value:
            raise OSError(f"GetDisplayConfigBufferSizes rc={rc}")
        paths = (_PATH_INFO * n_path.value)()
        modes = (_MODE_INFO * n_mode.value)() if n_mode.value else None
        n_p, n_m = wintypes.UINT(n_path.value), wintypes.UINT(n_mode.value)
        rc = u32.QueryDisplayConfig(
            _QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_p), paths,
            ctypes.byref(n_m), modes, None)
        if rc != _ERROR_SUCCESS:
            raise OSError(f"QueryDisplayConfig rc={rc}")
        for i in range(n_p.value):
            p = paths[i]
            # Nome GDI (\\.\DISPLAYx) da fonte...
            name_pkt = _SOURCE_DEVICE_NAME()
            name_pkt.header.type = _DEVICE_INFO_GET_SOURCE_NAME
            name_pkt.header.size = ctypes.sizeof(_SOURCE_DEVICE_NAME)
            name_pkt.header.adapterId = p.sourceInfo.adapterId
            name_pkt.header.id = p.sourceInfo.id
            dev = ""
            if u32.DisplayConfigGetDeviceInfo(ctypes.byref(name_pkt)) == _ERROR_SUCCESS:
                dev = (name_pkt.viewGdiDeviceName or "").strip("\x00").strip()
            # ...e estado advanced-color do alvo.
            adv = _ADVANCED_COLOR_INFO()
            adv.header.type = _DEVICE_INFO_GET_ADVANCED_COLOR_INFO
            adv.header.size = ctypes.sizeof(_ADVANCED_COLOR_INFO)
            adv.header.adapterId = p.targetInfo.adapterId
            adv.header.id = p.targetInfo.id
            if u32.DisplayConfigGetDeviceInfo(ctypes.byref(adv)) == _ERROR_SUCCESS:
                enabled = bool(adv.value & 0x2)
                key = dev or f"adapter{p.targetInfo.id}"
                result[key] = enabled
    except Exception:
        return dict(_hdr_cache.get("map", {}))
    try:
        _hdr_cache["ts"] = now
        _hdr_cache["map"] = dict(result)
    except Exception:
        pass
    return result


def _hdr_enabled_for_device(device_name: str) -> bool:
    """True apenas quando o Windows confirma advanced-color ativo no monitor."""
    try:
        m = _query_hdr_map()
    except Exception:
        return False
    if not m:
        return False  # API indisponivel -> desconhecido (tratado como off)
    if device_name in m:
        return bool(m[device_name])
    # DISPLAY1 vs \\.\DISPLAY1: compara sufixo numerico como fallback.
    try:
        import re
        want = re.search(r"(\d+)\s*$", device_name or "")
        if want:
            for k, v in m.items():
                kk = re.search(r"(\d+)\s*$", k or "")
                if kk and kk.group(1) == want.group(1):
                    return bool(v)
    except Exception:
        pass
    # Um unico monitor ativo e o mapa nao trouxe nome: usa o valor unico.
    vals = list(m.values())
    if len(vals) == 1:
        return bool(vals[0])
    return False


def list_monitors() -> list[dict]:
    mons: list[dict] = []
    i = 0
    while True:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        i += 1
        # So dispositivos attached to desktop
        if not (dd.StateFlags & 0x1):  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
            continue
        name = dd.DeviceName  # \\.\DISPLAY1
        desc = dd.DeviceString
        is_primary = bool(dd.StateFlags & 0x4)
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        ok = user32.EnumDisplaySettingsW(name, 0xFFFFFFFF, ctypes.byref(dm))  # ENUM_CURRENT_SETTINGS
        if ok:
            res = f"{dm.dmPelsWidth} x {dm.dmPelsHeight}"
            refresh = int(dm.dmDisplayFrequency)
            bpp = int(dm.dmBitsPerPel)
            w, h = int(dm.dmPelsWidth), int(dm.dmPelsHeight)
        else:
            res, refresh, bpp, w, h = "?", 0, 0, 0, 0
        mons.append({
            "device": name,
            "label": f"{desc} ({name})" if desc else name,
            "description": desc,
            "primary": is_primary,
            "resolution": res,
            "width": w,
            "height": h,
            "refresh": refresh,
            "bpp": bpp,
            "hdr": _hdr_enabled_for_device(name),
        })
    if not mons:
        mons.append({"device": None, "label": "Monitor padrao",
                     "description": "", "primary": True, "resolution": "?",
                     "width": 0, "height": 0, "refresh": 0, "bpp": 0, "hdr": False})
    # primario primeiro
    mons.sort(key=lambda m: (not m["primary"], m["device"] or ""))
    return mons


def qt_screen_extra() -> list[dict]:
    """Complemento via Qt (chamado com QApplication ativo). Retorna [] se Qt ausente."""
    try:
        from PySide6.QtGui import QGuiApplication
        app = QGuiApplication.instance()
        if app is None:
            return []
        out = []
        for s in app.screens():
            g = s.geometry()
            out.append({"qt_name": s.name(), "model": s.model(),
                        "size": (g.width(), g.height()),
                        "refresh": s.refreshRate(),
                        "depth": s.depth()})
        return out
    except Exception:
        return []
