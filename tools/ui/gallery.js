import { S } from './state.js';
import {
  $,
  $$,
  api,
  esc,
  fa,
  fail,
  toast
} from './core.js';
import { ic } from './icons.js';
import { reload } from './panels.js';
import { sceneNo } from './render.js';
import { blockByBid } from './player.js';
import { copyBatch } from './drawer.js';
/* The gallery: the page the app opens on. A dense grid of 16:9 tiles (one per picture, in file order), drag to reorder, the strip of pictures that have no
   place yet, the "+" tile and its picker. The address is review.html#gallery; review.html#IMG045 is the spread of that picture. */
let SEL = new Set(), LAST = null, PICK = false, D = null, SWALLOW = false;
const gal = () => document.body.classList.contains('gal');
const rtl = () => getComputedStyle($('#gallery')).direction === 'rtl';
const modeOf = h => {
  h = decodeURIComponent(String(h).replace(/^#/, ''));
  return h === 'review' ? false : !h || h === 'gallery' || blockByBid(h) < 0;
};
export function setMode(on) {
  document.body.classList.toggle('gal', on);
  $('#gallery').hidden = !on;
  if (on) {
    if (S.playing)
      $('#play').click();
    paint();
  }
}
export function startMode(hash) {
  const on = modeOf(hash);
  setMode(on);
  if (on)
    history.replaceState(null, '', '#gallery');
}
/* the pictures of the scenes that are on, in file order, with their scene's number */
const tiles = () => S.P.scenes.filter(s => !s.off).flatMap(sc => sc.blocks.flatMap(b => b.images.map(m => ({
  m,
  sc
}))));
const tileHtml = ({m, sc}, first) => {
  const st = m.off ? 'off' : m.status === 'ok' ? 'ok' : 'pend', n = m.versions.length;
  return `<div class="tile ${ m.src ? '' : 'empty' } ${ st }${ first ? ' sb' : '' }${ SEL.has(m.id) ? ' sel' : '' }" data-id="${ m.id }" data-drag="tile" tabindex="0" role="button" aria-label="${ m.id }">${ m.src ? `<img src="${ esc(m.src) }" alt="" loading="lazy" decoding="async" draggable="false">` : `<span class="gid" dir="ltr">${ m.id }</span>` }${ sc.id === 'scene-00' ? '' : `<b class="no">${ fa(sceneNo(sc)) }</b>` }<i class="dot"></i>${ n > 1 ? `<u class="gvc">${ fa(n) }</u>` : '' }</div>`;
};
function paint() {
  const g = $('#gallery');
  if (!S.P || !g)
    return;
  const all = tiles(), ids = new Set(all.map(t => t.m.id));
  SEL = new Set([...SEL].filter(i => ids.has(i)));
  let prev = null;
  const grid = all.map(t => {
    const first = prev && prev !== t.sc.id;
    prev = t.sc.id;
    return tileHtml(t, first);
  }).join('') + `<button type="button" class="tile add" data-gadd="1" aria-label="افزودن تصویر" title="افزودن تصویر">${ ic('plus') }</button>`;
  const batches = [...new Set(all.map(t => t.m.batch).filter(Boolean))].sort();
  const un = S.P.unplaced || [], inbox = (S.P.inbox || []).filter(f => f.kind === 'image');
  g.innerHTML = `<div class="gtools"><button type="button" class="quiet sm" id="gSel" aria-pressed="${ PICK }">انتخاب</button><span class="gcount" id="gCount"></span><span class="gsp"></span>${ batches.map(b => `<button type="button" class="quiet sm" data-gbatch="${ b }" title="کپی پرامپت‌های این دسته">${ ic('image') }<bdi dir="ltr">${ b }</bdi></button>`).join('') }</div><div class="ggrid" id="ggrid">${ grid }<div class="gline" hidden></div></div>${ un.length || inbox.length ? `<div class="gun"><h4>جا نگرفته‌ها <small>(بکش توی گالری، یا + بزن)</small></h4><div class="gur">${ un.map(u => `<div class="uit" data-drag="un" data-uid="${ u.id }">${ u.src ? `<img src="${ esc(u.src) }" alt="" loading="lazy" draggable="false">` : '<span class="uph"></span>' }<bdi dir="ltr">${ u.id }</bdi><button type="button" class="ib sm" data-gun="${ u.id }" aria-label="جاگذاری ${ u.id }">${ ic('plus') }</button></div>`).join('') }${ inbox.map(f => `<div class="uit" data-drag="un" data-uid=""><span class="uph"></span><bdi dir="ltr">${ esc(f.name) }</bdi><button type="button" class="ib sm" data-gun="" aria-label="جای تازه">${ ic('plus') }</button></div>`).join('') }</div></div>` : '' }`;
  count();
}
const count = () => {
  const c = $('#gCount');
  if (c)
    c.textContent = SEL.size ? `${ fa(SEL.size) } انتخاب‌شده` : `${ fa(tiles().length) } تصویر`;
};
export const galleryRefresh = () => {
  if (S.P)
    paint();
};
/* ---- where a drop lands: just before / after a tile (in reading order, so "before" is on the right in a right-to-left page) */
const ordered = () => $$('#ggrid .tile[data-id]');
function target(x, y) {
  const el = document.elementFromPoint(x, y), t = el && el.closest('#ggrid .tile');
  if (t && t.dataset.gadd !== undefined) {
    const l = ordered().pop();
    return l && { id: l.dataset.id, before: false, el: l };
  }
  let tt = t && t.dataset.id ? t : null;
  if (!tt && el && el.closest('#ggrid')) {
    let best = 60;
    ordered().forEach(c => {
      const r = c.getBoundingClientRect(), d = Math.abs(x - (r.left + r.right) / 2);
      if (y >= r.top - 3 && y <= r.bottom + 3 && d < best) {
        best = d;
        tt = c;
      }
    });
  }
  if (!tt)
    return null;
  const r = tt.getBoundingClientRect(), left = x < (r.left + r.right) / 2;
  return {
    id: tt.dataset.id,
    before: rtl() ? !left : left,
    el: tt
  };
}
function showLine(d) {
  const ln = $('#ggrid .gline');
  if (!ln)
    return;
  ln.hidden = !d;
  if (!d)
    return;
  const gr = $('#ggrid').getBoundingClientRect(), r = d.el.getBoundingClientRect(), edgeLeft = rtl() ? !d.before : d.before;
  ln.style.cssText = `left:${ (edgeLeft ? r.left : r.right) - gr.left - 2 }px;top:${ r.top - gr.top }px;height:${ r.height }px`;
}
function begin() {
  if (!D || D.on)
    return;
  D.on = true;
  document.body.classList.add('gdrag');
  const ids = D.kind === 'tile' ? (SEL.has(D.id) ? ordered().map(t => t.dataset.id).filter(i => SEL.has(i)) : [D.id]) : [];
  D.ids = ids;
  ids.forEach(i => $(`#ggrid .tile[data-id="${ i }"]`)?.classList.add('lift'));
  const gh = document.createElement('div');
  gh.className = 'gghost';
  gh.textContent = D.kind === 'tile' ? (ids.length > 1 ? fa(ids.length) : D.id) : D.uid || '+';
  document.body.appendChild(gh);
  D.ghost = gh;
}
function end(ok) {
  clearTimeout(D.timer);
  if (D.ghost)
    D.ghost.remove();
  document.body.classList.remove('gdrag');
  $$('#ggrid .lift').forEach(t => t.classList.remove('lift'));
  showLine(null);
  const d = D;
  D = null;
  if (d.on) {
    SWALLOW = true;
    setTimeout(() => SWALLOW = false, 0);
  }
  if (ok && d.on && d.drop)
    drop(d);
}
async function drop(d) {
  const pos = d.drop.before ? { before: d.drop.id } : { after: d.drop.id };
  try {
    if (d.kind === 'tile') {
      if (d.ids.includes(d.drop.id))
        return;
      await api('/api/move', {
        ids: d.ids,
        ...pos
      });
      SEL.clear();
    } else
      await api('/api/addimage', {
        ...pos,
        ...d.uid ? { id: d.uid } : {}
      });
  } catch (e) {
    fail(e);
  }
  await reload();
}
function pointerMove(e) {
  if (!D || e.pointerId !== D.pid)
    return;
  if (!D.on) {
    if (e.pointerType !== 'touch' && Math.hypot(e.clientX - D.x, e.clientY - D.y) > 6)
      begin();
    else if (Math.hypot(e.clientX - D.x, e.clientY - D.y) > 10)
      clearTimeout(D.timer);
  }
  if (!D.on)
    return;
  e.preventDefault();
  D.ghost.style.cssText = `left:${ e.clientX + 10 }px;top:${ e.clientY + 10 }px`;
  const g = $('#gallery'), r = g.getBoundingClientRect();
  if (e.clientY < r.top + 40)
    g.scrollBy(0, -14);
  else if (e.clientY > r.bottom - 40)
    g.scrollBy(0, 14);
  D.drop = target(e.clientX, e.clientY);
  showLine(D.drop);
}
/* ---- the picker: a new empty slot, a picture that has no place yet, or an existing picture moved here. pos = {after} | {before} | {scene} */
export function openPicker(pos, open) {
  const un = S.P.unplaced || [], all = tiles(), dlg = document.createElement('dialog');
  dlg.className = 'dlg gpick';
  dlg.innerHTML = `<h3>افزودن تصویر</h3><button type="button" class="opt" data-pk="new"><span>جای خالی تازه</span><span class="c">شمارهٔ بعدی</span></button>${ un.length ? '<h4>جا نگرفته‌ها</h4>' + un.map(u => `<button type="button" class="opt" data-pk="${ u.id }"><span><bdi dir="ltr">${ u.id }</bdi></span><span class="c">${ u.src ? 'فایل دارد' : 'فقط پرامپت' }</span></button>`).join('') : '' }<h4>جابه‌جایی یک تصویر به اینجا</h4><div class="row"><select id="pkAll" aria-label="همهٔ تصویرها">${ all.map(t => `<option value="${ t.m.id }">${ t.m.id } · ${ t.sc.id === 'scene-00' ? 'تامبنیل' : 'صحنه ' + fa(sceneNo(t.sc)) }</option>`).join('') }</select><button type="button" class="outline" data-pk="move">انتقال</button></div><div class="btns"><button type="button" class="quiet" data-pk="">انصراف</button></div>`;
  document.body.appendChild(dlg);
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('click', async e => {
    const b = e.target.closest('[data-pk]');
    if (!b)
      return;
    const k = b.dataset.pk;
    if (!k) {
      dlg.close();
      return;
    }
    try {
      let id;
      if (k === 'move') {
        id = $('#pkAll').value;
        await api('/api/move', {
          ids: [id],
          ...pos.scene ? { to_end_of_scene: pos.scene } : pos
        });
      } else
        id = (await api('/api/addimage', {
          ...pos,
          ...k === 'new' ? {} : { id: k }
        })).id;
      dlg.close();
      await reload();
      if (open)
        location.hash = id;
    } catch (er) {
      fail(er);
    }
  });
  dlg.showModal();
}
const lastScene = () => [...S.P.scenes].reverse().find(s => !s.off && s.id !== 'scene-00')?.id;
const endPos = () => {
  const l = tiles().pop();
  return l ? { after: l.m.id } : { scene: lastScene() };
};
export function boot_gallery() {
  window.addEventListener('hashchange', () => setMode(modeOf(location.hash)));
  $('#galBtn').addEventListener('click', () => {
    location.hash = 'gallery';
  });
  const g = $('#gallery');
  g.addEventListener('pointerdown', e => {
    const t = e.target.closest('[data-drag]');
    if (!t || e.button > 0)
      return;
    D = {
      kind: t.dataset.drag,
      id: t.dataset.id,
      uid: t.dataset.uid,
      x: e.clientX,
      y: e.clientY,
      pid: e.pointerId,
      on: false
    };
    if (e.pointerType === 'touch')
      D.timer = setTimeout(begin, 350);
  });
  window.addEventListener('pointermove', pointerMove, { passive: false });
  window.addEventListener('pointerup', e => D && e.pointerId === D.pid && end(true));
  window.addEventListener('pointercancel', e => D && e.pointerId === D.pid && end(false));
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape' && D)
      end(false);
  });
  g.addEventListener('click', async e => {
    if (SWALLOW) {
      e.preventDefault();
      return;
    }
    const b = e.target.closest('button');
    if (b && b.id === 'gSel') {
      PICK = !PICK;
      b.setAttribute('aria-pressed', PICK);
      g.classList.toggle('picking', PICK);
      return;
    }
    if (b && b.dataset.gbatch)
      return copyBatch(b.dataset.gbatch);
    if (b && b.dataset.gadd !== undefined)
      return openPicker(endPos());
    if (b && b.dataset.gun !== undefined) {
      try {
        await api('/api/addimage', {
          ...endPos(),
          ...b.dataset.gun ? { id: b.dataset.gun } : {}
        });
        toast('تصویر جا گرفت');
      } catch (er) {
        fail(er);
      }
      return reload();
    }
    const t = e.target.closest('.tile[data-id]');
    if (!t)
      return;
    const id = t.dataset.id;
    if (e.shiftKey && LAST) {
      const ids = ordered().map(x => x.dataset.id), a = ids.indexOf(LAST), z = ids.indexOf(id);
      ids.slice(Math.min(a, z), Math.max(a, z) + 1).forEach(i => SEL.add(i));
    } else if (PICK || e.ctrlKey || e.metaKey) {
      if (SEL.has(id))
        SEL.delete(id);
      else
        SEL.add(id);
    } else {
      location.hash = id;
      return;
    }
    LAST = id;
    $$('#ggrid .tile[data-id]').forEach(x => x.classList.toggle('sel', SEL.has(x.dataset.id)));
    count();
  });
  g.addEventListener('keydown', e => {
    const t = e.target.closest('.tile[data-id]');
    if (t && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      location.hash = t.dataset.id;
    }
  });
}
