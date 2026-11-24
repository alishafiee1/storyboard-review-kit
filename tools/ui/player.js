/* Auto-play, the floating play button, navigation, tabs, keyboard and start-up. */
/* ---------- playback */
function show(i) {
  cur = i;
  $('#prog').value = i;
  $('#jump').value = [...$('#jump').options].filter(o => +o.value <= i).pop()?.value;
  $$('.blk.on').forEach(x => x.classList.remove('on'));
  const el = $('#b' + i);
  if (!el)
    return;
  el.classList.add('on');
  el.scrollIntoView({
    block: 'start',
    behavior: SMOOTH
  });
  markImg(i, 0);
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
function wait(ms, t) {
  return new Promise(r => {
    let iv;
    const id = setTimeout(() => {
      clearInterval(iv);
      r();
    }, ms);
    iv = setInterval(() => {
      if (t !== token) {
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
    audio.playbackRate = +$('#speed').value;
    audio.ontimeupdate = () => {
      if (t === token)
        cb(audio.currentTime);
    };
    audio.onended = r;
    audio.onerror = r;
    poll = setInterval(() => {
      if (t !== token) {
        audio.pause();
        r();
      }
    }, 120);
    audio.play().catch(r);
  });
}
async function run(i, lgIn, fromJ) {
  const t = ++token;
  playing = true;
  $('#play').textContent = '⏸ توقف';
  const lg = lgIn || ($('#showEN').checked ? 'en' : 'fa');
  for (let n = i; n < BL.length && t === token; n++) {
    const b = BL[n];
    if ($('#b' + n).classList.contains('hide'))
      continue;
    show(n);
    const v = b.items.map((x, j) => [
      x,
      j
    ]).filter(([x, j]) => x.audio && x.audio[lg] && (n !== i || !fromJ || j >= fromJ));
    if (!v.length) {
      await wait(SILENT * 1000 / (+$('#speed').value || 1), t);
      continue;
    }
    const ds = await Promise.all(v.map(([x]) => dur(x.audio[lg])));
    const total = ds.reduce((a, b) => a + b, 0) || 1;
    let done = 0;
    for (let k = 0; k < v.length && t === token; k++) {
      const [it, j] = v[k];
      $$('.it.cur').forEach(x => x.classList.remove('cur'));
      $('#i' + n + '_' + j).classList.add('cur');
      START = {
        n,
        j,
        lg
      };
      await playClip(it.audio[lg], t, ct => {
        if (b.images.length > 1)
          markImg(n, Math.min(b.images.length - 1, Math.floor((done + ct) / total * b.images.length)));
      });
      done += ds[k];
      await wait(260, t);
    }
    await wait(380, t);
  }
  if (t === token) {
    playing = false;
    START = null;
    $('#play').textContent = '▶ پخش';
    $('#info').textContent = 'پایان';
  }
}
function go(i, start) {
  stopLine();
  START = null;
  token++;
  audio.pause();
  playing = false;
  $('#play').textContent = '▶ پخش';
  show(i);
  if (start)
    run(i);
}
$('#play').onclick = () => {
  stopLine();
  if (playing) {
    token++;
    audio.pause();
    playing = false;
    $('#play').textContent = '▶ پخش';
  } else if (START && BL[START.n])
    run(START.n, START.lg, START.j);
  else
    run(cur);
};
$('#fab').onclick = () => $('#play').click();
$('#subs').onclick = async () => {
  const b = $('#subs');
  b.disabled = true;
  try {
    const r = await api('/api/subtitles', {});
    alert('✓ ' + r.message);
  } catch (e) {
    fail(e);
  } finally {
    b.disabled = false;
  }
};
new MutationObserver(() => {
  const on = $('#play').textContent.includes('⏸');
  $('#fab').classList.toggle('playing', on);
  $('#fab').setAttribute('aria-label', on ? 'توقف پخش' : 'پخش خودکار');
}).observe($('#play'), {
  childList: true,
  characterData: true,
  subtree: true
});
$('#prev').onclick = () => go(Math.max(0, cur - 1), playing);
$('#next').onclick = () => go(Math.min(BL.length - 1, cur + 1), playing);
$('#jump').onchange = e => go(+e.target.value, playing);
$('#prog').oninput = e => go(+e.target.value, playing);
$('#filter').onchange = filt;
$('#speed').onchange = () => {
  audio.playbackRate = +$('#speed').value;
};
$('#showEN').onchange = () => {
  START = null;
  reload();
};
const TABS = {
  tabR: '#list',
  tabF: '#refs',
  tabS: '#spk'
};
function showTab(id) {
  if (id !== 'tabR') {
    token++;
    audio.pause();
    playing = false;
    $('#play').textContent = '▶ پخش';
  }
  Object.entries(TABS).forEach(([k, sel]) => {
    $(sel).classList.toggle('hide', k !== id);
    $('#' + k).classList.toggle('on', k === id);
  });
}
Object.keys(TABS).forEach(id => $('#' + id).onclick = () => showTab(id));
/* the slider and the dropdowns must not keep the keyboard: otherwise ArrowUp / ArrowDown move them (and jump to a block) instead of scrolling the page from where you are */
[
  '#prog',
  '#jump',
  '#filter',
  '#speed'
].forEach(s => {
  const el = $(s);
  el.addEventListener('change', () => el.blur());
});
$('#prog').addEventListener('pointerup', () => setTimeout(() => $('#prog').blur(), 0));
$('#prog').addEventListener('keydown', e => {
  if (/^(Arrow|Page)|^(Home|End)$/.test(e.key)) {
    e.preventDefault();
    e.target.blur();
  }
});
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && ![
      'SELECT',
      'TEXTAREA',
      'INPUT',
      'BUTTON'
    ].includes(e.target.tagName)) {
    e.preventDefault();
    $('#play').click();
  }
});
(async () => {
  try {
    const r = await fetch('/api/project');
    if (!r.ok)
      throw 0;
    P = await r.json();
    setInterval(() => fetch('/api/ping').catch(() => {
    }), 5000);
    fetch('/api/ping').catch(() => {
    });
  } catch (e) {
    $('#list').innerHTML = '<div class="msg">این صفحه باید از سرور باز بشه. فایل <b>click-for-review.bat</b> کنار همین فایل رو دابل‌کلیک کن.</div>';
    return;
  }
  render();
  show(0);
  if (P.tts && P.tts.job.state === 'running')
    pollJob();
})();
