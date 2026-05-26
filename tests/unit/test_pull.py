import json
from unittest.mock import MagicMock, patch

from geo_builder.designer.pull import pull


def _resp(body: bytes, content_type: str = "application/json") -> MagicMock:
    r = MagicMock()
    r.content = body
    r.raise_for_status = MagicMock()
    r.headers = {"Content-Type": content_type}
    return r


def _head(catalog_url: str = "./release/catalog.json") -> bytes:
    return json.dumps({"version": 1, "catalogUrl": catalog_url}).encode()


def _catalog(*manifest_urls: str) -> bytes:
    return json.dumps({"areas": [{"id": f"area{i}", "manifestUrl": url} for i, url in enumerate(manifest_urls)]}).encode()


def _manifest(*layer_urls: str) -> bytes:
    return json.dumps({"layers": [{"id": f"layer{i}", "url": url} for i, url in enumerate(layer_urls)]}).encode()


_GEOJSON = json.dumps({"type": "FeatureCollection", "features": []}).encode()


# ─── File layout ───────────────────────────────────────────────────────────────


class TestFileLayout:
    @patch("geo_builder.designer.pull.requests.get")
    def test_head_saved_at_root(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("no further fetches")
        head = json.dumps({"version": 1}).encode()
        mock_get.side_effect = lambda url, **kw: _resp(head) if "catalog.head.json" in url else (_ for _ in ()).throw(Exception("unexpected"))
        mock_get.side_effect = None
        mock_get.return_value = _resp(json.dumps({"version": 1}).encode())
        pull("http://svc", tmp_path)
        assert (tmp_path / "catalog.head.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_catalog_saved_at_path_matching_url(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head("./release/catalog.json")),
            "http://svc/catalog.head.debug.json": _resp(_head("./release/catalog.json")),
            "http://svc/release/catalog.json": _resp(_catalog()),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        assert (tmp_path / "release" / "catalog.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_manifest_saved_under_areas(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head()),
            "http://svc/catalog.head.debug.json": _resp(_head()),
            "http://svc/release/catalog.json": _resp(_catalog("../areas/napoli/manifest.json")),
            "http://svc/areas/napoli/manifest.json": _resp(_manifest()),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        assert (tmp_path / "areas" / "napoli" / "manifest.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_layer_saved_under_layers(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head()),
            "http://svc/catalog.head.debug.json": _resp(_head()),
            "http://svc/release/catalog.json": _resp(_catalog("../areas/napoli/manifest.json")),
            "http://svc/areas/napoli/manifest.json": _resp(_manifest("./layers/restaurants.geojson")),
            "http://svc/areas/napoli/layers/restaurants.geojson": _resp(_GEOJSON),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        assert (tmp_path / "areas" / "napoli" / "layers" / "restaurants.geojson").exists()


# ─── URL resolution ─────────────────────────────────────────────────────────────


class TestUrlResolution:
    @patch("geo_builder.designer.pull.requests.get")
    def test_catalog_url_resolved_relative_to_head(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head("./v2/catalog.json")),
            "http://svc/catalog.head.debug.json": _resp(_head("./v2/catalog.json")),
            "http://svc/v2/catalog.json": _resp(_catalog()),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        assert (tmp_path / "v2" / "catalog.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_manifest_url_resolved_relative_to_catalog(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head("./sub/catalog.json")),
            "http://svc/catalog.head.debug.json": _resp(_head("./sub/catalog.json")),
            "http://svc/sub/catalog.json": _resp(_catalog("../areas/napoli/manifest.json")),
            "http://svc/areas/napoli/manifest.json": _resp(_manifest()),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        assert (tmp_path / "areas" / "napoli" / "manifest.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_layer_url_resolved_relative_to_manifest(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head()),
            "http://svc/catalog.head.debug.json": _resp(_head()),
            "http://svc/release/catalog.json": _resp(_catalog("../areas/napoli/manifest.json")),
            "http://svc/areas/napoli/manifest.json": _resp(_manifest("./layers/foo.geojson")),
            "http://svc/areas/napoli/layers/foo.geojson": _resp(_GEOJSON),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        assert (tmp_path / "areas" / "napoli" / "layers" / "foo.geojson").exists()


# ─── Deduplication ─────────────────────────────────────────────────────────────


class TestDeduplication:
    @patch("geo_builder.designer.pull.requests.get")
    def test_same_catalog_not_fetched_twice(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head("./catalog.json")),
            "http://svc/catalog.head.debug.json": _resp(_head("./catalog.json")),
            "http://svc/catalog.json": _resp(_catalog()),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        calls = [c.args[0] for c in mock_get.call_args_list]
        assert calls.count("http://svc/catalog.json") == 1

    @patch("geo_builder.designer.pull.requests.get")
    def test_same_layer_shared_between_areas_fetched_once(self, mock_get, tmp_path):
        shared_layer = "http://svc/areas/shared/layers/common.geojson"
        responses = {
            "http://svc/catalog.head.json": _resp(_head()),
            "http://svc/catalog.head.debug.json": _resp(_head()),
            "http://svc/release/catalog.json": _resp(
                _catalog(
                    "../areas/a/manifest.json",
                    "../areas/b/manifest.json",
                )
            ),
            "http://svc/areas/a/manifest.json": _resp(_manifest("../shared/layers/common.geojson")),
            "http://svc/areas/b/manifest.json": _resp(_manifest("../shared/layers/common.geojson")),
            "http://svc/areas/shared/layers/common.geojson": _resp(_GEOJSON),
        }
        mock_get.side_effect = lambda url, **kw: responses[url]
        pull("http://svc", tmp_path)
        calls = [c.args[0] for c in mock_get.call_args_list]
        assert calls.count(shared_layer) == 1


# ─── Error handling ─────────────────────────────────────────────────────────────


class TestDefaultHead:
    @patch("geo_builder.designer.pull.requests.get")
    def test_missing_release_head_writes_default(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("404")
        pull("http://svc", tmp_path)
        assert (tmp_path / "catalog.head.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_missing_debug_head_writes_default(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("404")
        pull("http://svc", tmp_path)
        assert (tmp_path / "catalog.head.debug.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_default_release_head_catalog_url(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("404")
        pull("http://svc", tmp_path)
        payload = json.loads((tmp_path / "catalog.head.json").read_text())
        assert payload["catalogUrl"] == "./catalog.json"

    @patch("geo_builder.designer.pull.requests.get")
    def test_default_debug_head_catalog_url(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("404")
        pull("http://svc", tmp_path)
        payload = json.loads((tmp_path / "catalog.head.debug.json").read_text())
        assert payload["catalogUrl"] == "./catalog.debug.json"

    @patch("geo_builder.designer.pull.requests.get")
    def test_existing_head_not_overwritten_on_404(self, mock_get, tmp_path):
        custom = {"version": 1, "catalogUrl": "./custom/catalog.json"}
        (tmp_path / "catalog.head.json").write_text(json.dumps(custom))
        mock_get.side_effect = Exception("404")
        pull("http://svc", tmp_path)
        payload = json.loads((tmp_path / "catalog.head.json").read_text())
        assert payload["catalogUrl"] == "./custom/catalog.json"


class TestErrorHandling:
    @patch("geo_builder.designer.pull.requests.get")
    def test_missing_head_does_not_crash(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("404")
        pull("http://svc", tmp_path)  # must not raise

    @patch("geo_builder.designer.pull.requests.get")
    def test_second_head_processed_when_first_fails(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": Exception("404"),
            "http://svc/catalog.head.debug.json": _resp(_head("./debug/catalog.json")),
            "http://svc/debug/catalog.json": _resp(_catalog()),
        }
        mock_get.side_effect = lambda url, **kw: (_ for _ in ()).throw(responses[url]) if isinstance(responses[url], Exception) else responses[url]
        pull("http://svc", tmp_path)
        assert (tmp_path / "debug" / "catalog.json").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_failed_layer_fetch_does_not_crash(self, mock_get, tmp_path):
        responses = {
            "http://svc/catalog.head.json": _resp(_head()),
            "http://svc/catalog.head.debug.json": _resp(_head()),
            "http://svc/release/catalog.json": _resp(_catalog("../areas/napoli/manifest.json")),
            "http://svc/areas/napoli/manifest.json": _resp(_manifest("./layers/foo.geojson")),
            "http://svc/areas/napoli/layers/foo.geojson": Exception("timeout"),
        }
        mock_get.side_effect = lambda url, **kw: (_ for _ in ()).throw(responses[url]) if isinstance(responses[url], Exception) else responses[url]
        pull("http://svc", tmp_path)  # must not raise
        assert not (tmp_path / "areas" / "napoli" / "layers" / "foo.geojson").exists()

    @patch("geo_builder.designer.pull.requests.get")
    def test_head_without_catalog_url_stops_gracefully(self, mock_get, tmp_path):
        mock_get.return_value = _resp(json.dumps({"version": 1}).encode())
        pull("http://svc", tmp_path)
        calls = [c.args[0] for c in mock_get.call_args_list]
        assert all("catalog.head" in u for u in calls)
