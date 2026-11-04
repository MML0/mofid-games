"""What actually ships: settings, presets, assets, the build recipe, and the walls between the modules."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import market_hockey
from market_hockey import paths
from market_hockey.config import SCHEMA_VERSION, Config, get_schema
from market_hockey.config.generate_defaults import PRESETS, write_reference
from market_hockey.powerups import registry
from market_hockey.powerups.types import BUILTIN

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "market_hockey"
REPO = ROOT.parent


def imports_of(path):
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


# ---------------------------------------------------------------- config files
def test_shipped_settings_load_without_warnings():
    c = Config.load(ROOT / "config" / "settings.json")
    assert c.warnings == []
    raw = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
    assert raw["_meta"]["schema_version"] == SCHEMA_VERSION


def test_defaults_file_matches_the_schema():
    """If this fails: run `python -m market_hockey.config.generate_defaults`."""
    raw = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
    c = Config.load(ROOT / "config" / "defaults.json")
    assert raw["_meta"]["schema_version"] == SCHEMA_VERSION
    assert c.values == Config().values


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_presets_are_current_and_valid(name):
    path = ROOT / "config" / "presets" / f"{name}.json"
    c = Config.load(path)
    assert c.warnings == []
    assert c.values == Config(PRESETS[name]).values


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_values_are_real_settings_within_range(name):
    c = Config()
    for key, value in PRESETS[name].items():
        assert key in c.schema, key
        assert c.set(key, value)[2] is None, key


def test_config_reference_lists_every_setting(tmp_path):
    out = tmp_path / "ref.md"
    write_reference(out)
    text = out.read_text(encoding="utf-8")
    for key in get_schema():
        assert f"`{key}`" in text, key


def test_committed_config_reference_is_up_to_date(tmp_path):
    """If this fails: run `python -m market_hockey.config.generate_defaults`."""
    out = tmp_path / "ref.md"
    write_reference(out)
    assert out.read_text(encoding="utf-8") == (ROOT / "docs" / "CONFIG_REFERENCE.md").read_text(encoding="utf-8")


def test_generate_defaults_writes_everything(tmp_path, monkeypatch):
    from market_hockey.config import generate_defaults as gd

    monkeypatch.setattr(gd, "DEFAULTS_PATH", tmp_path / "defaults.json")
    monkeypatch.setattr(gd, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(gd, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(gd, "DOCS_DIR", tmp_path / "docs")
    gd.main()
    assert (tmp_path / "defaults.json").exists() and (tmp_path / "settings.json").exists()
    assert (tmp_path / "docs" / "CONFIG_REFERENCE.md").exists()
    assert {p.stem for p in (tmp_path / "presets").glob("*.json")} == set(PRESETS)


def test_generate_defaults_never_overwrites_the_operators_settings(tmp_path, monkeypatch):
    from market_hockey.config import generate_defaults as gd

    keep = tmp_path / "settings.json"
    keep.write_text("mine", encoding="utf-8")
    monkeypatch.setattr(gd, "DEFAULTS_PATH", tmp_path / "defaults.json")
    monkeypatch.setattr(gd, "SETTINGS_PATH", keep)
    monkeypatch.setattr(gd, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(gd, "DOCS_DIR", tmp_path / "docs")
    gd.main()
    assert keep.read_text(encoding="utf-8") == "mine"


# ---------------------------------------------------------------- settings that name files or keys
def test_default_fonts_exist():
    schema = get_schema()
    fonts = [p for p in schema.values() if p.kind == "font"]
    assert fonts
    for p in fonts:
        assert (paths.FONTS_DIR / p.default).exists(), p.path


def test_default_keys_are_real_and_not_used_twice():
    import pygame

    pygame.init()
    keys = [p.default for p in get_schema().values() if p.kind == "key"]
    assert len(keys) == len(set(keys))
    for k in keys:
        pygame.key.key_code(k)


def test_default_colors_are_valid():
    for p in get_schema().values():
        if p.kind == "color":
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", p.default), p.path


def test_persian_defaults_use_latin_digits():
    for p in get_schema().values():
        if p.kind == "str":
            assert not re.search(r"[۰-۹٠-٩]", p.default), p.path


def test_setting_labels_are_unique_within_their_group():
    seen = set()
    for p in get_schema().values():
        key = (p.tab, p.group, p.label)
        assert key not in seen, key
        seen.add(key)


# ---------------------------------------------------------------- power-ups
def test_builtin_list_matches_the_files():
    """Packaged builds that cannot list modules rely on this list."""
    files = {f.stem for f in (PKG / "powerups" / "types").glob("*.py") if not f.stem.startswith("_")}
    assert set(BUILTIN) == files


@pytest.mark.parametrize("tid,t", sorted(registry.all_types().items()))
def test_power_up_types_are_complete(tid, t):
    assert t.id == tid and t.name and t.icon
    schema = get_schema()
    for field in ("enabled", "class"):
        assert f"powerups.types.{tid}.{field}" in schema


def test_power_up_order_is_unique():
    orders = [t.order for t in registry.all_types().values()]
    assert len(orders) == len(set(orders))


# ---------------------------------------------------------------- the walls between modules
@pytest.mark.parametrize("sub", ["core", "prediction", "powerups", "config", "web"])
def test_game_logic_never_imports_a_ui_library(sub):
    """The logic runs headless and is testable because of this rule. A sensor or a UI can be swapped freely."""
    for f in (PKG / sub).rglob("*.py"):
        assert not imports_of(f) & {"pygame", "tkinter", "numpy"}, f


def test_the_game_does_not_depend_on_the_control_panel():
    for f in PKG.rglob("*.py"):
        if "ui" not in f.relative_to(PKG).parts:
            assert "tkinter" not in imports_of(f), f


def test_the_engine_knows_nothing_about_sensors():
    for f in (PKG / "core").rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert "inputs" not in (node.module or ""), f
    src = (PKG / "core" / "engine.py").read_text(encoding="utf-8").lower()
    assert "socket" not in src and "lidar" not in src


def test_only_the_network_and_link_modules_open_sockets_for_input():
    users = {f.relative_to(PKG).as_posix() for f in PKG.rglob("*.py") if "socket" in imports_of(f)}
    assert users <= {"inputs/network.py", "inputs/lidar.py", "inputs/osc.py", "config/live_link.py", "web/server.py"}


def test_no_stray_debug_code():
    for f in PKG.rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert "breakpoint()" not in src and "pdb.set_trace" not in src, f


def test_every_module_imports_cleanly():
    import importlib

    for f in PKG.rglob("*.py"):
        rel = f.relative_to(ROOT).with_suffix("")
        parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        importlib.import_module(".".join(parts))


# ---------------------------------------------------------------- packaging and release
def test_version_is_set():
    assert re.fullmatch(r"\d+\.\d+\.\d+", market_hockey.__version__)


def test_build_recipe_collects_every_module_and_the_assets():
    spec = (ROOT / "packaging" / "MarketHockey.spec").read_text(encoding="utf-8")
    assert 'rglob("*.py")' in spec  # dynamic imports (input sources, power-ups) survive packaging
    assert '"assets"' in spec and "settings_app.py" in spec and "main.py" in spec


def test_test_tools_are_not_bundled():
    spec = (ROOT / "packaging" / "MarketHockey.spec").read_text(encoding="utf-8")
    assert '"pytest"' in spec


def test_workflow_runs_the_tests_before_building():
    wf = (REPO / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert wf.index("pytest") < wf.index("pyinstaller")
    assert "MarketHockey" in wf


def test_every_game_in_the_workflow_has_its_folder_and_recipe():
    wf = (REPO / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    pairs = re.findall(r"^\s*- folder: (\S+)\s*\n\s*app: (\S+)", wf, re.M)
    assert pairs
    for folder, app in pairs:
        assert (REPO / folder / "packaging" / f"{app}.spec").exists()
        assert (REPO / folder / "requirements-build.txt").exists()


def test_player_guide_ships():
    pdf = ROOT / "docs" / "MarketHockey_Guide_FA.pdf"
    assert pdf.exists() and pdf.read_bytes()[:4] == b"%PDF"


def test_web_page_ships_and_is_self_contained():
    html = (paths.ASSETS_DIR / "web" / "index.html").read_text(encoding="utf-8")
    assert "هاکی بازار" in html
    assert not re.search(r'(src|href)="https?://', html)  # the exhibition may have no internet


def test_real_logs_and_settings_backups_are_not_committed():
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "logs/" in gitignore and "settings.prev.json" in gitignore


# ---------------------------------------------------------------- READMEs
READMES = [REPO / "README.md", ROOT / "README.md"]


@pytest.mark.parametrize("readme", READMES, ids=["repo", "game"])
def test_readme_links_and_pictures_exist(readme):
    text = readme.read_text(encoding="utf-8")
    targets = re.findall(r'\]\(([^)#\s]+)[^)]*\)', text) + re.findall(r'src="([^"]+)"', text)
    local = [t for t in targets if not t.startswith(("http://", "https://"))]
    assert local
    for t in local:
        assert (readme.parent / t).exists(), t


@pytest.mark.parametrize("readme", READMES, ids=["repo", "game"])
def test_readme_section_links_exist(readme):
    text = readme.read_text(encoding="utf-8")
    slugs = {re.sub(r"[^\w\- ]", "", h.lower()).strip().replace(" ", "-") for h in re.findall(r"^#+ (.+)$", text, re.M)}
    for anchor in re.findall(r"\]\(#([^)]+)\)", text):
        assert anchor in slugs, anchor


def test_readme_numbers_are_true():
    """The brag has to stay honest as the game grows."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{len(get_schema())} settings" in text and f"every** setting ({len(get_schema())})" in text
    assert len(registry.all_types()) == 10 and "Ten power-ups" in text
    assert Config()["physics.hz"] == 240 and "240 Hz" in text
    tests = sum(len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8"), re.M)) for f in (ROOT / "tests").glob("test_*.py"))
    assert tests >= 300  # 650+ once parametrized


@pytest.mark.parametrize("readme", READMES, ids=["repo", "game"])
def test_readme_download_badge_shows_this_version(readme):
    """A private repo can't use a live release badge: the public badge service answers "repo not found"."""
    text = readme.read_text(encoding="utf-8")
    assert f"badge/download-v{market_hockey.__version__}-" in text and "shields.io/github/" not in text


def test_readme_test_table_names_real_files():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    named = set(re.findall(r"`(test_\w+\.py)`", text))
    real = {f.name for f in (ROOT / "tests").glob("test_*.py")}
    assert named <= real and {"test_input_contract.py", "test_tracking_protocol.py"} <= named


# ---------------------------------------------------------------- paths
def test_paths_from_source_point_at_the_project():
    assert paths.APP_DIR == ROOT and paths.SETTINGS_PATH == ROOT / "config" / "settings.json"
    assert paths.launch_command("game") == [sys.executable, str(ROOT / "main.py")]
    assert paths.launch_command("panel") == [sys.executable, str(ROOT / "settings_app.py")]


def test_frozen_paths_live_next_to_the_exe(tmp_path):
    """Settings must be saved beside the .exe, and F1 must launch the sibling exe, not a Python script."""
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.frozen = True; sys.executable = {str(tmp_path / 'MarketHockey.exe')!r}; sys._MEIPASS = {str(tmp_path / '_internal')!r}\n"
        "from market_hockey import paths\n"
        "print(json.dumps({'settings': str(paths.SETTINGS_PATH), 'bundle': str(paths.BUNDLE_DIR),\n"
        "                  'assets': str(paths.ASSETS_DIR), 'panel': paths.launch_command('panel'),\n"
        "                  'game': paths.launch_command('game')}))\n"
    )
    out = json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout)
    assert Path(out["settings"]) == tmp_path.resolve() / "config" / "settings.json"
    assert Path(out["bundle"]) == tmp_path / "_internal"
    assert Path(out["assets"]) == tmp_path / "_internal" / "assets"  # no assets/ beside the exe: use the bundled copy
    assert Path(out["panel"][0]).stem == "ControlPanel" and Path(out["game"][0]).stem == "MarketHockey"
    assert len(out["panel"]) == 1


def test_crash_log_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(sys, "__excepthook__", lambda *a: None)
    paths.install_crash_log("game")
    try:
        raise ValueError("boom")
    except ValueError as exc:
        sys.excepthook(ValueError, exc, exc.__traceback__)
    assert "ValueError: boom" in (tmp_path / "logs" / "game_crash.log").read_text(encoding="utf-8")


# ---------------------------------------------------------------- command line
def run_main(*args, seconds=120, encoding="utf-8"):
    env = {**__import__("os").environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
           "PYTHONIOENCODING": encoding}
    return subprocess.run([sys.executable, str(ROOT / "main.py"), *map(str, args)], capture_output=True, text=True,
                          encoding=encoding, errors="replace", env=env, timeout=seconds, cwd=str(ROOT))


def test_cli_exports_icons(tmp_path):
    r = run_main("--export-icons", tmp_path)
    assert r.returncode == 0, r.stderr
    assert {p.stem for p in tmp_path.glob("*.png")} == set(registry.all_types())


def test_cli_text_selftest(tmp_path):
    r = run_main("--selftest-text", tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "text_harfbuzz.png").exists() and (tmp_path / "text_reshaper.png").exists()


def test_cli_game_runs_and_quits(tmp_path):
    from conftest import free_udp_port

    path = tmp_path / "s.json"
    Config({"web.bind": "127.0.0.1", "web.port": free_udp_port(), "live_link.game_port": free_udp_port(),
            "web.open_browser": False, "debug.log_matches": False}).save(path)
    r = run_main("--windowed", "--seconds", "1", "--seed", "3", "--config", path)
    assert r.returncode == 0, r.stderr


def test_a_console_that_cannot_show_persian_does_not_stop_the_game(tmp_path):
    """Windows uses cp1252 when output is redirected. It has no Persian letters and no arrows."""
    from conftest import free_udp_port

    assert run_main("--help", encoding="cp1252").returncode == 0
    path = tmp_path / "s.json"
    Config({"web.bind": "127.0.0.1", "web.port": free_udp_port(), "live_link.game_port": free_udp_port(),
            "web.open_browser": False, "debug.log_matches": False}).save(path)
    r = run_main("--windowed", "--seconds", "1", "--seed", "3", "--config", path, encoding="cp1252")
    assert r.returncode == 0, r.stderr


def test_cli_help_mentions_every_tool():
    r = run_main("--help")
    assert r.returncode == 0
    for flag in ("--windowed", "--screenshot-states", "--export-icons", "--selftest-text"):
        assert flag in r.stdout


def test_settings_app_module_imports():
    code = f"import sys; sys.path.insert(0, {str(ROOT)!r}); import market_hockey.ui.settings_window as s; print(s.main.__name__)"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "main" in r.stdout
