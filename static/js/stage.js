import { StudioClient, phaseNames } from './client.js';
import { PetRenderer } from './pet-renderer.js';
import { SpeechPlayer } from './speech-player.js';
import { LipSyncDriver } from './lip-sync.js';
import { MouthRenderer } from './mouth-renderer.js';
import { BackgroundMusic } from './background-music.js';

const client = new StudioClient('stage');
const $ = id => document.getElementById(id);
const pet = new PetRenderer($('character'), $('character-mode-label'));
const speech = new SpeechPlayer($('speech-audio'));
const music = new BackgroundMusic($('background-music'), $('speech-audio'), status => {
  $('music-status').textContent = ({idle:'音乐待机', off:'音乐已关闭', loading:'音乐加载中',
    playing:'轻柔钢琴 · 播放中', ducked:'轻柔钢琴 · 人声优先', error:'音乐不可用，点击重试'}[status]);
  $('toggle-music').textContent = status === 'error' ? '重试音乐' : music.enabled ? '关闭音乐' : '开启音乐';
  document.body.classList.toggle('needs-music', status === 'error');
});
function syncMusic() {
  music.setAllowed(!!client.connectionId && client.state?.playback_owner_id === client.connectionId &&
    client.state?.mode === 'running' && speech.enabled);
}
const mouth = new MouthRenderer($('character'), () => {
  $('lip-sync-status').textContent = '口型跟踪不可用';
});
const lipSync = new LipSyncDriver($('speech-audio'), level => mouth.setLevel(level), status => {
  $('character').dataset.lipSync = status;
  $('lip-sync-status').textContent = $('character').dataset.mouthTracking === 'unavailable' ? '口型跟踪不可用' :
    ({idle:'口型待机', preparing:'准备口型', ready:'语音口型已就绪', unavailable:'口型分析不可用'}[status]);
  if (status === 'unavailable') {
    mouth.setActive(false);
    $('stage-notice').textContent = '口型分析暂不可用，语音仍正常播放。';
  }
});
let active = null;
let timer = null;
let declaredFor = null;
let lastCaption = '';
let runtimeErrorShown = false;
let unlocking = false;
const captureAutoAudio = new URLSearchParams(location.search).get('view') === 'obs' &&
  new URLSearchParams(location.search).get('audio') === 'auto';
let autoAudioTried = false;
const scene = document.querySelector('.portrait-stage');
const captionObserver = new MutationObserver(() => {
  scene.classList.toggle('has-long-caption', $('caption').textContent.length > 70);
});
captionObserver.observe($('caption'), { childList: true, characterData: true, subtree: true });
// Font metrics and line wrapping vary with the viewport. Measure the rendered
// caption as well, so a three-line reply cannot cover the clock or mood tag.
const captionResize = new ResizeObserver(() => {
  const stageBox = scene.getBoundingClientRect();
  const captionBox = document.querySelector('.caption-wrap').getBoundingClientRect();
  scene.classList.toggle('hide-auxiliary', captionBox.bottom > stageBox.top + stageBox.height * .365);
});
captionResize.observe(document.querySelector('.caption-wrap'));
const clockFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hour:'2-digit', minute:'2-digit', hourCycle:'h23'
});
function updateClock() {
  const now = new Date();
  const parts = clockFormat.formatToParts(now);
  const hour = Number(parts.find(part => part.type === 'hour').value);
  const minute = Number(parts.find(part => part.type === 'minute').value);
  $('local-clock').textContent = clockFormat.format(now);
  $('local-clock').dateTime = now.toISOString();
  document.querySelector('.clock-face').style.setProperty('--hour-angle', `${(hour % 12) * 30 + minute / 2}deg`);
  document.querySelector('.clock-face').style.setProperty('--minute-angle', `${minute * 6}deg`);
}
updateClock();
const clockTimer = setInterval(updateClock, 1000);
const chatIds = new Set();
function clearDeskChat() {
  chatIds.clear();
  $('desk-chat').replaceChildren();
  $('chat-empty').hidden = false;
}
client.addEventListener('danmaku.received', event => {
  const data = event.detail.data;
  if (data.source !== 'bilibili' || typeof data.event_id !== 'string' ||
      typeof data.user !== 'string' || typeof data.text !== 'string' || chatIds.has(data.event_id)) return;
  chatIds.add(data.event_id);
  if (chatIds.size > 100) chatIds.delete(chatIds.values().next().value);
  const line = document.createElement('li');
  const name = document.createElement('strong');
  name.textContent = `${data.user.slice(0, 32)}：`;
  line.append(name, document.createTextNode(data.text.slice(0, 200)));
  $('desk-chat').prepend(line);
  while ($('desk-chat').children.length > 3) $('desk-chat').lastChild.remove();
  $('chat-empty').hidden = true;
});

function stop() {
  clearTimeout(timer);
  timer = null;
  active = null;
  mouth.setActive(false);
  lipSync.reset();
  speech.stop();
  pet.stop();
}
function voiceMode() { return !!client.state && client.state.tts_mode !== 'off'; }
function ready(claim = true, available = true) {
  const audioReady = !voiceMode() || speech.enabled;
  return client.send('renderer.ready', {
    ready: available && audioReady, claim_playback: claim,
    audio_status: voiceMode() ? (speech.enabled ? 'ready' : 'blocked') : 'off',
    character_mode: 'demo'
  });
}
function updateVoiceButton() {
  const needsSetup = client.state?.playback_owner_id !== client.connectionId || (voiceMode() && !speech.enabled);
  document.body.classList.toggle('needs-audio', needsSetup);
  document.querySelector('.stage-bottom').inert = document.documentElement.classList.contains('obs-view') && !needsSetup;
  $('enable-audio').hidden = !voiceMode();
  $('enable-audio').disabled = unlocking || !client.connectionId;
  $('enable-audio').textContent = unlocking ? '正在启用…' : speech.enabled ? '关闭声音' : '启用声音';
  $('enable-audio').classList.toggle('primary', !speech.enabled);
  $('enable-audio').classList.toggle('secondary', speech.enabled);
}
function confirm(type, identity, extra = {}) {
  client.send(type, { ...identity, ...extra });
}
client.addEventListener('invalidate', event => {
  music.setAllowed(false);
  stop();
  if (event.detail === 'instance') {
    clearDeskChat();
    autoAudioTried = false;
    lastCaption = '';
    runtimeErrorShown = false;
  }
});
client.addEventListener('connection', event => {
  const connected = event.detail === 'connected';
  $('connection').textContent = connected ? '本地已连接' : event.detail === 'connecting' ? '正在连接' : '连接已断开，正在重连';
  $('connection').classList.toggle('online', connected);
  if (!connected) {
    music.setAllowed(false);
    clearDeskChat();
    $('chat-status').textContent = '重连中';
    declaredFor = null;
    $('owner-label').textContent = '等待连接';
    $('claim').disabled = true;
    $('enable-audio').disabled = true;
    $('caption').textContent = '工位信号断了一下，马上回来。';
  }
});
client.addEventListener('state', event => {
  const state = event.detail;
  if (declaredFor !== client.connectionId) {
    declaredFor = client.connectionId;
    ready();
  }
  const owns = state.playback_owner_id === client.connectionId;
  syncMusic();
  if (owns && $('stage-notice').textContent === '正在申请播放权。') {
    $('stage-notice').textContent = '播放权已就绪，可以开始聊天。';
  }
  $('ai-name').textContent = state.ai_name || '大肥鱼';
  $('brain-mode').textContent = state.llm_mode === 'openai' ? '真实 AI' : '本地演示';
  $('voice-mode').textContent = !voiceMode() ? '语音关闭' : state.tts_status === 'error' ? '语音失败 · 字幕回退' : state.tts_mode === 'qwen_local' ? '小鲸固定声线' : 'Edge 语音';
  $('stage-version').textContent = state.llm_mode === 'demo' && !voiceMode() ? '本地字幕演示' : 'AI 语音直播间';
  $('owner-label').textContent = owns ? '播放舞台' : state.playback_owner_id ? '静音预览' : voiceMode() && !speech.enabled ? '等待启用声音' : '等待播放权';
  $('claim').disabled = false;
  $('claim').textContent = owns ? '释放播放权' : '申请播放权';
  updateVoiceButton();
  if (captureAutoAudio && voiceMode() && !speech.enabled && !autoAudioTried) {
    autoAudioTried = true;
    queueMicrotask(() => enableVoice());
  }
  $('stage-status').textContent = state.mode === 'paused' ? '已暂停' : state.phase === 'playing' && !voiceMode() ? '字幕展示中' : phaseNames[state.phase];
  $('stage-status').classList.toggle('is-running', state.mode === 'running');
  $('queue-count').textContent = `${state.queue_size} 条待回复`;
  $('completed-count').textContent = state.counters.completed;
  $('accepted-count').textContent = state.counters.accepted;
  $('chat-status').textContent = state.bili_mode === 'off' ? '未接入' :
    state.mode === 'paused' ? '已暂停' : state.bili_status === 'connected' ? '实时弹幕' : '连接中';
  $('mood-label').textContent = state.mode === 'paused' ? '发会儿呆' :
    ({neutral:'轻松摸鱼', happy:'今天超开心', shy:'有点害羞', sad:'慢慢陪着你'}[state.current?.emotion] || '轻松摸鱼');
  $('character').dataset.emotion = state.current?.emotion || 'neutral';
  if (state.mode === 'paused') {
    // A harmless paused snapshot must not cancel an in-progress audio unlock.
    if (!unlocking) stop();
    $('caption').textContent = '歇一小会儿，等你来聊。';
    $('caption-kind').textContent = '等待开始';
  } else if (state.current?.text && (!voiceMode() || ['awaiting_playback', 'playing'].includes(state.phase))) {
    $('caption').textContent = state.current.text;
    $('caption-kind').textContent = state.current.kind === 'reply' ? '回复观众' : '自主聊天';
    lastCaption = state.current.text;
  } else if (!active) {
    $('caption').textContent = lastCaption || '来了就坐，隔壁工位给你留着。';
    $('caption-kind').textContent = state.blocked_reason === 'no_renderer' ? '等待舞台就绪' : state.blocked_reason === 'audio_blocked' ? '等待启用声音' : ['generating', 'synthesizing'].includes(state.phase) ? '正在准备下一句' : '稍作休息';
  }
  if (active && state.current?.utterance_id !== active.utterance_id) stop();
  if (state.mode === 'paused' || state.phase === 'idle') pet.stop();
  else if (state.phase === 'generating' || state.phase === 'synthesizing') pet.setState('thinking');
  else if (state.phase === 'playing') pet.setState('speaking');
  else pet.stop();
  if (state.last_error) {
    runtimeErrorShown = true;
    $('stage-notice').textContent = state.last_error.message;
  } else if (runtimeErrorShown) {
    runtimeErrorShown = false;
    $('stage-notice').textContent = '已恢复，可以继续聊天。';
  } else if (voiceMode() && !speech.enabled && !unlocking) {
    $('stage-notice').textContent = '点击「启用声音」后申请播放权，其他舞台保持静音。';
  } else if (voiceMode() && speech.enabled) {
    $('stage-notice').textContent = owns ? '声音已启用，暂停或断连会立即停止当前语音。' : '声音已启用，本窗口当前为静音预览。';
  } else if (state.llm_mode === 'openai') {
    $('stage-notice').textContent = '真实模型已配置，当前使用字幕模式。';
  } else {
    $('stage-notice').textContent = owns ? '字幕舞台已就绪，可以在控制台开始聊天。' : '本窗口为字幕预览，可申请播放权。';
  }
});
client.addEventListener('utterance.ready', event => {
  const message = event.detail;
  if (client.state?.playback_owner_id !== client.connectionId || message.epoch !== client.epoch) return;
  if (active?.utterance_id === message.data.utterance_id) return;
  stop();
  active = { instance_id: message.instance_id, epoch: message.epoch, utterance_id: message.data.utterance_id };
  const identity = active;
  $('caption').textContent = message.data.text;
  $('caption-kind').textContent = message.data.kind === 'reply' ? '回复观众' : '自主聊天';
  lastCaption = message.data.text;
  if (message.data.audio_url) {
    speech.play(message.data.audio_url, {
      started: () => {
        if (active !== identity) return;
        pet.setState('speaking');
        mouth.setActive($('character').dataset.lipSync !== 'unavailable');
        confirm('playback.started', identity);
      },
      ended: () => {
        if (active !== identity) return;
        confirm('playback.ended', identity);
        stop();
      },
      error: code => {
        if (active !== identity) return;
        confirm('playback.error', identity, { code });
        stop();
        music.setAllowed(false);
        updateVoiceButton();
        $('stage-notice').textContent = code === 'autoplay_blocked' ? '浏览器阻止了声音，请重新点击「启用声音」。' : '音频播放失败，请重新启用声音。';
      }
    });
  } else {
    pet.setState('speaking');
    confirm('playback.started', identity);
    timer = setTimeout(() => {
      if (active !== identity) return;
      confirm('playback.ended', identity);
      stop();
    }, message.data.display_duration_ms);
  }
});
client.addEventListener('utterance.cancel', () => stop());
client.addEventListener('system.error', event => { $('stage-notice').textContent = event.detail.data.message; });
async function enableVoice() {
  if (speech.enabled || unlocking || !client.connectionId) return;
  unlocking = true;
  updateVoiceButton();
  try {
    await speech.enable();
    ready();
    $('stage-notice').textContent = '声音已启用，正在申请播放权。';
  } catch (error) {
    speech.disable();
    ready(false, false);
    $('stage-notice').textContent = '暂时无法启用声音，请再次点击按钮。';
  } finally {
    unlocking = false;
    updateVoiceButton();
  }
}
$('enable-audio').addEventListener('click', () => {
  if (!speech.enabled) { enableVoice(); return; }
  stop();
  speech.disable();
  music.setAllowed(false);
  ready(false, false);
  updateVoiceButton();
});
$('claim').addEventListener('click', () => {
  const owns = client.state?.playback_owner_id === client.connectionId;
  if (!owns && voiceMode() && !speech.enabled) {
    $('stage-notice').textContent = '请先点击「启用声音」。';
    return;
  }
  ready(!owns, !owns);
  if (owns) music.setAllowed(false);
  $('stage-notice').textContent = owns ? '已释放播放权，可在其他舞台申请。' : client.state?.playback_owner_id ? '另一个舞台正在播放，本窗口保持静音预览。' : '正在申请播放权。';
});
$('toggle-music').addEventListener('click', () => music.toggle());
window.addEventListener('pagehide', () => { music.dispose(); clearInterval(clockTimer); captionObserver.disconnect(); captionResize.disconnect(); stop(); lipSync.dispose(); mouth.dispose(); pet.dispose(); client.close(); });
