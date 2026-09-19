const {test}=require('node:test');
const assert=require('node:assert/strict');
const G=require('../mobile/guide.js');
const S=require('../mobile/speech.js');
const sample={v:1, question:'Was bedeutet E:23?',summary:'Wasser in der Bodenwanne.',intro:'Hinweise:',steps:['Wasserhahn schließen.','Kundendienst rufen!'],references:['Handbuch · Querverweis 36'],date:'2026-09-19'};

test('QR roundtrip preserves the complete German answer without query parameters',async()=>{
  const url=new URL(await G.makeUrl('https://example.org/viewer/',sample));
  assert.equal(url.search,''); assert.ok(url.hash.startsWith('#g1.'));
  assert.deepEqual(await G.decode(url.hash),sample);
});
test('only answer fields are shared; no application credentials or source payload',()=>{
  assert.deepEqual(G.validate({...sample,api_key:'do-not-copy',sources:[{text:'not shared'}]}),sample);
});
test('credential-like content is blocked even inside a question',()=>{
  assert.throws(()=>G.validate({...sample,question:'sk-'+'x'.repeat(30)}),/API-Schlüssel/);
});
test('HTML/script injection remains inert text in mobile and offline views',()=>{
  const html=G.portableHTML({...sample,steps:['<img src=x onerror=alert(1)>','</main><script>alert(1)</script>']});
  assert.ok(!html.includes('<script>')); assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;script&gt;'));
});
test('oversized QR is rejected rather than truncating the answer',async()=>{
  const noise=require('node:crypto').randomBytes(3500).toString('hex');
  await assert.rejects(G.makeUrl('https://example.org/',{...sample,steps:[noise]}),/zu lang/);
});
test('invalid payload and unsafe viewer scheme are rejected',async()=>{
  await assert.rejects(G.decode('#g1.NOT_A_GZIP'));
  await assert.rejects(G.makeUrl('javascript:alert(1)',sample),/HTTPS/);
});
test('decompression has a hard size limit',async()=>{
  const compressed=require('node:zlib').gzipSync('x'.repeat(100000)).toString('base64url');
  await assert.rejects(G.decode('#g1.'+compressed),/zu groß/);
});
test('speech and mobile steps preserve all response items',()=>{
  const guide=G.fromResponse({tts_summary:'E18',results:[{content:'Einleitung\n- [ ] **Pumpe:** reinigen\n- [ ] **Ablauf:** reinigen',reference:'Quelle'}]},'E18?');
  assert.deepEqual(guide.steps,['Pumpe: reinigen','Ablauf: reinigen']);
  assert.ok(G.speechText(guide).includes('Schritt 2. Ablauf: reinigen'));
});
function controls(){return {button:{textContent:'',disabled:false,setAttribute(){}},status:{textContent:''}};}
test('missing speech API does not break the app',()=>{
  delete global.speechSynthesis; delete global.SpeechSynthesisUtterance;
  const c=controls(), player=S.create(c.button,c.status); player.speak('Test');
  assert.equal(c.button.disabled,true); assert.match(c.status.textContent,/keine Sprachausgabe/);
});
function setupSpeech(){
  const spoken=[]; global.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};
  global.speechSynthesis={cancel(){},getVoices:()=>[{lang:'de-DE',localService:true,name:'local'}],speak:u=>spoken.push(u)};
  const c=controls(); return {...c,spoken,player:S.create(c.button,c.status)};
}
test('speech reports actual start and reads all chunks to completion',()=>{
  const c=setupSpeech(); c.player.speak('Erster Schritt. Zweiter Schritt.');
  c.spoken[0].onstart(); assert.equal(c.status.textContent,'Vorlesen läuft.');
  c.spoken[0].onend(); assert.equal(c.spoken[1].text,'Zweiter Schritt.');
  c.spoken[1].onend(); assert.equal(c.status.textContent,'Vorlesen beendet.');
});
test('cancel blocks stale callbacks and error is visible',()=>{
  const c=setupSpeech(); c.player.speak('Eins. Zwei.'); c.player.stop(); c.spoken[0].onend();
  assert.equal(c.spoken.length,1);
  c.player.speak('Neuer Text'); c.spoken[1].onerror({error:'not-allowed'});
  assert.match(c.status.textContent,/blockiert/); assert.equal(c.button.textContent,'Vorlesen');
});
test('long utterances are split without dropping words',()=>{
  const c=setupSpeech(), text=Array.from({length:100},(_,i)=>'Wort'+i).join(' ');
  c.player.speak(text);
  for(let i=0;i<c.spoken.length;i++) c.spoken[i].onend();
  assert.ok(c.spoken.every(u=>u.text.length<=180));
  assert.equal(c.spoken.map(u=>u.text).join(' '),text);
});
