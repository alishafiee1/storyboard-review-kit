import { S } from './state.js';
import {
  $,
  $$,
  SMOOTH,
  TT,
  api,
  audio,
  copy,
  esc,
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
import { showTab } from './player.js';
import {
  openComposer,
  openEditor,
  openSayEditor
} from './editors.js';
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
  $('#spk').innerHTML = `<div class="ttsbox">${ t.has_key ? '🔑 کلید API پیدا شد' : '⚠ کلید API پیدا نشد؛ توی پوشه‌ی پروژه فایل <code>.env</code> بساز و یه خط <code>OPENROUTER_API_KEY=...</code> توش بنویس' } · فهرست صداها: ${ upd } <button class="b" data-vrf="1" ${ t.has_key ? '' : 'disabled' }>🔄 رفرش لیست صداها</button> <span id="vmsg"></span><span>· مدل پیش‌فرض: <select data-dm="1">${ modelOpts(dm, false) }</select></span></div>` + `<p class="env">رنگ، صدا و لحن پیش‌فرض هر گوینده توی بالای <code>story.txt</code> نگه داشته می‌شه؛ لحن هر دیالوگ جدا هم قابل تغییره. گوینده‌ی جدید رو توی صفحه با نوشتن اسمش (توی «+ دیالوگ») می‌سازی. صدای هر گوینده از فهرست مدل پیش‌فرض می‌آد؛ عوض کردنش همه‌ی صحنه‌های اون گوینده رو «کهنه» می‌کنه.</p>` + (S.P.speakers || []).map((s, i) => `<div class="spt"><input type="color" value="${ s.color }" data-sc="${ i }"><b>${ esc(s.name) }</b>${ modelById(dm) && modelById(dm).voices.length ? `<select data-sv="${ i }">${ voiceOpts(dm, s.voice) }</select><button class="b" data-smp="${ i }">▶ نمونه</button>` : `<input type="text" list="voicel" value="${ esc(s.voice) }" placeholder="صدا (مثلاً george)" data-sv="${ i }">` }<input type="text" list="tonel" maxlength="40" value="${ esc(s.tone || '') }" placeholder="لحن پیش‌فرض" data-st="${ i }" class="${ toneKnown(s.tone) ? '' : 'unk' }" title="${ toneKnown(s.tone) ? '' : 'این لحن توی voices/voice-config.json نیست' }" style="direction:rtl"><span>${ used[s.name] || 0 } خط</span></div>`).join('') + unknown.map(n => `<div class="issue">⚠ گوینده‌ی «${ esc(n) }» توی فهرست نیست (${ used[n] } خط). <button class="b" data-addspk="${ esc(n) }">افزودن با رنگ و صدای خودکار</button></div>`).join('');
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
    $('#vmsg').textContent = '⏳';
    try {
      const r = await api('/api/voices/refresh', {});
      $('#vmsg').textContent = r.ok ? '✓ ' + r.message : '';
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
    $('#list').insertAdjacentHTML('afterbegin', `<div class="msg tonewarn">⚠ لحن ناشناخته (توی voices/voice-config.json نیست و برچسبی نمی‌فرسته): ${ [...ut].map(([t, n]) => esc(t) + ' (' + n + ')').join('، ') }</div>`);
  if (unknown.length && !$('#list .msg.spkwarn'))
    $('#list').insertAdjacentHTML('afterbegin', `<div class="msg spkwarn">⚠ گوینده‌ای که توی فهرست نیست: ${ unknown.map(esc).join('، ') } — تب «گوینده‌ها» رو ببین.</div>`);
}
export function toneList() {
  $('#tonel').innerHTML = (S.P.tts.tones || []).map(t => `<option value="${ esc(t.fa) }" label="${ esc(t.tag || 'بدون برچسب') }">`).join('');
}
export function labelList() {
  const L = new Set(['گگ']);
  S.P.scenes.forEach(s => s.blocks.forEach(b => b.items.forEach(i => {
    if (i.label)
      L.add(i.label);
  })));
  $('#lbll').innerHTML = [...L].map(l => `<option value="${ esc(l) }">`).join('');
}
export function lightbox(src, name) {
  $('#lb video').pause();
  $('#lb video').classList.add('hide');
  $('#lb img').classList.remove('hide');
  $('#lb img').src = src;
  $('#lb div').textContent = name;
  $('#lb').classList.remove('hide');
}
export function playVideo(src, name) {
  audio.pause();
  const v = $('#lb video');
  $('#lb img').classList.add('hide');
  v.classList.remove('hide');
  v.src = src;
  $('#lb div').textContent = name;
  $('#lb').classList.remove('hide');
  v.play().catch(() => {
  });
}
function closeLb() {
  $('#lb video').pause();
  $('#lb').classList.add('hide');
}
function jumpToImage(id) {
  showTab('tabR');
  const f = document.querySelector(`figure.shot[data-id="${ id }"]`);
  if (!f)
    return;
  if (f.closest('.hide'))
    $('#filter').value = 'all', filt();
  f.scrollIntoView({
    block: 'center',
    behavior: SMOOTH
  });
  f.classList.add('flash');
  setTimeout(() => f.classList.remove('flash'), 2000);
}
export function refsTab() {
  const R = $('#refs');
  const P = S.P, sz = n => n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
  const intake = (P.triage || []).length || (P.inbox || []).length || (P.imports || []).length ? `<div class="intake">${ (P.triage || []).length ? `<h4>⚠ نیاز به مرتب‌سازی (اسم رفرنس نیستن)</h4><ul data-triage="1">${ P.triage.map(t => `<li>${ esc(t.src) }</li>`).join('') }</ul>` : '' }${ (P.inbox || []).length ? `<h4>📥 inbox/ (${ P.inbox.length })</h4><ul data-inbox="1">${ P.inbox.map(f => `<li>${ esc(f.name) } <small>${ esc(f.kind) } · ${ sz(f.size) }</small></li>`).join('') }</ul>` : '' }${ (P.imports || []).length ? `<h4>⬇ آخرین ورودی‌ها</h4><ul data-imports="1">${ P.imports.map(i => `<li>${ esc(i.time) } → ${ esc(i.to) }</li>`).join('') }</ul>` : '' }</div>` : '';
  R.innerHTML = intake + `<div class="grid">${ S.P.refs.map((r, i) => `<div class="card"><img src="${ r.src }" loading="lazy" data-zoom="${ r.src }" data-name="${ esc(r.name) }"><b>${ esc(r.name) }</b> <small>${ esc(r.kind) }</small>${ r.video ? ` <button class="b vid" data-vid="${ esc(r.video) }" data-name="${ esc(r.name) }">▶ ویدیو</button>` : '' }<div>${ r.used.map(u => `<button class="chip ref" data-img="${ u }" title="رفتن به این تصویر">${ u }</button>`).join('') || '—' }</div>
  ${ r.prompt ? `<button class="b" data-r="${ i }">پرامپت</button><div class="pr hide"><button class="b" data-rc="${ i }">📋 کپی</button><textarea readonly style="min-height:140px">${ esc(r.prompt) }</textarea></div>` : '' }</div>`).join('') }</div>`;
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
  $('#info').textContent = `${ imgs.filter(m => m.src).length }/${ imgs.length } تصویر · ✅${ c('ok') } 🔁${ c('redo') } · ⚠${ imgs.filter(m => m.stale).length }${ issues ? ` · ⚑${ issues }` : '' }`;
}
export function filt() {
  const v = $('#filter').value;
  const all = S.BL.flatMap(b => b.images);
  $$('figure.shot').forEach(f => {
    const m = all.find(x => x.id === f.dataset.id);
    const show = v === 'all' || (v === 'missing' ? !m.src : v === 'none' ? !m.status : v === 'note' ? !!m.note : v === 'stale' ? m.stale : m.status === v);
    f.classList.toggle('hide', !show);
  });
  S.BL.forEach((b, i) => $('#b' + i).classList.toggle('hide', v !== 'all' && !(b.images.length && $$('#b' + i + ' figure.shot:not(.hide)').length)));
}
function restoreAnchor(bid, top, y) {
  const go = () => {
    const el = bid && document.querySelector(`.blk[data-bid="${ bid }"]`);
    if (el)
      scrollBy(0, el.getBoundingClientRect().top - top);
    else
      scrollTo(0, y);
  };
  go();
  setTimeout(go, 200);
}
export async function reload() {
  const ae = document.activeElement && document.activeElement.closest ? document.activeElement.closest('.blk') : null, vb = [...document.querySelectorAll('.blk:not(.hide)')].find(b => b.getBoundingClientRect().bottom > 90), an = ae || vb, abid = an && an.dataset.bid, atop = an ? an.getBoundingClientRect().top : 0, y = scrollY, fields = () => $$('textarea[data-key],input[data-key]'), drafts = fields().filter(t => t.value !== t.dataset.orig).map(t => [
      t.dataset.key,
      t.value
    ]);
  const open = $$('[data-key^="panel:"]:not(.hide)').map(e => e.dataset.key);
  S.P = await (await fetch('/api/project')).json();
  render();
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
  restoreAnchor(abid, atop, y);
}
export function boot_panels() {
  $('#lb').onclick = closeLb;
  $('#lb video').onclick = e => e.stopPropagation();
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape')
      closeLb();
  });
}
