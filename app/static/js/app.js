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
      if (!confirm(`Send TZS ${parseFloat(amount).toLocaleString()} to account ${to}?\n\nThis action cannot be undone.`)) {
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
      if (!confirm(`Pay TZS ${parseFloat(amount).toLocaleString()} to ${billerName}?\n\nThis action cannot be undone.`)) {
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
});
