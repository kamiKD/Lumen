"""Autostart via HKCU Run + flag ativa (crash-safety)."""
from __future__ import annotations

import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Lumen"


def _target() -> str:
    exe = sys.executable if getattr(sys, "frozen", False) else sys.executable
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    # modo dev: python main.py
    main = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    return f'"{exe}" "{main}" --minimized'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, VALUE)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, _target())
        else:
            try:
                winreg.DeleteValue(k, VALUE)
            except FileNotFoundError:
                pass


def active_flag_path() -> str:
    from .settings_manager import app_dir
    return os.path.join(app_dir(), "active.flag")


def write_active_flag(on: bool, profile: str = "") -> None:
    p = active_flag_path()
    try:
        if on:
            with open(p, "w", encoding="utf-8") as f:
                f.write(profile)
        else:
            if os.path.exists(p):
                os.remove(p)
    except OSError:
        pass


def read_active_flag() -> str | None:
    p = active_flag_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""
    return None
