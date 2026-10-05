// The piece editor: shows the Markdown as readers will see it, while the house types.

document.addEventListener('DOMContentLoaded', () => {
  const body = document.querySelector('textarea[data-preview-url]');
  if (!body) return;

  const editor = document.createElement('div');
  editor.className = 'fc-editor';
  const preview = document.createElement('div');
  preview.className = 'fc-preview';
  preview.setAttribute('aria-label', 'Preview of the piece');
  body.parentNode.insertBefore(editor, body);
  editor.append(body, preview);

  const token = () => (document.cookie.match(/(?:^|; )csrftoken=([^;]*)/) || [])[1] || '';

  let timer;
  const render = async () => {
    if (!body.value.trim()) {
      preview.innerHTML = '<p class="fc-empty">The piece will show here as you type.</p>';
      return;
    }
    try {
      const response = await fetch(body.dataset.previewUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': decodeURIComponent(token()) },
        body: new URLSearchParams({ body: body.value }),
      });
      if (response.ok) preview.innerHTML = await response.text();
    } catch (error) { /* keep the last good preview */ }
  };

  body.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(render, 350); });
  render();
});
