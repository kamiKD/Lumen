"""Widgets reutilizaveis da UI do Lumen.

Ficam separados do `app.py` para que a janela cuide so de orquestracao
(estado, tray, watchers) e o visual fique isolado aqui.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from .theme import repolish

# Teclas aceitas pelo dialogo de captura. O campo de texto antigo aceitava
# qualquer nome de `VK_NAMES`, mas `normalize_keybind` so sabe reescrever
# F-keys, letras e digitos — nomes como SPACE viravam "VK(0x20)" e quebravam
# no proximo arranque. Limitar aqui evita esse caminho quebrado.
CAPTURABLE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") | {f"F{i}" for i in range(1, 25)}


def key_name(vk: int) -> str | None:
    """Inteiro do Qt -> nome canonico aceito por `normalize_keybind`."""
    for i in range(1, 25):
        if vk == 0x6F + i:
            return f"F{i}"
    ch = chr(vk)
    return ch if ch in CAPTURABLE else None


# ------------------------------------------------------------------ Chip

class Chip(QLabel):
    """Etiqueta de estado compacta (ON/OFF, HDR, fonte do osu!)."""

    def __init__(self, text: str = "", state: str = "off", parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setAlignment(Qt.AlignCenter)
        self.setProperty("state", state)

    def set_state(self, state: str, text: str | None = None) -> None:
        if self.property("state") != state:
            self.setProperty("state", state)
            repolish(self)
        if text is not None:
            self.setText(text)


# ----------------------------------------------------------------- Banner

class Banner(QFrame):
    """Faixa inline para HDR, falhas e avisos.

    Substitui os QMessageBox giants: mostra a causa provavel, deixa o
    "detalhe tecnico" escondido e oferece a acao que resolve.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        self._action_cb = None
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 11, 12, 11)
        outer.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("bannerTitle")
        self.lbl_body = QLabel()
        self.lbl_body.setObjectName("bannerBody")
        self.lbl_body.setWordWrap(True)
        col.addWidget(self.lbl_title)
        col.addWidget(self.lbl_body)
        top.addLayout(col, 1)

        side = QVBoxLayout()
        side.setSpacing(6)
        side.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.btn_action = QPushButton()
        self.btn_action.setProperty("variant", "primary")
        self.btn_action.setVisible(False)
        self.btn_action.clicked.connect(self._on_action)
        self.btn_details = QPushButton("Detalhes")
        self.btn_details.setCheckable(True)
        self.btn_details.setVisible(False)
        self.btn_details.setCursor(Qt.PointingHandCursor)
        side.addWidget(self.btn_action)
        side.addWidget(self.btn_details)
        top.addLayout(side)
        outer.addLayout(top)

        self.lbl_details = QLabel()
        self.lbl_details.setObjectName("bannerDetails")
        self.lbl_details.setWordWrap(True)
        self.lbl_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_details.setVisible(False)
        outer.addWidget(self.lbl_details)
        self.btn_details.toggled.connect(self.lbl_details.setVisible)

        self.setVisible(False)

    def _on_action(self):
        cb, self._action_cb = self._action_cb, None
        self.btn_action.setVisible(False)
        if callable(cb):
            cb()

    def show_message(self, severity: str, title: str, body: str = "",
                     action_text: str = "", action=None, details: str = "") -> None:
        if self.property("severity") != severity:
            self.setProperty("severity", severity)
            repolish(self)
        self.lbl_title.setText(title)
        self.lbl_title.setVisible(bool(title))
        self.lbl_body.setText(body)
        self.lbl_body.setVisible(bool(body))

        self._action_cb = action
        self.btn_action.setText(action_text)
        self.btn_action.setVisible(bool(action_text and callable(action)))

        self.btn_details.setChecked(False)
        self.lbl_details.setText(details)
        self.lbl_details.setVisible(False)
        self.btn_details.setVisible(bool(details))
        self.setVisible(True)

    def clear_message(self) -> None:
        # A dynamic property "severity" fica obsoleta depois de limpar: o
        # proximo show_message com a MESMA severidade nao faria repolish e a
        # cor ficaria da mensagem anterior.
        if self.property("severity") not in (None, "none"):
            self.setProperty("severity", "none")
            repolish(self)
        self.setVisible(False)
        self._action_cb = None
        self.btn_action.setVisible(False)
        self.btn_details.setVisible(False)
        self.lbl_details.setVisible(False)


# ----------------------------------------------------------- LabeledSlider

class LabeledSlider(QWidget):
    """Slider com rotulo em coluna a esquerda e valor alinhado a direita.

    Todos os sliders do app usam este template, entao os rotulos ficam
    alinhados entre si (antes cada um empilhava o texto acima do slider).
    """

    valueChanged = Signal(int)
    editingFinished = Signal()

    def __init__(self, title: str, lo: int, hi: int, fmt: str = "{}",
                 parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self.lbl_title = QLabel(title)
        self.lbl_title.setMinimumWidth(76)
        self.lbl_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setTracking(True)

        self.lbl_value = QLabel()
        self.lbl_value.setMinimumWidth(58)
        self.lbl_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f = QFont()
        f.setStyleHint(QFont.Monospace)
        self.lbl_value.setFont(f)

        row.addWidget(self.lbl_title)
        row.addWidget(self.slider, 1)
        row.addWidget(self.lbl_value)

        self._fmt = fmt
        self.slider.valueChanged.connect(self._on_change)
        self.slider.sliderReleased.connect(self._refresh)
        self.slider.sliderReleased.connect(self.editingFinished.emit)
        self._refresh(self.slider.value())

    def _on_change(self, v: int):
        self._refresh(v)
        self.valueChanged.emit(v)

    def _refresh(self, v: int):
        self.lbl_value.setText(self._fmt.format(v))

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, v: int):
        self.slider.setValue(int(v))

    def text(self) -> str:
        return self.lbl_value.text()


# ------------------------------------------------------------- GammaCurve

class GammaCurve(QWidget):
    """Previa da curva de transferencia resultante (256 pontos da LUT)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._curve: list[float] = []

    def set_values(self, gamma: float, brightness: float, contrast: float) -> None:
        from .gamma_controller import calculate_lut
        self._curve = [v / 65535.0 for v in
                       calculate_lut(gamma, brightness, contrast)]
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.size().width(), self.size().height()
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        plot = self.rect().adjusted(28, 10, -10, -18)
        if plot.width() < 10 or plot.height() < 10:
            return

        p.setPen(QPen(QColor(128, 134, 142, 80), 1, Qt.DotLine))
        # identidade: y = x
        p.drawLine(plot.left(), plot.bottom(),
                   plot.right(), plot.top())
        # grade 25/50/75%
        p.setPen(QPen(QColor(128, 134, 142, 40), 1))
        for i in range(1, 4):
            y = plot.bottom() - plot.height() * i / 4.0
            p.drawLine(plot.left(), int(y), plot.right(), int(y))
        # eixos
        p.setPen(QPen(QColor(128, 134, 142, 100), 1))
        p.drawLine(plot.left(), plot.top(), plot.left(), plot.bottom())
        p.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())

        if self._curve:
            p.setPen(QPen(QColor(79, 140, 255), 1.5))
            pts = []
            n = len(self._curve)
            for i, v in enumerate(self._curve):
                x = plot.left() + plot.width() * i / (n - 1)
                y = plot.bottom() - plot.height() * v
                pts.append((int(x), int(y)))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a[0], a[1], b[0], b[1])

        p.setPen(QPen(QColor(100, 110, 120)))
        f = QFont(self.font())
        f.setPointSize(max(7, f.pointSize() - 1))
        p.setFont(f)
        r = self.rect()
        # Rotulos dos eixos. drawText(x, y, flags, text) nao existe no PySide6
        # 6.x; a assinatura com (int, int, str) e a unica com posicao livre.
        p.drawText(r.left(), r.bottom() - 3, "escuro")
        p.drawText(r.left(), r.top() + 11, "claro")
        p.drawText(r.right() - 22, r.bottom() - 3, "255")
        p.end()


# ------------------------------------------------------------ ProfileList

class ProfileList(QListWidget):
    """Lista de perfis com os valores a vista e indicacao de alteracao."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setSpacing(2)
        self.setUniformItemSizes(False)
        self.setAlternatingRowColors(False)

    def _build(self, name: str, values: str, dirty: bool) -> QListWidgetItem:
        it = QListWidgetItem()
        it.setData(Qt.UserRole, name)
        it.setText(f"{name}{'  *' if dirty else ''}\n{values}")
        f = QFont(it.font())
        f.setPointSizeF(max(8.0, f.pointSizeF() - 0.5))
        it.setFont(f)
        it.setToolTip(
            f"{name}\n{values}\n\n"
            + ("Alteracoes nao salvas — clique em Salvar."
               if dirty else "Duplo clique aplica. Clique direito: acoes."))
        # Duas linhas de texto num QListWidgetItem: a altura do item precisa
        # comportar ambas, senao a segunda linha e cortada.
        it.setSizeHint(QSize(0, 56))
        return it

    def populate(self, entries: list[dict], active: str) -> None:
        """entries: [{'name', 'values', 'dirty'}, ...] ja ordenadas."""
        cur = self.currentItem()
        keep = cur.data(Qt.UserRole) if cur else None
        self.clear()
        for e in entries:
            it = self._build(e["name"], e["values"], e.get("dirty", False))
            self.addItem(it)
            if e["name"] == active:
                self.setCurrentItem(it)
        if self.currentItem() is None and self.count():
            self.setCurrentRow(0)
        if keep and keep != active and self.currentItem() is None:
            self.setCurrentRow(0)

    def refresh_item(self, name: str, values: str, dirty: bool) -> None:
        for it in self.findItems(name, Qt.MatchExactly):
            new = self._build(name, values, dirty)
            it.setText(new.text())
            it.setToolTip(new.toolTip())
            return

    def current_name(self) -> str:
        it = self.currentItem()
        return it.data(Qt.UserRole) if it else ""

    def select_name(self, name: str) -> bool:
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == name:
                self.setCurrentRow(i)
                return True
        return False


# ---------------------------------------------------------- KeyGrabDialog

class KeyGrabDialog(QDialog):
    """Captura a proxima combinacao digitada, em vez de digitar texto."""

    def __init__(self, current: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capturar atalho global")
        self.setModal(True)
        self.result_key = ""
        self.setMinimumWidth(380)

        v = QVBoxLayout(self)
        v.setSpacing(10)
        lbl = QLabel("Pressione a combinacao que voce quer usar para o toggle.")
        lbl.setWordWrap(True)
        hint = QLabel("Aceito: F1-F24, letras e numeros (com CTRL / ALT / SHIFT / WIN). "
                      "Esc cancela.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.lbl_current = QLabel(f"Atalho atual: {current or '(nenhum)'}")
        self.lbl_error = QLabel()
        self.lbl_error.setObjectName("bannerTitle")
        self.lbl_error.setStyleSheet("color: #c2352a;")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        v.addWidget(lbl)
        v.addWidget(hint)
        v.addWidget(self.lbl_current)
        v.addWidget(self.lbl_error)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setEnabled(False)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def keyPressEvent(self, ev):
        if ev.isAutoRepeat():
            return
        key = ev.key()
        if key == Qt.Key_Escape and ev.modifiers() == Qt.NoModifier:
            self.reject()
            return
        name = key_name(key)
        if name is None:
            self.lbl_error.setText(
                "Essa tecla nao e aceita. Use F1-F24, uma letra ou um numero.")
            self.lbl_error.show()
            return
        mods = []
        m = ev.modifiers()
        if m & Qt.ControlModifier:
            mods.append("CTRL")
        if m & Qt.AltModifier:
            mods.append("ALT")
        if m & Qt.ShiftModifier:
            mods.append("SHIFT")
        if m & Qt.MetaModifier:
            mods.append("WIN")
        self.result_key = "+".join(mods + [name])
        self.accept()


# ------------------------------------------------------- DiagnosticsDialog

class DiagnosticsDialog(QDialog):
    """Tudo que antes ocupava o topo da janela, sob demanda."""

    def __init__(self, rows: list[tuple[str, str]], log_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lumen — Diagnostico")
        self.setMinimumWidth(520)
        self._rows = list(rows)
        v = QVBoxLayout(self)
        v.setSpacing(12)

        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setVerticalSpacing(7)
        for k, val in rows:
            lbl = QLabel(val or "?")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            key = QLabel(k)
            key.setObjectName("subtitle")
            f.addRow(key, lbl)
        v.addLayout(f)

        btns = QHBoxLayout()
        btn_logs = QPushButton("Abrir pasta de logs")
        btn_logs.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir)))
        btn_copy = QPushButton("Copiar")
        btn_copy.clicked.connect(self._copy)
        btns.addWidget(btn_logs)
        btns.addWidget(btn_copy)
        btns.addStretch(1)
        v.addLayout(btns)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)

    def _copy(self):
        QApplication.clipboard().setText(self._text())

    def _text(self) -> str:
        lines = ["Lumen — diagnostico"]
        lines += [f"{k}: {val}" for k, val in self._rows if val]
        return "\n".join(lines)
