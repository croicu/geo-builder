if (new URLSearchParams(location.search).get('break')) { debugger; }

(() => {
  const _handlers = {};
  const _pending = {};
  let _nextId = 0;

  // Dispatch incoming messages from Python.
  // { id, data [, requestId] }  → method call; handler return value is sent back if requestId present
  // { requestId, data }         → response to a JS-initiated event
  window.__geo_dispatch = ({ id, requestId, data }) => {
    if (id !== undefined) {
      const fn = _handlers[id];
      if (!fn) return;
      const result = fn(data);
      if (requestId !== undefined && result !== undefined) {
        window.chrome.webview.postMessage(JSON.stringify({ requestId, data: result }));
      }
    } else if (requestId !== undefined) {
      const cb = _pending[requestId];
      if (cb) {
        delete _pending[requestId];
        cb(data);
      }
    }
  };

  window.geo = {
    // Fire an event to Python. Pass callback to receive a response.
    invoke(id, payload, callback) {
      const requestId = callback !== undefined ? String(_nextId++) : undefined;
      if (requestId !== undefined) _pending[requestId] = callback;
      const msg = requestId !== undefined
        ? { id, requestId, data: payload }
        : { id, data: payload };
      window.chrome.webview.postMessage(JSON.stringify(msg));
    },
    // Register a handler for a Python method call.
    subscribe(id, fn) { _handlers[id] = fn; },
    unsubscribe(id)   { delete _handlers[id]; },
  };

  // Ping: Python sends a token, we echo it back as the method response.
  _handlers["__geo_ping__"] = (data) => data;
})();

//# sourceURL=startup.js
