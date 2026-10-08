"""Hotkey global via RegisterHotKey (eventos, sem polling -> CPU ~0%).

Correcao importante: RegisterHotKey(hWnd=NULL) associa o atalho a fila de
mensagens da thread que o registrou. Por isso o registro E o GetMessageW
precisam rodar na MESMA thread (a thread de pump). Versoes anteriores
registravam na thread principal e ouviam em outra -> o WM_HOTKEY nunca
chegava e o toggle parecia "nao funcionar".
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
HOTKEY_ID = 0xBEEF

VK_NAMES = {
    **{f"F{i}": 0x6F + i for i in range(1, 25)},
    **{c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PGUP": 0x21, "PGDN": 0x22, "UP": 0x26, "DOWN": 0x28,
    "LEFT": 0x25, "RIGHT": 0x27,
}


def parse_keybind(text: str) -> tuple[int, int]:
    """'CTRL+ALT+G' -> (modifiers, vk). Levanta ValueError se invalido."""
    parts = [p.strip().upper() for p in (text or "").split("+") if p.strip()]
    if not parts:
        raise ValueError("Keybind vazia.")
    mods = 0
    key = None
    for p in parts:
        if p in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif p == "ALT":
            mods |= MOD_ALT
        elif p == "SHIFT":
            mods |= MOD_SHIFT
        elif p in ("WIN", "WINDOWS", "META", "SUPER"):
            mods |= MOD_WIN
        else:
            if key is not None:
                raise ValueError(f"Tecla duplicada em '{text}'.")
            vk = VK_NAMES.get(p)
            if vk is None:
                # tenta letra/digito solto ou codigo tipo VK_XX
                if len(p) == 1:
                    vk = ord(p)
                else:
                    raise ValueError(f"Tecla desconhecida: {p}")
            key = vk
    if key is None:
        raise ValueError(f"Nenhuma tecla principal em '{text}'. Ex: F8, CTRL+ALT+G")
    return mods, key


def _vk_to_name() -> dict[int, str]:
    """Inverso de VK_NAMES com nomes canonicos (F8, A, SPACE, ESC...).

    A ordem importa: letras/digitos vencem F-keys, que vencem os nomes
    longos. Sem isso `normalize_keybind` devolvia `VK(0x20)` para SPACE e
    o atalho quebrava no arranque seguinte.
    """
    inv: dict[int, str] = {}
    for k, v in VK_NAMES.items():
        if len(k) == 1:
            inv.setdefault(v, k)
    for k, v in VK_NAMES.items():
        if k.startswith("F") and k[1:].isdigit():
            inv[v] = k
    for k, v in VK_NAMES.items():
        if len(k) > 1 and not (k.startswith("F") and k[1:].isdigit()):
            inv.setdefault(v, k)
    return inv


def normalize_keybind(text: str) -> str:
    mods, vk = parse_keybind(text)
    inv = _vk_to_name()
    order = []
    if mods & MOD_CONTROL:
        order.append("CTRL")
    if mods & MOD_ALT:
        order.append("ALT")
    if mods & MOD_SHIFT:
        order.append("SHIFT")
    if mods & MOD_WIN:
        order.append("WIN")
    name = inv.get(vk, f"VK({vk:#x})")
    order.append(name)
    return "+".join(order)


class HotkeyManager(QObject):
    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: threading.Thread | None = None
        self._pump_tid: int | None = None  # Win32 thread ID da pump (p/ WM_QUIT)
        self._stop = threading.Event()
        self._ready = threading.Event()  # pump sinaliza fim do registro
        self._error: str | None = None
        self._lock = threading.Lock()
        self.current = ""

    @property
    def registered(self) -> bool:
        th = self._thread
        return th is not None and th.is_alive() and self._error is None

    def _pump(self, mods: int, vk: int):
        # Roda na thread dedicada: registra AQUI para o WM_HOTKEY cair
        # nesta mesma fila de mensagens.
        self._pump_tid = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, HOTKEY_ID, mods, vk):
            err = ctypes.get_last_error()
            self._error = (
                f"Nao foi possivel registrar o atalho globalmente "
                f"(erro Win32 {err}). Outra aplicacao pode estar usando "
                f"a mesma tecla. Tente outra combinacao.")
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while not self._stop.is_set():
            # GetMessage bloqueia (sem polling) ate chegar mensagem
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:  # WM_QUIT / erro
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                try:
                    self.activated.emit()
                except RuntimeError:
                    pass  # app encerrando
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        try:
            user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            pass

    def start(self, keybind: str) -> str:
        """Registra (ou re-registra) o hotkey global. Retorna keybind normalizada."""
        norm = normalize_keybind(keybind)
        mods, vk = parse_keybind(norm)
        with self._lock:
            self._stop_locked()
            self._stop.clear()
            self._ready.clear()
            self._error = None
            self._pump_tid = None
            self._thread = threading.Thread(
                target=self._pump, args=(mods, vk),
                daemon=True, name="LumenHotkey")
            self._thread.start()
        # espera o registro concluir dentro da pump (fora do lock)
        if not self._ready.wait(timeout=5.0):
            self.stop()
            raise RuntimeError(
                f"Tempo esgotado ao registrar '{norm}'. Tente novamente.")
        if self._error:
            err = self._error
            self.stop()
            raise RuntimeError(f"'{norm}': {err}")
        self.current = norm
        return norm

    def _stop_locked(self):
        """Assume lock adquirido. Para a pump e libera a thread."""
        self._stop.set()
        tid = self._pump_tid
        th = self._thread
        self._thread = None
        self._pump_tid = None
        if tid:
            try:
                user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        if th is not None and th is not threading.current_thread():
            th.join(timeout=3.0)

    def stop(self):
        with self._lock:
            self._stop_locked()
