const token = document.querySelector('meta[name="dcp-token"]').content;
const form = document.getElementById("canary-form");
const promptInput = document.getElementById("prompt");
const runButton = document.getElementById("run");
const formError = document.getElementById("form-error");
let pollHandle = null;

async function request(path, options = {}) {
  const headers = { "X-DCP-Token": token, ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function render(snapshot) {
  promptInput.value = snapshot.canonical_prompt;
  document.getElementById("runtime-root").textContent = `evidence: ${snapshot.runtime_roots.data}/lab/records/`;
  document.getElementById("card-count").textContent = `карточек: ${snapshot.card_count}`;
  const task = snapshot.task;
  const card = document.getElementById("task-card");
  document.getElementById("empty-state").hidden = Boolean(task);
  card.hidden = !task;
  runButton.disabled = snapshot.active || Boolean(task);
  if (!task) return;

  document.getElementById("task-id").textContent = task.task_id;
  const state = document.getElementById("state");
  state.textContent = `${task.state_label} · ${task.state}`;
  state.dataset.state = task.state;
  document.getElementById("summary").textContent = task.summary;
  document.getElementById("attempt-count").textContent = task.attempt_count;
  document.getElementById("worker-count").textContent = task.worker_count;
  document.getElementById("retry-count").textContent = task.retry_count;
  document.getElementById("reason").textContent = task.terminal_reason || task.reason;

  const transitions = document.getElementById("transition-list");
  transitions.replaceChildren();
  for (const event of task.transitions || []) {
    const item = document.createElement("li");
    item.textContent = `${event.state} · ${event.reason}`;
    transitions.appendChild(item);
  }
  const evidence = document.getElementById("evidence-list");
  evidence.replaceChildren();
  const refs = task.evidence_refs || [];
  for (const ref of refs.length ? refs : ["появятся только после terminal cleanup"]) {
    const item = document.createElement("li");
    item.textContent = ref;
    evidence.appendChild(item);
  }

  if (["succeeded", "failed", "cleanup_failed", "safety_violation"].includes(task.state)) {
    if (pollHandle) window.clearInterval(pollHandle);
    pollHandle = null;
  }
}

async function refresh() {
  try {
    render(await request("/api/state"));
  } catch (error) {
    formError.textContent = `Не удалось прочитать локальное состояние: ${error.message}`;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  runButton.disabled = true;
  try {
    const snapshot = await request("/api/canary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptInput.value }),
    });
    render(snapshot);
    pollHandle = window.setInterval(refresh, 400);
  } catch (error) {
    runButton.disabled = false;
    formError.textContent = `Canary не запущен: ${error.message}`;
  }
});

refresh();
