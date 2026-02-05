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
    connecting: null, // {fromId, fromPort}
    dragging: null,   // {shape, offsetX, offsetY}
    currentId: null,
    nextShapeId: 1
  };

  // ============================================
  // SHAPE DEFINITIONS
  // ============================================
  var SHAPE_TYPES = {
    rectangle:     { label: 'Process',      color: '#3b82f6', textColor: '#fff', width: 140, height: 50 },
    diamond:       { label: 'Decision',     color: '#f59e0b', textColor: '#fff', width: 100, height: 80 },
    parallelogram: { label: 'Input/Output', color: '#10b981', textColor: '#fff', width: 140, height: 50 },
    cylinder:      { label: 'Data Store',   color: '#8b5cf6', textColor: '#fff', width: 100, height: 70 },
    cloud:         { label: 'External',     color: '#6b7280', textColor: '#fff', width: 120, height: 60 },
    note:          { label: 'Note',         color: '#fbbf24', textColor: '#000', width: 120, height: 60 }
  };

  // ============================================
  // DOM ELEMENTS
  // ============================================
  var canvas, svg, shapesLayer, connectionsLayer, portsLayer;
  var listEl, emptyEl, editorWrap, titleInput;

  function init() {
    canvas = document.getElementById('whiteboard-canvas');
    svg = document.getElementById('whiteboard-svg');
    shapesLayer = document.getElementById('shapes-layer');
    connectionsLayer = document.getElementById('connections-layer');
    portsLayer = document.getElementById('ports-layer');
    listEl = document.getElementById('flowchart-list');
    emptyEl = document.getElementById('flowchart-empty');
    editorWrap = document.getElementById('flowchart-editor');
    titleInput = document.getElementById('flowchart-title');

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
        if (state.selectedShape && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
          e.preventDefault();
          deleteShape(state.selectedShape);
        } else if (state.selectedConnection) {
          e.preventDefault();
          deleteConnection(state.selectedConnection);
        }
      }
      if (e.key === 'Escape') {
        cancelConnecting();
        deselectAll();
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

    // Check if clicking a port
    if (target.classList.contains('shape-port')) {
      var shapeId = target.getAttribute('data-shape-id');
      var port = target.getAttribute('data-port');
      startConnecting(shapeId, port, pos);
      return;
    }

    // Check if clicking a shape
    var shapeEl = target.closest('.wb-shape');
    if (shapeEl) {
      var id = shapeEl.getAttribute('data-id');
      var shape = state.shapes.find(function(s) { return s.id === id; });
      if (shape) {
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

    if (state.connecting) {
      updateTempConnection(pos);
    }
  }

  function onCanvasMouseUp(e) {
    if (state.dragging) {
      state.dragging = null;
    }

    if (state.connecting) {
      var target = e.target;
      if (target.classList.contains('shape-port')) {
        var toId = target.getAttribute('data-shape-id');
        var toPort = target.getAttribute('data-port');
        if (toId !== state.connecting.fromId) {
          addConnection(state.connecting.fromId, state.connecting.fromPort, toId, toPort);
        }
      }
      cancelConnecting();
    }
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
      text: text || def.label
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
    var ports = portsLayer.querySelectorAll('[data-shape-id="' + shape.id + '"]');
    ports.forEach(function(p) { p.remove(); });

    deselectAll();
    toast('Shape deleted', 'success');
  }

  function selectShape(shape) {
    deselectAll();
    state.selectedShape = shape;
    var el = shapesLayer.querySelector('[data-id="' + shape.id + '"]');
    if (el) el.classList.add('selected');
    showPorts(shape);
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
    hidePorts();
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

    // Text
    var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', shape.width / 2);
    text.setAttribute('y', shape.height / 2 + 4);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('fill', def.textColor);
    text.setAttribute('font-size', '12');
    text.setAttribute('font-family', 'Inter, sans-serif');
    text.setAttribute('pointer-events', 'none');
    text.textContent = truncateText(shape.text, 16);
    g.appendChild(text);

    shapesLayer.appendChild(g);

    // Update ports if selected
    if (state.selectedShape && state.selectedShape.id === shape.id) {
      showPorts(shape);
    }
  }

  function truncateText(text, max) {
    return text.length > max ? text.substring(0, max - 1) + '…' : text;
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
    
    // Body
    var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', '0');
    rect.setAttribute('y', ry);
    rect.setAttribute('width', w);
    rect.setAttribute('height', h - ry * 2);
    rect.setAttribute('fill', color);
    g.appendChild(rect);

    // Top ellipse
    var top = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
    top.setAttribute('cx', w / 2);
    top.setAttribute('cy', ry);
    top.setAttribute('rx', w / 2);
    top.setAttribute('ry', ry);
    top.setAttribute('fill', color);
    top.setAttribute('stroke', '#fff');
    top.setAttribute('stroke-width', '2');
    g.appendChild(top);

    // Bottom ellipse
    var bottom = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
    bottom.setAttribute('cx', w / 2);
    bottom.setAttribute('cy', h - ry);
    bottom.setAttribute('rx', w / 2);
    bottom.setAttribute('ry', ry);
    bottom.setAttribute('fill', color);
    bottom.setAttribute('stroke', '#fff');
    bottom.setAttribute('stroke-width', '2');
    g.appendChild(bottom);

    // Side strokes
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
  // PORTS (Connection Points)
  // ============================================
  function showPorts(shape) {
    hidePorts();
    var ports = getPortPositions(shape);
    Object.keys(ports).forEach(function(portName) {
      var pos = ports[portName];
      var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('class', 'shape-port');
      circle.setAttribute('cx', pos.x);
      circle.setAttribute('cy', pos.y);
      circle.setAttribute('r', '6');
      circle.setAttribute('data-shape-id', shape.id);
      circle.setAttribute('data-port', portName);
      portsLayer.appendChild(circle);
    });
  }

  function hidePorts() {
    portsLayer.innerHTML = '';
  }

  function getPortPositions(shape) {
    return {
      top:    { x: shape.x + shape.width / 2, y: shape.y },
      bottom: { x: shape.x + shape.width / 2, y: shape.y + shape.height },
      left:   { x: shape.x, y: shape.y + shape.height / 2 },
      right:  { x: shape.x + shape.width, y: shape.y + shape.height / 2 }
    };
  }

  // ============================================
  // CONNECTIONS
  // ============================================
  function startConnecting(fromId, fromPort, pos) {
    state.connecting = { fromId: fromId, fromPort: fromPort, startPos: pos };
    
    // Create temp line
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('id', 'temp-connection');
    line.setAttribute('class', 'wb-connection temp');
    line.setAttribute('x1', pos.x);
    line.setAttribute('y1', pos.y);
    line.setAttribute('x2', pos.x);
    line.setAttribute('y2', pos.y);
    connectionsLayer.appendChild(line);
  }

  function updateTempConnection(pos) {
    var line = document.getElementById('temp-connection');
    if (line) {
      line.setAttribute('x2', pos.x);
      line.setAttribute('y2', pos.y);
    }
  }

  function cancelConnecting() {
    state.connecting = null;
    var temp = document.getElementById('temp-connection');
    if (temp) temp.remove();
  }

  function addConnection(fromId, fromPort, toId, toPort, label) {
    var conn = {
      id: 'conn-' + Date.now(),
      from: fromId,
      fromPort: fromPort,
      to: toId,
      toPort: toPort,
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
    toast('Connection deleted', 'success');
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

    var fromPorts = getPortPositions(fromShape);
    var toPorts = getPortPositions(toShape);
    var start = fromPorts[conn.fromPort];
    var end = toPorts[conn.toPort];

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

    // Label
    if (conn.label) {
      var midX = (start.x + end.x) / 2;
      var midY = (start.y + end.y) / 2;
      var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', midX);
      text.setAttribute('y', midY - 5);
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', '#fff');
      text.setAttribute('font-size', '11');
      text.textContent = conn.label;
      g.appendChild(text);
    }

    connectionsLayer.appendChild(g);
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
        state.nextShapeId = Math.max.apply(null, state.shapes.map(function(s) {
          return parseInt(s.id.replace('shape-', '')) || 0;
        })) + 1;
        state.shapes.forEach(renderShape);
      }
      if (parsed.connections && Array.isArray(parsed.connections)) {
        state.connections = parsed.connections;
        state.connections.forEach(renderConnection);
      }
    } catch (e) {
      // Not JSON, might be old Mermaid format - ignore
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
    state.nextShapeId = 1;
    shapesLayer.innerHTML = '';
    connectionsLayer.innerHTML = '';
    portsLayer.innerHTML = '';
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
  // EDIT SHAPE TEXT
  // ============================================
  function editShapeText(shape) {
    var newText = prompt('Edit label:', shape.text);
    if (newText !== null) {
      shape.text = newText;
      renderShape(shape);
    }
  }

  // Double-click to edit
  function setupDoubleClick() {
    svg.addEventListener('dblclick', function(e) {
      var shapeEl = e.target.closest('.wb-shape');
      if (shapeEl) {
        var id = shapeEl.getAttribute('data-id');
        var shape = state.shapes.find(function(s) { return s.id === id; });
        if (shape) {
          editShapeText(shape);
        }
      }
    });
  }

  // ============================================
  // INIT
  // ============================================
  document.addEventListener('DOMContentLoaded', function() {
    init();
    setupButtonHandlers();
    setupDoubleClick();
  });

})();
