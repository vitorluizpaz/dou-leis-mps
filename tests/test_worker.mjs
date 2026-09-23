import assert from "node:assert/strict";
import test from "node:test";

import worker from "../cloudflare/worker.js";

test("scheduled trigger wakes Render without an API key", async () => {
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url: String(url), options };
    return new Response(null, { status: 200 });
  };
  try {
    await worker.scheduled(
      { cron: "57 12 * * *" },
      { BACKEND_URL: "https://dou-leis-mps.onrender.com" },
    );
    assert.equal(request.url, "https://dou-leis-mps.onrender.com/api/health");
    assert.equal(request.options.method, "GET");
    assert.equal(request.options.headers, undefined);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("scheduled trigger reports an unhealthy backend", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(null, { status: 503 });
  try {
    await assert.rejects(
      worker.scheduled(
        { cron: "50 12 * * *" },
        { BACKEND_URL: "https://dou-leis-mps.onrender.com" },
      ),
      /HTTP 503/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
