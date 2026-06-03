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


def MethodResult(output):
    if output.error != 0:
        Logger.warning(f"{type(output).__name__}: error {output.error} — {output.errorDescription}")
    return output


def _apply_template_style(geo_layer, tlayer: dict) -> None:
    """Merge template style fields over the layer's style so the template takes precedence."""
    template_style = tlayer.get("style", {})
    if not isinstance(template_style, dict):
        return
    for k, v in template_style.items():
        geo_layer.layer.style[k] = v


def _acquisition_matches(layer_acq: dict, template_acq: dict | None) -> bool:
    if template_acq is None:
        return False
    if layer_acq.get("provider") != template_acq.get("provider"):
        return False
    layer_filters = layer_acq.get("filters", {})
    template_filters = template_acq.get("filters", {})
    if not layer_filters or set(layer_filters.keys()) != set(template_filters.keys()):
        return False
    for key, layer_vals in layer_filters.items():
        template_vals = template_filters.get(key, [])
        if sorted(layer_vals) != sorted(template_vals):
            return False
    return True


def _build_user_stub(tmpl: dict):
    from ..entities import GeoLayer
    from ..protocols import Layer, UserStyle

    user_style = UserStyle()
    for tlayer in tmpl.get("layers", []):
        if tlayer.get("id") == "__user__":
            s = tlayer.get("style", {})
            user_style = UserStyle(
                name=str(tlayer.get("name", "My Trip")),
                color=str(s.get("color", "#9E9E9E")),
                opacity=float(s.get("opacity", 0.9)),
                radius=float(s.get("radius", 10.0)),
                min_zoom=float(s.get("minZoom", 14.0)),
            )
            break
    return GeoLayer(
        Layer(
            id="__user__",
            name=user_style.name,
            type="__user__",
            visible=True,
            style={
                "opacity": user_style.opacity,
                "color": user_style.color,
                "radius": user_style.radius,
                "minZoom": user_style.min_zoom,
            },
        )
    )


def _inject_missing_user_layers(catalog: GeoCatalog, tmpl: dict, in_dir: Path | None) -> None:
    """Ensure every area in the catalog has a __user__ layer stub.

    Injects the stub into memory and, when in_dir is provided, saves the area's
    manifest so subsequent loads include the layer.
    """
    for area in catalog.areas:
        has_user = False
        for gl in area.layers:
            if gl.layer.id == "__user__":
                has_user = True
                break
        if not has_user:
            area.layers.append(_build_user_stub(tmpl))
            Logger.info(f"_inject_missing_user_layers: added __user__ stub to area '{area.id}'.")
            if in_dir is not None:
                try:
                    area.save(in_dir)
                except OSError as exc:
                    Logger.warning(f"_inject_missing_user_layers: failed to save manifest for area '{area.id}': {exc}")


def _build_void_stub(tmpl: dict):
    from ..entities import GeoLayer
    from ..protocols import Layer, VoidStyle

    void_style = VoidStyle()
    for tlayer in tmpl.get("layers", []):
        if tlayer.get("id") == "__void__":
            s = tlayer.get("style", {})
            void_style = VoidStyle(
                name=str(tlayer.get("name", "Mundane")),
                color=str(s.get("color", "#1f1f1f")),
                opacity=float(s.get("opacity", 0.9)),
            )
            break
    return GeoLayer(
        Layer(
            id="__void__",
            name=void_style.name,
            type="__void__",
            visible=False,
            style={
                "opacity": void_style.opacity,
                "color": void_style.color,
            },
        )
    )


def _inject_missing_void_layers(catalog: GeoCatalog, tmpl: dict, in_dir: Path | None) -> None:
    """Ensure every area in the catalog has a __void__ layer stub.

    Injects the stub into memory and, when in_dir is provided, saves the area's
    manifest so subsequent loads include the layer.
    """
    for area in catalog.areas:
        has_void = False
        for gl in area.layers:
            if gl.layer.id == "__void__":
                has_void = True
                break
        if not has_void:
            area.layers.append(_build_void_stub(tmpl))
            Logger.info(f"_inject_missing_void_layers: added __void__ stub to area '{area.id}'.")
            if in_dir is not None:
                try:
                    area.save(in_dir)
                except OSError as exc:
                    Logger.warning(f"_inject_missing_void_layers: failed to save manifest for area '{area.id}': {exc}")


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
    Logger.diagnostic(f"WebResourceRequested: {url}")
    if data_pipeline is not None:
        deferral = args.GetDeferral()

        def complete(result) -> None:  # noqa: ANN001
            def on_ui() -> None:
                try:
                    if result is not None:
                        from System.IO import MemoryStream  # type: ignore[import]

                        stream = MemoryStream(bytearray(result.data))
                        headers = f"Content-Type: {result.content_type}\r\nAccess-Control-Allow-Origin: *"
                        if result.cache_control is not None:
                            headers += f"\r\nCache-Control: {result.cache_control}"
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
    import re

    from ..api import (
        ADD_AREA_ID,
        ADD_USER_POINT_ID,
        AREA_CHANGED_ID,
        ERR_AREA_NOT_FOUND,
        ERR_IO,
        ERR_MANIFEST_INVALID,
        ERR_TEMPLATE_NOT_FOUND,
        GET_AREA_JSON_ID,
        GET_USER_POINTS_ID,
        OK,
        PUT_AREA_JSON_ID,
        REMOVE_USER_POINT_ID,
        SET_AREA_BBOX_ID,
        AddAreaInput,
        AddAreaOutput,
        AddUserPointInput,
        AddUserPointOutput,
        AreaChangedData,
        AreaSummary,
        GetAreaJsonInput,
        GetAreaJsonOutput,
        GetUserPointsInput,
        GetUserPointsOutput,
        PutAreaJsonInput,
        PutAreaJsonOutput,
        RemoveUserPointInput,
        RemoveUserPointOutput,
        SetAreaBboxInput,
        SetAreaBboxOutput,
    )
    from ..builder import Builder
    from ..contracts import AcquisitionTask, AggregationTask, BoundingBox, DedupingTask, PoiTask, VoidTask
    from ..entities import GeoArea
    from ..errors import GeoError
    from ..persistence import load_catalog, save_catalog, save_catalog_meta
    from ..protocols import AreaStyle, PoiStyle, VoidStyle
    from ..settings import Settings

    api.define_event(AREA_CHANGED_ID, AreaChangedData)

    def _rebuild_area(area_id: str, fresh_catalog: GeoCatalog) -> None:
        """Run the pipeline for area_id, update catalog, and fire AreaChanged on success."""
        for a in fresh_catalog.areas:
            if a.id == area_id:
                for geo_layer in a.layers:
                    if geo_layer.layer.type not in ("__poi__", "__user__", "__void__"):
                        geo_layer.layer.geojson = None
                break

        try:
            result = Builder(fresh_catalog).run()
            save_catalog(result, out_dir, debug=debug, in_dir=in_dir)
        except Exception as exc:
            Logger.error(f"pipeline failed for area '{area_id}': {exc}")
            return

        catalog.areas[:] = result.areas
        for a in catalog.areas:
            a.subscribe_changed(on_area_changed)

        updated_area = None
        for a in result.areas:
            if a.id == area_id:
                updated_area = a
                break

        if updated_area is not None:
            area_summary = AreaSummary(
                id=updated_area.id,
                name=updated_area.name,
                bbox=updated_area.bbox,
                minRadiusPx=updated_area.minRadiusPx,
                maxRadiusPx=updated_area.maxRadiusPx,
                liveMapRadiusPx=updated_area.liveMapRadiusPx,
                manifestUrl=updated_area.manifestUrl,
            )
            Logger.info(f"AreaChanged: firing for area '{area_id}'.")
            api.call(AREA_CHANGED_ID, AreaChangedData(area=area_summary))

    def on_area_changed(changed_area: GeoArea) -> None:
        if in_dir is not None:
            try:
                fresh_catalog = load_catalog(in_dir, debug=debug)
            except GeoError as exc:
                Logger.warning(f"AreaChanged: failed to reload catalog: {exc}; using in-memory catalog.")
                fresh_catalog = catalog
        else:
            fresh_catalog = catalog

        _rebuild_area(changed_area.id, fresh_catalog)

    settings_for_inject = Settings.current()
    tmpl_for_inject = settings_for_inject.template or {}
    _inject_missing_user_layers(catalog, tmpl_for_inject, in_dir)
    _inject_missing_void_layers(catalog, tmpl_for_inject, in_dir)

    for area in catalog.areas:
        area.subscribe_changed(on_area_changed)

    api.define_method(SET_AREA_BBOX_ID, SetAreaBboxInput, SetAreaBboxOutput)

    def on_set_area_bbox(data: SetAreaBboxInput) -> SetAreaBboxOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return MethodResult(SetAreaBboxOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found"))

        area.bbox = _normalize_bbox(list(data.bbox))

        if in_dir is not None:
            save_catalog_meta(catalog, in_dir, debug=debug)
            try:
                fresh_catalog = load_catalog(in_dir, debug=debug)
            except GeoError as exc:
                Logger.warning(f"SetAreaBbox: failed to reload catalog: {exc}; using in-memory catalog.")
                fresh_catalog = catalog
        else:
            fresh_catalog = catalog

        _rebuild_area(data.areaId, fresh_catalog)
        return MethodResult(SetAreaBboxOutput(error=OK))

    api.register(SET_AREA_BBOX_ID, on_set_area_bbox)

    api.define_method(ADD_AREA_ID, AddAreaInput, AddAreaOutput)

    def on_add_area(data: AddAreaInput) -> AddAreaOutput:
        settings = Settings.current()
        template = settings.template
        if template is None:
            return MethodResult(
                AddAreaOutput(
                    error=ERR_TEMPLATE_NOT_FOUND,
                    errorDescription="No template loaded — tasks file missing or empty",
                )
            )

        area_id = re.sub(r"[^a-z0-9]+", "_", data.areaName.lower()).strip("_")
        bbox = _normalize_bbox(list(data.bbox))  # [west, south, east, north]

        tasks = []
        for tlayer in template.get("layers", []):
            acq = tlayer.get("acquisition")
            if acq is None:
                continue
            filters_raw = acq.get("filters", {})
            if not isinstance(filters_raw, dict) or not filters_raw:
                continue
            provider = str(acq.get("provider", "overpass"))
            layer_style = tlayer.get("style", {})
            layer_name = str(tlayer["name"]) if tlayer.get("name") else None
            layer_type = str(tlayer.get("type", "heatmap"))
            color = str(layer_style["color"]) if layer_style.get("color") is not None else None
            surface = bool(layer_style.get("surface", False))
            scale = float(layer_style["scale"]) if layer_style.get("scale") is not None else None
            filters = {}
            for filter_key, values in filters_raw.items():
                filters[filter_key] = AreaStyle(
                    values=[str(v) for v in values],
                    name=layer_name,
                    color=color,
                    surface=surface,
                    type=layer_type,
                    scale=scale,
                )
            tasks.append(
                AcquisitionTask(
                    areaId=area_id,
                    areaName=data.areaName,
                    provider=provider,
                    bbox=BoundingBox(west=bbox[0], south=bbox[1], east=bbox[2], north=bbox[3]),
                    filters=filters,
                )
            )
        tasks.append(AggregationTask())
        tasks.append(DedupingTask())

        poi_style = PoiStyle()
        for tlayer in template.get("layers", []):
            if tlayer.get("id") == "__poi__":
                s = tlayer.get("style", {})
                poi_style = PoiStyle(
                    name=str(tlayer.get("name", "POI")),
                    color=str(s["color"]) if s.get("color") is not None else None,
                    opacity=float(s.get("opacity", 0.7)),
                    radius=float(s["radius"]) if s.get("radius") is not None else None,
                )
                break
        tasks.append(PoiTask(style=poi_style))

        void_style = VoidStyle()
        for tlayer in template.get("layers", []):
            if tlayer.get("id") == "__void__":
                s = tlayer.get("style", {})
                void_style = VoidStyle(
                    name=str(tlayer.get("name", "Mundane")),
                    color=str(s["color"]) if s.get("color") is not None else "#1f1f1f",
                    opacity=float(s.get("opacity", 0.9)),
                )
                break
        tasks.append(VoidTask(style=void_style))

        if in_dir is not None:
            try:
                fresh_catalog = load_catalog(in_dir, debug=debug)
            except GeoError as exc:
                Logger.warning(f"AddArea: failed to reload catalog: {exc}; using in-memory catalog.")
                fresh_catalog = catalog
        else:
            fresh_catalog = catalog

        result = Builder(fresh_catalog).run(tasks=tasks)

        template_layers = template.get("layers", [])
        for a in result.areas:
            if a.id == area_id:
                for geo_layer in a.layers:
                    for tlayer in template_layers:
                        if not isinstance(tlayer, dict):
                            continue
                        layer_id = tlayer.get("id")
                        if geo_layer.layer.id == "__poi__" and layer_id == "__poi__":
                            geo_layer.seed_raw(tlayer)
                            _apply_template_style(geo_layer, tlayer)
                            break
                        if geo_layer.layer.acquisition is not None and _acquisition_matches(geo_layer.layer.acquisition, tlayer.get("acquisition")):
                            geo_layer.seed_raw(tlayer)
                            _apply_template_style(geo_layer, tlayer)
                            break

                has_user = False
                for gl in a.layers:
                    if gl.layer.id == "__user__":
                        has_user = True
                        break
                if not has_user:
                    a.layers.append(_build_user_stub(template))
                break

        save_catalog(result, out_dir, debug=debug, in_dir=in_dir)

        if in_dir is not None:
            from ..persistence import save_area_to_catalog, save_catalog_meta

            new_area_obj = None
            for a in result.areas:
                if a.id == area_id:
                    new_area_obj = a
                    break
            if new_area_obj is not None:
                save_area_to_catalog(new_area_obj, in_dir, debug=debug)
            save_catalog_meta(result, in_dir, debug=debug)

        catalog.areas[:] = result.areas
        for a in catalog.areas:
            a.subscribe_changed(on_area_changed)

        new_area = None
        for a in result.areas:
            if a.id == area_id:
                new_area = a
                break

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

        return MethodResult(AddAreaOutput(error=OK, area=area_summary))

    api.register(ADD_AREA_ID, on_add_area)

    api.define_method(GET_AREA_JSON_ID, GetAreaJsonInput, GetAreaJsonOutput)

    def on_get_area_json(data: GetAreaJsonInput) -> GetAreaJsonOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return MethodResult(GetAreaJsonOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found"))

        return MethodResult(GetAreaJsonOutput(error=OK, manifest=area.to_manifest_dict()))

    api.register(GET_AREA_JSON_ID, on_get_area_json)

    api.define_method(PUT_AREA_JSON_ID, PutAreaJsonInput, PutAreaJsonOutput)

    def on_put_area_json(data: PutAreaJsonInput) -> PutAreaJsonOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return MethodResult(PutAreaJsonOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found"))

        save_dir = in_dir if in_dir is not None else out_dir
        try:
            needs_rebuild = area.apply_manifest(data.manifest, save_dir)
        except GeoError as exc:
            return MethodResult(PutAreaJsonOutput(error=ERR_MANIFEST_INVALID, errorDescription=str(exc)))
        except OSError as exc:
            return MethodResult(PutAreaJsonOutput(error=ERR_IO, errorDescription=str(exc)))

        if not needs_rebuild:
            Logger.info(f"PutAreaJson: no acquisition change for '{data.areaId}'; copying manifest.")
            if in_dir is not None:
                from ..persistence import child_path

                manifest_out = child_path(out_dir, area.manifestUrl)
                manifest_out.parent.mkdir(parents=True, exist_ok=True)
                with open(manifest_out, "w", encoding="utf-8") as f:
                    json.dump(area.to_manifest_dict(), f, indent=2)
            area_summary = AreaSummary(
                id=area.id,
                name=area.name,
                bbox=area.bbox,
                minRadiusPx=area.minRadiusPx,
                maxRadiusPx=area.maxRadiusPx,
                liveMapRadiusPx=area.liveMapRadiusPx,
                manifestUrl=area.manifestUrl,
            )
            Logger.info(f"AreaChanged: firing for area '{data.areaId}'.")
            api.call(AREA_CHANGED_ID, AreaChangedData(area=area_summary))
            return MethodResult(PutAreaJsonOutput(error=OK))

        if in_dir is not None:
            try:
                fresh_catalog = load_catalog(in_dir, debug=debug)
            except GeoError as exc:
                Logger.warning(f"PutAreaJson: failed to reload catalog: {exc}; using in-memory catalog.")
                fresh_catalog = catalog
        else:
            fresh_catalog = catalog

        _rebuild_area(data.areaId, fresh_catalog)
        return MethodResult(PutAreaJsonOutput(error=OK))

    api.register(PUT_AREA_JSON_ID, on_put_area_json)

    api.define_method(GET_USER_POINTS_ID, GetUserPointsInput, GetUserPointsOutput)

    def on_get_user_points(data: GetUserPointsInput) -> GetUserPointsOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return MethodResult(GetUserPointsOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found"))

        if in_dir is None:
            return MethodResult(GetUserPointsOutput(error=ERR_IO, errorDescription="No input directory configured"))

        user_path = in_dir / "areas" / data.areaId / "user.geojson"
        if not user_path.exists():
            return MethodResult(GetUserPointsOutput(error=OK, geojson={"type": "FeatureCollection", "features": []}))

        try:
            with open(user_path, "r", encoding="utf-8") as f:
                geojson = json.load(f)
            return MethodResult(GetUserPointsOutput(error=OK, geojson=geojson))
        except OSError as exc:
            return MethodResult(GetUserPointsOutput(error=ERR_IO, errorDescription=str(exc)))

    api.register(GET_USER_POINTS_ID, on_get_user_points)

    api.define_method(ADD_USER_POINT_ID, AddUserPointInput, AddUserPointOutput)

    def on_add_user_point(data: AddUserPointInput) -> AddUserPointOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return MethodResult(AddUserPointOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found"))

        if in_dir is None:
            return MethodResult(AddUserPointOutput(error=ERR_IO, errorDescription="No input directory configured"))

        has_user = False
        for gl in area.layers:
            if gl.layer.id == "__user__":
                has_user = True
                break
        if not has_user:
            settings = Settings.current()
            tmpl = settings.template or {}
            area.layers.append(_build_user_stub(tmpl))

        user_path = in_dir / "areas" / data.areaId / "user.geojson"
        if user_path.exists():
            try:
                with open(user_path, "r", encoding="utf-8") as f:
                    geojson = json.load(f)
            except OSError as exc:
                return MethodResult(AddUserPointOutput(error=ERR_IO, errorDescription=str(exc)))
        else:
            geojson = {"type": "FeatureCollection", "features": []}

        props: dict = {
            "timestamp": data.point.timestamp,
            "pressure": data.point.pressure,
            "name": data.point.name,
        }
        if data.point.properties is not None:
            for k, v in data.point.properties.items():
                props[k] = v
        feature: dict = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [data.point.lon, data.point.lat]},
            "properties": props,
        }
        geojson["features"].append(feature)

        try:
            user_path.parent.mkdir(parents=True, exist_ok=True)
            with open(user_path, "w", encoding="utf-8") as f:
                json.dump(geojson, f, indent=2)
        except OSError as exc:
            return MethodResult(AddUserPointOutput(error=ERR_IO, errorDescription=str(exc)))

        Logger.info(f"AddUserPoint: added point to area '{data.areaId}'. Total: {len(geojson['features'])}.")
        return MethodResult(AddUserPointOutput(error=OK))

    api.register(ADD_USER_POINT_ID, on_add_user_point)

    api.define_method(REMOVE_USER_POINT_ID, RemoveUserPointInput, RemoveUserPointOutput)

    def on_remove_user_point(data: RemoveUserPointInput) -> RemoveUserPointOutput:
        area = None
        for a in catalog.areas:
            if a.id == data.areaId:
                area = a
                break

        if area is None:
            return MethodResult(RemoveUserPointOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found"))

        if in_dir is None:
            return MethodResult(RemoveUserPointOutput(error=ERR_IO, errorDescription="No input directory configured"))

        user_path = in_dir / "areas" / data.areaId / "user.geojson"
        if not user_path.exists():
            return MethodResult(RemoveUserPointOutput(error=OK))

        try:
            with open(user_path, "r", encoding="utf-8") as f:
                geojson = json.load(f)
        except OSError as exc:
            return MethodResult(RemoveUserPointOutput(error=ERR_IO, errorDescription=str(exc)))

        target = [data.lon, data.lat]
        kept = []
        for feat in geojson.get("features", []):
            if feat.get("geometry", {}).get("coordinates") != target:
                kept.append(feat)
        geojson["features"] = kept

        try:
            with open(user_path, "w", encoding="utf-8") as f:
                json.dump(geojson, f, indent=2)
        except OSError as exc:
            return MethodResult(RemoveUserPointOutput(error=ERR_IO, errorDescription=str(exc)))

        Logger.info(f"RemoveUserPoint: removed point from area '{data.areaId}'. Remaining: {len(kept)}.")
        return MethodResult(RemoveUserPointOutput(error=OK))

    api.register(REMOVE_USER_POINT_ID, on_remove_user_point)


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
            from System.Drawing import Point, Size  # type: ignore[import]

            from ..settings import Settings

            _s = Settings.current()
            if _s.window_width is not None and _s.window_height is not None:
                _form.Size = Size(_s.window_width, _s.window_height)
            if _s.window_left is not None and _s.window_top is not None:
                _form.Location = Point(_s.window_left, _s.window_top)
            _form.Show()

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

            def on_form_closing(sender, _) -> None:  # noqa: ANN001
                from System.Windows.Forms import FormWindowState  # type: ignore[import]

                from ..settings import Settings

                try:
                    if sender.WindowState == FormWindowState.Normal:
                        Settings.save_local(sender.Left, sender.Top, sender.Width, sender.Height)
                        Logger.info(f"Window geometry saved: left={sender.Left} top={sender.Top} width={sender.Width} height={sender.Height}")
                except Exception as exc:
                    Logger.warning(f"Failed to save window geometry: {exc}")

            _form.FormClosing += on_form_closing

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
        window = webview.create_window("Geo Designer", html=html, hidden=True)
    else:
        window = webview.create_window("Geo Designer", url, hidden=True)

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
            from ..errors import GeoError
            from ..persistence import load_catalog

            try:
                resolved_catalog = load_catalog(in_dir, debug=debug)
            except GeoError as exc:
                Logger.warning(f"launch: failed to load catalog after pull: {exc}")

        udf = Path(os.environ.get("LOCALAPPDATA", "~")).expanduser() / "geo-builder" / "WebView2"
        udf.mkdir(parents=True, exist_ok=True)
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(udf)

        threading.Thread(target=run_dispatcher, daemon=True).start()
        Logger.info("WebView control starting.")
        webview.start()
        Logger.info("WebView control closed.")
        if api is not None:
            api.stop()
    finally:
        Logger.set_logger(None)
