import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from geo_builder.designer.data_pipeline import DataPipeline


def _pipeline(out_dir: Path, in_dir: Path | None = None) -> DataPipeline:
    return DataPipeline(out_dir=out_dir, in_dir=in_dir)


def _mock_network(body: bytes, content_type: str = "application/json") -> MagicMock:
    resp = MagicMock()
    resp.content = body
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = MagicMock()
    return resp


def _collect(pipeline: DataPipeline, url: str, timeout: float = 5.0) -> tuple[bytes, str] | None:
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
        data, ct = p._resolve("http://svc/areas/napoli/manifest.json")
        assert data == b'{"version":1}'
        assert ct == "application/json"

    def test_memory_beats_out_dir(self, tmp_path):
        (tmp_path / "file.json").write_bytes(b"from-disk")
        p = _pipeline(tmp_path)
        p.set("http://svc/file.json", b"from-memory")
        data, _ = p._resolve("http://svc/file.json")
        assert data == b"from-memory"

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
        data, ct = p._resolve("http://svc/release/catalog.json")
        assert data == b'{"areas":[]}'
        assert ct == "application/json"

    def test_out_dir_beats_in_dir(self, tmp_path):
        out_dir = tmp_path / "out"
        in_dir = tmp_path / "in"
        (out_dir / "areas" / "napoli").mkdir(parents=True)
        (in_dir / "areas" / "napoli").mkdir(parents=True)
        (out_dir / "areas" / "napoli" / "manifest.json").write_bytes(b"from-out")
        (in_dir / "areas" / "napoli" / "manifest.json").write_bytes(b"from-in")
        p = _pipeline(out_dir, in_dir)
        data, _ = p._resolve("http://svc/areas/napoli/manifest.json")
        assert data == b"from-out"


# ─── L3 in dir ────────────────────────────────────────────────────────────────

class TestInDir:
    def test_file_served_from_in_dir(self, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        in_dir = tmp_path / "in"
        (in_dir / "areas" / "napoli").mkdir(parents=True)
        (in_dir / "areas" / "napoli" / "manifest.json").write_bytes(b"from-in")
        p = _pipeline(out_dir, in_dir)
        data, _ = p._resolve("http://svc/areas/napoli/manifest.json")
        assert data == b"from-in"

    def test_no_in_dir_skips_to_network(self, tmp_path):
        p = _pipeline(tmp_path, in_dir=None)
        with patch("geo_builder.designer.data_pipeline._session.get") as mock_get:
            mock_get.return_value = _mock_network(b"from-network")
            data, _ = p._resolve("http://svc/missing.json")
        assert data == b"from-network"


# ─── L4 network ───────────────────────────────────────────────────────────────

class TestNetwork:
    @patch("geo_builder.designer.data_pipeline._session.get")
    def test_network_hit_when_all_miss(self, mock_get, tmp_path):
        mock_get.return_value = _mock_network(b"from-network")
        p = _pipeline(tmp_path)
        data, _ = p._resolve("http://svc/missing.json")
        assert data == b"from-network"

    @patch("geo_builder.designer.data_pipeline._session.get")
    def test_network_content_type_preserved(self, mock_get, tmp_path):
        mock_get.return_value = _mock_network(b"...", "text/html; charset=utf-8")
        p = _pipeline(tmp_path)
        _, ct = p._resolve("http://svc/page.html")
        assert ct == "text/html"

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
        data, ct = result
        assert data == b"data"

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
