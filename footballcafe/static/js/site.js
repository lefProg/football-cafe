// Football Cafe: ticking the coupon and posting a reply. Both talk to the API under /api/pieces/.

(() => {
  const cookie = (name) => {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  };

  const post = (url, body) => fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': cookie('csrftoken') },
    body: JSON.stringify(body),
  });

  // ---------- the coupon ----------
  const coupon = document.querySelector('[data-coupon]');
  if (coupon) {
    const count = coupon.querySelector('[data-count]');
    const handIn = coupon.querySelector('[data-hand-in]');
    const verdict = coupon.querySelector('[data-verdict]');
    const oops = coupon.querySelector('[data-oops]');
    let verdictText = verdict.querySelector('span').textContent;

    // A full coupon from an earlier visit shows its verdict straight away; otherwise it waits to be handed in.
    handIn.hidden = !verdict.hidden;

    coupon.addEventListener('submit', async (event) => {
      const form = event.target.closest('.boxes');
      const button = event.submitter;
      if (!form || !button) return;
      event.preventDefault();
      oops.hidden = true;

      let data;
      try {
        const response = await post(form.dataset.voteUrl, { choice: Number(button.value) });
        if (!response.ok) throw new Error(response.status);
        data = await response.json();
      } catch (error) {
        oops.hidden = false;
        return;
      }

      const row = form.closest('[data-claim]');
      form.querySelectorAll('.vote').forEach((other) => other.setAttribute('aria-pressed', other === button));
      row.querySelector('.fill').style.width = data.claim.percent_agree + '%';
      row.querySelector('.cap').textContent = data.claim.percent_agree + '% of the cafe agrees';
      row.classList.add('voted');
      count.textContent = data.coupon.ticked + ' of ' + data.coupon.total + ' ticked';

      verdictText = data.coupon.verdict;
      if (!verdict.hidden) verdict.querySelector('span').textContent = verdictText;
      else handIn.disabled = !verdictText;
    });

    handIn.addEventListener('click', () => {
      verdict.querySelector('span').textContent = verdictText;
      verdict.hidden = false;
      handIn.hidden = true;
    });
  }

  // ---------- your turn ----------
  const REJECTED = 3;
  const replyForm = document.querySelector('[data-reply-form]');
  if (replyForm) {
    const nickname = replyForm.querySelector('[name=nickname]');
    const text = replyForm.querySelector('[name=text]');
    const trap = replyForm.querySelector('[name=website]');
    const button = replyForm.querySelector('button');
    const result = replyForm.querySelector('[data-result]');
    const label = button.textContent;

    try { nickname.value = localStorage.getItem('fc-nickname') || ''; } catch (error) { /* storage is optional */ }

    // The API answers 201 with {status, message}, or an error: {field: [reasons]} or {detail: reason}.
    const problem = (errors) => errors.detail || Object.values(errors).flat()[0] || 'Your reply could not be posted.';

    replyForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      button.disabled = true;
      button.textContent = 'The moderator is reading';
      result.textContent = '';

      let message, bad;
      try {
        const response = await post(replyForm.dataset.replyUrl, {
          nickname: nickname.value, text: text.value, website: trap.value,
        });
        const data = await response.json();
        if (response.ok) {
          message = data.message;
          bad = data.status === REJECTED;
          if (!bad) text.value = '';
          try { localStorage.setItem('fc-nickname', nickname.value); } catch (error) { /* storage is optional */ }
        } else {
          message = problem(data);
          bad = true;
        }
      } catch (error) {
        message = 'Your reply did not get through. Check your connection and post it again.';
        bad = true;
      }

      result.textContent = message;
      result.classList.toggle('bad', bad);
      button.disabled = false;
      button.textContent = label;
    });
  }
})();
