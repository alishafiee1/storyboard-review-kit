import {
  $,
  $$,
  TT,
  audio,
  esc,
  fa,
  fail,
  fmt,
  grow,
  modelById,
  track
} from './core.js';
import { S } from './state.js';
import {
  filt,
  labelList,
  refsTab,
  reload,
  speakersTab,
  stats,
  toneList
} from './panels.js';
import { wire } from './editors.js';
import { ic } from './icons.js';
import { drawerRefresh } from './drawer.js';
import { playUI } from './player.js';
import { galleryRefresh } from './gallery.js';
/* Drawing the page: scenes, dialogue lines, pictures. Every block (one picture + its lines) is in the page; only the current one is shown (see player.js). */
/* ---------- render */
let NUM = {};
/* scene number shown = its place among the scenes that are on (so moving or setting aside never needs renaming) */
export const sceneNo = s => s.id === 'scene-00' ? 0 : NUM[s.id] || 0;
export const sceneLabel = s => s.id === 'scene-00' ? 'تامبنیل' : `صحنه ${ fa(NUM[s.id] || '–') } · ${ s.title }`;
const issHtml = a => (a || []).map(x => `<div class="issue">فرمت: ${ esc(x.msg) } <button class="b" data-clr="${ x.ln }">حل شد</button></div>`).join('');
const flagBtn = ln => `<button class="lt-b flag" data-fl="${ ln }" aria-label="ثبت مشکل فرمت" title="ثبت مشکل فرمت این قسمت برای هوش مصنوعی">${ ic('flag') }</button>`;
const val = (txt, ln, key, x = '') => `<span class="v" data-ln="${ ln }" data-k="${ key }" data-old="${ esc(txt) }" ${ x } title="کلیک برای ویرایش">${ fmt(txt) }</span>`;
const delBtn = (ln, k, txt, hasEn) => `<button class="lt-b flag del" data-del="${ ln }" data-dk="${ k }" data-old="${ esc(txt) }" data-hasen="${ hasEn ? 1 : 0 }" aria-label="حذف" title="حذف">${ ic('close') }</button>`;
export const SPK = () => Object.fromEntries((S.P.speakers || []).map(s => [
  s.name,
  s
]));
const FALLBACK = [
  '#546e7a',
  '#6d4c41',
  '#00838f',
  '#ad1457',
  '#558b2f'
];
const colorOf = n => (SPK()[n] || {}).color || FALLBACK[[...String(n)].reduce((a, c) => a + c.charCodeAt(0), 0) % FALLBACK.length];
const addBar = ln => `<div class="addbar" data-after="${ ln }"><button data-add="say">+ دیالوگ</button><button data-add="act">+ توضیح صحنه</button></div>`;
const defTone = n => (SPK()[n] || {}).tone || '';
export const toneKnown = t => !String(t || '').trim() || (S.P.tts.tones || []).some(x => x.words.some(w => String(t).includes(w)));
export const unknownTones = () => {
  const m = new Map(), add = t => {
      t = String(t || '').trim();
      if (t && !toneKnown(t))
        m.set(t, (m.get(t) || 0) + 1);
    };
  (S.P.speakers || []).forEach(s => add(s.tone));
  S.P.scenes.forEach(s => s.blocks.forEach(b => b.items.forEach(i => add(i.tone))));
  return m;
};
const toneHtml = it => {
  const d = defTone(it.sp), eff = it.tone || d;
  const unk = !toneKnown(eff);
  return `<span class="v tn${ it.tone ? '' : ' dflt' }${ unk ? ' unk' : '' }" data-ln="${ it.ln }" data-k="tone" data-old="${ esc(it.tone) }" data-def="${ esc(d) }" title="${ unk ? 'این لحن توی فهرست لحن‌ها (voices/voice-config.json) نیست و برچسبی نمی‌فرسته؛ ' : '' }${ it.tone ? 'لحن این خط' : 'لحن پیش‌فرض گوینده' }؛ کلیک برای عوض‌کردن">${ eff ? esc(eff) : '+ لحن' }</span>`;
};
const lineBtns = (it, sc) => [
  'fa',
  'en'
].filter(lg => it.audio && it.audio[lg]).map(lg => {
  const v = (it.audio_v || {})[lg] || {
    names: [],
    chosen: ''
  };
  const vv = v.names.length > 1 ? `<button class="vv" data-vv="${ lg }" data-sc="${ sc.id }" data-iid="${ it.id }" aria-label="صدای بعدی" title="${ lg === 'fa' ? 'صدای فارسی' : 'English voice' }: ${ esc(v.chosen) } · کلیک = صدای بعدی (همونی که آخر می‌ذاری، صدای نهایی می‌شه)">‹${ fa(v.names.indexOf(v.chosen) + 1) }/${ fa(v.names.length) }›</button>` : '';
  return `<button class="ab" data-lg="${ lg }" data-src="${ esc(it.audio[lg]) }" title="${ lg === 'fa' ? 'پخش صدای فارسی این دیالوگ' : 'Play the English voice of this line' }">${ ic('speaker') }<small>${ lg.toUpperCase() }</small></button>${ vv }`;
}).join('');
let LA = null, LB = null;
export function stopLine() {
  if (LA) {
    LA.pause();
    LA = null;
  }
  if (LB) {
    LB.classList.remove('on');
    LB = null;
  }
}
function itemHtml(it, sc, i, j) {
  if (it.k === 'act')
    return `<div class="itw"><div class="it act${ it.label === 'گگ' ? ' gag' : '' }" id="i${ i }_${ j }">${ it.label ? `<span class="v alab" data-ln="${ it.ln }" data-k="label" data-old="${ esc(it.label) }" title="کلیک برای عوض‌کردن یا پاک‌کردن برچسب">${ esc(it.label) }</span>` : '' }${ val(it.fa, it.ln, 'act') }<span class="lt">${ flagBtn(it.ln) }${ delBtn(it.ln, 'act', it.fa, false) }</span>${ issHtml(it.issues) }</div></div>`;
  const faL = `<div class="fa">${ val(it.fa, it.ln, 'say', it.en != null ? 'data-hasen="1"' : '') }</div>`;
  const en = $('#showEN').checked ? it.en != null ? `<div class="en" dir="ltr">${ val(it.en, it.en_ln, 'en') }${ delBtn(it.en_ln, 'en', it.en, false) }</div>` : `<div class="en none"><button class="enp" data-aden="${ it.ln }" title="افزودن ترجمهٔ انگلیسی">EN+</button></div>` : '';
  return `<div class="itw"><div class="it sp${ it.vstale && it.vstale.length ? ' vstale' : '' }" style="--c:${ colorOf(it.sp) }" id="i${ i }_${ j }"><div class="who"><span class="v nm" data-ln="${ it.ln }" data-k="speaker" data-old="${ esc(it.sp) }" title="کلیک برای عوض‌کردن گوینده">${ esc(it.sp) }</span>${ toneHtml(it) }${ lineBtns(it, sc) }<span class="lt">${ it.id ? `<button class="lt-b vgen" data-vgen="${ it.id }" data-sc="${ sc.id }" aria-label="مدیریت و ساخت صدا" title="ساخت صدای تازه یا انتخاب بین صداهای این خط">${ ic('mic') }</button>` : '' }${ flagBtn(it.ln) }${ delBtn(it.ln, 'say', it.fa, it.en != null) }</span></div>${ faL }${ en }${ issHtml(it.issues) }</div></div>`;
}
const FX_PH = 'توصیهٔ ادیت (زوم، پن، فید، لرزش، نور، ذرات، صدا...) · Enter = ذخیره · Shift+Enter = خط بعد · Esc = برگشت';
/* the edit-advice box of a picture: saves on Enter or when the focus leaves (the note box does the same, see editors.js) */
export function wireFx(t, save) {
  track(t, document.createElement('button'));
  let busy = false;
  const go = async () => {
    if (busy || t.value === t.dataset.orig)
      return;
    busy = true;
    try {
      await save(t.value);
      t.dataset.orig = t.value;
      await reload();
    } catch (e) {
      fail(e);
    } finally {
      busy = false;
    }
  };
  t._save = go;
  t.addEventListener('input', () => grow(t));
  t.addEventListener('blur', () => setTimeout(() => {
    if (document.hasFocus() && t.isConnected && !t.closest('.hide'))
      go();
  }, 0));
  t.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      go();
    }
    if (e.key === 'Escape') {
      t.value = t.dataset.orig;
      t.dispatchEvent(new Event('input'));
    }
  });
}
/* where «one image up / down» puts a picture: past the neighbour in its scene, or over the scene header to the end of the scene above / the start of the
   scene below (scenes that are set aside are skipped, and nothing goes into the thumbnail scene). null = nowhere to go. */
export function moveTarget(id, step) {
  const vis = S.P.scenes.filter(s => !s.off), imgs = sc => sc.blocks.flatMap(b => b.images.map(i => i.id));
  const si = vis.findIndex(s => imgs(s).includes(id));
  if (si < 0 || vis[si].id === 'scene-00')
    return null;
  const list = imgs(vis[si]), k = list.indexOf(id);
  if (step < 0) {
    if (k > 0)
      return { ids: [id], before: list[k - 1] };
    const prev = vis[si - 1];
    return prev && prev.id !== 'scene-00' ? { ids: [id], to_end_of_scene: prev.id } : null;
  }
  if (k < list.length - 1)
    return { ids: [id], after: list[k + 1] };
  const next = vis[si + 1], nl = next ? imgs(next) : [];
  return next ? nl.length ? { ids: [id], before: nl[0] } : { ids: [id], to_end_of_scene: next.id } : null;
}
/* the little «۲/۴», quality and approved mark on the picture itself */
export const vmetaHtml = m => {
  const n = (m.versions || []).length, v = n ? m.versions[m.vi] : null, ok = v && m.picked && v.id === m.picked;
  return `${ n > 1 ? `<span class="vc">${ fa(m.vi + 1) }/${ fa(n) }</span>` : '' }${ v && v.q ? `<span class="vq" dir="ltr">${ esc(v.q) }</span>` : '' }${ ok ? `<span class="vok" title="این نسخه تأیید شده">${ ic('check') }</span>` : '' }`;
};
function figHtml(m, sc) {
  const n = (m.versions || []).length;
  const pic = m.src ? `<img src="${ m.src }" alt="" draggable="false">` : `<div class="ph"><b>${ m.id }</b><span>هنوز ساخته نشده</span></div>`;
  const arrows = n > 1 ? `<button class="va l" data-vn="-1" aria-label="نسخهٔ قبلی" title="نسخهٔ قبلی (↑)">${ ic('chevL') }</button><button class="va r" data-vn="1" aria-label="نسخهٔ بعدی" title="نسخهٔ بعدی (↓)">${ ic('chevR') }</button>` : '';
  const rj = m.rejected.length ? `<span class="rj">ردشده‌ها: ${ m.rejected.map((r, i) => `<a href="${ r }" target="_blank">${ fa(i + 1) }</a>`).join(' ') }</span>` : '';
  return `<figure class="shot${ m.off ? ' off' : '' }" data-id="${ m.id }" data-m="${ m.status }"><div class="mount"><i class="tape a"></i><i class="tape b"></i><div class="frame">${ pic }${ arrows }<span class="vmeta">${ vmetaHtml(m) }</span></div></div>
   <div class="idrow"><bdi class="iid" dir="ltr">${ m.id }</bdi>${ m.off ? '<span class="offl">کنار گذاشته شده</span>' : '' }${ m.video ? `<button class="quiet sm vid" data-vid="${ esc(m.video) }" data-name="${ m.id }" title="پخش ویدیوی این تصویر">${ ic('play') }ویدیو</button>` : '' }${ rj }</div>
   ${ m.stale ? `<div class="stalebox">پرامپت عوض شده؛ تصویر کهنه است <button class="quiet sm" data-clrimg="1">تصویر به‌روز شد</button></div>` : '' }${ issHtml(m.issues) }
   <div class="nbox pop hide" data-key="panel:note:${ m.id }" role="group" aria-label="یادداشت و ادیت"><div class="phead"><b>یادداشت</b><button class="ib sm" type="button" data-nclose="1" aria-label="بستن">${ ic('close') }</button></div>
     <textarea class="nt" rows="2" data-key="note:${ m.id }" data-orig="${ esc(m.note) }" placeholder="یادداشت برای این صحنه... (Enter = ذخیره · Shift+Enter = خط بعد · Esc = برگشت)">${ esc(m.note) }</textarea>
     <div class="btns" hidden><button class="b" data-sn="1">ذخیره یادداشت</button></div>
     <div class="phead"><b>ادیت</b></div>
     <textarea class="fx" rows="1" data-key="fx:${ m.id }" data-orig="${ esc(m.fx || '') }" placeholder="${ FX_PH }">${ esc(m.fx || '') }</textarea></div></figure>`;
}
/* the voice button of a scene: «make voices» for lines that are out of date */
function sceneModel(sc) {
  const m = modelById(sc.model || TT().default), need = [...new Set(sc.blocks.flatMap(b => b.items.filter(i => i.k === 'say').map(i => i.sp)))];
  const bad = m && m.voices.length ? need.filter(n => {
    const s = (S.P.speakers || []).find(x => x.name === n);
    return s && !m.voices.some(v => v.name === s.voice);
  }) : [];
  return `<button class="quiet" data-regen="${ sc.id }" ${ bad.length ? 'disabled title="اول صدای گوینده‌ها رو با مدل پیش‌فرض جور کن"' : '' }>${ ic('speaker') }ساخت صدای این صحنه</button><span class="jobst" data-job="${ sc.id }"></span>${ bad.length ? `<span class="bad">مدل پیش‌فرض صدای ${ bad.map(esc).join('، ') } رو نداره</span>` : '' }`;
}
/* a folder like «1-mimo-white-head» is shown as the title «mimo white head» with the muted label «اپیزود ۱» */
const nameParts = () => {
  const m = /^(\d+)[-_ .](.+)$/.exec(S.P.name || '');
  return m ? [
    m[2].replace(/[-_]+/g, ' '),
    'اپیزود ' + fa(+m[1])
  ] : [
    S.P.name,
    ''
  ];
};
export function render() {
  const list = $('#list');
  if ($('#picActs').closest('#list'))
    $('.be').appendChild($('#picActs'));
  list.innerHTML = '';
  S.BL = [];
  NUM = {};
  let nn = 0;
  S.P.scenes.forEach(sc => {
    if (sc.id !== 'scene-00' && !sc.off)
      NUM[sc.id] = ++nn;
  });
  S.P.scenes.forEach(sc => {
    if (sc.off)
      return;
    const warns = sc.warnings.map(w => w.issues.length ? issHtml(w.issues) : `<div class="issue">خط با قالب ناشناخته: <code>${ esc(w.text) }</code> <button class="b" data-wreg="${ w.ln }">ثبت برای هوش مصنوعی</button></div>`).join('') + issHtml(sc.issues);
    list.insertAdjacentHTML('beforeend', `<section data-scene="${ sc.id }" class="scn"><div class="bl"></div></section>`);
    const holder = list.lastElementChild.querySelector('.bl');
    sc.blocks.forEach(b => {
      const i = S.BL.length;
      S.BL.push(b);
      const d = document.createElement('section');
      d.className = 'blk' + (b.images.length ? '' : ' noimg');
      d.id = 'b' + i;
      d.dataset.bid = b.images.length ? b.images[0].id : sc.id + '#' + holder.children.length;
      const first = !holder.children.length;
      const head = `<div class="pghead"><button class="slabel" type="button" data-sedit="${ sc.id }" title="ویرایش عنوان، محیط و ادیت صحنه">${ esc(sceneLabel(sc)) }${ sc.time && sc.time !== '-' ? `<small dir="ltr">${ esc(sc.time) }</small>` : '' }</button><span class="cnt" aria-live="polite"></span></div>`;
      d.innerHTML = `<div class="imgs">${ b.images.length ? b.images.map(im => figHtml(im, sc)).join('') : '<div class="mount"><div class="frame"><div class="ph"><span>این متن به تصویری وصل نیست</span></div></div></div>' }</div><div class="txt">${ head }${ sc.env.map(e => `<div class="env">${ val(e.text, e.ln, 'env') }<span class="lt">${ flagBtn(e.ln) }</span>${ issHtml(e.issues) }</div>`).join('') }${ first ? warns : '' }${ b.items.map((t, j) => itemHtml(t, sc, i, j)).join('') }${ addBar(b.items.length ? b.items[b.items.length - 1].ln : b.images[b.images.length - 1].ln) }${ b.items.some(x => x.vstale && x.vstale.length) ? `<div class="vstrip">${ sceneModel(sc) }</div>` : '' }</div>`;
      holder.appendChild(d);
    });
  });
  $('#prog').max = Math.max(0, S.BL.length - 1);
  [$('#title').textContent, $('#ep').textContent] = nameParts();
  wire();
  refsTab();
  speakersTab();
  labelList();
  toneList();
  stats();
  filt();
  drawerRefresh();
  galleryRefresh();
}
/* the line you are on (clicked, or being played): pale olive wash and a terracotta tick; the counter says which one it is */
export function setActive(it) {
  const blk = it.closest('.blk');
  blk.querySelectorAll('.it.cur').forEach(x => x.classList.remove('cur'));
  it.classList.add('cur');
  const all = [...blk.querySelectorAll('.it')];
  blk.querySelector('.cnt').textContent = all.length ? `خط ${ fa(all.indexOf(it) + 1) } از ${ fa(all.length) }` : 'بدون متن';
}
export function defaultActive(blk) {
  const it = blk.querySelector('.it.sp') || blk.querySelector('.it');
  if (it)
    setActive(it);
  else
    blk.querySelector('.cnt').textContent = 'بدون متن';
}
export function boot_render() {
  document.addEventListener('click', e => {
    const it = e.target.closest('.blk .it');
    if (it && !e.target.closest('.ie') && !it.classList.contains('cur') && !S.playing)
      setActive(it);
  });
  document.addEventListener('click', e => {
    const b = e.target.closest('.ab');
    if (!b)
      return;
    if (LB === b) {
      stopLine();
      return;
    }
    stopLine();
    S.token++;
    audio.pause();
    S.playing = false;
    playUI();
    const m = /^i(\d+)_(\d+)$/.exec(b.closest('.it').id);
    if (m)
      S.START = {
        n: +m[1],
        j: +m[2],
        lg: b.dataset.lg
      };
    LA = new Audio(b.dataset.src);
    LB = b;
    b.classList.add('on');
    LA.playbackRate = S.speed;
    LA.onended = LA.onerror = () => stopLine();
    LA.play().catch(() => stopLine());
  });
}
