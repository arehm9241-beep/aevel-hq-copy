(function() {
  var monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  var current = new Date();
  var gridEl = document.getElementById('cal-grid');
  var titleEl = document.getElementById('cal-title');
  var eventsListEl = document.getElementById('events-list');
  var calDateInput = document.getElementById('cal-date');

  function api(method, path, body) {
    if (typeof Aevel !== 'undefined' && Aevel.api) {
      return Aevel.api(method, path, body);
    }
    var opts = { method: method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return fetch(path, opts).then(function(r) { return r.json().then(function(data) { if (!r.ok) throw new Error(data.error || 'Request failed'); return data; }); });
  }

  function toDateStr(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function setFormDateToToday() {
    if (calDateInput) calDateInput.value = toDateStr(new Date());
  }

  function loadEvents() {
    return api('GET', '/api/events').then(function(data) { return data.events || []; });
  }

  function isAllDay(ev) {
    return ev.is_all_day !== false && !ev.time_start && !ev.time_end;
  }

  function eventLabel(ev) {
    if (isAllDay(ev)) return 'All day';
    if (ev.time_start) return (ev.time_start + (ev.time_end ? '–' + ev.time_end : ''));
    return '';
  }

  function renderCalendar() {
    if (!gridEl || !titleEl) return;
    var y = current.getFullYear();
    var m = current.getMonth();
    var todayStr = toDateStr(new Date());
    titleEl.textContent = monthNames[m] + ' ' + y;
    var first = new Date(y, m, 1);
    var last = new Date(y, m + 1, 0);
    var startDay = first.getDay();
    var daysInMonth = last.getDate();
    loadEvents().then(function(events) {
      if (!events) events = [];
      var eventByDate = {};
      events.forEach(function(ev) {
        var d = ev.date;
        if (d) {
          if (!eventByDate[d]) eventByDate[d] = [];
          eventByDate[d].push(ev);
        }
      });
      var maxVisible = 6;
      var html = '';
      var dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
      dayNames.forEach(function(d) { html += '<div class="cal-cell head">' + d + '</div>'; });
      var pad = startDay;
      var prevMonth = new Date(y, m, 0);
      var prevDays = prevMonth.getDate();
      for (var i = 0; i < pad; i++) {
        html += '<div class="cal-cell other">' + (prevDays - pad + i + 1) + '</div>';
      }
      for (var d = 1; d <= daysInMonth; d++) {
        var dateStr = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
        var dayEvents = (eventByDate[dateStr] || []).slice();
        dayEvents.sort(function(a, b) {
          var ta = a.time_start || '00:00';
          var tb = b.time_start || '00:00';
          return (isAllDay(a) ? '00:00' : ta).localeCompare(isAllDay(b) ? '00:00' : tb);
        });
        var isToday = dateStr === todayStr;
        var cls = 'cal-cell' + (dayEvents.length ? ' has-event' : '') + (isToday ? ' today' : '') + ' cal-cell-droppable';
        var eventsHtml = '';
        dayEvents.slice(0, maxVisible).forEach(function(ev) {
          var allDay = isAllDay(ev);
          var evCls = 'cal-cell-event cal-cell-event-draggable' + (allDay ? ' cal-cell-event-allday' : ' cal-cell-event-timed');
          var label = eventLabel(ev);
          var titleEsc = (ev.title || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
          eventsHtml += '<span class="' + evCls + '" data-event-id="' + ev.id + '" data-event-date="' + dateStr + '" data-event=\'' + JSON.stringify({ id: ev.id, date: ev.date, title: ev.title, time_start: ev.time_start, time_end: ev.time_end, notes: ev.notes, is_all_day: allDay }).replace(/'/g, '&#39;') + '\' draggable="true" title="Drag to move, click to edit">' +
            (allDay ? '' : '<span class="cal-cell-event-time">' + (ev.time_start || '') + '</span> ') +
            titleEsc + '</span>';
        });
        if (dayEvents.length > maxVisible) {
          eventsHtml += '<span class="cal-cell-event cal-cell-more">+' + (dayEvents.length - maxVisible) + ' more</span>';
        }
        html += '<div class="' + cls + '" data-date="' + dateStr + '" tabindex="0"><span class="cal-cell-day">' + d + '</span><div class="cal-cell-events">' + eventsHtml + '</div></div>';
      }
      var total = pad + daysInMonth;
      var rest = total % 7 ? 7 - (total % 7) : 0;
      for (var j = 0; j < rest; j++) {
        html += '<div class="cal-cell other">' + (j + 1) + '</div>';
      }
      gridEl.innerHTML = html;
      bindCalendarEvents(events);
      renderEventsList(events, y, m);
    }).catch(function() {
      if (gridEl) gridEl.innerHTML = '';
      if (eventsListEl) eventsListEl.innerHTML = '<li class="empty-state"><p class="empty-state__title">Failed to load events</p></li>';
      if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Failed to load events', 'error');
    });
  }

  function bindCalendarEvents(events) {
    var eventMap = {};
    (events || []).forEach(function(e) { eventMap[e.id] = e; });
    gridEl.querySelectorAll('.cal-cell-event-draggable').forEach(function(span) {
      span.addEventListener('dragstart', function(e) {
        e.dataTransfer.setData('text/plain', this.getAttribute('data-event-id'));
        e.dataTransfer.effectAllowed = 'move';
        this.classList.add('cal-dragging');
        this.classList.add('cal-drag-pressed');
      });
      span.addEventListener('dragend', function() {
        this.classList.remove('cal-dragging');
        this.classList.remove('cal-drag-pressed');
        gridEl.querySelectorAll('.cal-cell-droppable').forEach(function(c) { c.classList.remove('cal-drag-over'); });
      });
      span.addEventListener('click', function(e) {
        e.stopPropagation();
        var ev = eventMap[this.getAttribute('data-event-id')] || {};
        var dataAttr = this.getAttribute('data-event');
        if (dataAttr) try { ev = JSON.parse(dataAttr.replace(/&#39;/g, "'")); } catch (ex) {}
        startInlineEdit(this, ev);
      });
    });
    gridEl.querySelectorAll('.cal-cell-droppable').forEach(function(cell) {
      cell.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        this.classList.add('cal-drag-over');
      });
      cell.addEventListener('dragleave', function() { this.classList.remove('cal-drag-over'); });
      cell.addEventListener('drop', function(e) {
        e.preventDefault();
        this.classList.remove('cal-drag-over');
        var eventId = e.dataTransfer.getData('text/plain');
        var newDate = this.getAttribute('data-date');
        if (!eventId || !newDate) return;
        api('PATCH', '/api/events/' + eventId, { date: newDate }).then(function() {
          renderCalendar();
          if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Event moved', 'success');
        }).catch(function() {});
      });
      cell.addEventListener('click', function(e) {
        if (e.target.closest('.cal-cell-event-draggable')) return;
        var date = this.getAttribute('data-date');
        if (date && calDateInput) {
          calDateInput.value = date;
          calDateInput.focus();
        }
      });
    });
  }

  function startInlineEdit(spanEl, ev) {
    var wrap = document.createElement('div');
    wrap.className = 'cal-inline-edit';
    var titleVal = (ev.title || '').replace(/"/g, '&quot;');
    var timeVal = ev.time_start || '';
    var notesVal = (ev.notes || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    wrap.innerHTML = '<input type="text" class="input input-sm cal-edit-title" value="' + titleVal + '" placeholder="Title">' +
      '<input type="time" class="input input-sm cal-edit-time" value="' + timeVal + '" placeholder="Time">' +
      '<input type="text" class="input input-sm cal-edit-notes" value="' + notesVal + '" placeholder="Notes">' +
      '<div class="cal-edit-actions"><button type="button" class="btn btn-small btn-primary cal-edit-save">Save</button><button type="button" class="btn btn-small btn-ghost cal-edit-cancel">Cancel</button></div>';
    spanEl.style.display = 'none';
    spanEl.parentNode.insertBefore(wrap, spanEl);
    var titleInp = wrap.querySelector('.cal-edit-title');
    var timeInp = wrap.querySelector('.cal-edit-time');
    var notesInp = wrap.querySelector('.cal-edit-notes');
    titleInp.focus();
    wrap.querySelector('.cal-edit-save').addEventListener('click', function() {
      var newTitle = (titleInp.value || '').trim();
      var newTime = (timeInp.value || '').trim() || null;
      var newNotes = (notesInp.value || '').trim() || null;
      if (!newTitle) { if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Title required', 'error'); return; }
      var payload = { title: newTitle, notes: newNotes, is_all_day: !newTime };
      if (newTime) payload.time_start = newTime;
      else payload.time_start = null;
      payload.time_end = null;
      api('PATCH', '/api/events/' + ev.id, payload).then(function() {
        wrap.remove();
        spanEl.style.display = '';
        renderCalendar();
        if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Updated', 'success');
      }).catch(function() {});
    });
    wrap.querySelector('.cal-edit-cancel').addEventListener('click', function() {
      wrap.remove();
      spanEl.style.display = '';
    });
  }

  var eventFilterQuery = '';
  function renderEventsList(events, y, m) {
    if (!eventsListEl) return;
    var monthStr = String(m + 1).padStart(2, '0');
    var inMonth = events.filter(function(e) {
      return e.date && e.date.startsWith(y + '-' + monthStr);
    }).sort(function(a, b) {
      var cmp = (a.date || '').localeCompare(b.date || '');
      if (cmp) return cmp;
      return (a.time_start || '00:00').localeCompare(b.time_start || '00:00');
    });
    var q = (eventFilterQuery || '').trim().toLowerCase();
    if (q) inMonth = inMonth.filter(function(e) { return (e.title || '').toLowerCase().indexOf(q) !== -1; });
    eventsListEl.innerHTML = inMonth.length ? inMonth.map(function(ev) {
      var escapedTitle = (ev.title || '').replace(/</g, '&lt;');
      var label = eventLabel(ev);
      return '<li class="event-list-item event-list-item-draggable' + (isAllDay(ev) ? ' event-allday' : ' event-timed') + '" data-id="' + (ev.id || '') + '" data-date="' + (ev.date || '') + '" data-title="' + escapedTitle + '">' +
        '<span class="event-date">' + (ev.date || '') + '</span><span class="event-label">' + label + '</span><span class="event-title">' + escapedTitle + '</span>' +
        '<div class="event-actions"><button type="button" class="btn btn-small btn-ghost event-edit" aria-label="Edit event">Edit</button>' +
        '<button type="button" class="btn btn-small btn-danger event-delete" data-id="' + (ev.id || '') + '" aria-label="Delete event">Delete</button></div></li>';
    }).join('') : '<li class="empty-state"><p class="empty-state__title">' + (eventFilterQuery ? 'No matching events' : 'No events this month') + '</p><p>Click a day above and add an event.</p></li>';
    eventsListEl.querySelectorAll('.event-delete').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var li = btn.closest('.event-list-item');
        var id = (li && li.getAttribute('data-id')) || btn.getAttribute('data-id');
        if (!id) return;
        var label = (li && li.querySelector('.event-title') && li.querySelector('.event-title').textContent) || 'this event';
        var deletedEv = { id: id, date: li.getAttribute('data-date'), title: label };
        function doDelete() {
          api('DELETE', '/api/events/' + id).then(function() {
            renderCalendar();
            if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Event deleted', 'success');
            if (typeof Aevel !== 'undefined' && Aevel.undoToast) {
              Aevel.undoToast('Event deleted', function() {
                api('POST', '/api/events', { date: deletedEv.date, title: deletedEv.title }).then(renderCalendar);
              });
            }
          }).catch(function() {});
        }
        if (typeof Aevel !== 'undefined' && Aevel.confirm) {
          Aevel.confirm({ title: 'Delete event', body: 'Delete "' + label.substring(0, 50) + (label.length > 50 ? '…"' : '"') + '?', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, doDelete);
        } else {
          doDelete();
        }
      });
    });
    eventsListEl.querySelectorAll('.event-edit').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var li = btn.closest('.event-list-item');
        var id = li && li.getAttribute('data-id');
        var ev = (events || []).find(function(e) { return String(e.id) === id; }) || { id: id, date: li.getAttribute('data-date'), title: (li.querySelector('.event-title') && li.querySelector('.event-title').textContent) || '' };
        var editRow = '<li class="event-edit-row" data-id="' + id + '">' +
          '<input type="date" class="input input-sm event-edit-date" value="' + (ev.date || '') + '">' +
          '<input type="time" class="input input-sm event-edit-time" value="' + (ev.time_start || '') + '">' +
          '<input type="text" class="input input-sm event-edit-title" value="' + (ev.title || '').replace(/"/g, '&quot;') + '" placeholder="Title">' +
          '<input type="text" class="input input-sm event-edit-notes" value="' + (ev.notes || '').replace(/"/g, '&quot;') + '" placeholder="Notes">' +
          '<button type="button" class="btn btn-small btn-primary event-save">Save</button>' +
          '<button type="button" class="btn btn-small btn-ghost event-cancel">Cancel</button></li>';
        li.insertAdjacentHTML('afterend', editRow);
        li.classList.add('hidden');
        var next = li.nextElementSibling;
        next.querySelector('.event-save').addEventListener('click', function() {
          var newDate = (next.querySelector('.event-edit-date').value || '').trim();
          var newTitle = (next.querySelector('.event-edit-title').value || '').trim();
          var newTime = (next.querySelector('.event-edit-time').value || '').trim() || null;
          var newNotes = (next.querySelector('.event-edit-notes').value || '').trim() || null;
          if (!newDate || !newTitle) { if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Date and title required', 'error'); return; }
          var payload = { date: newDate, title: newTitle, notes: newNotes, is_all_day: !newTime };
          if (newTime) payload.time_start = newTime;
          api('PATCH', '/api/events/' + id, payload).then(function() {
            next.remove();
            li.classList.remove('hidden');
            renderCalendar();
            if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Event updated', 'success');
          }).catch(function() {});
        });
        next.querySelector('.event-cancel').addEventListener('click', function() {
          next.remove();
          li.classList.remove('hidden');
        });
      });
    });
    eventsListEl.querySelectorAll('.event-list-item-draggable').forEach(function(li) {
      li.addEventListener('dragstart', function(e) {
        e.dataTransfer.setData('text/plain', this.getAttribute('data-id'));
        e.dataTransfer.effectAllowed = 'move';
        this.classList.add('cal-dragging');
      });
      li.addEventListener('dragend', function() {
        this.classList.remove('cal-dragging');
        if (gridEl) gridEl.querySelectorAll('.cal-cell-droppable').forEach(function(c) { c.classList.remove('cal-drag-over'); });
      });
    });
  }

  var calFilterEl = document.getElementById('cal-filter');
  if (calFilterEl) {
    calFilterEl.addEventListener('input', function() {
      eventFilterQuery = this.value || '';
      loadEvents().then(function(events) {
        if (!events) events = [];
        renderEventsList(events, current.getFullYear(), current.getMonth());
      }).catch(function() {});
    });
  }

  var prevBtn = document.getElementById('cal-prev');
  var nextBtn = document.getElementById('cal-next');
  var todayBtn = document.getElementById('cal-today');
  if (prevBtn) prevBtn.addEventListener('click', function() { current.setMonth(current.getMonth() - 1); renderCalendar(); });
  if (nextBtn) nextBtn.addEventListener('click', function() { current.setMonth(current.getMonth() + 1); renderCalendar(); });
  if (todayBtn) todayBtn.addEventListener('click', function() {
    current = new Date();
    renderCalendar();
    setFormDateToToday();
    if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Showing today', 'success');
  });

  var calForm = document.getElementById('cal-form');
  if (calForm) {
    calForm.addEventListener('submit', function(e) {
      e.preventDefault();
      var dateEl = document.getElementById('cal-date');
      var titleEl = document.getElementById('cal-title-input');
      var timeEl = document.getElementById('cal-time-input');
      var date = dateEl && dateEl.value;
      var title = titleEl && titleEl.value && titleEl.value.trim();
      if (!date || !title) return;
      var payload = { date: date, title: title };
      if (timeEl && timeEl.value) { payload.time_start = timeEl.value; payload.is_all_day = false; }
      api('POST', '/api/events', payload).then(function() {
        if (titleEl) titleEl.value = '';
        if (timeEl) timeEl.value = '';
        renderCalendar();
        if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Event added', 'success');
      }).catch(function() {});
    });
  }

  function showAIPanel(html, closable) {
    var panel = document.getElementById('cal-ai-panel');
    if (!panel) return;
    panel.innerHTML = (closable !== false ? '<button type="button" class="btn btn-small btn-ghost cal-ai-close" aria-label="Close">×</button>' : '') + html;
    panel.classList.remove('hidden');
    panel.querySelector('.cal-ai-close') && panel.querySelector('.cal-ai-close').addEventListener('click', function() { panel.classList.add('hidden'); });
  }

  function apiPost(path, body) {
    return fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
      .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }

  document.getElementById('cal-ai-optimize') && document.getElementById('cal-ai-optimize').addEventListener('click', function() {
    var btn = this;
    btn.disabled = true;
    btn.textContent = 'Thinking…';
    loadEvents().then(function(events) {
      var inView = events.filter(function(e) {
        var m = current.getMonth() + 1;
        var prefix = current.getFullYear() + '-' + (m < 10 ? '0' : '') + m;
        return e.date && e.date.startsWith(prefix);
      });
      if (inView.length === 0) { showAIPanel('<p class="cal-ai-muted">No events this month to optimize.</p>'); btn.disabled = false; btn.textContent = 'Optimize schedule'; return; }
      return apiPost('/api/ai/calendar/optimize', { events: inView }).then(function(data) {
        var sug = data.suggestions || [];
        var html = '<div class="cal-ai-output"><p class="cal-ai-label">AI-generated suggestions (edit before applying):</p><ul class="cal-ai-list">' +
          sug.map(function(s) {
            return '<li data-id="' + (s.id || '') + '"><span class="cal-ai-sug-date"><input type="date" value="' + (s.suggested_date || '') + '"></span> ' +
              '<span class="cal-ai-sug-time"><input type="time" value="' + (s.suggested_time_start || '') + '" placeholder="All day"></span> ' +
              '<span class="cal-ai-sug-reason">' + (s.reason || '').replace(/</g, '&lt;') + '</span> ' +
              '<button type="button" class="btn btn-small btn-primary cal-ai-apply">Apply</button></li>';
          }).join('') + '</ul></div>';
        showAIPanel(html);
        document.querySelectorAll('.cal-ai-apply').forEach(function(b) {
          b.addEventListener('click', function() {
            var li = b.closest('li');
            var id = li.getAttribute('data-id');
            var dateInp = li.querySelector('input[type="date"]');
            var timeInp = li.querySelector('input[type="time"]');
            var date = dateInp && dateInp.value;
            var time = timeInp && timeInp.value;
            if (!id || !date) return;
            var payload = { date: date };
            if (time) payload.time_start = time; else payload.is_all_day = true;
            api('PATCH', '/api/events/' + id, payload).then(function() {
              li.remove();
              renderCalendar();
              if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Applied', 'success');
            }).catch(function() {});
          });
        });
      }).catch(function(err) {
        showAIPanel('<p class="cal-ai-error">' + (err.message || 'Failed').replace(/</g, '&lt;') + '</p>');
      }).finally(function() {
        btn.disabled = false;
        btn.textContent = 'Optimize schedule';
      });
    });
  });

  document.getElementById('cal-ai-summarize') && document.getElementById('cal-ai-summarize').addEventListener('click', function() {
    var btn = this;
    btn.disabled = true;
    btn.textContent = 'Summarizing…';
    loadEvents().then(function(events) {
      var weekStart = new Date(current);
      weekStart.setDate(weekStart.getDate() - weekStart.getDay());
      var weekEnd = new Date(weekStart);
      weekEnd.setDate(weekEnd.getDate() + 6);
      var prefix = weekStart.getFullYear() + '-' + String(weekStart.getMonth() + 1).padStart(2, '0') + '-';
      var inWeek = events.filter(function(e) {
        if (!e.date) return false;
        var d = new Date(e.date);
        return d >= weekStart && d <= weekEnd;
      });
      return apiPost('/api/ai/calendar/summarize', { events: inWeek, scope: 'week' }).then(function(data) {
        showAIPanel('<div class="cal-ai-output"><p class="cal-ai-label">Week summary:</p><p class="cal-ai-text">' + (data.summary || '').replace(/</g, '&lt;').replace(/\n/g, '<br>') + '</p></div>');
      }).catch(function(err) {
        showAIPanel('<p class="cal-ai-error">' + (err.message || 'Failed').replace(/</g, '&lt;') + '</p>');
      }).finally(function() {
        btn.disabled = false;
        btn.textContent = 'Summarize';
      });
    });
  });

  document.getElementById('cal-ai-extract') && document.getElementById('cal-ai-extract').addEventListener('click', function() {
    var panel = document.getElementById('cal-ai-panel');
    panel.innerHTML = '<button type="button" class="btn btn-small btn-ghost cal-ai-close" aria-label="Close">×</button>' +
      '<p class="cal-ai-label">Paste text with dates/times. AI will extract events.</p>' +
      '<textarea class="input cal-ai-textarea" id="cal-extract-text" placeholder="e.g. Meeting with John Tuesday 2pm, Lunch Wednesday noon..."></textarea>' +
      '<button type="button" class="btn btn-primary" id="cal-extract-go">Extract</button>';
    panel.classList.remove('hidden');
    panel.querySelector('.cal-ai-close').addEventListener('click', function() { panel.classList.add('hidden'); });
    document.getElementById('cal-extract-go').addEventListener('click', function() {
      var text = (document.getElementById('cal-extract-text').value || '').trim();
      if (!text) { if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Paste some text first', 'error'); return; }
      this.disabled = true;
      this.textContent = 'Extracting…';
      apiPost('/api/ai/calendar/extract', { text: text }).then(function(data) {
        var evs = data.events || [];
        if (evs.length === 0) { panel.querySelector('.cal-ai-output') && (panel.querySelector('.cal-ai-output').innerHTML = '<p class="cal-ai-muted">No events found.</p>'); return; }
        var html = '<div class="cal-ai-output"><p class="cal-ai-label">Extracted events (edit, then add):</p><ul class="cal-ai-list">' +
          evs.map(function(e) {
            return '<li><input type="date" value="' + (e.date || '') + '"> <input type="time" value="' + (e.time_start || '') + '" placeholder="All day"> ' +
              '<input type="text" value="' + (e.title || '').replace(/"/g, '&quot;') + '" placeholder="Title"> ' +
              '<button type="button" class="btn btn-small btn-primary cal-ai-add-event">Add</button></li>';
          }).join('') + '</ul></div>';
        panel.insertAdjacentHTML('beforeend', html);
        document.querySelectorAll('.cal-ai-add-event').forEach(function(b) {
          b.addEventListener('click', function() {
            var li = b.closest('li');
            var inp = li.querySelectorAll('input');
            var date = inp[0].value;
            var time = inp[1].value;
            var title = (inp[2].value || '').trim();
            if (!date || !title) return;
            var payload = { date: date, title: title };
            if (time) payload.time_start = time;
            api('POST', '/api/events', payload).then(function() {
              li.remove();
              renderCalendar();
              if (typeof Aevel !== 'undefined' && Aevel.toast) Aevel.toast('Event added', 'success');
            }).catch(function() {});
          });
        });
      }).catch(function(err) {
        showAIPanel('<p class="cal-ai-error">' + (err.message || 'Failed').replace(/</g, '&lt;') + '</p>');
      }).finally(function() {
        document.getElementById('cal-extract-go').disabled = false;
        document.getElementById('cal-extract-go').textContent = 'Extract';
      });
    });
  });

  setFormDateToToday();
  renderCalendar();
})();
