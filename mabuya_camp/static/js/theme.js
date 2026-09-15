(function () {
  var STORAGE_KEY = 'mabuya-camp-theme';
  var DEFAULT_THEME = 'night';

  function getTheme() {
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'night' || saved === 'light') return saved;
    } catch (e) {}
    return DEFAULT_THEME;
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var buttons = document.querySelectorAll('[data-theme-toggle]');
    buttons.forEach(function (btn) {
      var next = theme === 'night' ? 'light' : 'night';
      btn.setAttribute('aria-label', 'Switch to ' + next + ' mode');
      btn.setAttribute('title', 'Switch to ' + next + ' mode');
    });
  }

  function setTheme(theme) {
    applyTheme(theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {}
  }

  applyTheme(getTheme());

  document.addEventListener('click', function (event) {
    var btn = event.target.closest('[data-theme-toggle]');
    if (!btn) return;
    var current = document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
    setTheme(current === 'night' ? 'light' : 'night');
  });
})();
