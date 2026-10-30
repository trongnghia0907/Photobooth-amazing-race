import test from 'node:test';
import assert from 'node:assert/strict';
import {newId} from '../src/utils/ids.js';

test('UUID fallback uses cryptographic bytes with UUIDv4 version/variant; missing randomness refuses',()=>{
  let called=false;
  const id=newId({getRandomValues(bytes){called=true;bytes.fill(255);return bytes;}});
  assert.equal(called,true);assert.equal(id,'ffffffff-ffff-4fff-bfff-ffffffffffff');
  assert.throws(()=>newId({}),/ngẫu nhiên an toàn/);
});
