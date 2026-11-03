/** Same-origin only; Vite proxies /api. Never send session credentials to CDN/upload services. */
import { boothFetch } from './booth-access.js';
export async function request(path, { token, key, body, method = 'GET' } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (key) headers['Idempotency-Key'] = key;
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }
  let response;
  try {
    response = await boothFetch(`/api${path}`, { method, headers, body, signal: AbortSignal.timeout(20000) });
  } catch {
    throw new Error('Could not connect to the backend. Your current photos are still in memory; please retry saving.');
  }
  let payload;
  try { payload = await response.json(); }
  catch {
    throw new Error(`The backend returned an invalid response (${response.status}). Please try again.`);
  }
  if (!response.ok) throw new Error(payload.error?.message || `The backend returned error ${response.status}. Please try again.`);
  return payload;
}
