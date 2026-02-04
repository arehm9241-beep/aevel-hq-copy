(function() {
  var STORAGE_KEY = 'blast_ai_enabled';
  function isAIEnabled() { return localStorage.getItem(STORAGE_KEY) !== 'false'; }

  var disabledEl = document.getElementById('ai-disabled-message');
  var panelEl = document.getElementById('ai-panel');
  var outputEl = document.getElementById('ai-output');

  function updateVisibility() {
    var on = isAIEnabled();
    if (disabledEl) disabledEl.classList.toggle('hidden', on);
    if (panelEl) panelEl.classList.toggle('hidden', !on);
  }
  updateVisibility();
  setInterval(updateVisibility, 500);

  var form = document.getElementById('ai-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      if (!isAIEnabled()) return;
      var input = document.getElementById('ai-input');
      var text = (input.value || '').trim();
      if (!text) return;
      outputEl.textContent = '…';
      fetch('/api/ai/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text })
      })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          outputEl.textContent = d.message || d.formatted || JSON.stringify(d, null, 2);
        })
        .catch(function(err) {
          outputEl.textContent = 'Error: ' + (err.message || 'Request failed');
        });
    });
  }
})();
