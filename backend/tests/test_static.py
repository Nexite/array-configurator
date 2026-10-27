from pathlib import Path

from fastapi.testclient import TestClient

from app.main import STATIC, create_app


def test_root_serves_spa(tmp_path, monkeypatch):
    STATIC.mkdir(parents=True, exist_ok=True)
    index = STATIC / "index.html"
    existed = index.exists()
    previous = index.read_text() if existed else None
    index.write_text("<html><title>Array Configurator</title></html>")
    try:
        client = TestClient(create_app())
        r = client.get("/")
        assert r.status_code == 200
        assert b"Array Configurator" in r.content
    finally:
        if existed and previous is not None:
            index.write_text(previous)
        elif index.exists() and not existed:
            index.unlink()
