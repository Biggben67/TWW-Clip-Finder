import json

import pytest

import portable_bootstrap as bootstrap


def test_bootstrap_rejects_non_japanese_disc(tmp_path):
    iso = tmp_path / "wrong.iso"
    iso.write_bytes(b"GZLE01")
    with pytest.raises(ValueError, match="Japanese Wind Waker"):
        bootstrap.ensure_animation_cache(iso, tmp_path / "anim")


def test_bootstrap_extracts_once_and_keeps_iso_private(tmp_path, monkeypatch):
    from harness.anim import parse_bck, parse_bmd

    iso = tmp_path / "game.iso"
    iso.write_bytes(b"GZLJ11")
    calls = []

    def object_arc(path, name):
        calls.append(name)
        return name.encode("ascii")

    def animations(raw, *, outdir):
        assert raw == b"LkAnm"
        for name in bootstrap.ANIMATION_FILES[:3]:
            (tmp_path / "anim" / name).write_text("{}", encoding="ascii")

    def skeleton(raw, *, outdir):
        assert raw == b"Link"
        (tmp_path / "anim" / bootstrap.ANIMATION_FILES[3]).write_text("{}", encoding="ascii")

    monkeypatch.setattr(parse_bck, "_gcm_read_object_arc", object_arc)
    monkeypatch.setattr(parse_bck, "extract_animation_sets", animations)
    monkeypatch.setattr(parse_bmd, "_gcm_read_object_arc", object_arc)
    monkeypatch.setattr(parse_bmd, "extract_skeleton", skeleton)

    cache = tmp_path / "anim"
    assert bootstrap.ensure_animation_cache(iso, cache)
    assert calls == ["LkAnm", "Link"]
    assert not bootstrap.ensure_animation_cache(iso, cache)
    assert calls == ["LkAnm", "Link"]
    assert bootstrap.main(["--iso", str(iso), "--cache-dir", str(cache)]) == 0
    assert json.loads((tmp_path / "portable_iso.json").read_text())["iso"] == str(iso)
    assert bootstrap.load_selected_iso(tmp_path / "portable_iso.json") == str(iso)
