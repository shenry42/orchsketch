"""Milestone 6: the packaged app. The build script bundles the data files, FluidSynth and the SoundFont, and
the built app's self-check (`OrchSketch.exe --self-check`) passes. Audio isn't opened here."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_build_script_bundles_everything():
    bat = (ROOT / "scripts" / "build_exe.bat").read_text(encoding="utf-8")
    assert "--onedir" in bat and "--windowed" in bat and "--name OrchSketch" in bat
    assert r'--add-data "%ROOT%\src\orchsketch\data;orchsketch\data"' in bat  # the loaders read it next to the package
    assert r'--add-binary "%DLLDIR%\*.dll;fluidsynth"' in bat
    assert r'GeneralUser-GS.sf2;soundfonts"' in bat
    assert "--hidden-import fluidsynth" in bat and "--self-check" in bat
    assert r"scripts\orchsketch_main.py" in bat and (ROOT / "scripts" / "orchsketch_main.py").exists()
    assert b"\r\n" in (ROOT / "scripts" / "build_exe.bat").read_bytes()  # Windows line endings


def test_every_data_file_is_inside_the_bundled_folder():
    from orchsketch.instruments import DATA_DIR
    assert DATA_DIR == ROOT / "src" / "orchsketch" / "data"
    files = {p.relative_to(DATA_DIR).as_posix() for p in DATA_DIR.rglob("*.json")}
    assert {"rules.json", "presets.json"} <= files and len([f for f in files if f.startswith("instruments/")]) == 22


def test_self_check_without_audio(tmp_path):
    from orchsketch.selfcheck import run
    ok, text = run(audio=False, log=tmp_path / "self_check.txt", synth=False)
    assert ok, text
    assert (tmp_path / "self_check.txt").read_text(encoding="utf-8").strip().endswith("SELF-CHECK OK")
    for name in ("Data files", "Generator", "Export", "Project"):
        assert f"PASS  {name}" in text


def test_app_routes_self_check_before_any_window(monkeypatch):
    import orchsketch.selfcheck as sc
    from orchsketch import app
    seen = []
    monkeypatch.setattr(sc, "main", lambda argv: seen.append(list(argv)) or 0)
    monkeypatch.setattr(sys, "argv", ["OrchSketch.exe", "--self-check"])
    assert app.main() == 0 and seen == [["OrchSketch.exe", "--self-check"]]
