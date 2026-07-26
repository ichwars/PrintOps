from spoolbuddy import daemon


def test_spoolbuddy_version_prefers_environment(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.2.6rc6")

    assert daemon._read_app_version() == "1.2.6rc6"


def test_spoolbuddy_version_reads_root_version_file(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(daemon, "_ROOT", tmp_path)
    (tmp_path / "VERSION").write_text("1.2.6rc7\n", encoding="utf-8")

    assert daemon._read_app_version() == "1.2.6rc7"


def test_spoolbuddy_version_reads_default_config_version(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(daemon, "_ROOT", tmp_path)
    config_path = tmp_path / "backend" / "app" / "core" / "config.py"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('_DEFAULT_APP_VERSION = "1.2.6rc8"\n', encoding="utf-8")

    assert daemon._read_app_version() == "1.2.6rc8"
