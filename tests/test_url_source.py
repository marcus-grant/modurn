"""Tests for the direct-URL source: filename resolution + real download/skip."""

from __future__ import annotations

import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from modurn.models import Mod
from modurn.sources.url import UrlSource, filename_from_response


def test_filename_from_content_disposition():
    assert filename_from_response('attachment; filename="Mod-1.2.zip"', "http://x/y") == "Mod-1.2.zip"
    assert filename_from_response("attachment; filename*=UTF-8''My%20Mod.7z", "http://x/y") == "My Mod.7z"


def test_filename_falls_back_to_url_basename():
    assert filename_from_response(None, "https://host/path/thing.zip?token=abc") == "thing.zip"
    assert filename_from_response(None, "https://host/") == "download.bin"


def _serve(directory: Path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def test_url_fetch_downloads_then_skips(tmp_path: Path):
    served = tmp_path / "served"
    served.mkdir()
    (served / "cool-mod.zip").write_bytes(b"PK\x03\x04 pretend archive")

    httpd = _serve(served)
    try:
        port = httpd.server_address[1]
        mod = Mod(name="Cool", source="url", url=f"http://127.0.0.1:{port}/cool-mod.zip")
        dest = tmp_path / "dl"

        first = UrlSource().fetch(mod, dest)
        assert len(first) == 1
        assert first[0].from_cache is False
        assert first[0].path.name == "cool-mod.zip"
        assert first[0].path.read_bytes().startswith(b"PK")

        # Second call reuses the file (resume-by-skip), no re-download.
        second = UrlSource().fetch(mod, dest)
        assert second[0].from_cache is True
        assert second[0].path == first[0].path
    finally:
        httpd.shutdown()
