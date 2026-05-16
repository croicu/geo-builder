if (new URLSearchParams(location.search).get('break')) { debugger; }

(() => {
  const _handlers = {};

  window.__geo_dispatch = ({ id, data }) => {
    const fn = _handlers[id];
    if (fn) fn(data);
  };

  window.geo = {
    invoke(id, payload) {
      window.chrome.webview.postMessage(JSON.stringify({ id, data: payload }));
    },
    subscribe(id, fn) {
      _handlers[id] = fn;
    },
  };

  _handlers["__geo_ping__"] = (token) => window.geo.invoke("__geo_ping__", token);
})();

//# sourceURL=startup.js