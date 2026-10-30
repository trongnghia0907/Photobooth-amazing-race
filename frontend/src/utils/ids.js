/** UUIDv4 with browser cryptographic randomness; also works on trusted test LANs
 * whose HTTP context does not expose crypto.randomUUID. Never Math.random.
 */
export function newId(rng=globalThis.crypto){
  if(typeof rng?.randomUUID==='function')return rng.randomUUID();
  if(typeof rng?.getRandomValues!=='function')throw new Error('Trình duyệt không có bộ tạo số ngẫu nhiên an toàn. Hãy cập nhật trình duyệt/dùng HTTPS.');
  const bytes=rng.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
