const demoSteps = [
  {
    kind: "Operator objective",
    html: '<p class="demo-command">“Open Calculator and evaluate 12 × 8.”</p><p>The operator defines one bounded outcome. The task starts with no implied permission to write files or run shell commands.</p>',
  },
  {
    kind: "Perception snapshot",
    html: '<div class="snapshot"><span>window.title</span><strong>Calculator</strong><span>display.value</span><strong>0</strong><span>controls</span><strong>42 accessible elements</strong></div><p>The agent combines a screenshot with accessibility data instead of guessing from pixels alone.</p>',
  },
  {
    kind: "Structured function call",
    html: '<pre><code>{\n  <span>"name"</span>: "press_keys",\n  <span>"args"</span>: { "keys": ["12", "*", "8", "="] }\n}</code></pre><p>The model can select only from tools exposed by the active permission tier and runtime.</p>',
  },
  {
    kind: "Verified outcome",
    html: '<div class="result"><small>Calculator display</small><strong>96</strong><span>verified</span></div><p>The next observation confirms the result. Only then can the agent call <code>finish_task</code>.</p>',
  },
];

const tabs = [...document.querySelectorAll("[data-step]")];
const content = document.querySelector("#demo-content");
const kind = document.querySelector("#demo-kind");
const counter = document.querySelector("#demo-counter");
const progress = document.querySelector("#demo-progress");
const control = document.querySelector("#demo-control");
const panel = document.querySelector("#demo-panel");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let activeStep = 0;
let playing = !reduceMotion;
let timer;

function showStep(index) {
  activeStep = index;
  const step = demoSteps[index];
  kind.textContent = step.kind;
  counter.textContent = `${String(index + 1).padStart(2, "0")} / 04`;
  content.innerHTML = step.html;
  tabs.forEach((tab, tabIndex) => {
    const isActive = tabIndex === index;
    tab.setAttribute("aria-selected", String(isActive));
    tab.tabIndex = isActive ? 0 : -1;
  });
  panel.setAttribute("aria-labelledby", tabs[index].id);
  progress.style.width = `${(index + 1) * 25}%`;
}

function schedule() {
  clearInterval(timer);
  if (!playing) return;
  timer = setInterval(() => showStep((activeStep + 1) % demoSteps.length), 4200);
}

function selectAndFocusStep(index) {
  const normalizedIndex = (index + tabs.length) % tabs.length;
  showStep(normalizedIndex);
  tabs[normalizedIndex].focus();
  schedule();
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    showStep(Number(tab.dataset.step));
    schedule();
  });
  tab.addEventListener("keydown", (event) => {
    const currentIndex = Number(tab.dataset.step);
    const keyTargets = {
      ArrowLeft: currentIndex - 1,
      ArrowRight: currentIndex + 1,
      Home: 0,
      End: tabs.length - 1,
    };
    if (!(event.key in keyTargets)) return;
    event.preventDefault();
    selectAndFocusStep(keyTargets[event.key]);
  });
});

control.addEventListener("click", () => {
  playing = !playing;
  control.textContent = playing ? "Pause walkthrough" : "Play walkthrough";
  schedule();
});

if (reduceMotion) control.textContent = "Play walkthrough";
showStep(0);
schedule();
