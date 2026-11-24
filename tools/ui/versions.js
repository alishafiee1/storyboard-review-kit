import {
  $,
  api,
  fa,
  fail
} from './core.js';
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
import { openDrawer } from './drawer.js';
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
/* approve = choose the shown version (the same as stopping on it); once more = take the approval back */
async function approve() {
  const c = curImg();
  if (!c)
    return;
  const {m, f} = c;
  try {
    if (m.versions.length) {
      if (m.status === 'ok') {
        await api('/api/image', {
          id: m.id,
          pick: '',
          status: ''
        });
        m.picked = '';
        m.status = '';
        paint(f, m);
      } else
        await pickVersion(f, m, m.vi);
    } else {
      const v = m.status === 'ok' ? '' : 'ok';
      await api('/api/image', {
        id: m.id,
        status: v
      });
      m.status = v;
      paint(f, m);
    }
  } catch (e) {
    fail(e);
  }
}
export async function archiveShown() {
  const c = curImg();
  if (!c || !c.m.versions[c.m.vi])
    return;
  await api('/api/archive', {
    kind: 'image',
    id: c.m.id,
    name: c.m.versions[c.m.vi].name
  });
  await reload();
}
/* ---------- the image «⋯» popover */
const closeMore = () => {
  $('#morePop').hidden = true;
  $('#more').setAttribute('aria-expanded', 'false');
};
const item = (attr, text, extra = '') => `<button type="button" role="menuitem" ${ attr } ${ extra }>${ text }</button>`;
function moreHtml() {
  const c = curImg(), sid = sceneId(), sc = sceneObj(sid), out = [];
  if (c) {
    const {m} = c, vis = S.P.scenes.filter(s => !s.off), prev = vis[vis.indexOf(sc) - 1];
    const first = sc.blocks.flatMap(b => b.images)[0]?.id === m.id;
    if (sid !== 'scene-00') {
      if (moveTarget(m.id, -1))
        out.push(item('data-imv="-1"', 'یک تصویر بالاتر'));
      if (moveTarget(m.id, 1))
        out.push(item('data-imv="1"', 'یک تصویر پایین‌تر'));
      out.push(item('data-iadd="1"', 'تصویر بعد از این'));
      if (!first)
        out.push(item('data-isc="1"', 'شروع صحنهٔ جدید از اینجا'));
      if (first && prev && prev.id !== 'scene-00')
        out.push(item('data-imerge="1"', 'ادغام با صحنهٔ قبل', 'title="عنوان این صحنه برداشته می‌شه و تصویرهاش می‌رن توی صحنهٔ قبل"'));
    }
    out.push(item('data-ioff="1"', m.off ? 'برگردان تصویر' : 'کنار بگذار', 'title="فایلش پاک نمی‌شه"'));
    if (m.versions.length)
      out.push(item('data-iarch="1"', 'نسخهٔ نمایش‌داده‌شده به آرشیو', 'title="فایل پاک نمی‌شه"'));
    if (m.archived.length)
      out.push(item('data-irest="1"', `نسخه‌های آرشیو (${ fa(m.archived.length) })`));
  }
  if (sid !== 'scene-00') {
    if (out.length)
      out.push('<hr>');
    out.push(item('data-smv="-1"', 'یک صحنه بالاتر'), item('data-smv="1"', 'یک صحنه پایین‌تر'), item('data-soff="1"', 'کنار گذاشتن این صحنه', 'title="متن و فایل‌ها پاک نمی‌شن"'), item(`data-addimg="${ sid }"`, 'تصویر جدید در این صحنه'), item(`data-addscene="${ sid }"`, 'صحنهٔ جدید بعد از این'));
  } else
    out.push(item(`data-addimg="${ sid }"`, 'تصویر جدید در این صحنه'));
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
  if (d.iadd)
    return run(async () => {
      const r = await api('/api/addimage', { after: m.id });
      await reload();
      goImage(r.id);
    });
  if (d.isc)
    return run(async () => {
      const title = prompt('عنوان صحنهٔ جدید که از این تصویر شروع می‌شه؟', 'صحنهٔ جدید');
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
      if (!confirm('این صحنه با صحنهٔ قبلش ادغام بشه؟\nعنوان این صحنه برداشته می‌شه و تصویرهاش می‌رن توی صحنهٔ قبل' + (info ? '؛ محیط و ادیتِ صحنه هم حذف می‌شه' : '') + '.\nبا «برگردان» می‌شه برگشت.'))
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
  if (d.iarch)
    return run(archiveShown);
  if (d.irest)
    return openDrawer('vers');
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
      if (!confirm('این صحنه کنار گذاشته بشه؟\nمتن، عکس‌ها و صداهاش پاک نمی‌شن؛ فقط از ترتیب نهایی بیرون می‌ره و هوش مصنوعی نادیده‌اش می‌گیره.'))
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
      const title = prompt('عنوان صحنهٔ جدید؟', 'صحنهٔ جدید');
      if (title === null)
        return;
      const n = prompt('چند جای خالی برای تصویر داشته باشه؟ (۰ تا ۱۲)', '1');
      if (n === null)
        return;
      const r = await api('/api/addscene', {
        after: d.addscene,
        title,
        images: +n || 0
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
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-vn]');
    if (b)
      browse(+b.dataset.vn);
    if (e.target.closest('[data-approve]'))
      approve();
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
    const url = (name === 'default' ? `audio/${ lg }/${ iid }.mp3` : `audio/${ lg }/${ iid }.${ name }.mp3`) + '?v=' + Date.now();
    it.audio[lg] = url;
    const play = b.parentElement.querySelector(`.ab[data-lg="${ lg }"]`);
    play.dataset.src = url;
    b.textContent = `‹${ fa(i + 1) }/${ fa(v.names.length) }›`;
    b.title = `${ lg === 'fa' ? 'صدای فارسی' : 'English voice' }: ${ name } · کلیک = صدای بعدی (همونی که آخر می‌ذاری، صدای نهایی می‌شه)`;
    stopLine();
    play.click();
  });
}
