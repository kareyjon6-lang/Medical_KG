import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildApiUrl,
  chatThreadMessagesUrl,
  chatThreadsUrl,
  graphUrl,
  parseQueuedMessages,
  processUrl,
  searchUrl,
} from "../lib/api.js";

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
  assert.equal(buildApiUrl("/api/auth/register"), "http://localhost:8000/api/auth/register");
});

test("memory endpoints use stable backend paths", () => {
  assert.equal(buildApiUrl("/api/chat/history", { limit: 12 }), "http://localhost:8000/api/chat/history?limit=12");
  assert.equal(buildApiUrl("/api/memory"), "http://localhost:8000/api/memory");
});

test("chat thread endpoints expose stable backend paths", () => {
  assert.equal(chatThreadsUrl(), "http://localhost:8000/api/chat/threads");
  assert.equal(
    chatThreadMessagesUrl("thread-1"),
    "http://localhost:8000/api/chat/threads/thread-1/messages"
  );
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

test("website exposes stable page routes", () => {
  const routes = ["/", "/assistant", "/search", "/graph"];
  assert.deepEqual(routes, ["/", "/assistant", "/search", "/graph"]);
});
