const {test} = require('node:test');
const assert = require('node:assert/strict');
const {exportBilibiliSubtitles} = require('../scripts/browser_subtitles.js');

async function run({player, resource, href='https://www.bilibili.com/video/BV12345/?p=2', options={}} = {}) {
  const oldFetch = globalThis.fetch, oldLocation = globalThis.location;
  const calls = [];
  globalThis.location = {href};
  globalThis.fetch = async (url, opts) => {
    calls.push({url, credentials:opts.credentials});
    let value;
    if (url.includes('/x/web-interface/view')) value = {code:0,data:{aid:123,bvid:'BV12345',title:'数学课',pages:[{page:1,cid:11,duration:120},{page:2,cid:22,duration:120}]}};
    else if (url.includes('/x/player/wbi/v2')) value = player || {code:0,data:{need_login_subtitle:true,subtitle:{subtitles:[]}}};
    else value = resource || {body:[{from:1,to:3,content:'定义域为正数。'}]};
    return {ok:true,json:async()=>value};
  };
  try { return {result:await exportBilibiliSubtitles(options), calls}; }
  finally { globalThis.fetch = oldFetch; globalThis.location = oldLocation; }
}
function tracks(...subtitles) { return {code:0,data:{subtitle:{subtitles}}}; }
function track(lan='ai-zh',url='https://aisubtitle.hdslb.com/bfs/subtitle/demo.json?auth_key=PRIVATE') {
  return {lan,lan_doc:'中文（自动生成）',subtitle_url:url};
}

test('an explicit subtitle login requirement stops before content retrieval', async()=>{
  const {result,calls}=await run();
  assert.equal(result.status,'waiting_login');assert.equal(result.source.part,2);assert.equal(calls.length,2);
  assert.ok(calls.every(c=>c.credentials==='include'));
});
test('same-session export contains transcript and identity, not signed URL or credentials',async()=>{
  const {result,calls}=await run({player:tracks(track())});
  assert.equal(result.status,'exported');assert.equal(result.source.cid,22);assert.equal(result.track.is_ai,true);
  assert.equal(result.body[0].content,'定义域为正数。');
  assert.equal(calls[2].credentials,'omit');assert.ok(!JSON.stringify(result).includes('PRIVATE'));
  assert.ok(!JSON.stringify(result).includes('subtitle_url'));
});
test('no tracks without a login flag does not claim login is required',async()=>{
  const {result}=await run({player:{code:0,data:{subtitle:{subtitles:[]}}}});
  assert.equal(result.status,'no_subtitle_returned');
});
test('wrong part is not silently replaced by the first part',async()=>{
  const {result,calls}=await run({options:{part:3}});
  assert.equal(result.status,'invalid_part');assert.equal(calls.length,1);
});
test('only approved subtitle CDN hosts are fetched',async()=>{
  const {result,calls}=await run({player:tracks(track('ai-zh','https://example.com/collect'))});
  assert.equal(result.status,'unsupported_subtitle_host');assert.equal(calls.length,2);
});
test('a manually supplied Chinese track is preferred over generated Chinese',async()=>{
  const {result,calls}=await run({player:tracks(track(),track('zh-Hans','https://aisubtitle.hdslb.com/manual.json'))});
  assert.equal(result.track.language,'zh-Hans');assert.equal(result.track.is_ai,false);
  assert.ok(calls[2].url.endsWith('/manual.json'));
});
test('a different page cannot initiate any requests',async()=>{
  const {result,calls}=await run({href:'https://example.com/video/BV12345/'});
  assert.equal(result.status,'wrong_page');assert.equal(calls.length,0);
});
test('malformed subtitle timestamps are rejected',async()=>{
  const {result}=await run({player:tracks(track()),resource:{body:[{from:1,to:0,content:'错误时间'}]}});
  assert.equal(result.status,'invalid_subtitle');
});
