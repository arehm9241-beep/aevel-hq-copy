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
    return fetch(path, opts).then(function(r) {
      return r.json().then(function(data) {
        if (!r.ok) throw new Error((data && data.error) || 'Request failed');
        return data;
      });
    });
  }

  function esc(s) { return (s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }

  function loadNotes() {
    return api('GET', '/api/community-notes').then(function(data) {
      var list = document.getElementById('community-notes-list');
      if (!list) return data.notes || [];
      var notes = data.notes || [];
      list.innerHTML = notes.length ? notes.map(function(n) {
        var date = n.created_at ? new Date(n.created_at).toLocaleDateString(undefined, { dateStyle: 'short' }) : '';
        return '<li class="community-note-item">' +
          '<div class="community-note-header">' +
          '<strong class="community-note-title">' + esc(n.title) + '</strong>' +
          '<span class="community-note-meta">' + esc(n.author_email) + ' · ' + date + '</span>' +
          '</div>' +
          '<p class="community-note-body">' + esc(n.body).replace(/\n/g, '<br>') + '</p>' +
          '<button type="button" class="btn btn-small btn-danger community-note-delete" data-id="' + (n.id || '') + '">Delete</button>' +
          '</li>';
      }).join('') : '<li class="empty-state"><p class="empty-state__title">No notes yet</p><p>Post an idea above to get started.</p></li>';
      list.querySelectorAll('.community-note-delete').forEach(function(btn) {
        btn.addEventListener('click', function() {
          var id = this.getAttribute('data-id');
          if (!id) return;
          if (typeof Aevel !== 'undefined' && Aevel.confirm) {
            Aevel.confirm({ title: 'Delete note', body: 'Remove this note?', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, function() {
              api('DELETE', '/api/community-notes/' + id).then(function() {
                loadNotes();
                if (Aevel.toast) Aevel.toast('Note removed', 'success');
              }).catch(function() {});
            });
          } else {
            api('DELETE', '/api/community-notes/' + id).then(function() { loadNotes(); }).catch(function() {});
          }
        });
      });
      return notes;
    }).catch(function() {
      var list = document.getElementById('community-notes-list');
      if (list) list.innerHTML = '<li class="empty-state"><p class="empty-state__title">Failed to load</p></li>';
      if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Failed to load notes', 'error');
      return [];
    });
  }

  var form = document.getElementById('community-note-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var titleEl = document.getElementById('cn-title');
      var bodyEl = document.getElementById('cn-body');
      var title = (titleEl && titleEl.value || '').trim();
      var body = (bodyEl && bodyEl.value || '').trim();
      if (!title) return;
      api('POST', '/api/community-notes', { title: title, body: body }).then(function() {
        if (titleEl) titleEl.value = '';
        if (bodyEl) bodyEl.value = '';
        loadNotes();
        if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Note posted', 'success');
      });
    });
  }

  loadNotes();
})();
