/* BenchWeave public site — panel navigation and theme toggle.
   Plain JS, no build chain. Hash deep links (#standards, #docs, #sdk) keep the
   panels reachable from outside the page. */

var THEME_KEY = 'bw-site-theme';
var PANEL_INDEX = { home: 0, standards: 1, docs: 2, sdk: 3, builtwith: 4 };

function showPanel(name, btn) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  document.querySelectorAll('nav.panels button').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  try { history.replaceState(null, '', '#' + name); } catch (e) { /* no history API */ }
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function applyStoredTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark') document.documentElement.setAttribute('data-theme', saved);
  } catch (e) {}
}

function currentTheme() {
  const set = document.documentElement.getAttribute('data-theme');
  if (set === 'light' || set === 'dark') return set;
  return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
}

function toggleTheme() {
  const next = currentTheme() === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
}

applyStoredTheme();

/* Open the panel named by the URL hash (e.g. /#standards), matching nav buttons. */
(function openFromHash() {
  const name = (location.hash || '').replace('#', '');
  if (name in PANEL_INDEX) {
    showPanel(name, document.querySelectorAll('nav.panels button')[PANEL_INDEX[name]]);
  }
})();

/* Reduced motion: the hero figure degrades to its finished state (plugins
   admitted and solid, run complete, evidence verified) rather than freezing
   at t=0 on the wireframes. */
if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.querySelectorAll('svg.schematic').forEach(function (svg) {
    if (typeof svg.setCurrentTime === 'function') svg.setCurrentTime(6.9);
    if (typeof svg.pauseAnimations === 'function') svg.pauseAnimations();
  });
}
