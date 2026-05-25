/* SecureMoney — app.js */

/* ── OTP input auto-advance ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const boxes = document.querySelectorAll('.otp-box');
  const hiddenInput = document.getElementById('otp-hidden');

  if (boxes.length) {
    boxes.forEach((box, i) => {
      box.addEventListener('input', (e) => {
        const val = e.target.value.replace(/\D/g, '');
        box.value = val.slice(-1);
        if (val && i < boxes.length - 1) boxes[i + 1].focus();
        syncOTP();
      });

      box.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !box.value && i > 0) {
          boxes[i - 1].focus();
          boxes[i - 1].value = '';
          syncOTP();
        }
      });

      box.addEventListener('paste', (e) => {
        e.preventDefault();
        const text = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '');
        boxes.forEach((b, j) => { b.value = text[j] || ''; });
        syncOTP();
        boxes[Math.min(text.length, boxes.length) - 1].focus();
      });
    });

    function syncOTP() {
      if (hiddenInput) hiddenInput.value = Array.from(boxes).map(b => b.value).join('');
    }
  }

  /* ── Session timeout countdown ─────────────────────────────────────────── */
  const timerEl = document.getElementById('session-timer');
  if (timerEl) {
    const timeoutMinutes = parseInt(timerEl.dataset.timeout || '15', 10);
    let remaining = timeoutMinutes * 60;

    const interval = setInterval(() => {
      remaining--;
      const m = Math.floor(remaining / 60).toString().padStart(2, '0');
      const s = (remaining % 60).toString().padStart(2, '0');
      timerEl.textContent = `${m}:${s}`;

      if (remaining <= 60) timerEl.style.color = 'var(--warning)';
      if (remaining <= 0) {
        clearInterval(interval);
        window.location.href = '/auth/logout';
      }
    }, 1000);

    // Reset on user activity
    ['click', 'keydown', 'scroll', 'mousemove'].forEach(ev => {
      document.addEventListener(ev, () => { remaining = timeoutMinutes * 60; }, { passive: true });
    });
  }

  /* ── Amount formatting ─────────────────────────────────────────────────── */
  document.querySelectorAll('.format-amount').forEach(input => {
    input.addEventListener('blur', () => {
      const v = parseFloat(input.value.replace(/,/g, ''));
      if (!isNaN(v)) input.value = v.toFixed(2);
    });
  });

  /* ── Confirm transfer modal ─────────────────────────────────────────────── */
  const transferForm = document.getElementById('transfer-form');
  if (transferForm) {
    transferForm.addEventListener('submit', (e) => {
      const amount  = document.getElementById('amount')?.value;
      const to      = document.getElementById('to_account')?.value;
      if (!confirm(i18n('confirm-transfer', {amount: parseFloat(amount).toLocaleString(), to: to}))) {
        e.preventDefault();
      }
    });
  }

  /* ── Bill payment confirm ───────────────────────────────────────────────── */
  const billForm = document.getElementById('bill-form');
  if (billForm) {
    billForm.addEventListener('submit', (e) => {
      const amount  = document.getElementById('amount')?.value;
      const biller  = document.getElementById('biller');
      const billerName = biller?.options[biller.selectedIndex]?.text || '';
      if (!confirm(i18n('confirm-bill', {amount: parseFloat(amount).toLocaleString(), biller: billerName}))) {
        e.preventDefault();
      }
    });
  }

  /* ── Auto-dismiss alerts ────────────────────────────────────────────────── */
  document.querySelectorAll('.sm-alert[data-auto-dismiss]').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity .5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 5000);
  });

  /* ── Table row click ────────────────────────────────────────────────────── */
  document.querySelectorAll('tr[data-href]').forEach(row => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => window.location = row.dataset.href);
  });

  /* ── Language Switcher Logic ───────────────────────────────────────────── */
  const setLanguage = (lang) => {
    localStorage.setItem('preferredLanguage', lang);
    
    // Update UI labels and flags
    const flagMap = { 'en': '🇬🇧', 'sw': '🇹🇿' };
    const labelMap = { 'en': 'English', 'sw': 'Kiswahili' };
    
    document.querySelectorAll('[data-current-lang-flag]').forEach(el => el.innerText = flagMap[lang]);
    document.querySelectorAll('[data-current-lang-label]').forEach(el => el.innerText = labelMap[lang]);
    
    // Perform instant translation with a subtle transition
    if (typeof updatePageLanguage === 'function') {
      document.body.classList.add('switching-language');
      document.body.style.transition = 'opacity 0.15s ease';
      document.body.style.opacity = '0.5';
      setTimeout(() => {
        updatePageLanguage();
        document.body.style.opacity = '1';
      }, 150);
    }
  };

  // Handle button clicks in switcher (event delegation = works on all pages)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-lang-option]');
    if (!btn) return;
    const lang = btn.getAttribute('data-lang-option');
    setLanguage(lang);
  });

  // Initialize Language
  let currentLang = localStorage.getItem('preferredLanguage');
  if (!currentLang) {
    // Auto-detect browser language
    const browserLang = navigator.language || navigator.userLanguage;
    currentLang = browserLang.startsWith('sw') ? 'sw' : 'en';
    localStorage.setItem('preferredLanguage', currentLang);
  }
  setLanguage(currentLang);

  // Dropdown UI toggle
  document.querySelectorAll('[data-lang-toggle]').forEach(toggle => {
    toggle.addEventListener('click', (e) => {
      toggle.parentElement.classList.toggle('active');
      e.stopPropagation();
    });
  });
  document.addEventListener('click', () => document.querySelectorAll('.language-switcher').forEach(s => s.classList.remove('active')));
});
