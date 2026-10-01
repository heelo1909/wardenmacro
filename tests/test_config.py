import shutil

import pytest
import yaml

from warden.__main__ import check_config
from warden.config import ConfigError, load_all, load_app_config, load_preset, save_model
from warden.config.loader import seed_user_config, user_config_path
from warden.config.schema import DETECTOR_NAMES, LaunchMode


def _copy_config(src, dst):
    shutil.copytree(src, dst)
    return dst / "default.yaml"


def test_bundled_default_config_validates(bundled_config):
    loaded = load_all(bundled_config / "default.yaml")
    assert loaded.preset_id == "glass_wrap"
    assert loaded.preset.contract.target_hours == 24
    assert loaded.preset.launch.mode is LaunchMode.public
    assert set(loaded.app.detectors) == set(DETECTOR_NAMES)


@pytest.mark.parametrize("name", ["default", "glass_wrap", "random"])
def test_every_bundled_preset_validates(bundled_config, name):
    preset = load_preset(bundled_config / "presets" / f"{name}.yaml")
    assert preset.launch.mode is LaunchMode.public  # public is the safe default everywhere


def test_seed_copies_defaults_once(bundled_config, warden_home):
    seed_user_config()
    cfg = user_config_path()
    assert cfg.exists()
    assert {p.stem for p in (warden_home / "presets").glob("*.yaml")} == {"default", "glass_wrap", "random"}
    cfg.write_text("active_preset: random\n", encoding="utf-8")
    seed_user_config()  # must not overwrite user edits
    assert cfg.read_text(encoding="utf-8") == "active_preset: random\n"
    assert load_all().preset_id == "random"


def test_reversed_roi_gives_readable_error(bundled_config, tmp_path):
    path = _copy_config(bundled_config, tmp_path / "cfg")
    data = yaml.safe_load(path.read_text())
    data["detectors"]["lobby_play"]["roi"] = [0.7, 0.7, 0.3, 0.98]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError) as info:
        load_app_config(path)
    text = str(info.value)
    assert "detectors.lobby_play.roi" in text
    assert "x1 (0.7) must be less than x2 (0.3)" in text


def test_typo_and_bad_types_listed_together(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("tick_rate: 5\ntimings:\n  tick_ms: fast\nrecovery:\n  prefer_button: maybe\n")
    with pytest.raises(ConfigError) as info:
        load_app_config(path)
    problems = info.value.problems
    assert any(p.startswith("tick_rate: unknown setting") for p in problems)
    assert any(p.startswith("timings.tick_ms:") for p in problems)
    assert any(p.startswith("recovery.prefer_button:") for p in problems)


def test_unknown_detector_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("detectors:\n  laser_beam:\n    method: frozen\n")
    with pytest.raises(ConfigError, match="unknown detector"):
        load_app_config(path)


def test_hsv_out_of_range(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("detectors:\n  health_bar:\n    hsv: [{lower: [0, 0, 0], upper: [200, 255, 255]}]\n")
    with pytest.raises(ConfigError, match="H=200 is outside 0..179"):
        load_app_config(path)


def test_yaml_syntax_error_reports_line(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("timings:\n  tick_ms: 250\n bad_indent: [\n")
    with pytest.raises(ConfigError, match=r"line \d+"):
        load_app_config(path)


def test_share_link_requires_code(tmp_path):
    path = tmp_path / "p.yaml"
    path.write_text("name: X\ncontract: {label: X}\nlaunch: {mode: share_link}\n")
    with pytest.raises(ConfigError, match="share_code is empty"):
        load_preset(path)


def test_missing_active_preset(bundled_config, tmp_path):
    path = _copy_config(bundled_config, tmp_path / "cfg")
    path.write_text(path.read_text().replace("active_preset: glass_wrap", "active_preset: nope"))
    with pytest.raises(ConfigError, match="'nope' not found"):
        load_all(path)


def test_save_round_trip(bundled_config, tmp_path):
    app = load_app_config(bundled_config / "default.yaml")
    out = tmp_path / "saved.yaml"
    save_model(app, out)
    assert load_app_config(out) == app
    assert not list(tmp_path.glob(".saved.yaml.*.tmp"))


def test_cli_check_config(bundled_config, tmp_path, capsys):
    assert check_config(str(bundled_config / "default.yaml")) == 0
    bad = tmp_path / "bad.yaml"
    bad.write_text("observe_only: sometimes\n")
    assert check_config(str(bad)) == 2
    assert "observe_only" in capsys.readouterr().err
