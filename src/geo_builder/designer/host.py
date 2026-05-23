from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.parse import urlparse

import webview

from ..diagnostics import ConsoleLogSink, Logger, TelemetryLevel
from ..entities import GeoCatalog
from .data_pipeline import DataPipeline
from .gateway import Gateway
from .pull import pull as _pull

_DEBUG_PORT = 9222
_HEAD_FILE = "catalog.head.json"
_STARTUP_HTML = Path(__file__).parent / "startup.html"
_STARTUP_JS = Path(__file__).parent / "startup.js"

_core = None
_form = None
api: Gateway | None = None
data_pipeline: DataPipeline | None = None
_api_ready = threading.Event()


def invoke_script(script: str) -> None:
    if _core is None or _form is None:
        Logger.warning("invoke_script: WebView2 not ready.")
        return
    from System import Action  # type: ignore[import]

    _form.BeginInvoke(Action(lambda: _core.ExecuteScriptAsync(script)))


# --- CoreWebView2 event handlers (fire on WebView2 browser/UI thread) ---


def _on_navigation_completed(sender, args) -> None:  # noqa: ANN001
    Logger.info(f"NavigationCompleted: success={args.IsSuccess} url={sender.Source}")


def _on_web_resource_requested(_, args) -> None:  # noqa: ANN001
    url = str(args.Request.Uri)
    # Logger.info(f"WebResourceRequested: {url}")
    if data_pipeline is not None:
        deferral = args.GetDeferral()

        def complete(result: tuple[bytes, str] | None) -> None:
            def on_ui() -> None:
                try:
                    if result is not None:
                        data, content_type = result
                        from System.IO import MemoryStream  # type: ignore[import]

                        stream = MemoryStream(bytearray(data))
                        headers = f"Content-Type: {content_type}\r\nAccess-Control-Allow-Origin: *"
                        args.Response = _core.Environment.CreateWebResourceResponse(stream, 200, "OK", headers)
                except Exception as exc:
                    Logger.warning(f"data pipeline: response error: {exc}")
                finally:
                    deferral.Complete()

            from System import Action  # type: ignore[import]

            _form.BeginInvoke(Action(on_ui))

        data_pipeline.handle(url, complete)


def _on_window_close_requested(*_) -> None:
    Logger.info("WindowCloseRequested")


def _on_web_message_received(_, args) -> None:  # noqa: ANN001
    raw = args.TryGetWebMessageAsString()
    Logger.info(f"WebMessageReceived: {raw}")
    if api is not None:
        api._on_message(raw)


def _normalize_bbox(bbox: list[float]) -> list[float]:
    """Normalize bbox longitudes to [-180, 180). Browsers can send values outside this range when the map is panned past the antimeridian."""

    def norm(lon: float) -> float:
        return ((lon + 180) % 360) - 180

    return [norm(bbox[0]), bbox[1], norm(bbox[2]), bbox[3]]


def _register_designer_handlers(api: Gateway, catalog: GeoCatalog, out_dir: Path, in_dir: Path | None, debug: bool) -> None:
    from ..api import (
        ADD_AREA_ID,
        ERR_AREA_NOT_FOUND,
        ERR_IO,
        ERR_MANIFEST_INVALID,
        ERR_TEMPLATE_NOT_FOUND,
        GET_AREA_JSON_ID,
        OK,
        PUT_AREA_JSON_ID,
        SET_AREA_BBOX_ID,
        AddAreaInput,
        AddAreaOutput,
        AreaSummary,
        GetAreaJsonInput,
        GetAreaJsonOutput,
        PutAreaJsonInput,
        PutAreaJsonOutput,
        SetAreaBboxInput,
        SetAreaBboxOutput,
    )
    from ..builder import Builder
    from ..contracts import AcquisitionTask, AggregationTask, BoundingBox, DedupingTask, PoiTask
    from ..entities import GeoLayer
    from ..errors import GeoError
    from ..persistence import load_catalog, save_catalog, save_catalog_meta
    from ..protocols import Manifest, PipelineStep
    from ..settings import Settings

    api.define_method(SET_AREA_BBOX_ID, SetAreaBboxInput, SetAreaBboxOutput)

    def on_set_area_bbox(data: SetAreaBboxInput) -> SetAreaBboxOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return SetAreaBboxOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found")

        area.bbox = _normalize_bbox(list(data.bbox))

        if in_dir is not None:
            save_catalog_meta(catalog, in_dir, debug=debug)
            try:
                fresh_catalog = load_catalog(in_dir, debug=debug)
            except GeoError:
                fresh_catalog = catalog
        else:
            fresh_catalog = catalog

        for a in fresh_catalog.areas:
            if a.id == data.areaId:
                a.layers.clear()
                break

        result = Builder(fresh_catalog).run()
        save_catalog(result, out_dir, debug=debug)

        return SetAreaBboxOutput(error=OK)

    api.register(SET_AREA_BBOX_ID, on_set_area_bbox)

    api.define_method(ADD_AREA_ID, AddAreaInput, AddAreaOutput)

    def on_add_area(data: AddAreaInput) -> AddAreaOutput:
        settings = Settings.current()
        template = settings.templates.get(data.template)
        if template is None:
            return AddAreaOutput(
                error=ERR_TEMPLATE_NOT_FOUND,
                errorDescription=f"Template '{data.template}' not found in tasks file",
            )

        area_id = GeoLayer.id_from_merge_key(data.areaName)
        bbox = _normalize_bbox(list(data.bbox))  # [west, south, east, north]

        acquisition_task = AcquisitionTask(
            areaId=area_id,
            areaName=data.areaName,
            provider=template.provider,
            bbox=BoundingBox(west=bbox[0], south=bbox[1], east=bbox[2], north=bbox[3]),
            filters=template.filters,
        )
        tasks = [acquisition_task, AggregationTask(), DedupingTask(), PoiTask()]

        if in_dir is not None:
            try:
                fresh_catalog = load_catalog(in_dir, debug=debug)
            except GeoError:
                fresh_catalog = catalog
        else:
            fresh_catalog = catalog

        result = Builder(fresh_catalog).run(tasks=tasks)
        save_catalog(result, out_dir, debug=debug)
        if in_dir is not None:
            save_catalog(result, in_dir, debug=debug)

        catalog.areas[:] = result.areas

        new_area = None
        for a in result.areas:
            if a.id == area_id:
                new_area = a
                break

        if new_area is not None:
            if new_area.detail is None:
                new_area.detail = Manifest(version=1)
            acq_steps = [s for s in new_area.detail.tasks if s.type == "acquisition"]
            new_area.detail.tasks = acq_steps + [
                PipelineStep(type="aggregation"),
                PipelineStep(type="deduping"),
            ]

        area_summary = None
        if new_area is not None:
            area_summary = AreaSummary(
                id=new_area.id,
                name=new_area.name,
                bbox=new_area.bbox,
                minRadiusPx=new_area.minRadiusPx,
                maxRadiusPx=new_area.maxRadiusPx,
                liveMapRadiusPx=new_area.liveMapRadiusPx,
                manifestUrl=new_area.manifestUrl,
            )

        return AddAreaOutput(error=OK, area=area_summary)

    api.register(ADD_AREA_ID, on_add_area)

    api.define_method(GET_AREA_JSON_ID, GetAreaJsonInput, GetAreaJsonOutput)

    def on_get_area_json(data: GetAreaJsonInput) -> GetAreaJsonOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return GetAreaJsonOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found")

        return GetAreaJsonOutput(error=OK, manifest=area.to_manifest_dict())

    api.register(GET_AREA_JSON_ID, on_get_area_json)

    api.define_method(PUT_AREA_JSON_ID, PutAreaJsonInput, PutAreaJsonOutput)

    def on_put_area_json(data: PutAreaJsonInput) -> PutAreaJsonOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return PutAreaJsonOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found")

        try:
            area.apply_manifest(data.manifest, out_dir)
        except GeoError as exc:
            return PutAreaJsonOutput(error=ERR_MANIFEST_INVALID, errorDescription=str(exc))
        except OSError as exc:
            return PutAreaJsonOutput(error=ERR_IO, errorDescription=str(exc))

        return PutAreaJsonOutput(error=OK)

    api.register(PUT_AREA_JSON_ID, on_put_area_json)


def _setup(window: webview.Window, catalog: GeoCatalog, out_dir: Path, in_dir: Path | None, debug: bool) -> None:
    try:
        import webview.platforms.winforms as wf
        from System import Action  # type: ignore[import]

        form = wf.BrowserView.instances.get(window.uid)
        if form is None:
            Logger.warning("Setup: could not locate BrowserView instance.")
            return

        def on_ui_thread() -> None:
            global _core, _form, api, data_pipeline  # noqa: PLW0603
            wv2 = getattr(form, "webview", None) or getattr(form, "browser", None)
            if wv2 is None:
                Logger.warning("Setup: could not locate WebView2 control.")
                return
            _form = form
            _core = wv2.CoreWebView2
            _core.Settings.UserAgent = "GeoBrowser/1.0 (https://github.com/croicu/geo-browser)"

            edge = getattr(form, "browser", None)
            if edge is not None and hasattr(edge, "on_script_notify"):
                wv2.WebMessageReceived -= edge.on_script_notify

            script = _STARTUP_JS.read_text(encoding="utf-8")
            _core.AddScriptToExecuteOnDocumentCreatedAsync(script)
            _core.ExecuteScriptAsync(script)

            api = Gateway(invoke_script)
            catalog.register_handlers(api)
            _register_designer_handlers(api, catalog, out_dir, in_dir, debug)
            _api_ready.set()

            data_pipeline = DataPipeline(
                out_dir=out_dir,
                in_dir=in_dir,
            )

            from Microsoft.Web.WebView2.Core import CoreWebView2WebResourceContext  # type: ignore[import]

            _core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All)
            _core.NavigationCompleted += _on_navigation_completed
            _core.WebResourceRequested += _on_web_resource_requested
            _core.WindowCloseRequested += _on_window_close_requested
            _core.WebMessageReceived += _on_web_message_received

            Logger.info("Setup complete.")

        form.Invoke(Action(on_ui_thread))

    except Exception as exc:
        Logger.warning(f"Setup failed: {exc}")


def launch(
    url: str,
    catalog: GeoCatalog | None = None,
    out_dir: Path | None = None,
    in_dir: Path | None = None,
    debug: bool = False,
    break_on_load: bool = False,
    dev_tools: bool = False,
    log_level: TelemetryLevel = TelemetryLevel.ERROR,
) -> None:
    resolved_catalog = catalog if catalog is not None else GeoCatalog()
    resolved_out_dir = out_dir if out_dir is not None else Path("./out")

    if debug:
        args = f"--remote-debugging-port={_DEBUG_PORT}"
        if dev_tools:
            args += " --auto-open-devtools-for-tabs"
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = args

    if break_on_load:
        sep = "&" if "?" in url else "?"
        app_url = f"{url}{sep}break=1"
        template = _STARTUP_HTML.read_text(encoding="utf-8")
        html = template.replace("GEO_TARGET_URL", json.dumps(app_url))
        window = webview.create_window("Geo Designer", html=html)
    else:
        window = webview.create_window("Geo Designer", url)

    setup_done = False

    def on_loaded() -> None:
        nonlocal setup_done
        if not setup_done:
            setup_done = True

            def do_setup() -> None:
                _setup(window, resolved_catalog, resolved_out_dir, in_dir, debug)
                if not break_on_load and api is not None:
                    api.ready()

            threading.Thread(target=do_setup, daemon=True).start()
        else:
            Logger.info("Page loaded")
            if api is not None:
                api.ready()

    window.events.loaded += on_loaded

    def run_dispatcher() -> None:
        _api_ready.wait()
        api.run()  # type: ignore[union-attr]

    Logger.set_logger(ConsoleLogSink(min_level=log_level))
    try:
        if in_dir is not None and not (in_dir / _HEAD_FILE).exists():
            p = urlparse(url)
            origin = f"{p.scheme}://{p.netloc}"
            Logger.info(f"Pulling from {origin} into {in_dir}")
            in_dir.mkdir(parents=True, exist_ok=True)
            _pull(origin, in_dir)

        threading.Thread(target=run_dispatcher, daemon=True).start()
        Logger.info("WebView control starting.")
        webview.start()
        Logger.info("WebView control closed.")
        if api is not None:
            api.stop()
    finally:
        Logger.set_logger(None)
