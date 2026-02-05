(function() {
  'use strict';

  // ============================================
  // WHITEBOARD STATE
  // ============================================
  var state = {
    shapes: [],
    connections: [],
    selectedShape: null,
    selectedConnection: null,
    lineMode: false,
    lineStart: null,
    dragging: null,
    currentId: null,
    nextShapeId: 1
  };

  // ============================================
  // SHAPE DEFINITIONS
  // ============================================
  var SHAPE_TYPES = {
    rectangle:     { color: '#3b82f6', textColor: '#fff', width: 160, height: 60 },
    diamond:       { color: '#f59e0b', textColor: '#fff', width: 120, height: 100 },
    parallelogram: { color: '#10b981', textColor: '#fff', width: 160, height: 60 },
    cylinder:      { color: '#8b5cf6', textColor: '#fff', width: 120, height: 80 },
    cloud:         { color: '#6b7280', textColor: '#fff', width: 140, height: 80 },
    note:          { color: '#fbbf24', textColor: '#000', width: 140, height: 80 }
  };

  // ============================================
  // DOM ELEMENTS
  // ============================================
  var canvas, svg, shapesLayer, connectionsLayer;
  var listEl, emptyEl, editorWrap, titleInput, lineModeBtn;

  function init() {
    canvas = document.getElementById('whiteboard-canvas');
    svg = document.getElementById('whiteboard-svg');
    shapesLayer = document.getElementById('shapes-layer');
    connectionsLayer = document.getElementById('connections-layer');
    listEl = document.getElementById('flowchart-list');
    emptyEl = document.getElementById('flowchart-empty');
    editorWrap = document.getElementById('flowchart-editor');
    titleInput = document.getElementById('flowchart-title');
    lineModeBtn = document.getElementById('line-mode-btn');

    if (!canvas || !svg) return;

    setupToolbar();
    setupCanvasEvents();
    loadList();
    showEmpty();
  }

  // ============================================
  // API HELPER
  // ============================================
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
        if (!r.ok) throw new Error(data.error || 'Request failed');
        return data;
      });
    });
  }

  // ============================================
  // TOOLBAR SETUP
  // ============================================
  function setupToolbar() {
    var toolbar = document.getElementById('shape-toolbar');
    if (!toolbar) return;

    toolbar.querySelectorAll('.shape-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var type = this.getAttribute('data-shape');
        if (type && SHAPE_TYPES[type]) {
          addShape(type, 200 + Math.random() * 200, 150 + Math.random() * 100);
        }
      });
    });

    // Line mode toggle
    if (lineModeBtn) {
      lineModeBtn.addEventListener('click', function() {
        state.lineMode = !state.lineMode;
        this.classList.toggle('active', state.lineMode);
        svg.style.cursor = state.lineMode ? 'crosshair' : 'default';
        if (!state.lineMode) {
          cancelLine();
        }
      });
    }
  }

  // ============================================
  // CANVAS EVENTS
  // ============================================
  function setupCanvasEvents() {
    svg.addEventListener('mousedown', onCanvasMouseDown);
    svg.addEventListener('mousemove', onCanvasMouseMove);
    svg.addEventListener('mouseup', onCanvasMouseUp);
    svg.addEventListener('mouseleave', onCanvasMouseUp);

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        var active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) {
          return; // Let delete work in text fields
        }
        e.preventDefault();
        if (state.selectedShape) {
          deleteShape(state.selectedShape);
        } else if (state.selectedConnection) {
          deleteConnection(state.selectedConnection);
        }
      }
      if (e.key === 'Escape') {
        cancelLine();
        deselectAll();
        state.lineMode = false;
        if (lineModeBtn) lineModeBtn.classList.remove('active');
        svg.style.cursor = 'default';
      }
    });
  }

  function getMousePos(e) {
    var rect = svg.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function onCanvasMouseDown(e) {
    var pos = getMousePos(e);
    var target = e.target;

    // Ignore clicks on text inputs
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
      return;
    }

    // Check if clicking a shape
    var shapeEl = target.closest('.wb-shape');
    if (shapeEl) {
      var id = shapeEl.getAttribute('data-id');
      var shape = state.shapes.find(function(s) { return s.id === id; });
      if (shape) {
        if (state.lineMode) {
          // Line mode: start or end line
          if (!state.lineStart) {
            state.lineStart = shape;
            createTempLine(shape, pos);
          } else if (state.lineStart.id !== shape.id) {
            // Complete the line
            addConnection(state.lineStart.id, shape.id);
            cancelLine();
          }
          return;
        }
        selectShape(shape);
        state.dragging = {
          shape: shape,
          offsetX: pos.x - shape.x,
          offsetY: pos.y - shape.y
        };
      }
      return;
    }

    // Check if clicking a connection
    var connEl = target.closest('.wb-connection');
    if (connEl) {
      var connId = connEl.getAttribute('data-id');
      selectConnection(connId);
      return;
    }

    // Clicking empty space
    deselectAll();
    if (state.lineMode) {
      cancelLine();
    }
  }

  function onCanvasMouseMove(e) {
    var pos = getMousePos(e);

    if (state.dragging) {
      var shape = state.dragging.shape;
      shape.x = Math.max(0, pos.x - state.dragging.offsetX);
      shape.y = Math.max(0, pos.y - state.dragging.offsetY);
      renderShape(shape);
      updateConnectionsForShape(shape.id);
    }

    if (state.lineStart) {
      updateTempLine(pos);
    }
  }

  function onCanvasMouseUp(e) {
    if (state.dragging) {
      state.dragging = null;
    }
  }

  // ============================================
  // LINE DRAWING
  // ============================================
  function createTempLine(fromShape, pos) {
    var startX = fromShape.x + fromShape.width / 2;
    var startY = fromShape.y + fromShape.height / 2;
    
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('id', 'temp-line');
    line.setAttribute('class', 'wb-connection temp');
    line.setAttribute('x1', startX);
    line.setAttribute('y1', startY);
    line.setAttribute('x2', pos.x);
    line.setAttribute('y2', pos.y);
    connectionsLayer.appendChild(line);
  }

  function updateTempLine(pos) {
    var line = document.getElementById('temp-line');
    if (line) {
      line.setAttribute('x2', pos.x);
      line.setAttribute('y2', pos.y);
    }
  }

  function cancelLine() {
    state.lineStart = null;
    var temp = document.getElementById('temp-line');
    if (temp) temp.remove();
  }

  // ============================================
  // SHAPE MANAGEMENT
  // ============================================
  function addShape(type, x, y, text) {
    var def = SHAPE_TYPES[type];
    var shape = {
      id: 'shape-' + (state.nextShapeId++),
      type: type,
      x: x,
      y: y,
      width: def.width,
      height: def.height,
      text: text || ''
    };
    state.shapes.push(shape);
    renderShape(shape);
    selectShape(shape);
    return shape;
  }

  function deleteShape(shape) {
    // Remove connections to/from this shape
    state.connections = state.connections.filter(function(c) {
      if (c.from === shape.id || c.to === shape.id) {
        removeConnectionElement(c.id);
        return false;
      }
      return true;
    });

    // Remove shape
    state.shapes = state.shapes.filter(function(s) { return s.id !== shape.id; });
    var el = shapesLayer.querySelector('[data-id="' + shape.id + '"]');
    if (el) el.remove();

    deselectAll();
    toast('Deleted', 'success');
  }

  function selectShape(shape) {
    deselectAll();
    state.selectedShape = shape;
    var el = shapesLayer.querySelector('[data-id="' + shape.id + '"]');
    if (el) el.classList.add('selected');
  }

  function deselectAll() {
    state.selectedShape = null;
    state.selectedConnection = null;
    shapesLayer.querySelectorAll('.selected').forEach(function(el) {
      el.classList.remove('selected');
    });
    connectionsLayer.querySelectorAll('.selected').forEach(function(el) {
      el.classList.remove('selected');
    });
  }

  // ============================================
  // SHAPE RENDERING
  // ============================================
  function renderShape(shape) {
    var existing = shapesLayer.querySelector('[data-id="' + shape.id + '"]');
    if (existing) existing.remove();

    var def = SHAPE_TYPES[shape.type];
    var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'wb-shape' + (state.selectedShape === shape ? ' selected' : ''));
    g.setAttribute('data-id', shape.id);
    g.setAttribute('transform', 'translate(' + shape.x + ',' + shape.y + ')');

    var path;
    switch (shape.type) {
      case 'rectangle':
        path = createRect(shape.width, shape.height, def.color);
        break;
      case 'diamond':
        path = createDiamond(shape.width, shape.height, def.color);
        break;
      case 'parallelogram':
        path = createParallelogram(shape.width, shape.height, def.color);
        break;
      case 'cylinder':
        path = createCylinder(shape.width, shape.height, def.color);
        break;
      case 'cloud':
        path = createCloud(shape.width, shape.height, def.color);
        break;
      case 'note':
        path = createNote(shape.width, shape.height, def.color);
        break;
      default:
        path = createRect(shape.width, shape.height, def.color);
    }
    g.appendChild(path);

    // Editable text using foreignObject
    var fo = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
    fo.setAttribute('x', '10');
    fo.setAttribute('y', '10');
    fo.setAttribute('width', shape.width - 20);
    fo.setAttribute('height', shape.height - 20);

    var textarea = document.createElement('textarea');
    textarea.className = 'shape-text-input';
    textarea.placeholder = 'Type here...';
    textarea.value = shape.text || '';
    textarea.style.cssText = 'width:100%;height:100%;background:transparent;border:none;outline:none;resize:none;' +
      'color:' + def.textColor + ';font-size:12px;font-family:Inter,sans-serif;text-align:center;' +
      'display:flex;align-items:center;justify-content:center;padding:4px;box-sizing:border-box;';
    
    textarea.addEventListener('input', function() {
      shape.text = this.value;
    });
    textarea.addEventListener('mousedown', function(e) {
      e.stopPropagation(); // Prevent drag when typing
    });
    textarea.addEventListener('focus', function() {
      selectShape(shape);
    });

    fo.appendChild(textarea);
    g.appendChild(fo);

    shapesLayer.appendChild(g);
  }

  function createRect(w, h, color) {
    var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('width', w);
    rect.setAttribute('height', h);
    rect.setAttribute('rx', '6');
    rect.setAttribute('fill', color);
    rect.setAttribute('stroke', '#fff');
    rect.setAttribute('stroke-width', '2');
    return rect;
  }

  function createDiamond(w, h, color) {
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    var points = [
      (w/2) + ',0',
      w + ',' + (h/2),
      (w/2) + ',' + h,
      '0,' + (h/2)
    ].join(' ');
    path.setAttribute('points', points);
    path.setAttribute('fill', color);
    path.setAttribute('stroke', '#fff');
    path.setAttribute('stroke-width', '2');
    return path;
  }

  function createParallelogram(w, h, color) {
    var skew = 15;
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    var points = [
      skew + ',0',
      w + ',0',
      (w - skew) + ',' + h,
      '0,' + h
    ].join(' ');
    path.setAttribute('points', points);
    path.setAttribute('fill', color);
    path.setAttribute('stroke', '#fff');
    path.setAttribute('stroke-width', '2');
    return path;
  }

  function createCylinder(w, h, color) {
    var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    var ry = 10;
    
    var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', '0');
    rect.setAttribute('y', ry);
    rect.setAttribute('width', w);
    rect.setAttribute('height', h - ry * 2);
    rect.setAttribute('fill', color);
    g.appendChild(rect);

    var top = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
    top.setAttribute('cx', w / 2);
    top.setAttribute('cy', ry);
    top.setAttribute('rx', w / 2);
    top.setAttribute('ry', ry);
    top.setAttribute('fill', color);
    top.setAttribute('stroke', '#fff');
    top.setAttribute('stroke-width', '2');
    g.appendChild(top);

    var bottom = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
    bottom.setAttribute('cx', w / 2);
    bottom.setAttribute('cy', h - ry);
    bottom.setAttribute('rx', w / 2);
    bottom.setAttribute('ry', ry);
    bottom.setAttribute('fill', color);
    bottom.setAttribute('stroke', '#fff');
    bottom.setAttribute('stroke-width', '2');
    g.appendChild(bottom);

    var left = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    left.setAttribute('x1', '0');
    left.setAttribute('y1', ry);
    left.setAttribute('x2', '0');
    left.setAttribute('y2', h - ry);
    left.setAttribute('stroke', '#fff');
    left.setAttribute('stroke-width', '2');
    g.appendChild(left);

    var right = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    right.setAttribute('x1', w);
    right.setAttribute('y1', ry);
    right.setAttribute('x2', w);
    right.setAttribute('y2', h - ry);
    right.setAttribute('stroke', '#fff');
    right.setAttribute('stroke-width', '2');
    g.appendChild(right);

    return g;
  }

  function createCloud(w, h, color) {
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    var d = 'M' + (w * 0.2) + ',' + (h * 0.7) +
            ' Q0,' + (h * 0.7) + ' 0,' + (h * 0.5) +
            ' Q0,' + (h * 0.2) + ' ' + (w * 0.25) + ',' + (h * 0.2) +
            ' Q' + (w * 0.3) + ',0 ' + (w * 0.5) + ',0' +
            ' Q' + (w * 0.7) + ',0 ' + (w * 0.75) + ',' + (h * 0.15) +
            ' Q' + w + ',' + (h * 0.15) + ' ' + w + ',' + (h * 0.4) +
            ' Q' + w + ',' + (h * 0.7) + ' ' + (w * 0.8) + ',' + (h * 0.7) +
            ' Z';
    path.setAttribute('d', d);
    path.setAttribute('fill', color);
    path.setAttribute('stroke', '#fff');
    path.setAttribute('stroke-width', '2');
    return path;
  }

  function createNote(w, h, color) {
    var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    var fold = 12;
    
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    var d = 'M0,0 L' + (w - fold) + ',0 L' + w + ',' + fold + ' L' + w + ',' + h + ' L0,' + h + ' Z';
    path.setAttribute('d', d);
    path.setAttribute('fill', color);
    path.setAttribute('stroke', '#666');
    path.setAttribute('stroke-width', '2');
    g.appendChild(path);

    var corner = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    corner.setAttribute('d', 'M' + (w - fold) + ',0 L' + (w - fold) + ',' + fold + ' L' + w + ',' + fold);
    corner.setAttribute('fill', 'none');
    corner.setAttribute('stroke', '#666');
    corner.setAttribute('stroke-width', '1');
    g.appendChild(corner);

    return g;
  }

  // ============================================
  // CONNECTIONS
  // ============================================
  function addConnection(fromId, toId, label) {
    // Check if connection already exists
    var exists = state.connections.some(function(c) {
      return (c.from === fromId && c.to === toId) || (c.from === toId && c.to === fromId);
    });
    if (exists) return;

    var conn = {
      id: 'conn-' + Date.now(),
      from: fromId,
      to: toId,
      label: label || ''
    };
    state.connections.push(conn);
    renderConnection(conn);
    return conn;
  }

  function deleteConnection(connId) {
    state.connections = state.connections.filter(function(c) { return c.id !== connId; });
    removeConnectionElement(connId);
    deselectAll();
    toast('Line deleted', 'success');
  }

  function removeConnectionElement(connId) {
    var el = connectionsLayer.querySelector('[data-id="' + connId + '"]');
    if (el) el.remove();
  }

  function selectConnection(connId) {
    deselectAll();
    state.selectedConnection = connId;
    var el = connectionsLayer.querySelector('[data-id="' + connId + '"]');
    if (el) el.classList.add('selected');
  }

  function renderConnection(conn) {
    var existing = connectionsLayer.querySelector('[data-id="' + conn.id + '"]');
    if (existing) existing.remove();

    var fromShape = state.shapes.find(function(s) { return s.id === conn.from; });
    var toShape = state.shapes.find(function(s) { return s.id === conn.to; });
    if (!fromShape || !toShape) return;

    // Calculate best connection points (center to center, then find edge)
    var start = getEdgePoint(fromShape, toShape);
    var end = getEdgePoint(toShape, fromShape);

    var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'wb-connection');
    g.setAttribute('data-id', conn.id);

    // Arrow line
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', start.x);
    line.setAttribute('y1', start.y);
    line.setAttribute('x2', end.x);
    line.setAttribute('y2', end.y);
    line.setAttribute('marker-end', 'url(#arrowhead)');
    g.appendChild(line);

    // Clickable hitbox (wider invisible line for easier selection)
    var hitbox = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    hitbox.setAttribute('x1', start.x);
    hitbox.setAttribute('y1', start.y);
    hitbox.setAttribute('x2', end.x);
    hitbox.setAttribute('y2', end.y);
    hitbox.setAttribute('stroke', 'transparent');
    hitbox.setAttribute('stroke-width', '12');
    hitbox.style.cursor = 'pointer';
    g.appendChild(hitbox);

    connectionsLayer.appendChild(g);
  }

  function getEdgePoint(fromShape, toShape) {
    var fromCx = fromShape.x + fromShape.width / 2;
    var fromCy = fromShape.y + fromShape.height / 2;
    var toCx = toShape.x + toShape.width / 2;
    var toCy = toShape.y + toShape.height / 2;

    var dx = toCx - fromCx;
    var dy = toCy - fromCy;
    var angle = Math.atan2(dy, dx);

    // Determine which edge to use
    var hw = fromShape.width / 2;
    var hh = fromShape.height / 2;

    var edgeAngle = Math.atan2(hh, hw);
    var absAngle = Math.abs(angle);

    var x, y;
    if (absAngle < edgeAngle || absAngle > Math.PI - edgeAngle) {
      // Left or right edge
      x = fromCx + (dx > 0 ? hw : -hw);
      y = fromCy + (dx > 0 ? hw : -hw) * Math.tan(angle);
    } else {
      // Top or bottom edge
      y = fromCy + (dy > 0 ? hh : -hh);
      x = fromCx + (dy > 0 ? hh : -hh) / Math.tan(angle);
    }

    return { x: x, y: y };
  }

  function updateConnectionsForShape(shapeId) {
    state.connections.forEach(function(conn) {
      if (conn.from === shapeId || conn.to === shapeId) {
        renderConnection(conn);
      }
    });
  }

  // ============================================
  // SAVE / LOAD
  // ============================================
  function loadList() {
    return api('GET', '/api/flowcharts').then(function(data) {
      var items = data.flowcharts || [];
      if (!listEl) return items;
      listEl.innerHTML = items.length ? items.map(function(f) {
        return '<li class="flowchart-item' + (f.id === state.currentId ? ' active' : '') + '" data-id="' + (f.id || '') + '">' +
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
    state.currentId = id;
    emptyEl.classList.add('hidden');
    editorWrap.classList.remove('hidden');
    api('GET', '/api/flowcharts/' + id).then(function(f) {
      if (f.error) return;
      titleInput.value = f.title || '';
      loadWhiteboardData(f.mermaid_text || '');
      loadList();
    }).catch(function() {});
  }

  function loadWhiteboardData(data) {
    clearCanvas();
    if (!data) return;
    
    try {
      var parsed = JSON.parse(data);
      if (parsed.shapes && Array.isArray(parsed.shapes)) {
        state.shapes = parsed.shapes;
        var maxId = 0;
        state.shapes.forEach(function(s) {
          var num = parseInt(s.id.replace('shape-', '')) || 0;
          if (num > maxId) maxId = num;
        });
        state.nextShapeId = maxId + 1;
        state.shapes.forEach(renderShape);
      }
      if (parsed.connections && Array.isArray(parsed.connections)) {
        state.connections = parsed.connections;
        state.connections.forEach(renderConnection);
      }
    } catch (e) {
      // Not JSON, ignore
    }
  }

  function getWhiteboardData() {
    return JSON.stringify({
      shapes: state.shapes,
      connections: state.connections
    });
  }

  function clearCanvas() {
    state.shapes = [];
    state.connections = [];
    state.selectedShape = null;
    state.selectedConnection = null;
    state.lineStart = null;
    state.nextShapeId = 1;
    shapesLayer.innerHTML = '';
    connectionsLayer.innerHTML = '';
  }

  function showEmpty() {
    state.currentId = null;
    editorWrap.classList.add('hidden');
    emptyEl.classList.remove('hidden');
    titleInput.value = '';
    clearCanvas();
  }

  // ============================================
  // TOOLBAR ACTIONS
  // ============================================
  function setupButtonHandlers() {
    var newBtn = document.getElementById('flowchart-new');
    var saveBtn = document.getElementById('flowchart-save');
    var deleteBtn = document.getElementById('flowchart-delete');
    var clearBtn = document.getElementById('flowchart-clear');

    if (newBtn) {
      newBtn.addEventListener('click', function() {
        api('POST', '/api/flowcharts', { title: 'Untitled flowchart', mermaid_text: '' }).then(function(f) {
          if (f.id) {
            state.currentId = f.id;
            emptyEl.classList.add('hidden');
            editorWrap.classList.remove('hidden');
            titleInput.value = f.title || '';
            clearCanvas();
            loadList();
            toast('Flowchart created', 'success');
          }
        });
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener('click', function() {
        if (!state.currentId) return;
        api('PATCH', '/api/flowcharts/' + state.currentId, {
          title: titleInput.value.trim() || 'Untitled flowchart',
          mermaid_text: getWhiteboardData()
        }).then(function() {
          loadList();
          toast('Saved', 'success');
        });
      });
    }

    if (deleteBtn) {
      deleteBtn.addEventListener('click', function() {
        if (!state.currentId) return;
        if (typeof Aevel !== 'undefined' && Aevel.confirm) {
          Aevel.confirm({ title: 'Delete flowchart', body: 'Delete this flowchart?', confirmLabel: 'Delete', cancelLabel: 'Cancel', danger: true }, function() {
            api('DELETE', '/api/flowcharts/' + state.currentId).then(function() {
              showEmpty();
              loadList();
              toast('Deleted', 'success');
            });
          });
        } else {
          api('DELETE', '/api/flowcharts/' + state.currentId).then(function() {
            showEmpty();
            loadList();
          });
        }
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', function() {
        clearCanvas();
        toast('Canvas cleared', 'info');
      });
    }
  }

  function toast(msg, type) {
    if (typeof Aevel !== 'undefined' && Aevel.toast) {
      Aevel.toast(msg, type);
    }
  }

  // ============================================
  // INIT
  // ============================================
  document.addEventListener('DOMContentLoaded', function() {
    init();
    setupButtonHandlers();
  });

})();
