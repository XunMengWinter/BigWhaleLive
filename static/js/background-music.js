/** Local instrumental bed; only the current, running speech owner may hear it. */
export class BackgroundMusic {
  constructor(audio, speech, onStatus = () => {}) {
    this.audio = audio;
    this.speech = speech;
    this.onStatus = onStatus;
    this.allowed = false;
    this.enabled = true;
    this.failed = false;
    this.pending = false;
    this.generation = 0;
    this.fadeTimer = null;
    this.startTimer = null;
    this.ducked = false;
    audio.loop = true;
    audio.volume = 0;
    this.handlers = {
      playing: () => {
        if (!this.allowed || !this.enabled || this.failed) { audio.pause(); return; }
        clearTimeout(this.startTimer);
        this.fadeTo(this.ducked ? .09 : .28);
        this.onStatus(this.ducked ? 'ducked' : 'playing');
      },
      error: () => this.fail(),
    };
    for (const [event, handler] of Object.entries(this.handlers)) audio.addEventListener(event, handler);
    this.speechHandlers = {};
    for (const event of ['playing', 'pause', 'ended', 'waiting', 'emptied', 'error']) {
      const handler = () => this.duck(event === 'playing');
      this.speechHandlers[event] = handler;
      speech.addEventListener(event, handler);
    }
  }

  fadeTo(target) {
    clearInterval(this.fadeTimer);
    const start = this.audio.volume;
    const began = performance.now();
    const duration = target < start ? 120 : 1400;
    this.fadeTimer = setInterval(() => {
      const progress = Math.min(1, (performance.now() - began) / duration);
      this.audio.volume = start + (target - start) * progress;
      if (progress === 1) { clearInterval(this.fadeTimer); this.fadeTimer = null; }
    }, 30);
  }

  duck(value) {
    this.ducked = value;
    if (this.allowed && this.enabled && !this.failed && !this.audio.paused) {
      this.fadeTo(value ? .09 : .28);
      this.onStatus(value ? 'ducked' : 'playing');
    }
  }

  setAllowed(allowed) {
    this.allowed = !!allowed;
    if (!this.allowed || !this.enabled) {
      this.stop();
    } else if (!this.failed && !this.pending && this.audio.paused) {
      this.start();
    }
  }

  async start() {
    const generation = ++this.generation;
    this.pending = true;
    this.audio.volume = 0;
    this.onStatus('loading');
    this.startTimer = setTimeout(() => { if (generation === this.generation) this.fail(); }, 8000);
    try {
      await this.audio.play();
      if (generation !== this.generation && (!this.allowed || !this.enabled || this.failed)) this.audio.pause();
    } catch {
      if (generation === this.generation) this.fail();
    } finally {
      if (generation === this.generation) this.pending = false;
    }
  }

  stop() {
    this.generation += 1;
    this.pending = false;
    clearInterval(this.fadeTimer);
    clearTimeout(this.startTimer);
    this.fadeTimer = null;
    this.audio.volume = 0;
    this.audio.pause();
    this.audio.currentTime = 0;
    this.onStatus(this.failed ? 'error' : this.enabled ? 'idle' : 'off');
  }

  fail() {
    this.failed = true;
    this.stop();
  }

  toggle() {
    if (this.failed) {
      this.failed = false;
      this.enabled = true;
      this.audio.load();
    } else this.enabled = !this.enabled;
    this.setAllowed(this.allowed);
  }

  dispose() {
    this.allowed = false;
    this.stop();
    for (const [event, handler] of Object.entries(this.handlers)) this.audio.removeEventListener(event, handler);
    for (const [event, handler] of Object.entries(this.speechHandlers)) this.speech.removeEventListener(event, handler);
  }
}
