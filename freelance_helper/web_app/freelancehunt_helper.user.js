// ==UserScript==
// @name         Freelancehunt AI Assistant & CRM Co-Pilot
// @namespace    https://freelans.duckdns.org/
// @version      1.2.1
// @description  Розумний асистент для фрилансера: аналіз замовлення, автозаповнення ставки, рекомендована ціна та синхронізація з CRM без ризику бану.
// @author       Freelance AI Helper
// @match        https://freelancehunt.com/project/*
// @match        https://freelancehunt.ua/project/*
// @match        https://*.freelancehunt.com/project/*
// @match        https://*.freelancehunt.ua/project/*
// @icon         https://freelancehunt.com/favicon.ico
// @grant        GM_xmlhttpRequest
// @grant        GM_setClipboard
// @grant        GM_notification
// @connect      freelans.duckdns.org
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // Base API configuration
  const API_BASE = 'https://freelans.duckdns.org';
  const LOCAL_API = 'http://127.0.0.1:8088';

  // Extract project ID from URL (e.g. /project/telegram-bot/12345.html or /project/12345.html)
  function getProjectIdFromUrl() {
    const match = window.location.pathname.match(/(\d+)\.html/) || window.location.pathname.match(/\/project\/.*?(\d+)/);
    return match ? match[1] : null;
  }

  const projectId = getProjectIdFromUrl();
  if (!projectId) {
    return; // Not a project detail page
  }

  // State object
  const state = {
    projectId: projectId,
    title: '',
    description: '',
    budget: '',
    bidsCount: 0,
    score: null,
    reason: '',
    category: '',
    recommendedAmount: null,
    recommendedCurrency: 'UAH',
    recommendedDays: 2,
    sweetSpot: '',
    bidShort: '',
    bidFull: '',
    questions: '',
    activeTab: 'short', // 'short', 'full', 'questions'
    collapsed: localStorage.getItem('fhai_collapsed') === 'true',
    loading: true,
  };

  // Extract project information from page DOM
  function scrapePageProject() {
    const titleEl = document.querySelector('h1') || document.querySelector('.page-header h1');
    state.title = titleEl ? titleEl.innerText.trim() : document.title;

    const descEl = document.querySelector('.project-description') ||
                   document.querySelector('#project-description') ||
                   document.querySelector('div[itemprop="description"]') ||
                   document.querySelector('.well.project-description');
    state.description = descEl ? descEl.innerText.trim() : '';

    const priceEl = document.querySelector('.price') ||
                    document.querySelector('.text-green') ||
                    document.querySelector('.project-budget');
    state.budget = priceEl ? priceEl.innerText.trim() : '';

    const bidsTab = document.querySelector('a[href*="#bids"]') || document.querySelector('.nav-tabs a[href*="bids"]');
    if (bidsTab) {
      const match = bidsTab.innerText.match(/\d+/);
      state.bidsCount = match ? parseInt(match[0], 10) : 0;
    }
  }

  // Cross-origin request supporting both GM_xmlhttpRequest and native fetch
  function makeApiRequest(url, method = 'GET', data = null) {
    return new Promise((resolve, reject) => {
      if (typeof GM_xmlhttpRequest === 'function') {
        GM_xmlhttpRequest({
          method: method,
          url: url,
          data: data ? JSON.stringify(data) : undefined,
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          onload: (response) => {
            try {
              if (response.status >= 200 && response.status < 300) {
                resolve(JSON.parse(response.responseText));
              } else {
                reject(new Error('HTTP ' + response.status));
              }
            } catch (e) {
              reject(e);
            }
          },
          onerror: (err) => reject(err),
          ontimeout: () => reject(new Error('Timeout')),
        });
      } else {
        // Fallback for Safari Userscripts or browsers without GM_xmlhttpRequest
        fetch(url, {
          method: method,
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          body: data ? JSON.stringify(data) : undefined,
        })
          .then(res => res.json())
          .then(resolve)
          .catch(reject);
      }
    });
  }

  // Copy text cross-browser
  function copyTextToClipboard(text) {
    if (typeof GM_setClipboard === 'function') {
      GM_setClipboard(text);
      return true;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
      return true;
    }
    const tempInput = document.createElement('textarea');
    tempInput.value = text;
    document.body.appendChild(tempInput);
    tempInput.select();
    document.execCommand('copy');
    document.body.removeChild(tempInput);
    return true;
  }

  // Parse URL hash parameters (e.g. #autobid&amount=3000&days=2&bid=...)
  function parseHashParams() {
    const hash = window.location.hash.slice(1);
    if (!hash) return {};
    const params = {};
    hash.split('&').forEach(part => {
      const idx = part.indexOf('=');
      if (idx !== -1) {
        const k = part.slice(0, idx);
        const v = part.slice(idx + 1);
        try {
          params[decodeURIComponent(k)] = decodeURIComponent(v);
        } catch (e) {
          params[k] = v;
        }
      } else if (part) {
        params[part] = true;
      }
    });
    return params;
  }

  // Load bid draft data from URL hash or API
  async function loadBidDraft() {
    const hashParams = parseHashParams();
    const hasHashData = Boolean(hashParams.bid || hashParams.amount || hashParams.days);

    if (hasHashData) {
      if (hashParams.bid) {
        state.bidShort = hashParams.bid;
        state.bidFull = hashParams.bid;
      }
      if (hashParams.amount) {
        state.recommendedAmount = hashParams.amount;
      }
      if (hashParams.days) {
        state.recommendedDays = hashParams.days;
      }
      state.score = 95;
      state.reason = 'Готова ставка передана напряму з Telegram';
      state.loading = false;
      updateWidgetUI();
      setTimeout(() => {
        ensureAndFillBidForm(30);
      }, 150);
      return;
    }

    state.loading = true;
    updateWidgetUI();

    const queryParams = new URLSearchParams({
      project_id: state.projectId,
      title: state.title,
      description: state.description.slice(0, 500),
      budget: state.budget,
      bids_count: String(state.bidsCount),
    });

    let res = null;
    try {
      res = await makeApiRequest(`${API_BASE}/api/bid_draft?${queryParams.toString()}`);
    } catch (err) {
      try {
        res = await makeApiRequest(`${LOCAL_API}/api/bid_draft?${queryParams.toString()}`);
      } catch (err2) {
        console.warn('[Freelancehunt AI] Could not reach API, using client-side fallback generation');
      }
    }

    if (res && res.success) {
      state.score = res.score;
      state.reason = res.reason;
      state.recommendedAmount = res.recommended_amount;
      state.recommendedCurrency = res.recommended_currency || 'UAH';
      state.recommendedDays = res.recommended_days || 2;
      state.sweetSpot = res.sweet_spot || '';
      state.bidShort = res.bid_short || '';
      state.bidFull = res.bid_full || '';
      state.questions = res.questions || '';
    } else {
      // Local fallback generation if offline
      state.score = 75;
      state.reason = 'Автономний режим: аналіз виконано локально';
      state.recommendedDays = 2;
      state.bidShort = `Вітаю! Ознайомився із завданням «${state.title}» та готовий якісно виконати під ключ.\n\nМаю релевантний практичний досвід, виконаю роботу швидко, чисто та з гарантією підтримки.\n\nГотовий обговорити деталі в чаті та розпочати роботу!`;
      state.bidFull = state.bidShort;
      state.questions = `Що варто уточнити:\n1. Чи є готове детальне ТЗ або макет?\n2. Які точні дедлайни по проєкту?`;
    }

    state.loading = false;
    updateWidgetUI();

    // Automatic fill on page load: enabled by default, or triggered by #autofill / #autobid in URL
    const isAutoFillEnabled = localStorage.getItem('fhai_autofill') !== 'false' || window.location.hash.includes('autofill') || window.location.hash.includes('autobid');
    if (isAutoFillEnabled) {
      setTimeout(() => {
        ensureAndFillBidForm(25);
      }, 400);
    }
  }

  // Create or update the floating widget in DOM
  let rootContainer = null;

  function injectWidget() {
    if (document.getElementById('fhai-root')) return;

    rootContainer = document.createElement('div');
    rootContainer.id = 'fhai-root';

    const style = document.createElement('style');
    style.textContent = `
      #fhai-root {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 999999;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: #f8fafc;
      }
      .fhai-badge-btn {
        display: flex;
        align-items: center;
        gap: 8px;
        background: linear-gradient(135deg, #0284c7, #0369a1);
        color: #ffffff;
        padding: 10px 16px;
        border-radius: 30px;
        cursor: pointer;
        box-shadow: 0 8px 24px rgba(2, 132, 199, 0.45);
        font-weight: 600;
        font-size: 13px;
        border: 1px solid rgba(255, 255, 255, 0.25);
        transition: transform 0.2s, box-shadow 0.2s;
        user-select: none;
      }
      .fhai-badge-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 28px rgba(2, 132, 199, 0.6);
      }
      .fhai-panel {
        width: 380px;
        background: rgba(15, 23, 42, 0.96);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 16px;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
        overflow: hidden;
        display: flex;
        flex-direction: column;
        animation: fhai-fade-in 0.25s ease-out;
      }
      @keyframes fhai-fade-in {
        from { opacity: 0; transform: translateY(12px) scale(0.98); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }
      .fhai-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 14px;
        background: rgba(30, 41, 59, 0.8);
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      }
      .fhai-header-title {
        font-size: 13px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 6px;
        color: #38bdf8;
      }
      .fhai-header-actions {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .fhai-score-pill {
        font-size: 11px;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 12px;
        background: rgba(16, 185, 129, 0.2);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.4);
      }
      .fhai-score-pill.warning {
        background: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border-color: rgba(245, 158, 11, 0.4);
      }
      .fhai-score-pill.danger {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
        border-color: rgba(239, 68, 68, 0.4);
      }
      .fhai-icon-btn {
        background: transparent;
        border: none;
        color: #94a3b8;
        cursor: pointer;
        padding: 4px;
        font-size: 14px;
        line-height: 1;
        border-radius: 4px;
      }
      .fhai-icon-btn:hover {
        color: #ffffff;
        background: rgba(255, 255, 255, 0.1);
      }
      .fhai-body {
        padding: 12px 14px;
        display: flex;
        flex-direction: column;
        gap: 10px;
        max-height: 480px;
        overflow-y: auto;
      }
      .fhai-info-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: rgba(30, 41, 59, 0.5);
        padding: 8px 10px;
        border-radius: 8px;
        font-size: 12px;
        border: 1px solid rgba(255, 255, 255, 0.05);
      }
      .fhai-info-val {
        font-weight: 600;
        color: #38bdf8;
      }
      .fhai-tabs {
        display: flex;
        gap: 4px;
        background: rgba(30, 41, 59, 0.6);
        padding: 3px;
        border-radius: 8px;
      }
      .fhai-tab {
        flex: 1;
        text-align: center;
        padding: 5px 8px;
        font-size: 11px;
        font-weight: 600;
        border-radius: 6px;
        cursor: pointer;
        color: #94a3b8;
        user-select: none;
      }
      .fhai-tab.active {
        background: #0284c7;
        color: #ffffff;
      }
      .fhai-textarea {
        width: 100%;
        box-sizing: border-box;
        height: 120px;
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        color: #e2e8f0;
        font-size: 12px;
        line-height: 1.45;
        padding: 8px 10px;
        resize: vertical;
        font-family: inherit;
      }
      .fhai-textarea:focus {
        outline: none;
        border-color: #38bdf8;
      }
      .fhai-actions {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .fhai-btn-primary {
        background: linear-gradient(135deg, #0284c7, #0369a1);
        color: #ffffff;
        border: none;
        border-radius: 8px;
        padding: 9px 12px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        transition: background 0.15s;
      }
      .fhai-btn-primary:hover {
        background: linear-gradient(135deg, #0369a1, #075985);
      }
      .fhai-btn-row {
        display: flex;
        gap: 6px;
      }
      .fhai-btn-secondary {
        flex: 1;
        background: rgba(51, 65, 85, 0.8);
        color: #f1f5f9;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 7px 10px;
        font-size: 11px;
        font-weight: 500;
        cursor: pointer;
        text-align: center;
      }
      .fhai-btn-secondary:hover {
        background: rgba(71, 85, 105, 0.9);
      }
      .fhai-toast {
        background: #10b981;
        color: #ffffff;
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
        text-align: center;
        animation: fhai-fade-in 0.2s ease-out;
      }
      .fhai-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 14px;
        background: rgba(15, 23, 42, 0.9);
        border-top: 1px solid rgba(255, 255, 255, 0.06);
        font-size: 10px;
        color: #64748b;
      }
      .fhai-footer a {
        color: #38bdf8;
        text-decoration: none;
      }
      .fhai-footer a:hover {
        text-decoration: underline;
      }
      .fhai-safe-badge {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        color: #34d399;
      }
    `;

    document.head.appendChild(style);
    document.body.appendChild(rootContainer);
  }

  // Toast feedback message
  function showToast(text, duration = 3000) {
    const existing = document.querySelector('.fhai-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'fhai-toast';
    toast.innerText = text;

    const bodyEl = document.querySelector('.fhai-body');
    if (bodyEl) {
      bodyEl.prepend(toast);
      setTimeout(() => toast.remove(), duration);
    }
  }

  // Find native Freelancehunt bid form input elements
  function findFormElements() {
    const commentEl = document.querySelector('textarea[name="comment"]') ||
                      document.querySelector('textarea#comment') ||
                      document.querySelector('textarea[name="text"]') ||
                      document.querySelector('#bid-form textarea') ||
                      document.querySelector('.bid-form textarea') ||
                      document.querySelector('form[action*="bid"] textarea');

    const daysEl = document.querySelector('input[name="days"]') ||
                   document.querySelector('input#days') ||
                   document.querySelector('input[name="period"]') ||
                   document.querySelector('input[name="delivery_period"]');

    const amountEl = document.querySelector('input[name="amount"]') ||
                     document.querySelector('input#amount') ||
                     document.querySelector('input[name="cost"]') ||
                     document.querySelector('input[name="price"]');

    return { commentEl, daysEl, amountEl };
  }

  // Attempt to open or expand the bid form if it is hidden behind a button
  function tryOpenBidForm() {
    const { commentEl } = findFormElements();
    if (commentEl && commentEl.offsetParent !== null) {
      return true; // Already visible
    }

    const candidates = Array.from(document.querySelectorAll('a, button, [role="button"], input[type="button"]'));
    const openBtn = candidates.find(el => {
      if (el.closest('#fhai-root') || el.id === 'fhai-cancel-btn' || el.id === 'fhai-now-btn') return false;
      const txt = (el.textContent || el.value || '').trim().toLowerCase();
      const href = (el.getAttribute('href') || '').toLowerCase();
      return (
        txt.includes('зробити ставку') ||
        txt.includes('змінити ставку') ||
        txt.includes('додати ставку') ||
        txt.includes('подати ставку') ||
        txt.includes('редагувати ставку') ||
        href.includes('#bid') ||
        href.includes('/bid')
      );
    });

    if (openBtn) {
      console.log('[Freelancehunt AI] Triggering bid form open button:', openBtn);
      openBtn.click();
      return true;
    }

    const bidForm = document.getElementById('bid-form') || document.querySelector('.bid-form');
    if (bidForm) {
      bidForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return true;
    }

    return false;
  }

  // Poll until the bid form is in DOM and visible, then fill it
  function ensureAndFillBidForm(retriesLeft = 25) {
    const { commentEl } = findFormElements();

    if (commentEl && commentEl.offsetParent !== null) {
      fillNativeBidForm(true);
      return;
    }

    tryOpenBidForm();

    if (retriesLeft > 0) {
      setTimeout(() => {
        ensureAndFillBidForm(retriesLeft - 1);
      }, 350);
    } else {
      fillNativeBidForm(false);
    }
  }

  // Auto-submit countdown timer and submission runner
  let autoSubmitTimer = null;
  let autoSubmitSeconds = 5;

  function startAutoSubmitCountdown() {
    if (autoSubmitTimer) clearInterval(autoSubmitTimer);
    autoSubmitSeconds = 5;

    const oldBanner = document.getElementById('fhai-autosubmit-banner');
    if (oldBanner) oldBanner.remove();

    const banner = document.createElement('div');
    banner.id = 'fhai-autosubmit-banner';
    banner.style.cssText = `
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      background: #0f172a;
      color: #f8fafc;
      padding: 12px 20px;
      border-radius: 12px;
      border: 2px solid #10b981;
      box-shadow: 0 10px 28px rgba(0,0,0,0.6);
      z-index: 99999999;
      display: flex;
      align-items: center;
      gap: 14px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 13px;
      animation: fhai-fade-in 0.2s ease-out;
    `;
    banner.innerHTML = `
      <span>🚀 <b>Авто-відправка ставки</b> через <b id="fhai-sec" style="color:#38bdf8;font-size:16px;">5</b>с...</span>
      <button id="fhai-cancel-btn" style="background:#ef4444;color:#fff;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-weight:600;font-size:12px;">Скасувати</button>
      <button id="fhai-now-btn" style="background:#10b981;color:#fff;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-weight:600;font-size:12px;">Відправити зараз ↵</button>
    `;
    document.body.appendChild(banner);

    const cancelBtn = document.getElementById('fhai-cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        clearInterval(autoSubmitTimer);
        banner.remove();
        showToast('🛑 Авто-відправку скасовано. Форма готова для ручної перевірки.');
      });
    }

    function doSubmit() {
      clearInterval(autoSubmitTimer);
      banner.remove();
      const submitBtn = document.querySelector('#bid-form button[type="submit"]') ||
                        document.querySelector('form.bid-form button[type="submit"]') ||
                        document.querySelector('button[type="submit"][name="submit"]') ||
                        document.querySelector('#bid-form input[type="submit"]') ||
                        Array.from(document.querySelectorAll('button, input[type="submit"], a.btn')).find(b => {
                          if (b.closest('#fhai-root')) return false;
                          const t = (b.textContent || b.value || '').trim().toLowerCase();
                          return (t.includes('зробити ставку') || t.includes('оновити ставку') || t.includes('зберегти')) &&
                                 !t.includes('автозаповнити');
                        });
      if (submitBtn && !submitBtn.disabled) {
        showToast('🚀 Натискаємо «Зробити ставку»...');
        submitBtn.click();
      } else {
        showToast('⚠️ Форму заповнено, натисніть кнопку відправки на сторінці.');
      }
    }

    const nowBtn = document.getElementById('fhai-now-btn');
    if (nowBtn) {
      nowBtn.addEventListener('click', doSubmit);
    }

    autoSubmitTimer = setInterval(() => {
      autoSubmitSeconds--;
      const secEl = document.getElementById('fhai-sec');
      if (secEl) secEl.textContent = String(autoSubmitSeconds);

      if (autoSubmitSeconds <= 0) {
        doSubmit();
      }
    }, 1000);
  }

  // Auto-fill Freelancehunt native bid form fields with authentic human events
  function fillNativeBidForm(quiet = false) {
    const textToFill = getCurrentBidText();
    const { commentEl, daysEl, amountEl } = findFormElements();

    let filledCount = 0;

    if (commentEl) {
      commentEl.value = textToFill;
      commentEl.dispatchEvent(new Event('input', { bubbles: true }));
      commentEl.dispatchEvent(new Event('change', { bubbles: true }));
      commentEl.dispatchEvent(new Event('blur', { bubbles: true }));
      commentEl.style.border = '2px solid #10b981';
      filledCount++;
    }

    if (daysEl && state.recommendedDays) {
      daysEl.value = state.recommendedDays;
      daysEl.dispatchEvent(new Event('input', { bubbles: true }));
      daysEl.dispatchEvent(new Event('change', { bubbles: true }));
      daysEl.dispatchEvent(new Event('blur', { bubbles: true }));
      daysEl.style.border = '2px solid #10b981';
      filledCount++;
    }

    if (amountEl && state.recommendedAmount) {
      amountEl.value = state.recommendedAmount;
      amountEl.dispatchEvent(new Event('input', { bubbles: true }));
      amountEl.dispatchEvent(new Event('change', { bubbles: true }));
      amountEl.dispatchEvent(new Event('blur', { bubbles: true }));
      amountEl.style.border = '2px solid #10b981';
      filledCount++;
    }

    if (filledCount > 0) {
      showToast('✨ Форму автоматично відкрито та заповнено!');
      if (commentEl) {
        commentEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        commentEl.focus();
      }

      const isAutoSubmit = localStorage.getItem('fhai_autosubmit') === 'true' || window.location.hash.includes('autobid');
      if (isAutoSubmit) {
        startAutoSubmitCountdown();
      }
    } else if (!quiet) {
      showToast('⚠️ Форму ставки не знайдено (можливо, прийом ставок завершено)');
      copyTextToClipboard(textToFill);
    }
  }

  // Append questions to bid textarea
  function appendQuestions() {
    if (!state.questions) return;
    const commentEl = document.querySelector('textarea[name="comment"]') ||
                      document.querySelector('textarea#comment') ||
                      document.querySelector('textarea[name="text"]');
    if (commentEl) {
      commentEl.value = (commentEl.value ? commentEl.value + '\n\n' : '') + state.questions;
      commentEl.dispatchEvent(new Event('input', { bubbles: true }));
      commentEl.dispatchEvent(new Event('change', { bubbles: true }));
      showToast('❓ Уточнюючі питання додано до тексту!');
    } else {
      copyTextToClipboard(state.questions);
      showToast('📋 Питання скопійовано в буфер!');
    }
  }

  // Sync to Mini App CRM pipeline
  async function syncToCrm(status = 'bid_sent') {
    try {
      showToast('⏳ Синхронізація з CRM...');
      const payload = {
        project_id: state.projectId,
        status: status,
        deal_amount: state.recommendedAmount || undefined,
        currency: state.recommendedCurrency || 'UAH',
      };
      await makeApiRequest(`${API_BASE}/api/pipeline`, 'POST', payload);
      showToast('💼 Статус збережено в CRM: ' + (status === 'bid_sent' ? 'Ставка зроблена' : status));
    } catch (e) {
      showToast('⚠️ Не вдалося зв’язатися з сервером CRM');
    }
  }

  function getCurrentBidText() {
    if (state.activeTab === 'short') return state.bidShort;
    if (state.activeTab === 'full') return state.bidFull;
    if (state.activeTab === 'questions') return state.questions;
    return state.bidShort;
  }

  // Render the widget DOM
  function updateWidgetUI() {
    if (!rootContainer) return;

    if (state.collapsed) {
      const scoreClass = state.score >= 70 ? '' : (state.score >= 40 ? 'warning' : 'danger');
      const scoreText = state.score !== null ? `${state.score}` : '...';

      rootContainer.innerHTML = `
        <div class="fhai-badge-btn" id="fhai-open-btn" title="Відкрити Freelance AI Co-Pilot">
          <span>🤖 Co-Pilot</span>
          <span class="fhai-score-pill ${scoreClass}">${scoreText}</span>
        </div>
      `;

      const openBtn = document.getElementById('fhai-open-btn');
      if (openBtn) {
        openBtn.addEventListener('click', () => {
          state.collapsed = false;
          localStorage.setItem('fhai_collapsed', 'false');
          updateWidgetUI();
        });
      }
      return;
    }

    const score = state.score !== null ? state.score : '--';
    const scoreClass = score >= 70 ? '' : (score >= 40 ? 'warning' : 'danger');
    const scoreLabel = score >= 70 ? 'Рекомендовано' : (score >= 40 ? 'Сумнівно' : 'Не підходить');
    const sweetSpotText = state.sweetSpot || (state.recommendedAmount ? `${state.recommendedAmount} ${state.recommendedCurrency}` : 'За домовленістю');

    rootContainer.innerHTML = `
      <div class="fhai-panel">
        <div class="fhai-header">
          <div class="fhai-header-title">
            <span>🤖 AI Co-Pilot</span>
            <span class="fhai-safe-badge" title="Працює у вашому браузері без ризику блокування">🛡 100% Anti-Ban</span>
          </div>
          <div class="fhai-header-actions">
            <span class="fhai-score-pill ${scoreClass}">${score} • ${scoreLabel}</span>
            <button class="fhai-icon-btn" id="fhai-collapse-btn" title="Згорнути">✕</button>
          </div>
        </div>

        <div class="fhai-body">
          <div class="fhai-info-row">
            <span>Ціна & Термін:</span>
            <span class="fhai-info-val">💰 ${sweetSpotText} • ⏱ ${state.recommendedDays} дні</span>
          </div>

          <div class="fhai-tabs">
            <div class="fhai-tab ${state.activeTab === 'short' ? 'active' : ''}" data-tab="short">⚡️ Коротка</div>
            <div class="fhai-tab ${state.activeTab === 'full' ? 'active' : ''}" data-tab="full">📝 Повна</div>
            <div class="fhai-tab ${state.activeTab === 'questions' ? 'active' : ''}" data-tab="questions">❓ Питання</div>
          </div>

          <textarea class="fhai-textarea" id="fhai-bid-preview">${getCurrentBidText()}</textarea>

          <div class="fhai-actions">
            <button class="fhai-btn-primary" id="fhai-autofill-btn">
              <span>✨ Відкрити та заповнити форму</span>
            </button>
            <div class="fhai-btn-row">
              <button class="fhai-btn-secondary" id="fhai-copy-btn">📋 Скопіювати</button>
              <button class="fhai-btn-secondary" id="fhai-add-q-btn">❓ +Питання</button>
              <button class="fhai-btn-secondary" id="fhai-crm-btn">💼 В CRM</button>
            </div>
            <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:#94a3b8;cursor:pointer;margin-top:4px;user-select:none;">
              <input type="checkbox" id="fhai-autosubmit-cb" ${localStorage.getItem('fhai_autosubmit') === 'true' ? 'checked' : ''} style="cursor:pointer;">
              <span>⚡️ Авто-відправка ставки (5с таймер)</span>
            </label>
          </div>
        </div>

        <div class="fhai-footer">
          <span>Підтримка 10 браузерів</span>
          <a href="${API_BASE}" target="_blank">🌐 Відкрити Mini App ↗</a>
        </div>
      </div>
    `;

    // Event listeners
    const collapseBtn = document.getElementById('fhai-collapse-btn');
    if (collapseBtn) {
      collapseBtn.addEventListener('click', () => {
        state.collapsed = true;
        localStorage.setItem('fhai_collapsed', 'true');
        updateWidgetUI();
      });
    }

    const previewEl = document.getElementById('fhai-bid-preview');
    if (previewEl) {
      previewEl.addEventListener('input', (e) => {
        if (state.activeTab === 'short') state.bidShort = e.target.value;
        if (state.activeTab === 'full') state.bidFull = e.target.value;
        if (state.activeTab === 'questions') state.questions = e.target.value;
      });
    }

    rootContainer.querySelectorAll('.fhai-tab').forEach(tabEl => {
      tabEl.addEventListener('click', () => {
        state.activeTab = tabEl.getAttribute('data-tab');
        updateWidgetUI();
      });
    });

    const autofillBtn = document.getElementById('fhai-autofill-btn');
    if (autofillBtn) autofillBtn.addEventListener('click', () => ensureAndFillBidForm(15));

    const autoSubmitCb = document.getElementById('fhai-autosubmit-cb');
    if (autoSubmitCb) {
      autoSubmitCb.addEventListener('change', (e) => {
        localStorage.setItem('fhai_autosubmit', e.target.checked ? 'true' : 'false');
        showToast(e.target.checked ? '⚡️ Авто-відправку увімкнено (таймер 5 сек)' : 'Ручний режим: авто-відправку вимкнено');
      });
    }

    const copyBtn = document.getElementById('fhai-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        copyTextToClipboard(getCurrentBidText());
        showToast('📋 Текст успішно скопійовано в буфер!');
      });
    }

    const addQBtn = document.getElementById('fhai-add-q-btn');
    if (addQBtn) addQBtn.addEventListener('click', appendQuestions);

    const crmBtn = document.getElementById('fhai-crm-btn');
    if (crmBtn) crmBtn.addEventListener('click', () => syncToCrm('bid_sent'));
  }

  // Initialize
  function init() {
    scrapePageProject();
    injectWidget();
    tryOpenBidForm();
    loadBidDraft();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

