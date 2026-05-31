import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from geo_builder.designer.data_pipeline import DataPipeline, PipelineResult


def _pipeline(out_dir: Path, in_dir: Path | None = None) -> DataPipeline:
    return DataPipeline(out_dir=out_dir, in_dir=in_dir)


def _mock_network(body: bytes, content_type: str = "application/json", cache_control: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.content = body
    headers = {"Content-Type": content_type}
    if cache_control is not None:
        headers["Cache-Control"] = cache_control
    resp.headers = headers
    resp.raise_for_status = MagicMock()
    return resp


def _collect(pipeline: DataPipeline, url: str, timeout: float = 5.0) -> PipelineResult | None:
    captured = []
    done = threading.Event()

    def complete(result):
        captured.append(result)
        done.set()

    pipeline.handle(url, complete)
    assert done.wait(timeout=timeout), "handle never called complete"
    return captured[0]


# ─── L1 memory ────────────────────────────────────────────────────────────────


class TestMemory:
    def test_set_and_resolve(self, tmp_path):
        p = _pipeline(tmp_path)
        p.set("http://svc/areas/napoli/manifest.json", b'{"version":1}')
        r = p._resolve("http://svc/areas/napoli/manifest.json")
        assert r.data == b'{"version":1}'
        assert r.content_type == "application/json"
        assert r.cache_control == "no-store"

    def test_memory_beats_out_dir(self, tmp_path):
        (tmp_path / "file.json").write_bytes(b"from-disk")
        p = _pipeline(tmp_path)
        p.set("http://svc/file.json", b"from-memory")
        assert p._resolve("http://svc/file.json").data == b"from-memory"

    def test_path_derived_from_url(self, tmp_path):
        p = _pipeline(tmp_path)
        p.set("http://svc/a/b/c.json", b"abc")
        assert p._resolve("http://svc/a/b/c.json") is not None
        assert p._resolve("http://svc/x/y/z.json") is None


# ─── L2 out dir ───────────────────────────────────────────────────────────────


class TestOutDir:
    def test_file_served_from_out_dir(self, tmp_path):
        (tmp_path / "release").mkdir()
        (tmp_path / "release" / "catalog.json").write_bytes(b'{"areas":[]}')
        p = _pipeline(tmp_path)
        r = p._resolve("http://svc/release/catalog.json")
        assert r.data == b'{"areas":[]}'
        assert r.content_type == "application/json"
        assert r.cache_control == "no-store"

    def test_out_dir_beats_in_dir(self, tmp_path):
        out_dir = tmp_path / "out"
        in_dir = tmp_path / "in"
        (out_dir / "areas" / "napoli").mkdir(parents=True)
        (in_dir / "areas" / "napoli").mkdir(parents=True)
        (out_dir / "areas" / "napoli" / "manifest.json").write_bytes(b"from-out")
        (in_dir / "areas" / "napoli" / "manifest.json").write_bytes(b"from-in")
        p = _pipeline(out_dir, in_dir)
        assert p._resolve("http://svc/areas/napoli/manifest.json").data == b"from-out"


# ─── L3 in dir ────────────────────────────────────────────────────────────────


class TestInDir:
    def test_file_served_from_in_dir(self, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        in_dir = tmp_path / "in"
        (in_dir / "areas" / "napoli").mkdir(parents=True)
        (in_dir / "areas" / "napoli" / "manifest.json").write_bytes(b"from-in")
        p = _pipeline(out_dir, in_dir)
        r = p._resolve("http://svc/areas/napoli/manifest.json")
        assert r.data == b"from-in"
        assert r.cache_control == "no-store"

    def test_no_in_dir_skips_to_network(self, tmp_path):
        p = _pipeline(tmp_path, in_dir=None)
        with patch("geo_builder.designer.data_pipeline._session.get") as mock_get:
            mock_get.return_value = _mock_network(b"from-network", cache_control="max-age=3600")
            r = p._resolve("http://svc/missing.json")
        assert r.data == b"from-network"
        assert r.cache_control == "max-age=3600"


# ─── L4 network ───────────────────────────────────────────────────────────────


class TestNetwork:
    @patch("geo_builder.designer.data_pipeline._session.get")
    def test_network_cache_control_passed_through(self, mock_get, tmp_path):
        mock_get.return_value = _mock_network(b"tile", cache_control="max-age=523755")
        p = _pipeline(tmp_path)
        r = p._resolve("http://svc/tile.png")
        assert r.cache_control == "max-age=523755"

    @patch("geo_builder.designer.data_pipeline._session.get")
    def test_network_no_cache_control_when_server_omits(self, mock_get, tmp_path):
        mock_get.return_value = _mock_network(b"data")
        p = _pipeline(tmp_path)
        assert p._resolve("http://svc/missing.json").cache_control is None

    @patch("geo_builder.designer.data_pipeline._session.get")
    def test_network_content_type_preserved(self, mock_get, tmp_path):
        mock_get.return_value = _mock_network(b"...", "text/html; charset=utf-8")
        p = _pipeline(tmp_path)
        assert p._resolve("http://svc/page.html").content_type == "text/html"

    @patch("geo_builder.designer.data_pipeline._session.get")
    def test_network_error_returns_none(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("timeout")
        p = _pipeline(tmp_path)
        assert p._resolve("http://svc/missing.json") is None

    @patch("geo_builder.designer.data_pipeline._session.get")
    def test_no_write_back_to_in_dir(self, mock_get, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        in_dir = tmp_path / "in"
        in_dir.mkdir()
        mock_get.return_value = _mock_network(b"from-network")
        p = _pipeline(out_dir, in_dir)
        p._resolve("http://svc/areas/napoli/manifest.json")
        assert not (in_dir / "areas" / "napoli" / "manifest.json").exists()


# ─── handle ───────────────────────────────────────────────────────────────────


class TestHandle:
    def test_complete_called_with_result(self, tmp_path):
        (tmp_path / "file.json").write_bytes(b"data")
        p = _pipeline(tmp_path)
        result = _collect(p, "http://svc/file.json")
        assert result is not None
        assert result.data == b"data"
        assert result.cache_control == "no-store"

    def test_complete_called_with_none_on_miss(self, tmp_path):
        with patch("geo_builder.designer.data_pipeline._session.get") as mock_get:
            mock_get.side_effect = Exception("network error")
            p = _pipeline(tmp_path)
            result = _collect(p, "http://svc/missing.json")
        assert result is None

    def test_complete_always_called_even_on_exception(self, tmp_path):
        p = _pipeline(tmp_path)
        with patch.object(p, "_resolve", side_effect=RuntimeError("boom")):
            result = _collect(p, "http://svc/anything")
        assert result is None
