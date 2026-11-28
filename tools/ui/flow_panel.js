import { $, api, esc, fa, fail, toast } from './core.js';
import { ic } from './icons.js';

/* Flow Automation Dashboard Modal (Phase D - Cycle 016)
   Provides controls to launch Chrome on port 9222, start/pause/resume jobs,
   show live batch progress, handle failed item resends, and display self-heal diagnostics. */

let dlgEl = null;
let pollTimer = null;

function renderModalHtml() {
  return `
    <div class="flow-header">
      <h3>ساخت با Flow</h3>
      <button type="button" class="ib" id="flowClose" aria-label="بستن" data-dclose>${ic('close')}</button>
    </div>

    <!-- Chrome Orchestration (R2) -->
    <div class="flow-sec">
      <div class="flow-sec-head">
        <div>
          <b>مرورگر کروم (پورت ۹۲۲۲)</b>
          <span id="flowChromeBadge" class="tag" style="margin-right:8px">بررسی وضعیت...</span>
        </div>
        <button type="button" class="outline" id="flowLaunchChrome">باز کردن کروم</button>
      </div>
      <div id="flowChromeNote" class="muted" style="font-size:13px;margin-top:4px">
        کروم با درگاه اشکال‌زدایی 9222 و پروفایل پایدار اجرا می‌شود تا ورود به گوگل فقط یک‌بار انجام شود.
      </div>
    </div>

    <!-- Actions (R3, R4) -->
    <div class="flow-sec">
      <div class="flow-sec-head">
        <div class="flow-actions">
          <button type="button" class="outline" id="flowStart">شروع</button>
          <button type="button" class="quiet" id="flowPause">توقف</button>
          <button type="button" class="outline" id="flowResume">ادامه</button>
        </div>
        <span id="flowJobState" class="tag">آماده</span>
      </div>
      <!-- Progress Bar (R3) -->
      <div class="flow-prog-bar">
        <div id="flowProgFill" class="flow-prog-fill" style="width:0%"></div>
      </div>
      <div id="flowProgText" class="flow-prog-text">Batch 0/0 | 0/0 images generated (0%)</div>
      <div id="flowStepInfo" class="muted" style="font-size:13px"></div>
    </div>

    <!-- Self-Healing Diagnostics Notice (R5, R6) -->
    <div id="flowSelfHealBox" class="flow-heal-badge" hidden>
      <span class="tag warn">توقف خودترمیمی</span>
      <span id="flowHealTimestamp" style="font-weight:500"></span>
      <span id="flowHealPath" class="muted" dir="ltr" style="font-size:13px"></span>
      <small style="color:var(--ink-muted);width:100%;margin-top:4px">
        خطای انتخابگر رخ داده است. می‌توانید tools/flow_selectors.json را ویرایش کرده و روی «ادامه» کلیک کنید.
      </small>
    </div>

    <!-- Failed Items & Per-Row Resend (R4) -->
    <div class="flow-sec">
      <div class="flow-sec-head">
        <b>فهرست موارد ناموفق</b>
        <span id="flowFailedCount" class="tag" style="display:none"></span>
      </div>
      <div id="flowFailedList" class="flow-failed-list">
        <p class="muted">موردی برای ارسال مجدد وجود ندارد.</p>
      </div>
    </div>
  `;
}

async function fetchFlowStatus() {
  try {
    const res = await fetch('/api/flow/status');
    if (!res.ok) return;
    const st = await res.json();
    updatePanelUI(st);
  } catch (e) {
    // Silent on network poll errors
  }
}

function updatePanelUI(st) {
  if (!dlgEl || !dlgEl.open) return;

  // 1. Chrome badge
  const chromeBadge = dlgEl.querySelector('#flowChromeBadge');
  if (chromeBadge) {
    if (st.chrome_connected) {
      chromeBadge.textContent = 'متصل';
      chromeBadge.className = 'tag ok';
    } else {
      chromeBadge.textContent = 'قطع';
      chromeBadge.className = 'tag';
    }
  }

  // 2. Action buttons & state
  const btnStart = dlgEl.querySelector('#flowStart');
  const btnPause = dlgEl.querySelector('#flowPause');
  const btnResume = dlgEl.querySelector('#flowResume');
  const jobStateTag = dlgEl.querySelector('#flowJobState');

  const isRunning = st.state === 'running';
  const isPaused = st.state === 'paused';

  if (btnStart) btnStart.disabled = isRunning || isPaused;
  if (btnPause) btnPause.disabled = !isRunning;
  if (btnResume) btnResume.disabled = !isPaused;

  if (jobStateTag) {
    const labels = {
      idle: 'آماده',
      running: 'در حال اجرا',
      paused: 'متوقف',
      done: 'تکمیل شد',
      failed: 'خطا'
    };
    jobStateTag.textContent = labels[st.state] || st.state;
    jobStateTag.className = 'tag' + (isRunning || st.state === 'done' ? ' ok' : (isPaused ? ' warn' : ''));
  }

  // 3. Progress metrics
  const progFill = dlgEl.querySelector('#flowProgFill');
  const progText = dlgEl.querySelector('#flowProgText');
  const stepInfo = dlgEl.querySelector('#flowStepInfo');

  const pct = Math.max(0, Math.min(100, st.percent || 0));
  if (progFill) progFill.style.width = pct + '%';
  if (progText) {
    if (st.total > 0) {
      progText.textContent = `Batch ${st.active_batch || 1}/${st.total_batches || 1} | ${st.done || 0}/${st.total || 0} images generated (${pct}%)`;
    } else {
      progText.textContent = st.progress_text || `Batch 0/0 | 0/0 images generated (0%)`;
    }
  }
  if (stepInfo) {
    stepInfo.textContent = st.current_item
      ? `تصویر جاری: ${st.current_item}${st.step_elapsed ? ` (${fa(st.step_elapsed)} ثانیه)` : ''}`
      : (st.error ? `خطا: ${st.error}` : '');
  }

  // 4. Self-healing notice
  const healBox = dlgEl.querySelector('#flowSelfHealBox');
  const healTs = dlgEl.querySelector('#flowHealTimestamp');
  const healPath = dlgEl.querySelector('#flowHealPath');
  if (healBox) {
    if (st.self_heal && st.self_heal.paused) {
      healBox.hidden = false;
      if (healTs) healTs.textContent = st.self_heal.timestamp || '';
      if (healPath) healPath.textContent = st.self_heal.diagnostic_dir || '';
    } else {
      healBox.hidden = true;
    }
  }

  // 5. Failed items list
  const failedList = dlgEl.querySelector('#flowFailedList');
  const failedCount = dlgEl.querySelector('#flowFailedCount');
  const failedItems = st.failed_items || [];

  if (failedCount) {
    if (failedItems.length) {
      failedCount.style.display = '';
      failedCount.textContent = fa(failedItems.length);
    } else {
      failedCount.style.display = 'none';
    }
  }

  if (failedList) {
    if (!failedItems.length) {
      failedList.innerHTML = '<p class="muted">موردی برای ارسال مجدد وجود ندارد.</p>';
    } else {
      failedList.innerHTML = failedItems.map(it => `
        <div class="failed-row">
          <div>
            <bdi dir="ltr"><b>${esc(it.output_name)}</b></bdi>
            <span class="muted" style="margin-right:8px;font-size:13px">${esc(it.error || it.reason || '')}</span>
          </div>
          <button type="button" class="quiet sm" data-resend="${esc(it.output_name)}">ارسال مجدد</button>
        </div>
      `).join('');
    }
  }
}

export function openFlowPanel() {
  if (!dlgEl) {
    dlgEl = document.createElement('dialog');
    dlgEl.id = 'flowModal';
    dlgEl.className = 'dlg flow-panel';
    dlgEl.innerHTML = renderModalHtml();
    document.body.appendChild(dlgEl);
    bindPanelEvents(dlgEl);
  }

  dlgEl.showModal();
  fetchFlowStatus();

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(fetchFlowStatus, 1500);
}

export function closeFlowPanel() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (dlgEl && dlgEl.open) {
    dlgEl.close();
  }
}

function bindPanelEvents(dlg) {
  dlg.addEventListener('click', async e => {
    // Backdrop click closes
    const r = dlg.getBoundingClientRect();
    if (e.target === dlg && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)) {
      closeFlowPanel();
      return;
    }

    const t = e.target.closest('button');
    if (!t) return;

    if (t.id === 'flowClose' || t.dataset.dclose !== undefined) {
      closeFlowPanel();
      return;
    }

    if (t.id === 'flowLaunchChrome') {
      t.disabled = true;
      try {
        const r = await api('/api/flow/launch-chrome', {});
        if (r.already_connected) {
          toast('کروم از قبل روی پورت ۹۲۲۲ باز است');
        } else if (r.ok) {
          toast('کروم اجرا شد');
        } else {
          toast('خطا: ' + (r.error || 'کروم اجرا نشد'));
        }
        await fetchFlowStatus();
      } catch (err) {
        fail(err);
      } finally {
        t.disabled = false;
      }
      return;
    }

    if (t.id === 'flowStart') {
      try {
        await api('/api/flow/start', { mode: 'download' });
        toast('فرآیند ساخت Flow آغاز شد');
        await fetchFlowStatus();
      } catch (err) {
        fail(err);
      }
      return;
    }

    if (t.id === 'flowPause') {
      try {
        await api('/api/flow/pause', {});
        toast('درخواست توقف ارسال شد');
        await fetchFlowStatus();
      } catch (err) {
        fail(err);
      }
      return;
    }

    if (t.id === 'flowResume') {
      try {
        await api('/api/flow/resume', {});
        toast('فرآیند ساخت ادامه یافت (انتخابگرها بازخوانی شدند)');
        await fetchFlowStatus();
      } catch (err) {
        fail(err);
      }
      return;
    }

    if (t.dataset.resend) {
      const name = t.dataset.resend;
      t.disabled = true;
      try {
        await api('/api/flow/resend', { output_name: name });
        toast(`ارسال مجدد ${name} در صف قرار گرفت`);
        await fetchFlowStatus();
      } catch (err) {
        fail(err);
      } finally {
        t.disabled = false;
      }
      return;
    }
  });

  dlg.addEventListener('close', () => {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  });
}

export function boot_flow_panel() {
  // Panel initializes on first open
}
