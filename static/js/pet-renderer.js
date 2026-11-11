/** Local dsh-pet media only. Animation never drives dialogue acknowledgements. */
export class PetRenderer {
  constructor(root, label, { now = () => performance.now() } = {}) {
    this.root = root;
    this.label = label;
    this.videos = new Map([...root.querySelectorAll('video[data-clip]')].map(video => [video.dataset.clip, video]));
    this.current = null;
    this.requested = null;
    this.targetState = 'idle';
    this.revision = 0;
    this.now = now;
    this.pending = null;
    this.disposed = false;
    this.recoveries = 0;
    this.nextRetryAt = 0;
    this.lastProgressAt = this.now();
    this.lastSample = null;
    this.motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
    // Upstream explicitly documents Safari's missing WebM-alpha support.
    const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    this.safari = ios || (/Safari/.test(navigator.userAgent) && !/Chrome|Chromium|CriOS|Edg|OPR/.test(navigator.userAgent));
    this.failed = false;
    this.errorHandlers = new Map();
    for (const video of this.videos.values()) {
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      const onError = () => {
        if (!this.disposed && this.targetState === video.dataset.clip) {
          this.nextRetryAt = this.now() + 1000;
          this.showPoster(video.error?.code === 4);
        }
      };
      this.errorHandlers.set(video, onError);
      video.addEventListener('error', onError);
    }
    this.onPreferenceChange = () => {
      this.requested = null;
      this.setState(this.targetState);
    };
    this.motionPreference.addEventListener('change', this.onPreferenceChange);
    this.onWake = () => {
      if (this.disposed || document.hidden || this.safari || this.motionPreference.matches || this.failed) return;
      this.recoveries = 0;
      this.nextRetryAt = 0;
      this.requested = null;
      this.setState(this.targetState);
    };
    document.addEventListener('visibilitychange', this.onWake);
    window.addEventListener('focus', this.onWake);
    this.watchdog = setInterval(() => this.checkPlayback(), 1000);
    this.setState('idle');
  }

  showPoster(failed = false) {
    this.failed ||= failed;
    this.revision += 1;
    this.current = null;
    this.requested = null;
    this.pending = null;
    this.root.classList.remove('has-video');
    this.root.dataset.motion = 'static';
    for (const video of this.videos.values()) {
      video.pause();
      video.classList.remove('is-active');
    }
    this.label.textContent = '大肥鱼 · 静态立绘 ↗';
  }

  async setState(state) {
    if (this.disposed) return;
    const clip = this.videos.has(state) ? state : 'idle';
    const changed = this.targetState !== clip;
    this.targetState = clip;
    if (changed) {
      this.recoveries = 0;
      this.nextRetryAt = 0;
    }
    if (this.safari || this.motionPreference.matches || this.failed) {
      this.showPoster();
      return;
    }
    const next = this.videos.get(clip);
    if (this.pending?.clip === clip) return;
    if (this.requested === clip && this.current === next && !next.paused && !next.ended && !next.error) return;
    if (!changed && this.now() < this.nextRetryAt) return;
    this.requested = clip;
    const revision = ++this.revision;
    this.pending = { clip, revision, beganAt: this.now() };
    if (next.error) {
      this.nextRetryAt = this.now() + 1000;
      this.showPoster(next.error.code === 4);
      return;
    }
    try {
      if (next.readyState >= HTMLMediaElement.HAVE_METADATA && (this.current !== next || next.ended)) next.currentTime = 0;
      await next.play();
      if (revision !== this.revision) {
        if (this.current !== next && this.requested !== clip) next.pause();
        return;
      }
      this.current = next;
      this.pending = null;
      this.lastProgressAt = this.now();
      this.lastSample = this.sample(next);
      for (const video of this.videos.values()) {
        video.classList.toggle('is-active', video === next);
        if (video !== next) video.pause();
      }
      this.root.classList.add('has-video');
      this.root.dataset.motion = clip;
      this.label.textContent = '大肥鱼 · dsh-pet 动画 ↗';
    } catch (error) {
      // AbortError/network/decoder interruptions can recover. Only an actual
      // unsupported format permanently selects the explicit static fallback.
      if (revision === this.revision) {
        this.nextRetryAt = this.now() + 1000;
        this.showPoster(error.name === 'NotSupportedError' || next.error?.code === 4);
      }
    }
  }

  sample(video) {
    const quality = video.getVideoPlaybackQuality?.();
    if (quality?.totalVideoFrames > 0) return `frame:${quality.totalVideoFrames - quality.droppedVideoFrames}`;
    return `time:${video.currentTime}`;
  }

  checkPlayback() {
    if (this.disposed || this.safari || this.motionPreference.matches || this.failed) return;
    const now = this.now();
    if (document.hidden) {
      this.lastProgressAt = now;
      return;
    }
    if (this.pending && now - this.pending.beganAt < 4000) return;
    const video = this.current;
    if (!this.pending && video && !video.paused && !video.ended && !video.error) {
      const sample = this.sample(video);
      if (sample !== this.lastSample) {
        this.lastSample = sample;
        this.lastProgressAt = now;
        this.recoveries = 0;
      }
      if (now - this.lastProgressAt < 4000) return;
    }
    if (now < this.nextRetryAt || this.recoveries >= 3) return;
    this.recoveries += 1;
    this.showPoster();
    const target = this.videos.get(this.targetState);
    try { target.load(); } catch { /* Retain poster while media is unavailable. */ }
    this.nextRetryAt = 0;
    this.setState(this.targetState);
    this.nextRetryAt = now + Math.min(1000 * this.recoveries, 5000);
  }

  stop() { this.setState('idle'); }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    clearInterval(this.watchdog);
    document.removeEventListener('visibilitychange', this.onWake);
    window.removeEventListener('focus', this.onWake);
    this.motionPreference.removeEventListener('change', this.onPreferenceChange);
    for (const [video, handler] of this.errorHandlers) video.removeEventListener('error', handler);
    this.revision += 1;
    this.requested = null;
    this.showPoster();
  }
}
