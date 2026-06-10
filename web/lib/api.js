export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";


export function buildApiUrl(path, params = {}) {
  const url = new URL(path, API_BASE_URL);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}


export function searchUrl(query, limit = 10, options = {}) {
  return buildApiUrl("/api/search", {
    q: query,
    limit,
    label: options.label,
    source: options.source,
    effects: Array.isArray(options.effects) ? options.effects.join("|") : options.effects,
  });
}


export function graphUrl(query, options = {}) {
  return buildApiUrl("/api/graph", {
    q: query,
    depth: options.depth || 1,
    limit: options.limit || 30,
  });
}


export function processUrl() {
  return buildApiUrl("/process");
}


export function chatThreadsUrl() {
  return buildApiUrl("/api/chat/threads");
}


export function chatThreadMessagesUrl(threadId) {
  return buildApiUrl(`/api/chat/threads/${encodeURIComponent(threadId)}/messages`);
}


export async function authRequest(path, username, password) {
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(`Auth request failed with ${response.status}`);
  }
  return response.json();
}


export async function login(username, password) {
  return authRequest("/api/auth/login", username, password);
}


export async function adminLogin(username, password) {
  return authRequest("/api/auth/admin/login", username, password);
}


export async function register(username, password) {
  return authRequest("/api/auth/register", username, password);
}


export async function fetchMe(token) {
  const response = await fetch(buildApiUrl("/api/auth/me"), {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Me request failed with ${response.status}`);
  }
  return response.json();
}


export async function logout(token) {
  const response = await fetch(buildApiUrl("/api/auth/logout"), {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Logout request failed with ${response.status}`);
  }
  return response.json();
}


export async function postChat(message, token) {
  const response = await fetch(buildApiUrl("/api/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    throw new Error(`Chat request failed with ${response.status}`);
  }
  return response.json();
}


export function parseQueuedMessages(buffer) {
  const messages = [];
  let start = -1;
  let depth = 0;
  let inString = false;
  let escaped = false;
  let consumed = 0;

  for (let index = 0; index < buffer.length; index += 1) {
    const char = buffer[index];

    if (start === -1) {
      if (char === "{") {
        start = index;
        depth = 1;
      } else {
        consumed = index + 1;
      }
      continue;
    }

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        messages.push(JSON.parse(buffer.slice(start, index + 1)));
        consumed = index + 1;
        start = -1;
      }
    }
  }

  const rest = start === -1 ? buffer.slice(consumed).trimStart() : buffer.slice(start);
  return { messages, rest };
}


export async function postChatStream(message, token, onMessage, options = {}) {
  const response = await fetch(processUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ input: message, thread_id: options.threadId || undefined }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Streaming chat request failed with ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseQueuedMessages(buffer);
    buffer = parsed.rest;
    parsed.messages.forEach(onMessage);
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    parseQueuedMessages(`${buffer}\n`).messages.forEach(onMessage);
  }
}


export async function fetchChatHistory(token, limit = 30) {
  const response = await fetch(buildApiUrl("/api/chat/history", { limit }), {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Chat history request failed with ${response.status}`);
  }
  return response.json();
}


export async function fetchChatThreads(token, limit = 30) {
  const response = await fetch(buildApiUrl("/api/chat/threads", { limit }), {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Chat threads request failed with ${response.status}`);
  }
  return response.json();
}


export async function createChatThread(token, title, focusEntity = "") {
  const response = await fetch(chatThreadsUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ title, focus_entity: focusEntity }),
  });
  if (!response.ok) {
    throw new Error(`Create chat thread request failed with ${response.status}`);
  }
  return response.json();
}


export async function fetchThreadMessages(token, threadId, limit = 100) {
  const response = await fetch(buildApiUrl(`/api/chat/threads/${encodeURIComponent(threadId)}/messages`, { limit }), {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Thread messages request failed with ${response.status}`);
  }
  return response.json();
}


export async function clearThreadMessages(token, threadId) {
  const response = await fetch(chatThreadMessagesUrl(threadId), {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Clear thread messages request failed with ${response.status}`);
  }
  return response.json();
}


export async function deleteChatThread(token, threadId) {
  const response = await fetch(chatThreadsUrl() + `/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Delete chat thread request failed with ${response.status}`);
  }
  return response.json();
}


export async function fetchLongTermMemory(token, limit = 20) {
  const response = await fetch(buildApiUrl("/api/memory", { limit }), {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Memory request failed with ${response.status}`);
  }
  return response.json();
}


export async function fetchAdminUsers(token, limit = 100) {
  const response = await fetch(buildApiUrl("/api/admin/users", { limit }), {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Admin users request failed with ${response.status}`);
  }
  return response.json();
}


export async function createAdminUser(token, username, password, role = "user") {
  const response = await fetch(buildApiUrl("/api/admin/users"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ username, password, role }),
  });
  if (!response.ok) {
    throw new Error(`Create admin user request failed with ${response.status}`);
  }
  return response.json();
}


export async function deleteAdminUser(token, userId) {
  const response = await fetch(buildApiUrl(`/api/admin/users/${encodeURIComponent(userId)}`), {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error(`Delete admin user request failed with ${response.status}`);
  }
  return response.json();
}


function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}


export async function fetchSearchResults(query, limit = 10, options = {}) {
  const response = await fetch(searchUrl(query, limit, options));
  if (!response.ok) {
    throw new Error(`Search request failed with ${response.status}`);
  }
  return response.json();
}


export async function fetchKnowledgeGraph(query, options = {}) {
  const response = await fetch(graphUrl(query, options));
  if (!response.ok) {
    throw new Error(`Graph request failed with ${response.status}`);
  }
  return response.json();
}
