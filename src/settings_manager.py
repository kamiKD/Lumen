"""Persistencia em %APPDATA%/Lumen/config.json + logs. Escrita atomica."""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from copy import deepcopy

APP_NAME = "Lumen"

# Nome anterior do app. A pasta %APPDATA%/GammaSync e migrada para %APPDATA%/Lumen
# na primeira execucao, para nao perder os perfis/config do usuario no rename.
LEGACY_APP_NAME = "GammaSync"

DEFAULTS = {
    "version": 1,
    "gamma": 1.0,
    "brightness": 50.0,
    "contrast": 50.0,
    "monitor": None,          # device \\.\DISPLAY1 ou None=default
    "gpu": "",
    "keybind": "F8",
    "gamma_on": False,
    "restore_on_exit": True,
    "start_with_windows": False,
    "start_minimized": False,
    "active_profile": "Default",
    "ui_theme": "auto",            # auto | light | dark
    "window_geometry": "",         # base64 de QWidget.saveGeometry()
    "profiles": {
        "Default":  {"gamma": 1.0, "brightness": 50.0, "contrast": 50.0,
                     "monitor": None, "gpu": ""},
        "Gaming":   {"gamma": 1.8, "brightness": 55.0, "contrast": 60.0,
                     "monitor": None, "gpu": ""},
        "CS2":      {"gamma": 1.5, "brightness": 55.0, "contrast": 65.0,
                     "monitor": None, "gpu": ""},
        "Valorant": {"gamma": 1.4, "brightness": 52.0, "contrast": 62.0,
                     "monitor": None, "gpu": ""},
        "Minecraft":{"gamma": 1.6, "brightness": 55.0, "contrast": 58.0,
                     "monitor": None, "gpu": ""},
        "Dark":     {"gamma": 2.2, "brightness": 48.0, "contrast": 65.0,
                     "monitor": None, "gpu": ""},
        "Osu! EZ":  {"gamma": 0.5, "brightness": 50.0, "contrast": 50.0,
                     "monitor": None, "gpu": ""},
        "Osu! NM":  {"gamma": 1.0, "brightness": 50.0, "contrast": 50.0,
                     "monitor": None, "gpu": ""},
    },
}


def app_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    _migrate_legacy(base, d)
    return d


def _migrate_legacy(base: str, new_dir: str) -> None:
    """Copia %APPDATA%/GammaSync -> %APPDATA%/Lumen uma unica vez.

    Roda so quando o config novo ainda nao existe, entao um usuario que ja rodou
    a versao renomeada nunca e sobrescrito pelo conteudo antigo.
    """
    old = os.path.join(base, LEGACY_APP_NAME)
    if not os.path.isdir(old) or os.path.realpath(old) == os.path.realpath(new_dir):
        return
    if os.path.exists(os.path.join(new_dir, "config.json")):
        return
    try:
        for name in os.listdir(old):
            src = os.path.join(old, name)
            dst = os.path.join(new_dir, name)
            if os.path.exists(dst):
                continue
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    except OSError:
        pass  # migracao e melhor-esforco; falhar nao deve impedir o app de abrir


def log_dir() -> str:
    d = os.path.join(app_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(app_dir(), "config.json")


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("Lumen")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(os.path.join(log_dir(), "lumen.log"),
                                 encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    return logger


class SettingsManager:
    def __init__(self):
        self.log = setup_logging()
        self.data: dict = deepcopy(DEFAULTS)
        self.load()

    def load(self) -> dict:
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                raw = json.load(f)
            merged = deepcopy(DEFAULTS)
            merged.update(raw)
            # garante chaves de perfil validas
            if not isinstance(merged.get("profiles"), dict) or not merged["profiles"]:
                merged["profiles"] = deepcopy(DEFAULTS["profiles"])
            self.data = merged
        except FileNotFoundError:
            self.save()
        except Exception as e:  # noqa: BLE001
            self.log.warning("Falha ao ler config (%s); usando padrao.", e)
        return self.data

    def save(self) -> None:
        path = config_path()
        fd, tmp = tempfile.mkstemp(dir=app_dir(), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise

    # atalhos
    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, persist: bool = True):
        self.data[key] = value
        if persist:
            try:
                self.save()
            except Exception as e:  # noqa: BLE001
                self.log.warning("Falha ao salvar config: %s", e)
