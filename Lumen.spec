# -*- mode: python ; coding: utf-8 -*-
"""Lumen — spec otimizado para tamanho minimo.

Antes: collect_all('PySide6') puxava TUDO (QtWebEngine 193MB + 3D +
Multimedia + Pdf + Qml...), gerando ~235MB.
Agora: deixa o PyInstaller detectar so o usado (Core/Gui/Widgets) +
excludes agressivos + filtragem de DLLs/plugins/traducoes inuteis.
"""
try:
    from PyInstaller.building.datastruct import TOC
except ImportError:  # fallback p/ versoes antigas
    from PyInstaller.building.build import TOC

# Modulos Qt que o app NAO usa (app usa so Core/Gui/Widgets + sinais).
EXCLUDES = [
    # Web / docs
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebView",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    # 3D / graficos avancados
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.QtQuick3D",
    # QML / Quick
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.QtQuickTest",
    "PySide6.QtQmlCompiler",
    # Charts / dados
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    # Midia / sensores / hardware
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtLocation", "PySide6.QtPositioning",
    # SQL / rede pesada / outros
    "PySide6.QtSql", "PySide6.QtNetworkAuth", "PySide6.QtHttpServer",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech", "PySide6.QtAxContainer",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtHelp",
    "PySide6.QtPrintSupport", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtTest",
    "PySide6.QtConcurrent", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    # Stdlib nao usada pelo app (NOTA: NAO excluir 'email'/'http'/'json'/
    # 'urllib'/'logging' — urllib.request importa email e http.client;
    # excluir 'email' quebrava o exe com ModuleNotFoundError).
    "tkinter", "unittest",
    # NVML opcional (so existe em maquina NVIDIA; import e try/except)
    "pynvml", "nvidia",
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
)

# --- Filtra binarios inuteis que o hook do PySide6 puxa junto ---------------
_DROP_BIN = (
    "webengine", "qt6pdf", "qt63d", "qt6multimedia", "qt6location",
    "qt6positioning", "qt6sensors", "qt6serial", "qt6bluetooth", "qt6nfc",
    "qt6sql", "qt6charts", "qt6datavisualization", "qt6graphs",
    "qt6quick", "qt6qml", "qt6designer", "qt6help", "qt6svg",
    "qt6scxml", "qt6statemachine", "qt6texttospeech", "qt6axcontainer",
    "qt6remoteobjects", "qt6httpserver", "qt6networkauth",
    "avcodec", "avformat", "avutil", "swscale", "swresample",
    "opengl32sw.dll",
)
a.binaries = TOC([
    x for x in a.binaries
    if not any(d in x[0].lower() for d in _DROP_BIN)
])

# --- Filtra datas: plugins Qt e traducoes desnecessarios --------------------
def _keep_data(dest: str) -> bool:
    low = dest.replace("\\", "/").lower()
    # Fora do PySide6: mantem (ex.: assets)
    if "pyside6" not in low:
        return True
    # Traducoes: descarta tudo (app nao usa i18n do Qt)
    if "/translations/" in low or low.endswith(".qm"):
        return False
    # Locales do WebEngine
    if "qtwebengine_locales" in low:
        return False
    # QML / tipos
    if "/qml/" in low or low.endswith((".qml", ".qmlc", ".qmltypes")):
        return False
    # Plugins: mantem so o essencial p/ app Widgets
    if "/plugins/" in low:
        keep_dirs = ("/plugins/platforms/",
                     "/plugins/styles/",
                     "/plugins/imageformats/",
                     "/plugins/iconengines/",
                     "/plugins/tls/")
        if not any(k in low for k in keep_dirs):
            return False
        # em imageformats, mantem so ico/png/jpeg/gif
        if "/plugins/imageformats/" in low:
            return any(k in low for k in ("qico", "qpng", "qjpeg", "qgif"))
        return True
    return True


a.datas = TOC([x for x in a.datas if _keep_data(x[0])])

pyz = PYZ(a.pure, optimize=2)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Lumen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["qwindows.dll", "python3*.dll", "vcruntime*.dll"],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
