import { S } from './state.js';
import {
  $,
  $$,
  SILENT,
  api,
  audio,
  fa,
  fail,
  pollJob
} from './core.js';
import {
  defaultActive,
  render,
  setActive,
  stopLine
} from './render.js';
import {
  filt,
  reload
} from './panels.js';
import { ic } from './icons.js';
import { startMode } from './gallery.js';
import { stepVersion } from './versions.js';
import {
  drawerOpen,
  drawerRefresh,
  undo
} from './drawer.js';
/* The scrolling list of pictures: navigation, the top bar's numbers, the transport under the picture, auto-play, keyboard and start-up. */
/* ---------- which block is shown */
export const vis = () => S.BL.map((_, i) => i).filter(i => {
  const el = $('#b' + i);
  return el && !el.classList.contains('hide');
});
/* the picture on show (a block shared by several pictures: the one being played, else the first) */
export function curImg() {
  const b = S.BL[S.cur];
  if (!b || !b.images.length)
    return null;
  const fs = $$('#b' + S.cur + ' figure.shot'), f = fs.find(x => x.classList.contains('cur')) || fs[0];
  const m = f && b.images.find(x => x.id === f.dataset.id);
  return m ? {
    m,
    f
  } : null;
}
const mmss = t => `${ fa(Math.floor(t / 60)) }:${ fa(String(Math.floor(t % 60)).padStart(2, '0')) }`;
function setTime(t, total) {
  $('#ttime').textContent = `${ mmss(t) } / ${ mmss(total) }`;
  $('#tbar i').style.width = (total ? Math.min(100, t / total * 100) : 0) + '%';
}
export function playUI() {
  const on = S.playing;
  $('#play').classList.toggle('playing', on);
  $('#play').setAttribute('aria-label', on ? 'توقف پخش' : 'پخش خودکار');
  $('#play').title = (on ? 'توقف پخش' : 'پخش خودکار') + ' (Space)';
}
/* top bar: «۴۵ / ۵۰», the tick line, «approved», the icons that need a picture; footer: set aside */
export function chrome() {
  const v = vis(), p = v.indexOf(S.cur), n = v.length, c = curImg(), m = c && c.m;
  $('#pos').textContent = `${ fa(Math.max(0, p) + 1 - (n ? 0 : 1)) } / ${ fa(n) }`;
  const pr = $('#prog');
  pr.max = Math.max(0, n - 1);
  pr.value = Math.max(0, p);
  pr.style.setProperty('--p', (n > 1 ? Math.max(0, p) / (n - 1) * 100 : 100) + '%');
  const one = 190 / Math.max(1, n - 1), step = one < 5 ? one * 5 : one;
  pr.style.setProperty('--step', step.toFixed(2) + 'px');
  $('#navPrev').disabled = $('#prev').disabled = p <= 0;
  $('#navNext').disabled = $('#next').disabled = p < 0 || p >= n - 1;
  $('#apr').innerHTML = m && m.status === 'ok' ? ic('check') + 'تأیید شده' : '';
  $('#apr').classList.toggle('show', !!(m && m.status === 'ok'));
  const acts = $('#picActs');
  const home = c ? c.f : $('.be');
  if (acts.parentElement !== home)
    home.appendChild(acts);
  [
    '#bNote',
    '#bPrompt',
    '#bVprompt',
    '#bFlag',
    '#more'
  ].forEach(s => $(s).disabled = !m);
  $('#bNote').classList.toggle('has', !!(m && (m.note || m.fx)));
  $('#bVprompt').classList.toggle('has', !!(m && m.vprompt));
  $('#bPrompt').classList.toggle('has', !!(m && m.stale));
  const a = $('#aside');
  a.disabled = !m;
  a.innerHTML = ic('tray') + `<span>${ m && m.off ? 'برگردان' : 'کنار بگذار' }</span>`;
  const en = $('#showEN').checked;
  $('#lang').setAttribute('aria-pressed', en ? 'true' : 'false');
  $('#lang').classList.toggle('en', en);
}
/* the list scrolls: a jump from a button moves the list to that page (smooth when near); while it moves, the scroll watcher stays quiet */
let SCROLLING = 0, FIRST = true;
function scrollToBlock(el, tries = 0) {
  const list = $('#list');
  SCROLLING = Date.now() + 700;
  if (list && !list.clientHeight && tries < 25) {
    /* the list is still hidden (the gallery is closing): look again in a moment */
    setTimeout(() => S.cur === +el.id.slice(1) && scrollToBlock(el, tries + 1), 40);
    return;
  }
  if (!list || list.scrollHeight <= list.clientHeight)
    return;
  const lr = list.getBoundingClientRect(), top = el.getBoundingClientRect().top - lr.top + list.scrollTop;
  if (Math.abs(top - list.scrollTop) < 2)
    return;
  const near = !FIRST && Math.abs(top - list.scrollTop) < list.clientHeight * 3;
  FIRST = false;
  SCROLLING = Date.now() + (near ? 700 : 150);
  list.scrollTo({
    top,
    behavior: near ? 'smooth' : 'auto'
  });
}
/* the page nearest the middle of the list is the one on show (a manual scroll) */
function onListScroll() {
  if (Date.now() < SCROLLING) {
    SCROLLING = Date.now() + 160;
    return;
  }
  if (S.playing)
    return;
  const list = $('#list'), lr = list.getBoundingClientRect(), mid = lr.top + lr.height * 0.4;
  let best = null, bd = 1e9;
  for (const i of vis()) {
    const r = $('#b' + i).getBoundingClientRect(), d = r.top <= mid && r.bottom >= mid ? 0 : Math.min(Math.abs(r.top - mid), Math.abs(r.bottom - mid));
    if (d < bd) {
      bd = d;
      best = i;
    }
  }
  if (best != null && best !== S.cur) {
    stopLine();
    show(best, null, true);
  }
}
export function show(i, keepJ, fromScroll) {
  const el = $('#b' + i);
  if (!el)
    return;
  S.cur = i;
  filt();
  $$('.blk.on').forEach(x => x.classList.remove('on'));
  $$('section.scn.cur').forEach(x => x.classList.remove('cur'));
  el.classList.add('on');
  el.closest('.scn').classList.add('cur');
  markImg(i, 0);
  const keep = keepJ != null && el.querySelectorAll('.it')[keepJ];
  if (keep)
    setActive(keep);
  else
    defaultActive(el);
  chrome();
  preTime(i);
  drawerRefresh();
  if (!fromScroll)
    scrollToBlock(el);
  if (!document.body.classList.contains('gal'))
    history.replaceState(null, '', '#' + el.dataset.bid);
}
/* the block of a picture / the block the page was showing (after a reload the numbers may have moved) */
export const blockOf = id => S.BL.findIndex(b => b.images.some(m => m.id === id));
export const blockByBid = bid => $$('.blk').findIndex(el => el.dataset.bid === bid);
export function showNear(i) {
  const v = vis();
  if (!v.length)
    return;
  show(v.includes(i) ? i : v.find(x => x >= i) ?? v[v.length - 1]);
}
function markImg(i, f) {
  $$('figure.shot.cur').forEach(x => x.classList.remove('cur'));
  const a = $$('#b' + i + ' figure.shot');
  if (a.length > 1 && a[f])
    a[f].classList.add('cur');
}
const dcache = {};
function dur(src) {
  return new Promise(r => {
    if (dcache[src])
      return r(dcache[src]);
    const a = new Audio();
    a.preload = 'metadata';
    a.onloadedmetadata = () => r(dcache[src] = a.duration || 0);
    a.onerror = () => r(0);
    a.src = src;
  });
}
const lines = (b, lg) => b.items.filter(x => x.audio && x.audio[lg]);
/* the length of the lines of the block on show, in the language that would play */
async function preTime(i) {
  const lg = $('#showEN').checked ? 'en' : 'fa', b = S.BL[i];
  setTime(0, 0);
  if (!b)
    return;
  const ds = await Promise.all(lines(b, lg).map(x => dur(x.audio[lg])));
  const total = ds.reduce((a, c) => a + c, 0) || SILENT;
  if (S.cur === i && !S.playing)
    setTime(0, total / S.speed);
}
function wait(ms, t) {
  return new Promise(r => {
    let iv;
    const id = setTimeout(() => {
      clearInterval(iv);
      r();
    }, ms);
    iv = setInterval(() => {
      if (t !== S.token) {
        clearTimeout(id);
        clearInterval(iv);
        r();
      }
    }, 120);
  });
}
function playClip(src, t, cb) {
  stopLine();
  return new Promise(res => {
    let poll;
    const r = () => {
      clearInterval(poll);
      res();
    };
    audio.src = src;
    audio.playbackRate = S.speed;
    audio.ontimeupdate = () => {
      if (t === S.token)
        cb(audio.currentTime);
    };
    audio.onended = r;
    audio.onerror = r;
    poll = setInterval(() => {
      if (t !== S.token) {
        audio.pause();
        r();
      }
    }, 120);
    audio.play().catch(r);
  });
}
async function run(i, lgIn, fromJ) {
  const t = ++S.token;
  S.playing = true;
  playUI();
  const lg = lgIn || ($('#showEN').checked ? 'en' : 'fa');
  for (let n = i; n < S.BL.length && t === S.token; n++) {
    const b = S.BL[n];
    if ($('#b' + n).classList.contains('hide'))
      continue;
    show(n);
    const v = b.items.map((x, j) => [
      x,
      j
    ]).filter(([x, j]) => x.audio && x.audio[lg] && (n !== i || !fromJ || j >= fromJ));
    if (!v.length) {
      setTime(0, SILENT / S.speed);
      await wait(SILENT * 1000 / (S.speed || 1), t);
      continue;
    }
    const ds = await Promise.all(v.map(([x]) => dur(x.audio[lg])));
    const total = ds.reduce((a, b) => a + b, 0) || 1;
    let done = 0;
    for (let k = 0; k < v.length && t === S.token; k++) {
      const [it, j] = v[k];
      setActive($('#i' + n + '_' + j));
      S.START = {
        n,
        j,
        lg
      };
      await playClip(it.audio[lg], t, ct => {
        setTime((done + ct) / S.speed, total / S.speed);
        if (b.images.length > 1)
          markImg(n, Math.min(b.images.length - 1, Math.floor((done + ct) / total * b.images.length)));
      });
      done += ds[k];
      await wait(260, t);
    }
    await wait(380, t);
  }
  if (t === S.token) {
    S.playing = false;
    S.START = null;
    playUI();
  }
}
function stop() {
  stopLine();
  S.token++;
  audio.pause();
  S.playing = false;
  playUI();
}
export function go(i, start) {
  stop();
  S.START = null;
  show(i);
  if (start)
    run(i);
}
/* previous / next picture that the filter lets through */
function step(d) {
  const v = vis(), p = v.indexOf(S.cur), k = v[Math.max(0, Math.min(v.length - 1, p + d))];
  if (k != null && k !== S.cur)
    go(k, S.playing);
}
export function stopPlayback() {
  stop();
}
export function boot_player() {
  let tick = 0;
  $('#list').addEventListener('scroll', () => {
    if (tick)
      return;
    tick = requestAnimationFrame(() => {
      tick = 0;
      onListScroll();
    });
  }, { passive: true });
  document.addEventListener('click', e => {
    const f = e.target.closest('[data-fwd]');
    if (f)
      document.getElementById(f.dataset.fwd).click();
  });
  $('#play').onclick = () => {
    stopLine();
    if (S.playing)
      stop();
    else if (S.START && S.BL[S.START.n])
      run(S.START.n, S.START.lg, S.START.j);
    else
      run(S.cur);
  };
  $('#subs').onclick = async () => {
    const b = $('#subs');
    b.disabled = true;
    try {
      const r = await api('/api/subtitles', {});
      alert(r.message);
    } catch (e) {
      fail(e);
    } finally {
      b.disabled = false;
    }
  };
  $('#prev').onclick = $('#navPrev').onclick = () => step(-1);
  $('#next').onclick = $('#navNext').onclick = () => step(1);
  $('#prog').oninput = e => {
    const k = vis()[+e.target.value];
    if (k != null)
      go(k, S.playing);
  };
  $('#lang').onclick = () => {
    $('#showEN').checked = !$('#showEN').checked;
    S.START = null;
    reload();
  };
  /* the slider must not keep the keyboard: otherwise ← → ↑ ↓ move it instead of going to the next picture / version */
  $('#prog').addEventListener('pointerup', () => setTimeout(() => $('#prog').blur(), 0));
  $('#prog').addEventListener('keydown', e => {
    if (/^(Arrow|Page)|^(Home|End)$/.test(e.key)) {
      e.preventDefault();
      e.target.blur();
    }
  });
  $('#bUndo').onclick = () => undo(false);
  /* Ctrl+Z = undo the last structural change (code KeyZ, so it also works on the Persian keyboard); inside a text box it stays the browser's own text undo */
  document.addEventListener('keydown', e => {
    if (e.defaultPrevented || !(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey || e.code !== 'KeyZ')
      return;
    const t = e.target;
    if ([
        'SELECT',
        'TEXTAREA',
        'INPUT'
      ].includes(t.tagName) || t.isContentEditable || document.querySelector('dialog[open]'))
      return;
    e.preventDefault();
    undo(false);
  });
  document.addEventListener('keydown', e => {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey)
      return;
    const tag = e.target.tagName;
    if ([
        'SELECT',
        'TEXTAREA',
        'INPUT'
      ].includes(tag) && e.target.id !== 'prog' || e.target.isContentEditable)
      return;
    if (document.querySelector('dialog[open]') || document.body.classList.contains('gal') || drawerOpen() || !$('#morePop').hidden)
      return;
    if (e.code === 'Space' && tag !== 'BUTTON') {
      e.preventDefault();
      $('#play').click();
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      step(e.key === 'ArrowLeft' ? -1 : 1);
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      stepVersion(e.key === 'ArrowUp' ? -1 : 1);
    }
  });
  /* a link like review.html#IMG045 (or a change of the address) shows that picture */
  window.addEventListener('hashchange', () => {
    const at = blockByBid(decodeURIComponent(location.hash.slice(1)));
    if (at >= 0 && at !== S.cur)
      go(at, S.playing);
  });
  (async () => {
    try {
      const r = await fetch('/api/project');
      if (!r.ok)
        throw 0;
      S.P = await r.json();
      setInterval(() => fetch('/api/ping').catch(() => {
      }), 5000);
      fetch('/api/ping').catch(() => {
      });
    } catch (e) {
      $('#list').innerHTML = '<div class="msg">این صفحه باید از سرور باز بشه. فایل <b>click-for-review.bat</b> کنار همین فایل رو دابل‌کلیک کن.</div>';
      return;
    }
    render();
    const at = blockByBid(decodeURIComponent(location.hash.slice(1)));
    startMode(location.hash);
    show(at >= 0 ? at : 0);
    if (S.P.tts && S.P.tts.job.state === 'running')
      pollJob();
  })();
}
