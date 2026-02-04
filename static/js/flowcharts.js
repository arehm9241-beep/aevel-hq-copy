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

  var listEl = document.getElementById('flowchart-list');
  var emptyEl = document.getElementById('flowchart-empty');
  var editorWrap = document.getElementById('flowchart-editor');
  var titleInput = document.getElementById('flowchart-title');
  var mermaidInput = document.getElementById('flowchart-mermaid');
  var previewEl = document.getElementById('flowchart-preview');
  var currentId = null;
  var previewTimer = null;

  function renderPreview() {
    if (!previewEl || !mermaidInput) return;
    var code = (mermaidInput.value || '').trim();
    previewEl.innerHTML = '';
    if (!code) return;
    var div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = code;
    previewEl.appendChild(div);
    if (typeof mermaid !== 'undefined' && mermaid.run) {
      mermaid.run({ nodes: [div], suppressErrors: true }).catch(function() {
        previewEl.innerHTML = '<p class="text-secondary">Invalid Mermaid syntax</p>';
      });
    }
  }

  function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(renderPreview, 400);
  }

  if (mermaidInput) mermaidInput.addEventListener('input', schedulePreview);

  if (typeof mermaid !== 'undefined') {
    mermaid.initialize({ startOnLoad: false, theme: 'dark' });
  }

  function loadList() {
    return api('GET', '/api/flowcharts').then(function(data) {
      var items = data.flowcharts || [];
      if (!listEl) return items;
      listEl.innerHTML = items.length ? items.map(function(f) {
        return '<li class="flowchart-item' + (f.id === currentId ? ' active' : '') + '" data-id="' + (f.id || '') + '">' +
          '<span class="flowchart-item-title">' + (f.title || 'Untitled').replace(/</g, '&lt;') + '</span></li>';
      }).join('') : '<li class="flowchart-item empty">No flowcharts yet</li>';
      listEl.querySelectorAll('.flowchart-item[data-id]').forEach(function(li) {
        li.addEventListener('click', function() {
          var id = this.getAttribute('data-id');
          if (id) selectFlowchart(id);
        });
      });
      return items;
    });
  }

  function selectFlowchart(id) {
    currentId = id;
    emptyEl.classList.add('hidden');
    editorWrap.classList.remove('hidden');
    api('GET', '/api/flowcharts/' + id).then(function(f) {
      if (f.error) return;
      titleInput.value = f.title || '';
      mermaidInput.value = f.mermaid_text || '';
      loadList();
      schedulePreview();
    }).catch(function() {});
  }

  function showEmpty() {
    currentId = null;
    editorWrap.classList.add('hidden');
    emptyEl.classList.remove('hidden');
    titleInput.value = '';
    mermaidInput.value = '';
    previewEl.innerHTML = '';
  }

  document.getElementById('flowchart-new').addEventListener('click', function() {
    api('POST', '/api/flowcharts', { title: 'Untitled flowchart', mermaid_text: 'graph LR\n  A --> B' }).then(function(f) {
      if (f.id) {
        currentId = f.id;
        emptyEl.classList.add('hidden');
        editorWrap.classList.remove('hidden');
        titleInput.value = f.title || '';
        mermaidInput.value = f.mermaid_text || '';
        loadList();
        schedulePreview();
        if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Flowchart created', 'success');
      }
    });
  });

  document.getElementById('flowchart-save').addEventListener('click', function() {
    if (!currentId) return;
    api('PATCH', '/api/flowcharts/' + currentId, {
      title: titleInput.value.trim() || 'Untitled flowchart',
      mermaid_text: mermaidInput.value
    }).then(function() {
      loadList();
      schedulePreview();
      if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Saved', 'success');
    });
  });

  var togglePreviewBtn = document.getElementById('flowchart-toggle-preview');
  var splitEl = document.getElementById('flowchart-split');
  if (togglePreviewBtn && splitEl) {
    togglePreviewBtn.addEventListener('click', function() {
      splitEl.classList.toggle('full-preview');
      this.textContent = splitEl.classList.contains('full-preview') ? 'Split view' : 'Preview full';
    });
  }

  document.getElementById('flowchart-delete').addEventListener('click', function() {
    if (!currentId) return;
    if (typeof Aevel !== 'undefined' && Aevel.confirm) {
      Aevel.confirm({ title: 'Delete flowchart', body: 'Delete this flowchart?', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, function() {
        api('DELETE', '/api/flowcharts/' + currentId).then(function() {
          showEmpty();
          loadList();
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Deleted', 'success');
        });
      });
    } else {
      api('DELETE', '/api/flowcharts/' + currentId).then(function() {
        showEmpty();
        loadList();
      });
    }
  });

  loadList();
  showEmpty();
})();
