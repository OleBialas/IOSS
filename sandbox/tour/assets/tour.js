// Start the repository tour on the home page of a repository.
// The tour starts by itself on the first visit. The "Start tour" button
// starts it again.

(() => {
  const match = location.pathname.match(/^\/([^/]+)\/([^/]+)\/?$/);
  const fileTable = document.querySelector("#repo-files-table");
  if (!match || !fileTable || !window.driver || !window.IOSS_TOUR_STEPS) {
    return;
  }

  const repo = `/${match[1]}/${match[2]}`;
  const doneKey = `ioss-tour-done:${repo}`;

  const steps = window.IOSS_TOUR_STEPS.map((step) => ({
    ...step,
    element: step.element?.replaceAll("{repo}", repo),
  }))
    .filter((step) => !step.element || document.querySelector(step.element))
    .map((step) => ({
      element: step.element,
      popover: { title: step.title, description: step.description },
    }));

  const tour = window.driver.js.driver({
    showProgress: true,
    steps,
    onDestroyed: () => {
      try {
        localStorage.setItem(doneKey, "1");
      } catch {
        // Private windows can block storage. The tour then starts each time.
      }
    },
  });

  const button = document.createElement("button");
  button.type = "button";
  button.className = "ui primary button";
  button.textContent = "Start tour";
  button.style.cssText = "position: fixed; right: 1.5rem; bottom: 1.5rem; z-index: 1000;";
  button.addEventListener("click", () => tour.drive());
  document.body.append(button);

  let done = false;
  try {
    done = localStorage.getItem(doneKey) === "1";
  } catch {
    // See onDestroyed.
  }
  if (!done) {
    tour.drive();
  }
})();
