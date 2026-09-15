(function () {
  const root = document.getElementById('messageComposer');
  if (!root) return;

  const form = document.getElementById('messageComposerForm');
  const intentInput = document.getElementById('messageIntent');
  const titleInput = document.getElementById('messageTitle');
  const bodyHidden = document.getElementById('messageBodyHidden');
  const editor = document.getElementById('messageBodyEditor');
  const categoryInput = document.getElementById('messageCategory');
  const categoryLabel = document.getElementById('composerCategoryLabel');
  const selectPeople = document.getElementById('composerSelectPeople');

  function syncBody() {
    if (!editor || !bodyHidden) return;
    const html = editor.innerHTML.trim();
    const empty = html === '' || html === '<br>' || html === '<div><br></div>';
    bodyHidden.value = empty ? '' : editor.innerHTML;
  }

  function syncPlaceholder() {
    if (!editor) return;
    const text = (editor.textContent || '').replace(/\u00a0/g, ' ').trim();
    const html = editor.innerHTML.trim();
    const empty = !text && (html === '' || html === '<br>' || html === '<div><br></div>');
    editor.classList.toggle('is-empty', empty);
  }

  form.querySelectorAll('[data-intent]').forEach((btn) => {
    btn.addEventListener('click', () => {
      intentInput.value = btn.getAttribute('data-intent') || 'post';
    });
  });

  form.addEventListener('submit', (e) => {
    syncBody();
    if (!(titleInput.value || '').trim()) {
      e.preventDefault();
      titleInput.focus();
      return;
    }
  });

  document.querySelectorAll('.composer-cat-option').forEach((btn) => {
    btn.addEventListener('click', () => {
      categoryInput.value = btn.getAttribute('data-value') || '';
      categoryLabel.textContent = btn.getAttribute('data-label') || 'Pick a category (optional)';
    });
  });

  document.querySelectorAll('input[name="notify_mode"]').forEach((radio) => {
    radio.addEventListener('change', () => {
      if (!selectPeople) return;
      selectPeople.classList.toggle('d-none', radio.value !== 'select' || !radio.checked);
      if (radio.value === 'select' && radio.checked) {
        selectPeople.classList.remove('d-none');
      } else if (document.querySelector('input[name="notify_mode"][value="select"]').checked) {
        selectPeople.classList.remove('d-none');
      } else {
        selectPeople.classList.add('d-none');
      }
    });
  });

  // Ensure select panel visibility on load
  const selectedMode = document.querySelector('input[name="notify_mode"]:checked');
  if (selectPeople) {
    selectPeople.classList.toggle('d-none', !(selectedMode && selectedMode.value === 'select'));
  }

  document.querySelectorAll('.composer-tool').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const cmd = btn.getAttribute('data-cmd');
      const value = btn.getAttribute('data-value') || null;
      editor.focus();

      if (cmd === 'attach' || cmd === 'insertImage') {
        const url = window.prompt(cmd === 'insertImage' ? 'Image URL' : 'Link URL');
        if (!url) return;
        if (cmd === 'insertImage') {
          document.execCommand('insertImage', false, url);
        } else {
          document.execCommand('createLink', false, url);
        }
        syncPlaceholder();
        return;
      }

      if (cmd === 'createLink') {
        const url = window.prompt('Link URL');
        if (!url) return;
        document.execCommand('createLink', false, url);
        syncPlaceholder();
        return;
      }

      if (cmd === 'formatBlock') {
        document.execCommand('formatBlock', false, value || 'p');
      } else if (cmd === 'foreColor') {
        document.execCommand('foreColor', false, value || '#5b9cf5');
      } else {
        document.execCommand(cmd, false, value);
      }
      syncPlaceholder();
    });
  });

  editor.addEventListener('input', syncPlaceholder);
  editor.addEventListener('blur', syncBody);
  syncPlaceholder();
})();
