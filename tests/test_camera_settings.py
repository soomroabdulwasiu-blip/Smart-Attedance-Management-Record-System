from amrs import settings

def test_mirror_preference_persists_and_handles_corrupt_file(tmp_path,monkeypatch):
    path=tmp_path/'ui_settings.json';monkeypatch.setattr(settings,'SETTINGS_PATH',path)
    assert settings.mirror_preview_enabled() is True
    settings.save_mirror_preview(False);assert settings.mirror_preview_enabled() is False
    settings.save_mirror_preview(True);assert settings.mirror_preview_enabled() is True
    path.write_text('{invalid',encoding='utf-8');assert settings.mirror_preview_enabled() is True
