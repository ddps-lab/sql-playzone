// Shows a banner on every admin page while an exam rule is switched on, so
// nobody forgets to switch it off after the exam.
(async function () {
  const rules = {
    exam_browser_required: "exam browser only",
    single_session_required: "one session per student",
  };
  const root = (window.CTFd && CTFd.config && CTFd.config.urlRoot) || "";
  const active = [];
  for (const key of Object.keys(rules)) {
    try {
      const response = await fetch(`${root}/api/v1/configs/${key}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) continue;
      const body = await response.json();
      const value = body.data && body.data.value;
      if (value === true || value === "true") active.push(rules[key]);
    } catch (error) {
      // a failed lookup only hides the banner
    }
  }
  if (!active.length) return;
  const banner = document.createElement("div");
  banner.className = "alert alert-warning text-center rounded-0 mb-0";
  banner.setAttribute("role", "alert");
  banner.textContent = `Exam rules are on: ${active.join(", ")}. Switch them off after the exam (Admin > Exam Mode).`;
  // <main> starts below the fixed navbar; the body itself is covered by it
  const container = document.querySelector("main") || document.body;
  container.insertBefore(banner, container.firstChild);
})();
