(function() {
  function api(method, path, body) {
    if (typeof Aevel !== 'undefined' && Aevel.api) {
      return Aevel.api(method, path, body);
    }
    var opts = { method: method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return fetch(path, opts).then(function(r) { return r.json().then(function(data) { if (!r.ok) throw new Error(data.error || 'Request failed'); return data; }); });
  }

  function loadNotes() {
    return api('GET', '/api/notes').then(function(data) { return data.notes || []; }).catch(function() {
      if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Failed to load notes', 'error');
      return [];
    });
  }

  function render(notes) {
    var list = document.getElementById('notes-list');
    if (!list) return;
    list.innerHTML = notes.length ? notes.map(function(n) {
      return '<li class="note-item" data-id="' + (n.id || '') + '">' +
        '<h4>' + (n.title || '').replace(/</g, '&lt;') + '</h4>' +
        '<p>' + (n.body || '').replace(/</g, '&lt;').replace(/\n/g, '<br>') + '</p>' +
        '<div class="note-actions"><button type="button" class="btn btn-small btn-danger note-delete" aria-label="Delete note">Delete</button></div></li>';
    }).join('') : '<li class="empty-state"><p class="empty-state__title">No notes yet</p><p>Create one above to get started.</p></li>';
    list.querySelectorAll('.note-delete').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('.note-item');
        var id = row && row.getAttribute('data-id');
        if (!id) return;
        var title = (row.querySelector('h4') && row.querySelector('h4').textContent) || 'this note';
        if (typeof Aevel !== 'undefined' && Aevel.confirm) {
          Aevel.confirm({ title: 'Delete note', body: 'Delete “‘ + title.replace(/</g, '&lt;').substring(0, 40) + (title.length > 40 ? '…”' : '”') + '? This cannot be undone.', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, function() {
            api('DELETE', '/api/notes/' + id).then(function() { loadNotes().then(render); if (Aevel.toast) Aevel.toast('Note deleted', 'success'); }).catch(function() {});
          });
        } else {
          api('DELETE', '/api/notes/' + id).then(function() { loadNotes().then(render); }).catch(function() {});
        }
      });
    });
  }

  var form = document.getElementById('note-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var titleEl = document.getElementById('note-title');
      var bodyEl = document.getElementById('note-body');
      var title = (titleEl && titleEl.value || '').trim();
      var body = (bodyEl && bodyEl.value || '').trim();
      if (!title) return;
      api('POST', '/api/notes', { title: title, body: body }).then(function() {
        if (titleEl) titleEl.value = '';
        if (bodyEl) bodyEl.value = '';
        loadNotes().then(render);
        if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Note saved', 'success');
      }).catch(function() {});
    });
  }

  loadNotes().then(render);
})();
