const loginPanel = document.querySelector("#login-panel");
const consolePanel = document.querySelector("#console");
const loginForm = document.querySelector("#login-form");
const loginMessage = document.querySelector("#login-message");
const tokenInput = document.querySelector("#operator-token");
const commandForm = document.querySelector("#command-form");
const commandInput = document.querySelector("#command-input");
const activityLog = document.querySelector("#activity-log");
const connectionDot = document.querySelector("#connection-dot");
const connectionLabel = document.querySelector("#connection-label");
const desktopStream = document.querySelector("#desktop-stream");
const streamPlaceholder = document.querySelector("#stream-placeholder");

let socket = null;

function setConnected(connected, label = connected ? "Connected" : "Disconnected") {
  connectionDot.classList.toggle("online", connected);
  connectionLabel.textContent = label;
}

function addLog(message) {
  const row = document.createElement("div");
  row.className = "log-entry";
  const timestamp = document.createElement("time");
  timestamp.dateTime = new Date().toISOString();
  timestamp.textContent = new Date().toLocaleTimeString();
  const text = document.createElement("span");
  text.textContent = typeof message === "string" ? message : JSON.stringify(message);
  row.append(timestamp, text);
  activityLog.append(row);
  activityLog.scrollTop = activityLog.scrollHeight;
}

async function loadHealth() {
  try {
    const response = await fetch("/health", { cache: "no-store" });
    const health = await response.json();
    document.querySelector("#agent-version").textContent = health.version;
    document.querySelector("#agent-uptime").textContent = `${Math.round(health.uptime_seconds)}s`;
    document.querySelector("#agent-state").textContent = health.agent_state;
  } catch {
    document.querySelector("#agent-state").textContent = "Unavailable";
  }
}

function startStream() {
  streamPlaceholder.hidden = true;
  desktopStream.hidden = false;
  desktopStream.src = `/stream?session=${Date.now()}`;
  desktopStream.addEventListener("error", () => {
    desktopStream.hidden = true;
    streamPlaceholder.hidden = false;
    streamPlaceholder.textContent = "Desktop capture is unavailable in this runtime.";
  }, { once: true });
}

function connectSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.host}/ws`);
  socket.addEventListener("open", () => {
    setConnected(true);
    addLog("Authenticated operator session connected.");
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "status" && typeof message.payload === "object") {
      document.querySelector("#agent-state").textContent = message.payload.agent_state;
      addLog(message.payload.message);
      return;
    }
    addLog(message.payload);
  });
  socket.addEventListener("close", (event) => {
    setConnected(false, event.code === 4401 ? "Session expired" : "Disconnected");
    socket = null;
  });
  socket.addEventListener("error", () => addLog("The realtime connection failed."));
}

function showConsole() {
  loginPanel.hidden = true;
  consolePanel.hidden = false;
  setConnected(false, "Connecting");
  loadHealth();
  connectSocket();
  startStream();
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginMessage.textContent = "";
  const token = tokenInput.value;
  try {
    const response = await fetch("/api/session", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    tokenInput.value = "";
    if (!response.ok) throw new Error("Token rejected. Check the configured value.");
    showConsole();
  } catch (error) {
    tokenInput.value = "";
    loginMessage.textContent = error.message;
  }
});

commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const command = commandInput.value.trim();
  if (!command || !socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "command", payload: command }));
  commandInput.value = "";
});

document.querySelector("#cancel-button").addEventListener("click", () => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "cancel", payload: "" }));
  }
});

document.querySelector("#clear-log").addEventListener("click", () => activityLog.replaceChildren());

document.querySelector("#logout-button").addEventListener("click", async () => {
  await fetch("/api/session", { method: "DELETE" });
  if (socket) socket.close();
  desktopStream.removeAttribute("src");
  consolePanel.hidden = true;
  loginPanel.hidden = false;
  setConnected(false, "Locked");
});

fetch("/api/session", { cache: "no-store" }).then((response) => {
  if (response.ok) showConsole();
});
