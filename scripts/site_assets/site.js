(() => {
  const search = document.querySelector('[data-search]');
  const cards = [...document.querySelectorAll('[data-card]')];
  const filters = [...document.querySelectorAll('[data-filter]')];
  const status = document.querySelector('[data-results]');
  const empty = document.querySelector('[data-empty]');
  const requested = new URLSearchParams(location.search).get('category');
  let active = filters.some(item => item.dataset.filter === requested) ? requested : 'all';
  for (const item of filters) item.setAttribute('aria-pressed', String(item.dataset.filter === active));
  const update = () => {
    const query = (search?.value || '').trim().toLocaleLowerCase();
    let visible = 0;
    for (const card of cards) {
      const matches = (active === 'all' || card.dataset.category === active) && card.dataset.search.includes(query);
      card.hidden = !matches;
      if (matches) visible++;
    }
    if (status) status.textContent = `${visible} ${visible === 1 ? 'note' : 'notes'}`;
    if (empty) empty.hidden = visible !== 0;
  };
  for (const filter of filters) filter.addEventListener('click', () => {
    active = filter.dataset.filter;
    for (const item of filters) item.setAttribute('aria-pressed', String(item === filter));
    update();
  });
  search?.addEventListener('input', update);
  if (cards.length) update();
  function revealAnswer() {
    if (!location.hash) return;
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = document.getElementById(id);
    const details = target?.closest('details');
    if (details) { details.open = true; target.scrollIntoView(); }
  }
  window.addEventListener('hashchange', revealAnswer);
  revealAnswer();
})();
