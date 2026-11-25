/* Prayer Watch page only. If the "next" gathering has ended and the page has not been regenerated yet,
   swap it for a plain note. tools/update.py writes the real next date. */
const live = document.querySelector('[data-ends]');
if (live && Date.now() > Date.parse(live.dataset.ends)) {
  live.hidden = true;
  document.querySelector('[data-passed]').hidden = false;
}
