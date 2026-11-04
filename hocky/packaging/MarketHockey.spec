# PyInstaller recipe: builds MarketHockey(.exe), ControlPanel(.exe) and LidarTracker(.exe) into ONE folder that share
# their libraries.
#
#   pip install -r requirements-build.txt
#   pyinstaller --noconfirm packaging/MarketHockey.spec
#
# Output: dist/MarketHockey/  (the GitHub workflow then copies config/, assets/ and logs/ next to the .exe files,
# so settings are saved beside the executables and can be edited / replaced on the exhibition PC).
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

import sys
from pathlib import Path

HERE = os.path.abspath(os.path.join(SPECPATH, ".."))  # the game folder (hocky/)
sys.path.insert(0, HERE)

# Power-ups are imported dynamically, so list every module explicitly (new files are picked up automatically).
hidden = sorted({f"market_hockey.powerups.types.{p.stem}"
                 for p in Path(HERE, "market_hockey", "powerups", "types").glob("*.py") if not p.stem.startswith("_")})
hidden += [f"market_hockey.{'.'.join(p.relative_to(Path(HERE, 'market_hockey')).with_suffix('').parts)}"
           for p in Path(HERE, "market_hockey").rglob("*.py") if p.stem != "__init__"]
hidden += collect_submodules("arabic_reshaper")
datas = (collect_data_files("arabic_reshaper")
         + [(os.path.join(HERE, "assets"), "assets")])   # fallback copy inside the bundle
excludes = ["pytest", "_pytest", "IPython", "matplotlib", "scipy", "pandas", "PIL"]
icon = os.path.join(HERE, "packaging", "icon.ico")
icon = icon if os.path.exists(icon) else None


def analysis(script):
    return Analysis([os.path.join(HERE, script)], pathex=[HERE], hiddenimports=hidden, datas=datas,
                    excludes=excludes, noarchive=False)


a_game = analysis("main.py")
a_panel = analysis("settings_app.py")
# the LiDAR tracker: LIdar/ as delivered, with its setup window in the same .exe (see lidar_tracker.py)
LIDAR = os.path.join(HERE, "LIdar")
a_lidar = Analysis([os.path.join(HERE, "lidar_tracker.py")], pathex=[HERE, LIDAR],
                   hiddenimports=hidden + ["floor_game", "lidar_setup", "serial", "serial.tools.list_ports"],
                   datas=datas, excludes=excludes, noarchive=False)

exe_game = EXE(PYZ(a_game.pure), a_game.scripts, [], exclude_binaries=True, name="MarketHockey",
               console=False, icon=icon, upx=False)
exe_panel = EXE(PYZ(a_panel.pure), a_panel.scripts, [], exclude_binaries=True, name="ControlPanel",
                console=False, icon=icon, upx=False)
# a console program: the game starts it without a window and keeps its output in logs/lidar_tracker.log
exe_lidar = EXE(PYZ(a_lidar.pure), a_lidar.scripts, [], exclude_binaries=True, name="LidarTracker",
                console=True, icon=icon, upx=False)

coll = COLLECT(exe_game, a_game.binaries, a_game.datas,
               exe_panel, a_panel.binaries, a_panel.datas,
               exe_lidar, a_lidar.binaries, a_lidar.datas,
               upx=False, name="MarketHockey")
