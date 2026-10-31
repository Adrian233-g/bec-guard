// Small public-API client for the mailbox provisioner. No request or response
// bodies are logged; exceptions are intentionally independent of remote text.
export function n8nApiClient({ baseUrl, apiKey, timeoutMs = 10000, fetchImpl = fetch }) {
  const url = new URL(baseUrl);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      !['http:', 'https:'].includes(url.protocol) || !apiKey ||
      (url.protocol === 'http:' && !['n8n', 'localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) {
    throw new Error('Invalid n8n API configuration');
  }
  return async function request(method, path, body) {
    if (!['GET', 'POST', 'DELETE'].includes(method) ||
        !/^\/[A-Za-z0-9_/-]+$/.test(path) || path.includes('//') || path.includes('..')) {
      throw new Error('Invalid n8n request');
    }
    let response;
    try {
      response = await fetchImpl(`${url.origin}/api/v1${path}`, {
        method, redirect: 'error', signal: AbortSignal.timeout(timeoutMs),
        headers: { 'X-N8N-API-KEY': apiKey, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) throw new Error('Request failed');
      if (response.status === 204) return {};
      return await response.json();
    } catch {
      throw new Error('n8n API request failed');
    }
  };
}
