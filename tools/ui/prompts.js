import {
  $,
  api,
  copy,
  esc,
  fa,
  fail,
  grow,
  lineRef
} from './core.js';
import { S } from './state.js';
import { ic } from './icons.js';
import { curImg } from './player.js';
import {
  lightbox,
  playVideo,
  reload
} from './panels.js';
import { sceneNo } from './render.js';
/* The image and video prompt card (a paper dialog in the middle of the page), the note popover and the flag of the picture on show. */
let PM = null;
/* the references of a picture as chips, with the button that opens the attach dialog */
const refsRow = m => `<span class="rl">رفرنس‌ها</span>${ m.refs.map(c => c.src ? `<button type="button" class="chip ref" data-ref="${ c.src }" data-name="${ esc(c.name) }" title="باز کردن رفرنس">${ esc(c.name) }</button>${ c.video ? `<button type="button" class="chip ref" data-vid="${ esc(c.video) }" data-name="${ esc(c.name) }" title="پخش ویدیوی این رفرنس">${ ic('play') }</button>` : '' }` : `<span class="chip miss" title="این رفرنس هنوز ساخته نشده">${ esc(c.name) }</span>`).join('') || '<small>بدون رفرنس</small>' }<button type="button" class="chip add" data-attach="${ m.id }" title="رفرنس‌های این تصویر رو اضافه یا کم کن">اتچ رفرنس</button>`;
const words = t => t.trim() ? t.trim().split(/\s+/).length : 0;
export function openPrompt(kind) {
  const c = curImg();
  if (!c || PM)
    return;
  const {m} = c, video = kind === 'video', id = m.id, text = (video ? m.vprompt : m.prompt) || '';
  const sc = S.P.scenes.find(s => s.blocks.some(b => b.images.some(x => x.id === id)));
  const el = document.createElement('dialog');
  el.className = 'dlg pm';
  el.dataset.kind = video ? 'vprompt' : 'prompt';
  el.dataset.iid = id;
  el.innerHTML = `<div class="pmc"><i class="tape a"></i><i class="tape b"></i><header><div><h3>${ video ? 'پرامپت ویدیو' : 'پرامپت تصویر' }</h3><p class="sub">${ sc ? 'صحنه ' + fa(sceneNo(sc) || '–') : 'تصویر' } · قابل ویرایش${ video ? ' · تصویر = فریم اول' : '' }</p></div><button type="button" class="ib" data-pclose="1" aria-label="بستن">${ ic('close') }</button></header>
    ${ video ? '' : `<div class="prefs">${ refsRow(m) }</div>` }
    <textarea class="ptxt" dir="auto" spellcheck="false" data-key="${ video ? 'vprompt' : 'prompt' }:${ id }" data-orig="${ esc(text) }" placeholder="هنوز پرامپت ${ video ? 'ویدیو ' : '' }نداره؛ بنویس و ذخیره کن">${ esc(text) }</textarea>
    <footer><span class="pmeta"></span><span class="sp"></span><button type="button" class="stamp" data-psave="1">${ ic('check') }<span>ذخیره</span></button><button type="button" class="outline" data-pcopy="1">${ ic('copy') }<span>رونوشت</span></button><button type="button" class="quiet" data-pclose="1">بستن</button></footer></div>`;
  document.body.appendChild(el);
  const ta = el.querySelector('textarea'), meta = el.querySelector('.pmeta'), sv = el.querySelector('[data-psave]');
  const dirty = () => ta.value !== ta.dataset.orig;
  const paint = () => {
    meta.innerHTML = `<bdi dir="ltr">${ id }</bdi> · انگلیسی · ${ fa(words(ta.value)) } واژه`;
    sv.classList.toggle('dirty', dirty());
    ta.classList.toggle('dirty', dirty());
  };
  const tryClose = () => {
    if (dirty() && !confirm('تغییرهای ذخیره‌نشده از بین می‌ره. بسته بشه؟'))
      return;
    el.close();
  };
  ta.addEventListener('input', paint);
  paint();
  el.addEventListener('cancel', e => {
    e.preventDefault();
    if ($('#lb').classList.contains('hide'))
      tryClose();
  });
  el.addEventListener('click', e => {
    if (e.target === el)
      tryClose();
  });
  el.addEventListener('close', () => {
    PM = null;
    el.remove();
  });
  el.querySelectorAll('[data-pclose]').forEach(b => b.onclick = tryClose);
  el.querySelector('[data-pcopy]').onclick = e => copy(ta.value, e.currentTarget);
  sv.onclick = async () => {
    try {
      await api(video ? '/api/vprompt' : '/api/prompt', {
        id,
        old: ta.dataset.orig,
        new: ta.value
      });
      ta.dataset.orig = ta.value;
      paint();
      meta.textContent = 'ذخیره شد';
      await reload();
    } catch (e) {
      fail(e);
    }
  };
  PM = {
    el,
    video,
    id,
    refs: el.querySelector('.prefs')
  };
  el.showModal();
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}
/* after a reload (a reference was attached, the file changed): redraw the reference chips of the open card */
export function redrawPrompt() {
  if (!PM || !PM.el.open || !PM.refs)
    return;
  const m = S.BL.flatMap(b => b.images).find(x => x.id === PM.id);
  if (m)
    PM.refs.innerHTML = refsRow(m);
}
function toggleNote() {
  const c = curImg();
  if (!c)
    return;
  const nb = c.f.querySelector('.nbox');
  nb.classList.toggle('hide');
  const open = !nb.classList.contains('hide');
  $('#bNote').classList.toggle('open', open);
  if (open) {
    nb.querySelectorAll('textarea').forEach(grow);
    nb.querySelector('textarea.nt').focus();
  }
}
async function flagImage() {
  const c = curImg();
  if (!c)
    return;
  const msg = prompt('مشکل فرمت این تصویر چیه؟ (برای هوش مصنوعی ثبت می‌شه؛ اختیاری)', 'فرمت این قسمت درست نیست');
  if (msg === null)
    return;
  const sid = c.f.closest('section[data-scene]').dataset.scene;
  try {
    await api('/api/issue', {
      ...lineRef(sid, c.m.ln),
      message: msg
    });
    await reload();
  } catch (e) {
    fail(e);
  }
}
export function boot_prompts() {
  $('#bNote').onclick = toggleNote;
  $('#bPrompt').onclick = () => openPrompt('image');
  $('#bVprompt').onclick = () => openPrompt('video');
  $('#bFlag').onclick = flagImage;
  document.addEventListener('click', e => {
    const r = e.target.closest('[data-ref]');
    if (r)
      lightbox(r.dataset.ref, r.dataset.name);
    const v = e.target.closest('.pm [data-vid]');
    if (v)
      playVideo(v.dataset.vid, v.dataset.name);
    const n = e.target.closest('[data-nclose]');
    if (n) {
      const nb = n.closest('.nbox');
      nb.querySelectorAll('textarea').forEach(x => x.value !== x.dataset.orig && x._save && x._save());
      nb.classList.add('hide');
      $('#bNote').classList.remove('open');
    }
  });
}
