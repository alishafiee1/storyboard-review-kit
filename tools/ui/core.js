/* Shared state and helpers: api calls, copy, auto-grow, the open-editor registry, dirty tracking. */
const SMOOTH = matchMedia('(prefers-reduced-motion:reduce)').matches ? 'auto' : 'smooth';
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
let P = null, BL = [], cur = 0, playing = false, token = 0;
const audio = new Audio(), SILENT = 3.2;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;'
}[c]));
function fmt(t) {
  t = esc(t);
  t = t.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>');
  t = t.replace(/〔(واقعیت|فرضیه) \| (.*?)〕/g, (m, a, b) => `<span class="tag ${ a === 'واقعیت' ? 'fact' : 'hyp' }">${ a }<small>${ b }</small></span>`);
  return t.replace(/`(.+?)`/g, '<code>$1</code>');
}
async function api(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok)
    throw new Error(j.error || 'خطا ' + r.status);
  return j;
}
const fail = e => alert(e.message || e);
const TT = () => P.tts || {
    default: '',
    catalog: []
  }, modelById = id => TT().catalog.find(m => m.id === id);
const modelOpts = (sel, withDefault, hint) => (withDefault ? `<option value="">پیش‌فرض (${ esc(TT().default) })</option>` : '') + TT().catalog.map(m => `<option value="${ esc(m.id) }"${ m.id === sel ? ' selected' : '' }>${ esc(m.id) } · $${ esc(m.price) }/k${ m.voices.length ? '' : ' · بدون فهرست صدا' }${ hint ? hint(m) : '' }</option>`).join('') + (sel && !modelById(sel) ? `<option value="${ esc(sel) }" selected>⚠ ${ esc(sel) } (توی فهرست نیست)</option>` : '');
const voiceOpts = (model, sel) => {
  const m = modelById(model), vs = m ? m.voices : [];
  return vs.map(v => `<option value="${ esc(v.name) }"${ v.name === sel ? ' selected' : '' }>${ esc(v.name) } · ${ esc(v.accent) }</option>`).join('') + (sel && !vs.some(v => v.name === sel) ? `<option value="${ esc(sel) }" selected>${ vs.length ? '⚠ ' : '' }${ esc(sel) }${ vs.length ? ' (برای این مدل نیست)' : '' }</option>` : '');
};
const smpAudio = new Audio();
async function sample(model, voice, btn) {
  const t = btn.textContent;
  btn.disabled = true;
  btn.textContent = '…';
  audio.pause();
  try {
    const r = await api('/api/sample', {
      model,
      voice
    });
    smpAudio.src = r.url;
    await smpAudio.play();
  } catch (e) {
    fail(e);
  } finally {
    btn.disabled = false;
    btn.textContent = t;
  }
}
let JOBT = null;
function pollJob() {
  if (JOBT)
    return;
  JOBT = setInterval(async () => {
    try {
      const j = await (await fetch('/api/job')).json();
      document.querySelectorAll('[data-job]').forEach(x => x.textContent = x.dataset.job === j.scene && j.state === 'running' ? `⏳ ${ j.done }/${ j.total } خط ساخته شد…` : '');
      if (j.state !== 'running') {
        clearInterval(JOBT);
        JOBT = null;
        await reload();
        if (typeof redrawDialog === 'function')
          redrawDialog();
        if (j.errors.length)
          alert('بعضی خط‌ها ساخته نشدن:\n' + j.errors.slice(0, 6).join('\n'));
        if (j.warnings && j.warnings.length)
          alert('⚠ هشدار:\n' + j.warnings.slice(0, 6).join('\n'));
      }
    } catch (e) {
    }
  }, 2000);
}
function copy(t, btn) {
  const done = () => {
    const o = btn.textContent;
    btn.textContent = 'کپی شد ✓';
    setTimeout(() => btn.textContent = o, 1500);
  };
  const fb = () => {
    const a = document.createElement('textarea');
    a.value = t;
    document.body.appendChild(a);
    a.select();
    document.execCommand('copy');
    a.remove();
    done();
  };
  navigator.clipboard ? navigator.clipboard.writeText(t).then(done, fb) : fb();
}
const grow = ta => {
  ta.style.height = 'auto';
  ta.style.height = ta.scrollHeight + 4 + 'px';
};
const autoGrow = ta => {
  ta.addEventListener('input', () => grow(ta));
  requestAnimationFrame(() => grow(ta));
};
/* the picture grows to match a tall dialogue column (16:9 kept) */
const RO = new ResizeObserver(es => es.forEach(e => {
  const d = e.target.closest('.blk');
  clearTimeout(d._ft);
  d._ft = setTimeout(() => fitBlock(d), 120);
}));
const FIT_IMAGES = false;
/* true = picture grows to the height of a long dialogue column (looked like some pictures were more important, so it is off) */
function fitBlock(d) {
  if (!FIT_IMAGES) {
    d.style.gridTemplateColumns = '';
    return;
  }
  const imgs = d.querySelector('.imgs'), txt = d.querySelector('.txt'), figs = imgs ? [...imgs.querySelectorAll('figure.shot')] : [];
  if (!figs.length || innerWidth <= 760) {
    d.style.gridTemplateColumns = '';
    return;
  }
  const cs = getComputedStyle(d), W = d.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 22;
  for (let k = 0; k < 3; k++) {
    let ctl = 0;
    figs.forEach(f => {
      const im = f.querySelector('img,.ph');
      ctl += f.offsetHeight - im.offsetHeight;
    });
    const first = figs[0].querySelector('img'), a = first && first.naturalWidth ? first.naturalHeight / first.naturalWidth : 0.5625;
    const target = (txt.offsetHeight - ctl - 14 * (figs.length - 1)) / figs.length / a, dflt = W * 5 / 9;
    const w = Math.round(Math.min(W * 0.72, Math.max(dflt, target)));
    const cur = imgs.offsetWidth;
    if (Math.abs(w - cur) <= 6)
      break;
    d.style.gridTemplateColumns = w > dflt + 6 ? `${ w }px minmax(0,1fr)` : '';
  }
}
const EDITORS = new Set();
let RELOADS = 0;
function onLeave(w, fn) {
  let busy = false;
  const run = async () => {
    if (busy || !w.isConnected)
      return;
    busy = true;
    try {
      await fn();
    } finally {
      busy = false;
    }
  };
  EDITORS.add({
    w,
    run
  });
  w.addEventListener('focusout', () => setTimeout(() => {
    if (w._keep || w.contains(document.activeElement) || !document.hasFocus())
      return;
    run();
  }, 0));
}
/* a click anywhere outside an open editor commits it (saves a change, otherwise just closes). Works even when the browser does not report focus changes. */
document.addEventListener('pointerdown', async e => {
  const t = e.target, inner = t.closest && t.closest('.v'), bar = t.closest && t.closest('.addbar button');
  const pend = inner ? {
    type: 'v',
    scene: inner.closest('section[data-scene]').dataset.scene,
    ln: inner.dataset.ln,
    k: inner.dataset.k
  } : bar ? {
    type: 'a',
    scene: bar.closest('section[data-scene]').dataset.scene,
    after: bar.parentElement.dataset.after,
    kind: bar.dataset.add
  } : null;
  const r0 = RELOADS;
  let ran = false;
  for (const x of [...EDITORS]) {
    if (!x.w.isConnected) {
      EDITORS.delete(x);
      continue;
    }
    if (x.w._keep || x.w.contains(t))
      continue;
    ran = true;
    await x.run();
  }
  document.querySelectorAll('.fxbox:not(.hide) textarea').forEach(x => {
    if (!x.closest('.fxbox').contains(t) && x.value !== x.dataset.orig && x._save)
      x._save();
  });
  document.querySelectorAll('.nbox:not(.hide) textarea.nt').forEach(nt => {
    const nb = nt.closest('.nbox');
    if (nb.contains(t))
      return;
    if (nt.value !== nt.dataset.orig)
      nt.closest('figure.shot').querySelector('[data-sn]').click();
  });
  if (ran && RELOADS !== r0 && pend) {
    const sec = document.querySelector(`section[data-scene="${ pend.scene }"]`);
    if (!sec)
      return;
    if (pend.type === 'v') {
      const v = [...sec.querySelectorAll('.v')].find(x => x.dataset.ln === pend.ln && x.dataset.k === pend.k);
      if (v)
        openFromV(v);
    } else {
      const bt = sec.querySelector(`.addbar[data-after="${ pend.after }"] button[data-add="${ pend.kind }"]`);
      if (bt)
        bt.click();
    }
  }
}, true);
/* dirty tracking: every editable textarea has data-key + data-orig; its save button is green while they differ */
function track(ta, btn) {
  const f = () => {
    const d = ta.value !== ta.dataset.orig;
    btn.classList.toggle('dirty', d);
    ta.classList.toggle('dirty', d);
  };
  ta.addEventListener('input', f);
  f();
}
const anyDirty = () => $$('textarea[data-key],input[data-key]').some(t => t.value !== t.dataset.orig);
window.addEventListener('beforeunload', e => {
  if (anyDirty()) {
    e.preventDefault();
    e.returnValue = '';
  }
});
