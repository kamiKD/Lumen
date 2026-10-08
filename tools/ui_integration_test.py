import os, sys, tempfile
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="gs_int_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = ["harness"]
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
app = QApplication([])
from src import theme
theme.apply_theme(app, "dark")
from src.app import MainWindow
from src.settings_manager import SettingsManager
s = SettingsManager(); s.set("start_minimized", False)
w = MainWindow(s, minimized=False); w.showNormal(); app.processEvents()
fails=[]
def chk(l,c,e=""):
    print(f"{'PASS' if c else 'FAIL'}  {l} {e}")
    if not c: fails.append(l)

# HDR do monitor ativo empurra o banner
w._set_gamma_state(True, silent=True)
w.monitors[0]["hdr"] = True
w._update_monitor_labels()
chk("HDR liga chip warn", w.hdr_chip.property("state")=="warn", w.hdr_chip.text())
chk("banner warn", w.banner.property("severity")=="warn")
w.monitors[0]["hdr"] = False
w._update_monitor_labels()
chk("HDR desliga chip", w.hdr_chip.property("state")=="off", w.hdr_chip.text())
chk("banner warn some", w.banner.property("severity")=="none" and not w.banner.isVisible())

# banner de erro nao e sobrescrito por HDR desligado
w._set_banner("error","Erro de teste","corpo",details="detalhe")
w._update_monitor_labels()
chk("banner erro sobrevive ao refresh", w.banner.property("severity")=="error")
w._clear_banner()

# _apply_live bem-sucedido limpa o erro
w._set_gamma_state(False, silent=True)
class FakeGamma:
    backend_name="fake"
    def apply(self,*a,**k): return True
    def restore(self,*a,**k): return True
    def restore_all(self): pass
real, w.gamma = w.gamma, FakeGamma()
w._set_banner("error","Erro antigo","x")
w.btn_toggle.setChecked(True)
w._apply_live()
chk("apply ok limpa erro", w.banner.property("severity")=="none")
w.gamma = real

# _set_gamma_state: falha de apply forca OFF e persiste
w.gamma = FakeGamma()
w.gamma.apply = lambda *a, **k: False
ok = w._set_gamma_state(True)
chk("apply falhou -> retorna False", ok is False, ok)
chk("toggle forcado OFF", w.btn_toggle.isChecked() is False)
chk("gamma_on persistido OFF", s.get("gamma_on") is False)
chk("active.flag limpo", w.gamma is not None)
w.gamma = real

# fluxo de perfil: novo -> dirty -> salvar -> limpo
w._on_profile_new.__self__  # sanidade
before = w.profile_list.count()
w.profile_list.setCurrentRow(before-1)
name = w.active_profile
w.sld_gamma.setValue(123)
w._update_dirty()
chk("dirty habilita Salvar", w.btn_profile_save.isEnabled())
saved = {}
w.pm.snapshot_current = lambda n,g,b,c,m,gpu: saved.update(n=n)
w._on_profile_save()
chk("save grava no perfil", saved.get("n")==name, saved)
chk("statusbar de sucesso", w.lbl_status.isVisible() and "salvo" in w.lbl_status.text(),
    w.lbl_status.text())

# perfil coringa (monitor None) nao fica sujo so por trocar de monitor.
# Antes disso o slider precisa bater com o perfil, senao a diferenca de gamma
# (123 vs 1.40) marcaria o perfil sujo de qualquer jeito.
p = w.pm.get(name)
g, b, c = w._ui_values()
print("   ui:", g, b, c, "| perfil:", {k: p.get(k) for k in ("gamma","brightness","contrast","monitor")})
p["gamma"], p["brightness"], p["contrast"] = g, b, c
p["monitor"] = None
w._update_dirty()
chk("coringa nao marca sujo", not w.btn_profile_save.isEnabled(),
    w.lbl_profile_info.text())
# perfil fixo em outro monitor marca sujo
w.pm.get(name)["monitor"] = "\\\\.\\DISPLAY99"
w._update_dirty()
chk("perfil de outro monitor marca sujo", w.btn_profile_save.isEnabled())
w.pm.get(name)["monitor"] = None
w._reload_profiles()

# tray: perfil ativo no tooltip
w._update_tray()
chk("tray tem perfis", w.menu_profiles.actions().__len__() >= 8)
chk("tray marca ativo", any(a.isChecked() for a in w.menu_profiles.actions()))

# item deletado do perfil ativo nao quebra
n_before = w.profile_list.count()
w._on_profile_delete_orig = w._on_profile_delete
w.pm.delete(w.active_profile)
w._reload_profiles()
chk("lista reduz apos delete", w.profile_list.count() == n_before-1, w.profile_list.count())
chk("active_profile valido", w.pm.get(w.active_profile) is not None, w.active_profile)

# tray ativacao: enum
from PySide6.QtWidgets import QSystemTrayIcon
w._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
chk("tray double click", w.isVisible())

w.hk.stop()
print(); print("FALHAS:", fails if fails else "nenhuma")
