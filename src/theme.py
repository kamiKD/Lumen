"""Tema visual do Lumen: tokens de cor, tipografia e espacamento.

Objetivo: um unico lugar para a identidade visual, com variantes clara e
escura, em vez de `setStyleSheet("color: gray")` espalhado pelo app.py.

O tema segue a preferencia do Windows (`QStyleHints::colorScheme`) e aceita
override manual ("auto" | "light" | "dark") persistido na config.
"""
from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------- tokens

# Espacamento e raio sao compartilhados pelas duas variantes.
# RADIUS 6 e o raio do Windows 11 para controles interativos; os cards
# maiores usam 8 (o Win11 usa raio grande so em superficies flutuantes).
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADIUS = 6
FONT_PT = 10
# Segoe UI Variable e a fonte do Windows 11; cai para Segoe UI se faltar.
FONT_STACK = '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'
MONO_STACK = '"Cascadia Mono", Consolas, "Courier New", monospace'

# Fonte de icones do Windows (Segoe Fluent/MDL2). Verificado em tempo de
# execucao por `icon_font()`: se a fonte nao existir, a UI cai para texto.
ICON_FONT = "Segoe MDL2 Assets"

# Glifos (codepoints estaveis do MDL2, conferidos por renderizacao).
ICONS = {
    "monitor":    "\ue7f4",
    "brightness": "\ue706",
    "settings":   "\ue713",
    "chevron":    "\ue76c",
    "refresh":    "\ue72c",
    "color":      "\ue790",
    "keyboard":   "\ue765",
    "power":      "\ue7e8",
    "devices":    "\ue772",
    "user":       "\ue77b",
    "repair":     "\ue7f3",
    "save":       "\ue8bb",
    "key":        "\ue192",
    "sync":       "\ue895",
    "sounds":     "\ue767",
}

LIGHT = {
    # Paleta do Windows 11: fundo #f3f3f3 (Fluent), cards brancos, acento
    # azul do sistema, selecao de nav cinza-azulada translucida.
    "bg": "#f3f3f3",
    "handle": "#ffffff",
    "surface": "#ffffff",
    "surface_alt": "#f9f9f9",
    "nav": "#f3f3f3",
    "nav_hover": "#e9e9ec",
    "nav_active": "#e0e0e6",
    "border": "#e5e5e5",
    "border_strong": "#cccccc",
    "text": "#1a1a1a",
    "text_muted": "#5d5d5d",
    "text_faint": "#8a8a8a",
    "accent": "#0067c0",
    "accent_hover": "#0053a6",
    "accent_soft": "#eff6fc",
    "on": "#0f7b0f",
    "on_deep": "#0b5c0b",
    "on_soft": "#eef7ee",
    "off": "#616161",
    "off_soft": "#f0f0f0",
    "warn": "#9d5d00",
    "warn_soft": "#fff8e6",
    "warn_border": "#f2d9a8",
    "error": "#b10e1c",
    "error_soft": "#fdf3f4",
    "error_border": "#f2c0c4",
    "track": "#d6d6d6",
}

DARK = {
    # Windows 11 escuro: fundo #202020, cards #2b2b2b, acento #4cc2ff,
    # selecao de nav com pílula translucida sobre o fundo.
    "bg": "#202020",
    "handle": "#ffffff",
    "surface": "#2b2b2b",
    "surface_alt": "#323232",
    "nav": "#202020",
    "nav_hover": "#2a2a2a",
    "nav_active": "#343434",
    "border": "#3d3d3d",
    "border_strong": "#4a4a4a",
    "text": "#ffffff",
    "text_muted": "#c5c5c5",
    "text_faint": "#8a8a8a",
    "accent": "#4cc2ff",
    "accent_hover": "#6ccfff",
    "accent_soft": "#123552",
    "on": "#6ccb5f",
    "on_deep": "#5ab04f",
    "on_soft": "#16301a",
    "off": "#9a9a9a",
    "off_soft": "#2e2e2e",
    "warn": "#fce100",
    "warn_soft": "#332a00",
    "warn_border": "#5c4d00",
    "error": "#ff99a4",
    "error_soft": "#3a1c20",
    "error_border": "#663338",
    "track": "#4a4a4a",
}

PREFERENCES = ("auto", "light", "dark")


def system_prefers_dark() -> bool:
    """Usa o colorScheme do Windows; cai pra luminancia da paleta se faltar."""
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except Exception:
        pass
    try:
        app = QGuiApplication.instance()
        return app.palette().window().color().lightness() < 128
    except Exception:
        return False


def tokens_for(preference: str = "auto") -> dict:
    if preference == "light":
        return dict(LIGHT)
    if preference == "dark":
        return dict(DARK)
    return dict(DARK if system_prefers_dark() else LIGHT)


def is_dark(preference: str = "auto") -> bool:
    return tokens_for(preference)["bg"] == DARK["bg"]


# ---------------------------------------------------------------- QSS

_QSS = Template("""\
QWidget {
    font-family: ${font_stack};
    font-size: ${font_pt}pt;
    color: ${text};
}
QMainWindow, QDialog { background: ${bg}; }
QToolTip {
    background: ${surface}; color: ${text};
    border: 1px solid ${border_strong}; border-radius: 4px; padding: 4px 6px;
}

/* Labels nunca pintam fundo: herdariam o do painel e virariam "caixas". */
QLabel, QCheckBox, QRadioButton, QGroupBox > QWidget { background: transparent; }
QCheckBox, QRadioButton { spacing: 8px; }
QCheckBox:disabled, QRadioButton:disabled { color: ${text_faint}; }
/* Nao estilizamos ::indicator de proposito: qualquer regra em ::indicator faz
   o Qt parar de desenhar o check nativo e passar a usar a paleta, o que
   destoa do tema. O check do sistema acompanha light/dark sozinho. */

/* ---------------------------------------------------------- paineis */
QGroupBox {
    background: ${surface};
    border: 1px solid ${border};
    border-radius: 8px;
    margin-top: 13px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 5px;
    color: ${text_muted};
}

/* ---------------------------------------------------------- botoes
   Botao padrao do Win11: superficie sutil, borda de 1px, raio 4, texto
   10pt. Primario leva o acento. */
QPushButton {
    background: ${surface_alt};
    border: 1px solid ${border_strong};
    border-radius: 4px;
    padding: 5px 12px;
    color: ${text};
    font-size: ${font_pt}pt;
}
QPushButton:hover { background: ${surface_alt}; border-color: ${text_faint}; }
QPushButton:pressed { background: ${border}; }
QPushButton:disabled {
    color: ${text_faint}; border-color: ${border};
    background: ${surface_alt};
}
QPushButton:focus { border-color: ${accent}; }

QPushButton[variant="primary"] {
    background: ${accent};
    color: ${bg};
    border-color: ${accent};
    font-weight: 600;
}
QPushButton[variant="primary"]:hover { background: ${accent_hover}; border-color: ${accent_hover}; }
QPushButton[variant="primary"]:disabled {
    background: ${border}; color: ${text_faint}; border-color: ${border};
}

QPushButton[variant="danger"] { color: ${error}; border-color: ${error_border}; }
QPushButton[variant="danger"]:hover { background: ${error_soft}; border-color: ${error}; }
QPushButton[variant="danger"]:disabled { color: ${text_faint}; border-color: ${border}; background: ${surface_alt}; }

/* Toggle principal do cabecalho: estilo de switch do Win11 (pilula). */
QPushButton#heroToggle {
    padding: 7px 20px;
    font-size: 10.5pt;
    font-weight: 600;
    border-radius: 100px;
    min-width: 120px;
}
QPushButton#heroToggle:checked {
    background: ${on}; border-color: ${on_deep}; color: #ffffff;
}
QPushButton#heroToggle:checked:hover { background: ${on_deep}; }
QPushButton#heroToggle:!checked {
    background: ${accent_soft}; border: 1px solid ${accent}; color: ${accent};
}
QPushButton#heroToggle:!checked:hover { background: ${accent_soft}; }

/* ---------------------------------------------------------- entradas */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: ${surface};
    border: 1px solid ${border_strong};
    border-radius: ${radius}px;
    padding: 5px 8px;
    selection-background-color: ${accent};
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: ${accent}; }
QLineEdit:disabled, QComboBox:disabled { color: ${text_faint}; background: ${surface_alt}; }
/* Nao estilizamos ::drop-down / ::down-arrow: qualquer regra nesses
   subcontroles faz o Qt parar de desenhar a seta nativa. O visual nativo
   acompanha o tema do sistema. */
QComboBox QAbstractItemView {
    background: ${surface};
    border: 1px solid ${border_strong};
    selection-background-color: ${accent_soft};
    selection-color: ${text};
    outline: 0;
}

/* ---------------------------------------------------------- sliders
   Padrao Win11: trilha fina de 4px, preenchida com o acento, e handle
   circular de 20px branco com borda sutil. */
QSlider::groove:horizontal {
    height: 4px; background: ${track}; border-radius: 2px;
    border: none;
}
QSlider::sub-page:horizontal { background: ${accent}; border-radius: 2px; }
QSlider::sub-page:horizontal:disabled { background: ${track}; }
QSlider::add-page:horizontal { background: ${track}; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 20px; height: 20px;
    margin: -8px 0;
    background: ${handle};
    border: 1px solid ${border_strong};
    border-radius: 11px;
}
QSlider::handle:horizontal:hover {
    background: ${handle}; border-color: ${accent};
}
QSlider::handle:horizontal:pressed {
    background: ${accent}; border-color: ${accent};
}
QSlider::handle:horizontal:disabled {
    background: ${surface_alt}; border-color: ${border};
}

/* ---------------------------------------------------------- listas */
QListWidget {
    background: ${surface};
    border: 1px solid ${border};
    border-radius: 8px;
    padding: 4px;
    outline: 0;
}
QListWidget::item { border-radius: 6px; padding: 2px; color: ${text}; }
QListWidget::item:selected { background: ${accent_soft}; color: ${text}; }
QListWidget::item:hover:!selected { background: ${surface_alt}; }

/* ---------------------------------------------------------- abas
   O Windows 11 nao usa abas: a navegacao fica numa barra lateral com
   pilula de selecao. As regras do QTabWidget continuam para o Dialogo
   de Diagnostico, que usa abas de verdade. */
QTabWidget::pane {
    border: 1px solid ${border};
    border-radius: 8px;
    background: ${surface};
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: ${text_muted};
    padding: 8px 20px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:selected {
    background: ${surface};
    color: ${text};
    font-weight: 600;
    border-color: ${border};
    border-bottom-color: ${surface};
}
QTabBar::tab:hover:!selected { color: ${text}; background: ${surface_alt}; }

/* ------------------------------------------------- navegacao lateral
   Item com icone + texto; o selecionado ganha pilula e uma barra de
   acento de 3px na borda esquerda, como no painel do Windows 11. */
QFrame#navRail {
    background: ${nav};
    border: none;
}
QFrame#navItem {
    background: transparent;
    border: none;
    border-radius: 4px;
    border-left: 3px solid transparent;
    color: ${text};
}
QFrame#navItem:hover { background: ${nav_hover}; }
QFrame#navItem[selected="true"] {
    background: ${nav_active};
    border-left: 3px solid ${accent};
}
QFrame#navItem[selected="true"] QLabel {
    color: ${text};
    font-weight: 600;
}
QLabel#navUser    { font-weight: 600; font-size: 11pt; }
QLabel#navUserSub { color: ${text_muted}; font-size: 9pt; }

/* ------------------------------------------------------ cartoes
   Cards do painel do Windows 11: largura cheia, raio 8, borda sutil e
   4px de distancia entre eles. */
QFrame#card {
    background: ${surface};
    border: 1px solid ${border};
    border-radius: 8px;
}
QLabel#pageTitle {
    font-size: 20pt;
    font-weight: 600;
    color: ${text};
    background: transparent;
}
QLabel#cardIcon {
    font-family: "${icon_font}";
    color: ${text};
    background: transparent;
}
QLabel#cardSub { color: ${text_muted}; font-size: 9pt; background: transparent; }
QLabel#cardTitle { font-weight: 600; background: transparent; }

/* Hero: bloco de identidade no topo da pagina, como o do Sistema. */
QFrame#hero {
    background: ${surface};
    border: 1px solid ${border};
    border-radius: 8px;
}
QLabel#heroName { font-size: 13pt; font-weight: 600; background: transparent; }
QLabel#heroSub  { color: ${text_muted}; font-size: 9pt; background: transparent; }
QLabel#heroIcon {
    font-family: "${icon_font}";
    font-size: 26pt;
    color: ${text};
    background: transparent;
}

/* ---------------------------------------------------------- chips */
QLabel#chip {
    background: ${off_soft};
    color: ${off};
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 9pt;
}
QLabel#chip[state="on"]    { background: ${on_soft};    color: ${on}; }
QLabel#chip[state="off"]   { background: ${off_soft};   color: ${off}; }
QLabel#chip[state="warn"]  { background: ${warn_soft};  color: ${warn}; }
QLabel#chip[state="error"] { background: ${error_soft}; color: ${error}; }
QLabel#chip[state="info"]  { background: ${accent_soft}; color: ${accent}; }

/* ---------------------------------------------------------- banner */
QFrame#banner {
    background: ${surface_alt};
    border: 1px solid ${border};
    border-left: 3px solid ${border_strong};
    border-radius: 8px;
}
QFrame#banner[severity="info"]  { background: ${accent_soft}; border-color: ${border}; border-left-color: ${accent}; }
QFrame#banner[severity="ok"]    { background: ${on_soft};    border-color: ${border}; border-left-color: ${on}; }
QFrame#banner[severity="warn"]  { background: ${warn_soft};  border-color: ${warn_border}; border-left-color: ${warn}; }
QFrame#banner[severity="error"] { background: ${error_soft}; border-color: ${error_border}; border-left-color: ${error}; }
QLabel#bannerTitle { font-weight: 600; background: transparent; }
QLabel#bannerBody  { color: ${text_muted}; background: transparent; }
QLabel#bannerDetails {
    color: ${text_faint}; background: transparent; font-family: ${mono_stack}; font-size: 9pt;
}

/* ---------------------------------------------------------- molduras */
QFrame#header {
    background: ${surface};
    border: none;
    border-radius: 8px;
}
QFrame#curvePanel {
    background: transparent;
    border: none;
    border-radius: 8px;
}
/* A curva da aba Gamma vira card quando marcada com property="card". */
QFrame#curvePanel[card="true"] {
    background: ${surface};
    border: 1px solid ${border};
    border-radius: 8px;
}
QLabel#statusBar {
    background: ${accent_soft};
    color: ${text};
    border-radius: 6px;
    padding: 7px 12px;
}
QLabel#statusBar[kind="error"] { background: ${error_soft}; color: ${error}; }
QLabel#statusBar[kind="ok"]    { background: ${on_soft};    color: ${on}; }
QLabel#hint      { color: ${text_faint}; background: transparent; }
QLabel#subtitle  { color: ${text_muted}; background: transparent; }

/* Scrollbar discreta, no estilo Win11: fina e sem setas. */
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical {
    background: transparent; width: 12px; margin: 0;
}
QScrollBar::handle:vertical {
    background: ${border_strong}; border-radius: 5px; min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: ${text_faint}; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
""")


def build_qss(tokens: dict) -> str:
    base = dict(tokens)
    base["font_stack"] = FONT_STACK
    base["mono_stack"] = MONO_STACK
    base["font_pt"] = FONT_PT
    base["radius"] = RADIUS
    base["icon_font"] = ICON_FONT
    return _QSS.substitute(base)


def icon_font(size_pt: int = 16) -> "QFont":
    """Fonte de icones do Windows. Vazia se a fonte nao existir na maquina."""
    if ICON_FONT not in _available_fonts():
        return QFont()
    f = QFont(ICON_FONT)
    f.setPointSize(size_pt)
    return f


def _available_fonts() -> set:
    global _FONTS_CACHE
    if _FONTS_CACHE is None:
        from PySide6.QtGui import QFontDatabase
        app = QApplication.instance()
        _FONTS_CACHE = set(QFontDatabase.families()) if app else set()
    return _FONTS_CACHE


_FONTS_CACHE = None


def repolish(widget) -> None:
    """Reaplica o estilo apos mudar uma dynamic property (QSS nao refaz sozinho)."""
    try:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
    except RuntimeError:
        pass


def apply_theme(app: QApplication, preference: str = "auto") -> dict:
    """Aplica o tema no QApplication e repolisha a UI existente.

    Retorna os tokens usados (util para testes e para o diagnostico).
    """
    tokens = tokens_for(preference)
    app.setStyleSheet(build_qss(tokens))
    for w in app.allWidgets():
        repolish(w)
    return tokens
