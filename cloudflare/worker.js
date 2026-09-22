const API_PREFIX = "/api/";

function securityHeaders(headers) {
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Referrer-Policy", "no-referrer");
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  headers.set(
    "Content-Security-Policy",
    "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; " +
      "form-action 'self'; img-src 'self' data:; connect-src 'self'; " +
      "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
  );
  return headers;
}

async function proxyApi(request, env) {
  const incoming = new URL(request.url);
  const backend = new URL(env.BACKEND_URL);
  backend.pathname = incoming.pathname;
  backend.search = incoming.search;

  const upstreamRequest = new Request(backend, request);
  const response = await fetch(upstreamRequest);
  const headers = securityHeaders(new Headers(response.headers));
  headers.set("Cache-Control", "no-store");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith(API_PREFIX)) {
      return proxyApi(request, env);
    }

    const response = await env.ASSETS.fetch(request);
    const headers = securityHeaders(new Headers(response.headers));
    if (headers.get("Content-Type")?.includes("text/html")) {
      headers.set("Cache-Control", "public, max-age=300");
    }
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
