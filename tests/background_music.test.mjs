import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('../static/js/background-music.js', import.meta.url), 'utf8');
const {BackgroundMusic} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
class Audio extends EventTarget {
  paused = true; volume = 1; currentTime = 0; plays = 0;
  async play() { this.plays++; this.paused = false; this.dispatchEvent(new Event('playing')); }
  pause() { this.paused = true; }
  load() {}
}
function harness(t) {
  const audio = new Audio(), speech = new Audio(), statuses = [];
  const music = new BackgroundMusic(audio, speech, status => statuses.push(status));
  t.after(() => music.dispose());
  return {audio, speech, music, statuses};
}
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
test('no music before owner permission; pause/revoke clears sound and pending fade', async t => {
  const {audio, music} = harness(t);
  music.setAllowed(false); assert.equal(audio.plays, 0);
  music.setAllowed(true); await flush(); assert.equal(audio.paused, false); assert.equal(audio.loop, true);
  audio.currentTime = 42; music.setAllowed(false);
  assert.equal(audio.paused, true); assert.equal(audio.currentTime, 0); assert.equal(audio.volume, 0);
  assert.equal(music.fadeTimer, null);
});
test('speech events duck only the bed and restore it after waiting/end', async t => {
  const {music, speech, audio, statuses} = harness(t);
  music.setAllowed(true); await flush();
  speech.dispatchEvent(new Event('playing')); assert.equal(music.ducked, true); assert.equal(statuses.at(-1), 'ducked');
  speech.dispatchEvent(new Event('waiting')); assert.equal(music.ducked, false);
  speech.dispatchEvent(new Event('playing')); speech.dispatchEvent(new Event('ended'));
  assert.equal(statuses.at(-1), 'playing'); assert.equal(speech.volume, 1); assert.equal(audio.paused, false);
});
test('late play completion after cancellation cannot restart the bed', async t => {
  const {music, audio} = harness(t); let complete;
  audio.play = () => new Promise(resolve => { complete = () => { audio.paused = false; resolve(); }; });
  music.setAllowed(true); music.setAllowed(false); complete(); await flush();
  assert.equal(audio.paused, true); assert.equal(audio.volume, 0);
});
test('load/autoplay failure is latched, does not retry on snapshots or touch speech', async t => {
  const {music, audio, speech, statuses} = harness(t);
  audio.play = async () => { audio.plays++; throw new Error('autoplay'); };
  music.setAllowed(true); await flush();
  for (let i = 0; i < 10; i++) music.setAllowed(true);
  assert.equal(audio.plays, 1); assert.equal(statuses.at(-1), 'error'); assert.equal(speech.plays, 0);
  audio.play = Audio.prototype.play; music.toggle(); await flush();
  assert.equal(audio.plays, 2); assert.equal(audio.paused, false);
});
test('manual music off survives snapshots; disposed media listeners cannot restart fades', async t => {
  const {music, audio, speech} = harness(t);
  music.setAllowed(true); await flush(); music.toggle(); music.setAllowed(true);
  assert.equal(audio.paused, true); assert.equal(audio.volume, 0); assert.equal(audio.plays, 1);
  music.dispose(); speech.dispatchEvent(new Event('playing')); audio.dispatchEvent(new Event('playing'));
  assert.equal(music.fadeTimer, null);
});
