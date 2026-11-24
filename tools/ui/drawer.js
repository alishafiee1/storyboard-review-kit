import { S } from './state.js';
import {
  $,
  $$,
  api,
  audio,
  copyText,
  esc,
  fa,
  fail,
  toast
} from './core.js';
import { ic } from './icons.js';
import {
  filt,
  reload
} from './panels.js';
import {
  curImg,
  go
} from './player.js';
import {
  bringBack,
  pickVersion
} from './versions.js';
import { sceneNo } from './render.js';
/* The paper drawer (menu): scene list, filter and search, speed, subtitles, voices, references, versions and archive, undo, batch prompts, inbox.
   Each row of the menu opens a panel inside the drawer; ‹ goes back. */
const PANELS = {
  scenes: '#pScenes',
  filter: '#pFilter',
  speed: '#pSpeed',
  subs: '#pSubs',
  spk: '#spk',
  refs: '#refs',
  vers: '#pVers',
  undo: '#pUndo',
  batch: '#pBatch',
  inbox: '#pInbox'
};
const ROWS = [
  [
    'scenes',
    'list',
    'فهرست صحنه‌ها'
  ],
  [
    'filter',
    'sliders',
    'فیلتر و جست‌وجو'
  ],
  [
    'speed',
    'speed',
    'سرعت پخش'
  ],
  [
    'subs',
    'subs',
    'زیرنویس'
  ],
  [
    'spk',
    'mic',
    'صداها و گوینده‌ها'
  ],
  [
    'refs',
    'file',
    'رفرنس‌ها'
  ],
  [
    'vers',
    'calendar',
    'نسخه‌ها و آرشیو'
  ],
  [
    'undo',
    'undo',
    'برگردان آخرین تغییر'
  ],
  [
    'batch',
    'batch',
    'کپی پرامپت‌های دسته'
  ],
  [
    'inbox',
    'inbox',
    'ورودی‌ها و inbox'
  ]
];
const FILTERS = [
  [
    'all',
    'همه'
  ],
  [
    'missing',
    'ساخته‌نشده'
  ],
  [
    'none',
    'بدون علامت'
  ],
  [
    'ok',
    'تأیید‌شده'
  ],
  [
    'redo',
    'بازسازی'
  ],
  [
    'note',
    'دارای یادداشت'
  ],
  [
    'stale',
    'کهنه'
  ]
];
const SPEEDS = [
  0.9,
  1,
  1.15,
  1.3
];
const HLABEL = {
  addimage: 'افزودن تصویر',
  addscene: 'افزودن صحنه',
  sceneoff: 'کنار گذاشتن یا برگرداندن صحنه',
  scenemove: 'جابه‌جایی صحنه',
  scenemark: 'ویرایش نشانهٔ صحنه',
  move: 'جابه‌جایی تصویر',
  add: 'افزودن خط',
  delete: 'حذف خط'
};
const speedText = v => fa(String(v).replace('.', '٫')) + '×';
let PANEL = null;
export const drawerOpen = () => document.body.classList.contains('dopen');
export function openDrawer(panel) {
  document.body.classList.add('dopen');
  $('#drawer').setAttribute('aria-hidden', 'false');
  $('#scrim').hidden = false;
  $('#menuBtn').setAttribute('aria-expanded', 'true');
  showPanel(panel || null);
}
export function closeDrawer() {
  if (!drawerOpen())
    return;
  document.body.classList.remove('dopen');
  $('#drawer').setAttribute('aria-hidden', 'true');
  $('#scrim').hidden = true;
  $('#menuBtn').setAttribute('aria-expanded', 'false');
  $('#menuBtn').focus();
}
function showPanel(name) {
  PANEL = name;
  $$('.dpanel').forEach(p => p.hidden = true);
  $('#dmenu').hidden = !!name;
  $('#dback').hidden = !name;
  const p = name && $(PANELS[name]);
  $('#dtitle').textContent = p ? p.dataset.title : 'منو';
  $('#drawer').classList.toggle('wide', !!(p && p.classList.contains('wide')));
  if (p) {
    p.hidden = false;
    build(name);
  }
  const f = (p || $('#dmenu')).querySelector('button, input, select');
  if (f)
    f.focus({ preventScroll: true });
}
const imgs = () => S.BL.flatMap(b => b.images);
/* ---- scene list */
function buildScenes() {
  const here = S.BL[S.cur] && $('#b' + S.cur).closest('section[data-scene]').dataset.scene;
  const on = S.P.scenes.filter(s => !s.off).map(sc => {
    const el = document.querySelector(`section[data-scene="${ sc.id }"] .blk`), n = sc.blocks.reduce((a, b) => a + b.images.length, 0);
    return `<button type="button" class="srow${ sc.id === here ? ' sel' : '' }" data-go="${ el ? el.id.slice(1) : 0 }"><span class="n">${ sc.id === 'scene-00' ? ic('image') : fa(sceneNo(sc)) }</span><span class="t">${ esc(sc.title) }</span><span class="c">${ fa(n) } تصویر</span></button>`;
  });
  const off = S.P.scenes.filter(s => s.off).map(sc => `<div class="srow off"><span class="n">–</span><span class="t">${ esc(sc.title) }</span><span class="c">کنار گذاشته شده</span><button type="button" class="quiet sm" data-son="${ sc.id }">برگردان</button></div>`);
  $('#slist').innerHTML = on.join('') + (off.length ? '<h4>کنار گذاشته‌شده‌ها</h4>' + off.join('') : '');
}
/* ---- filter and search */
function paintFilter() {
  const all = imgs(), count = k => k === 'all' ? all.length : all.filter(m => k === 'missing' ? !m.src : k === 'none' ? !m.status : k === 'note' ? !!m.note : k === 'stale' ? m.stale : m.status === k).length;
  $('#fopts').innerHTML = FILTERS.map(([k, t]) => `<button type="button" class="opt${ S.filter === k ? ' sel' : '' }" data-filter="${ k }" aria-pressed="${ S.filter === k }"><span>${ t }</span><span class="c">${ fa(count(k)) }</span></button>`).join('');
}
/* ---- speed */
function paintSpeed() {
  $('#pSpeed').innerHTML = SPEEDS.map(v => `<button type="button" class="opt${ S.speed === v ? ' sel' : '' }" data-speed="${ v }" aria-pressed="${ S.speed === v }"><span>${ speedText(v) }</span></button>`).join('');
}
/* ---- versions and archive of the picture on show */
function buildVers() {
  const c = curImg(), P = $('#pVers');
  if (!c) {
    P.innerHTML = '<p class="muted">این بخش از متن به تصویری وصل نیست.</p>';
    return;
  }
  const {m} = c;
  P.innerHTML = `<p class="muted"><bdi dir="ltr">${ m.id }</bdi> · ایستادن روی یک نسخه یعنی تأیید آن؛ هیچ فایلی پاک نمی‌شه.</p>` + (m.versions.length ? m.versions.map((v, i) => `<div class="vrow2${ i === m.vi ? ' sel' : '' }"><img class="thumb" src="${ esc(v.src) }" alt=""><span class="vt">نسخهٔ ${ fa(i + 1) }${ v.q ? ' · <bdi dir="ltr">' + esc(v.q) + '</bdi>' : '' }${ m.picked && v.id === m.picked ? ' · تأیید شده' : '' }</span><button type="button" class="quiet sm" data-vpick="${ i }">نمایش و تأیید</button><button type="button" class="quiet sm" data-varch="${ esc(v.name) }" title="فایل پاک نمی‌شه">آرشیو</button></div>`).join('') : '<p class="muted">هنوز تصویری ساخته نشده.</p>') + (m.archived.length ? '<h4>آرشیو</h4>' + m.archived.map(a => `<div class="vrow2"><img class="thumb" src="${ esc(a.src) }" alt=""><span class="vt"><bdi dir="ltr">${ esc(a.name) }</bdi></span><button type="button" class="quiet sm" data-irestore="${ esc(a.name) }">برگردان</button></div>`).join('') : '');
}
/* ---- undo */
function buildUndo() {
  const h = [...S.P.history || []].reverse().slice(0, 10), t = x => `${ x.slice(9, 11) }:${ x.slice(11, 13) }:${ x.slice(13, 15) }`;
  $('#pUndo').innerHTML = h.length ? `<p class="muted">آخرین تغییرهای ساختاری (افزودن، حذف، جابه‌جایی). «برگردان» فایل را بایت‌به‌بایت به حالت پیش از آخرین تغییر برمی‌گردونه.</p><ol class="hist">${ h.map((x, i) => `<li${ i ? '' : ' class="sel"' }><span>${ esc(HLABEL[x.label] || x.label) }</span><bdi dir="ltr" class="c">${ fa(t(x.time)) }</bdi></li>`).join('') }</ol><button type="button" class="outline" data-undo="1">${ ic('undo') }برگردان آخرین تغییر</button>` : '<p class="muted">چیزی برای برگرداندن نیست.</p>';
}
async function undo(force) {
  const h = S.P.history || [];
  if (!h.length)
    return;
  try {
    const r = await api('/api/undo', {
      id: h[h.length - 1].id,
      force
    });
    toast('برگشت: ' + (HLABEL[r.undone.label] || r.undone.label));
    await reload();
  } catch (e) {
    if (!force && /force/.test(e.message)) {
      if (confirm(e.message + '\n\nباز هم برگردد؟'))
        return undo(true);
    } else {
      fail(e);
      await reload();
    }
  }
}
/* ---- batch prompts */
function buildBatch() {
  const by = new Map();
  imgs().forEach(m => {
    if (m.batch)
      by.set(m.batch, (by.get(m.batch) || 0) + 1);
  });
  $('#pBatch').innerHTML = by.size ? `<p class="muted">پرامپت‌های یک دسته (۱۰ تصویر) با خط رفرنس و اسم خروجی، یک‌جا کپی می‌شن.</p>` + [...by].sort().map(([b, n]) => `<button type="button" class="opt" data-batch="${ b }"><span>دستهٔ <bdi dir="ltr">${ b }</bdi></span><span class="c">${ fa(n) } تصویر</span></button>`).join('') + '<div id="bmsg" class="muted" role="status"></div>' : '<p class="muted">تصویری توی پروژه نیست.</p>';
}
export async function copyBatch(b) {
  try {
    const j = await (await fetch('/api/batch?b=' + encodeURIComponent(b))).json();
    if (j.error)
      throw new Error(j.error);
    if (!j.text) {
      toast('این دسته پرامپتی نداره');
      return;
    }
    await copyText(j.text);
    toast(`${ fa(j.ids.length) } پرامپت دستهٔ ${ b } کپی شد`);
    if ($('#bmsg'))
      $('#bmsg').innerHTML = j.missing.length ? 'بدون پرامپت یا فایل رفرنس: <bdi dir="ltr">' + j.missing.map(esc).join('، ') + '</bdi>' : '';
  } catch (e) {
    fail(e);
  }
}
/* ---- inbox, odd files of refs/, and the log of what the Downloads watcher moved */
function buildInbox() {
  const P = S.P, sz = n => n > 1048576 ? fa((n / 1048576).toFixed(1)) + ' MB' : fa(Math.max(1, Math.round(n / 1024))) + ' KB';
  const t = P.triage || [], i = P.inbox || [], m = P.imports || [];
  $('#pInbox').innerHTML = !t.length && !i.length && !m.length ? '<p class="muted">فایل تازه‌ای نیامده. فایل‌های متفرقه رو بریز توی پوشهٔ <bdi dir="ltr">inbox/</bdi> تا هوش مصنوعی مرتبشون کنه.</p>' : (t.length ? `<h4>نیاز به مرتب‌سازی (اسم رفرنس نیستن)</h4><ul data-triage="1">${ t.map(x => `<li><bdi dir="ltr">${ esc(x.src) }</bdi></li>`).join('') }</ul>` : '') + (i.length ? `<h4>inbox/ (${ fa(i.length) })</h4><ul data-inbox="1">${ i.map(f => `<li><bdi dir="ltr">${ esc(f.name) }</bdi> <small>${ esc(f.kind) } · ${ sz(f.size) }</small></li>`).join('') }</ul>` : '') + (m.length ? `<h4>آخرین ورودی‌ها</h4><ul data-imports="1">${ m.map(x => `<li><bdi dir="ltr">${ esc(x.time) } → ${ esc(x.to) }</bdi></li>`).join('') }</ul>` : '');
}
function build(name) {
  ({
    scenes: buildScenes,
    filter: paintFilter,
    speed: paintSpeed,
    vers: buildVers,
    undo: buildUndo,
    batch: buildBatch,
    inbox: buildInbox
  })[name]?.();
}
/* the menu rows with their trailing values; called after every redraw and when the picture changes */
export function drawerRefresh() {
  const P = S.P, trail = {
      filter: S.filter !== 'all' || S.q ? 'فعال' : '',
      speed: `<bdi dir="ltr">${ speedText(S.speed) }</bdi>`,
      refs: P.refs.length ? fa(P.refs.length) : '',
      undo: (P.history || []).length ? fa(P.history.length) : '',
      inbox: ((P.inbox || []).length + (P.triage || []).length) ? fa((P.inbox || []).length + (P.triage || []).length) : ''
    };
  $('#dmenu').innerHTML = ROWS.map(([k, i, t]) => `<button type="button" class="drow${ k === PANEL ? ' sel' : '' }" data-panel="${ k }">${ ic(i) }<span class="rt">${ t }</span><span class="trail">${ trail[k] || '' }</span></button>`).join('');
  if (drawerOpen() && PANEL)
    build(PANEL);
}
export function boot_drawer() {
  $$('[data-ic]').forEach(el => el.innerHTML = ic(el.dataset.ic));
  $('#pScenes').innerHTML = '<p id="info" class="muted"></p><div id="slist"></div>';
  $('#pFilter').innerHTML = '<input id="q" type="search" placeholder="جست‌وجو در متن، گوینده و یادداشت…" autocomplete="off"><div id="fopts"></div>';
  $('#menuBtn').onclick = () => drawerOpen() ? closeDrawer() : openDrawer();
  $('#dclose').onclick = $('#scrim').onclick = closeDrawer;
  $('#dback').onclick = () => {
    showPanel(null);
    drawerRefresh();
  };
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && drawerOpen() && !document.querySelector('dialog[open]') && $('#lb').classList.contains('hide'))
      closeDrawer();
  });
  $('#drawer').addEventListener('click', e => {
    const t = e.target.closest('button');
    if (!t)
      return;
    const d = t.dataset;
    if (d.panel) {
      showPanel(d.panel);
      drawerRefresh();
    } else if (d.go !== undefined) {
      closeDrawer();
      go(+d.go);
    } else if (d.son)
      bringBack(d.son);
    else if (d.filter) {
      S.filter = d.filter;
      filt(true);
      paintFilter();
      drawerRefresh();
    } else if (d.speed) {
      S.speed = +d.speed;
      audio.playbackRate = S.speed;
      paintSpeed();
      drawerRefresh();
    } else if (d.vpick !== undefined) {
      const c = curImg();
      if (c)
        pickVersion(c.f, c.m, +d.vpick).then(buildVers, fail);
    } else if (d.varch) {
      const c = curImg();
      if (c)
        api('/api/archive', {
          kind: 'image',
          id: c.m.id,
          name: d.varch
        }).then(reload, fail);
    } else if (d.irestore) {
      const c = curImg();
      if (c)
        api('/api/restore', {
          kind: 'image',
          id: c.m.id,
          name: d.irestore
        }).then(reload, fail);
    } else if (d.undo)
      undo(false);
    else if (d.batch)
      copyBatch(d.batch);
  });
  $('#q').addEventListener('input', e => {
    S.q = e.target.value.trim();
    filt(true);
    drawerRefresh();
  });
}
