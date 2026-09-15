(function () {
  const app = document.getElementById('projectMessagesApp');
  if (!app) return;

  const projectId = app.getAttribute('data-project-id');
  const filterInput = document.getElementById('messagesFilter');
  const list = document.getElementById('messagesList');
  const filterEmpty = document.getElementById('messagesFilterEmpty');
  const errorEl = document.getElementById('messagesError');
  const newCategoryBtn = document.getElementById('newCategoryBtn');
  const createCategoryBtn = document.getElementById('createCategoryBtn');
  const newCategoryName = document.getElementById('newCategoryName');
  const modalEl = document.getElementById('newCategoryModal');
  const modal = modalEl ? new bootstrap.Modal(modalEl) : null;

  function showError(msg) {
    if (!errorEl) return;
    errorEl.textContent = msg || '';
    errorEl.classList.toggle('d-none', !msg);
  }

  if (filterInput && list) {
    filterInput.addEventListener('input', () => {
      const q = (filterInput.value || '').trim().toLowerCase();
      let visible = 0;
      list.querySelectorAll('.message-row').forEach((row) => {
        const hay = row.getAttribute('data-search') || '';
        const show = !q || hay.includes(q);
        row.classList.toggle('is-filtered-out', !show);
        if (show) visible += 1;
      });
      if (filterEmpty) {
        filterEmpty.classList.toggle('d-none', visible > 0 || !q);
      }
    });
  }

  if (newCategoryBtn && modal) {
    newCategoryBtn.addEventListener('click', () => {
      showError('');
      newCategoryName.value = '';
      modal.show();
      setTimeout(() => newCategoryName.focus(), 200);
    });
  }

  async function createCategory() {
    const name = (newCategoryName.value || '').trim();
    showError('');
    if (!name) {
      showError('Category name is required');
      return;
    }
    createCategoryBtn.disabled = true;
    try {
      const res = await fetch(`/projects/${projectId}/api/message-categories`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showError(data.error || 'Could not create category');
        return;
      }
      if (modal) modal.hide();
      window.location.href = `/projects/${projectId}/messages?category=${data.category.id}`;
    } catch (err) {
      showError('Could not create category');
    } finally {
      createCategoryBtn.disabled = false;
    }
  }

  if (createCategoryBtn) {
    createCategoryBtn.addEventListener('click', createCategory);
  }
  if (newCategoryName) {
    newCategoryName.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        createCategory();
      }
    });
  }
})();
