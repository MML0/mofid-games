"""Each module here defines one power-up type and registers itself with @register.

New files are discovered automatically. BUILTIN is only a fallback for packaged builds that cannot list modules;
add new power-ups to it too (and to hiddenimports in packaging/LandHockey.spec happens automatically).
"""

BUILTIN = ["expand", "shrink", "speed_up", "chaos", "double_ball", "trajectory_reveal", "slow_down", "dim_ball",
           "shield", "bull_market"]
