from __future__ import annotations

import json
import os
from pathlib import Path

import webview

from ..diagnostics import Logger

_DEBUG_PORT = 9222
_STARTUP_HTML = Path(__file__).parent / "startup.html"
_STARTUP_JS = Path(__file__).parent / "startup.js"


def _register_break(window: webview.Window) -> None:
    try:
        import webview.platforms.winforms as wf
        form = wf.BrowserView.instances.get(window.uid)
        wv2 = getattr(form, "webview", None) or getattr(form, "browser", None)
        if wv2 is not None:
            task = wv2.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(
                _STARTUP_JS.read_text(encoding="utf-8")
            )
            task.Wait()
            Logger.info("Init break registered via AddScriptToExecuteOnDocumentCreated.")
        else:
            Logger.warning("Init break: could not locate CoreWebView2 instance.")
    except Exception as exc:
        Logger.warning(f"Init break registration failed: {exc}")


def launch(url: str, debug: bool = False, break_on_load: bool = False, dev_tools: bool = False) -> None:
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
        webview.start(_register_break, window)
    else:
        webview.create_window("Geo Designer", url)
        webview.start()
    Logger.info("WebView control started.")
