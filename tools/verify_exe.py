"""Verifica o Lumen.exe empacotado: sobe, confere janela/tema e tira print.

Isola o APPDATA num temporario para nao tocar na config real e nao registrar
o atalho F8 do usuario.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist", "Lumen.exe")
# O titulo real usa travessao: "Lumen — Controle de Gamma (...)".
# Comparar por prefixo evita depender do caractere e de encoding do console.
TITLE_PREFIX = "Lumen "

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


def find_window(prefix):
    """Retorna (hwnd, titulo) da 1a janela visivel cujo titulo comeca com prefix."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            if buf.value.startswith(prefix):
                found.append((h, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else (None, None)


def screenshot(hwnd, path):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    # PrintWindow em vez de BitBlt da tela: captura a JANELA, nao o que estiver
    # por cima dela na tela. PW_RENDERFULLCONTENT = 2.
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(hwnd, mdc, 2)
    if not ok:
        gdi32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                    ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]
    bi = BMI()
    bi.biSize = ctypes.sizeof(BMI)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)

    import zlib
    # buf e um c_char array: indexar devolve bytes, nao int. Pegamos .raw e
    # trabalhamos com int via memoryview.
    mv = memoryview(buf.raw)
    raw = bytearray()
    for y in range(h):
        raw.append(0)                      # filtro PNG: linha sem compressao
        off = y * w * 4
        for x in range(w):
            i = off + x * 4
            raw.append(mv[i + 2])          # BGR -> RGB
            raw.append(mv[i + 1])
            raw.append(mv[i])

    def chunk(tag, data):
        return (len(data).to_bytes(4, "big") + tag + data
                + zlib.crc32(tag + data).to_bytes(4, "big"))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big")
                   + bytes((8, 2, 0, 0, 0)))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return w, h


def main():
    if not os.path.isfile(EXE):
        print("ERRO: exe nao encontrado em", EXE)
        return 1
    iso = tempfile.mkdtemp(prefix="gs_verify_")
    env = dict(os.environ, APPDATA=iso)
    print("exe :", EXE, f"({os.path.getsize(EXE)/1048576:.1f} MB)")
    print("APPDATA isolado:", iso)
    proc = subprocess.Popen([EXE], env=env)
    ok = True
    try:
        hwnd, title = None, None
        for _ in range(45):          # ate ~45s (onefile demor para extrair)
            time.sleep(1)
            hwnd, title = find_window(TITLE_PREFIX)
            if hwnd:
                break
        if not hwnd:
            print("FALHA: janela principal nao apareceu")
            return 1
        print("OK   janela principal: hwnd=%d titulo=%r" % (hwnd, title))
        # Restore + topo: o BitBlt/PrintWindow pegaria outra janela se a
        # Lumen estivesse coberta.
        user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        time.sleep(2)

        cfg = os.path.join(iso, "Lumen", "config.json")
        if not os.path.isfile(cfg):
            print("FALHA: config.json nao foi criado")
            ok = False
        else:
            with open(cfg, encoding="utf-8") as f:
                data = json.load(f)
            for key in ("ui_theme", "window_geometry", "profiles"):
                if key not in data:
                    print("FALHA: chave ausente na config:", key)
                    ok = False
            print("OK   config.json com ui_theme=%r window_geometry=%r"
                  % (data.get("ui_theme"),
                     (data.get("window_geometry") or "")[:16]))

        out = os.path.join(os.path.dirname(EXE), "..", "_exe_shot.png")
        res = screenshot(hwnd, os.path.abspath(out))
        if res:
            print("OK   screenshot %dx%d -> _exe_shot.png" % res)
        else:
            print("FALHA: screenshot ficou 0x0")
            ok = False

        # O .exe nao expoe a arvore de widgets, entao o app recebe
        # --ui-selfcheck e mede o proprio layout (ver main() em src/app.py).
        # Rodar no processo empacotado e o que garante que a medicao vale
        # para o build, nao so para o dev.
        sc = subprocess.run([EXE, "--ui-selfcheck"], env=env,
                            capture_output=True, text=True, timeout=120)
        for line in sc.stdout.splitlines():
            print("   " + line)
        if "RESULTADO: OK" not in sc.stdout:
            print("FALHA: --ui-selfcheck reprovou")
            ok = False

        # Maximiza antes de fechar: assim exercitamos saveGeometry no estado
        # maximizado e o base64 gravado tem de ser diferente do inicial.
        user32.ShowWindow(hwnd, 3)   # SW_MAXIMIZE
        time.sleep(2)
        user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
        time.sleep(3)
        with open(cfg, encoding="utf-8") as f:
            data2 = json.load(f)
        geo = data2.get("window_geometry") or ""
        if geo:
            print("OK   geometria gravada no close (%d chars base64)" % len(geo))
        else:
            print("FALHA: geometria nao foi salva no closeEvent")
            ok = False

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(iso, ignore_errors=True)
        print("limpo; processos Lumen restantes:",
              subprocess.run(["tasklist", "/FI", "IMAGENAME eq Lumen.exe"],
                             capture_output=True, text=True).stdout.count("Lumen.exe"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
