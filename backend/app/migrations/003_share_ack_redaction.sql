-- Older development ACK caches may contain the bearer URL. Keep only the
-- composite reference; reconstruct owner-only share metadata on replay.
UPDATE operations
SET result_json=json_set(json_remove(result_json,'$.share'),'$._share_composite',json_extract(result_json,'$.share.composite_id'))
WHERE json_type(result_json,'$.share')='object';
PRAGMA user_version = 3;
