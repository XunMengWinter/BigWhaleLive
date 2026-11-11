import { StudioClient, phaseNames, post } from './client.js';

const $ = id => document.getElementById(id);
const client = new StudioClient('control');
const seen = new Set();
const seenDanmaku = new Set();
let pending = null;
let everStarted = false;
let runtimeErrorShown = false;
const emptyFeed = $('feed-empty').cloneNode(true);
client.addEventListener('invalidate', event => {
  if (event.detail !== 'instance') return;
  seen.clear();
  seenDanmaku.clear();
  pending = null;
  everStarted = false;
  runtimeErrorShown = false;
  $('message-feed').replaceChildren(emptyFeed.cloneNode(true));
});

function notice(text, error = false) {
  $('notice').textContent = text;
  $('notice').classList.toggle('error', error);
}
function addMessage(kind, name, text) {
  $('feed-empty')?.remove();
  const item = document.createElement('li');
  item.className = `message ${kind}`;
  const header = document.createElement('div');
  header.className = 'message-meta';
  const author = document.createElement('strong');
  author.textContent = name;
  const time = document.createElement('time');
  time.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  header.append(author, time);
  const body = document.createElement('p');
  body.textContent = text;
  item.append(header, body);
  $('message-feed').prepend(item);
  while ($('message-feed').children.length > 16) $('message-feed').lastChild.remove();
}
function render(state) {
  const running = state.mode === 'running';
  everStarted ||= running;
  const biliFailed = state.bili_mode !== 'off' && state.bili_mode && state.bili_status === 'error';
  $('start').textContent = running ? biliFailed ? '重连弹幕' : '主播运行中' : everStarted ? '恢复主播' : '开始主播';
  $('start').disabled = running && !biliFailed;
  $('pause').disabled = !running;
  $('skip').disabled = !state.current;
  $('run-state').textContent = running ? '运行中' : '已暂停';
  $('run-state').classList.toggle('is-running', running);
  $('phase').textContent = state.phase === 'playing' && state.tts_mode === 'off' ? '字幕展示中' : phaseNames[state.phase];
  $('llm-description').textContent = state.llm_mode === 'openai' ? `真实 AI · ${state.llm_model}` : '本地预设文案 · 演示';
  const voiceStatus = {idle: '等待合成', ok: '已合成', error: '失败，字幕回退'};
  $('tts-description').textContent = state.tts_mode !== 'off' ? `${state.tts_mode === 'qwen_local' ? '小鲸固定声线' : 'Edge TTS'} · ${voiceStatus[state.tts_status] || '等待合成'}` : '关闭 · 字幕模式';
  const platformStatus = {connecting:'连接中', connected:'已连接', error:'连接失败'};
  const platformName = state.bili_mode === 'web' ? 'B站网页弹幕' : 'B站官方弹幕';
  $('bili-description').textContent = state.bili_mode && state.bili_mode !== 'off' ? `${platformName} · ${platformStatus[state.bili_status] || '等待连接'}` : '模拟弹幕 · B站未启用';
  const bili = state.diagnostics?.bilibili;
  const webHelp = {web_guest_session_required:'当前仅允许访客连接，请重新启动不带账号会话的读取客户端。',
    web_auth_rejected:'平台拒绝了访客鉴权，请稍后重连；本模式不会登录账号。',
    web_http_rejected:'网页接口拒绝了请求，请稍后重连；本模式不会登录账号。'};
  $('bili-detail').textContent = !bili ? '配置网页房间或开放平台后重启，可启用真实弹幕。' :
    state.bili_status === 'error' ? `${state.bili_mode === 'web' ? webHelp[bili.reason] || '请检查房间、网络与网页会话，再点击重连。' : '请检查开放平台配置与授权，再点击重连。'}错误：${bili.reason || 'connection_failed'}${bili.error_code !== null ? ` (${bili.error_code})` : ''}` :
    `${state.bili_room_id ? `房间 ${state.bili_room_id} · ` : ''}${state.bili_mode === 'web' ? `访客 · ${bili.live_status === 1 ? '直播中' : '未开播'} · ` : ''}收到 ${bili.received} 条，入队 ${bili.accepted} 条，重复 ${bili.duplicate} 条；${state.bili_mode === 'web' && bili.anonymous ? `匿名 ${bili.anonymous} 条（共用匿名冷却）。` : ''}暂停时保持连接并丢弃新弹幕。${bili.end_failures ? '上次场次收尾未确认，请检查平台状态。' : ''}`;
  $('control-version').textContent = state.llm_mode === 'demo' && state.tts_mode === 'off' ? '本地字幕演示' : '真实服务模式';
  $('queue-size').textContent = state.queue_size;
  $('completed').textContent = state.counters.completed;
  $('accepted').textContent = state.counters.accepted;
  $('failed').textContent = state.counters.failed;
  $('queue-detail').textContent = `过期 ${state.counters.expired} · 重复 ${state.counters.duplicate} · 拒绝 ${state.counters.rejected}`;
  $('renderer-state').textContent = state.playback_owner_id ? '播放舞台已就绪' : '等待打开舞台';
  $('renderer-dot').classList.toggle('online', !!state.playback_owner_id);
  $('state-detail').textContent = state.blocked_reason === 'no_renderer' ? '请打开舞台并申请播放权，随后继续。' :
    state.blocked_reason === 'provider_backoff' ? '本轮生成失败，稍后继续处理新消息。' :
    state.blocked_reason === 'audio_blocked' ? '请在舞台启用声音。' : running ? '空闲时会主动发言，弹幕会优先进入下一轮。' : '舞台就绪后，点击开始。';
  if (state.current?.text && !seen.has(state.current.utterance_id)) {
    seen.add(state.current.utterance_id);
    if (seen.size > 100) seen.delete(seen.values().next().value);
    addMessage('ai', `${state.ai_name || '大肥鱼'} · ${state.current.kind === 'reply' ? '回复观众' : '自主聊天'}`, state.current.text);
  }
  if (state.last_error) {
    runtimeErrorShown = true;
    notice(state.last_error.message, true);
  } else if (runtimeErrorShown) {
    runtimeErrorShown = false;
    notice('已恢复，主播可以继续聊天。');
  }
}
client.addEventListener('state', event => render(event.detail));
client.addEventListener('danmaku.received', event => {
  const data = event.detail.data;
  if (data.source !== 'bilibili' || seenDanmaku.has(data.event_id)) return;
  seenDanmaku.add(data.event_id);
  if (seenDanmaku.size > 100) seenDanmaku.delete(seenDanmaku.values().next().value);
  addMessage('viewer', `${data.user} · B站`, data.text);
});
client.addEventListener('connection', event => {
  const online = event.detail === 'connected';
  $('connection').textContent = online ? '本地已连接' : event.detail === 'connecting' ? '正在连接' : '连接中断，正在重连';
  $('connection').classList.toggle('online', online);
  if (!online) document.querySelectorAll('[data-action]').forEach(button => { button.disabled = true; });
});
client.addEventListener('system.error', event => notice(event.detail.data.message, true));
for (const button of document.querySelectorAll('[data-action]')) {
  button.addEventListener('click', async () => {
    const action = button.dataset.action;
    const reconnecting = ['start', 'resume'].includes(action) && client.state?.mode === 'running' && client.state?.bili_status === 'error';
    button.disabled = true;
    try {
      await post('/api/control', { action });
      // WebSocket snapshots carry ordering. An HTTP response may arrive after
      // a newer platform update, so it must not overwrite the live state.
      notice(reconnecting ? client.state?.bili_status === 'connected' ? '弹幕连接已恢复。' : '正在重连弹幕，结果见平台状态。' :
        action === 'pause' ? '已暂停并清空等待队列。' : action === 'skip' ? '已跳过当前发言。' : '主播已开始，等待舞台或新弹幕。');
    } catch (error) {
      notice(error.message, true);
      if (client.state) render(client.state);
    }
  });
}
$('danmaku-form').addEventListener('submit', async event => {
  event.preventDefault();
  const user = $('user').value.trim();
  const text = $('text').value.trim();
  if (!user || !text) { notice('请填写观众昵称和弹幕内容。', true); return; }
  if (!pending || pending.user !== user || pending.text !== text) pending = { user, text, client_message_id: crypto.randomUUID() };
  $('send').disabled = true;
  try {
    const result = await post('/api/danmaku', pending);
    if (!result.duplicate) addMessage('viewer', user, text);
    notice(result.duplicate ? '这条弹幕已接收，没有重复入队。' : '弹幕已入队，主播会在下一轮回复。');
    pending = null;
    $('text').value = '';
    $('text').dispatchEvent(new Event('input'));
  } catch (error) { notice(error.message, true); }
  finally { $('send').disabled = false; }
});
$('text').addEventListener('input', () => { $('char-count').textContent = `${Array.from($('text').value).length} / 200`; });
for (const button of document.querySelectorAll('[data-example]')) {
  button.addEventListener('click', () => {
    $('text').value = button.dataset.example;
    $('text').dispatchEvent(new Event('input'));
    $('text').focus();
  });
}
window.addEventListener('pagehide', () => client.close());
