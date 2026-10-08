"""Tema visual do Lumen: tokens de cor, tipografia e espacamento.

Objetivo: um unico lugar para a identidade visual, com variantes clara e
escura, em vez de `setStyleSheet("color: gray")` espalhado pelo app.py.

O tema segue a preferencia do Windows (`QStyleHints::colorScheme`) e aceita
override manual ("auto" | "light" | "dark") persistido na config.
"""
from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------- tokens

# Espacamento e raio sao compartilhados pelas duas variantes.
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADIUS = 6
FONT_PT = 10
FONT_STACK = '"Segoe UI", "Inter", system-ui, sans-serif'
MONO_STACK = '"Cascadia Mono", Consolas, "Courier New", monospace'

LIGHT = {
    "bg": "#f2f4f7",
    "surface": "#ffffff",
    "surface_alt": "#f7f8fa",
    "border": "#e0e4ea",
    "border_strong": "#c6ccd5",
    "text": "#1a1e23",
    "text_muted": "#58616d",
    "text_faint": "#8a929c",
    "accent": "#2f6feb",
    "accent_hover": "#2559c4",
    "accent_soft": "#e8f0fe",
    "on": "#1a8f4c",
    "on_deep": "#15703c",
    "on_soft": "#e3f5ea",
    "off": "#78828d",
    "off_soft": "#eceef1",
    "warn": "#a86500",
    "warn_soft": "#fdf4e3",
    "warn_border": "#e9c88c",
    "error": "#c2352a",
    "error_soft": "#fdeceb",
    "error_border": "#f0b4af",
    "track": "#d9dee5",
}

DARK = {
    "bg": "#0f1115",
    "surface": "#15181d",
    "surface_alt": "#1b1f26",
    "border": "#232830",
    "border_strong": "#2f3540",
    "text": "#e8eaed",
    "text_muted": "#9aa3af",
    "text_faint": "#5c6672",
    "accent": "#4f8cff",
    "accent_hover": "#6ba0ff",
    "accent_soft": "#141c2e",
    "on": "#34d399",
    "on_deep": "#10b981",
    "on_soft": "#0a1f16",
    "off": "#6b7280",
    "off_soft": "#1a1e24",
    "warn": "#f59e0b",
    "warn_soft": "#1f1a0e",
    "warn_border": "#3d2f18",
    "error": "#ef4444",
    "error_soft": "#2a1515",
    "error_border": "#4a1f1f",
    "track": "#1f242c",
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

/* ---------------------------------------------------------- botoes */
QPushButton {
    background: ${surface};
    border: 1px solid ${border_strong};
    border-radius: ${radius}px;
    padding: 6px 14px;
    color: ${text};
    transition: background 120ms, border-color 120ms;
}
QPushButton:hover { background: ${surface_alt}; border-color: ${accent}; }
QPushButton:pressed { background: ${bg}; }
QPushButton:disabled { color: ${text_faint}; border-color: ${border}; background: ${surface_alt}; }
QPushButton:focus { border-color: ${accent}; }

QPushButton[variant="primary"] {
    background: ${accent}; color: #ffffff; border-color: ${accent}; font-weight: 600;
}
QPushButton[variant="primary"]:hover { background: ${accent_hover}; border-color: ${accent_hover}; }
QPushButton[variant="primary"]:disabled { background: ${border_strong}; color: ${off_soft}; border-color: ${border}; }

QPushButton[variant="danger"] { color: ${error}; border-color: ${error_border}; }
QPushButton[variant="danger"]:hover { background: ${error_soft}; border-color: ${error}; }
QPushButton[variant="danger"]:disabled { color: ${text_faint}; border-color: ${border}; background: ${surface_alt}; }

/* Toggle principal: botao de acao primaria, nao um hero dominante. */
QPushButton#heroToggle {
    padding: 7px 20px;
    font-size: 10.5pt;
    font-weight: 600;
    border-radius: 7px;
}
QPushButton#heroToggle:checked {
    background: ${on}; border-color: ${on_deep};
    color: #ffffff;
}
QPushButton#heroToggle:checked:hover { background: ${on_deep}; }
QPushButton#heroToggle:!checked {
    background: ${surface}; border: 1px solid ${border_strong}; color: ${text};
}
QPushButton#heroToggle:!checked:hover { border-color: ${accent}; background: ${surface_alt}; }

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

/* ---------------------------------------------------------- sliders */
QSlider::groove:horizontal { height: 4px; background: ${track}; border-radius: 2px; }
QSlider::sub-page:horizontal { background: ${accent}; border-radius: 2px; }
QSlider::sub-page:horizontal:disabled { background: ${track}; }
QSlider::handle:horizontal {
    width: 14px; margin: -5px 0;
    background: ${surface}; border: 2px solid ${accent}; border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: ${accent}; }
QSlider::handle:horizontal:disabled { border-color: ${track}; background: ${surface_alt}; }

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

/* ---------------------------------------------------------- abas */
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
""")


def build_qss(tokens: dict) -> str:
    base = dict(tokens)
    base["font_stack"] = FONT_STACK
    base["mono_stack"] = MONO_STACK
    base["font_pt"] = FONT_PT
    base["radius"] = RADIUS
    return _QSS.substitute(base)


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
