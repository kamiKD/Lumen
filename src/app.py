"""Janela principal Lumen (PySide6, leve, aplicacao em tempo real).

Estrutura da UI:
  header  — estado (chip) + toggle principal + monitor + HDR + diagnostico
  banner  — HDR ativo / falhas de gamma, com acao que resolve
  abas    — Gamma | Perfis | Opcoes
  status  — mensagens transitorias (substituem os "Perfil salvo." em modal)
"""
from __future__ import annotations

import argparse
import atexit
import sys

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSizePolicy, QStackedWidget, QStyle, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

from .settings_manager import SettingsManager
from .profile_manager import ProfileManager
from .gamma_controller import (
    UniversalGammaController, is_gamma_supported, diagnose_gamma_failure,
    get_last_gamma_error, win32_error_text,
)
from . import display_manager, gpu_detector, autostart, theme
from .ui import (
    Banner, Card, CardRow, Chip, DiagnosticsDialog, GammaCurve, KeyGrabDialog,
    LabeledSlider, NAV_ITEMS, NavRail, ProfileList,
)
# Alias legado: codigo externo ainda pode importar nvidia_controller.
from . import nvidia_controller  # noqa: F401

import os


class _NavTabsShim:
    """Fachada de `QTabWidget` sobre a pilha de paginas.

    A janela migrou de abas para navegacao lateral, mas os testes e o
    `--ui-selfcheck` consultam `tabs.count()`, `tabs.tabText(i)` e
    `tabs.setCurrentIndex(i)`. Esta classe mantem essa API funcionando sem
    duplicar estado: os indices sao os mesmos da ordem em `NAV_ITEMS`.
    """

    def __init__(self, pages: dict, stack):
        self._order = [t for t, _ in NAV_ITEMS]
        self._pages = pages
        self._stack = stack

    def count(self) -> int:
        return len(self._order)

    def tabText(self, index: int) -> str:
        return self._order[index]

    def currentIndex(self) -> int:
        page = self._stack.currentWidget()
        for i, title in enumerate(self._order):
            if self._pages.get(title) is page:
                return i
        return -1

    def setCurrentIndex(self, index: int) -> None:
        """Troca de pagina pela API de abas; a nav acompanha."""
        if 0 <= index < len(self._order):
            self._stack.setCurrentWidget(self._pages[self._order[index]])
            rail = getattr(self._stack, "_nav", None)
            if rail is not None:
                rail.select(self._order[index])

    def setCurrentIndex_by_title(self, title: str) -> None:
        if title in self._pages:
            self._stack.setCurrentWidget(self._pages[title])


def app_icon() -> QIcon:
    """Retorna o icone do Lumen (funciona em dev e no .exe PyInstaller)."""
    candidates = []
    try:
        # PyInstaller onefile/onedir: arquivos em sys._MEIPASS
        base = getattr(sys, "_MEIPASS", None)
        if base:
            candidates.append(os.path.join(base, "assets", "icon.png"))
            candidates.append(os.path.join(base, "assets", "icon.ico"))
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    candidates += [
        os.path.join(root, "assets", "icon.png"),
        os.path.join(root, "assets", "icon.ico"),
        os.path.join(here, "assets", "icon.png"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return QIcon(p)
    return QIcon()


def _err(parent, title: str, msg: str):
    QMessageBox.warning(parent, title, msg)


def _gamma_failure_details(dev) -> str:
    """Diagnostico curto p/ exibir junto ao erro (Win32 + HDR + GPU)."""
    try:
        d = diagnose_gamma_failure(dev)
        code = get_last_gamma_error()
        extra = f"Detalhe tecnico: {d}." if d else ""
        if code:
            try:
                extra += f" (GetLastError={code}: {win32_error_text(code)})"
            except Exception:
                extra += f" (GetLastError={code})"
        return extra
    except Exception:
        return ""


_AMD_FIX_HINT = (
    "Passos para AMD (causas mais comuns):\n"
    "1. Desligue o HDR no Windows (Configuracoes > Sistema > Tela > HDR) "
    "e no AMD Adrenalin.\n"
    "2. No Adrenalin (Monitor/Display): use 8 bpc, RGB 4:4:4 (Full) e "
    "desligue “10-Bit Pixel Format”.\n"
    "3. Desligue Vari-Bright (notebooks), Luz noturna e filtros "
    "(ReLive/overlay); feche jogos em tela cheia exclusiva.\n"
    "4. Atualize o driver AMD, reconecte o cabo e selecione o monitor "
    "PRIMARIO na lista.\n"
    "5. Troque HDR/driver e reabra o app antes de tentar de novo."
)


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager, minimized: bool = False):
        super().__init__()
        self.s = settings
        self.pm = ProfileManager(settings)
        self.gamma = UniversalGammaController()
        self.monitors: list[dict] = []
        self.nv = {"primary_name": "", "driver": "", "found": False,
                   "vendor": "", "label": ""}
        self.gpu_info = self.nv  # alias generico
        self._active_profile = str(self.s.get("active_profile", "Default") or "Default")
        self._tray_first_hide = True
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(30)
        self._apply_timer.timeout.connect(self._apply_live)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._hide_status)
        # Banner persistente (HDR) x banner de erro sao o mesmo widget; o
        # aviso de HDR sobe de novo quando o usuario arrasta um slider.
        self._banner_kind = "none"

        self.setWindowTitle("Lumen — Controle de Gamma (AMD / Intel / NVIDIA)")
        # A barra lateral de navegacao (196px) + sliders + curva precisa de
        # largura. Abaixo de 860 a curva invade os sliders, entao esse e o
        # piso em vez do antigo 720.
        self.setMinimumSize(880, 600)
        try:
            self.setWindowIcon(app_icon())
        except Exception:
            pass
        self._build_ui()
        self._restore_geometry()
        self._refresh_hardware()
        self._load_from_settings()
        self._setup_tray()
        self._setup_hotkey(initial=True)

        # crash-safety: se flag ativa de sessao anterior, restaura e avisa
        leftover = autostart.read_active_flag()
        if leftover is not None and leftover != "__clean__":
            # sessao anterior terminou com gamma ativo ou crash
            try:
                self.gamma.restore_all()
            except Exception:
                pass
            autostart.write_active_flag(False)
            self.s.log.warning("Flag ativa encontrada do arranque anterior; rampa restaurada.")

        # re-aplica se estava ON
        if self.s.get("gamma_on"):
            self._set_gamma_state(True, silent=True)

        atexit.register(self._on_exit)
        app = QGuiApplication.instance()
        try:
            app.screenAdded.connect(lambda *a: self._on_screens_changed())
            app.screenRemoved.connect(lambda *a: self._on_screens_changed())
        except Exception:
            pass
        if minimized or self.s.get("start_minimized"):
            QTimer.singleShot(0, self.hide)

    # ---------------------------------------------------------- UI: topo
    def _build_ui(self):
        c = QWidget()
        self.setCentralWidget(c)
        root = QVBoxLayout(c)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        self.banner = Banner()
        root.addWidget(self.banner)

        # Navegacao lateral no estilo Windows 11 + pilha de paginas.
        # Antes era um QTabWidget; as abas viraram itens da nav para casar
        # com o visual do sistema. `tabs` continua existindo como atalho
        # (os testes e o --ui-selfcheck usam `tabs.count()`/`tabText()`).
        split = QWidget()
        sh = QHBoxLayout(split)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(0)

        self.nav = NavRail(NAV_ITEMS)
        self.nav.changed.connect(self._on_nav_changed)
        sh.addWidget(self.nav)

        self.stack = QStackedWidget()
        sh.addWidget(self.stack, 1)
        self._pages: dict[str, QWidget] = {}
        for title, _sub in NAV_ITEMS:
            page = {
                "Gamma": self._build_tab_gamma,
                "Perfis": self._build_tab_profiles,
                "Opcoes": self._build_tab_options,
            }[title]()
            self._pages[title] = page
            self.stack.addWidget(page)
        root.addWidget(split, 1)

        # Fachada de abas sobre o stack, so para os testes/diagnostico.
        self.tabs = _NavTabsShim(self._pages, self.stack)
        # Ponteiro invertido para o setCurrentIndex conseguir mover a nav.
        self.stack._nav = self.nav

        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("statusBar")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.hide()
        root.addWidget(self.lbl_status)

    def _build_header(self):
        hdr = QFrame()
        hdr.setObjectName("header")
        h = QHBoxLayout(hdr)
        h.setContentsMargins(16, 10, 14, 10)
        h.setSpacing(10)
        # O monitor e o unico que cede espaco (elida); todo o resto e fixo.
        h.setStretch(0, 0)

        self.status_pill = Chip("● Gamma OFF", "off")
        self.status_pill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        h.addWidget(self.status_pill)

        self.btn_toggle = QPushButton("Ligar gamma")
        self.btn_toggle.setObjectName("heroToggle")
        self.btn_toggle.setCheckable(True)
        # Fixed/Minimum: e o botao principal e nunca pode ser cortado nem
        # elidado ("jar gamm" ja aconteceu com o header apertado).
        self.btn_toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_toggle.setMinimumWidth(self.btn_toggle.sizeHint().width())
        self.btn_toggle.setToolTip(
            "Liga/desliga a curva de gamma. Atalho global funciona minimizado.")
        self.btn_toggle.clicked.connect(self._on_toggle_btn)
        h.addWidget(self.btn_toggle)

        self.btn_reset = QPushButton("Restaurar")
        self.btn_reset.setToolTip("Volta a rampa original do monitor (gamma neutro).")
        self.btn_reset.clicked.connect(lambda: self._manual_set(False))
        h.addWidget(self.btn_reset)

        h.addStretch(1)

        self.cmb_monitor = QComboBox()
        # E o widget que deve ceder espaco: elida o nome do monitor em vez de
        # empurrar os botoes. Expanding + minimo curto = encolhe com elegancia.
        self.cmb_monitor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cmb_monitor.setMinimumWidth(110)
        self.cmb_monitor.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_monitor.setMinimumContentsLength(12)
        self.cmb_monitor.setToolTip("Monitor alvo para a curva de gamma.")
        self.cmb_monitor.currentIndexChanged.connect(self._on_monitor_changed)
        h.addWidget(self.cmb_monitor, 1)

        self.hdr_chip = Chip("HDR", "off")
        self.hdr_chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.hdr_chip.setToolTip("Estado do HDR no monitor selecionado.")
        h.addWidget(self.hdr_chip)
        # O chip muda de texto depois ("HDR desligado"). A largura e fixada em
        # _update_monitor_labels, ja com o stylesheet aplicado: medir antes do
        # polish daria um numero diferente do que o Qt usa de verdade.

        self.btn_diag = QPushButton("Diagnostico")
        self.btn_diag.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_diag.setToolTip("GPU, driver, monitores, resolucao e erro tecnico.")
        self.btn_diag.clicked.connect(self._open_diagnostics)
        h.addWidget(self.btn_diag)
        return hdr

    def _on_nav_changed(self, title: str) -> None:
        self.tabs.setCurrentIndex_by_title(title)

    # ------------------------------------------------------- UI: aba Gamma
    def _build_tab_gamma(self):
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(28, 24, 28, 24)
        h.setSpacing(20)

        # Sliders section (primary focus) — no GroupBox, clean rows
        sliders_widget = QWidget()
        v = QVBoxLayout(sliders_widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)
        # Alinha ao topo e nao centraliza: os tres sliders ficam agrupados
        # no alto, como no painel do Windows 11, em vez de flutuar no meio.
        v.setAlignment(Qt.AlignTop)
        self.sld_gamma = LabeledSlider("Gamma", 10, 500, "{}", parent=page)
        self.sld_bri = LabeledSlider("Brilho", 0, 100, "{}%", parent=page)
        self.sld_con = LabeledSlider("Contraste", 0, 100, "{}%", parent=page)
        for s in (self.sld_gamma, self.sld_bri, self.sld_con):
            s.valueChanged.connect(self._on_gamma_ui)
            s.editingFinished.connect(self._persist_current)
            v.addWidget(s)

        v.addSpacing(4)
        self.lbl_live = QLabel()
        self.lbl_live.setObjectName("subtitle")
        self.lbl_live.setWordWrap(True)
        v.addWidget(self.lbl_live)
        v.addStretch(1)
        sliders_widget.setMinimumWidth(300)
        h.addWidget(sliders_widget, 4)

        # Curve section (smaller, subtle)
        curve = QFrame()
        curve.setObjectName("curvePanel")
        # Card da curva, como os cards do Windows 11 (fundo + borda sutil).
        curve.setProperty("card", True)
        cv = QVBoxLayout(curve)
        cv.setContentsMargins(16, 14, 16, 14)
        cv.setSpacing(8)
        ttl = QLabel("Curva resultante")
        ttl.setObjectName("subtitle")
        self.gamma_curve = GammaCurve(curve)
        # O painel da curva fica com largura minima propria: sem isso ele
        # aceita encolher e invade a coluna dos sliders.
        curve.setMinimumWidth(230)
        self.gamma_curve.setToolTip(
            "Previa da curva de transferencia. O tracejado e a curva neutra "
            "(gamma 1.0). Abaixo da diagonal escurece as sombras; acima, clareia.")
        cv.addWidget(ttl)
        cv.addWidget(self.gamma_curve, 1)
        h.addWidget(curve, 2)
        return page

    # ------------------------------------------------------ UI: aba Perfis
    def _build_tab_profiles(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(10)

        self.profile_list = ProfileList(page)
        # Espaco extra embaixo: com 9 perfis o ultimo item ficava cortado
        # dentro da area rolavel.
        self.profile_list.setStyleSheet("QListWidget { padding-bottom: 10px; }")
        self.profile_list.currentItemChanged.connect(
            lambda cur, _prev: self._on_profile_selected(
                cur.data(Qt.UserRole) if cur else ""))
        self.profile_list.itemDoubleClicked.connect(
            lambda it: self._on_profile_selected(it.data(Qt.UserRole)))
        self.profile_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.profile_list.customContextMenuRequested.connect(self._profile_menu)
        v.addWidget(self.profile_list, 1)

        hint = QLabel("Duplo clique aplica. Clique direito: salvar, renomear, "
                      "duplicar, excluir. O asterisco marca alteracoes nao salvas.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_profile_save = QPushButton("Salvar")
        self.btn_profile_save.setProperty("variant", "primary")
        self.btn_profile_save.clicked.connect(self._on_profile_save)
        self.btn_profile_new = QPushButton("Novo")
        self.btn_profile_new.clicked.connect(self._on_profile_new)
        self.btn_profile_rename = QPushButton("Renomear")
        self.btn_profile_rename.clicked.connect(self._on_profile_rename)
        self.btn_profile_dup = QPushButton("Duplicar")
        self.btn_profile_dup.clicked.connect(self._on_profile_duplicate)
        self.btn_profile_del = QPushButton("Excluir")
        self.btn_profile_del.setProperty("variant", "danger")
        self.btn_profile_del.clicked.connect(self._on_profile_delete)
        for b in (self.btn_profile_save, self.btn_profile_new,
                  self.btn_profile_rename, self.btn_profile_dup,
                  self.btn_profile_del):
            row.addWidget(b)
        row.addStretch(1)
        self.lbl_profile_info = QLabel()
        self.lbl_profile_info.setObjectName("hint")
        row.addWidget(self.lbl_profile_info)
        v.addLayout(row)
        return page

    # ------------------------------------------------------ UI: aba Opcoes
    def _build_tab_options(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(18)

        # --- Card: atalho global (linha com campo + botoes, estilo Win11)
        card_key = Card("Atalho global")
        row_key = CardRow(
            "Alternar gamma",
            "Ex.: F8, CTRL+F8, ALT+F8, CTRL+ALT+G. Capturar aceita F1-F24, "
            "letras e numeros.")
        self.edt_key = QLineEdit()
        self.edt_key.setReadOnly(True)
        self.edt_key.setPlaceholderText("F8")
        self.edt_key.setFixedWidth(150)
        btn_cap = QPushButton("Capturar")
        btn_cap.setToolTip("Clique e pressione a combinacao desejada.")
        btn_cap.clicked.connect(self._on_keybind_capture)
        btn_key = QPushButton("Aplicar")
        btn_key.setProperty("variant", "primary")
        btn_key.clicked.connect(self._on_keybind_apply)
        for w in (self.edt_key, btn_cap, btn_key):
            row_key.add_control(w)
        card_key.add(row_key)
        v.addWidget(card_key)

        # --- Card: opcoes de inicializacao (uma linha por checkbox)
        card_start = Card("Inicializacao")
        # O texto vem do CardRow (titulo da linha); o QCheckBox fica sem
        # label para nao repetir a mesma frase duas vezes.
        self.chk_restore = QCheckBox()
        self.chk_restore.toggled.connect(lambda v: self.s.set("restore_on_exit", v))
        card_start.add(CardRow(
            "Restaurar o gamma original ao sair",
            "Volta a rampa neutra do monitor ao fechar o app.", self.chk_restore))

        self.chk_autostart = QCheckBox()
        self.chk_autostart.toggled.connect(self._on_autostart)
        card_start.add(CardRow(
            "Iniciar com o Windows",
            "Adiciona o Lumen na inicializacao automatica (HKCU Run).",
            self.chk_autostart))

        self.chk_min = QCheckBox()
        self.chk_min.toggled.connect(lambda v: self.s.set("start_minimized", v))
        card_start.add(CardRow(
            "Iniciar minimizado",
            "Abre direto na bandeja, sem mostrar a janela.", self.chk_min))
        v.addWidget(card_start)

        # --- Card: tema
        card_theme = Card("Aparencia")
        self.cmb_theme = QComboBox()
        self.cmb_theme.setFixedWidth(210)
        for key, label in (("auto", "Automatico (seguir o Windows)"),
                           ("light", "Claro"), ("dark", "Escuro")):
            self.cmb_theme.addItem(label, key)
        i = self.cmb_theme.findData(str(self.s.get("ui_theme", "auto")))
        self.cmb_theme.setCurrentIndex(i if i >= 0 else 0)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        card_theme.add(CardRow(
            "Tema",
            "Automatico acompanha a configuracao de cor do Windows.",
            self.cmb_theme))
        v.addWidget(card_theme)

        v.addStretch(1)
        return page

    # ---------------------------------------------------------- geometria
    def _restore_geometry(self):
        raw = self.s.get("window_geometry")
        if raw:
            try:
                data = QByteArray.fromBase64(str(raw).encode("ascii"))
                if not data.isEmpty() and self.restoreGeometry(data):
                    return
            except Exception:
                self.s.log.warning("Geometria da janela invalida; recentrando.")
        self._center()

    def _center(self):
        scr = QApplication.primaryScreen()
        if scr is None:
            return
        self.resize(1000, 680)
        g = self.geometry()
        g.moveCenter(scr.availableGeometry().center())
        self.setGeometry(g)

    def _save_geometry(self):
        try:
            self.s.set("window_geometry",
                       bytes(self.saveGeometry().toBase64()).decode("ascii"))
        except Exception:
            pass

    def _on_theme_changed(self, _idx):
        pref = self.cmb_theme.currentData() or "auto"
        self.s.set("ui_theme", pref)
        theme.apply_theme(QApplication.instance(), pref)

    # ----------------------------------------------------- status transitorio
    def _flash(self, text: str, kind: str = "info", ms: int = 3200):
        self.lbl_status.setText(text)
        self.lbl_status.setProperty("kind", kind)
        theme.repolish(self.lbl_status)
        self.lbl_status.show()
        self._status_timer.start(ms)

    def _hide_status(self):
        self.lbl_status.hide()

    # ---------------------------------------------------------- banner
    def _set_banner(self, severity: str, title: str, body: str = "",
                    action_text: str = "", action=None, details: str = ""):
        self._banner_kind = severity
        self.banner.show_message(severity, title, body, action_text, action,
                                 details)

    def _clear_banner(self):
        self._banner_kind = "none"
        self.banner.clear_message()

    def _open_hdr_settings(self):
        QDesktopServices.openUrl(QUrl("ms-settings:display"))

    def _show_gamma_error(self, title: str, dev):
        """Falha de gamma: causa provavel na faixa, detalhe tecnico escondido."""
        det = _gamma_failure_details(dev)
        self.s.log.warning("%s: %s", title, det)
        self._set_banner(
            "error", title,
            "Causas comuns: HDR ativo, 10-Bit Pixel Format (AMD), cabo/monitor "
            "ou driver de video.",
            "Como resolver",
            self._open_gamma_help,
            det,
        )

    def _open_gamma_help(self):
        QMessageBox.information(
            self, "Como resolver",
            "1. Desligue o HDR (Configuracoes > Sistema > Tela > HDR) e no "
            "painel do fabricante.\n"
            "2. AMD: 8 bpc, RGB 4:4:4 (Full), sem “10-Bit Pixel Format”, "
            "sem Vari-Bright nem Luz noturna.\n"
            "3. Feche overlays e jogos em tela cheia exclusiva.\n"
            "4. Atualize o driver, reconecte o cabo e escolha o monitor "
            "PRIMARIO na lista.\n"
            "5. Troque HDR/driver e reabra o app antes de tentar de novo.\n\n"
            "Depois, abra a aba Diagnostico para ver o erro tecnico exato.")

    # ---------------------------------------------------------- UI: dados
    def _refresh_hardware(self):
        # Deteccao vendor-agnostic: AMD, Intel, NVIDIA, video integrado ou
        # driver basico. Ausencia de GPU dedicada NAO bloqueia o uso:
        # SetDeviceGammaRamp funciona em qualquer cenario com monitor.
        self.nv = gpu_detector.summarize()
        self.gpu_info = self.nv
        self.monitors = display_manager.list_monitors()
        cur = self.cmb_monitor.currentData()
        self.cmb_monitor.blockSignals(True)
        self.cmb_monitor.clear()
        for m in self.monitors:
            # Nome curto + completo: o combo elida o curto quando aperta e o
            # tooltip mostra a descricao real do monitor.
            name = m["description"] or m["label"]
            self.cmb_monitor.addItem(name, m["device"])
            idx = self.cmb_monitor.count() - 1
            full = m["label"]
            extra = f"{m.get('resolution', '?')} @ {m.get('refresh', 0)} Hz"
            self.cmb_monitor.setItemData(idx, f"{full}\n{extra}",
                                         Qt.ToolTipRole)
        # restaura selecao
        sel = self.s.get("monitor")
        idx = self.cmb_monitor.findData(sel)
        self.cmb_monitor.setCurrentIndex(idx if idx >= 0 else 0)
        if cur and self.cmb_monitor.findData(cur) >= 0 and not sel:
            self.cmb_monitor.setCurrentIndex(self.cmb_monitor.findData(cur))
        self.cmb_monitor.blockSignals(False)
        self._update_monitor_labels()
        # gpu padrao
        if self.nv.get("primary_name") and not self.s.get("gpu"):
            self.s.set("gpu", self.nv["primary_name"])

    def _update_monitor_labels(self):
        """Atualiza o chip de HDR e o banner persistente (rotulos antes fixos)."""
        m = self._current_monitor()
        if not m:
            self.hdr_chip.set_state("off", "HDR ?")
            return
        hdr = bool(m.get("hdr"))
        self.hdr_chip.set_state("warn" if hdr else "off",
                                "HDR ligado" if hdr else "HDR desligado")
        # Reserva a largura do texto real para o cabecalho nao refluir e o
        # chip nunca sair elidado.
        self.hdr_chip.setFixedWidth(self.hdr_chip.sizeHint().width())
        if hdr and self._banner_kind in ("none", "warn"):
            self._set_banner(
                "warn",
                "HDR ativo — o Windows ignora a curva de gamma",
                "Com HDR ligado o SetDeviceGammaRamp e ignorado pelo sistema. "
                "Desligue o HDR para o Lumen ter efeito.",
                "Abrir configuracoes de tela",
                self._open_hdr_settings,
            )
        elif not hdr and self._banner_kind == "warn":
            self._clear_banner()

    def _current_monitor(self) -> dict | None:
        dev = self.cmb_monitor.currentData()
        for m in self.monitors:
            if m["device"] == dev:
                return m
        return self.monitors[0] if self.monitors else None

    def _current_device(self):
        return self.cmb_monitor.currentData()

    def _monitor_label(self, device) -> str:
        if not device:
            return "qualquer monitor"
        for m in self.monitors:
            if m["device"] == device:
                return m["label"]
        return str(device)

    def _diagnostic_rows(self) -> list[tuple[str, str]]:
        nv = self.nv
        m = self._current_monitor()
        rows = [
            ("GPU", nv.get("label") or "?"),
            ("Fabricante", nv.get("vendor") or "?"),
            ("Driver", nv.get("driver") or "?"),
            ("GPU dedicada", "sim" if nv.get("found")
             else "nao (video integrado / driver basico — gamma funciona)"),
            ("Backend", self.gamma.backend_name),
            ("Gamma suportado", "sim" if is_gamma_supported(self._current_device())
             else "nao (HDR ativo, monitor desconectado ou driver)"),
            ("Ultimo erro Win32", self._last_error_text()),
        ]
        for mon in self.monitors:
            hdr = "HDR ligado" if mon.get("hdr") else "HDR desligado"
            prim = " (primario)" if mon.get("primary") else ""
            rows.append((mon["label"],
                         f"{mon.get('resolution', '?')} @ "
                         f"{mon.get('refresh', 0)} Hz, "
                         f"{mon.get('bpp', 0)} bpp, {hdr}{prim}"))
        extra = display_manager.qt_screen_extra()
        for e in extra:
            g = e["size"]
            rows.append((f"Qt: {e.get('qt_name', '?')}",
                         f"{e.get('model', '')} {g[0]}x{g[1]} @ "
                         f"{e.get('refresh', 0)} Hz, {e.get('depth', 0)} bits"))
        if m is not None:
            rows.append(("Atalho", self.s.get("keybind", "F8")))
            rows.append(("Config", os.path.join(
                os.getenv("APPDATA") or "", "Lumen", "config.json")))
        return rows

    def _last_error_text(self) -> str:
        code = get_last_gamma_error()
        if not code:
            return "nenhum"
        try:
            return f"{code} ({win32_error_text(code)})"
        except Exception:
            return str(code)

    def _check_header_fits(self) -> list[str]:
        """Widgets do cabecalho cujo texto nao cabe (seriam elidados).

        Roda em dev e no .exe empacotado: foi no build que 'Ligar gamma'
        apareceu como 'jar gamm' e 'HDR desligado' como 'HDR desligadc'.
        """
        bad = []
        for name, wid, need in _header_measurements(self):
            if need > wid:
                bad.append(f"{name}: texto {need}px > widget {wid}px")
        return bad

    def _open_diagnostics(self):
        from . import settings_manager
        dlg = DiagnosticsDialog(self._diagnostic_rows(),
                                settings_manager.log_dir(), self)
        dlg.exec()

    def _load_from_settings(self):
        self.sld_gamma.setValue(int(round(float(self.s.get("gamma", 1.0)) * 100)))
        self.sld_bri.setValue(int(round(float(self.s.get("brightness", 50.0)))))
        self.sld_con.setValue(int(round(float(self.s.get("contrast", 50.0)))))
        self.edt_key.setText(self.s.get("keybind", "F8"))
        for w, key, default in (
            (self.chk_restore, "restore_on_exit", True),
            (self.chk_autostart, "start_with_windows", False),
            (self.chk_min, "start_minimized", False),
        ):
            w.blockSignals(True)
            w.setChecked(bool(self.s.get(key, default)))
            w.blockSignals(False)
        self._reload_profiles()
        self._update_gamma_preview()
        self._update_status_ui()

    def _reload_profiles(self):
        g, b, c = self._ui_values()
        cur = self._current_device()
        entries = []
        for name in self.pm.names():
            p = self.pm.get(name) or {}
            entries.append({
                "name": name,
                "values": self._profile_summary(p, name, g, b, c, cur),
                "dirty": self._profile_dirty(p, g, b, c, cur),
            })
        self.profile_list.populate(entries, self._active_profile)
        self._update_dirty()

    def _profile_summary(self, p: dict, name: str, g, b, c, cur) -> str:
        mon = p.get("monitor")
        mon_txt = "todos" if not mon else self._monitor_label(mon)
        return (f"gamma {float(p.get('gamma', 1.0)):.2f}   "
                f"brilho {float(p.get('brightness', 50.0)):.0f}%   "
                f"contraste {float(p.get('contrast', 50.0)):.0f}%   "
                f"· {mon_txt}")

    def _profile_dirty(self, p: dict, g, b, c, cur) -> bool:
        if not p:
            return False
        dirty = (abs(float(p.get("gamma", 1.0)) - g) > 1e-6
                 or abs(float(p.get("brightness", 50.0)) - b) > 1e-6
                 or abs(float(p.get("contrast", 50.0)) - c) > 1e-6)
        # Perfil salvo em "qualquer monitor" (None) e coringa: trocar de
        # monitor na hora de aplicar nao deve marcar o perfil como sujo.
        mon = p.get("monitor") or None
        return dirty or (mon is not None and mon != (cur or None))

    # ---------------------------------------------------------- gamma
    def _ui_values(self):
        return (self.sld_gamma.value() / 100.0,
                float(self.sld_bri.value()),
                float(self.sld_con.value()))

    def _on_gamma_ui(self, *_a):
        self._update_gamma_preview()
        # aplica em tempo real se ligado (debounce curto p/ nao piscar)
        if self.btn_toggle.isChecked():
            if not self._apply_timer.isActive():
                self._apply_timer.start()
        self._update_dirty()

    def _update_gamma_preview(self):
        g, b, c = self._ui_values()
        self.gamma_curve.set_values(g, b, c)

    def _apply_live(self):
        g, b, c = self._ui_values()
        dev = self._current_device()
        ok = self.gamma.apply(g, b, c, dev)
        if not ok:
            det = _gamma_failure_details(dev)
            try:
                self.s.log.warning("Falha ao aplicar gamma: %s", det)
            except Exception:
                pass
            self._set_banner(
                "error",
                "Nao foi possivel aplicar a curva neste monitor",
                "Ajuste o HDR, o formato de cor ou reconecte o cabo.",
                "Como resolver",
                self._open_gamma_help,
                det,
            )
        elif self._banner_kind == "error":
            self._clear_banner()
        self.s.set("gamma", g, persist=False)
        self.s.set("brightness", b, persist=False)
        self.s.set("contrast", c, persist=False)
        self.s.set("monitor", dev, persist=False)
        self.s.save()

    def _persist_current(self):
        g, b, c = self._ui_values()
        self.s.set("gamma", g, persist=False)
        self.s.set("brightness", b, persist=False)
        self.s.set("contrast", c, persist=False)
        self.s.set("monitor", self._current_device(), persist=False)
        self.s.save()

    def _set_gamma_state(self, on: bool, silent: bool = False) -> bool:
        """Aplica/restaura o gamma. SEMPRE termina com a UI em sintonia com o
        que foi realmente feito — inclusive no caminho de falha, onde antes o
        botao ficava dessincronizado da rampa."""
        dev = self._current_device()
        if on:
            g, b, c = self._ui_values()
            if not is_gamma_supported(dev) and not silent:
                self._show_gamma_error("Gamma nao suportado neste monitor", dev)
                on = False
            if on and not self.gamma.apply(g, b, c, dev):
                if not silent:
                    self._show_gamma_error("Falha ao aplicar o gamma", dev)
                on = False
            if on:
                autostart.write_active_flag(True, self.active_profile)
        else:
            ok = self.gamma.restore(dev)
            if not ok and not silent:
                self.s.log.warning("Falha ao restaurar a rampa original.")
                self._set_banner(
                    "error", "Falha ao restaurar a rampa original",
                    "Tente ligar e desligar o gamma novamente.",
                    details=_gamma_failure_details(dev),
                )
            autostart.write_active_flag(False)

        # ponto unico de verdade da UI, para qualquer caminho de saida
        self.btn_toggle.setChecked(on)
        self.s.set("gamma_on", on)
        self.s.save()
        self._update_status_ui()
        self._update_tray()
        return on

    def _on_manual_toggle(self):
        self._set_gamma_state(not self.btn_toggle.isChecked())

    def _manual_set(self, on: bool):
        self._set_gamma_state(on)

    def _on_toggle_btn(self, checked: bool):
        # O botao e checkable e o Qt ja o inverteu; _set_gamma_state reescreve
        # o estado ao final, entao nao ha mais o dance de setChecked aqui.
        self._manual_set(checked)

    def _update_status_ui(self):
        on = self.btn_toggle.isChecked()
        self.btn_toggle.setText("Desligar gamma" if on else "Ligar gamma")
        self.status_pill.set_state("on" if on else "off",
                                   "● Gamma ON" if on else "○ Gamma OFF")
        if on:
            self.lbl_live.setText(
                "Aplicacao em tempo real: as mudancas ja entram na tela.")
        else:
            self.lbl_live.setText(
                "Gamma desligado — os valores ficam salvos, mas so entram na "
                "tela ao ligar o Gamma.")
        # sliders seguem editaveis com o gamma OFF (da para pre-configurar),
        # mas o estado do toggle precisa ficar evidente na propria aba.
        self.btn_toggle.setProperty("state", "on" if on else "off")
        theme.repolish(self.btn_toggle)

    def _on_monitor_changed(self):
        self._update_monitor_labels()
        self.s.set("monitor", self._current_device())
        self._update_dirty()
        # se ligado, aplica no novo monitor imediatamente
        if self.btn_toggle.isChecked():
            self._apply_live()

    def _on_screens_changed(self):
        self._refresh_hardware()
        if self.btn_toggle.isChecked():
            # reaplica apos troca de resolucao/monitor
            QTimer.singleShot(500, self._apply_live)

    # ---------------------------------------------------------- hotkey
    def _setup_hotkey(self, initial=False):
        from .hotkey_manager import HotkeyManager
        if not hasattr(self, "hk"):
            self.hk = HotkeyManager(self)
            self.hk.activated.connect(self._on_manual_toggle)
        try:
            norm = self.hk.start(self.s.get("keybind", "F8"))
            self.s.set("keybind", norm, persist=False)
            self.edt_key.setText(norm)
        except Exception as e:  # noqa: BLE001
            if not initial:
                self._show_hotkey_error(str(e))
            self.s.log.warning("Hotkey falhou: %s", e)

    def _show_hotkey_error(self, msg: str):
        self._set_banner("error", "Atalho global indisponivel", msg,
                         action_text="Recapturar",
                         action=self._on_keybind_capture)

    def _on_keybind_capture(self):
        dlg = KeyGrabDialog(self.edt_key.text(), self)
        if dlg.exec() != KeyGrabDialog.Accepted or not dlg.result_key:
            return
        self.edt_key.setText(dlg.result_key)
        self._register_keybind(dlg.result_key)

    def _on_keybind_apply(self):
        self._register_keybind(self.edt_key.text().strip())

    def _register_keybind(self, txt: str) -> bool:
        from .hotkey_manager import normalize_keybind
        try:
            norm = normalize_keybind(txt)
        except ValueError as e:
            self._show_hotkey_error(
                f"{e} Exemplos: F8, CTRL+F8, ALT+F8, SHIFT+F8, CTRL+ALT+G")
            return False
        try:
            self.hk.start(norm)
        except Exception as e:  # noqa: BLE001
            self._show_hotkey_error(str(e))
            return False
        self.edt_key.setText(norm)
        self.s.set("keybind", norm)
        if self._banner_kind == "error":
            self._clear_banner()
        self._flash(f"Atalho global definido: {norm}", "ok")
        return True

    # ---------------------------------------------------------- perfis
    @property
    def active_profile(self) -> str:
        return self._active_profile

    def _set_active_profile(self, name: str):
        self._active_profile = name or "Default"
        self.s.set("active_profile", self._active_profile, persist=False)
        if self.profile_list.current_name() != self._active_profile:
            self.profile_list.blockSignals(True)
            self.profile_list.select_name(self._active_profile)
            self.profile_list.blockSignals(False)

    def _update_dirty(self):
        p = self.pm.get(self._active_profile) or {}
        g, b, c = self._ui_values()
        dirty = self._profile_dirty(p, g, b, c, self._current_device())
        self.btn_profile_save.setEnabled(dirty)
        self.lbl_profile_info.setText(
            "alteracoes nao salvas" if dirty else f"perfil '{self._active_profile}' salvo")
        if self.active_profile:
            self.profile_list.refresh_item(
                self._active_profile,
                self._profile_summary(p, self._active_profile, g, b, c,
                                      self._current_device()),
                dirty)

    def _on_profile_selected(self, name: str):
        if not name:
            return
        p = self.pm.get(name)
        if not p:
            return
        self._set_active_profile(name)
        self.sld_gamma.setValue(int(round(float(p.get("gamma", 1.0)) * 100)))
        self.sld_bri.setValue(int(round(float(p.get("brightness", 50.0)))))
        self.sld_con.setValue(int(round(float(p.get("contrast", 50.0)))))
        mon = p.get("monitor")
        if mon:
            i = self.cmb_monitor.findData(mon)
            if i >= 0:
                self.cmb_monitor.setCurrentIndex(i)
        self.s.save()
        if self.btn_toggle.isChecked():
            self._apply_live()
        self._update_gamma_preview()
        self._update_dirty()
        self._update_tray()

    def _profile_menu(self, pos):
        it = self.profile_list.itemAt(pos)
        if it is None:
            return
        name = it.data(Qt.UserRole)
        menu = QMenu(self)
        acts = {
            "Aplicar": lambda: self._on_profile_selected(name),
            "Salvar valores atuais": self._on_profile_save,
            "Renomear...": self._on_profile_rename,
            "Duplicar": self._on_profile_duplicate,
        }
        for txt, fn in acts.items():
            a = QAction(txt, self)
            a.triggered.connect(fn)
            menu.addAction(a)
        menu.addSeparator()
        a_del = QAction("Excluir", self)
        a_del.triggered.connect(self._on_profile_delete)
        menu.addAction(a_del)
        menu.exec(self.profile_list.viewport().mapToGlobal(pos))

    def _on_profile_save(self):
        name = self.active_profile
        if not name:
            return
        g, b, c = self._ui_values()
        self.pm.snapshot_current(name, g, b, c, self._current_device(),
                                 self.nv.get("primary_name", ""))
        self.s.set("active_profile", name)
        self._reload_profiles()
        self._update_tray()
        self._flash(f"Perfil '{name}' salvo.", "ok")

    def _on_profile_new(self):
        name, ok = QInputDialog.getText(self, "Novo perfil", "Nome:")
        if not (ok and name.strip()):
            return
        try:
            g, b, c = self._ui_values()
            self.pm.create(name.strip(),
                           {"gamma": g, "brightness": b, "contrast": c,
                            "monitor": self._current_device(),
                            "gpu": self.nv.get("primary_name", "")})
            self.s.set("active_profile", name.strip())
            self._reload_profiles()
            self._set_active_profile(name.strip())
            self._update_tray()
            self._flash(f"Perfil '{name.strip()}' criado.", "ok")
        except ValueError as e:
            _err(self, "Perfil", str(e))

    def _on_profile_rename(self):
        old = self.active_profile
        if not old:
            return
        name, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=old)
        if not (ok and name.strip()):
            return
        try:
            self.pm.rename(old, name.strip())
            self._set_active_profile(name.strip())
            self._reload_profiles()
        except ValueError as e:
            _err(self, "Perfil", str(e))

    def _on_profile_duplicate(self):
        old = self.active_profile
        if not old:
            return
        try:
            new = self.pm.duplicate(old)
            self.s.set("active_profile", new)
            self._reload_profiles()
            self._set_active_profile(new)
            self._update_tray()
            self._flash(f"Perfil '{new}' criado a partir de '{old}'.", "ok")
        except (KeyError, ValueError) as e:
            _err(self, "Perfil", str(e))

    def _on_profile_delete(self):
        old = self.active_profile
        if not old:
            return
        if QMessageBox.question(self, "Excluir", f"Excluir o perfil '{old}'?") \
                != QMessageBox.Yes:
            return
        try:
            self.pm.delete(old)
            self._active_profile = str(self.s.get("active_profile", "Default"))
            self._reload_profiles()
            self._set_active_profile(self._active_profile)
            self._update_dirty()
            self._update_tray()
            self._flash(f"Perfil '{old}' excluido.", "ok")
        except ValueError as e:
            _err(self, "Perfil", str(e))

    # ---------------------------------------------------------- opcoes/tray
    def _on_autostart(self, on: bool):
        try:
            autostart.set_enabled(on)
            self.s.set("start_with_windows", on)
        except Exception as e:  # noqa: BLE001
            _err(self, "Inicializacao", f"Permissao insuficiente: {e}")
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(not on)
            self.chk_autostart.blockSignals(False)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # mesmo sem bandeja, define o icone da janela
            self.setWindowIcon(app_icon())
            return
        self.tray = QSystemTrayIcon(self)
        icon = app_icon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.setWindowIcon(icon)
        menu = QMenu()
        self.act_on = QAction("Gamma ON", self, checkable=True)
        self.act_off = QAction("Gamma OFF", self, checkable=True)
        self.act_on.triggered.connect(lambda: self._manual_set(True))
        self.act_off.triggered.connect(lambda: self._manual_set(False))
        menu.addAction(self.act_on)
        menu.addAction(self.act_off)
        menu.addSeparator()
        self.menu_profiles = QMenu("Perfis", menu)
        menu.addMenu(self.menu_profiles)
        act_toggle = QAction("Toggle Gamma", self)
        act_toggle.triggered.connect(self._on_manual_toggle)
        menu.addAction(act_toggle)
        menu.addSeparator()
        act_open = QAction("Abrir aplicativo", self)
        act_open.triggered.connect(self._show_window)
        menu.addAction(act_open)
        act_quit = QAction("Sair", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._update_tray()

    def _update_tray(self):
        if not hasattr(self, "tray"):
            return
        on = self.btn_toggle.isChecked()
        try:
            self.act_on.setChecked(on)
            self.act_off.setChecked(not on)
            self.tray.setToolTip(
                f"Lumen — Gamma {'ON' if on else 'OFF'}"
                + (f" · {self.active_profile}" if self.active_profile else ""))
            self.menu_profiles.clear()
            for name in self.pm.names():
                a = QAction(name, self, checkable=True)
                a.setChecked(name == self.active_profile)
                a.triggered.connect(
                    lambda _c=False, n=name: self._on_profile_selected(n))
                self.menu_profiles.addAction(a)
        except RuntimeError:
            pass

    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def closeEvent(self, ev):
        self._save_geometry()
        # minimizar p/ bandeja em vez de sair
        ev.ignore()
        self.hide()
        if self._tray_first_hide and hasattr(self, "tray"):
            self.tray.showMessage("Lumen",
                                  "Minimizado para a bandeja. Use Sair para encerrar.",
                                  QSystemTrayIcon.Information, 3000)
            self._tray_first_hide = False

    def _quit_app(self):
        self._save_geometry()
        QApplication.instance().quit()

    def _on_exit(self):
        try:
            self.hk.stop()
        except Exception:
            pass
        try:
            self._save_geometry()
            if self.s.get("restore_on_exit", True):
                self.gamma.restore_all()
            autostart.write_active_flag(False)
            try:
                self.s.save()
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            try:
                self.s.log.error("Falha ao restaurar ao sair: %s", e)
            except Exception:
                pass


def _ui_selfcheck() -> int:
    """Mede o layout sem abrir loop de eventos (usado por tools/verify_exe.py).

    Existe por causa de um bug que so apareceu no .exe: com a janela na
    largura minima, 'Ligar gamma' era elidado para 'jar gamm' e 'HDR
    desligado' para 'HDR desligadc'. Textos elidados nao dao erro nenhum —
    so o print revela. Rodar dentro do processo empacotado garante que a
    medicao vale para o build.
    """
    app = QApplication.instance() or QApplication(sys.argv[:1])
    theme.apply_theme(app, "auto")
    s = SettingsManager()
    s.set("start_minimized", False)
    w = MainWindow(s, minimized=True)
    w.showNormal()
    app.processEvents()

    # Varrendo a largura: o problema era o header apertado, entao medimos
    # desde o minimo da janela ate um tamanho confortavel.
    worst = []
    for width in range(w.minimumWidth(), 1241, 40):
        w.resize(width, w.height())
        app.processEvents()
        for b in w._check_header_fits():
            worst.append(f"{width}px -> {b}")
    w.resize(1000, 680)
    app.processEvents()
    bad = list(worst)
    for name, wid, need in _header_measurements(w):
        flag = "ELIDADO" if need > wid else "ok"
        extra = f"  '{w.hdr_chip.text()}'" if name == "chip HDR" else ""
        print(f"{flag:9} {name:12} precisa {need:4d}px / tem {wid:4d}px{extra}")
    print(f"janela: {w.width()}x{w.height()}  (min {w.minimumWidth()}px)")
    print(f"varridas: {len(worst)} problema(s) entre {w.minimumWidth()} e 1240px")
    if bad:
        print("RESULTADO: FALHOU -> " + "; ".join(bad))
        w.hk.stop()
        return 1
    print("RESULTADO: OK")
    w.hk.stop()
    return 0


def _header_measurements(w) -> list[tuple[str, int, int]]:
    """(nome, largura do widget, largura minima do texto) do cabecalho."""
    from PySide6.QtGui import QFontMetrics
    out = []
    for name, widget in (("chip estado", w.status_pill),
                         ("toggle", w.btn_toggle),
                         ("restaurar", w.btn_reset),
                         ("chip HDR", w.hdr_chip),
                         ("diagnostico", w.btn_diag)):
        text = widget.text()
        # QFontMetrics com a fonte real do widget mede o texto que o Qt
        # tentaria desenhar; se isso passa da largura, ele elida.
        need = max(QFontMetrics(widget.font()).horizontalAdvance(text),
                   widget.sizeHint().width())
        out.append((name, widget.width(), need))
    # O combo e o unico que DEVE poder elidar (e o comportamento desejado
    # quando o nome do monitor e longo), entao entra com o valor minimo
    # aceito em vez do texto inteiro.
    out.append(("monitor", w.cmb_monitor.width(), w.cmb_monitor.minimumWidth()))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lumen")
    ap.add_argument("--minimized", action="store_true")
    ap.add_argument("--ui-selfcheck", action="store_true",
                    help="mede o layout e sai (diagnostico de build)")
    args = ap.parse_args(argv)
    if args.ui_selfcheck:
        return _ui_selfcheck()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Lumen")
    app.setOrganizationName("Lumen")
    try:
        app.setWindowIcon(app_icon())
    except Exception:
        pass
    settings = SettingsManager()
    try:
        theme.apply_theme(app, str(settings.get("ui_theme", "auto")))
    except Exception as e:  # noqa: BLE001
        settings.log.warning("Tema nao aplicado (%s); usando estilo do sistema.", e)
    w = MainWindow(settings, minimized=args.minimized)
    if not args.minimized and not settings.get("start_minimized"):
        w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
