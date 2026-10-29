import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nextPhase } from '../src/core/session-machine.js';

test('mock capture, save, retry and next guest follow explicit phases', () => {
  let phase = 'IDLE';
  for (const [event, expected] of [['PREVIEW','PREVIEW'],['COUNTDOWN','COUNTDOWN'],['CAPTURE','CAPTURING'],
    ['BUSY','SAVING'],['FAIL','ERROR'],['BUSY','SAVING'],['PREVIEW','PREVIEW'],['EDIT','EDITING'],['BUSY','SAVING'],['SAVED','READY'],['RESET','IDLE']]) {
    phase = nextPhase(phase,event);
    assert.equal(phase,expected);
  }
  assert.throws(()=>nextPhase('IDLE','UNKNOWN'));
});
