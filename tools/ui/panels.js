import { S } from './state.js';
import {
  $,
  $$,
  TT,
  api,
  audio,
  copy,
  esc,
  fa,
  fail,
  modelById,
  modelOpts,
  sample,
  voiceOpts
} from './core.js';
import {
  render,
  toneKnown,
  unknownTones
} from './render.js';
import {
  blockByBid,
  chrome,
  show,
  showNear
} from './player.js';
import {
  closeDrawer,
  openDrawer
} from './drawer.js';
import {
  openComposer,
  openEditor,
  openSayEditor
} from './editors.js';
import { redrawPrompt } from './prompts.js';
/* Speakers tab, tone/label lists, references tab, lightbox, filter, stats and reload(). */
export function speakersTab() {
  const used = {};
  S.P.scenes.forEach(s => s.blocks.forEach(b => b.items.forEach(i => {
    if (i.k === 'say')
      used[i.sp] = (used[i.sp] || 0) + 1;
  })));
  const known = new Set((S.P.speakers || []).map(s => s.name)), unknown = Object.keys(used).filter(n => !known.has(n));
  $('#spkl').innerHTML = (S.P.speakers || []).map(s => `<option value="${ esc(s.name) }">`).join('');
  $('#voicel').innerHTML = (S.P.voices || []).map(v => `<option value="${ v }">`).join('');
  const t = TT(), upd = t.updated ? new Date(t.updated * 1000).toLocaleDateString('fa-IR') : 'هنوز ساخته نشده', dm = t.default;
  const tones = S.P.tts.tones || [], dmod = modelById(dm), haveVoices = !!(dmod && dmod.voices.length), ut0 = unknownTones();
  const toneVoice = ((S.P.speakers || []).find(sp => haveVoices && dmod.voices.some(v => v.name === sp.voice)) || {}).voice || (haveVoices ? dmod.voices[0].name : '');
  const mark = tn => (tn.tests || {})[dm] || '';
  const speakerCard = (s, i) => `<div class="spcard">
      <div class="srow"><input type="color" value="${ s.color }" data-sc="${ i }" aria-label="رنگ"><span class="st"><b>${ esc(s.name) }</b><small class="muted">${ used[s.name] || 0 } خط</small></span></div>
      <div class="srow">${ haveVoices ? `<select data-sv="${ i }" aria-label="صدا">${ voiceOpts(dm, s.voice) }</select><button type="button" class="outline" data-smp="${ i }">نمونه</button>` : `<input type="text" list="voicel" value="${ esc(s.voice) }" placeholder="صدا (مثلاً george)" data-sv="${ i }" aria-label="صدا">` }</div>
      <div class="srow"><input type="text" list="tonel" maxlength="40" value="${ esc(s.tone || '') }" placeholder="لحن پیش‌فرض" aria-label="لحن پیش‌فرض" data-st="${ i }" class="${ toneKnown(s.tone) ? '' : 'unk' }" style="direction:rtl"></div>
      ${ toneKnown(s.tone) ? '' : `<div class="vwarn">لحن «${ esc(s.tone) }» تعریف نشده و برچسبی نمی‌فرسته. <button type="button" class="quiet" data-addtone="${ esc(s.tone) }">افزودن به لحن‌ها</button></div>` }
    </div>`;
  const toneRow = tn => {
    const m = mark(tn), st = m === 'good' ? '<span class="tag ok">کار می‌کنه</span>' : m === 'bad' ? '<span class="tag bad">کار نمی‌کنه</span>' : '<span class="tag">تست نشده</span>';
    return `<div class="tnrow"><div class="srow"><span class="st"><b>${ esc(tn.fa) }</b>${ tn.tag ? `<bdi class="tg" dir="ltr">${ esc(tn.tag) }</bdi>` : '<small class="muted">بدون برچسب (چیزی نمی‌فرسته)</small>' }</span>${ tn.tag ? st : '' }</div>
      <div class="srow act">${ tn.tag && haveVoices && toneVoice ? `<button type="button" class="outline" data-tsmp="${ esc(tn.id) }">نمونه</button><button type="button" class="quiet" data-tmark="${ esc(tn.id) }:good">کار می‌کنه</button><button type="button" class="quiet" data-tmark="${ esc(tn.id) }:bad">کار نمی‌کنه</button>` : '' }<button type="button" class="quiet" data-tdel="${ esc(tn.id) }">حذف</button></div></div>`;
  };
  $('#spk').innerHTML = `<section class="vsec"><h4>مدل پیش‌فرض</h4>
      <div class="srow"><select data-dm="1" aria-label="مدل پیش‌فرض">${ modelOpts(dm, false) }</select></div>
      <div class="srow"><span class="st"><small class="muted">فهرست صداها: ${ upd }</small></span><button type="button" class="outline" data-vrf="1" ${ t.has_key ? '' : 'disabled' }>رفرش لیست صداها</button></div>
      <small class="muted" id="vmsg" role="status"></small>
      ${ t.has_key ? '' : '<div class="vwarn">کلید API تنظیم نشده. <button type="button" class="quiet" data-gosettings="1">رفتن به تنظیمات</button></div>' }
      <p class="muted vhint">صدای هر گوینده از فهرست این مدل میاد؛ عوض‌کردنش صدای اون گوینده رو «کهنه» می‌کنه.</p>
    </section>
    <section class="vsec"><h4>گوینده‌ها</h4>
      ${ (S.P.speakers || []).map(speakerCard).join('') }
      ${ unknown.map(n => `<div class="vwarn">گوینده‌ی «${ esc(n) }» توی فهرست نیست (${ used[n] } خط). <button type="button" class="quiet" data-addspk="${ esc(n) }">افزودن با رنگ و صدای خودکار</button></div>`).join('') }
    </section>
    <section class="vsec"><h4>لحن‌ها</h4>
      <p class="muted vhint">لحن یه برچسب انگلیسی به مدل می‌فرسته (مثل <bdi dir="ltr">[whispers]</bdi>) و فقط بعضی مدل‌ها اون رو می‌فهمن. برای هر لحن یه نمونه بساز، گوش بده و علامت بزن که توی مدل <bdi dir="ltr">${ esc(dm) }</bdi> کار می‌کنه یا نه.</p>
      ${ tones.map(toneRow).join('') || '<p class="muted">هنوز لحنی نیست.</p>' }
      <div class="tnadd"><b>افزودن لحن</b>
        <input id="tnfa" type="text" maxlength="30" placeholder="اسم فارسی، مثلاً غمگین" aria-label="اسم لحن" style="direction:rtl">
        <input id="tntag" type="text" dir="ltr" maxlength="32" placeholder="[sad]  (خالی = بدون برچسب)" aria-label="برچسب انگلیسی" spellcheck="false">
        <div class="srow"><button type="button" class="outline" data-tadd="1">افزودن لحن</button></div>
      </div>
      ${ ut0.size ? `<p class="muted vhint">لحن‌های بدون تعریف توی متن: ${ [...ut0.keys()].map(esc).join('، ') }</p>` : '' }
    </section>`;
  $$('#spk [data-gosettings]').forEach(b => b.onclick = () => openDrawer('settings'));
  $$('#spk [data-addtone]').forEach(b => b.onclick = () => {
    $('#tnfa').value = b.dataset.addtone;
    $('#tnfa').scrollIntoView({ block: 'center' });
    $('#tntag').focus();
  });
  $$('#spk [data-tadd]').forEach(b => b.onclick = async () => {
    try {
      await api('/api/tone', {
        op: 'add',
        fa: $('#tnfa').value.trim(),
        tag: $('#tntag').value.trim()
      });
      await reload();
    } catch (e) {
      fail(e);
    }
  });
  $$('#spk [data-tdel]').forEach(b => b.onclick = async () => {
    if (!confirm('این لحن از فهرست حذف بشه؟ توی متن‌ها دست نمی‌خوره، فقط برچسبش دیگه فرستاده نمی‌شه.'))
      return;
    try {
      await api('/api/tone', {
        op: 'remove',
        id: b.dataset.tdel
      });
      await reload();
    } catch (e) {
      fail(e);
    }
  });
  $$('#spk [data-tmark]').forEach(b => b.onclick = async () => {
    const [id, result] = b.dataset.tmark.split(':');
    const cur = (tones.find(x => x.id === id) || {}).tests || {};
    try {
      await api('/api/voicetest', {
        model: dm,
        tone: id,
        result: cur[dm] === result ? '' : result
      });
      await reload();
    } catch (e) {
      fail(e);
    }
  });
  $$('#spk [data-tsmp]').forEach(b => b.onclick = async () => {
    const txt = b.textContent;
    b.disabled = true;
    b.textContent = '…';
    try {
      const r = await api('/api/tonesample', {
        model: dm,
        voice: toneVoice,
        tone: b.dataset.tsmp
      });
      await new Audio(r.url).play();
    } catch (e) {
      fail(e);
    } finally {
      b.disabled = false;
      b.textContent = txt;
    }
  });
  $$('#spk [data-sc]').forEach(c => c.onchange = async () => {
    const s = S.P.speakers[+c.dataset.sc];
    try {
      await api('/api/speaker', {
        name: s.name,
        color: c.value
      });
      await reload();
    } catch (e) {
      fail(e);
    }
  });
  $$('#spk [data-sv]').forEach(c => c.onchange = async () => {
    const s = S.P.speakers[+c.dataset.sv];
    try {
      await api('/api/speaker', {
        name: s.name,
        voice: c.value.trim()
      });
      await reload();
    } catch (e) {
      fail(e);
    }
  });
  $$('#spk [data-smp]').forEach(b => b.onclick = () => {
    const s = S.P.speakers[+b.dataset.smp], sel = $(`#spk [data-sv="${ b.dataset.smp }"]`);
    sample(dm, sel ? sel.value : s.voice, b);
  });
  $$('#spk [data-dm]').forEach(c => c.onchange = async () => {
    try {
      await api('/api/ttsmodel', { model: c.value });
      await reload();
    } catch (e) {
      fail(e);
      await reload();
    }
  });
  $$('#spk [data-vrf]').forEach(b => b.onclick = async () => {
    b.disabled = true;
    $('#vmsg').textContent = '…';
    try {
      const r = await api('/api/voices/refresh', {});
      $('#vmsg').textContent = r.ok ? r.message : '';
      if (!r.ok)
        alert(r.message);
      else
        await reload();
    } catch (e) {
      fail(e);
      b.disabled = false;
      $('#vmsg').textContent = '';
    }
  });
  $$('#spk [data-st]').forEach(c => c.onchange = async () => {
    const s = S.P.speakers[+c.dataset.st];
    try {
      await api('/api/speaker', {
        name: s.name,
        tone: c.value.trim()
      });
      await reload();
    } catch (e) {
      fail(e);
    }
  });
  $$('#spk [data-addspk]').forEach(b => b.onclick = async () => {
    try {
      await api('/api/speaker', { name: b.dataset.addspk });
      await reload();
    } catch (e) {
      fail(e);
    }
  });
  const ut = unknownTones();
  $$('#list .msg.tonewarn').forEach(x => x.remove());
  if (ut.size)
    $('#list').insertAdjacentHTML('afterbegin', `<div class="msg tonewarn">لحن ناشناخته (توی voices/voice-config.json نیست و برچسبی نمی‌فرسته): ${ [...ut].map(([t, n]) => esc(t) + ' (' + n + ')').join('، ') }</div>`);
  if (unknown.length && !$('#list .msg.spkwarn'))
    $('#list').insertAdjacentHTML('afterbegin', `<div class="msg spkwarn">گوینده‌ای که توی فهرست نیست: ${ unknown.map(esc).join('، ') } — منو ← «صداها و گوینده‌ها» رو ببین.</div>`);
}
export function toneList() {
  $('#tonel').innerHTML = (S.P.tts.tones || []).map(t => `<option value="${ esc(t.fa) }">`).join('');
}
export function labelList() {
  const L = new Set(['گگ']);
  S.P.scenes.forEach(s => s.blocks.forEach(b => b.items.forEach(i => {
    if (i.label)
      L.add(i.label);
  })));
  $('#lbll').innerHTML = [...L].map(l => `<option value="${ esc(l) }">`).join('');
}
/* the big picture / video sits in the browser's top layer, so it also shows above an open dialog (the prompt card) */
function openLb() {
  const lb = $('#lb');
  lb.classList.remove('hide');
  if (lb.showPopover && !lb.matches(':popover-open'))
    lb.showPopover();
}
export function lightbox(src, name) {
  $('#lb video').pause();
  $('#lb video').classList.add('hide');
  $('#lb img').classList.remove('hide');
  $('#lb img').src = src;
  $('#lb div').textContent = name;
  openLb();
}
export function playVideo(src, name) {
  audio.pause();
  const v = $('#lb video');
  $('#lb img').classList.add('hide');
  v.classList.remove('hide');
  v.src = src;
  $('#lb div').textContent = name;
  openLb();
  v.play().catch(() => {
  });
}
function closeLb() {
  $('#lb video').pause();
  $('#lb').classList.add('hide');
  if ($('#lb').matches(':popover-open'))
    $('#lb').hidePopover();
}
function jumpToImage(id) {
  closeDrawer();
  if (S.filter !== 'all' || S.q) {
    S.filter = 'all';
    S.q = '';
    filt(true);
  }
  const i = S.BL.findIndex(b => b.images.some(m => m.id === id));
  if (i >= 0)
    show(i);
}
export function refsTab() {
  const R = $('#refs');
  R.innerHTML = `<div class="grid">${ S.P.refs.map((r, i) => `<div class="card"><img src="${ r.src }" loading="lazy" data-zoom="${ r.src }" data-name="${ esc(r.name) }"><b>${ esc(r.name) }</b> <small>${ esc(r.kind) }</small>${ r.video ? ` <button class="b vid" data-vid="${ esc(r.video) }" data-name="${ esc(r.name) }">ویدیو</button>` : '' }<div>${ r.used.map(u => `<button class="chip ref" data-img="${ u }" title="رفتن به این تصویر">${ u }</button>`).join('') || '—' }</div>
  ${ r.prompt ? `<button class="b" data-r="${ i }">پرامپت</button><div class="pr hide"><button class="b" data-rc="${ i }">کپی</button><textarea readonly style="min-height:140px">${ esc(r.prompt) }</textarea></div>` : '' }</div>`).join('') }</div>`;
  R.querySelectorAll('[data-r]').forEach(b => b.onclick = () => b.nextElementSibling.classList.toggle('hide'));
  R.querySelectorAll('[data-rc]').forEach(b => b.onclick = () => copy(b.nextElementSibling.querySelector('textarea').value, b));
  R.querySelectorAll('[data-zoom]').forEach(i => i.onclick = () => lightbox(i.dataset.zoom, i.dataset.name));
  R.querySelectorAll('[data-img]').forEach(b => b.onclick = () => jumpToImage(b.dataset.img));
  R.querySelectorAll('[data-vid]').forEach(b => b.onclick = () => playVideo(b.dataset.vid, b.dataset.name));
}
export function stats() {
  const imgs = S.BL.flatMap(b => b.images);
  const c = k => imgs.filter(m => m.status === k).length;
  const issues = S.P.scenes.reduce((n, s) => n + s.issues.length + s.warnings.length + s.env.reduce((a, e) => a + e.issues.length, 0) + s.blocks.reduce((a, b) => a + b.images.reduce((x, m) => x + m.issues.length, 0) + b.items.reduce((x, t) => x + t.issues.length, 0), 0), 0);
  $('#info').textContent = `${ fa(imgs.filter(m => m.src).length) } از ${ fa(imgs.length) } تصویر ساخته شده · ${ fa(c('ok')) } تأیید · ${ fa(c('redo')) } بازسازی · ${ fa(imgs.filter(m => m.stale).length) } کهنه${ issues ? ` · ${ fa(issues) } مشکل فرمت` : '' }`;
}
/* the filter and the search box decide which blocks can be reached; the block on show is kept until you move on, so choosing a version
   under a filter does not make the picture vanish under your hands (`force` = the filter itself just changed) */
let FILTERING = false;
const matches = (b, m, q) => !q || [
  m ? m.id : '',
  m ? m.note : '',
  ...b.items.flatMap(t => [
    t.sp,
    t.fa,
    t.en
  ])
].some(x => String(x || '').toLowerCase().includes(q));
export function filt(force) {
  if (FILTERING)
    return;
  FILTERING = true;
  const v = S.filter, q = S.q.toLowerCase();
  const all = S.BL.flatMap(b => b.images);
  $$('figure.shot').forEach(f => {
    const m = all.find(x => x.id === f.dataset.id);
    const show = v === 'all' || (v === 'missing' ? !m.src : v === 'none' ? !m.status : v === 'note' ? !!m.note : v === 'stale' ? m.stale : m.status === v);
    f.classList.toggle('hide', !show);
  });
  S.BL.forEach((b, i) => {
    const hide = (v !== 'all' && !(b.images.length && $$('#b' + i + ' figure.shot:not(.hide)').length)) || !b.images.some(m => matches(b, m, q)) && !(!b.images.length && matches(b, null, q));
    $('#b' + i).classList.toggle('hide', hide && (force || i !== S.cur));
  });
  FILTERING = false;
  if (force && $('#b' + S.cur) && $('#b' + S.cur).classList.contains('hide'))
    showNear(S.cur);
  else if (S.BL.length)
    chrome();
}
export async function reload() {
  const here = $('#b' + S.cur), abid = here && here.dataset.bid, was = S.cur, actJ = here ? [...here.querySelectorAll('.it')].findIndex(x => x.classList.contains('cur')) : -1, fields = () => $$('textarea[data-key],input[data-key]'), drafts = fields().filter(t => t.value !== t.dataset.orig).map(t => [
      t.dataset.key,
      t.value
    ]);
  const open = $$('[data-key^="panel:"]:not(.hide)').map(e => e.dataset.key);
  S.P = await (await fetch('/api/project')).json();
  render();
  const at = blockByBid(abid);
  if (at >= 0 && !$('#b' + at).classList.contains('hide'))
    show(at, actJ >= 0 ? actJ : undefined);
  else
    showNear(at >= 0 ? at : Math.min(was, S.BL.length - 1));
  S.RELOADS++;
  open.forEach(k => {
    const e = document.querySelector(`[data-key="${ k }"]`);
    if (e)
      e.classList.remove('hide');
  });
  drafts.forEach(([k, v]) => {
    let t = document.querySelector(`[data-key="${ k }"]`);
    if (!t && k.startsWith('line:')) {
      const [, scene, ln, key, op] = k.split(':');
      const sec = document.querySelector(`section[data-scene="${ scene }"]`);
      const host = op === 'add_en' ? sec && [...sec.querySelectorAll(`[data-aden="${ ln }"]`)].map(b => b.parentElement)[0] : sec && [...sec.querySelectorAll('.v')].find(x => x.dataset.ln === ln && x.dataset.k === key);
      if (host)
        t = openEditor(host, {
          scene,
          ln: +ln,
          key,
          old: op === 'add_en' ? '' : host.dataset.old,
          op
        });
    }
    if (!t && /^say[ntx]+:/.test(k)) {
      const [, scene, ln] = k.split(':');
      const host = [...document.querySelectorAll(`section[data-scene="${ scene }"] .v`)].find(x => x.dataset.ln === ln && x.dataset.k === 'speaker');
      if (host) {
        openSayEditor(host.closest('.it'), {
          scene,
          ln: +ln
        });
        t = document.querySelector(`[data-key="${ k }"]`);
      }
    }
    if (!t && (k.startsWith('add:') || k.startsWith('addname:') || k.startsWith('addlabel:') || k.startsWith('addtone:'))) {
      const [, scene, after, kind] = k.split(':');
      const sc3 = document.querySelector(`section[data-scene="${ scene }"]`), bar = sc3 && (sc3.querySelector(`.addbar[data-after="${ after }"]`) || [...sc3.querySelectorAll('.v')].filter(x => x.dataset.ln === after).map(x => x.closest('.it'))[0]);
      if (bar) {
        const c = openComposer(bar, {
          scene,
          after: +after,
          kind
        });
        t = k.startsWith('add:') ? c && c.ta : k.startsWith('addname:') ? c && c.nm : k.startsWith('addtone:') ? c && c.tn : c && c.lb;
      }
    }
    if (t) {
      const hb = t.closest('.nbox,.pr');
      if (hb)
        hb.classList.remove('hide');
      t.value = v;
      t.dispatchEvent(new Event('input'));
    }
  });
  redrawPrompt();
}
export function boot_panels() {
  $('#lb').onclick = closeLb;
  $('#lb video').onclick = e => e.stopPropagation();
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !$('#lb').classList.contains('hide')) {
      closeLb();
      e.preventDefault();
    }
  });
}
