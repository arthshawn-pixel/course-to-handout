/* Execute ONLY through a host browser tool that explicitly supports page JavaScript
 * with network requests, inside the user-authorized Bilibili video tab.
 * It returns transcript content, never cookies or signed subtitle URLs.
 * CommonJS export exists for offline behavioral tests, not for browser-session emulation.
 */
async function exportBilibiliSubtitles(options = {}) {
  const pageURL = new URL(globalThis.location.href);
  const match = pageURL.pathname.match(/^\/video\/(BV[0-9A-Za-z]+|av\d+)\/?$/);
  if (pageURL.protocol !== 'https:' || !['www.bilibili.com', 'bilibili.com'].includes(pageURL.hostname) || !match) {
    return {status: 'wrong_page', message: '请在用户指定的 B 站视频标签页执行。'};
  }
  const part = options.part ?? Number(pageURL.searchParams.get('p') || 1);
  if (!Number.isSafeInteger(part) || part < 1) return {status: 'invalid_part'};
  const video = match[1];
  async function request(url, credentials) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {credentials, signal: controller.signal});
      if (!response.ok) throw new Error('HTTP_' + response.status);
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  try {
    const identity = video.startsWith('BV') ? 'bvid=' + encodeURIComponent(video) : 'aid=' + video.slice(2);
    const metadata = await request('https://api.bilibili.com/x/web-interface/view?' + identity, 'include');
    if (metadata.code !== 0 || !metadata.data) return {status: 'resource_unavailable', code: metadata.code};
    const data = metadata.data;
    const page = data.pages?.find(p => p.page === part);
    if (!page) return {status: 'invalid_part', available_parts: data.pages?.length || 0};
    const player = await request('https://api.bilibili.com/x/player/wbi/v2?aid=' + data.aid + '&cid=' + page.cid, 'include');
    if (player.code !== 0 || !player.data) return {status: 'resource_unavailable', code: player.code};
    const tracks = (player.data.subtitle?.subtitles || []).filter(t => t.subtitle_url && t.lan);
    if (!tracks.length) {
      return {status: player.data.need_login_subtitle ? 'waiting_login' : 'no_subtitle_returned',
              source: {bvid: data.bvid, part, cid: page.cid},
              message: player.data.need_login_subtitle ? '请用户在当前浏览器会话登录后再执行。' : '当前会话没有返回可读字幕；不是对所有会话的不存在证明。'};
    }
    const chinese = tracks.filter(t => /^(ai-)?zh(?:-|$)/i.test(t.lan));
    const candidates = options.language ? tracks.filter(t => t.lan === options.language) : chinese;
    if (!candidates.length) return {status: 'choose_language', languages: tracks.map(t => ({language: t.lan, label: t.lan_doc || t.lan}))};
    candidates.sort((a,b) => Number(a.lan.startsWith('ai-')) - Number(b.lan.startsWith('ai-')));
    const track = candidates[0];
    const resource = new URL(track.subtitle_url, pageURL.href);
    if (resource.protocol !== 'https:' || resource.username || resource.password ||
        !['bilibili.com', 'hdslb.com'].some(d => resource.hostname === d || resource.hostname.endsWith('.' + d))) {
      return {status: 'unsupported_subtitle_host'};
    }
    // Subtitle CDN request receives no account cookies; the signed URL stays inside this function.
    const content = await request(resource.href, 'omit');
    if (!Array.isArray(content.body) || !content.body.length) return {status: 'invalid_subtitle'};
    const duration = Number(page.duration);
    const body = content.body.map(s => ({from: s.from, to: s.to, content: s.content}));
    if (!body.every(s => Number.isFinite(s.from) && Number.isFinite(s.to) && 0 <= s.from &&
                    s.from < s.to && s.to <= duration + 1 && typeof s.content === 'string' && s.content.trim())) {
      return {status: 'invalid_subtitle'};
    }
    return {status: 'exported', schema_version: 1,
            source: {bvid: data.bvid, aid: data.aid, part, cid: page.cid, duration, title: data.title},
            track: {language: track.lan, label: track.lan_doc || track.lan, is_ai: track.lan.startsWith('ai-')},
            body, captured_at: new Date().toISOString()};
  } catch (error) {
    const code = /^HTTP_\d{3}$/.test(error.message) ? error.message : error.name === 'AbortError' ? 'timeout' : 'network_or_browser_capability';
    return {status: 'read_failed', code};
  }
}

if (typeof module !== 'undefined' && module.exports) module.exports = {exportBilibiliSubtitles};
