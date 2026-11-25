/* Fades items in as they arrive. Does nothing for reduced motion; content is never hidden without JS. */
(() => {
  const root = document.documentElement;
  const items = [...document.querySelectorAll('[data-reveal]')];
  if (!items.length || matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  root.classList.add('js');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); } });
  }, { threshold: 0.12 });
  items.forEach((el) => io.observe(el));
})();
