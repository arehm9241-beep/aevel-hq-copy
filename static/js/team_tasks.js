(function() {
  function api(method, path) {
    if (typeof Aevel !== 'undefined' && Aevel.api) {
      return Aevel.api(method, path);
    }
    return fetch(path, { method: method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }).then(function(r) {
      return r.json().then(function(data) { if (!r.ok) throw new Error((data && data.error) || 'Request failed'); return data; });
    });
  }

  function esc(s) { return (s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
  function urgencyLabel(u) { return u === 'high' ? 'High' : (u === 'low' ? 'Low' : 'Normal'); }

  function load() {
    api('GET', '/api/tasks/team').then(function(data) {
      var list = document.getElementById('team-tasks-list');
      if (!list) return;
      var tasks = data.tasks || [];
      list.innerHTML = tasks.length ? tasks.map(function(t) {
        var owner = esc(t.owner_email || '');
        var assignee = t.assigned_to ? esc(t.assigned_to) : '—';
        var due = t.due_date ? esc(t.due_date) : '—';
        var urg = (t.urgency || 'normal');
        return '<li class="team-task-item ' + (t.done ? 'done' : '') + '">' +
          '<input type="checkbox" class="team-task-done" ' + (t.done ? 'checked' : '') + ' disabled title="Edit in Tasks">' +
          '<div class="team-task-body">' +
          '<span class="team-task-text">' + esc(t.text) + '</span>' +
          '<div class="team-task-meta">' +
          '<span class="team-task-owner" title="Created by">' + owner + '</span>' +
          '<span class="team-task-assignee">Assigned: ' + assignee + '</span>' +
          '<span class="team-task-due">Due: ' + due + '</span>' +
          '<span class="team-task-urgency task-urgency-' + urg + '">' + urgencyLabel(urg) + '</span>' +
          '</div></div></li>';
      }).join('') : '<li class="empty-state"><p class="empty-state__title">No team tasks yet</p><p>Add tasks in the Tasks page — they’ll show here for the whole team.</p></li>';
    }).catch(function() {
      var list = document.getElementById('team-tasks-list');
      if (list) list.innerHTML = '<li class="empty-state"><p class="empty-state__title">Failed to load</p></li>';
      if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Failed to load team tasks', 'error');
    });
  }

  load();
})();
