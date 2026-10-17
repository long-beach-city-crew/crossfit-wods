// Description toggle on the workout page. Delegated from document so it keeps
// working after hx-boost swaps the body.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-toggle]");
  if (!button) return;
  const target = document.getElementById(button.dataset.toggle);
  target.hidden = !target.hidden;
  button.setAttribute("aria-expanded", !target.hidden);
});
