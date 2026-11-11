/** A small tracked mouth overlay; the original body animation remains intact. */
export function trackingFrame(time, count) {
  return Math.max(0, Math.min(count - 1, Math.round(time * 24)));
}

export class MouthRenderer {
  constructor(root, onFailure = () => {}) {
    this.root = root;
    this.svg = root.querySelector('.character-mouth');
    this.group = this.svg.querySelector('g');
    this.skin = this.svg.querySelector('.mouth-skin');
    this.mouth = this.svg.querySelector('.mouth-shape');
    this.tongue = this.svg.querySelector('.mouth-tongue');
    this.level = 0;
    this.active = false;
    this.disposed = false;
    this.controller = new AbortController();
    this.tracking = null;
    this.presentedTimes = new Map();
    this.videoCallbacks = new Map();
    for (const video of root.querySelectorAll('video[data-clip]')) {
      if (!video.requestVideoFrameCallback) continue;
      const presented = (_, metadata) => {
        if (this.disposed) return;
        this.presentedTimes.set(video, metadata.mediaTime);
        this.videoCallbacks.set(video, video.requestVideoFrameCallback(presented));
      };
      this.videoCallbacks.set(video, video.requestVideoFrameCallback(presented));
    }
    this.motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
    fetch('/static/assets/dsh-pet/mouth-tracking.json', {signal: this.controller.signal})
      .then(response => { if (!response.ok) throw new Error('tracking'); return response.json(); })
      .then(data => {
        if (data.fps !== 24 || data.width !== 640 || data.height !== 360 || data.clips?.speaking?.length !== 241 ||
            !data.clips.speaking.every(frame => frame.length === 7 && frame.every(Number.isFinite))) throw new Error('tracking');
        if (!this.disposed) this.tracking = data;
      }).catch(() => { if (!this.disposed) { this.root.dataset.mouthTracking = 'unavailable'; onFailure(); } });
    this.frame = null;
  }

  setLevel(level) { this.level = Number.isFinite(level) ? Math.max(0, Math.min(1, level)) : 0; }
  setActive(active) {
    cancelAnimationFrame(this.frame);
    this.active = active;
    if (active && !this.disposed) this.frame = requestAnimationFrame(() => this.draw());
    else { this.level = 0; this.root.dataset.mouthLevel = '0'; this.svg.style.visibility = 'hidden'; }
  }

  draw() {
    if (this.disposed || !this.active) return;
    const video = this.root.querySelector('video.is-active');
    const visible = this.active && this.tracking && !this.motionPreference.matches &&
      this.root.dataset.motion === 'speaking' && video?.readyState >= 2;
    this.svg.style.visibility = visible ? 'visible' : 'hidden';
    if (visible) {
      const frames = this.tracking.clips.speaking;
      // WebM timestamps are rounded to milliseconds. currentTime may advance
      // past a frame that is still on screen, especially during decoder load.
      const time = this.presentedTimes.get(video) ?? video.currentTime;
      const index = trackingFrame(time, frames.length);
      const [x, y, rx, ry, r, g, b] = frames[index];
      this.group.setAttribute('transform', `translate(${x} ${y})`);
      this.skin.setAttribute('x', -rx);
      this.skin.setAttribute('y', -ry);
      this.skin.setAttribute('width', rx * 2);
      this.skin.setAttribute('height', ry * 2);
      this.skin.setAttribute('fill', `rgb(${r} ${g} ${b})`);
      const level = this.level < .035 ? 0 : this.level;
      const width = 2.5 + level * 2.7;
      const height = level * 5;
      this.mouth.setAttribute('d', level === 0 ? 'M -2 0 Q 0 .7 2 0' :
        `M ${-width} -1 Q 0 -1.8 ${width} -1 Q ${width * .8} ${height} 0 ${height} Q ${-width * .8} ${height} ${-width} -1 Z`);
      this.mouth.setAttribute('fill', level === 0 ? 'none' : '#78454b');
      this.tongue.setAttribute('d', level > .25 ?
        `M ${-width * .55} ${height * .7} Q 0 ${height * .4} ${width * .55} ${height * .7} Q 0 ${height * 1.08} ${-width * .55} ${height * .7} Z` : '');
      this.root.dataset.mouthLevel = level.toFixed(3);
    } else this.root.dataset.mouthLevel = '0';
    this.frame = requestAnimationFrame(() => this.draw());
  }

  dispose() {
    this.disposed = true;
    this.controller.abort();
    for (const [video, callback] of this.videoCallbacks) video.cancelVideoFrameCallback(callback);
    this.videoCallbacks.clear();
    cancelAnimationFrame(this.frame);
    this.setActive(false);
  }
}
