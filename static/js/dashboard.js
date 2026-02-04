(function() {
  var STORAGE_KEY = 'blast_ai_enabled';

  window.Dashboard = {
    isAIEnabled: function() {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw === null) return true;
      return raw === 'true';
    },
    setAIToggle: function(enabled) {
      localStorage.setItem(STORAGE_KEY, enabled ? 'true' : 'false');
      var toggle = document.getElementById('ai-toggle');
      if (toggle) toggle.checked = enabled;
      var togglePage = document.getElementById('ai-toggle-page');
      if (togglePage) togglePage.checked = enabled;
    },
    syncToggleFromStorage: function(checkbox) {
      if (!checkbox) return;
      checkbox.checked = Dashboard.isAIEnabled();
    }
  };

  var toggle = document.getElementById('ai-toggle');
  if (toggle) {
    Dashboard.syncToggleFromStorage(toggle);
    toggle.addEventListener('change', function() {
      Dashboard.setAIToggle(toggle.checked);
    });
  }
})();
