from __future__ import annotations

import os

import webview

_DEBUG_PORT = 9222


def launch(url: str, debug: bool = False) -> None:
    if debug:
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={_DEBUG_PORT}"
    webview.create_window("Geo Designer", url)
    webview.start()
