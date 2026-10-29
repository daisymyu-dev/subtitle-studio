'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../web/concept-core.js');

test('line navigation is bounded, without unintended wraparound', () => {
  assert.equal(core.moveIndex(0,-1,4),0);
  assert.equal(core.moveIndex(3,1,4),3);
  assert.equal(core.moveIndex(1,1,4),2);
});
test('time and progress handle unavailable metadata', () => {
  assert.equal(core.formatTime(NaN),'00:00');
  assert.equal(core.formatTime(63.9),'01:03');
  assert.equal(core.progress(10,0),0);
  assert.equal(core.progress(20,10),1000);
  assert.equal(core.progress(2.5,10),250);
});
test('bookmarks only accept known demo terms and toggle cleanly', () => {
  assert.deepEqual(core.toggleSaved([], 'priced', ['priced','bandwagon']),['priced']);
  assert.deepEqual(core.toggleSaved(['priced'], 'priced', ['priced']),[]);
  assert.deepEqual(core.toggleSaved([], 'unknown', ['priced']),[]);
});
