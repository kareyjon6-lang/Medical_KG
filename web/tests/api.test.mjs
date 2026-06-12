import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildApiUrl,
  chatJobsUrl,
  chatThreadMessagesUrl,
  chatThreadsUrl,
  graphUrl,
  parseQueuedMessages,
  postChatStream,
  processUrl,
  searchUrl,
} from "../lib/api.js";
import { appendThoughtChunk } from "../lib/thoughts.js";

test("buildApiUrl encodes Chinese query parameters", () => {
  assert.equal(
    buildApiUrl("/api/search", { q: "麻黄汤", limit: 5 }),
    "http://localhost:8000/api/search?q=%E9%BA%BB%E9%BB%84%E6%B1%A4&limit=5"
  );
});

test("searchUrl and graphUrl expose stable backend paths", () => {
  assert.equal(searchUrl("桂枝", 8), "http://localhost:8000/api/search?q=%E6%A1%82%E6%9E%9D&limit=8");
  assert.equal(
    searchUrl("", 50, { label: "Formula" }),
    "http://localhost:8000/api/search?limit=50&label=Formula"
  );
  assert.equal(
    graphUrl("麻黄汤", { depth: 1, limit: 20 }),
    "http://localhost:8000/api/graph?q=%E9%BA%BB%E9%BB%84%E6%B1%A4&depth=1&limit=20"
  );
});

test("auth endpoints use stable backend paths", () => {
  assert.equal(buildApiUrl("/api/auth/login"), "http://localhost:8000/api/auth/login");
  assert.equal(buildApiUrl("/api/auth/admin/login"), "http://localhost:8000/api/auth/admin/login");
  assert.equal(buildApiUrl("/api/auth/register"), "http://localhost:8000/api/auth/register");
});

test("memory endpoints use stable backend paths", () => {
  assert.equal(buildApiUrl("/api/chat/history", { limit: 12 }), "http://localhost:8000/api/chat/history?limit=12");
  assert.equal(buildApiUrl("/api/memory"), "http://localhost:8000/api/memory");
});

test("chat thread endpoints expose stable backend paths", () => {
  assert.equal(chatThreadsUrl(), "http://localhost:8000/api/chat/threads");
  assert.equal(chatJobsUrl(), "http://localhost:8000/api/chat/jobs");
  assert.equal(chatJobsUrl("job-1"), "http://localhost:8000/api/chat/jobs/job-1");
  assert.equal(
    chatThreadMessagesUrl("thread-1"),
    "http://localhost:8000/api/chat/threads/thread-1/messages"
  );
});

test("admin endpoints expose stable backend paths", () => {
  assert.equal(buildApiUrl("/api/admin/users", { limit: 100 }), "http://localhost:8000/api/admin/users?limit=100");
  assert.equal(buildApiUrl("/api/admin/users/user-1"), "http://localhost:8000/api/admin/users/user-1");
});

test("streaming chat helpers target process endpoint and parse queued messages", () => {
  assert.equal(processUrl(), "http://localhost:8000/process");
  assert.deepEqual(
    parseQueuedMessages('{"type":"think","msg":"检索实体"}\n{"type":"stream","msg":"麻黄汤"}\n'),
    {
      messages: [
        { type: "think", msg: "检索实体" },
        { type: "stream", msg: "麻黄汤" },
      ],
      rest: "",
    }
  );
  assert.deepEqual(
    parseQueuedMessages('{"type":"think","msg":"开始"}{"type":"stream","msg":"回答"}{"type":"do'),
    {
      messages: [
        { type: "think", msg: "开始" },
        { type: "stream", msg: "回答" },
      ],
      rest: '{"type":"do',
    }
  );
});

test("postChatStream forwards abort signal to the streaming request", async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  const messages = [];
  let requestOptions;
  globalThis.fetch = async (_url, options) => {
    requestOptions = options;
    return new Response(new ReadableStream({
      start(streamController) {
        streamController.enqueue(new TextEncoder().encode('{"type":"done"}\n'));
        streamController.close();
      },
    }), { status: 200 });
  };

  try {
    await postChatStream("你好", "token", (message) => messages.push(message), {
      signal: controller.signal,
      threadId: "thread-1",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestOptions.signal, controller.signal);
  assert.equal(JSON.parse(requestOptions.body).thread_id, "thread-1");
  assert.deepEqual(messages, [{ type: "done" }]);
});

test("postChatStream can target chat jobs endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody = "";
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    requestBody = options.body;
    return new Response(new ReadableStream({
      start(streamController) {
        streamController.enqueue(new TextEncoder().encode('{"type":"done","job_id":"job-1","thread_id":"thread-1"}\n'));
        streamController.close();
      },
    }), { status: 200 });
  };

  try {
    await postChatStream("麻黄汤是什么？", "token", () => {}, {
      threadId: "thread-1",
      useJobEndpoint: true,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "http://localhost:8000/api/chat/jobs");
  assert.deepEqual(JSON.parse(requestBody), { input: "麻黄汤是什么？", thread_id: "thread-1" });
});

test("website exposes stable page routes", () => {
  const routes = ["/", "/assistant", "/search", "/graph", "/admin"];
  assert.deepEqual(routes, ["/", "/assistant", "/search", "/graph", "/admin"]);
});

test("thought chunks keep Chinese Cypher values on the same line", () => {
  const chunks = [
    '开始生成Cypher查询语句{"cypher":"MATCH (s:Symptom) WHERE s.name IN [',
    '"喉',
    '痛"',
    ',',
    '"咽喉',
    '痛"',
    '] RETURN s"}',
  ];
  const thoughts = chunks.reduce((items, chunk) => appendThoughtChunk(items, `${chunk}\n`), []);

  assert.equal(thoughts.length, 1);
  assert.match(thoughts[0], /喉痛/);
  assert.match(thoughts[0], /咽喉痛/);
  assert.notEqual(thoughts[0], "痛");
});
