from warden.tools import diagnostics_cli


def test_run_does_not_crash_without_roblox(bundled_config, monkeypatch, capsys):
    # The seeded user config is used by load_all(); point WARDEN_HOME is already
    # handled by the autouse fixture. Just make sure it never raises.
    assert diagnostics_cli.run() == 0
    out = capsys.readouterr().out
    assert "DPI awareness" in out
    assert "Roblox window" in out
    assert "OCR" in out
