import { S } from './state.js';
import { reload } from './panels.js';
import { redrawDialog } from './dialogs.js';
import { openFromV } from './editors.js';
/* Shared state and helpers: api calls, copy, auto-grow, the open-editor registry, dirty tracking. */
export const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
export const audio = new Audio(), SILENT = 3.2;
export const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;'
}[c]));
export function fmt(t) {
  t = esc(t);
  t = t.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>');
  t = t.replace(/〔(واقعیت|فرضیه) \| (.*?)〕/g, (m, a, b) => `<span class="tag ${ a === 'واقعیت' ? 'fact' : 'hyp' }">${ a }<small>${ b }</small></span>`);
  return t.replace(/`(.+?)`/g, '<code>$1</code>');
}
export async function api(path, body) {
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
function runAsk(html, onOpen, valFn) {
  return new Promise(res => {
    const dlg = document.createElement('dialog');
    dlg.className = 'dlg ask';
    dlg.innerHTML = html;
    document.body.appendChild(dlg);
    let out = valFn ? null : false;
    dlg.addEventListener('close', () => {
      dlg.remove();
      res(out);
    });
    dlg.addEventListener('click', e => {
      if (e.target === dlg)
        dlg.close();
      const b = e.target.closest('[data-ask]');
      if (b) {
        if (b.dataset.ask === 'ok')
          out = valFn ? valFn(dlg) : true;
        dlg.close();
      }
      const ch = e.target.closest('[data-askchip]');
      if (ch) {
        const inp = dlg.querySelector('input');
        if (inp) {
          inp.value = ch.dataset.askchip;
          inp.focus();
        }
      }
    });
    dlg.addEventListener('keydown', e => {
      if (e.key === 'Enter' && e.target.tagName === 'INPUT' && !e.isComposing) {
        e.preventDefault();
        dlg.querySelector('[data-ask=ok]').click();
      }
    });
    dlg.showModal();
    if (onOpen)
      onOpen(dlg);
  });
}
export const askAlert = (msg, title = 'توجه') => runAsk(`<h3>${ esc(title) }</h3><p class="askmsg">${ esc(msg) }</p><div class="dbar"><span class="sp"></span><button type="button" class="b pri" data-ask="ok">باشه</button></div>`, d => d.querySelector('[data-ask=ok]').focus());
export const askConfirm = (msg, okLabel = 'تأیید') => runAsk(`<p class="askmsg">${ esc(msg) }</p><div class="dbar"><span class="sp"></span><button type="button" class="quiet" data-ask="cancel">انصراف</button><button type="button" class="b pri" data-ask="ok">${ esc(okLabel) }</button></div>`, d => d.querySelector('[data-ask=ok]').focus());
export const askPrompt = (msg, def = '', {placeholder = '', chips = []} = {}) => runAsk(`<p class="askmsg">${ esc(msg) }</p><input type="text" value="${ esc(def) }" placeholder="${ esc(placeholder) }" autocomplete="off">${ chips.length ? `<div class="askchips">${ chips.map(c => `<button type="button" class="chip" data-askchip="${ esc(c) }">${ esc(c) }</button>`).join('') }</div>` : '' }<div class="dbar"><span class="sp"></span><button type="button" class="quiet" data-ask="cancel">انصراف</button><button type="button" class="b pri" data-ask="ok">ثبت</button></div>`, d => {
  const i = d.querySelector('input');
  i.focus();
  i.select();
}, d => d.querySelector('input').value);
export const askNewScene = () => runAsk(`<h3>صحنهٔ جدید</h3><div class="askrow"><label class="fld">عنوان صحنه<input type="text" data-ns="title" value="صحنهٔ جدید" maxlength="60" autocomplete="off"></label><label class="fld">تعداد تصویر<input type="number" data-ns="n" min="0" max="12" value="1"></label></div><div class="dbar"><span class="sp"></span><button type="button" class="quiet" data-ask="cancel">انصراف</button><button type="button" class="b pri" data-ask="ok">ساخت صحنه</button></div>`, d => {
  const i = d.querySelector('[data-ns=title]');
  i.focus();
  i.select();
}, d => ({
  title: d.querySelector('[data-ns=title]').value,
  images: Math.max(0, Math.min(12, +d.querySelector('[data-ns=n]').value || 0))
}));
export const fail = e => askAlert(e.message || e, 'خطا');
/* Persian digits for numbers shown in the chrome (۴۵ / ۵۰) */
export const fa = n => String(n).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
/* a one-line note at the bottom of the page that goes away by itself */
let TOAST_T = 0;
export function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(TOAST_T);
  TOAST_T = setTimeout(() => t.hidden = true, 2600);
}
/* How a line is addressed to the server: by its picture (index counted from the picture's own [IMG] line, so it survives moving the
   picture), or by the scene for lines above the first picture. `key` is the name of the number ('index', or 'after' when adding). */
export function lineRef(scene, ln, key = 'index') {
  const sc = S.P.scenes.find(s => s.id === scene);
  for (const b of sc ? sc.blocks : []) {
    const im = b.images[0];
    if (im && ln >= im.ln && ln < im.end)
      return {
        image: im.id,
        [key]: ln - im.ln
      };
  }
  return {
    scene,
    [key]: ln
  };
}
export const TT = () => S.P.tts || {
    default: '',
    catalog: []
  }, modelById = id => TT().catalog.find(m => m.id === id);
export const modelOpts = (sel, withDefault, hint) => (withDefault ? `<option value="">پیش‌فرض (${ esc(TT().default) })</option>` : '') + TT().catalog.map(m => `<option value="${ esc(m.id) }"${ m.id === sel ? ' selected' : '' }>${ esc(m.id) } · $${ esc(m.price) }/k${ m.voices.length ? '' : ' · بدون فهرست صدا' }${ hint ? hint(m) : '' }</option>`).join('') + (sel && !modelById(sel) ? `<option value="${ esc(sel) }" selected>${ esc(sel) } (توی فهرست نیست)</option>` : '');
export const voiceOpts = (model, sel) => {
  const m = modelById(model), vs = m ? m.voices : [];
  return vs.map(v => `<option value="${ esc(v.name) }"${ v.name === sel ? ' selected' : '' }>${ esc(v.name) }${ v.accent && v.accent !== '؟' ? ' · ' + esc(v.accent) : '' }</option>`).join('') + (sel && !vs.some(v => v.name === sel) ? `<option value="${ esc(sel) }" selected>${ vs.length ? '' : '' }${ esc(sel) }${ vs.length ? ' (توی این مدل نیست)' : '' }</option>` : '');
};
const smpAudio = new Audio();
export async function sample(model, voice, btn) {
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
export function pollJob() {
  if (JOBT)
    return;
  const jp = $('#jobPill');
  const syncPill = j => {
    if (!jp)
      return;
    const on = j.state === 'running';
    jp.hidden = !on;
    if (on)
      jp.textContent = j.total ? `صدا: ${ fa(j.done) }/${ fa(j.total) }…` : 'در حال ساخت صدا…';
  };
  JOBT = setInterval(async () => {
    try {
      const j = await (await fetch('/api/job')).json();
      syncPill(j);
      document.querySelectorAll('[data-job]').forEach(x => x.textContent = x.dataset.job === j.scene && j.state === 'running' ? `${ fa(j.done) }/${ fa(j.total) } خط ساخته شد…` : '');
      if (j.state !== 'running') {
        clearInterval(JOBT);
        JOBT = null;
        await reload();
        if (typeof redrawDialog === 'function')
          redrawDialog();
        if (j.errors.length)
          askAlert(j.errors.slice(0, 6).join('\n'), 'بعضی خط‌ها ساخته نشدن');
        if (j.warnings && j.warnings.length)
          askAlert(j.warnings.slice(0, 6).join('\n'), 'هشدار');
      }
    } catch (e) {
    }
  }, 2000);
}
/* copy text to the clipboard (a plain textarea when the browser does not allow the clipboard API); resolves when done */
export function copyText(t) {
  const fb = () => {
    const a = document.createElement('textarea');
    a.value = t;
    document.body.appendChild(a);
    a.select();
    document.execCommand('copy');
    a.remove();
  };
  return navigator.clipboard ? navigator.clipboard.writeText(t).catch(fb) : Promise.resolve(fb());
}
export function copy(t, btn) {
  copyText(t).then(() => {
    const o = btn.innerHTML;
    btn.textContent = 'کپی شد';
    setTimeout(() => btn.innerHTML = o, 1500);
  });
}
export const grow = ta => {
  ta.style.height = 'auto';
  ta.style.height = ta.scrollHeight + 4 + 'px';
};
export const autoGrow = ta => {
  ta.addEventListener('input', () => grow(ta));
  requestAnimationFrame(() => grow(ta));
};
const EDITORS = new Set();
export function onLeave(w, fn) {
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
/* dirty tracking: every editable textarea has data-key + data-orig; its save button is green while they differ */
export function track(ta, btn) {
  const f = () => {
    const d = ta.value !== ta.dataset.orig;
    btn.classList.toggle('dirty', d);
    ta.classList.toggle('dirty', d);
  };
  ta.addEventListener('input', f);
  f();
}
const anyDirty = () => $$('textarea[data-key],input[data-key]').some(t => t.value !== t.dataset.orig);
export function boot_core() {
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
    const r0 = S.RELOADS;
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
    /* the note / edit-advice popover: a click outside saves what changed and closes it */
    document.querySelectorAll('.nbox:not(.hide)').forEach(nb => {
      if (nb.contains(t) || t.closest && t.closest('#bNote'))
        return;
      nb.querySelectorAll('textarea').forEach(x => {
        if (x.value !== x.dataset.orig && x._save)
          x._save();
      });
      nb.classList.add('hide');
      $('#bNote').classList.remove('open');
    });
    if (ran && S.RELOADS !== r0 && pend) {
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
  window.addEventListener('beforeunload', e => {
    if (anyDirty()) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}
