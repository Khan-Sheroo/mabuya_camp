(function () {
  const app = document.getElementById('projectFilesApp');
  if (!app) return;

  const projectId = app.getAttribute('data-project-id');
  const keepKey = `mabuya-files-keep-open-${projectId}`;
  const openKey = `mabuya-files-open-${projectId}`;

  const fileInput = document.getElementById('fileInput');
  const uploadQueue = document.getElementById('uploadQueue');
  const uploadQueueBody = document.getElementById('uploadQueueBody');
  const uploadBtn = document.getElementById('uploadBtn');
  const clearQueueBtn = document.getElementById('clearQueueBtn');
  const applyAllLabel = document.getElementById('applyAllLabel');
  const applyAllLabelBtn = document.getElementById('applyAllLabelBtn');
  const uploadFolderSelect = document.getElementById('uploadFolderSelect');
  const errorEl = document.getElementById('uploadError');
  const successEl = document.getElementById('uploadSuccess');
  const folderError = document.getElementById('folderError');
  const newFolderName = document.getElementById('newFolderName');
  const createFolderBtn = document.getElementById('createFolderBtn');
  const renameFolderInput = document.getElementById('renameFolderInput');
  const renameFolderBtn = document.getElementById('renameFolderBtn');
  const renameFolderId = document.getElementById('renameFolderId');
  const folderBar = document.getElementById('folderBar');
  const filesFilter = document.getElementById('filesFilter');
  const keepFoldersOpen = document.getElementById('keepFoldersOpen');
  const viewAllBtn = document.getElementById('viewAllBtn');
  const viewImagesBtn = document.getElementById('viewImagesBtn');
  const fileTypeBtn = document.getElementById('fileTypeBtn');
  const sortBtn = document.getElementById('sortBtn');

  const uploadModalEl = document.getElementById('uploadModal');
  const newFolderModalEl = document.getElementById('newFolderModal');
  const renameFolderModalEl = document.getElementById('renameFolderModal');
  const uploadModal = uploadModalEl ? new bootstrap.Modal(uploadModalEl) : null;
  const newFolderModal = newFolderModalEl ? new bootstrap.Modal(newFolderModalEl) : null;
  const renameFolderModal = renameFolderModalEl ? new bootstrap.Modal(renameFolderModalEl) : null;

  const previewModalEl = document.getElementById('projectFilePreviewModal');
  const previewModal = previewModalEl ? new bootstrap.Modal(previewModalEl) : null;
  const previewTitle = document.getElementById('projectFilePreviewModalLabel');
  const previewBody = document.getElementById('projectFilePreviewBody');
  const previewDownload = document.getElementById('projectFilePreviewDownload');

  let queue = [];
  let viewMode = 'all';
  let fileType = 'all';
  let sortMode = 'manual';

  function showError(msg) {
    errorEl.textContent = msg || '';
    errorEl.classList.toggle('d-none', !msg);
    successEl.classList.add('d-none');
  }

  function showSuccess(msg) {
    successEl.textContent = msg || '';
    successEl.classList.toggle('d-none', !msg);
    errorEl.classList.add('d-none');
  }

  function showFolderError(msg) {
    folderError.textContent = msg || '';
    folderError.classList.toggle('d-none', !msg);
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function defaultLabelFromFilename(filename) {
    const name = String(filename || '').split(/[/\\]/).pop() || '';
    const stem = name.includes('.') ? name.slice(0, name.lastIndexOf('.')) : name;
    const cleaned = stem.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
    return (cleaned || name || 'Untitled').slice(0, 200);
  }

  function reloadPage() {
    window.location.href = `/projects/${projectId}/files`;
  }

  function getOpenSet() {
    try {
      return new Set(JSON.parse(localStorage.getItem(openKey) || '[]'));
    } catch (e) {
      return new Set();
    }
  }

  function saveOpenSet(set) {
    try {
      localStorage.setItem(openKey, JSON.stringify([...set]));
    } catch (e) { /* ignore */ }
  }

  function setFolderOpen(block, open) {
    block.classList.toggle('is-open', open);
    const toggle = block.querySelector('.docs-folder-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    const key = block.getAttribute('data-folder');
    const openSet = getOpenSet();
    if (open) openSet.add(key);
    else openSet.delete(key);
    saveOpenSet(openSet);
  }

  function applyKeepOpenPreference() {
    const keep = keepFoldersOpen.checked;
    try {
      localStorage.setItem(keepKey, keep ? '1' : '0');
    } catch (e) { /* ignore */ }
    if (keep) {
      folderBar.querySelectorAll('.docs-folder-block').forEach((block) => setFolderOpen(block, true));
    }
  }

  function restoreOpenState() {
    let keep = false;
    try {
      keep = localStorage.getItem(keepKey) === '1';
    } catch (e) { /* ignore */ }
    keepFoldersOpen.checked = keep;
    if (keep) {
      folderBar.querySelectorAll('.docs-folder-block').forEach((block) => setFolderOpen(block, true));
      return;
    }
    const openSet = getOpenSet();
    folderBar.querySelectorAll('.docs-folder-block').forEach((block) => {
      setFolderOpen(block, openSet.has(block.getAttribute('data-folder')));
    });
  }

  function applyFilters() {
    const q = (filesFilter.value || '').trim().toLowerCase();
    const type = viewMode === 'images' ? 'images' : fileType;

    folderBar.querySelectorAll('.docs-folder-block').forEach((block) => {
      const folderName = block.getAttribute('data-folder-name') || '';
      let visibleFiles = 0;

      block.querySelectorAll('.file-row').forEach((row) => {
        const isImage = row.getAttribute('data-is-image') === '1';
        const isPdf = row.getAttribute('data-is-pdf') === '1';
        const search = row.getAttribute('data-search') || '';
        let typeOk = true;
        if (type === 'images') typeOk = isImage;
        else if (type === 'pdf') typeOk = isPdf;
        else if (type === 'other') typeOk = !isImage && !isPdf;
        const textOk = !q || search.includes(q) || folderName.includes(q);
        const show = typeOk && textOk;
        row.classList.toggle('is-filtered-out', !show);
        if (show) visibleFiles += 1;
      });

      const empty = block.querySelector('.docs-folder-empty');
      if (empty) empty.classList.toggle('is-filtered-out', visibleFiles > 0 || q || type !== 'all');

      const folderMatch = !q || folderName.includes(q);
      const showBlock = folderMatch || visibleFiles > 0;
      block.classList.toggle('is-filtered-out', !showBlock);

      if (q && showBlock && visibleFiles > 0) {
        setFolderOpen(block, true);
      }
    });
  }

  function applySort() {
    if (sortMode === 'manual') return;
    const blocks = [...folderBar.querySelectorAll('.docs-folder-block')];
    blocks.sort((a, b) => {
      if (a.classList.contains('docs-folder-unfiled')) return 1;
      if (b.classList.contains('docs-folder-unfiled')) return -1;
      if (sortMode === 'name') {
        return (a.getAttribute('data-sort-name') || '').localeCompare(b.getAttribute('data-sort-name') || '');
      }
      return (b.getAttribute('data-sort-date') || '').localeCompare(a.getAttribute('data-sort-date') || '');
    });
    blocks.forEach((block) => folderBar.appendChild(block));

    folderBar.querySelectorAll('.docs-folder-block').forEach((block) => {
      const list = block.querySelector('.docs-file-list');
      if (!list) return;
      const rows = [...list.querySelectorAll('.file-row')];
      rows.sort((a, b) => {
        if (sortMode === 'name') {
          return (a.getAttribute('data-sort-name') || '').localeCompare(b.getAttribute('data-sort-name') || '');
        }
        return (b.getAttribute('data-sort-date') || '').localeCompare(a.getAttribute('data-sort-date') || '');
      });
      rows.forEach((row) => list.appendChild(row));
    });
  }

  function renderQueue() {
    uploadQueueBody.innerHTML = '';
    queue.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'upload-queue-row';
      row.innerHTML = `
        <div class="upload-queue-name">${escapeHtml(item.file.name)}</div>
        <input type="text" class="files-input queue-label" maxlength="200" data-id="${item.id}"
               value="${escapeHtml(item.label)}" placeholder="e.g. contract, photo">
        <button type="button" class="btn files-btn-danger btn-sm queue-remove" data-id="${item.id}">Remove</button>`;
      uploadQueueBody.appendChild(row);
    });
    const hasItems = queue.length > 0;
    uploadQueue.classList.toggle('is-visible', hasItems);
    uploadBtn.disabled = !hasItems;
    clearQueueBtn.disabled = !hasItems;
    uploadBtn.textContent = hasItems
      ? `Upload ${queue.length} file${queue.length === 1 ? '' : 's'}`
      : 'Upload selected';
  }

  function addFiles(fileList) {
    Array.from(fileList || []).forEach((file) => {
      queue.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        file,
        label: defaultLabelFromFilename(file.name),
      });
    });
    renderQueue();
  }

  function openUploadModal(folderId) {
    showError('');
    showSuccess('');
    uploadFolderSelect.value = folderId == null ? '' : String(folderId);
    if (uploadModal) uploadModal.show();
  }

  document.getElementById('newUploadBtn').addEventListener('click', () => openUploadModal(''));
  document.getElementById('newFolderBtn').addEventListener('click', () => {
    showFolderError('');
    newFolderName.value = '';
    if (newFolderModal) newFolderModal.show();
    setTimeout(() => newFolderName.focus(), 200);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files.length) addFiles(fileInput.files);
    fileInput.value = '';
  });

  uploadQueueBody.addEventListener('input', (e) => {
    const input = e.target.closest('.queue-label');
    if (!input) return;
    const item = queue.find((q) => q.id === input.getAttribute('data-id'));
    if (item) item.label = input.value;
  });

  uploadQueueBody.addEventListener('click', (e) => {
    const btn = e.target.closest('.queue-remove');
    if (!btn) return;
    queue = queue.filter((q) => q.id !== btn.getAttribute('data-id'));
    renderQueue();
  });

  clearQueueBtn.addEventListener('click', () => {
    queue = [];
    renderQueue();
  });

  applyAllLabelBtn.addEventListener('click', () => {
    const label = (applyAllLabel.value || '').trim();
    queue.forEach((item) => {
      item.label = label || defaultLabelFromFilename(item.file.name);
    });
    renderQueue();
  });

  uploadBtn.addEventListener('click', async () => {
    if (!queue.length) {
      showError('Choose one or more files to upload');
      return;
    }
    showError('');
    showSuccess('');
    const fd = new FormData();
    queue.forEach((item) => {
      fd.append('files', item.file);
      fd.append('labels', item.label || '');
    });
    const folderId = uploadFolderSelect.value || '';
    if (folderId) fd.append('folder_id', folderId);
    uploadBtn.disabled = true;
    try {
      const res = await fetch(`/projects/${projectId}/api/files`, {
        method: 'POST',
        body: fd,
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showError(data.error || 'Upload failed');
        uploadBtn.disabled = false;
        return;
      }
      if (uploadModal) uploadModal.hide();
      reloadPage();
    } catch (err) {
      showError('Upload failed. Please try again.');
      uploadBtn.disabled = false;
    }
  });

  createFolderBtn.addEventListener('click', async () => {
    const name = (newFolderName.value || '').trim();
    showFolderError('');
    if (!name) {
      showFolderError('Folder name is required');
      return;
    }
    createFolderBtn.disabled = true;
    try {
      const res = await fetch(`/projects/${projectId}/api/folders`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showFolderError(data.error || 'Could not create folder');
        return;
      }
      if (newFolderModal) newFolderModal.hide();
      reloadPage();
    } catch (err) {
      showFolderError('Could not create folder');
    } finally {
      createFolderBtn.disabled = false;
    }
  });

  newFolderName.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      createFolderBtn.click();
    }
  });

  renameFolderBtn.addEventListener('click', async () => {
    const id = renameFolderId.value;
    const name = (renameFolderInput.value || '').trim();
    showFolderError('');
    if (!id || !name) {
      showFolderError('Folder name is required');
      return;
    }
    renameFolderBtn.disabled = true;
    try {
      const res = await fetch(`/projects/${projectId}/api/folders/${id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showFolderError(data.error || 'Could not rename folder');
        return;
      }
      if (renameFolderModal) renameFolderModal.hide();
      reloadPage();
    } catch (err) {
      showFolderError('Could not rename folder');
    } finally {
      renameFolderBtn.disabled = false;
    }
  });

  folderBar.addEventListener('click', async (e) => {
    const toggle = e.target.closest('.docs-folder-toggle');
    if (toggle) {
      const block = toggle.closest('.docs-folder-block');
      if (!block) return;
      if (keepFoldersOpen.checked) return;
      setFolderOpen(block, !block.classList.contains('is-open'));
      return;
    }

    const uploadInto = e.target.closest('.folder-upload-btn');
    if (uploadInto) {
      openUploadModal(uploadInto.getAttribute('data-folder') || '');
      return;
    }

    const renameBtn = e.target.closest('.folder-rename-btn');
    if (renameBtn) {
      renameFolderId.value = renameBtn.getAttribute('data-folder');
      renameFolderInput.value = renameBtn.getAttribute('data-name') || '';
      if (renameFolderModal) renameFolderModal.show();
      setTimeout(() => renameFolderInput.focus(), 200);
      return;
    }

    const deleteBtn = e.target.closest('.folder-delete-btn');
    if (deleteBtn) {
      const folderId = deleteBtn.getAttribute('data-folder');
      if (!confirm('Delete this folder? Files will move to Unfiled.')) return;
      showFolderError('');
      try {
        const res = await fetch(`/projects/${projectId}/api/folders/${folderId}/delete`, {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            Accept: 'application/json',
          },
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          showFolderError(data.error || 'Could not delete folder');
          return;
        }
        reloadPage();
      } catch (err) {
        showFolderError('Could not delete folder');
      }
      return;
    }

    const previewBtn = e.target.closest('.preview-doc-btn');
    if (previewBtn) {
      openPreviewFromRow(previewBtn.closest('.file-row'));
      return;
    }

    const delDoc = e.target.closest('.delete-doc-btn');
    if (delDoc) {
      const docId = delDoc.getAttribute('data-doc-id');
      if (!confirm('Delete this file?')) return;
      try {
        const res = await fetch(`/projects/${projectId}/files/${docId}/delete`, {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            Accept: 'application/json',
          },
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          alert('Could not delete file');
          return;
        }
        reloadPage();
      } catch (err) {
        alert('Could not delete file');
      }
    }
  });

  function openPreviewFromRow(row) {
    if (!row || !previewModal) return;
    const docId = row.getAttribute('data-doc-id');
    const filename = row.getAttribute('data-filename') || 'Preview';
    const label = row.getAttribute('data-label') || '';
    const isImage = row.getAttribute('data-is-image') === '1';
    const isPdf = row.getAttribute('data-is-pdf') === '1';
    const viewUrl = `/projects/${projectId}/files/${docId}/download`;
    const downloadUrl = `${viewUrl}?download=1`;

    previewTitle.textContent = label ? `${filename} — ${label}` : filename;
    previewDownload.href = downloadUrl;
    previewBody.innerHTML = '';

    if (isImage) {
      const img = document.createElement('img');
      img.src = viewUrl;
      img.alt = filename;
      img.className = 'files-preview-img';
      previewBody.appendChild(img);
    } else if (isPdf) {
      const iframe = document.createElement('iframe');
      iframe.src = viewUrl;
      iframe.title = filename;
      iframe.className = 'files-preview-frame';
      previewBody.appendChild(iframe);
    } else {
      previewBody.innerHTML = `
        <div class="files-preview-fallback">
          <p>No in-app preview for this file type.</p>
          <a class="btn files-btn-primary" href="${downloadUrl}">Download to open</a>
        </div>`;
    }
    previewModal.show();
  }

  async function moveDocToFolder(docId, folderKey) {
    const folderId = folderKey === 'unfiled' || folderKey === 'all' || !folderKey ? null : folderKey;
    const res = await fetch(`/projects/${projectId}/files/${docId}/move`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ folder_id: folderId }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || 'Could not move file');
    }
  }

  async function uploadFilesToFolder(fileList, folderKey) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    const fd = new FormData();
    files.forEach((file) => {
      fd.append('files', file);
      fd.append('labels', defaultLabelFromFilename(file.name));
    });
    if (folderKey && folderKey !== 'unfiled' && folderKey !== 'all') {
      fd.append('folder_id', folderKey);
    }
    const res = await fetch(`/projects/${projectId}/api/files`, {
      method: 'POST',
      body: fd,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || 'Upload failed');
    }
    return data;
  }

  let dragAutoScrollActive = false;
  let dragAutoScrollY = 0;
  let dragAutoScrollRaf = null;
  const DRAG_SCROLL_EDGE = 80;
  const DRAG_SCROLL_MAX = 28;

  function stopDragAutoScroll() {
    dragAutoScrollActive = false;
    dragAutoScrollY = 0;
    if (dragAutoScrollRaf) {
      cancelAnimationFrame(dragAutoScrollRaf);
      dragAutoScrollRaf = null;
    }
  }

  function tickDragAutoScroll() {
    if (!dragAutoScrollActive) {
      dragAutoScrollRaf = null;
      return;
    }
    const y = dragAutoScrollY;
    const vh = window.innerHeight;
    let delta = 0;
    if (y < DRAG_SCROLL_EDGE) {
      delta = -Math.ceil(DRAG_SCROLL_MAX * (1 - y / DRAG_SCROLL_EDGE));
    } else if (y > vh - DRAG_SCROLL_EDGE) {
      delta = Math.ceil(DRAG_SCROLL_MAX * (1 - (vh - y) / DRAG_SCROLL_EDGE));
    }
    if (delta) window.scrollBy(0, delta);
    dragAutoScrollRaf = requestAnimationFrame(tickDragAutoScroll);
  }

  function startDragAutoScroll() {
    dragAutoScrollActive = true;
    if (!dragAutoScrollRaf) {
      dragAutoScrollRaf = requestAnimationFrame(tickDragAutoScroll);
    }
  }

  document.addEventListener('dragover', (e) => {
    if (!dragAutoScrollActive) return;
    dragAutoScrollY = e.clientY;
    e.preventDefault();
  });

  folderBar.addEventListener('dragstart', (e) => {
    const row = e.target.closest('.file-row');
    if (!row) return;
    if (e.target.closest('button, a, select, input')) {
      e.preventDefault();
      return;
    }
    const docId = row.getAttribute('data-doc-id');
    e.dataTransfer.setData('application/x-project-doc-id', docId);
    e.dataTransfer.setData('text/plain', docId);
    e.dataTransfer.effectAllowed = 'move';
    row.classList.add('dragging');
    startDragAutoScroll();
  });

  folderBar.addEventListener('dragend', (e) => {
    const row = e.target.closest('.file-row');
    if (row) row.classList.remove('dragging');
    document.querySelectorAll('.docs-folder-block.drag-over').forEach((el) => el.classList.remove('drag-over'));
    stopDragAutoScroll();
  });

  document.addEventListener('dragenter', (e) => {
    if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) {
      startDragAutoScroll();
    }
  });
  document.addEventListener('drop', stopDragAutoScroll);
  window.addEventListener('dragend', stopDragAutoScroll);

  folderBar.addEventListener('dragover', (e) => {
    const block = e.target.closest('.docs-folder-block.drop-target');
    if (!block) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = e.dataTransfer.types.includes('Files') ? 'copy' : 'move';
    block.classList.add('drag-over');
  });

  folderBar.addEventListener('dragleave', (e) => {
    const block = e.target.closest('.docs-folder-block.drop-target');
    if (!block) return;
    if (!block.contains(e.relatedTarget)) {
      block.classList.remove('drag-over');
    }
  });

  folderBar.addEventListener('drop', async (e) => {
    const block = e.target.closest('.docs-folder-block.drop-target');
    if (!block) return;
    e.preventDefault();
    block.classList.remove('drag-over');
    const folderKey = block.getAttribute('data-folder');

    try {
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        showFolderError('');
        await uploadFilesToFolder(e.dataTransfer.files, folderKey);
        reloadPage();
        return;
      }

      const docId =
        e.dataTransfer.getData('application/x-project-doc-id') ||
        e.dataTransfer.getData('text/plain');
      if (!docId) return;
      await moveDocToFolder(docId, folderKey);
      reloadPage();
    } catch (err) {
      showFolderError(err.message || 'Drop failed');
    }
  });

  viewAllBtn.addEventListener('click', () => {
    viewMode = 'all';
    viewAllBtn.classList.add('is-active');
    viewImagesBtn.classList.remove('is-active');
    applyFilters();
  });

  viewImagesBtn.addEventListener('click', () => {
    viewMode = 'images';
    viewImagesBtn.classList.add('is-active');
    viewAllBtn.classList.remove('is-active');
    applyFilters();
  });

  document.getElementById('fileTypeMenu').addEventListener('click', (e) => {
    const item = e.target.closest('[data-type]');
    if (!item) return;
    fileType = item.getAttribute('data-type');
    document.querySelectorAll('#fileTypeMenu .dropdown-item').forEach((el) => {
      el.classList.toggle('is-active', el === item);
    });
    const labels = { all: 'File type', images: 'Images', pdf: 'PDFs', other: 'Other' };
    fileTypeBtn.innerHTML = `${labels[fileType] || 'File type'} <i class="bi bi-chevron-down"></i>`;
    if (fileType === 'images') {
      viewMode = 'images';
      viewImagesBtn.classList.add('is-active');
      viewAllBtn.classList.remove('is-active');
    } else if (viewMode === 'images' && fileType === 'all') {
      viewMode = 'all';
      viewAllBtn.classList.add('is-active');
      viewImagesBtn.classList.remove('is-active');
    }
    applyFilters();
  });

  document.getElementById('sortMenu').addEventListener('click', (e) => {
    const item = e.target.closest('[data-sort]');
    if (!item) return;
    sortMode = item.getAttribute('data-sort');
    document.querySelectorAll('#sortMenu .dropdown-item').forEach((el) => {
      el.classList.toggle('is-active', el === item);
    });
    const labels = { manual: 'Sort manually', name: 'Name A–Z', newest: 'Newest first' };
    sortBtn.innerHTML = `${labels[sortMode] || 'Sort'} <i class="bi bi-chevron-down"></i>`;
    applySort();
  });

  filesFilter.addEventListener('input', applyFilters);
  keepFoldersOpen.addEventListener('change', applyKeepOpenPreference);

  if (previewModalEl) {
    previewModalEl.addEventListener('hidden.bs.modal', () => {
      previewBody.innerHTML = '';
    });
  }

  restoreOpenState();
  applyFilters();
})();
