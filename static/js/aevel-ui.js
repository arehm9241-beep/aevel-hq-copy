/**
 * Aevel — shared UI utilities: toasts, confirm modal, loading states
 */
(function() {
  var toastContainer = null;

  function getToastContainer() {
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.className = 'toast-container';
      toastContainer.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastContainer);
    }
    return toastContainer;
  }

  window.Aevel = {
    toast: function(message, type) {
      type = type || 'success';
      var el = document.createElement('div');
      el.className = 'toast toast--' + type;
      el.textContent = message;
      getToastContainer().appendChild(el);
      requestAnimationFrame(function() { el.classList.add('toast--visible'); });
      setTimeout(function() {
        el.classList.remove('toast--visible');
        setTimeout(function() { el.remove(); }, 300);
      }, 3200);
    },

    undoToast: function(message, onUndo) {
      var el = document.createElement('div');
      el.className = 'toast toast--success toast-undo';
      el.innerHTML = '<span class="toast-undo-msg">' + (message.replace(/</g, '&lt;')) + '</span> <button type="button" class="btn btn-small btn-ghost toast-undo-btn">Undo</button>';
      getToastContainer().appendChild(el);
      requestAnimationFrame(function() { el.classList.add('toast--visible'); });
      var t = setTimeout(function() {
        el.classList.remove('toast--visible');
        setTimeout(function() { el.remove(); }, 300);
      }, 5000);
      el.querySelector('.toast-undo-btn').addEventListener('click', function() {
        clearTimeout(t);
        if (typeof onUndo === 'function') onUndo();
        el.classList.remove('toast--visible');
        setTimeout(function() { el.remove(); }, 300);
      });
    },

    confirm: function(options, onConfirm, onCancel) {
      var title = options.title || 'Confirm';
      var body = options.body || 'Are you sure?';
      var confirmLabel = options.confirmLabel || 'Confirm';
      var cancelLabel = options.cancelLabel || 'Cancel';
      var danger = options.danger === true;

      var overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-labelledby', 'confirm-title');

      var modal = document.createElement('div');
      modal.className = 'confirm-modal';
      modal.innerHTML =
        '<h3 id="confirm-title" class="confirm-modal__title">' + (title.replace(/</g, '&lt;')) + '</h3>' +
        '<p class="confirm-modal__body">' + (body.replace(/</g, '&lt;')) + '</p>' +
        '<div class="confirm-modal__actions">' +
          '<button type="button" class="btn btn-ghost confirm-cancel">' + (cancelLabel.replace(/</g, '&lt;')) + '</button>' +
          '<button type="button" class="btn ' + (danger ? 'btn-danger' : 'btn-primary') + ' confirm-ok">' + (confirmLabel.replace(/</g, '&lt;')) + '</button>' +
        '</div>';
      overlay.appendChild(modal);

      function close(result) {
        overlay.classList.remove('modal-overlay--visible');
        setTimeout(function() {
          overlay.remove();
          document.body.style.overflow = '';
        }, 200);
        if (result && typeof onConfirm === 'function') onConfirm();
        if (!result && typeof onCancel === 'function') onCancel();
      }

      modal.querySelector('.confirm-ok').addEventListener('click', function() { close(true); });
      modal.querySelector('.confirm-cancel').addEventListener('click', function() { close(false); });
      overlay.addEventListener('click', function(e) { if (e.target === overlay) close(false); });
      overlay.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') close(false);
        if (e.key === 'Enter') close(true);
      });

      document.body.style.overflow = 'hidden';
      document.body.appendChild(overlay);
      requestAnimationFrame(function() { overlay.classList.add('modal-overlay--visible'); });
      modal.querySelector('.confirm-ok').focus();
    },

    loading: function(containerId, show) {
      var el = document.getElementById(containerId);
      if (!el) return;
      if (show) {
        el.classList.add('loading-active');
        el.setAttribute('aria-busy', 'true');
      } else {
        el.classList.remove('loading-active');
        el.removeAttribute('aria-busy');
      }
    },

    /** API helper: fetch + parse JSON, show error toast on failure, return data or throw */
    api: function(method, path, body) {
      var opts = { method: method, credentials: 'same-origin', headers: {} };
      if (body !== undefined) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
      var self = this;
      return fetch(path, opts).then(function(r) {
        return r.json().then(function(data) {
          if (!r.ok) {
            var msg = (data && data.error) ? data.error : 'Request failed';
            if (self.toast) self.toast(msg, 'error');
            throw new Error(msg);
          }
          return data;
        });
      }).catch(function(err) {
        if (self.toast && (!err.message || err.message === 'Failed to fetch')) self.toast('Request failed', 'error');
        else if (self.toast && err.message) self.toast(err.message, 'error');
        throw err;
      });
    }
  };
})();
