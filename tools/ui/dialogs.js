import { S } from './state.js';
import { reload } from './panels.js';
import {
  TT,
  api,
  esc,
  fail,
  modelOpts,
  pollJob
} from './core.js';
/* Pop-up dialogs: the voice manager of one line (choose, listen, archive, make another) and the picture archive.
   Nothing is deleted: «archive» moves a file into an archive folder and «restore» moves it back. */
let DLG = null;
/* {el, draw} of the dialog that is open, so it can be redrawn after the page reloads */
export const redrawDialog = () => {
  if (DLG && DLG.el.open)
    DLG.draw();
};
const findItem = id => S.BL.flatMap(b => b.items).find(x => x.id === id);
const findImage = id => S.BL.flatMap(b => b.images).find(x => x.id === id);
const voiceUrl = (lg, id, name) => name === 'default' ? `audio/${ lg }/${ id }.mp3` : `audio/${ lg }/${ id }.${ name }.mp3`;
const dlgAudio = new Audio();
function openDialog(draw) {
  if (DLG && DLG.el.open)
    DLG.el.close();
  const el = document.createElement('dialog');
  el.className = 'dlg';
  document.body.appendChild(el);
  const d = {
    el,
    draw: () => {
      el.innerHTML = draw();
      el.querySelector('[data-dclose]').onclick = () => el.close();
    }
  };
  el.addEventListener('close', () => {
    dlgAudio.pause();
    if (DLG === d)
      DLG = null;
    el.remove();
  });
  el.addEventListener('click', e => {
    if (e.target === el)
      el.close();
  });
  DLG = d;
  d.draw();
  el.showModal();
  return d;
}
const dAct = async fn => {
  try {
    await fn();
    await reload();
    redrawDialog();
  } catch (e) {
    fail(e);
  }
};
const hintFor = sc => mm => {
  const need = [...new Set(sc.blocks.flatMap(b => b.items.filter(i => i.k === 'say').map(i => i.sp)))];
  const miss = mm.voices.length ? need.filter(n => {
    const s = (S.P.speakers || []).find(x => x.name === n);
    return s && s.voice && !mm.voices.some(v => v.name === s.voice);
  }) : [];
  return miss.length ? ' · ⚠ صدای ' + miss.join('، ') + ' را ندارد' : '';
};
/* ---- voice manager of one line */
function openVoiceDialog(sid, iid) {
  openDialog(() => {
    const sc = S.P.scenes.find(s => s.id === sid), it = findItem(iid);
    if (!sc || !it)
      return '<p>این خط دیگه نیست.</p><button data-dclose>بستن</button>';
    const langs = [
      'fa',
      'en'
    ].filter(lg => lg === 'fa' || it.en != null);
    const rows = lg => {
      const v = (it.audio_v || {})[lg] || {
        names: [],
        chosen: '',
        archived: []
      };
      return `<div class="dlang"><b>${ lg === 'fa' ? 'فارسی' : 'English' }</b>` + (v.names.length ? v.names.map(n => `<div class="vrow"><label><input type="radio" name="vp-${ lg }" data-dpick="${ lg }" value="${ esc(n) }"${ n === v.chosen ? ' checked' : '' }> <bdi dir="ltr">${ esc(n) }</bdi>${ n === v.chosen ? ' ✔' : '' }</label><button class="b" data-dplay="${ voiceUrl(lg, iid, n) }">▶</button><button class="b" data-darch="${ lg }" data-n="${ esc(n) }">🗄 آرشیو</button></div>`).join('') : '<div class="none">هنوز صدایی ساخته نشده.</div>') + (v.archived && v.archived.length ? `<details><summary>آرشیو (${ v.archived.length })</summary>${ v.archived.map(a => `<div class="vrow"><bdi dir="ltr">${ esc(a.name) }</bdi><button class="b" data-dplay="${ a.src }">▶</button><button class="b" data-drest="${ lg }" data-n="${ esc(a.name) }">↩ برگردان</button></div>`).join('') }</details>` : '') + `</div>`;
    };
    return `<h3>صدای این خط</h3><p class="dq">${ esc(it.sp) }: ${ esc(it.fa) }</p>${ langs.map(rows).join('') }<hr>
      <div class="dgen"><label>مدل: <select id="dmodel">${ modelOpts(sc.model || TT().default, false, hintFor(sc)) }</select></label>
      ${ langs.map(lg => `<label><input type="checkbox" data-dlg="${ lg }" checked> ${ lg === 'fa' ? 'فارسی' : 'English' }</label>`).join('') }
      <button class="b pri" data-dmake="1">🔊 ساخت صدا</button> <span class="jobst" data-job="${ sid }"></span></div>
      <small>ساخت صدا هزینه داره (قیمت هر مدل کنار اسمشه). صدای تازه کنار قبلی‌ها می‌شینه و همون نهایی می‌شه؛ ساختن دوبارهٔ همون مدل، قبلی رو می‌فرسته آرشیو.</small>
      <div class="dbar"><button class="b" data-dclose="1">بستن</button></div>`;
  });
  DLG.el.dataset.kind = 'voice';
  DLG.el.dataset.sid = sid;
  DLG.el.dataset.iid = iid;
}
/* ---- picture archive of one shot */
function openArchiveDialog(iid) {
  openDialog(() => {
    const m = findImage(iid);
    if (!m)
      return '<p>این تصویر دیگه نیست.</p><button data-dclose>بستن</button>';
    const k = m.archived || [];
    return `<h3>آرشیو ${ esc(iid) }</h3>${ k.length ? k.map(a => `<div class="vrow"><img class="dthumb" src="${ esc(a.src) }" alt=""><bdi dir="ltr">${ esc(a.name) }</bdi><button class="b" data-irestore="${ esc(a.name) }">↩ برگردان</button></div>`).join('') : '<div class="none">آرشیو خالیه.</div>' }<div class="dbar"><button class="b" data-dclose="1">بستن</button></div>`;
  });
  DLG.el.dataset.kind = 'archive';
  DLG.el.dataset.iid = iid;
}
/* ---- attach / detach reference pictures of one shot (edits the [REFS TO ATTACH: ...] line of its prompt) */
function openAttachDialog(iid) {
  openDialog(() => {
    const m = findImage(iid);
    if (!m)
      return '<p>این تصویر دیگه نیست.</p><button data-dclose>بستن</button>';
    const have = m.refs.map(r => r.name), all = S.P.refs || [], known = new Set(all.map(r => r.name));
    const row = (name, src, kind) => `<label class="aref"><input type="checkbox" data-aref="${ esc(name) }"${ have.includes(name) ? ' checked' : '' }>${ src ? `<img class="dthumb" src="${ esc(src) }" alt="">` : '<span class="dthumb none">فایل نداره</span>' }<span><bdi dir="ltr">${ esc(name) }</bdi><small>${ esc(kind || '') }</small></span></label>`;
    return `<h3>رفرنس‌های ${ esc(iid) }</h3><div class="arefs">${ all.map(r => row(r.name, r.src, r.kind)).join('') }${ have.filter(n => !known.has(n)).map(n => row(n, '', 'ساخته نشده')).join('') }</div><small>رفرنس تازه باید قبلاً توی images/refs/ باشه. تغییر رفرنس یعنی تصویر کهنه می‌شه و باید دوباره ساخته بشه.</small><div class="dbar"><button class="b pri" data-dsaverefs="1">💾 ذخیره</button> <button class="b" data-dclose="1">انصراف</button></div>`;
  });
  DLG.el.dataset.kind = 'attach';
  DLG.el.dataset.iid = iid;
}
export function boot_dialogs() {
  document.addEventListener('click', e => {
    const t = e.target.closest('button,input[data-dpick]');
    if (!t)
      return;
    const g = t.closest('dialog.dlg');
    if (!g) {
      if (t.dataset.vgen)
        return openVoiceDialog(t.dataset.sc, t.dataset.vgen);
      const f = t.closest('figure.shot');
      if (f && t.dataset.irest)
        return openArchiveDialog(f.dataset.id);
      if (f && t.dataset.attach)
        return openAttachDialog(f.dataset.id);
      if (f && t.dataset.iarch) {
        const m = findImage(f.dataset.id);
        if (m && m.versions[m.vi])
          dAct(() => api('/api/archive', {
            kind: 'image',
            id: m.id,
            name: m.versions[m.vi].name
          }));
        return;
      }
      return;
    }
    const sid = g.dataset.sid, iid = g.dataset.iid;
    if (t.dataset.dsaverefs) {
      const m = findImage(iid), on = [...g.querySelectorAll('[data-aref]:checked')].map(x => x.dataset.aref);
      const names = [
        ...m.refs.map(r => r.name).filter(n => on.includes(n)),
        ...on.filter(n => !m.refs.some(r => r.name === n))
      ];
      return dAct(async () => {
        await api('/api/refs', {
          id: iid,
          refs: names
        });
        g.close();
      });
    }
    if (t.dataset.dplay) {
      dlgAudio.src = t.dataset.dplay + '?v=' + Date.now();
      dlgAudio.play().catch(() => {
      });
      return;
    }
    if (t.dataset.dpick)
      return dAct(() => api('/api/voicepick', {
        scene: sid,
        id: iid,
        lang: t.dataset.dpick,
        variant: t.value
      }));
    if (t.dataset.darch)
      return dAct(() => api('/api/archive', {
        kind: 'voice',
        id: iid,
        lang: t.dataset.darch,
        name: t.dataset.n,
        scene: sid
      }));
    if (t.dataset.drest)
      return dAct(() => api('/api/restore', {
        kind: 'voice',
        id: iid,
        lang: t.dataset.drest,
        name: t.dataset.n
      }));
    if (t.dataset.irestore)
      return dAct(() => api('/api/restore', {
        kind: 'image',
        id: iid,
        name: t.dataset.irestore
      }));
    if (t.dataset.dmake) {
      const langs = [...g.querySelectorAll('[data-dlg]:checked')].map(x => x.dataset.dlg);
      if (!langs.length)
        return alert('حداقل یه زبان انتخاب کن.');
      api('/api/linevoice', {
        scene: sid,
        id: iid,
        model: g.querySelector('#dmodel').value,
        langs
      }).then(() => {
        t.disabled = true;
        pollJob();
      }).catch(fail);
    }
  });
}
