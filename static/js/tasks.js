(function() {
  function api(method, path, body) {
    if (typeof Aevel !== 'undefined' && Aevel.api) {
      return Aevel.api(method, path, body);
    }
    var opts = { method: method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return fetch(path, opts).then(function(r) { return r.json().then(function(data) { if (!r.ok) throw new Error(data.error || 'Request failed'); return data; }); });
  }

  function loadTasks() {
    return api('GET', '/api/tasks').then(function(data) { return data.tasks || []; });
  }

  function loadPrefs() {
    return api('GET', '/api/preferences').then(function(d) { return d; });
  }

  function saveTaskOrder(ids) {
    return api('PATCH', '/api/preferences', { task_order: ids });
  }

  function esc(s) { return (s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }

  function urgencyStyle(u) {
    if (u === 'high') return 'task-pri-high';
    if (u === 'low') return 'task-pri-low';
    return 'task-pri-normal';
  }

  function urgencyLabel(u) { return u === 'high' ? 'High' : (u === 'low' ? 'Low' : 'Normal'); }

  function groupTasks(tasks, taskOrder) {
    var today = new Date().toISOString().slice(0, 10);
    var completed = [];
    var todayList = [];
    var upcoming = [];
    var orderMap = {};
    (taskOrder || []).forEach(function(id, i) { orderMap[id] = i; });
    tasks.forEach(function(t) {
      if (t.done) completed.push(t);
      else if (t.due_date === today) todayList.push(t);
      else upcoming.push(t);
    });
    function sortByOrder(a, b) {
      var oa = orderMap[a.id] ?? 999;
      var ob = orderMap[b.id] ?? 999;
      return oa - ob;
    }
    todayList.sort(sortByOrder);
    upcoming.sort(sortByOrder);
    completed.sort(function(a, b) { return (b.created_at || '').localeCompare(a.created_at || ''); });
    return { today: todayList, upcoming: upcoming, completed: completed };
  }

  function renderGroups(groups) {
    var container = document.getElementById('task-groups');
    var skeleton = document.getElementById('task-list-skeleton');
    if (!container) return;
    if (skeleton) skeleton.classList.add('hidden');
    container.classList.remove('hidden');
    var html = '';
    ['today', 'upcoming', 'completed'].forEach(function(key) {
      var list = groups[key] || [];
      var title = key === 'today' ? 'Today' : (key === 'upcoming' ? 'Upcoming' : 'Completed');
      html += '<div class="task-group" data-group="' + key + '">';
      html += '<h3 class="task-group-title">' + title + ' (' + list.length + ')</h3>';
      html += '<ul class="task-list" id="task-list-' + key + '" data-group="' + key + '">';
      if (list.length === 0) {
        html += '<li class="empty-state"><p class="empty-state__title">' + (key === 'completed' ? 'No completed tasks' : 'No tasks') + '</p></li>';
      } else {
        html += list.map(function(t) {
          var urg = (t.urgency || 'normal');
          var priCls = urgencyStyle(urg);
          var assignee = t.assigned_to ? esc(t.assigned_to) : '';
          var due = t.due_date ? esc(t.due_date) : '';
          var meta = [];
          if (assignee) meta.push('<span class="task-meta task-assignee">' + assignee + '</span>');
          if (due) meta.push('<span class="task-meta task-due">Due ' + due + '</span>');
          meta.push('<span class="task-meta task-urgency ' + priCls + '">' + urgencyLabel(urg) + '</span>');
          return '<li class="task-item ' + (t.done ? 'done' : '') + ' ' + priCls + '" data-id="' + (t.id || '') + '" draggable="true">' +
            '<input type="checkbox" class="task-select" aria-label="Select for batch">' +
            '<input type="checkbox" class="task-done" ' + (t.done ? 'checked' : '') + ' aria-label="Mark done">' +
            '<div class="task-body">' +
            '<span class="task-text" tabindex="0" contenteditable="false">' + esc(t.text) + '</span>' +
            (meta.length ? '<div class="task-meta-row">' + meta.join('') + '</div>' : '') +
            '<div class="task-edit-row hidden">' +
            '<input type="text" class="input input-sm task-edit-text" value="' + esc(t.text) + '">' +
            '<input type="text" class="input input-sm task-edit-assignee" placeholder="Assign to" value="' + esc(t.assigned_to || '') + '">' +
            '<input type="text" class="input input-sm task-edit-due" placeholder="Due date" value="' + esc(t.due_date || '') + '">' +
            '<select class="input input-sm task-edit-urgency"><option value="low"' + (urg === 'low' ? ' selected' : '') + '>Low</option><option value="normal"' + (urg === 'normal' ? ' selected' : '') + '>Normal</option><option value="high"' + (urg === 'high' ? ' selected' : '') + '>High</option></select>' +
            '<button type="button" class="btn btn-small btn-primary task-save-edit">Save</button>' +
            '<button type="button" class="btn btn-small btn-ghost task-cancel-edit">Cancel</button></div>' +
            '</div>' +
            '<div class="task-actions">' +
            '<button type="button" class="btn btn-small btn-ghost task-edit" aria-label="Edit">Edit</button>' +
            '<button type="button" class="btn btn-small btn-ghost task-ai-breakdown" aria-label="Break down">Break down</button>' +
            '<button type="button" class="btn btn-small btn-ghost task-ai-estimate" aria-label="Estimate">Estimate</button>' +
            '<button type="button" class="btn btn-small btn-danger task-delete" aria-label="Delete">Delete</button></div></li>';
        }).join('');
      }
      html += '</ul></div>';
    });
    container.innerHTML = html;
    bindTaskEvents(groups);
  }

  function bindTaskEvents(groups) {
    var allTasks = (groups.today || []).concat(groups.upcoming || []).concat(groups.completed || []);

    function updateBatchBar() {
      var bar = document.getElementById('task-batch-bar');
      var countEl = bar && bar.querySelector('.task-batch-count');
      var completeBtn = document.getElementById('task-batch-complete');
      var deleteBtn = document.getElementById('task-batch-delete');
      var cancelBtn = document.getElementById('task-batch-cancel');
      var selected = document.querySelectorAll('.task-select:checked');
      var n = selected.length;
      if (bar) bar.classList.toggle('hidden', n === 0);
      if (countEl) countEl.textContent = n ? n + ' selected' : '';
      if (completeBtn) completeBtn.textContent = n ? 'Complete (' + n + ')' : 'Complete selected';
      if (deleteBtn) deleteBtn.textContent = n ? 'Delete (' + n + ')' : 'Delete selected';
    }

    document.querySelectorAll('.task-select').forEach(function(cb) {
      cb.addEventListener('change', updateBatchBar);
    });

    document.getElementById('task-batch-complete') && document.getElementById('task-batch-complete').addEventListener('click', function() {
      var ids = [];
      document.querySelectorAll('.task-select:checked').forEach(function(cb) {
        var id = cb.closest('.task-item') && cb.closest('.task-item').getAttribute('data-id');
        if (id) ids.push(id);
      });
      if (ids.length === 0) return;
      api('POST', '/api/tasks/batch-complete', { ids: ids, done: true }).then(function() {
        loadTasks().then(function(tasks) {
          loadPrefs().then(function(prefs) {
            renderGroups(groupTasks(tasks, prefs.task_order));
            if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Completed ' + ids.length + ' task(s)', 'success');
          });
        });
      }).catch(function() {});
    });

    document.getElementById('task-batch-delete') && document.getElementById('task-batch-delete').addEventListener('click', function() {
      var ids = [];
      var deleted = [];
      document.querySelectorAll('.task-select:checked').forEach(function(cb) {
        var row = cb.closest('.task-item');
        var id = row && row.getAttribute('data-id');
        if (id) {
          ids.push(id);
          deleted.push({ id: id, text: (row.querySelector('.task-text') && row.querySelector('.task-text').textContent) || '' });
        }
      });
      if (ids.length === 0) return;
      if (typeof Aevel !== 'undefined' && Aevel.confirm) {
        Aevel.confirm({ title: 'Delete tasks', body: 'Delete ' + ids.length + ' task(s)?', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, function() {
          api('POST', '/api/tasks/batch-delete', { ids: ids }).then(function() {
            loadTasks().then(function(tasks) {
              loadPrefs().then(function(prefs) {
                renderGroups(groupTasks(tasks, prefs.task_order));
                if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Tasks deleted', 'success');
                if (typeof Aevel !== 'undefined' && Aevel.undoToast) {
                  Aevel.undoToast('Tasks deleted', function() {
                    Promise.all(deleted.slice(0, 5).map(function(d) { return api('POST', '/api/tasks', { text: d.text }); })).then(function() {
                      loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
                    });
                  });
                }
              });
            });
          }).catch(function() {});
        });
      } else {
        api('POST', '/api/tasks/batch-delete', { ids: ids }).then(function() {
          loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
        }).catch(function() {});
      }
    });

    document.getElementById('task-batch-cancel') && document.getElementById('task-batch-cancel').addEventListener('click', function() {
      document.querySelectorAll('.task-select').forEach(function(cb) { cb.checked = false; });
      updateBatchBar();
    });

    document.querySelectorAll('.task-done').forEach(function(cb) {
      cb.addEventListener('change', function() {
        var id = cb.closest('.task-item').getAttribute('data-id');
        if (!id) return;
        var item = allTasks.find(function(t) { return String(t.id) === id; });
        api('PATCH', '/api/tasks/' + id, { done: !item.done }).then(function() {
          loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
        }).catch(function() {});
      });
    });

    document.querySelectorAll('.task-edit').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('.task-item');
        var editRow = row && row.querySelector('.task-edit-row');
        var textSpan = row && row.querySelector('.task-text');
        if (editRow && textSpan) {
          editRow.classList.remove('hidden');
          textSpan.classList.add('hidden');
          btn.classList.add('hidden');
          editRow.querySelector('.task-edit-text').focus();
        }
      });
    });

    document.querySelectorAll('.task-save-edit').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('.task-item');
        var id = row && row.getAttribute('data-id');
        if (!id) return;
        var editRow = row.querySelector('.task-edit-row');
        var text = (row.querySelector('.task-edit-text') && row.querySelector('.task-edit-text').value || '').trim();
        var assignee = (row.querySelector('.task-edit-assignee') && row.querySelector('.task-edit-assignee').value || '').trim();
        var due = (row.querySelector('.task-edit-due') && row.querySelector('.task-edit-due').value || '').trim();
        var urgency = (row.querySelector('.task-edit-urgency') && row.querySelector('.task-edit-urgency').value) || 'normal';
        if (!text) { if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Task text required', 'error'); return; }
        api('PATCH', '/api/tasks/' + id, { text: text, assigned_to: assignee, due_date: due, urgency: urgency }).then(function() {
          loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Updated', 'success');
        }).catch(function() {});
      });
    });

    document.querySelectorAll('.task-cancel-edit').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('.task-item');
        var editRow = row && row.querySelector('.task-edit-row');
        var textSpan = row && row.querySelector('.task-text');
        var editBtn = row && row.querySelector('.task-edit');
        if (editRow) editRow.classList.add('hidden');
        if (textSpan) textSpan.classList.remove('hidden');
        if (editBtn) editBtn.classList.remove('hidden');
      });
    });

    document.querySelectorAll('.task-text').forEach(function(span) {
      span.addEventListener('dblclick', function() {
        var row = this.closest('.task-item');
        var editRow = row && row.querySelector('.task-edit-row');
        var editBtn = row && row.querySelector('.task-edit');
        if (editRow && editBtn) {
          editRow.classList.remove('hidden');
          this.classList.add('hidden');
          editBtn.classList.add('hidden');
          editRow.querySelector('.task-edit-text').value = this.textContent;
          editRow.querySelector('.task-edit-text').focus();
        }
      });
    });

    document.querySelectorAll('.task-delete').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('.task-item');
        var id = row && row.getAttribute('data-id');
        if (!id) return;
        var text = (row.querySelector('.task-text') && row.querySelector('.task-text').textContent) || 'this task';
        var deletedTask = { id: id, text: text };
        if (typeof Aevel !== 'undefined' && Aevel.confirm) {
          Aevel.confirm({ title: 'Delete task', body: 'Delete "' + text.substring(0, 40) + (text.length > 40 ? '…"' : '"') + '?', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, function() {
            api('DELETE', '/api/tasks/' + id).then(function() {
              loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
              if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Task deleted', 'success');
              if (typeof Aevel !== 'undefined' && Aevel.undoToast) {
                Aevel.undoToast('Task deleted', function() {
                  api('POST', '/api/tasks', { text: deletedTask.text }).then(function() {
                    loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
                  });
                });
              }
            }).catch(function() {});
          });
        } else {
          api('DELETE', '/api/tasks/' + id).then(function() {
            loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
          }).catch(function() {});
        }
      });
    });

    function apiPost(path, body) {
      return fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
        .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
    }

    document.querySelectorAll('.task-ai-breakdown').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('.task-item');
        var id = row && row.getAttribute('data-id');
        var text = (row.querySelector('.task-text') && row.querySelector('.task-text').textContent) || '';
        if (!text) return;
        btn.disabled = true;
        btn.textContent = '…';
        apiPost('/api/ai/tasks/break-down', { text: text }).then(function(data) {
          var sub = data.subtasks || [];
          if (sub.length === 0) { if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('No subtasks generated', 'error'); return; }
          Promise.all(sub.map(function(s) { return api('POST', '/api/tasks', { text: s }); })).then(function() {
            loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, p.task_order)); }); });
            if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Added ' + sub.length + ' subtasks', 'success');
          });
        }).catch(function(err) {
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast(err.message || 'Failed', 'error');
        }).finally(function() {
          btn.disabled = false;
          btn.textContent = 'Break down';
        });
      });
    });

    document.querySelectorAll('.task-ai-estimate').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('.task-item');
        var text = (row.querySelector('.task-text') && row.querySelector('.task-text').textContent) || '';
        if (!text) return;
        btn.disabled = true;
        btn.textContent = '…';
        apiPost('/api/ai/tasks/estimate', { text: text }).then(function(data) {
          var msg = (data.level || '') + (data.time_est ? ' · ' + data.time_est : '') + (data.explanation ? ' — ' + data.explanation : '');
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast(msg, 'success');
        }).catch(function(err) {
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast(err.message || 'Failed', 'error');
        }).finally(function() {
          btn.disabled = false;
          btn.textContent = 'Estimate';
        });
      });
    });

    var draggedId = null;
    var dragOverEl = null;
    document.querySelectorAll('.task-item[draggable]').forEach(function(li) {
      li.addEventListener('dragstart', function(e) {
        draggedId = this.getAttribute('data-id');
        e.dataTransfer.setData('text/plain', draggedId);
        e.dataTransfer.effectAllowed = 'move';
        this.classList.add('task-dragging');
      });
      li.addEventListener('dragend', function() {
        this.classList.remove('task-dragging');
        document.querySelectorAll('.task-item').forEach(function(x) { x.classList.remove('task-drag-over'); });
      });
      li.addEventListener('dragover', function(e) {
        e.preventDefault();
        if (!draggedId || draggedId === this.getAttribute('data-id')) return;
        document.querySelectorAll('.task-item').forEach(function(x) { x.classList.remove('task-drag-over'); });
        this.classList.add('task-drag-over');
        dragOverEl = this;
      });
      li.addEventListener('drop', function(e) {
        e.preventDefault();
        this.classList.remove('task-drag-over');
        var targetId = this.getAttribute('data-id');
        if (!draggedId || !targetId || draggedId === targetId) return;
        var group = this.closest('.task-list').getAttribute('data-group');
        if (group === 'completed') return;
        var list = groups[group] || [];
        var ids = list.map(function(t) { return t.id; });
        var fromIdx = ids.indexOf(draggedId);
        var toIdx = ids.indexOf(targetId);
        if (fromIdx < 0 || toIdx < 0) return;
        ids.splice(fromIdx, 1);
        var newToIdx = ids.indexOf(targetId);
        ids.splice(newToIdx, 0, draggedId);
        var otherGroups = (group === 'today' ? groups.upcoming : groups.today) || [];
        var otherIds = otherGroups.map(function(t) { return t.id; });
        var completedIds = (groups.completed || []).map(function(t) { return t.id; });
        var newOrder = ids.concat(otherIds).concat(completedIds);
        saveTaskOrder(newOrder).then(function() {
          loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, newOrder)); }); });
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Reordered', 'success');
        }).catch(function() {});
      });
    });
  }

  document.getElementById('task-prioritize') && document.getElementById('task-prioritize').addEventListener('click', function() {
    var btn = this;
    btn.disabled = true;
    btn.textContent = 'Prioritizing…';
    loadTasks().then(function(tasks) {
      var active = tasks.filter(function(t) { return !t.done; });
      if (active.length === 0) { btn.disabled = false; btn.textContent = 'Prioritize'; if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('No active tasks', 'error'); return; }
      return fetch('/api/ai/tasks/prioritize', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tasks: active }) })
        .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.error || 'Failed'); return d; }); })
        .then(function(data) {
          var order = (data.order || []).sort(function(a, b) { return (a.order || 0) - (b.order || 0); });
          var ids = order.map(function(o) { return o.id; });
          saveTaskOrder(ids).then(function() {
            loadTasks().then(function(t) { loadPrefs().then(function(p) { renderGroups(groupTasks(t, ids)); }); });
            if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Tasks prioritized', 'success');
          });
        })
        .catch(function(err) {
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast(err.message || 'Failed', 'error');
        })
        .finally(function() {
          btn.disabled = false;
          btn.textContent = 'Prioritize';
        });
    });
  });

  var form = document.getElementById('task-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var input = document.getElementById('task-input');
      var text = (input && input.value || '').trim();
      if (!text) return;
      var assignee = (document.getElementById('task-assignee') && document.getElementById('task-assignee').value || '').trim();
      var due = (document.getElementById('task-due') && document.getElementById('task-due').value || '').trim();
      var urgency = (document.getElementById('task-urgency') && document.getElementById('task-urgency').value) || 'normal';
      var body = { text: text, assigned_to: assignee || undefined, due_date: due || undefined, urgency: urgency };
      api('POST', '/api/tasks', body).then(function() {
        input.value = '';
        if (document.getElementById('task-assignee')) document.getElementById('task-assignee').value = '';
        if (document.getElementById('task-due')) document.getElementById('task-due').value = '';
        if (document.getElementById('task-urgency')) document.getElementById('task-urgency').value = 'normal';
        loadTasks().then(function(t) {
          loadPrefs().then(function(p) {
            renderGroups(groupTasks(t, p.task_order));
            if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Task added', 'success');
          });
        });
      }).catch(function() {});
    });
  }

  loadTasks().then(function(tasks) {
    loadPrefs().then(function(prefs) {
      renderGroups(groupTasks(tasks, prefs.task_order));
    });
  });
})();
