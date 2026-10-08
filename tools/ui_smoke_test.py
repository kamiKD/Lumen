"""Harness de fumaça: sobe a janela real e exercita o fluxo principal."""
import os
import sys
import tempfile

# Isola a config do usuario real durante o teste.
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="lumen_test_")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeyEvent

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = ["harness"]
from src.app import MainWindow
from src.settings_manager import SettingsManager

app = QApplication.instance() or QApplication([])
from src import theme
theme.apply_theme(app, "dark")

fails = []


def check(label, cond, extra=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label} {extra}")
    if not cond:
        fails.append(label)


s = SettingsManager()
s.set("start_minimized", False)
w = MainWindow(s, minimized=False)
# isVisible() dos filhos depende da janela visivel, entao mostramos.
w.showNormal()
app.processEvents()

# --- estrutura da UI
check("janela construida e visivel", w.isVisible() is True)
check("3 abas", w.tabs.count() == 3,
      [w.tabs.tabText(i) for i in range(w.tabs.count())])
check("toggle existe e e checkable", w.btn_toggle.isCheckable())
check("perfis populados", w.profile_list.count() > 0,
      w.profile_list.count())
check("chip HDR presente", w.hdr_chip.text() != "")
check("curva desenhavel", w.gamma_curve.width() > 0)
check("status inicial OFF", not w.btn_toggle.isChecked())

# --- banners
check("banner escondido no inicio", not w.banner.isVisible())
w._set_banner("warn", "t", "b", "acao", lambda: None, "detalhe")
check("banner aparece", w.banner.isVisible())
check("botao de acao visivel", w.banner.btn_action.isVisible())
check("detalhes disponiveis", w.banner.btn_details.isVisible() and
      w.banner.lbl_details.text() == "detalhe")
w.banner.btn_details.setChecked(True)
check("detalhes expandem", w.banner.lbl_details.isVisible())
w._clear_banner()
check("banner some", not w.banner.isVisible())

# --- sliders
w.sld_gamma.setValue(180)
w.sld_bri.setValue(55)
w.sld_con.setValue(60)
g, b, c = w._ui_values()
check("slider -> valores", (round(g, 2), b, c) == (1.8, 55.0, 60.0),
      (g, b, c))
check("gamma text formatado", w.sld_gamma.text() == "180",
      w.sld_gamma.text())
w.sld_gamma.setValue(100)
check("preview recebe curva", len(w.gamma_curve._curve) == 256)

# --- dirty tracking
name = w.active_profile
w._reload_profiles()
was_enabled = w.btn_profile_save.isEnabled()
w.sld_gamma.setValue(250)
check("Salvar habilita com alteracao", w.btn_profile_save.isEnabled(),
      f"antes={was_enabled}")
check("asterisco marca alteracao", "*" in
      w.profile_list.currentItem().text())
w.sld_gamma.setValue(100)
w._update_dirty()
check("Salvar desabilita sem alteracao",
      not w.btn_profile_save.isEnabled())

# --- selecao de perfil carrega valores
items = {w.profile_list.item(i).data(Qt.UserRole): i
         for i in range(w.profile_list.count())}
if "Gaming" in items:
    w.profile_list.setCurrentRow(items["Gaming"])
    check("perfil Gaming aplica valores",
          abs(w._ui_values()[0] - 1.8) < 1e-6, w._ui_values())
    check("active_profile prop", w.active_profile == "Gaming", w.active_profile)

# --- sincronia do toggle no caminho de falha (o bug corrigido)
w.btn_toggle.setChecked(True)          # simula estado "ligado"
ok = w._set_gamma_state(False, silent=True)
check("restore silent nao quebra", ok is False, ok)
check("toggle dessincronizado apos falha silenciosa",
      w.btn_toggle.isChecked() is False, w.btn_toggle.isChecked())
check("config gamma_on coerente", s.get("gamma_on") is False,
      s.get("gamma_on"))
w._set_gamma_state(True, silent=True)
check("toggle liga de novo", w.btn_toggle.isChecked() is True)

# --- hotkey capture
from src.ui import KeyGrabDialog
dlg = KeyGrabDialog("F8")
ev = QKeyEvent(QKeyEvent.KeyPress, 0x6F + 8, Qt.ControlModifier, "F8")
dlg.keyPressEvent(ev)
check("captura CTRL+F8", dlg.result_key == "CTRL+F8", dlg.result_key)
dlg2 = KeyGrabDialog("F8")
ev2 = QKeyEvent(QKeyEvent.KeyPress, 0x20, Qt.NoModifier, " ")
dlg2.keyPressEvent(ev2)
# isVisible() seria False: o dialogo em si nao foi exibido. O que importa
# e o erro ter sido marcado e destravado o erro visivel.
check("recusa SPACE com erro destravado",
      dlg2.result_key == "" and not dlg2.lbl_error.isHidden(),
      dlg2.lbl_error.text())
dlg3 = KeyGrabDialog("F8")
ev3 = QKeyEvent(QKeyEvent.KeyPress, 0x1B, Qt.NoModifier, "\x1b")
dlg3.keyPressEvent(ev3)
check("Esc cancela", dlg3.result_key == "")

# --- persistencia de geometria
w._save_geometry()
check("geometria salva", bool(s.get("window_geometry")),
      len(str(s.get("window_geometry"))))
w2 = MainWindow(SettingsManager(), minimized=True)
check("geometria restaurada", w2.width() == w.width() and
      w2.height() == w.height(), (w2.width(), w2.height()))

# --- tema
for pref in ("light", "dark", "auto"):
    w.cmb_theme.setCurrentIndex(w.cmb_theme.findData(pref))
    check(f"tema {pref}", s.get("ui_theme") == pref and
          app.styleSheet() != "", pref)

# --- persistencia das opcoes
check("tema virou default do combo",
      w.cmb_theme.currentData() == s.get("ui_theme"))
w._quit_app()

print()
print("FALHAS:", fails if fails else "nenhuma")
sys.exit(1 if fails else 0)
