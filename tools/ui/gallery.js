import { S } from './state.js';
import {
  $,
  $$,
  api,
  esc,
  fa,
  fail,
  matchItem,
  toast
} from './core.js';
import { ic } from './icons.js';
import {
  filt,
  lightbox,
  reload
} from './panels.js';
import {
  moveTarget,
  sceneNo
} from './render.js';
import { blockByBid } from './player.js';
import {
  copyBatch,
  drawerRefresh,
  openDrawer
} from './drawer.js';
/* The gallery: the page the app opens on. A dense grid of 16:9 tiles (one per picture, in file order), drag to reorder, the strip of pictures that have no
   place yet, the "+" tile and its picker. The address is review.html#gallery; review.html#IMG045 is the spread of that picture. */
let SEL = new Set(), LAST = null, PICK = false, D = null, SWALLOW = false, REORD = false;
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
  sc,
  b
}))));
/* the search and filter of the gallery: status filter + id, scene title, note or any line of the picture's block */
const hit = ({m, sc, b}, q = S.q) => matchItem({m, sc, b}, S.filter, q);
const tileHtml = (t, first) => {
  const {m, sc} = t;
  const st = m.off ? 'off' : m.status === 'redo' ? 'redo' : m.status === 'ok' ? 'ok' : 'pend', n = m.versions.length;
  const tip = `${ m.id } · ${ sc.title }${ m.note ? ' · دارای یادداشت' : '' }${ m.stale ? ' · کهنه' : '' }`;
  return `<div class="tile ${ m.src ? '' : 'empty' } ${ st }${ first ? ' sb' : '' }${ SEL.has(m.id) ? ' sel' : '' }" ${ hit(t) ? '' : 'hidden' } data-id="${ m.id }" data-drag="tile" tabindex="0" role="button" aria-label="${ m.id }" title="${ esc(tip) }">${ m.src ? `<img src="${ esc(m.src) }" alt="" loading="lazy" decoding="async" draggable="false"><span class="tid" dir="ltr">${ m.id }</span>` : `<span class="gid" dir="ltr">${ m.id }</span>` }${ sc.id === 'scene-00' ? '' : `<b class="no">${ fa(sceneNo(sc)) }</b>` }<i class="dot"></i>${ m.stale ? '<i class="gstl" title="پرامپت عوض شده">!</i>' : '' }${ n > 1 ? `<u class="gvc">${ fa(n) }</u>` : '' }</div>`;
};
function paint() {
  const g = $('#gallery');
  if (!S.P || !g)
    return;
  const all = tiles(), ids = new Set(all.map(t => t.m.id));
  SEL = new Set([...SEL].filter(i => ids.has(i)));
  const scenes = S.P.scenes.filter(s => !s.off);
  let prev = null;
  const grid = scenes.map(sc => {
    const is00 = sc.id === 'scene-00';
    const scTiles = sc.blocks.flatMap(b => b.images.map(m => ({ m, sc, b })));
    const head = `<div class="gshead" data-scene="${ sc.id }"><div class="gsinfo">${ is00 ? '' : `<b class="gsnum">صحنه ${ fa(sceneNo(sc)) }</b>` }<span class="gstitle">${ esc(sc.title || (is00 ? 'تامبنیل' : '')) }</span><span class="gscount">${ fa(scTiles.length) } تصویر</span></div><span class="mw smore-w"><button class="ib sm" type="button" data-smore="${ sc.id }" aria-label="منوی صحنه" aria-haspopup="menu" aria-expanded="false" title="منوی صحنه">${ ic('dots') }</button><div class="pop menu" role="menu" hidden></div></span></div>`;
    const tilesHtml = scTiles.map(t => {
      const first = prev && prev !== t.sc.id;
      prev = t.sc.id;
      return tileHtml(t, first);
    }).join('');
    const dropHtml = is00 ? '' : `<button type="button" class="tile add gdrop" data-gdrop="${ sc.id }" data-gadd="${ sc.id }" aria-label="افزودن تصویر به انتهای صحنه" title="کشیدن تصویر به اینجا یا کلیک برای افزودن">${ ic('plus') }</button>`;
    return `<div class="gsec" data-scene="${ sc.id }">${ head }<div class="gtiles">${ tilesHtml }${ dropHtml }</div></div>`;
  }).join('');
  const batches = [...new Set(all.map(t => t.m.batch).filter(Boolean))].sort();
  const un = S.P.unplaced || [], inbox = (S.P.inbox || []).filter(f => f.kind === 'image');
  g.innerHTML = `<div class="gtools"><button type="button" class="quiet sm" id="gSel" aria-pressed="${ PICK }">انتخاب</button><button type="button" class="quiet sm" id="gMove" aria-pressed="${ REORD }" title="در حالت جابه‌جایی، با کشیدن انگشت تصویر جابه‌جا می‌شود و صفحه جابه‌جا نمی‌شود">جابه‌جایی</button><span class="gcount" id="gCount"></span><span class="gbulk" id="gBulk" hidden><button type="button" class="quiet sm" data-gbulk="redo">بازسازی</button><button type="button" class="quiet sm" data-gbulk="off">کنار بگذار</button><button type="button" class="quiet sm" data-gbulk="clear">لغو</button></span><span class="gsp"></span>${ batches.map(b => `<button type="button" class="quiet sm" data-gbatch="${ b }" title="کپی پرامپت‌های این دسته">${ ic('batch') }<bdi dir="ltr">${ b }</bdi></button>`).join('') }</div><div class="ggrid" id="ggrid">${ grid }<div class="gline" hidden></div></div>${ un.length || inbox.length ? `<div class="gun"><h4>جا نگرفته‌ها <small>(بکش توی گالری، یا + بزن)</small></h4><div class="gur">${ un.map(u => `<div class="uit" data-drag="un" data-uid="${ u.id }">${ u.src ? `<img src="${ esc(u.src) }" alt="" loading="lazy" draggable="false">` : '<span class="uph"></span>' }<bdi dir="ltr">${ u.id }</bdi><button type="button" class="ib sm" data-gun="${ u.id }" aria-label="جاگذاری ${ u.id }">${ ic('plus') }</button></div>`).join('') }${ inbox.map(f => `<div class="uit" data-drag="un" data-uid="">${ f.src ? `<img src="${ esc(f.src) }" alt="" loading="lazy" draggable="false" data-inbzoom="${ esc(f.src) }" data-name="${ esc(f.name) }" title="بزرگ‌نمایی">` : '<span class="uph"></span>' }<bdi dir="ltr">${ esc(f.name) }</bdi><button type="button" class="ib sm" data-gun="" aria-label="جای تازه">${ ic('plus') }</button></div>`).join('') }</div></div>` : '' }`;
  g.classList.toggle('reorder', REORD);
  count();
}
const stat = () => {
  const all = tiles(), ok = all.filter(t => t.m.status === 'ok' && !t.m.off).length, pct = all.length ? Math.round(ok * 100 / all.length) : 0;
  $('#gst').textContent = `${ fa(ok) } / ${ fa(all.length) } تأیید شده`;
  $('#gpct').textContent = fa(pct) + '٪';
  $('#gstat .gbar i').style.width = pct + '%';
};
const count = () => {
  stat();
  const c = $('#gCount'), b = $('#gBulk');
  if (b) {
    b.hidden = !SEL.size;
    if (SEL.size) {
      const all = tiles(), sel = all.filter(t => SEL.has(t.m.id));
      const allOff = sel.length > 0 && sel.every(t => t.m.off);
      const allRedo = sel.length > 0 && sel.every(t => t.m.status === 'redo');
      const bOff = b.querySelector('[data-gbulk="off"], [data-gbulk="on"]');
      if (bOff) {
        bOff.dataset.gbulk = allOff ? 'on' : 'off';
        bOff.textContent = allOff ? 'برگردان' : 'کنار بگذار';
      }
      const bRedo = b.querySelector('[data-gbulk="redo"], [data-gbulk="unredo"]');
      if (bRedo) {
        bRedo.dataset.gbulk = allRedo ? 'unredo' : 'redo';
        bRedo.textContent = allRedo ? 'لغو بازسازی' : 'بازسازی';
      }
    }
  }
  $$('#ggrid .gsec').forEach(sec => {
    const cntEl = sec.querySelector('.gscount');
    if (cntEl) {
      const shown = sec.querySelectorAll('.tile[data-id]:not([hidden])').length;
      const total = sec.querySelectorAll('.tile[data-id]').length;
      cntEl.textContent = shown < total ? `${ fa(shown) } از ${ fa(total) } تصویر` : `${ fa(total) } تصویر`;
    }
  });
  if (c) {
    const shown = $$('#ggrid .tile[data-id]:not([hidden])').length, total = tiles().length;
    c.textContent = SEL.size ? `${ fa(SEL.size) } انتخاب‌شده` : shown < total ? `${ fa(shown) } از ${ fa(total) } تصویر` : `${ fa(total) } تصویر`;
  }
};
export function galleryFilter() {
  if (!S.P || !$('#ggrid'))
    return;
  const q = S.q.trim().toLowerCase(), byId = new Map(tiles().map(t => [t.m.id, t]));
  $$('#ggrid .tile[data-id]').forEach(el => {
    const t = byId.get(el.dataset.id);
    el.hidden = !(t && hit(t, q));
  });
  $$('#ggrid .gsec').forEach(sec => {
    const sc = S.P.scenes.find(s => s.id === sec.dataset.scene);
    const titleHit = q && sc && sc.title.toLowerCase().includes(q);
    const hasVis = sec.querySelectorAll('.tile[data-id]:not([hidden])').length > 0;
    sec.hidden = !(hasVis || titleHit || (!q && S.filter === 'all'));
  });
  const gq = $('#gq');
  if (gq && gq.value !== S.q)
    gq.value = S.q;
  const gf = $('#gFilter');
  if (gf)
    gf.classList.toggle('has', S.filter !== 'all');
  count();
}
export const galleryRefresh = () => {
  if (S.P)
    paint();
};
/* ---- where a drop lands: just before / after a tile (in reading order, so "before" is on the right in a right-to-left page) */
const ordered = () => $$('#ggrid .tile[data-id]');
function target(x, y) {
  const el = document.elementFromPoint(x, y);
  const dz = el && el.closest('#ggrid [data-gdrop]');
  if (dz && dz.dataset.gdrop !== 'scene-00')
    return { scene: dz.dataset.gdrop, el: dz };
  let tt = el && el.closest('#ggrid .tile[data-id]');
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
  $$('#ggrid [data-gdrop].dragover').forEach(e => e.classList.remove('dragover'));
  if (!ln)
    return;
  if (!d) {
    ln.hidden = true;
    return;
  }
  if (d.scene) {
    ln.hidden = true;
    d.el.classList.add('dragover');
    return;
  }
  ln.hidden = false;
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
  const pos = d.drop.scene ?
    { to_end_of_scene: d.drop.scene } :
    (d.drop.before ? { before: d.drop.id } : { after: d.drop.id });
  try {
    if (d.kind === 'tile') {
      if (!d.drop.scene && d.ids.includes(d.drop.id))
        return;
      await api('/api/move', {
        ids: d.ids,
        ...pos
      });
      SEL.clear();
    } else
      await api('/api/addimage', {
        ...d.drop.scene ? { scene: d.drop.scene } : pos,
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
    if ((e.pointerType !== 'touch' || REORD) && Math.hypot(e.clientX - D.x, e.clientY - D.y) > 6)
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
  if (pos.scene === 'scene-00')
    return;
  const un = S.P.unplaced || [], all = tiles(), dlg = document.createElement('dialog');
  dlg.className = 'dlg gpick';
  dlg.innerHTML = `<h3>افزودن تصویر</h3><button type="button" class="opt" data-pk="new"><span>جای خالی تازه</span><span class="c">شمارهٔ بعدی</span></button>${ un.length ? '<h4>جا نگرفته‌ها</h4>' + un.map(u => `<button type="button" class="opt" data-pk="${ u.id }"><span><bdi dir="ltr">${ u.id }</bdi></span><span class="c">${ u.src ? 'فایل دارد' : 'فقط پرامپت' }</span></button>`).join('') : '' }<h4>جابه‌جایی یک تصویر به اینجا</h4><div class="pkgrid" id="pkGrid">${ all.map(t => {
    const is00 = t.sc.id === 'scene-00';
    return `<button type="button" class="pktile" data-pk="move" data-id="${ t.m.id }" ${ is00 ? 'disabled title="تصویر تامبنیل جابه‌جا نمی‌شود"' : `title="${ t.m.id } · صحنه ${ fa(sceneNo(t.sc)) }"` } aria-label="${ t.m.id }">${ t.m.src ? `<img src="${ esc(t.m.src) }" alt="" loading="lazy">` : `<span class="ph">${ t.m.id }</span>` }<span class="pid" dir="ltr">${ t.m.id }</span></button>`;
  }).join('') }</div><div class="btns"><button type="button" class="quiet" data-pk="">انصراف</button></div>`;
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
        id = b.dataset.id;
        if (!id)
          return;
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
  const g = $('#gallery'), q = $('#gq');
  $('#gSearch').addEventListener('click', () => {
    q.hidden = !q.hidden;
    $('#gSearch').setAttribute('aria-expanded', String(!q.hidden));
    if (q.hidden) {
      q.value = '';
      S.q = '';
      if ($('#q'))
        $('#q').value = '';
      filt(true);
      drawerRefresh();
    } else {
      q.value = S.q;
      q.focus();
    }
  });
  q.addEventListener('input', () => {
    S.q = q.value.trim();
    if ($('#q'))
      $('#q').value = S.q;
    filt(true);
    drawerRefresh();
  });
  q.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      $('#gSearch').click();
    }
  });
  $('#gFilter').addEventListener('click', () => openDrawer('filter'));
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
    if (e.pointerType === 'touch' && !REORD)
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
    const iz = e.target.closest('[data-inbzoom]');
    if (iz)
      return lightbox(iz.dataset.inbzoom, iz.dataset.name);
    const b = e.target.closest('button');
    if (b && b.id === 'gMove') {
      REORD = !REORD;
      b.setAttribute('aria-pressed', REORD);
      g.classList.toggle('reorder', REORD);
      return;
    }
    if (b && b.id === 'gSel') {
      PICK = !PICK;
      b.setAttribute('aria-pressed', PICK);
      g.classList.toggle('picking', PICK);
      return;
    }
    if (b && b.dataset.gbatch)
      return copyBatch(b.dataset.gbatch);
    if (b && b.dataset.gbulk) {
      const k = b.dataset.gbulk;
      if (k === 'clear') {
        SEL.clear();
        return paint();
      }
      try {
        const ids = [...SEL];
        if (k === 'redo')
          await api('/api/imagebulk', { ids, status: 'redo' });
        else if (k === 'unredo' || k === 'clear_redo')
          await api('/api/imagebulk', { ids, status: '' });
        else if (k === 'on' || k === 'back')
          await api('/api/imagebulk', { ids, off: false });
        else if (k === 'off')
          await api('/api/imagebulk', { ids, off: true });
        SEL.clear();
        toast('تغییر گروهی انجام شد');
      } catch (er) {
        fail(er);
      }
      return reload();
    }
    if (b && b.dataset.gadd !== undefined)
      return openPicker(b.dataset.gdrop ? { scene: b.dataset.gdrop } : endPos());
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
  g.addEventListener('keydown', async e => {
    if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      e.preventDefault();
      const focused = document.activeElement?.closest('#ggrid .tile[data-id]');
      const id = focused?.dataset.id || (SEL.size === 1 ? [...SEL][0] : null);
      if (!id || id === 'IMG000')
        return;
      const step = rtl() ? (e.key === 'ArrowLeft' ? 1 : -1) : (e.key === 'ArrowLeft' ? -1 : 1);
      const body = moveTarget(id, step);
      if (!body)
        return;
      const ids = SEL.has(id) ? ordered().map(t => t.dataset.id).filter(i => SEL.has(i)) : [id];
      try {
        await api('/api/move', { ...body, ids });
        await reload();
        $(`#ggrid .tile[data-id="${ id }"]`)?.focus();
      } catch (err) {
        fail(err);
      }
      return;
    }
    const t = e.target.closest('.tile[data-id]');
    if (t && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      location.hash = t.dataset.id;
    }
  });
}
