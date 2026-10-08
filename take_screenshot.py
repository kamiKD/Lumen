"""Take screenshots of all Lumen tabs for visual verification."""
import os, sys, tempfile
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="gs_shot_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication([])
from src import theme
theme.apply_theme(app, "dark")
from src.app import MainWindow
from src.settings_manager import SettingsManager
s = SettingsManager()
s.set("start_minimized", False)
w = MainWindow(s, minimized=False)
w.showNormal()
app.processEvents()

import time
time.sleep(0.3)
app.processEvents()

out = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tab 0: Gamma (already ON)
w.grab().save(os.path.join(out, "shot_tab_gamma.png"))

# Tab 1: Perfis
w.tabs.setCurrentIndex(1)
app.processEvents()
time.sleep(0.2)
w.grab().save(os.path.join(out, "shot_tab_profiles.png"))

# Tab 2: Opcoes
w.tabs.setCurrentIndex(2)
app.processEvents()
time.sleep(0.2)
w.grab().save(os.path.join(out, "shot_tab_options.png"))

# Back to Gamma with toggle ON
w.tabs.setCurrentIndex(0)
w._set_gamma_state(True, silent=True)
app.processEvents()
time.sleep(0.2)
w.grab().save(os.path.join(out, "shot_tab_gamma_on.png"))

print("All screenshots saved")
w.hk.stop()
