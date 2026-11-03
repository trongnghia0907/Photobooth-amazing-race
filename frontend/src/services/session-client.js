import { request } from './api-client.js';

export const getSession = context => request(`/sessions/${context.id}`, { token: context.token });
export const updateLayout = (context, operation) => request(`/sessions/${context.id}/layout`, {
  method:'PUT', token:context.token, key:operation.key,
  body:{layout:operation.layout,slot_count:operation.slotCount},
});

export const createSession = (context, layout) => request('/sessions', {
  method: 'POST', token: context.token, key: context.createKey,
  body: { layout, slot_count: context.slotCount },
});

export function uploadPhoto(context, operation, blob) {
  const body = new FormData();
  body.append('slot_index', operation.slot);
  body.append('source', operation.source);
  body.append('file', blob, 'shot.png');
  return request(`/sessions/${context.id}/photos`, { method: 'POST', token: context.token, key: operation.key, body });
}

export const deletePhotos = (context, operation) => request(
  `/sessions/${context.id}/photos${operation.slot === null ? '' : `/${operation.slot}`}`,
  { method: 'DELETE', token: context.token, key: operation.key },
);

export function uploadComposite(context, operation) {
  const body = new FormData();
  body.append('file', operation.blob, 'composite.png');
  body.append('shots_revision', operation.shotsRevision);
  body.append('editor_json', JSON.stringify(operation.editor));
  return request(`/sessions/${context.id}/composite`, { method: 'PUT', token: context.token, key: operation.uploadKey, body });
}

export const completeSession = (context, operation) => request(`/sessions/${context.id}/complete`, {
  method: 'POST', token: context.token, key: operation.completeKey,
  body: { composite_id: operation.compositeId },
});
