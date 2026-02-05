(function() {
  var burger = document.getElementById('burger-toggle');
  var menu = document.getElementById('burger-menu');
  if (!burger || !menu) return;

  function setOpen(open) {
    burger.classList.toggle('is-open', open);
    menu.classList.toggle('is-open', open);
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  burger.addEventListener('click', function() {
    var isOpen = burger.classList.contains('is-open');
    setOpen(!isOpen);
  });

  document.addEventListener('click', function(e) {
    if (!menu.contains(e.target) && !burger.contains(e.target)) {
      setOpen(false);
    }
  });
})();

