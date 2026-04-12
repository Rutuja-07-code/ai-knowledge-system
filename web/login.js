/* ============================================================
   Login Page — Multi-step wizard logic
   ============================================================ */

const INTEREST_CATALOG = [
  { key: "technology", label: "Technology", icon: "💻" },
  { key: "science", label: "Science", icon: "🔬" },
  { key: "world", label: "World", icon: "🌍" },
  { key: "business", label: "Business", icon: "📊" },
  { key: "health", label: "Health", icon: "🏥" },
  { key: "sports", label: "Sports", icon: "⚽" },
  { key: "ai_ml", label: "AI & ML", icon: "🤖" },
  { key: "climate", label: "Climate", icon: "🌿" },
];

const steps = [
  document.getElementById("step0"),
  document.getElementById("step1"),
  document.getElementById("step2"),
];
const dots = document.querySelectorAll(".step-dot");
const nameInput = document.getElementById("userName");
const btnGetStarted = document.getElementById("btnGetStarted");
const btnBackToWelcome = document.getElementById("btnBackToWelcome");
const btnToInterests = document.getElementById("btnToInterests");
const btnBackToProfile = document.getElementById("btnBackToProfile");
const btnLaunch = document.getElementById("btnLaunch");
const interestGrid = document.getElementById("interestGrid");

let currentStep = 0;
let selectedInterests = new Set();

/* ----- redirect if already logged in ----- */
(function checkExistingProfile() {
  const profile = localStorage.getItem("aiks_profile");
  if (profile) {
    try {
      const parsed = JSON.parse(profile);
      if (parsed.name && parsed.interests && parsed.interests.length > 0) {
        window.location.href = "/dashboard.html";
        return;
      }
    } catch (_) {
      /* invalid — stay on login */
    }
  }
})();

/* ----- step navigation ----- */
function goToStep(index) {
  steps[currentStep].classList.remove("active");
  steps[index].classList.add("active");

  dots.forEach((dot, i) => {
    dot.classList.remove("active", "done");
    if (i < index) dot.classList.add("done");
    if (i === index) dot.classList.add("active");
  });

  currentStep = index;

  if (index === 1) {
    nameInput.focus();
  }
}

/* ----- build interest grid ----- */
function renderInterests() {
  interestGrid.innerHTML = INTEREST_CATALOG.map(
    (interest) => `
      <div
        class="interest-chip"
        data-key="${interest.key}"
        role="button"
        tabindex="0"
        aria-pressed="false"
      >
        <span class="chip-icon">${interest.icon}</span>
        <span>${interest.label}</span>
        <span class="chip-check">✓</span>
      </div>
    `
  ).join("");
}
renderInterests();

/* ----- interest selection ----- */
interestGrid.addEventListener("click", (event) => {
  const chip = event.target.closest(".interest-chip");
  if (!chip) return;

  const key = chip.dataset.key;
  if (selectedInterests.has(key)) {
    selectedInterests.delete(key);
    chip.classList.remove("selected");
    chip.setAttribute("aria-pressed", "false");
  } else {
    selectedInterests.add(key);
    chip.classList.add("selected");
    chip.setAttribute("aria-pressed", "true");
  }

  btnLaunch.disabled = selectedInterests.size === 0;
});

/* ----- name input validation ----- */
nameInput.addEventListener("input", () => {
  btnToInterests.disabled = nameInput.value.trim().length === 0;
});
nameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && nameInput.value.trim().length > 0) {
    event.preventDefault();
    goToStep(2);
  }
});

/* ----- button handlers ----- */
btnGetStarted.addEventListener("click", () => goToStep(1));
btnBackToWelcome.addEventListener("click", () => goToStep(0));
btnToInterests.addEventListener("click", () => {
  if (nameInput.value.trim().length > 0) goToStep(2);
});
btnBackToProfile.addEventListener("click", () => goToStep(1));

btnLaunch.addEventListener("click", () => {
  const name = nameInput.value.trim();
  const interests = Array.from(selectedInterests);

  if (!name || interests.length === 0) return;

  const profile = { name, interests, createdAt: new Date().toISOString() };
  localStorage.setItem("aiks_profile", JSON.stringify(profile));

  window.location.href = "/dashboard.html";
});
