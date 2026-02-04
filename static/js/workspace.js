(function() {
  function api(method, path, body) {
    if (typeof Aevel !== 'undefined' && Aevel.api) {
      return Aevel.api(method, path, body);
    }
    var opts = { method: method, credentials: 'same-origin', headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function(r) { return r.json().then(function(data) { if (!r.ok) throw new Error(data.error || 'Request failed'); return data; }); });
  }

  var listEl = document.getElementById('workspace-list');
  var emptyEl = document.getElementById('workspace-empty');
  var editorWrap = document.getElementById('workspace-editor');
  var titleInput = document.getElementById('workspace-title');
  var bodyInput = document.getElementById('workspace-body');
  var currentId = null;

  function loadPages() {
    return api('GET', '/api/workspace').then(function(data) {
      var pages = data.pages || [];
      if (!listEl) return pages;
      listEl.innerHTML = pages.length ? pages.map(function(p) {
        return '<li class="workspace-page-item' + (p.id === currentId ? ' active' : '') + '" data-id="' + (p.id || '') + '">' +
          '<span class="workspace-page-title">' + (p.title || 'Untitled').replace(/</g, '&lt;') + '</span></li>';
      }).join('') : '<li class="workspace-page-item empty">No pages yet</li>';
      listEl.querySelectorAll('.workspace-page-item[data-id]').forEach(function(li) {
        li.addEventListener('click', function() {
          var id = this.getAttribute('data-id');
          if (id) selectPage(id);
        });
      });
      return pages;
    });
  }

  function selectPage(id) {
    currentId = id;
    emptyEl.classList.add('hidden');
    editorWrap.classList.remove('hidden');
    api('GET', '/api/workspace/' + id).then(function(p) {
      if (p.error) return;
      titleInput.value = p.title || '';
      bodyInput.value = p.body || '';
      loadPages();
    }).catch(function() {});
  }

  function showEmpty() {
    currentId = null;
    editorWrap.classList.add('hidden');
    emptyEl.classList.remove('hidden');
    titleInput.value = '';
    bodyInput.value = '';
  }

  document.getElementById('workspace-new').addEventListener('click', function() {
    api('POST', '/api/workspace', { title: 'Untitled', body: '' }).then(function(p) {
      if (p.id) {
        currentId = p.id;
        emptyEl.classList.add('hidden');
        editorWrap.classList.remove('hidden');
        titleInput.value = p.title || '';
        bodyInput.value = p.body || '';
        loadPages();
        if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Page created', 'success');
      }
    });
  });

  document.getElementById('workspace-save').addEventListener('click', function() {
    if (!currentId) return;
    api('PATCH', '/api/workspace/' + currentId, {
      title: titleInput.value.trim() || 'Untitled',
      body: bodyInput.value
    }).then(function() {
      loadPages();
      if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Saved', 'success');
    }).catch(function() {});
  });

  document.getElementById('workspace-delete').addEventListener('click', function() {
    if (!currentId) return;
    if (typeof Aevel !== 'undefined' && Aevel.confirm) {
      Aevel.confirm({ title: 'Delete page', body: 'Delete this page? This cannot be undone.', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, function() {
        api('DELETE', '/api/workspace/' + currentId).then(function() {
          showEmpty();
          loadPages();
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Page deleted', 'success');
        });
      });
    } else {
      api('DELETE', '/api/workspace/' + currentId).then(function() {
        showEmpty();
        loadPages();
      });
    }
  });

  loadPages();
  showEmpty();
})();
