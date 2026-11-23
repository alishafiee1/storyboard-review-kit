/* Drawing the page: scenes, dialogue lines, pictures with their buttons. */
/* ---------- render */
const label=s=>s.id==='scene-00'?'تامبنیل':`صحنه ${+s.id.slice(6)} · ${s.title}${s.time&&s.time!=='-'?' · '+s.time:''}`;
const labelHtml=s=>s.id==='scene-00'?'<span class="num">★</span><span class="t">تامبنیل</span>':`<span class="num">${+s.id.slice(6)}</span><span class="t">${esc(s.title)}</span>${s.time&&s.time!=='-'?'<span class="tm"><bdi dir="ltr">'+esc(s.time)+'</bdi></span>':''}`;
const issHtml=a=>(a||[]).map(x=>`<div class="issue">⚠ فرمت: ${esc(x.msg)} <button class="b" data-clr="${x.ln}">✓ حل شد</button></div>`).join('');
const flagBtn=ln=>`<button class="flag" data-fl="${ln}" aria-label="ثبت مشکل فرمت" title="ثبت مشکل فرمت این قسمت برای هوش مصنوعی">⚑</button>`;
const val=(txt,ln,key,x='')=>`<span class="v" data-ln="${ln}" data-k="${key}" data-old="${esc(txt)}" ${x} title="کلیک برای ویرایش">${fmt(txt)}</span>`;
const delBtn=(ln,k,txt,hasEn)=>`<button class="flag del" data-del="${ln}" data-dk="${k}" data-old="${esc(txt)}" data-hasen="${hasEn?1:0}" aria-label="حذف" title="حذف">✕</button>`;
const SPK=()=>Object.fromEntries((P.speakers||[]).map(s=>[s.name,s]));
const FALLBACK=['#546e7a','#6d4c41','#00838f','#ad1457','#558b2f'];
const colorOf=n=>(SPK()[n]||{}).color||FALLBACK[[...String(n)].reduce((a,c)=>a+c.charCodeAt(0),0)%FALLBACK.length];
const addBar=ln=>`<div class="addbar" data-after="${ln}"><button data-add="say">+ دیالوگ</button><button data-add="act">+ توضیح صحنه</button></div>`;
const defTone=n=>(SPK()[n]||{}).tone||'';
const toneKnown=t=>!String(t||'').trim()||(P.tts.tones||[]).some(x=>x.words.some(w=>String(t).includes(w)));
const unknownTones=()=>{const m=new Map(),add=t=>{t=String(t||'').trim();if(t&&!toneKnown(t))m.set(t,(m.get(t)||0)+1)};
  (P.speakers||[]).forEach(s=>add(s.tone));P.scenes.forEach(s=>s.blocks.forEach(b=>b.items.forEach(i=>add(i.tone))));return m};
const toneHtml=it=>{const d=defTone(it.sp),eff=it.tone||d;const unk=!toneKnown(eff);return `<span class="v tn${it.tone?'':' dflt'}${unk?' unk':''}" data-ln="${it.ln}" data-k="tone" data-old="${esc(it.tone)}" data-def="${esc(d)}" title="${unk?'این لحن توی فهرست لحن‌ها (voices/voice-config.json) نیست و برچسبی نمی‌فرسته؛ ':''}${it.tone?'لحن این خط':'لحن پیش‌فرض گوینده'}؛ کلیک برای عوض‌کردن">${eff?'('+esc(eff)+')':'+ لحن'}</span>`};
const lineBtns=it=>['fa','en'].filter(lg=>it.audio&&it.audio[lg]).map(lg=>`<button class="ab" data-lg="${lg}" data-src="${esc(it.audio[lg])}" title="${lg==='fa'?'پخش صدای فارسی این دیالوگ':'Play the English voice of this line'}">🔊 ${lg.toUpperCase()}</button>`).join('');
let LA=null,LB=null,START=null;function stopLine(){if(LA){LA.pause();LA=null}if(LB){LB.classList.remove('on');LB=null}}
document.addEventListener('click',e=>{const b=e.target.closest('.ab');if(!b)return;if(LB===b){stopLine();return}
  stopLine();token++;audio.pause();playing=false;$('#play').textContent='▶ پخش';
  const m=/^i(\d+)_(\d+)$/.exec(b.closest('.it').id);if(m)START={n:+m[1],j:+m[2],lg:b.dataset.lg};
  LA=new Audio(b.dataset.src);LB=b;b.classList.add('on');LA.playbackRate=+$('#speed').value;LA.onended=LA.onerror=()=>stopLine();LA.play().catch(()=>stopLine())});
function itemHtml(it,sc,i,j){
  if(it.k==='act')return `<div class="itw"><div class="it act${it.label==='گگ'?' gag':''}" id="i${i}_${j}">${it.label?`<span class="v alab" data-ln="${it.ln}" data-k="label" data-old="${esc(it.label)}" title="کلیک برای عوض‌کردن یا پاک‌کردن برچسب">${esc(it.label)}</span>`:''}${val(it.fa,it.ln,'act')}${flagBtn(it.ln)}${delBtn(it.ln,'act',it.fa,false)}${issHtml(it.issues)}</div></div>`;
  const fa=`<div class="fa">${val(it.fa,it.ln,'say',it.en!=null?'data-hasen="1"':'')}</div>`;
  const en=$('#showEN').checked?(it.en!=null?`<div class="en">${val(it.en,it.en_ln,'en')}${delBtn(it.en_ln,'en',it.en,false)}</div>`:`<div class="en none"><button class="enp" data-aden="${it.ln}" title="افزودن ترجمهٔ انگلیسی">EN+</button></div>`):'';
  return `<div class="itw"><div class="it sp t${(i*7+j)%3}${sc.voice_stale.length?' vstale':''}" style="--c:${colorOf(it.sp)}" id="i${i}_${j}"><div class="who"><span class="dot"></span><span class="v nm" data-ln="${it.ln}" data-k="speaker" data-old="${esc(it.sp)}" title="کلیک برای عوض‌کردن گوینده">${esc(it.sp)}</span>${toneHtml(it)}${lineBtns(it)}${flagBtn(it.ln)}${delBtn(it.ln,'say',it.fa,it.en!=null)}</div>${fa}${en}${issHtml(it.issues)}</div></div>`}
const FX_PH='توصیهٔ ادیت (زوم، پن، فید، لرزش، نور، ذرات، صدا...) · Enter = ذخیره · Shift+Enter = خط بعد · Esc = برگشت';
const fxBox=(key,v,title)=>`<div class="fxbox${v?'':' hide'}" data-key="panel:fx:${key}"><span class="fxl">🎬 ${title}</span><textarea rows="1" data-key="fx:${key}" data-orig="${esc(v)}" placeholder="${FX_PH}">${esc(v)}</textarea></div>`;
function wireFx(box,btn,save){const t=box.querySelector('textarea');track(t,btn);
  let busy=false;const go=async()=>{if(busy)return;if(t.value===t.dataset.orig){if(!t.value.trim())box.classList.add('hide');return}busy=true;try{await save(t.value);t.dataset.orig=t.value;await reload()}catch(e){fail(e)}finally{busy=false}};t._save=go;
  btn.onclick=()=>{box.classList.toggle('hide');if(!box.classList.contains('hide')){grow(t);t.focus()}};t.addEventListener('input',()=>grow(t));if(!box.classList.contains('hide'))grow(t);
  t.addEventListener('blur',()=>setTimeout(()=>{if(document.hasFocus()&&box.isConnected)go()},0));
  t.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();go()}if(e.key==='Escape'){t.value=t.dataset.orig;t.dispatchEvent(new Event('input'));if(!t.value.trim())box.classList.add('hide')}})}
function figHtml(m){
  const im=m.src?`<img src="${m.src}" loading="lazy">`:`<div class="ph"><b>${m.id}</b><br>هنوز ساخته نشده</div>`;
  const rj=m.rejected.length?` ردشده‌ها: ${m.rejected.map((r,i)=>`<a href="${r}" target="_blank">${i+1}</a>`).join('')}`:'';
  const chips=m.refs.map(c=>c.src?`<button class="chip ref" data-ref="${c.src}" data-name="${esc(c.name)}" title="باز کردن رفرنس">${esc(c.name)}</button>${c.video?`<button class="chip ref" data-vid="${esc(c.video)}" data-name="${esc(c.name)}" title="پخش ویدیوی این رفرنس">▶</button>`:''}`:`<span class="chip miss" title="این رفرنس هنوز ساخته نشده">${esc(c.name)}</span>`).join('');
  return `<figure class="shot" data-id="${m.id}" data-m="${m.status}"><div class="idl">${m.id}</div>${im}<div class="ctl">
   <div class="refs">${chips||'<small>بدون رفرنس</small>'}</div>
   <div class="btns"><button class="b" data-m="ok">✅ تأیید</button><button class="b" data-m="redo">🔁 بازسازی</button><button class="b" data-nt="1">📝 یادداشت${m.note?' •':''}</button><button class="b fxb" data-fx="1" title="توصیهٔ ادیت برای این تصویر">🎬 ادیت${m.fx?' •':''}</button><button class="b" data-p="1">پرامپت</button><button class="b" data-vp="1" title="پرامپت ساخت ویدیو از همین تصویر">🎬 پرامپت ویدیو${m.vprompt?'':' ·'}</button>${m.video?`<button class="b vid" data-vid="${esc(m.video)}" data-name="${m.id}" title="پخش ویدیوی این تصویر">▶ ویدیو</button>`:''}<span class="st"></span></div>
   ${m.stale?`<div class="stalebox">⚠ پرامپت عوض شده؛ تصویر کهنه است <button class="b" data-clrimg="1">✓ تصویر به‌روز شد</button></div>`:''}${issHtml(m.issues)}
   <div class="nbox${m.note?'':' hide'}" data-key="panel:note:${m.id}"><textarea class="nt" rows="2" data-key="note:${m.id}" data-orig="${esc(m.note)}" placeholder="یادداشت برای این عکس... (Enter = ذخیره · Shift+Enter = خط بعد · Esc = برگشت)">${esc(m.note)}</textarea>
     <div class="btns" hidden><button class="b" data-sn="1">💾 ذخیره یادداشت</button></div></div>
   ${fxBox(m.id,m.fx||'','ادیت این تصویر')}
   <div class="pr hide${m.stale?' stale':''}" data-key="panel:${m.id}"><small>${rj}</small>
     <div class="btns"><button class="b" data-sp="1">💾 ذخیره پرامپت</button><button class="b" data-cp="1">📋 کپی پرامپت</button></div>
     <textarea data-key="prompt:${m.id}" data-orig="${esc(m.prompt)}" spellcheck="false">${esc(m.prompt)}</textarea></div>
   <div class="pr vpr hide" data-key="panel:v:${m.id}"><small>🎬 پرامپت ساخت ویدیو از همین تصویر (تصویر = فریم اول)</small>
     <div class="btns"><button class="b" data-svp="1">💾 ذخیره پرامپت ویدیو</button><button class="b" data-cvp="1">📋 کپی پرامپت ویدیو</button></div>
     <textarea data-key="vprompt:${m.id}" data-orig="${esc(m.vprompt)}" spellcheck="false" placeholder="هنوز پرامپت ویدیو نداره؛ بنویس و ذخیره کن">${esc(m.vprompt)}</textarea></div></div></figure>`}
function sceneModel(sc){const eff=sc.model||TT().default,m=modelById(eff),need=[...new Set(sc.blocks.flatMap(b=>b.items.filter(i=>i.k==='say').map(i=>i.sp)))];
  const bad=m&&m.voices.length?need.filter(n=>{const s=(P.speakers||[]).find(x=>x.name===n);return s&&!m.voices.some(v=>v.name===s.voice)}):[];
  const lacks=mm=>{const miss=mm.voices.length?need.filter(n=>{const s=(P.speakers||[]).find(x=>x.name===n);return s&&s.voice&&!mm.voices.some(v=>v.name===s.voice)}):[];return miss.length?' · ⚠ صدای '+miss.join('، ')+' را ندارد':''};
  return `<span>مدل صدا: <select data-scm="${sc.id}">${modelOpts(sc.model,true,lacks)}</select></span>${sc.voice_stale.length?`<button class="b" data-regen="${sc.id}" ${bad.length?'disabled title="اول صدای گوینده‌ها رو با این مدل جور کن"':''}>🔊 بازسازی صدا</button>`:''}<span class="jobst" data-job="${sc.id}"></span>${bad.length?`<span class="bad">⚠ این مدل صدای ${bad.map(esc).join('، ')} رو نداره</span>`:''}`}
function render(){const list=$('#list');list.innerHTML='';BL=[];$('#jump').innerHTML='';
  P.scenes.forEach(sc=>{const o=document.createElement('option');o.value=BL.length;o.textContent=label(sc).slice(0,40);$('#jump').appendChild(o);
    const items=sc.blocks.flatMap(b=>b.items.filter(x=>x.id));const cnt=lg=>items.filter(x=>x.audio[lg]).length;
    const vs=lg=>`<span class="lg${sc.voice_stale.includes(lg)?' stale':''}">${lg==='fa'?'فارسی':'English'}: ${cnt(lg)}/${items.length} ${sc.voice_stale.includes(lg)?'⚠ کهنه':'✓'}</span>${sc.voice_stale.includes(lg)?`<button class="b" data-flag="${lg}">✓ صدای ${lg==='fa'?'فارسی':'انگلیسی'} به‌روز شد</button>`:''}`;
    const warns=sc.warnings.map(w=>w.issues.length?issHtml(w.issues):`<div class="issue">⚠ خط با قالب ناشناخته: <code>${esc(w.text)}</code> <button class="b" data-wreg="${w.ln}">⚑ ثبت برای هوش مصنوعی</button></div>`).join('')+issHtml(sc.issues);
    list.insertAdjacentHTML('beforeend',`<section data-scene="${sc.id}"><h2 class="sc">${labelHtml(sc)}</h2><div class="fxs"><button class="b fxb" data-sfx="1" title="توصیهٔ ادیت برای کل این صحنه (گذار، موسیقی، حال‌وهوا)">🎬 ادیت صحنه${sc.fx?' •':''}</button>${fxBox(sc.id,sc.fx||'','ادیت کل صحنه')}</div>
      ${sc.env.map(e=>`<div class="env">${val(e.text,e.ln,'env')}${flagBtn(e.ln)}${issHtml(e.issues)}</div>`).join('')}${items.length?`<div class="vstrip">🔊 ${vs('fa')} ${vs('en')} ${sceneModel(sc)}</div>`:''}${warns}<div class="bl"></div></section>`);
    const holder=list.lastElementChild.querySelector('.bl');
    sc.blocks.forEach(b=>{const i=BL.length;BL.push(b);const d=document.createElement('section');d.className='blk'+(b.images.length?'':' noimg');d.id='b'+i;d.dataset.bid=b.images.length?b.images[0].id:sc.id+'#'+holder.children.length;
      d.innerHTML=(b.images.length?`<div class="imgs">${b.images.map(figHtml).join('')}</div>`:'')+`<div class="txt">${b.items.map((t,j)=>itemHtml(t,sc,i,j)).join('')}${addBar(b.items.length?b.items[b.items.length-1].ln:b.images[b.images.length-1].ln)}</div>`;
      holder.appendChild(d)})});
  RO.disconnect();$$('.blk').forEach(d=>{const t=d.querySelector('.txt');if(t)RO.observe(t);d.querySelectorAll('img').forEach(i=>i.addEventListener('load',()=>fitBlock(d)));fitBlock(d)});
  $('#prog').max=Math.max(0,BL.length-1);$('#title').textContent=P.name;wire();refsTab();speakersTab();labelList();toneList();stats();filt()}
