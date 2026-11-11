/** Analyse a separate decoded copy; never reroute or duplicate audible playback. */
export function buildEnvelope(buffer, step = .02) {
  if (!Number.isFinite(buffer.duration) || buffer.duration > 120) throw new Error('audio_duration');
  const size = Math.max(1, Math.round(buffer.sampleRate * step));
  const channels = Array.from({length: buffer.numberOfChannels}, (_, i) => buffer.getChannelData(i));
  const values = [];
  for (let start = 0; start < buffer.length; start += size) {
    const end = Math.min(start + size, buffer.length);
    let sum = 0;
    for (const channel of channels) for (let i = start; i < end; i++) sum += channel[i] ** 2;
    values.push(Math.sqrt(sum / ((end - start) * channels.length)));
  }
  const sorted = [...values].sort((a, b) => a - b);
  const reference = Math.max(.015, sorted[Math.floor(sorted.length * .9)] || 0);
  const threshold = Math.max(.004, reference * .06);
  return {step, values: values.map(value => value <= threshold ? 0 :
    Math.min(1, ((value - threshold) / reference) ** .65))};
}

export function envelopeAt(envelope, time) {
  if (!envelope || !Number.isFinite(time) || time < 0) return 0;
  return envelope.values[Math.floor(time / envelope.step)] || 0;
}

export class LipSyncDriver {
  constructor(audio, onLevel, onStatus = () => {}) {
    this.audio = audio;
    this.onLevel = onLevel;
    this.onStatus = onStatus;
    this.revision = 0;
    this.playing = false;
    this.level = 0;
    this.frame = null;
    this.context = null;
    this.controller = null;
    this.envelope = null;
    this.disposed = false;
    this.handlers = {
      loadstart: () => this.prepare(),
      playing: () => { this.playing = true; this.lastTick = performance.now(); this.tick(); },
      waiting: () => this.rest(),
      pause: () => this.rest(),
      ended: () => this.reset(),
      emptied: () => this.reset(),
      error: () => this.reset()
    };
    for (const [event, handler] of Object.entries(this.handlers)) audio.addEventListener(event, handler);
  }

  rest() {
    this.playing = false;
    cancelAnimationFrame(this.frame);
    this.frame = null;
    this.level = 0;
    this.onLevel(0);
  }

  reset() {
    this.revision++;
    this.controller?.abort();
    this.controller = null;
    this.envelope = null;
    this.rest();
    this.onStatus('idle');
  }

  async prepare() {
    this.reset();
    const source = this.audio.getAttribute('src') || '';
    if (!/^\/audio\/[0-9a-f-]{36}\.mp3$/.test(source) || this.disposed) return;
    const revision = this.revision;
    const controller = this.controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    this.onStatus('preparing');
    try {
      const response = await fetch(source, {signal: controller.signal});
      if (!response.ok || Number(response.headers.get('content-length')) > 8 * 1024 * 1024) throw new Error('audio_fetch');
      const bytes = await response.arrayBuffer();
      if (bytes.byteLength > 8 * 1024 * 1024) throw new Error('audio_size');
      if (this.disposed || revision !== this.revision) return;
      const Context = window.AudioContext || window.webkitAudioContext;
      this.context ||= new Context();
      const decoded = await this.context.decodeAudioData(bytes);
      if (this.disposed || revision !== this.revision) return;
      this.envelope = buildEnvelope(decoded);
      this.onStatus('ready');
    } catch {
      if (!this.disposed && revision === this.revision) {
        this.envelope = null;
        this.onLevel(0);
        this.onStatus('unavailable');
      }
    } finally { clearTimeout(timeout); }
  }

  tick() {
    cancelAnimationFrame(this.frame);
    if (this.disposed || !this.playing || this.audio.paused || this.audio.ended) { this.rest(); return; }
    const now = performance.now();
    const dt = Math.min(.1, Math.max(0, (now - this.lastTick) / 1000));
    this.lastTick = now;
    const target = this.audio.readyState >= 3 ? envelopeAt(this.envelope, this.audio.currentTime) : 0;
    const rate = target > this.level ? .018 : .035;
    this.level += (target - this.level) * (1 - Math.exp(-dt / rate));
    if (target === 0 && this.level < .025) this.level = 0;
    this.onLevel(this.level);
    this.frame = requestAnimationFrame(() => this.tick());
  }

  dispose() {
    this.disposed = true;
    this.reset();
    for (const [event, handler] of Object.entries(this.handlers)) this.audio.removeEventListener(event, handler);
    this.context?.close().catch(() => {});
  }
}
