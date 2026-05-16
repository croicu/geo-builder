from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import webview

from ..diagnostics import ConsoleLogSink, Logger, TelemetryLevel
from .gateway import Gateway

_DEBUG_PORT = 9222
_STARTUP_HTML = Path(__file__).parent / "startup.html"
_STARTUP_JS = Path(__file__).parent / "startup.js"

_core = None
_form = None
api: Gateway | None = None
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
    Logger.info(f"WebResourceRequested: {args.Request.Uri}")


def _on_window_close_requested(*_) -> None:
    Logger.info("WindowCloseRequested")


def _on_web_message_received(_, args) -> None:  # noqa: ANN001
    raw = args.TryGetWebMessageAsString()
    Logger.info(f"WebMessageReceived: {raw}")
    if api is not None:
        api._on_message(raw)


def _setup(window: webview.Window, catalog=None) -> None:
    try:
        import webview.platforms.winforms as wf
        from System import Action  # type: ignore[import]

        form = wf.BrowserView.instances.get(window.uid)
        if form is None:
            Logger.warning("Setup: could not locate BrowserView instance.")
            return

        def on_ui_thread() -> None:
            global _core, _form, api  # noqa: PLW0603
            wv2 = getattr(form, "webview", None) or getattr(form, "browser", None)
            if wv2 is None:
                Logger.warning("Setup: could not locate WebView2 control.")
                return
            _form = form
            _core = wv2.CoreWebView2

            edge = getattr(form, "browser", None)
            if edge is not None and hasattr(edge, "on_script_notify"):
                wv2.WebMessageReceived -= edge.on_script_notify

            script = _STARTUP_JS.read_text(encoding="utf-8")
            _core.AddScriptToExecuteOnDocumentCreatedAsync(script)
            _core.ExecuteScriptAsync(script)

            api = Gateway(invoke_script)
            if catalog is not None:
                catalog.register_handlers(api)
            _api_ready.set()

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
    catalog=None,
    debug: bool = False,
    break_on_load: bool = False,
    dev_tools: bool = False,
    log_level: TelemetryLevel = TelemetryLevel.ERROR,
) -> None:
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
                _setup(window, catalog)
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
        threading.Thread(target=run_dispatcher, daemon=True).start()
        Logger.info("WebView control starting.")
        webview.start()
        Logger.info("WebView control closing.")
        if api is not None:
            api.stop()
    finally:
        Logger.set_logger(None)
