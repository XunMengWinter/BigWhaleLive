/** One audible media element. Video animations remain muted and independent. */
export class SpeechPlayer {
  constructor(audio) {
    this.audio = audio;
    this.enabled = false;
    this.generation = 0;
    this.removeHandlers = null;
    audio.volume = 1;
    audio.muted = false;
  }

  stop() {
    this.generation += 1;
    this.removeHandlers?.();
    this.removeHandlers = null;
    this.audio.pause();
    this.audio.removeAttribute('src');
    this.audio.load();
  }

  async enable() {
    this.stop();
    const generation = this.generation;
    // A short silent PCM WAV unlocks this exact media element within the click.
    const wav = new Uint8Array(44 + 800);
    const view = new DataView(wav.buffer);
    const string = (offset, value) => [...value].forEach((char, index) => { wav[offset + index] = char.charCodeAt(0); });
    string(0, 'RIFF'); view.setUint32(4, wav.length - 8, true); string(8, 'WAVE');
    string(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, 8000, true); view.setUint32(28, 16000, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true); string(36, 'data'); view.setUint32(40, 800, true);
    const url = URL.createObjectURL(new Blob([wav], { type: 'audio/wav' }));
    try {
      this.audio.src = url;
      await this.audio.play();
      if (this.generation !== generation) throw new DOMException('Cancelled', 'AbortError');
      this.audio.pause();
      this.audio.removeAttribute('src');
      this.audio.load();
      this.enabled = true;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  disable() {
    this.stop();
    this.enabled = false;
  }

  play(url, callbacks) {
    this.stop();
    const generation = this.generation;
    let started = false;
    const valid = () => generation === this.generation;
    const fail = code => {
      if (!valid()) return;
      this.disable();
      callbacks.error(code);
    };
    if (!this.enabled || !/^\/audio\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.mp3$/.test(url)) {
      fail(this.enabled ? 'audio_error' : 'autoplay_blocked');
      return;
    }
    const playing = () => {
      if (!valid() || started) return;
      started = true;
      callbacks.started();
    };
    const ended = () => {
      if (!valid() || !started) return;
      this.stop();
      callbacks.ended();
    };
    const error = () => fail('audio_error');
    this.audio.addEventListener('playing', playing);
    this.audio.addEventListener('ended', ended);
    this.audio.addEventListener('error', error);
    this.removeHandlers = () => {
      this.audio.removeEventListener('playing', playing);
      this.audio.removeEventListener('ended', ended);
      this.audio.removeEventListener('error', error);
    };
    this.audio.src = url;
    this.audio.play().catch(error => {
      if (valid()) fail(error.name === 'NotAllowedError' ? 'autoplay_blocked' : 'audio_error');
    });
  }
}
