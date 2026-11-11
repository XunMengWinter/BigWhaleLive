export class StudioClient extends EventTarget {
  constructor(role) {
    super();
    this.role = role;
    this.state = null;
    this.connectionId = null;
    this.instance = null;
    this.epoch = -1;
    this.seq = -1;
    this.retry = 0;
    this.stopped = false;
    this.watchdog = null;
    this.reconnectTimer = null;
    this.connect();
  }
  dispatch(type, detail) { this.dispatchEvent(new CustomEvent(type, { detail })); }
  send(type, data) {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify({ v: 1, type, data }));
    return true;
  }
  connect() {
    if (this.stopped) return;
    this.dispatch('connection', 'connecting');
    this.socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    const socket = this.socket;
    socket.addEventListener('open', () => {
      this.seq = -1;
      this.connectionId = null;
      this.retry = 0;
      this.lastPing = performance.now();
      this.send('client.hello', { role: this.role });
      this.dispatch('connection', 'connected');
      clearInterval(this.watchdog);
      this.watchdog = setInterval(() => {
        if (performance.now() - this.lastPing >= 10000) socket.close();
      }, 1000);
    });
    socket.addEventListener('message', event => {
      let message;
      try { message = JSON.parse(event.data); } catch { socket.close(); return; }
      if (message.v !== 1) { socket.close(); return; }
      if (this.instance !== message.instance_id) {
        this.instance = message.instance_id;
        this.seq = -1;
        this.epoch = -1;
        this.dispatch('invalidate', 'instance');
      }
      if (message.seq <= this.seq || message.epoch < this.epoch) return;
      this.seq = message.seq;
      if (message.epoch > this.epoch) {
        this.epoch = message.epoch;
        this.dispatch('invalidate', 'epoch');
      }
      if (message.type === 'server.ping') {
        this.lastPing = performance.now();
        this.send('client.pong', { token: message.data.token });
      } else if (message.type === 'state.snapshot') {
        this.connectionId = message.data.connection_id;
        this.state = message.data.state;
        this.dispatch('state', this.state);
      } else {
        this.dispatch(message.type, message);
      }
    });
    socket.addEventListener('error', () => this.dispatch('connection', 'disconnected'));
    socket.addEventListener('close', () => {
      clearInterval(this.watchdog);
      this.connectionId = null;
      this.dispatch('invalidate', 'disconnected');
      this.dispatch('connection', 'disconnected');
      if (!this.stopped) {
        const seconds = [1, 2, 4, 8, 16, 30][Math.min(this.retry++, 5)];
        this.reconnectTimer = setTimeout(() => this.connect(), seconds * 1000);
      }
    });
  }
  close() {
    this.stopped = true;
    clearInterval(this.watchdog);
    clearTimeout(this.reconnectTimer);
    this.socket?.close();
  }
}

export async function post(path, data) {
  const response = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || '操作失败，请稍后重试');
  return result;
}

export const phaseNames = {
  idle: '待机', generating: '生成台词', synthesizing: '合成语音',
  awaiting_playback: '等待舞台确认', playing: '正在发言'
};
