import json
import sys
import threading
import urllib.error
import urllib.request

import pytest

import runtime


def test_the_choices_follow_the_hardware(monkeypatch):
    monkeypatch.setattr(runtime, "apple_silicon", lambda: False)
    monkeypatch.setattr(runtime, "nvidia", lambda: True)
    assert [c["id"] for c in runtime.choices()] == ["cuda", "cpu"]
    monkeypatch.setattr(runtime, "nvidia", lambda: False)
    assert [c["id"] for c in runtime.choices()] == ["cpu"]
    monkeypatch.setattr(runtime, "apple_silicon", lambda: True)
    assert [c["id"] for c in runtime.choices()] == ["mps"]


def test_a_choice_this_computer_cannot_use_is_refused(monkeypatch):
    monkeypatch.setattr(runtime, "apple_silicon", lambda: False)
    monkeypatch.setattr(runtime, "nvidia", lambda: False)
    with pytest.raises(ValueError):
        runtime.start("cuda")


def test_a_download_made_while_the_app_ran_is_taken_on_the_next_start(monkeypatch, tmp_path):
    monkeypatch.setenv("EMA_READER_RUNTIME", str(tmp_path))
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "old.txt").write_text("")
    (tmp_path / "site.new" / "yenipaket").mkdir(parents=True)
    (tmp_path / "site.new" / "yenipaket" / "__init__.py").write_text("NAME = 'yeni'\n")
    monkeypatch.setattr(sys, "path", list(sys.path))
    runtime.activate()
    assert not (tmp_path / "site.new").exists() and not (tmp_path / "site" / "old.txt").exists()
    assert sys.path[0] == str(tmp_path / "site")
    import yenipaket

    assert yenipaket.NAME == "yeni"
    del sys.modules["yenipaket"]


def test_before_the_download_speech_asks_for_it_and_only_the_app_may_start_it(monkeypatch, tmp_path):
    pytest.importorskip("numpy")
    import app

    monkeypatch.setenv("EMA_READER_RUNTIME", str(tmp_path))
    monkeypatch.setattr(runtime, "has_model", lambda: False)
    monkeypatch.setattr(app, "loading", threading.Event())
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as found:
            urllib.request.urlopen(f"{base}/tts?text=Merhaba")
        assert found.value.code == 503 and json.load(found.value)["setup"] is True

        status = json.load(urllib.request.urlopen(f"{base}/api/setup"))
        assert status["ready"] is False and status["choices"]

        request = urllib.request.Request(f"{base}/api/setup", data=b'{"choice": "cpu"}', method="POST")
        with pytest.raises(urllib.error.HTTPError) as found:
            urllib.request.urlopen(request)
        assert found.value.code == 403
    finally:
        server.shutdown()
