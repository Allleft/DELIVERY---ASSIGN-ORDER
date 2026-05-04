(function attachOfficeDispatchBackendApi(globalObject) {
  const root = globalObject || (typeof window !== "undefined" ? window : globalThis);

  const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

  function resolveBaseUrl() {
    const override = asText(root.__OFFICE_DISPATCH_API_BASE).trim();
    return override || DEFAULT_BASE_URL;
  }

  async function listBatches() {
    return requestJson("GET", "/api/dispatch/batches");
  }

  async function createBatch(payload) {
    return requestJson("POST", "/api/dispatch/batches", payload);
  }

  async function getBatch(batchId) {
    return requestJson("GET", `/api/dispatch/batches/${encodeURIComponent(asText(batchId).trim())}`);
  }

  async function saveBatchOrders(batchId, orders) {
    return requestJson("POST", `/api/dispatch/batches/${encodeURIComponent(asText(batchId).trim())}/orders`, orders);
  }

  async function listBatchOrders(batchId) {
    return requestJson("GET", `/api/dispatch/batches/${encodeURIComponent(asText(batchId).trim())}/orders`);
  }

  async function generateBatchPlan(batchId) {
    return requestJson("POST", `/api/dispatch/batches/${encodeURIComponent(asText(batchId).trim())}/generate`);
  }

  async function requestJson(method, path, body) {
    if (typeof root.fetch !== "function") {
      throw createApiError("BACKEND_UNAVAILABLE", "fetch is unavailable in this environment.");
    }
    const url = `${resolveBaseUrl()}${path}`;
    const response = await root.fetch(url, {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" })
      },
      body: body === undefined ? undefined : JSON.stringify(body)
    });

    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (_) {
        payload = { detail: text };
      }
    }
    if (!response.ok) {
      const detail = asText(payload?.detail).trim() || `HTTP ${response.status}`;
      throw createApiError("BACKEND_RESPONSE_ERROR", detail, response.status, payload);
    }
    return payload || {};
  }

  function createApiError(code, message, status, payload) {
    const error = new Error(message || code);
    error.code = code;
    error.status = status;
    error.payload = payload;
    return error;
  }

  function asText(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  root.OfficeDispatchBackendApi = Object.freeze({
    DEFAULT_BASE_URL,
    resolveBaseUrl,
    listBatches,
    createBatch,
    getBatch,
    saveBatchOrders,
    listBatchOrders,
    generateBatchPlan
  });
})(typeof window !== "undefined" ? window : globalThis);
