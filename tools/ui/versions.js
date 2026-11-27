import {
  $,
  api,
  askConfirm,
  askNewScene,
  askPrompt,
  esc,
  fa,
  fail,
  toast
} from './core.js';
import { ic } from './icons.js';
import {
  filt,
  reload,
  stats
} from './panels.js';
import { S } from './state.js';
import {
  moveTarget,
  stopLine,
  vmetaHtml
} from './render.js';
import {
  blockOf,
  chrome,
  curImg,
  show
} from './player.js';
import { openPicker } from './gallery.js';
/* Picture versions, the image «⋯» menu, scene management and voice variants. Everything is written to story.txt; no file is renamed or deleted. */
/* ---------- where we are */
const sceneId = () => $('#b' + S.cur).closest('section[data-scene]').dataset.scene;
const sceneObj = sid => S.P.scenes.find(x => x.id === sid);
export const goImage = id => {
  const i = blockOf(id);
  if (i >= 0)
    show(i);
};
const goScene = sid => {
  const el = document.querySelector(`section[data-scene="${ sid }"] .blk`);
  if (el)
    show(+el.id.slice(1));
};
/* ---------- versions: the one you stop on is the chosen (approved) one */
function paint(f, m) {
  const v = m.versions[m.vi], im = f.querySelector('img');
  if (v) {
    m.src = v.src;
    if (im)
      im.src = v.src;
  }
  f.dataset.m = m.status;
  f.querySelector('.vmeta').innerHTML = vmetaHtml(m);
  stats();
  filt();
  chrome();
}
export async function pickVersion(f, m, ni) {
  const vid = m.versions[ni].id;
  await api('/api/image', {
    id: m.id,
    pick: vid
  });
  m.vi = ni;
  m.picked = vid;
  m.status = 'ok';
  paint(f, m);
}
async function browse(d) {
  const c = curImg();
  if (!c || c.m.versions.length < 2)
    return;
  const n = c.m.versions.length;
  try {
    await pickVersion(c.f, c.m, (c.m.vi + d + n) % n);
  } catch (e) {
    fail(e);
  }
}
export const stepVersion = d => browse(d);
export async function archiveShown() {
  const c = curImg();
  if (!c || !c.m.versions[c.m.vi])
    return;
  const id = c.m.id, name = c.m.versions[c.m.vi].name;
  await api('/api/archive', {
    kind: 'image',
    id,
    name
  });
  await reload();
  toastAct('رفت توی آرشیو', 'بازگردانی', async () => {
    try {
      await api('/api/restore', {
        kind: 'image',
        id,
        name
      });
      await reload();
      await showRestored(id, name);
    } catch (e) {
      fail(e);
    }
  });
}
/* a brought-back version is shown at once (and, as always, the version you stop on is the chosen one); before, the old pick stayed on screen and it looked as if nothing came back */
export async function showRestored(id, name) {
  const m = S.BL.flatMap(b => b.images).find(x => x.id === id), f = document.querySelector(`figure.shot[data-id="${ id }"]`);
  if (!m || !f)
    return;
  const i = m.versions.findIndex(v => v.name === name || (v.files || []).some(x => x.split('/').pop() === name));
  if (i >= 0)
    await pickVersion(f, m, i);
}
/* a toast with one button (the archive says «back» for a few seconds; the popup of the archive is always one click away) */
let TOAST_ACT = 0;
function toastAct(msg, label, fn) {
  const t = $('#toast'), b = document.createElement('button');
  t.textContent = msg + ' ';
  b.type = 'button';
  b.className = 'quiet';
  b.textContent = label;
  b.onclick = () => {
    t.hidden = true;
    fn();
  };
  t.append(b);
  t.hidden = false;
  clearTimeout(TOAST_ACT);
  TOAST_ACT = setTimeout(() => t.hidden = true, 7000);
}
/* ---------- the archive of the shown picture: a grid like the gallery picker; a click opens one with ‹ › and «bring back» */
export function openArchive() {
  const c = curImg();
  if (!c)
    return;
  const id = c.m.id, dlg = document.createElement('dialog');
  let at = -1;
  const list = () => (curImgById(id) || { archived: [] }).archived;
  const draw = () => {
    const a = list();
    if (at >= a.length)
      at = a.length - 1;
    if (!a.length) {
      dlg.innerHTML = `<h3>آرشیو <bdi dir="ltr">${ id }</bdi></h3><p class="muted">آرشیو این تصویر خالیه. با دکمهٔ «آرشیو» زیر تصویر، نسخهٔ جاری می‌ره اینجا و هیچ فایلی پاک نمی‌شه.</p><div class="btns"><button type="button" class="outline" data-ar="close">بستن</button></div>`;
      return;
    }
    if (at < 0) {
      dlg.innerHTML = `<h3>آرشیو <bdi dir="ltr">${ id }</bdi> <small class="muted">${ fa(a.length) } مورد</small></h3><div class="agrid">${ a.map((x, i) => `<button type="button" class="atile" data-ar="open" data-i="${ i }" aria-label="نسخهٔ آرشیو ${ fa(i + 1) }"><img src="${ esc(x.src) }" alt="" loading="lazy"></button>`).join('') }</div><p class="muted">روی یکی کلیک کن تا بزرگ ببینیش و برش‌گردونی.</p><div class="btns"><button type="button" class="outline" data-ar="close">بستن</button></div>`;
      return;
    }
    const x = a[at];
    dlg.innerHTML = `<h3>آرشیو <bdi dir="ltr">${ id }</bdi> <small class="muted">${ fa(at + 1) } / ${ fa(a.length) }</small></h3><div class="aview">${ a.length > 1 ? `<button type="button" class="va l" data-ar="step" data-d="-1" aria-label="قبلی">${ ic('chevL') }</button><button type="button" class="va r" data-ar="step" data-d="1" aria-label="بعدی">${ ic('chevR') }</button>` : '' }<img src="${ esc(x.src) }" alt=""></div><p class="muted"><bdi dir="ltr">${ esc(x.name) }</bdi></p><div class="btns"><button type="button" class="quiet" data-ar="list">برگشت به فهرست</button><button type="button" class="outline" data-ar="restore">بازگردانی به نسخه‌ها</button></div>`;
  };
  dlg.className = 'dlg archdlg';
  document.body.appendChild(dlg);
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('click', async e => {
    const b = e.target.closest('[data-ar]');
    if (!b)
      return;
    const k = b.dataset.ar, a = list();
    if (k === 'close')
      dlg.close();
    else if (k === 'open') {
      at = +b.dataset.i;
      draw();
    } else if (k === 'list') {
      at = -1;
      draw();
    } else if (k === 'step') {
      at = (at + +b.dataset.d + a.length) % a.length;
      draw();
    } else if (k === 'restore' && a[at]) {
      try {
        await api('/api/restore', {
          kind: 'image',
          id,
          name: a[at].name
        });
        await reload();
        await showRestored(id, a[at].name);
        at = -1;
        draw();
        toast('برگشت به نسخه‌ها و نشونش داده شد');
      } catch (er) {
        fail(er);
      }
    }
  });
  draw();
  dlg.showModal();
}
const curImgById = id => S.BL.flatMap(b => b.images).find(x => x.id === id);
/* ---------- the image «⋯» popover */
const closeMore = () => {
  $('#morePop').hidden = true;
  $('#more').setAttribute('aria-expanded', 'false');
};
const item = (attr, text, extra = '', icon = '') => `<button type="button" role="menuitem" ${ attr } ${ extra }>${ icon ? ic(icon) : '' }<span>${ text }</span></button>`;
function moreHtml() {
  const c = curImg(), sid = sceneId(), sc = sceneObj(sid), out = [];
  if (c) {
    const {m} = c, vis = S.P.scenes.filter(s => !s.off), prev = vis[vis.indexOf(sc) - 1];
    const first = sc.blocks.flatMap(b => b.images)[0]?.id === m.id;
    out.push(`<div class="mhead">تصویر <bdi dir="ltr">${ m.id }</bdi></div>`);
    if (sid !== 'scene-00') {
      if (moveTarget(m.id, -1))
        out.push(item('data-imv="-1"', 'یک تصویر بالاتر', '', 'up'));
      if (moveTarget(m.id, 1))
        out.push(item('data-imv="1"', 'یک تصویر پایین‌تر', '', 'down'));
      out.push(item('data-iadd="1"', 'تصویر جدید بعد از این', '', 'plus'));
      out.push(item('data-ipick="1"', 'انتخاب یا جابه‌جایی به بعد…', '', 'grid'));
      if (!first)
        out.push(item('data-isc="1"', 'شروع صحنهٔ جدید از اینجا', '', 'list'));
      if (first && prev && prev.id !== 'scene-00')
        out.push(item('data-imerge="1"', 'ادغام با صحنهٔ قبل', 'title="عنوان این صحنه برداشته می‌شه و تصویرهاش می‌رن توی صحنهٔ قبل"', 'undo'));
    }
    out.push(item('data-iredo="1"', m.status === 'redo' ? 'برداشتن علامت بازسازی' : 'نیاز به بازسازی', '', 'redo'));
    out.push(item('data-ioff="1"', m.off ? 'برگردان تصویر' : 'کنار بگذار', 'title="فایلش پاک نمی‌شه"', 'tray'));
    if (m.versions.length)
      out.push(item('data-iarch="1"', 'نسخهٔ فعلی به آرشیو', 'title="فایل پاک نمی‌شه"', 'archive'));
    if (m.archived.length)
      out.push(item('data-irest="1"', `نسخه‌های آرشیو (${ fa(m.archived.length) })`, '', 'restore'));
  }
  if (sid !== 'scene-00') {
    if (out.length)
      out.push('<hr>');
    out.push('<div class="mhead">این صحنه</div>');
    out.push(item('data-smv="-1"', 'یک صحنه بالاتر', '', 'up'), item('data-smv="1"', 'یک صحنه پایین‌تر', '', 'down'), item(`data-addimg="${ sid }"`, 'تصویر جدید در انتهای صحنه', '', 'plus'), item(`data-addscene="${ sid }"`, 'صحنهٔ جدید بعد از این', '', 'list'), item('data-soff="1"', 'کنار گذاشتن این صحنه', 'title="متن و فایل‌ها پاک نمی‌شن"', 'tray'));
  }
  return out.join('');
}
function openMore() {
  const pop = $('#morePop');
  pop.innerHTML = moreHtml();
  pop.hidden = false;
  $('#more').setAttribute('aria-expanded', 'true');
}
const run = async fn => {
  try {
    await fn();
  } catch (e) {
    fail(e);
  }
};
async function onItem(b) {
  const c = curImg(), m = c && c.m, sid = sceneId(), d = b.dataset;
  if (d.imv)
    return run(async () => {
      const body = moveTarget(m.id, +d.imv);
      if (body)
        await api('/api/move', body);
      await reload();
    });
  if (d.ipick)
    return openPicker({ after: m.id }, true);
  if (d.iadd)
    return run(async () => {
      const r = await api('/api/addimage', { after: m.id });
      await reload();
      goImage(r.id);
    });
  if (d.isc)
    return run(async () => {
      const title = await askPrompt('عنوان صحنهٔ جدید که از این تصویر شروع می‌شه؟', 'صحنهٔ جدید');
      if (title === null)
        return;
      await api('/api/scenemark', {
        op: 'insert',
        before: m.id,
        title
      });
      await reload();
    });
  if (d.imerge)
    return run(async () => {
      const sc = sceneObj(sid), info = sc.env.length || sc.fx || sc.model;
      if (!(await askConfirm('این صحنه با صحنهٔ قبلش ادغام بشه؟\nعنوان این صحنه برداشته می‌شه و تصویرهاش می‌رن توی صحنهٔ قبل' + (info ? '؛ محیط و ادیتِ صحنه هم حذف می‌شه' : '') + '.\nبا «برگردان» می‌شه برگشت.', 'ادغام')))
        return;
      await api('/api/scenemark', {
        op: 'remove',
        scene: sc.id,
        force: !!info
      });
      await reload();
    });
  if (d.ioff !== undefined)
    return run(async () => {
      await api('/api/image', {
        id: m.id,
        off: !m.off
      });
      await reload();
    });
  if (d.iredo !== undefined)
    return run(async () => {
      await api('/api/image', {
        id: m.id,
        status: m.status === 'redo' ? '' : 'redo'
      });
      await reload();
    });
  if (d.iarch)
    return run(archiveShown);
  if (d.irest)
    return openArchive();
  if (d.smv)
    return run(async () => {
      await api('/api/scenemove', {
        scene: sid,
        step: +d.smv
      });
      await reload();
    });
  if (d.soff !== undefined)
    return run(async () => {
      if (!(await askConfirm('این صحنه کنار گذاشته بشه؟\nمتن، عکس‌ها و صداهاش پاک نمی‌شن؛ فقط از ترتیب نهایی بیرون می‌ره و هوش مصنوعی نادیده‌اش می‌گیره.', 'کنار بگذار')))
        return;
      await api('/api/sceneoff', {
        scene: sid,
        off: true
      });
      await reload();
    });
  if (d.addimg)
    return run(async () => {
      const r = await api('/api/addimage', { scene: d.addimg });
      await reload();
      goImage(r.id);
    });
  if (d.addscene)
    return run(async () => {
      const res = await askNewScene();
      if (!res)
        return;
      const r = await api('/api/addscene', {
        after: d.addscene,
        title: res.title,
        images: res.images
      });
      await reload();
      goScene(r.scene);
    });
}
/* bring a scene that was set aside back (from the scene list in the drawer) */
export const bringBack = sid => run(async () => {
  await api('/api/sceneoff', {
    scene: sid,
    off: false
  });
  await reload();
  goScene(sid);
});
export function boot_versions() {
  $('#bArch').onclick = () => run(archiveShown);
  $('#bArchList').onclick = openArchive;
  $('#bRedo').onclick = () => run(async () => {
    const c = curImg();
    if (!c)
      return;
    await api('/api/image', {
      id: c.m.id,
      status: c.m.status === 'redo' ? '' : 'redo'
    });
    await reload();
  });
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-vn]');
    if (b)
      browse(+b.dataset.vn);
    const o = e.target.closest('[data-ioff]');
    if (o && !o.closest('#morePop'))
      onItem(o);
  });
  $('#more').onclick = () => $('#morePop').hidden ? openMore() : closeMore();
  $('#morePop').addEventListener('click', e => {
    const b = e.target.closest('[role=menuitem]');
    if (!b)
      return;
    closeMore();
    onItem(b);
  });
  document.addEventListener('pointerdown', e => {
    if (!$('#morePop').hidden && !e.target.closest('#morePop,#more'))
      closeMore();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !$('#morePop').hidden) {
      closeMore();
      $('#more').focus();
    }
  });
  /* the small ‹۱/۲› next to a voice button: next voice of that line; the one you stop on becomes the chosen (final) voice */
  document.addEventListener('click', async e => {
    const b = e.target.closest('.vv');
    if (!b)
      return;
    const lg = b.dataset.vv, iid = b.dataset.iid, it = S.BL.flatMap(x => x.items).find(x => x.id === iid);
    if (!it)
      return;
    const v = it.audio_v[lg], i = (v.names.indexOf(v.chosen) + 1) % v.names.length, name = v.names[i];
    try {
      await api('/api/voicepick', {
        scene: b.dataset.sc,
        id: iid,
        lang: lg,
        variant: name
      });
    } catch (err) {
      return fail(err);
    }
    v.chosen = name;
    const base = (v.srcs && v.srcs[name]) || (name === 'default' ? `audio/${ lg }/${ iid }.mp3` : /^[0-9a-f]{8}$/.test(name) ? `audio/${ lg }/${ iid }_${ name }.mp3` : `audio/${ lg }/${ iid }.${ name }.mp3`);
    const url = base + '?v=' + Date.now();
    it.audio[lg] = url;
    const play = b.parentElement.querySelector(`.ab[data-lg="${ lg }"]`);
    play.dataset.src = url;
    b.textContent = `‹${ fa(i + 1) }/${ fa(v.names.length) }›`;
    b.title = `${ lg === 'fa' ? 'صدای فارسی' : 'English voice' }: ${ name } · کلیک = صدای بعدی (همونی که آخر می‌ذاری، صدای نهایی می‌شه)`;
    stopLine();
    play.click();
  });
}
