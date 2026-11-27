import {
  $$,
  api,
  askAlert,
  askConfirm,
  askPrompt,
  autoGrow,
  esc,
  fail,
  grow,
  lineRef,
  onLeave,
  pollJob,
  track
} from './core.js';
import {
  SPK,
  wireFx
} from './render.js';
import {
  filt,
  playVideo,
  reload,
  stats
} from './panels.js';
import { S } from './state.js';
import { openSceneDialog } from './dialogs.js';
/* Inline editing of dialogue, notes, edit advice and prompts, and wiring every button. */
/* ---------- inline editing: only the text after "key:" can be changed; the file format itself is never touched */
export function openEditor(host, {scene, ln, key, old, op}) {
  op = op || (key === 'speaker' ? 'speaker' : key === 'label' ? 'label' : key === 'tone' ? 'tone' : 'edit');
  const k = `line:${ scene }:${ ln }:${ key }:${ op }`;
  if (document.querySelector(`[data-key="${ k }"]`))
    return;
  const w = document.createElement('div');
  w.className = 'ie';
  const field = op === 'speaker' || op === 'label' || op === 'tone' ? `<input data-key="${ k }" data-orig="${ esc(old) }" ${ op === 'speaker' ? 'list="spkl"' : op === 'tone' ? 'list="tonel" maxlength="40" placeholder="لحن این خط (خالی = لحن پیش‌فرض گوینده)"' : 'list="lbll" maxlength="15" placeholder="خالی = بدون برچسب"' } autocomplete="off">` : `<textarea rows="2" data-key="${ k }" data-orig="${ esc(old) }"></textarea>`;
  w.innerHTML = `${ field }<div class="bar"><button class="b pri sv" hidden title="ذخیره (Enter) · خط بعد: Shift+Enter">ذخیره</button><button class="b cx" hidden title="انصراف (Esc)">انصراف</button></div>`;
  const ta = w.querySelector('textarea,input'), sv = w.querySelector('.sv'), cx = w.querySelector('.cx');
  ta.value = op === 'tone' && !old ? host.dataset.def || '' : old;
  const init = ta.value;
  host.style.display = 'none';
  host.after(w);
  track(ta, sv);
  if (ta.tagName === 'TEXTAREA')
    autoGrow(ta);
  ta.focus();
  if (op === 'speaker')
    tabComplete(ta);
  cx.onclick = () => {
    w.remove();
    host.style.display = '';
  };
  sv.onclick = async () => {
    w._keep = true;
    try {
      if (op === 'speaker' && ta.value.trim() !== old && !SPK()[ta.value.trim()] && !(await askConfirm(`گویندهٔ جدید «${ ta.value.trim() }» ساخته بشه؟ رنگ و صدای خودش رو می‌گیره.`, 'بساز')))
        return;
      if (op === 'edit' && !ta.value.trim()) {
        if (key === 'env')
          return askAlert('محیط حذف‌شدنی نیست؛ متن جدید بنویس.');
        ta.dataset.orig = ta.value;
        if (await askDelete(scene, ln, key, old, host.dataset.hasen === '1'))
          return;
        ta.dataset.orig = old;
        return;
      }
      await api('/api/line', {
        ...lineRef(scene, ln),
        old,
        new: ta.value,
        op
      });
      ta.dataset.orig = ta.value;
      await reload();
    } catch (e) {
      fail(e);
    } finally {
      w._keep = false;
    }
  };
  ta.onkeydown = e => {
    if (e.key === 'Escape')
      cx.click();
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sv.click();
    }
  };
  onLeave(w, async () => {
    if (ta.value === init || !ta.value.trim())
      cx.click();
    else
      await sv.onclick();
  });
  return ta;
}
const DK = {
  act: 'توضیح تصویر',
  say: 'دیالوگ',
  en: 'ترجمهٔ انگلیسی'
};
async function askDelete(scene, ln, kind, old, hasEn) {
  const msg = `این ${ DK[kind] } حذف بشه؟\n«${ old.length > 60 ? old.slice(0, 60) + '…' : old }»` + (kind === 'say' && hasEn ? '\nترجمهٔ انگلیسی‌اش هم حذف می‌شه.' : '') + (kind === 'say' ? '\n(صدای این خط کهنه علامت می‌خوره)' : '');
  if (!(await askConfirm(msg, 'حذف')))
    return false;
  try {
    await api('/api/delete', {
      ...lineRef(scene, ln),
      old
    });
    await reload();
    return true;
  } catch (e) {
    fail(e);
    return false;
  }
}
export function openSayEditor(box, {scene, ln, focus}) {
  const pick = a => {
    const f = focus === 'nm' ? a.nm : focus === 'tn' ? a.tn : a.tx;
    f.focus();
    if (f !== a.tx)
      f.select();
  };
  if (box.querySelector('.ie.say')) {
    const a = box.querySelector('.ie.say').api;
    pick(a);
    return a;
  }
  const nmEl = box.querySelector('.nm'), tnEl = box.querySelector('.tn'), txEl = box.querySelector('.fa .v');
  if (!txEl) {
    askAlert('برای ویرایش دیالوگ، زبان «فا» باید روشن باشد (دکمهٔ فا/EN بالای صفحه).');
    return;
  }
  const O = {
      name: nmEl.dataset.old,
      tone: tnEl.dataset.old,
      text: txEl.dataset.old
    }, def = tnEl.dataset.def || '', hasEn = txEl.dataset.hasen === '1';
  const w = document.createElement('div');
  w.className = 'ie say';
  w.innerHTML = `<div class="row"><input class="nm" list="spkl" autocomplete="off" data-key="sayn:${ scene }:${ ln }" data-orig="${ esc(O.name) }" placeholder="گوینده"><input class="tn" list="tonel" maxlength="40" autocomplete="off" data-key="sayt:${ scene }:${ ln }" data-orig="${ esc(O.tone) }" placeholder="${ esc(def ? 'لحن (خالی = ' + def + ')' : 'لحن (اختیاری)') }"></div>
    <textarea rows="3" data-key="saytx:${ scene }:${ ln }" data-orig="${ esc(O.text) }"></textarea>
    <div class="bar"><button class="b pri sv" hidden title="ذخیره (Enter) · خط بعد: Shift+Enter">ذخیره</button><button class="b cx" hidden title="انصراف (Esc)">انصراف</button></div>`;
  const nm = w.querySelector('input.nm'), tn = w.querySelector('input.tn'), tx = w.querySelector('textarea'), sv = w.querySelector('.sv'), cx = w.querySelector('.cx');
  nm.value = O.name;
  tn.value = O.tone;
  tx.value = O.text;
  const f = () => {
    sv.classList.toggle('dirty', nm.value !== O.name || tn.value !== O.tone || tx.value !== O.text);
    [
      nm,
      tn,
      tx
    ].forEach(x => x.classList.toggle('dirty', x.value !== x.dataset.orig));
  };
  [
    nm,
    tn,
    tx
  ].forEach(x => x.addEventListener('input', f));
  f();
  box.classList.add('ed');
  box.prepend(w);
  tabComplete(nm);
  autoGrow(tx);
  pick({
    nm,
    tn,
    tx
  });
  const close = () => {
    w.remove();
    box.classList.remove('ed');
  };
  cx.onclick = close;
  sv.onclick = async () => {
    w._keep = true;
    try {
      if (!tx.value.trim()) {
        [
          nm,
          tn,
          tx
        ].forEach(x => x.dataset.orig = x.value);
        if (await askDelete(scene, ln, 'say', O.text, hasEn))
          return;
        nm.dataset.orig = O.name;
        tn.dataset.orig = O.tone;
        tx.dataset.orig = O.text;
        return;
      }
      if (!nm.value.trim())
        return askAlert('اسم گوینده را بنویس.');
      if (nm.value.trim() !== O.name && !SPK()[nm.value.trim()] && !(await askConfirm(`گویندهٔ جدید «${ nm.value.trim() }» ساخته بشه؟ رنگ و صدای خودش رو می‌گیره.`, 'بساز')))
        return;
      await api('/api/line', {
        ...lineRef(scene, ln),
        op: 'say',
        old: O,
        new: {
          name: nm.value.trim(),
          tone: tn.value.trim(),
          text: tx.value
        }
      });
      [
        nm,
        tn,
        tx
      ].forEach(x => x.dataset.orig = x.value);
      await reload();
    } catch (e) {
      fail(e);
    } finally {
      w._keep = false;
    }
  };
  w.onkeydown = e => {
    if (e.key === 'Escape')
      close();
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sv.click();
    }
  };
  onLeave(w, async () => {
    const changed = nm.value !== O.name || tn.value !== O.tone || tx.value !== O.text;
    if (!changed || !tx.value.trim() || !nm.value.trim())
      close();
    else
      await sv.onclick();
  });
  w.api = {
    nm,
    tn,
    tx
  };
  return w.api;
}
function tabComplete(inp) {
  inp.addEventListener('keydown', e => {
    if (e.key !== 'Tab')
      return;
    const v = inp.value;
    if (!v.trim())
      return;
    const m = (S.P.speakers || []).map(s => s.name).find(n => n.startsWith(v) && n !== v);
    if (m) {
      e.preventDefault();
      inp.value = m;
      inp.dispatchEvent(new Event('input'));
    }
  });
}
export function openComposer(bar, {scene, after, kind}) {
  const k = `add:${ scene }:${ after }:${ kind }`;
  if (document.querySelector(`[data-key="${ k }"]`))
    return;
  const w = document.createElement('div');
  w.className = 'cmp';
  w.innerHTML = (kind === 'say' ? `<input class="nm" list="spkl" autocomplete="off" data-key="addname:${ scene }:${ after }:${ kind }" data-orig="" placeholder="گوینده (اسمش رو تایپ کن؛ Tab = تکمیل)"><input class="tn" list="tonel" maxlength="40" autocomplete="off" data-key="addtone:${ scene }:${ after }:${ kind }" data-orig="" placeholder="لحن (اختیاری؛ خالی = لحن پیش‌فرض گوینده)">` : `<input class="lb" list="lbll" maxlength="15" autocomplete="off" data-key="addlabel:${ scene }:${ after }:${ kind }" data-orig="" placeholder="برچسب (اختیاری، مثلاً گگ)">`) + `<textarea rows="2" data-key="${ k }" data-orig="" placeholder="${ kind === 'say' ? 'متن دیالوگ... (Enter = ثبت · Shift+Enter = خط بعد · Esc = انصراف)' : 'توضیح تصویر... (Enter = ثبت · Shift+Enter = خط بعد · Esc = انصراف)' }"></textarea><div class="btns" hidden><button class="b sv">افزودن</button><button class="b cx">انصراف</button></div>`;
  bar.after(w);
  autoGrow(w.querySelector('textarea'));
  const ta = w.querySelector('textarea'), nm = w.querySelector('input.nm'), lb = w.querySelector('input.lb'), tn = w.querySelector('input.tn'), sv = w.querySelector('.sv'), cx = w.querySelector('.cx');
  const f = () => {
    sv.classList.toggle('dirty', !!(ta.value || nm && nm.value || lb && lb.value || tn && tn.value));
    [
      ta,
      nm,
      lb,
      tn
    ].forEach(x => x && x.classList.toggle('dirty', !!x.value));
  };
  ta.addEventListener('input', f);
  if (tn)
    tn.addEventListener('input', f);
  if (nm) {
    nm.addEventListener('input', f);
    tabComplete(nm);
  }
  if (lb)
    lb.addEventListener('input', f);
  f();
  (nm || lb || ta).focus();
  cx.onclick = () => w.remove();
  sv.onclick = async () => {
    w._keep = true;
    try {
      const name = nm ? nm.value.trim() : '';
      if (kind === 'say') {
        if (!name)
          return askAlert('اسم گوینده رو بنویس.');
        if (!SPK()[name] && !(await askConfirm(`گویندهٔ جدید «${ name }» ساخته بشه؟ رنگ و صدای خودش رو می‌گیره.`, 'بساز')))
          return;
      }
      await api('/api/add', {
        ...lineRef(scene, after, 'after'),
        kind,
        speaker: name,
        text: ta.value,
        label: lb ? lb.value.trim() : '',
        tone: tn ? tn.value.trim() : ''
      });
      ta.dataset.orig = ta.value;
      if (nm)
        nm.dataset.orig = nm.value;
      if (lb)
        lb.dataset.orig = lb.value;
      if (tn)
        tn.dataset.orig = tn.value;
      await reload();
    } catch (e) {
      fail(e);
    } finally {
      w._keep = false;
    }
  };
  w.onkeydown = e => {
    if (e.key === 'Escape')
      cx.click();
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (e.target === ta)
        sv.click();
      else
        ta.focus();
    }
  };
  onLeave(w, async () => {
    const any = ta.value.trim() || nm && nm.value.trim() || lb && lb.value.trim() || tn && tn.value.trim();
    if (!any) {
      cx.click();
      return;
    }
    if (!ta.value.trim() || kind === 'say' && !nm.value.trim())
      return;
    await sv.onclick();
  });
  return {
    ta,
    nm,
    lb,
    tn
  };
}
export function openFromV(v) {
  const sid = v.closest('section[data-scene]').dataset.scene, k = v.dataset.k, ln = +v.dataset.ln;
  return [
    'speaker',
    'tone',
    'say'
  ].includes(k) ? openSayEditor(v.closest('.it'), {
    scene: sid,
    ln,
    focus: {
      speaker: 'nm',
      tone: 'tn'
    }[k] || 'tx'
  }) : openEditor(v, {
    scene: sid,
    ln,
    key: k,
    old: v.dataset.old
  });
}
export function wire() {
  $$('figure.shot').forEach(f => {
    const id = f.dataset.id, m = S.BL.flatMap(b => b.images).find(x => x.id === id);
    const nt = f.querySelector('.nt'), ft = f.querySelector('.fx'), sn = f.querySelector('[data-sn]');
    track(nt, sn);
    /* the note is one input: Enter or leaving the field saves it */
    nt.addEventListener('input', () => grow(nt));
    grow(nt);
    nt._save = () => sn.click();
    nt.addEventListener('blur', () => setTimeout(() => {
      if (!document.hasFocus() || !nt.isConnected || nt.closest('.hide'))
        return;
      if (nt.value !== nt.dataset.orig)
        sn.click();
    }, 0));
    nt.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        sn.click();
      }
      if (e.key === 'Escape') {
        nt.value = nt.dataset.orig;
        nt.dispatchEvent(new Event('input'));
      }
    });
    sn.onclick = async () => {
      try {
        const body = { id };
        if (nt.value !== nt.dataset.orig)
          body.note = nt.value;
        if (ft.value !== ft.dataset.orig)
          body.fx = ft.value;
        if (body.note === undefined && body.fx === undefined)
          return;
        await api('/api/image', body);
        if (body.note !== undefined) {
          nt.dataset.orig = nt.value;
          nt.dispatchEvent(new Event('input'));
          m.note = nt.value;
          stats();
          filt();
        }
        if (body.fx !== undefined) {
          ft.dataset.orig = ft.value;
          await reload();
        }
      } catch (e) {
        fail(e);
      }
    };
    wireFx(ft, v => api('/api/image', {
      id,
      fx: v
    }));
    f.querySelectorAll('[data-vid]').forEach(b => b.onclick = () => playVideo(b.dataset.vid, b.dataset.name));
    const c = f.querySelector('[data-clrimg]');
    if (c)
      c.onclick = async () => {
        try {
          await api('/api/image', {
            id,
            stale: false
          });
          await reload();
        } catch (e) {
          fail(e);
        }
      };
  });
  $$('section[data-scene]').forEach(s => {
    const sid = s.dataset.scene;
    s.querySelectorAll('[data-regen]').forEach(b => b.onclick = async () => {
      try {
        await api('/api/regen', { scene: sid });
        pollJob();
      } catch (e) {
        fail(e);
      }
    });
    s.querySelectorAll('.v').forEach(v => v.onclick = () => openFromV(v));
    s.querySelectorAll('[data-aden]').forEach(b => b.onclick = () => openEditor(b.parentElement, {
      scene: sid,
      ln: +b.dataset.aden,
      key: 'en',
      old: '',
      op: 'add_en'
    }));
    s.querySelectorAll('[data-fl]').forEach(b => b.onclick = async () => {
      const msg = await askPrompt('مشکل فرمت این قسمت چیه؟ (برای هوش مصنوعی ثبت می‌شه؛ اختیاری)', 'فرمت این قسمت درست نیست', {
        chips: ['متن ناقص', 'ترجمه نامناسب', 'گوینده اشتباه', 'لحن نامناسب']
      });
      if (msg === null)
        return;
      try {
        await api('/api/issue', {
          ...lineRef(sid, +b.dataset.fl),
          message: msg
        });
        await reload();
      } catch (e) {
        fail(e);
      }
    });
    s.querySelectorAll('[data-wreg]').forEach(b => b.onclick = async () => {
      try {
        await api('/api/issue', {
          ...lineRef(sid, +b.dataset.wreg),
          message: 'خط با قالب ناشناخته: ' + b.parentElement.querySelector('code').textContent
        });
        await reload();
      } catch (e) {
        fail(e);
      }
    });
    s.querySelectorAll('[data-clr]').forEach(b => b.onclick = async () => {
      try {
        await api('/api/issue', {
          ...lineRef(sid, +b.dataset.clr),
          clear: true
        });
        await reload();
      } catch (e) {
        fail(e);
      }
    });
    s.querySelectorAll('[data-del]').forEach(b => b.onclick = () => askDelete(sid, +b.dataset.del, b.dataset.dk, b.dataset.old, b.dataset.hasen === '1'));
    s.querySelectorAll('.addbar button').forEach(b => b.onclick = () => openComposer(b.parentElement, {
      scene: sid,
      after: +b.parentElement.dataset.after,
      kind: b.dataset.add
    }));
  });
  $$('[data-sedit]').forEach(b => b.onclick = () => openSceneDialog(b.dataset.sedit));
}
