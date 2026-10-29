/** Same-origin only; Vite proxies /api. Never send session credentials to CDN/upload services. */
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
    response = await fetch(`/api${path}`, { method, headers, body, signal: AbortSignal.timeout(20000) });
  } catch {
    throw new Error('Không kết nối được backend. Ảnh đang có vẫn giữ trong bộ nhớ; hãy thử lưu lại.');
  }
  let payload;
  try { payload = await response.json(); }
  catch {
    throw new Error(`Backend trả dữ liệu không hợp lệ (${response.status}). Hãy thử lại.`);
  }
  if (!response.ok) throw new Error(payload.error?.message || `Backend trả lỗi ${response.status}. Hãy thử lại.`);
  return payload;
}
