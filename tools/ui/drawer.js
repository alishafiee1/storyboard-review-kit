import { S } from './state.js';
import {
  $,
  $$,
  api,
  askConfirm,
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
  pickVersion,
  showRestored
} from './versions.js';
import { sceneNo } from './render.js';
/* The paper drawer (menu): scene list, filter and search, speed, subtitles, voices, references, versions and archive, undo, batch prompts, inbox.
   Each row of the menu opens a panel inside the drawer; ‹ goes back. */
const PANELS = {
  scenes: '#pScenes',
  filter: '#pFilter',
  speed: '#pSpeed',
  spk: '#spk',
  refs: '#refs',
  vers: '#pVers',
  undo: '#pUndo',
  batch: '#pBatch',
  inbox: '#pInbox',
  settings: '#pSettings',
  export: '#pExport',
  help: '#pHelp'
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
  ],
  [
    'export',
    'batch',
    'خروجی برای ادیتور'
  ],
  [
    'settings',
    'gear',
    'تنظیمات'
  ],
  [
    'help',
    'help',
    'راهنما'
  ]
];
const GROUPS = [
  ['ناوبری و مرور', ['scenes', 'filter', 'vers']],
  ['تولید و رسانه', ['spk', 'refs', 'batch', 'inbox']],
  ['خروجی و تحویل', ['export', 'speed']],
  ['سیستم و راهنما', ['undo', 'settings', 'help']]
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
export const filterLabel = k => (FILTERS.find(([x]) => x === k) || ['', ''])[1];
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
  if ($('#q') && $('#q').value !== S.q)
    $('#q').value = S.q;
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
export async function undo(force) {
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
      if (await askConfirm(e.message + '\n\nباز هم برگردد؟', 'برگردان'))
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
/* ---- settings: one row per service (its key is written to .env and never shown again), the Downloads watcher */
async function buildSettings() {
  const P = $('#pSettings');
  if (P.querySelector('#skey') && P.querySelector('#skey').value)
    return;
  let s;
  try {
    s = await (await fetch('/api/settings')).json();
  } catch (e) {
    P.innerHTML = '<p class="muted">تنظیمات خونده نشد.</p>';
    return;
  }
  const src = { env: 'از متغیر محیطی', '.env': 'از فایل <bdi dir="ltr">.env</bdi>' }[s.key_source] || '';
  P.innerHTML = `<h4>سرویس‌ها</h4>
    <div class="svc">
      <div class="srow"><span class="st"><b>OpenRouter</b><small class="muted">ساخت صدا${ s.key_set ? ' · ' + src : '' }</small></span><span class="tag${ s.key_set ? ' ok' : '' }" id="skst" role="status">${ s.key_set ? 'تنظیم شده' : 'تنظیم نشده' }</span><button type="button" class="outline" data-sset="keyopen">${ s.key_set ? 'تغییر' : 'افزودن کلید' }</button></div>
      <div id="skeybox" hidden>
        <input id="skey" type="password" dir="ltr" autocomplete="off" spellcheck="false" placeholder="sk-or-v1-…" aria-label="کلید API">
        <div class="srow"><button type="button" class="outline" data-sset="key">ذخیره</button><button type="button" class="quiet" data-sset="keyclose">انصراف</button>${ s.key_set ? '<button type="button" class="quiet" data-sset="test">تست کلید</button>' : '' }<a class="muted" href="https://openrouter.ai/keys" target="_blank" rel="noopener">گرفتن کلید</a></div>
      </div>
    </div>
    <p class="muted">کلید فقط توی فایل <bdi dir="ltr">.env</bdi> کنار پروژه ذخیره می‌شه (توی گیت نمی‌ره) و دوباره نشون داده نمی‌شه. سرویس تازه‌ای که اضافه بشه همین‌جا یه ردیف می‌گیره.</p>
    <h4>دانلودها</h4>
    <label class="srow"><input type="checkbox" id="swatch"${ s.watch ? ' checked' : '' }> <span>فایل‌های Flow که مال این پروژه‌ان از پوشهٔ دانلود خودکار برن توی پوشهٔ درست</span></label>
    <div class="srow"><span class="st"><small class="muted">پوشه</small><bdi dir="ltr">${ esc(s.downloads) }</bdi></span><button type="button" class="outline" data-sset="dlopen">تغییر</button></div>
    <div id="sdlbox" hidden>
      <input id="sdl" type="text" dir="ltr" autocomplete="off" spellcheck="false" value="${ esc(s.downloads_custom) }" placeholder="${ esc(s.downloads) }" aria-label="پوشهٔ دانلود">
      <div class="srow"><button type="button" class="outline" data-sset="dl">ذخیره</button><button type="button" class="quiet" data-sset="dlclose">انصراف</button><small class="muted">خالی = پوشهٔ Downloads کاربر</small></div>
    </div>`;
  $('#swatch').onchange = e => settingsClick('watch', e.target.checked);
}
async function settingsClick(act, on) {
  const st = $('#skst');
  try {
    if (act === 'keyopen') {
      $('#skeybox').hidden = false;
      $('#skey').focus();
    } else if (act === 'keyclose') {
      $('#skey').value = '';
      $('#skeybox').hidden = true;
    } else if (act === 'dlopen') {
      $('#sdlbox').hidden = false;
      $('#sdl').focus();
    } else if (act === 'dlclose') {
      $('#sdlbox').hidden = true;
    } else if (act === 'key') {
      const k = $('#skey').value.trim();
      if (!k)
        return toast('اول کلید رو بنویس');
      const r = await api('/api/settings', { key: k });
      $('#skey').value = '';
      toast('کلید ذخیره شد' + (r.note ? ' · ' + r.note : ''));
      await buildSettings();
    } else if (act === 'test') {
      st.textContent = 'در حال تست…';
      const r = await api('/api/settings/testkey', {});
      st.textContent = (r.ok ? 'درسته: ' : 'ناموفق: ') + r.message;
    } else if (act === 'dl') {
      await api('/api/settings', { downloads: $('#sdl').value.trim() });
      toast('ذخیره شد');
      await buildSettings();
    } else if (act === 'watch') {
      await api('/api/settings', { watch_downloads: on });
      toast(on ? 'نگهبان دانلودها روشن شد' : 'نگهبان دانلودها خاموش شد');
    }
  } catch (e) {
    fail(e);
  }
}
/* ---- export for the editor: Premiere XML, subtitles, and one zip with the chosen pictures and voices */
function buildExport() {
  const P = $('#pExport');
  if (P.querySelector('#exres') && P.querySelector('#exres').dataset.busy === '1')
    return;
  P.innerHTML = `<h4>تایم‌لاین پریمیر (XML)</h4>
    <p class="muted">خروجی ساده با مسیر نسبی در پوشهٔ <bdi dir="ltr">premiere/</bdi> از روی ترتیب داستان و نسخه‌های تأییدشده.</p>
    <div class="srow act"><button type="button" class="outline" data-ex="px-fa">ساخت XML فارسی</button><button type="button" class="outline" data-ex="px-en">ساخت XML انگلیسی</button><button type="button" class="quiet" data-ex="pchk">بررسی فایل‌های XML</button></div>
    <p id="pxres" class="muted" role="status"></p>
    <h4>زیرنویس (SRT)</h4>
    <div class="srow"><span class="st"><small class="muted">فایل‌های <bdi dir="ltr">subtitles/fa.srt</bdi> و <bdi dir="ltr">en.srt</bdi></small></span><button type="button" class="outline" data-ex="subs">ساخت زیرنویس</button></div>
    <p id="subres" class="muted" role="status"></p>
    <h4>زیپ برای ادیتور</h4>
    <p class="muted">یه زیپ کنار پوشهٔ پروژه ساخته می‌شه شامل صفحهٔ بازبینی، سناریو، فقط عکس و صدای <b>انتخاب‌شده</b> و بستهٔ پریمیر.</p>
    <label class="srow"><input type="checkbox" id="exclips"> <span>کلیپ‌های ویدیویی (<bdi dir="ltr">videos/clips</bdi>) هم باشه</span></label>
    <div class="srow"><button type="button" class="outline" data-ex="go">ساخت زیپ</button></div>
    <p id="exres" class="muted" role="status"></p>`;
}
async function exportAct(act, btn) {
  if (act === 'go')
    return exportGo(btn);
  const px = $('#pxres'), sb = $('#subres');
  btn.disabled = true;
  try {
    if (act === 'subs') {
      sb.textContent = 'در حال ساخت زیرنویس…';
      const r = await api('/api/subtitles', {});
      sb.textContent = r.message || 'ساخته شد';
    } else if (act === 'px-fa' || act === 'px-en') {
      const lang = act.slice(3);
      px.textContent = 'در حال ساخت XML…';
      const r = await api('/api/premiere/export', { lang });
      px.innerHTML = `ساخته شد: <bdi dir="ltr">${ esc(r.path) }</bdi>${ r.warnings.length ? '<br>هشدار: ' + r.warnings.slice(0, 5).map(esc).join('، ') : '' }`;
    } else if (act === 'pchk') {
      px.textContent = 'در حال بررسی…';
      const r = await api('/api/premiere/check', {});
      px.innerHTML = r.xmls.length ? r.xmls.map(x => `<bdi dir="ltr">${ esc(x.name) }</bdi>: ${ fa(x.total) } فایل${ x.missing ? ` · <b style="color:var(--accent)">${ fa(x.missing) } گمشده</b>` : ' · سالم' }${ x.absolute ? ` · ${ fa(x.absolute) } مسیر مطلق` : '' }`).join('<br>') : 'فایل XML پریمیر پیدا نشد.';
    }
  } catch (e) {
    fail(e);
  } finally {
    btn.disabled = false;
  }
}
async function exportGo(btn) {
  const res = $('#exres');
  btn.disabled = true;
  res.dataset.busy = '1';
  res.textContent = 'در حال ساخت زیپ… ممکنه چند دقیقه طول بکشه؛ صفحه رو نبند.';
  try {
    const r = await api('/api/pack', { clips: $('#exclips').checked });
    res.innerHTML = `آماده شد: <bdi dir="ltr">${ esc(r.path) }</bdi><br>${ fa(r.files) } فایل · ${ fa(r.mb) } مگابایت${ r.package ? ' · بستهٔ پریمیر: <bdi dir="ltr">' + esc(r.package) + '</bdi>' : ' · بستهٔ پریمیر پیدا نشد' }${ r.missing.length ? '<br>هشدار: ' + r.missing.map(esc).join('، ') : '' }`;
  } catch (e) {
    res.textContent = '';
    fail(e);
  } finally {
    btn.disabled = false;
    delete res.dataset.busy;
  }
}
/* ---- help: the cards of skills/how-to-write-prompts-for-flow.md (the same guide the AI reads), short, with «more» under each; the project's own scripts; the version */
const HELP = { cards: null };
const plain = t => t.replace(/^```.*$/gm, '').replace(/\*\*/g, '').replace(/`/g, '').replace(/\n{3,}/g, '\n\n').trim();
async function loadHelp() {
  if (HELP.cards)
    return;
  const get = async u => {
    try {
      const r = await fetch(u);
      return r.ok ? await r.text() : '';
    } catch (e) {
      return '';
    }
  };
  const guide = await get('/skills/how-to-write-prompts-for-flow.md'), own = await get('/skills/project-scripts.md');
  const cards = [{
    title: 'میانبرهای صفحه‌کلید',
    summary: '← → تصویر قبلی/بعدی · ↑ ↓ نسخهٔ قبلی/بعدی · Space پخش · Ctrl+Z برگردان',
    body: '← / → : رفتن به تصویر قبلی یا بعدی (مطابق فیلتر)\n↑ / ↓ : جابه‌جایی بین نسخه‌های تصویر و تأیید خودکار\nSpace : پخش یا توقف خودکار صداهای صحنه\nCtrl+Z : برگرداندن آخرین تغییر ساختاری\nEsc : بستن پنجره، منو یا کشو\nEnter (در ویرایش خط و یادداشت) : ذخیره (Shift+Enter = خط بعد)'
  }];
  guide.split(/^## /m).slice(1).forEach(part => {
    const lines = part.replace(/<style>[\s\S]*$/, '').split('\n'), title = lines[0].replace(/^[\d۰-۹]+\)\s*/, '').trim();
    const sum = lines.findIndex(l => l.startsWith('> خلاصه:'));
    cards.push({
      title: plain(title),
      summary: sum >= 0 ? plain(lines[sum].replace('> خلاصه:', '')) : '',
      body: plain(lines.slice(1).filter((l, i) => i + 1 !== sum).join('\n'))
    });
  });
  const ownBody = own.replace(/```[\s\S]*?```/g, '');
  if (/^## /m.test(ownBody))
    cards.push({
      title: 'اسکریپت‌های این پروژه',
      summary: 'اسکریپت‌هایی که فقط مال همین پروژه‌ان و جای دستور کیت می‌شینن.',
      body: plain(own.replace(/^#.*\n/, ''))
    });
  HELP.cards = cards;
}
async function buildHelp() {
  const P = $('#pHelp');
  if (P.dataset.ready === '1')
    return;
  P.innerHTML = '<p class="muted">در حال خوندن…</p>';
  await loadHelp();
  let ver = '';
  try {
    ver = (await (await fetch('/api/settings')).json()).version || '';
  } catch (e) {
  }
  P.dataset.ready = '1';
  P.innerHTML = !HELP.cards.length ? '<p class="muted">فایل راهنما پیدا نشد. با <bdi dir="ltr">python tools/update.py</bdi> به‌روزش کن.</p>' : HELP.cards.map((c, i) => `<div class="hcard"><div class="srow"><span class="st"><b>${ esc(c.title) }</b><small class="muted">${ esc(c.summary) }</small></span><button type="button" class="outline" data-hmore="${ i }" aria-expanded="false">توضیح بیشتر</button></div><pre class="hbody" hidden>${ esc(c.body) }</pre></div>`).join('') + `<div class="hcard"><div class="srow"><span class="st"><b>درباره</b><small class="muted">نسخهٔ کیت <bdi dir="ltr">${ esc(ver) }</bdi> · به‌روزرسانی: <bdi dir="ltr">python tools/update.py</bdi></small></span></div></div>`;
}
function build(name) {
  ({
    scenes: buildScenes,
    filter: paintFilter,
    speed: paintSpeed,
    vers: buildVers,
    undo: buildUndo,
    batch: buildBatch,
    inbox: buildInbox,
    settings: buildSettings,
    export: buildExport,
    help: buildHelp
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
  const bu = $('#bUndo');
  bu.disabled = !(P.history || []).length;
  bu.title = bu.disabled ? 'چیزی برای برگرداندن نیست' : 'برگردان آخرین تغییر ساختاری (Ctrl+Z)';
  const byKey = Object.fromEntries(ROWS.map(r => [r[0], r]));
  const rowHtml = ([k, i, t]) => `<button type="button" class="drow${ k === PANEL ? ' sel' : '' }" data-panel="${ k }">${ ic(i) }<span class="rt">${ t }</span><span class="trail">${ trail[k] || '' }</span></button>`;
  $('#dmenu').innerHTML = GROUPS.map(([g, keys]) => `<div class="dgrp">${ g }</div>` + keys.map(k => rowHtml(byKey[k])).join('')).join('');
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
      if ($('#spdBtn'))
        $('#spdBtn').textContent = speedText(S.speed);
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
        }).then(reload).then(() => showRestored(c.m.id, d.irestore)).catch(fail);
    } else if (d.ex)
      exportAct(d.ex, t);
    else if (d.sset)
      settingsClick(d.sset);
    else if (d.hmore != null) {
      const body = t.closest('.hcard').querySelector('.hbody'), open = body.hidden;
      body.hidden = !open;
      t.textContent = open ? 'کمتر' : 'توضیح بیشتر';
      t.setAttribute('aria-expanded', String(open));
    }
    else if (d.undo)
      undo(false);
    else if (d.batch)
      copyBatch(d.batch);
  });
  $('#q').addEventListener('input', e => {
    S.q = e.target.value.trim();
    if ($('#gq'))
      $('#gq').value = S.q;
    filt(true);
    drawerRefresh();
  });
}
