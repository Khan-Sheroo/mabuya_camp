(function () {
  function closeAllMenus(except) {
    document.querySelectorAll('.card-color-picker.is-open').forEach(function (picker) {
      if (except && picker === except) return;
      picker.classList.remove('is-open');
      var btn = picker.querySelector('.card-color-btn');
      var menu = picker.querySelector('.card-color-menu');
      if (btn) btn.setAttribute('aria-expanded', 'false');
      if (menu) menu.hidden = true;
    });
  }

  document.addEventListener('click', function (event) {
    var toggle = event.target.closest('.card-color-btn');
    if (toggle) {
      event.preventDefault();
      event.stopPropagation();
      var picker = toggle.closest('.card-color-picker');
      var menu = picker.querySelector('.card-color-menu');
      var willOpen = !picker.classList.contains('is-open');
      closeAllMenus();
      if (willOpen) {
        picker.classList.add('is-open');
        toggle.setAttribute('aria-expanded', 'true');
        menu.hidden = false;
      }
      return;
    }

    var swatch = event.target.closest('.card-color-swatch');
    if (swatch) {
      event.preventDefault();
      event.stopPropagation();
      var card = swatch.closest('.project-card');
      var picker = swatch.closest('.card-color-picker');
      var projectId = card && card.getAttribute('data-project-id');
      var color = swatch.getAttribute('data-color');
      var hex = swatch.getAttribute('data-hex');
      if (!projectId || !color) return;

      fetch('/projects/' + projectId + '/color', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ color: color }),
      })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
          if (!result.ok || !result.data.ok) return;
          card.style.setProperty('--card-color', result.data.hex || hex);
          picker.querySelectorAll('.card-color-swatch').forEach(function (el) {
            el.classList.toggle('is-selected', el.getAttribute('data-color') === color);
          });
          closeAllMenus();
        })
        .catch(function () {});
      return;
    }

    if (!event.target.closest('.card-color-picker')) {
      closeAllMenus();
    }
  });
})();
