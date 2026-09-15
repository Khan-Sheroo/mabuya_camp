(function () {
  const app = document.getElementById('projectScheduleApp');
  if (!app) return;

  const projectId = app.getAttribute('data-project-id');
  const windowStart = app.getAttribute('data-window-start');
  const filterInput = document.getElementById('scheduleFilter');
  const errorEl = document.getElementById('scheduleError');
  const newEventBtn = document.getElementById('newEventBtn');
  const eventModalEl = document.getElementById('eventModal');
  const eventModal = eventModalEl ? new bootstrap.Modal(eventModalEl) : null;
  const todoPeekEl = document.getElementById('todoPeekModal');
  const todoPeekModal = todoPeekEl ? new bootstrap.Modal(todoPeekEl) : null;

  const eventIdInput = document.getElementById('eventId');
  const eventTitle = document.getElementById('eventTitle');
  const eventDate = document.getElementById('eventDate');
  const eventSubtitle = document.getElementById('eventSubtitle');
  const eventNotes = document.getElementById('eventNotes');
  const saveEventBtn = document.getElementById('saveEventBtn');
  const deleteEventBtn = document.getElementById('deleteEventBtn');
  const modalLabel = document.getElementById('eventModalLabel');

  function showError(msg) {
    errorEl.textContent = msg || '';
    errorEl.classList.toggle('d-none', !msg);
  }

  function reload(view) {
    const params = new URLSearchParams();
    if (windowStart) params.set('start', windowStart);
    if (view) params.set('view', view);
    else if (app.getAttribute('data-view')) params.set('view', app.getAttribute('data-view'));
    const qs = params.toString();
    window.location.href = `/projects/${projectId}/schedule${qs ? `?${qs}` : ''}`;
  }

  function clearAssigneeChecks() {
    document.querySelectorAll('#eventAssignees input[type="checkbox"]').forEach((cb) => {
      cb.checked = false;
    });
  }

  function setAssigneeChecks(ids) {
    const set = new Set((ids || []).map(String));
    document.querySelectorAll('#eventAssignees input[type="checkbox"]').forEach((cb) => {
      cb.checked = set.has(cb.value);
    });
  }

  function openNewEvent(dateIso) {
    eventIdInput.value = '';
    eventTitle.value = '';
    eventSubtitle.value = '';
    eventNotes.value = '';
    eventDate.value = dateIso || new Date().toISOString().slice(0, 10);
    clearAssigneeChecks();
    modalLabel.textContent = 'New event';
    deleteEventBtn.classList.add('d-none');
    saveEventBtn.textContent = 'Save event';
    if (eventModal) eventModal.show();
    setTimeout(() => eventTitle.focus(), 200);
  }

  function openEditEvent(article) {
    eventIdInput.value = article.getAttribute('data-id');
    eventTitle.value = article.getAttribute('data-title') || '';
    eventSubtitle.value = article.getAttribute('data-subtitle') || '';
    eventNotes.value = article.getAttribute('data-notes') || '';
    eventDate.value = article.getAttribute('data-date') || '';
    clearAssigneeChecks();
    article.querySelectorAll('.schedule-avatar').forEach((av) => {
      const name = av.getAttribute('title');
      document.querySelectorAll('#eventAssignees .schedule-assignee-option').forEach((opt) => {
        const label = opt.querySelector('span:last-child');
        if (label && label.textContent.trim() === name) {
          opt.querySelector('input').checked = true;
        }
      });
    });
    modalLabel.textContent = 'Edit event';
    deleteEventBtn.classList.remove('d-none');
    saveEventBtn.textContent = 'Save changes';
    if (eventModal) eventModal.show();
  }

  function openTodoPeek(article) {
    document.getElementById('todoPeekTitle').textContent = article.getAttribute('data-title') || 'To-do';
    document.getElementById('todoPeekSub').textContent = article.getAttribute('data-subtitle') || '';
    const notes = article.getAttribute('data-notes') || '';
    const notesEl = document.getElementById('todoPeekNotes');
    notesEl.textContent = notes;
    notesEl.classList.toggle('d-none', !notes.trim());
    const todoId = article.getAttribute('data-todo-id');
    document.getElementById('todoPeekLink').href =
      `/projects/${projectId}/todos${todoId ? `#todo-${todoId}` : ''}`;
    if (todoPeekModal) todoPeekModal.show();
  }

  newEventBtn.addEventListener('click', () => openNewEvent());

  app.addEventListener('click', async (e) => {
    const addBtn = e.target.closest('[data-new-on]');
    if (addBtn) {
      openNewEvent(addBtn.getAttribute('data-new-on'));
      return;
    }

    const toggle = e.target.closest('[data-toggle-event]');
    if (toggle) {
      e.preventDefault();
      const id = toggle.getAttribute('data-toggle-event');
      try {
        const res = await fetch(`/projects/${projectId}/api/events/${id}/toggle`, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          showError(data.error || 'Could not update event');
          return;
        }
        reload();
      } catch (err) {
        showError('Could not update event');
      }
      return;
    }

    const openBtn = e.target.closest('[data-open-item]');
    if (openBtn) {
      const article = openBtn.closest('.schedule-item');
      if (!article) return;
      if (article.getAttribute('data-kind') === 'todo') {
        openTodoPeek(article);
      } else {
        openEditEvent(article);
      }
    }
  });

  saveEventBtn.addEventListener('click', async () => {
    const title = (eventTitle.value || '').trim();
    const dateVal = eventDate.value;
    showError('');
    if (!title) {
      showError('Title is required');
      return;
    }
    if (!dateVal) {
      showError('Date is required');
      return;
    }

    const assigneeIds = [...document.querySelectorAll('#eventAssignees input:checked')].map((cb) => cb.value);
    const payload = {
      title,
      event_date: dateVal,
      subtitle: (eventSubtitle.value || '').trim(),
      notes: (eventNotes.value || '').trim(),
      assignee_ids: assigneeIds,
    };

    const id = eventIdInput.value;
    const url = id
      ? `/projects/${projectId}/api/events/${id}`
      : `/projects/${projectId}/api/events`;

    saveEventBtn.disabled = true;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showError(data.error || 'Could not save event');
        return;
      }
      if (eventModal) eventModal.hide();
      reload();
    } catch (err) {
      showError('Could not save event');
    } finally {
      saveEventBtn.disabled = false;
    }
  });

  deleteEventBtn.addEventListener('click', async () => {
    const id = eventIdInput.value;
    if (!id || !confirm('Delete this event?')) return;
    try {
      const res = await fetch(`/projects/${projectId}/api/events/${id}/delete`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showError(data.error || 'Could not delete event');
        return;
      }
      if (eventModal) eventModal.hide();
      reload();
    } catch (err) {
      showError('Could not delete event');
    }
  });

  filterInput.addEventListener('input', () => {
    const q = (filterInput.value || '').trim().toLowerCase();
    document.querySelectorAll('.schedule-item').forEach((item) => {
      const hay = item.getAttribute('data-search') || '';
      item.classList.toggle('is-filtered-out', q && !hay.includes(q));
    });
  });

  eventTitle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      saveEventBtn.click();
    }
  });

  // Infinite scroll: load more weeks as you reach the edges
  const calendar = document.getElementById('scheduleCalendar');
  const weeksEl = document.getElementById('scheduleWeeks');
  const navLabel = document.getElementById('scheduleNavLabel');
  const prevBtn = document.getElementById('schedulePrevBtn');
  const nextBtn = document.getElementById('scheduleNextBtn');
  const CHUNK = 6;
  let loadingWeeks = false;

  function parseIso(iso) {
    const [y, m, d] = (iso || '').split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  function formatIso(dt) {
    const y = dt.getFullYear();
    const m = String(dt.getMonth() + 1).padStart(2, '0');
    const d = String(dt.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function addDays(iso, days) {
    const dt = parseIso(iso);
    dt.setDate(dt.getDate() + days);
    return formatIso(dt);
  }

  function getRange() {
    return {
      start: calendar.getAttribute('data-range-start'),
      end: calendar.getAttribute('data-range-end'),
    };
  }

  function setRange(start, end) {
    calendar.setAttribute('data-range-start', start);
    calendar.setAttribute('data-range-end', end);
  }

  function applyFilterToNewItems() {
    const q = (filterInput.value || '').trim().toLowerCase();
    if (!q) return;
    weeksEl.querySelectorAll('.schedule-item').forEach((item) => {
      const hay = item.getAttribute('data-search') || '';
      item.classList.toggle('is-filtered-out', !hay.includes(q));
    });
  }

  function updateNavLabel(fallback) {
    if (!navLabel) return;
    if (fallback) {
      navLabel.textContent = fallback;
      return;
    }
    const weeks = [...weeksEl.querySelectorAll('.schedule-week')];
    let visible = null;
    const mid = window.scrollY + window.innerHeight * 0.35;
    for (const week of weeks) {
      const rect = week.getBoundingClientRect();
      const top = rect.top + window.scrollY;
      const bottom = top + rect.height;
      if (mid >= top && mid <= bottom) {
        visible = week;
        break;
      }
    }
    if (!visible && weeks.length) visible = weeks[0];
    if (!visible) return;
    const startIso = visible.getAttribute('data-week-start');
    const start = parseIso(startIso);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todaySun = new Date(today);
    todaySun.setDate(today.getDate() - ((today.getDay() + 7) % 7));
    if (formatIso(start) === formatIso(todaySun)) {
      navLabel.textContent = 'Next 6 Weeks';
    } else if (start < todaySun) {
      navLabel.textContent = 'Previous weeks';
    } else {
      navLabel.textContent = start.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    }
  }

  async function fetchWeeks(startIso, weeksCount) {
    const params = new URLSearchParams({
      start: startIso,
      weeks: String(weeksCount),
    });
    const res = await fetch(`/projects/${projectId}/api/schedule/weeks?${params}`, {
      headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || 'Could not load dates');
    }
    return data;
  }

  async function loadMoreForward() {
    if (!calendar || !weeksEl || loadingWeeks) return;
    loadingWeeks = true;
    calendar.classList.add('is-loading-weeks');
    try {
      const { end } = getRange();
      const data = await fetchWeeks(addDays(end, 1), CHUNK);
      weeksEl.insertAdjacentHTML('beforeend', data.html);
      setRange(getRange().start, data.end);
      applyFilterToNewItems();
      updateNavLabel(data.nav_label);
    } catch (err) {
      showError(err.message || 'Could not load more dates');
    } finally {
      loadingWeeks = false;
      calendar.classList.remove('is-loading-weeks');
    }
  }

  async function loadMoreBackward() {
    if (!calendar || !weeksEl || loadingWeeks) return;
    loadingWeeks = true;
    calendar.classList.add('is-loading-weeks');
    try {
      const { start } = getRange();
      const data = await fetchWeeks(addDays(start, -(CHUNK * 7)), CHUNK);
      const marker = weeksEl.firstElementChild;
      weeksEl.insertAdjacentHTML('afterbegin', data.html);
      setRange(data.start, getRange().end);
      applyFilterToNewItems();
      updateNavLabel(data.nav_label);
      // Jump to the first newly inserted week without fighting scroll anchoring
      const inserted = marker
        ? marker.previousElementSibling
        : weeksEl.querySelector('.schedule-week');
      if (inserted) {
        const top = inserted.getBoundingClientRect().top + window.scrollY - 80;
        window.scrollTo({ top: Math.max(0, top), behavior: 'auto' });
      }
    } catch (err) {
      showError(err.message || 'Could not load earlier dates');
    } finally {
      loadingWeeks = false;
      calendar.classList.remove('is-loading-weeks');
    }
  }

  function onScroll() {
    if (!calendar || app.getAttribute('data-view') !== 'calendar') return;

    const docBottom = document.documentElement.scrollHeight - window.innerHeight;
    const nearBottom = window.scrollY >= docBottom - 480;

    // Only extend forward on scroll — never prepend on reach-top (that causes bounce-back)
    if (nearBottom) {
      loadMoreForward();
    }

    updateNavLabel();
  }

  if (calendar && weeksEl) {
    window.addEventListener('scroll', onScroll, { passive: true });
    updateNavLabel();

    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        loadMoreBackward();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener('click', async () => {
        const before = weeksEl.querySelectorAll('.schedule-week').length;
        await loadMoreForward();
        const weeks = weeksEl.querySelectorAll('.schedule-week');
        const target = weeks[Math.min(before, weeks.length - 1)];
        if (target) {
          const top = target.getBoundingClientRect().top + window.scrollY - 80;
          window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
        }
      });
    }

    // If the initial calendar is shorter than the viewport, preload another chunk
    if (document.documentElement.scrollHeight <= window.innerHeight + 80) {
      loadMoreForward();
    }
  }
})();
