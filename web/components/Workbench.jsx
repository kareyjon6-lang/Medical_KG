"use client";

import * as THREE from "three";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  Brain,
  ChevronRight,
  Clock,
  Database,
  Filter,
  History,
  Layers3,
  LogOut,
  MessageCircle,
  Network,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  adminLogin,
  clearThreadMessages,
  createAdminUser,
  createChatThread,
  deleteAdminUser,
  deleteChatThread,
  fetchAdminUsers,
  fetchChatThreads,
  fetchKnowledgeGraph,
  fetchMe,
  fetchSearchResults,
  fetchThreadMessages,
  login,
  logout,
  postChatStream,
  register,
} from "../lib/api";
import { appendThoughtChunk } from "../lib/thoughts";

const defaultMessages = [
  {
    role: "assistant",
    content: "你好，我可以结合中医知识图谱回答方剂、药材、功效、主治和禁忌相关问题。",
  },
];

const demoGraph = {
  nodes: [
    { id: "Formula:麻黄汤", name: "麻黄汤", label: "Formula", properties: { source: "伤寒论", effect: "发汗解表，宣肺平喘" } },
    { id: "Herb:麻黄", name: "麻黄", label: "Herb", properties: { effect: "发汗解表" } },
    { id: "Herb:桂枝", name: "桂枝", label: "Herb", properties: { effect: "温通经脉" } },
    { id: "Herb:杏仁", name: "杏仁", label: "Herb", properties: { effect: "降气止咳" } },
    { id: "Herb:甘草", name: "甘草", label: "Herb", properties: { effect: "调和诸药" } },
    { id: "Source:伤寒论", name: "伤寒论", label: "Source", properties: {} },
    { id: "Effect:发汗解表", name: "发汗解表", label: "Effect", properties: {} },
    { id: "Symptom:恶寒发热", name: "恶寒发热", label: "Symptom", properties: {} },
  ],
  edges: [
    { id: "1", source: "Formula:麻黄汤", target: "Herb:麻黄", label: "HAS_INGREDIENT" },
    { id: "2", source: "Formula:麻黄汤", target: "Herb:桂枝", label: "HAS_INGREDIENT" },
    { id: "3", source: "Formula:麻黄汤", target: "Herb:杏仁", label: "HAS_INGREDIENT" },
    { id: "4", source: "Formula:麻黄汤", target: "Herb:甘草", label: "HAS_INGREDIENT" },
    { id: "5", source: "Formula:麻黄汤", target: "Source:伤寒论", label: "FROM_SOURCE" },
    { id: "6", source: "Formula:麻黄汤", target: "Effect:发汗解表", label: "HAS_EFFECT" },
    { id: "7", source: "Formula:麻黄汤", target: "Symptom:恶寒发热", label: "ALLEVIATES_SYMPTOM" },
  ],
};

const demoResults = [
  {
    id: "Formula:麻黄汤",
    name: "麻黄汤",
    label: "Formula",
    properties: {
      source: "伤寒论",
      ingredients: "麻黄、桂枝、杏仁、甘草",
      effect: "发汗解表，宣肺平喘",
      indication: "风寒表实证，恶寒发热，无汗而喘",
      taboo: "表虚自汗、阴虚盗汗者慎用",
      related: "组成：麻黄（药材）；组成：桂枝（药材）；出处：伤寒论（出处）",
    },
  },
];

const hotQueries = ["麻黄汤", "桂枝汤", "银翘散", "四君子汤", "发汗解表", "风寒表实证"];
const relationFilters = ["HAS_INGREDIENT", "HAS_EFFECT", "FROM_SOURCE", "ALLEVIATES_SYMPTOM", "TREATS_DISEASE"];

const authRuntime = {
  token: "",
  user: null,
};

const anonymousRuntimeKey = "anonymous";
const chatRuntimeStore = new Map();

function createChatRuntime() {
  return {
    activeThreadId: "",
    activeView: "assistant",
    loading: false,
    messages: defaultMessages,
    progress: 0,
    subscribers: new Set(),
    thoughts: [],
    unread: false,
  };
}

function getRuntimeKey(authState) {
  const user = authState?.user;
  if (!authState?.token || !user) return anonymousRuntimeKey;
  return [user.role || "user", user.id || user.username || authState.token].join(":");
}

function getChatRuntime(key = anonymousRuntimeKey) {
  if (!chatRuntimeStore.has(key)) {
    chatRuntimeStore.set(key, createChatRuntime());
  }
  return chatRuntimeStore.get(key);
}

function snapshotChatRuntime(runtime) {
  return {
    activeThreadId: runtime.activeThreadId,
    loading: runtime.loading,
    messages: runtime.messages,
    progress: runtime.progress,
    thoughts: runtime.thoughts,
    unread: runtime.unread,
  };
}

function patchChatRuntime(runtime, patch) {
  Object.assign(runtime, patch);
  const snapshot = snapshotChatRuntime(runtime);
  runtime.subscribers.forEach((subscriber) => subscriber(snapshot));
}

function resetChatRuntime(runtime) {
  patchChatRuntime(runtime, {
    activeThreadId: "",
    loading: false,
    messages: defaultMessages,
    progress: 0,
    thoughts: [],
    unread: false,
  });
}

function subscribeChatRuntime(runtime, subscriber) {
  runtime.subscribers.add(subscriber);
  subscriber(snapshotChatRuntime(runtime));
  return () => runtime.subscribers.delete(subscriber);
}

export default function Workbench({ initialView = "assistant" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const graphRef = useRef(null);
  const shellRef = useRef(null);
  const runtimeRef = useRef(getChatRuntime(getRuntimeKey({ token: authRuntime.token, user: authRuntime.user })));
  const runtimeSnapshot = snapshotChatRuntime(runtimeRef.current);
  const [auth, setAuth] = useState(() => ({ token: authRuntime.token, user: authRuntime.user }));
  const runtimeKey = useMemo(() => getRuntimeKey(auth), [auth.token, auth.user?.id, auth.user?.role, auth.user?.username]);
  const [savedSession, setSavedSession] = useState(null);
  const [restoring, setRestoring] = useState(() => !authRuntime.token);
  const [silentRestoring, setSilentRestoring] = useState(() => (
    typeof window !== "undefined"
      && Boolean(window.localStorage.getItem("tcm_kg_token"))
      && window.sessionStorage.getItem("tcm_kg_session_confirmed") === "1"
      && !authRuntime.token
  ));
  const [activeView, setActiveView] = useState(initialView);
  const [status, setStatus] = useState(() => (authRuntime.token ? "登录成功" : "等待登录"));
  const [messages, setMessages] = useState(runtimeSnapshot.messages);
  const [prompt, setPrompt] = useState("");
  const [thoughts, setThoughts] = useState(runtimeSnapshot.thoughts);
  const [thinkingProgress, setThinkingProgress] = useState(runtimeSnapshot.progress);
  const [chatLoading, setChatLoading] = useState(runtimeSnapshot.loading);
  const [assistantHasUnread, setAssistantHasUnread] = useState(runtimeSnapshot.unread);
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(runtimeSnapshot.activeThreadId);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(demoResults);
  const [selectedResult, setSelectedResult] = useState(demoResults[0]);
  const [recentQueries, setRecentQueries] = useState(["麻黄汤", "桂枝汤"]);
  const [entityFilter, setEntityFilter] = useState("全部");
  const [sourceFilter, setSourceFilter] = useState("");
  const [effectFilters, setEffectFilters] = useState([]);
  const [hotOffset, setHotOffset] = useState(0);
  const [graphFocus, setGraphFocus] = useState("");
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [graphDepth, setGraphDepth] = useState(1);
  const [activeRelations, setActiveRelations] = useState(relationFilters);
  const [selectedNode, setSelectedNode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hasWebGL, setHasWebGL] = useState(true);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminForm, setAdminForm] = useState({ username: "", password: "", role: "user" });
  const [adminStatus, setAdminStatus] = useState("等待管理员登录");

  useEffect(() => {
    const token = window.localStorage.getItem("tcm_kg_token");
    const sessionConfirmed = window.sessionStorage.getItem("tcm_kg_session_confirmed") === "1";
    const savedQuery = window.localStorage.getItem("tcm_kg_query");
    const urlQuery = searchParams.get("q");
    const nextQuery = urlQuery || savedQuery || "";

    setQuery(nextQuery);
    setGraphFocus(nextQuery);

    if (!token) {
      setRestoring(false);
      setSilentRestoring(false);
      setSavedSession(null);
      return;
    }

    if (!sessionConfirmed) {
      window.localStorage.removeItem("tcm_kg_token");
      window.localStorage.removeItem("tcm_kg_query");
      window.localStorage.removeItem("tcm_kg_graph_focus");
      authRuntime.token = "";
      authRuntime.user = null;
      setAuth({ token: "", user: null });
      setSavedSession(null);
      setRestoring(false);
      setSilentRestoring(false);
      setStatus("等待登录");
      return;
    }

    if (sessionConfirmed && authRuntime.token === token && authRuntime.user) {
      setAuth({ token, user: authRuntime.user });
      setSavedSession(null);
      setRestoring(false);
      setSilentRestoring(false);
      setStatus("登录成功");
      return;
    }

    setRestoring(true);
    setSilentRestoring(sessionConfirmed && !authRuntime.token);
    setStatus(sessionConfirmed ? "正在恢复已登录会话" : "已检测到历史会话，请选择继续或重新登录");
    fetchMe(token)
      .then((data) => {
        if (sessionConfirmed) {
          authRuntime.token = token;
          authRuntime.user = data.user;
          setAuth({ token, user: data.user });
          setSavedSession(null);
          setStatus("登录成功");
          if (initialView === "admin" && data.user?.role !== "admin") {
            setActiveView("assistant");
            router.replace("/assistant");
          }
          return;
        }
        setSavedSession({ token, user: data.user });
        setStatus("已检测到历史会话，请选择继续或重新登录");
      })
      .catch(() => {
        window.localStorage.removeItem("tcm_kg_token");
        window.sessionStorage.removeItem("tcm_kg_session_confirmed");
        authRuntime.token = "";
        authRuntime.user = null;
        setSavedSession(null);
        setAuth({ token: "", user: null });
        setStatus("登录已过期，请重新登录");
      })
      .finally(() => {
        setRestoring(false);
        setSilentRestoring(false);
      });
  }, [initialView, router, searchParams]);

  useEffect(() => {
    setActiveView(initialView);
  }, [initialView]);

  useEffect(() => {
    const runtime = getChatRuntime(runtimeKey);
    runtimeRef.current = runtime;
    return subscribeChatRuntime(runtime, (snapshot) => {
      setMessages(snapshot.messages);
      setThoughts(snapshot.thoughts);
      setThinkingProgress(snapshot.progress);
      setChatLoading(snapshot.loading);
      setAssistantHasUnread(snapshot.unread);
      setActiveThreadId(snapshot.activeThreadId);
    });
  }, [runtimeKey]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    runtime.activeView = activeView;
    if (activeView === "assistant" && runtime.unread) {
      patchChatRuntime(runtime, { unread: false });
    }
  }, [activeView]);

  useEffect(() => {
    if (!auth.token) return;
    refreshUserContext(auth.token);
  }, [auth.token]);

  useEffect(() => {
    if (!auth.token || auth.user?.role !== "admin") return;
    refreshAdminUsers();
  }, [auth.token, auth.user?.role]);

  useEffect(() => {
    if (!auth.token || activeView !== "admin" || auth.user?.role === "admin") return;
    setActiveView("assistant");
    router.replace("/assistant");
  }, [activeView, auth.token, auth.user?.role, router]);

  useEffect(() => {
    const canvas = document.createElement("canvas");
    setHasWebGL(Boolean(window.WebGLRenderingContext && canvas.getContext("webgl")));
  }, []);

  useEffect(() => {
    if (!auth.token || activeView !== "graph") return;
    loadGraphForFocus(graphFocus);
  }, [auth.token, activeView, graphFocus, graphDepth]);

  useEffect(() => {
    if (activeView !== "search") return;
    const routeQuery = searchParams.get("q");
    const savedQuery = window.localStorage.getItem("tcm_kg_query") || "";
    const nextText = routeQuery !== null ? routeQuery : (query || savedQuery);
    if (nextText !== query) {
      setQuery(nextText);
    }
    loadSearchResults(nextText, {
      syncGraph: true,
      replaceRoute: false,
      entityFilter,
      sourceFilter,
      effectFilters,
    });
  }, [activeView, searchParams, entityFilter, sourceFilter, effectFilters]);

  const filteredResults = useMemo(() => {
    return results;
  }, [results]);

  const graphData = useMemo(() => {
    const allowed = new Set(activeRelations);
    const edges = graph.edges.filter((edge) => allowed.has(edge.label));
    const nodeIds = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
    const nodes = graph.nodes.filter((node) => nodeIds.has(node.id) || node.name === graphFocus);
    return {
      nodes: nodes.map((node) => ({
        ...node,
        val: node.name === graphFocus ? 8 : 4,
        color: entityColor(node.label, node.name === graphFocus),
      })),
      links: edges.map((edge) => ({
        ...edge,
        source: edge.source,
        target: edge.target,
        color: relationColor(edge.label),
      })),
    };
  }, [activeRelations, graph, graphFocus]);

  async function refreshUserContext(token) {
    try {
      const threadData = await fetchChatThreads(token, 30);
      setThreads(threadData.items || []);
    } catch (error) {
      setStatus("历史记录读取异常");
    }
  }

  async function refreshAdminUsers() {
    if (!auth.token || auth.user?.role !== "admin") return;
    try {
      const data = await fetchAdminUsers(auth.token, 200);
      setAdminUsers(data.items || []);
      setAdminStatus("用户列表已同步");
    } catch (error) {
      setAdminStatus("用户列表读取失败");
    }
  }

  async function handleAuthed(data) {
    window.localStorage.setItem("tcm_kg_token", data.token);
    window.sessionStorage.setItem("tcm_kg_session_confirmed", "1");
    authRuntime.token = data.token;
    authRuntime.user = data.user;
    setAuth({ token: data.token, user: data.user });
    setSavedSession(null);
    setStatus("登录成功");
    await refreshUserContext(data.token);
    if (data.user?.role === "admin") {
      setActiveView("admin");
      router.push("/admin");
    } else if (activeView === "admin") {
      setActiveView("assistant");
      router.push("/assistant");
    }
  }

  async function handleContinueSession(session) {
    if (!session?.token) return;
    await handleAuthed(session);
  }

  async function handleCreateAdminUser(event) {
    event.preventDefault();
    if (!adminForm.username.trim() || !adminForm.password.trim()) return;
    setAdminStatus("正在创建用户");
    try {
      await createAdminUser(auth.token, adminForm.username.trim(), adminForm.password, adminForm.role);
      setAdminForm({ username: "", password: "", role: "user" });
      await refreshAdminUsers();
      setAdminStatus("用户已创建");
    } catch (error) {
      setAdminStatus("创建失败：用户名可能已存在或密码过短");
    }
  }

  async function handleDeleteAdminUser(userId) {
    setAdminStatus("正在删除用户");
    try {
      await deleteAdminUser(auth.token, userId);
      await refreshAdminUsers();
      setAdminStatus("用户已删除");
    } catch (error) {
      setAdminStatus("删除失败：不能删除当前管理员或最后一个管理员");
    }
  }

  async function handleLogout() {
    const token = auth.token;
    window.localStorage.removeItem("tcm_kg_token");
    window.sessionStorage.removeItem("tcm_kg_session_confirmed");
    authRuntime.token = "";
    authRuntime.user = null;
    setAuth({ token: "", user: null });
    setSavedSession(null);
    setThreads([]);
    setAdminUsers([]);
    setActiveThreadId("");
    resetChatRuntime(runtimeRef.current);
    if (token) {
      try {
        await logout(token);
      } catch (error) {
        setStatus("本地已退出，服务端会话稍后清理");
      }
    }
  }

  async function handleSelectThread(threadId) {
    if (!threadId || chatLoading) return;
    setActiveThreadId(threadId);
    setStatus("正在读取历史对话");
    try {
      const data = await fetchThreadMessages(auth.token, threadId, 100);
      patchChatRuntime(runtimeRef.current, {
        activeThreadId: threadId,
        messages: data.items?.length ? data.items.map(({ role, content }) => ({ role, content })) : defaultMessages,
        progress: 0,
        thoughts: [],
        unread: false,
      });
      const thread = threads.find((item) => item.id === threadId);
      if (thread?.focus_entity) {
        setGraphFocus(thread.focus_entity);
      }
      setStatus("历史对话已载入");
    } catch (error) {
      setStatus("历史对话读取失败");
    }
  }

  async function handleNewThread() {
    try {
      const data = await createChatThread(auth.token, "新的中医问答", graphFocus);
      const thread = data.thread;
      setThreads((items) => [thread, ...items]);
      setActiveThreadId(thread.id);
      patchChatRuntime(runtimeRef.current, { activeThreadId: thread.id, messages: defaultMessages, progress: 0, thoughts: [], unread: false });
      setStatus("已创建新对话");
    } catch (error) {
      setStatus("新建对话失败");
    }
  }

  async function handleClearCurrentThread() {
    if (chatLoading) return;
    patchChatRuntime(runtimeRef.current, { messages: defaultMessages, progress: 0, thoughts: [], unread: false });
    if (!activeThreadId) {
      setStatus("当前对话已清空");
      return;
    }
    try {
      await clearThreadMessages(auth.token, activeThreadId);
      setThreads((items) => items.map((thread) => (
        thread.id === activeThreadId ? { ...thread, message_count: 0 } : thread
      )));
      setStatus("当前历史对话已清空");
    } catch (error) {
      setStatus("清空当前对话失败");
    }
  }

  async function handleDeleteThread(threadId) {
    if (!threadId || chatLoading) return;
    try {
      await deleteChatThread(auth.token, threadId);
      const nextThreads = threads.filter((thread) => thread.id !== threadId);
      setThreads(nextThreads);
      if (threadId === activeThreadId) {
        setActiveThreadId("");
        patchChatRuntime(runtimeRef.current, { activeThreadId: "", messages: defaultMessages, progress: 0, thoughts: [], unread: false });
      }
      setStatus("历史对话已删除");
    } catch (error) {
      setStatus("删除历史对话失败");
    }
  }

  async function ensureThreadForPrompt(text) {
    if (activeThreadId) return activeThreadId;
    const title = text.slice(0, 28);
    const data = await createChatThread(auth.token, title, graphFocus);
    const thread = data.thread;
    setThreads((items) => [thread, ...items]);
    setActiveThreadId(thread.id);
    patchChatRuntime(runtimeRef.current, { activeThreadId: thread.id });
    return thread.id;
  }

  async function handleChat(event) {
    event.preventDefault();
    const text = prompt.trim();
    const runtime = runtimeRef.current;
    const requestToken = auth.token;
    if (!text || runtime.loading) return;

    setPrompt("");
    patchChatRuntime(runtime, {
      loading: true,
      messages: [...runtime.messages, { role: "user", content: text }, { role: "assistant", content: "" }],
      progress: 8,
      thoughts: [],
      unread: false,
    });
    setStatus("模型正在流式回答");

    try {
      const threadId = await ensureThreadForPrompt(text);
      patchChatRuntime(runtime, { activeThreadId: threadId });
      await postChatStream(
        text,
        auth.token,
        (eventMessage) => {
          if (eventMessage.type === "think") {
            const nextThoughts = appendThoughtChunk(runtime.thoughts, eventMessage.msg || "");
            if (nextThoughts !== runtime.thoughts) {
              patchChatRuntime(runtime, {
                progress: Math.min(92, runtime.progress + 8),
                thoughts: nextThoughts,
              });
            }
          }
          if (eventMessage.type === "stream") {
            patchChatRuntime(runtime, {
              messages: appendToLastAssistant(runtime.messages, eventMessage.msg || ""),
            });
          }
          if (eventMessage.type === "done") {
            patchChatRuntime(runtime, { progress: 100 });
          }
        },
        { threadId },
      );
      if (authRuntime.token === requestToken) {
        await refreshUserContext(requestToken);
        setStatus("回答生成完成");
      }
      if (runtime.activeView !== "assistant") {
        patchChatRuntime(runtime, { unread: true });
      }
    } catch (error) {
      patchChatRuntime(runtime, {
        messages: appendToLastAssistant(runtime.messages, "服务暂时不可用，请稍后再试。"),
        unread: runtime.activeView !== "assistant",
      });
      if (authRuntime.token === requestToken) {
        setStatus("问答连接异常");
      }
    } finally {
      patchChatRuntime(runtime, { loading: false, progress: runtime.progress ? 100 : 0 });
    }
  }

  async function handleSearch(event) {
    event.preventDefault();
    const text = query.trim();
    await loadSearchResults(text, { syncGraph: true, replaceRoute: true, entityFilter, sourceFilter, effectFilters });
  }

  async function loadSearchResults(text, options = {}) {
    const cleanText = (text || "").trim();
    const {
      syncGraph = false,
      replaceRoute = true,
      entityFilter: nextEntityFilter = entityFilter,
      sourceFilter: nextSourceFilter = sourceFilter,
      effectFilters: nextEffectFilters = effectFilters,
    } = options;
    const backendLabel = entityFilterToBackendLabel(nextEntityFilter);
    setLoading(true);
    setStatus(cleanText ? "正在检索方药知识" : backendLabel ? `正在载入${nextEntityFilter}` : "正在载入全部实体");
    try {
      if (cleanText) {
        window.localStorage.setItem("tcm_kg_query", cleanText);
        setRecentQueries((items) => [cleanText, ...items.filter((item) => item !== cleanText)].slice(0, 6));
      } else {
        window.localStorage.removeItem("tcm_kg_query");
      }
      if (syncGraph) {
        if (cleanText) {
          window.localStorage.setItem("tcm_kg_graph_focus", cleanText);
        } else {
          window.localStorage.removeItem("tcm_kg_graph_focus");
          setGraph({ nodes: [], edges: [] });
          setSelectedNode(null);
        }
        setGraphFocus(cleanText);
      }
      if (replaceRoute) {
        router.replace(cleanText ? `/search?q=${encodeURIComponent(cleanText)}` : "/search");
      }
      const searchData = await fetchSearchResults(cleanText, 1000, {
        label: backendLabel,
        source: nextSourceFilter,
        effects: nextEffectFilters,
      });
      const nextResults = searchData.items?.length ? searchData.items : [];
      setResults(nextResults);
      setSelectedResult(nextResults[0] || null);
      setStatus(nextResults.length ? (cleanText ? `已找到 ${nextResults.length} 条结果` : `已载入 ${nextResults.length} 个实体`) : "暂无匹配结果");
    } catch (error) {
      setResults([]);
      setSelectedResult(null);
      setStatus("检索异常");
    } finally {
      setLoading(false);
    }
  }

  function handleSelectResult(item) {
    setSelectedResult(item);
    setQuery(item.name);
    setGraphFocus(item.name);
    window.localStorage.setItem("tcm_kg_query", item.name);
    window.localStorage.setItem("tcm_kg_graph_focus", item.name);
    setStatus(`图谱页已同步：${item.name}`);
  }

  function handleEntityFilterChange(filter) {
    setEntityFilter(filter);
    loadSearchResults(query.trim(), { syncGraph: true, replaceRoute: false, entityFilter: filter, sourceFilter, effectFilters });
  }

  function handleSourceFilterChange(source) {
    const nextSource = sourceFilter === source ? "" : source;
    setSourceFilter(nextSource);
    loadSearchResults(query.trim(), { syncGraph: true, replaceRoute: false, entityFilter, sourceFilter: nextSource, effectFilters });
  }

  function handleEffectFilterToggle(effect) {
    const nextEffects = effectFilters.includes(effect)
      ? effectFilters.filter((item) => item !== effect)
      : [...effectFilters, effect];
    setEffectFilters(nextEffects);
    loadSearchResults(query.trim(), { syncGraph: true, replaceRoute: false, entityFilter, sourceFilter, effectFilters: nextEffects });
  }

  function handleClearSearchFilters() {
    setQuery("");
    setEntityFilter("全部");
    setSourceFilter("");
    setEffectFilters([]);
    loadSearchResults("", {
      syncGraph: true,
      replaceRoute: true,
      entityFilter: "全部",
      sourceFilter: "",
      effectFilters: [],
    });
  }

  function handleQuickSearch(text) {
    setQuery(text);
    loadSearchResults(text, { syncGraph: true, replaceRoute: true, entityFilter, sourceFilter, effectFilters });
  }

  function handleRotateHotQueries() {
    setHotOffset((value) => (value + 3) % hotQueries.length);
  }

  async function loadGraphForFocus(text) {
    const cleanText = text.trim();
    if (!cleanText) {
      setGraph({ nodes: [], edges: [] });
      setSelectedNode(null);
      setStatus("图谱等待搜索");
      return;
    }
    setLoading(true);
    setStatus("正在加载图数据库");
    try {
      const graphData = await fetchKnowledgeGraph(cleanText, { depth: graphDepth, limit: 80 });
      const nextGraph = graphData.nodes?.length ? graphData : { nodes: [], edges: [] };
      setGraph(nextGraph);
      setSelectedNode(nextGraph.nodes.find((node) => node.name === cleanText) || nextGraph.nodes[0] || null);
      setStatus("图谱已加载");
    } catch (error) {
      setGraph({ nodes: [], edges: [] });
      setSelectedNode(null);
      setStatus("图谱加载异常");
    } finally {
      setLoading(false);
    }
  }

  function switchRelation(label) {
    setActiveRelations((items) => {
      if (items.includes(label)) {
        return items.length === 1 ? items : items.filter((item) => item !== label);
      }
      return [...items, label];
    });
  }

  function handleNavigate(view) {
    if (view === "admin" && auth.user?.role !== "admin") return;
    setActiveView(view);
    const runtime = runtimeRef.current;
    runtime.activeView = view;
    if (view === "assistant") {
      patchChatRuntime(runtime, { unread: false });
    }
  }

  function handleWorkbenchPointerMove(event) {
    if (activeView === "graph") return;
    const element = shellRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
    const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    element.style.setProperty("--mx", x.toFixed(3));
    element.style.setProperty("--my", y.toFixed(3));
    element.style.setProperty("--mouse-x", `${event.clientX - rect.left}px`);
    element.style.setProperty("--mouse-y", `${event.clientY - rect.top}px`);
  }

  function resetWorkbenchPointer() {
    const element = shellRef.current;
    if (!element) return;
    element.style.setProperty("--mx", "0");
    element.style.setProperty("--my", "0");
    element.style.setProperty("--mouse-x", "50%");
    element.style.setProperty("--mouse-y", "50%");
  }

  if (!auth.token && silentRestoring) {
    return (
      <main className="auth-restore-shell">
        <div className="login-image-bg" />
        <div className="paper-wash" />
        <div className="auth-restore-card">正在恢复已登录会话...</div>
      </main>
    );
  }

  if (!auth.token) {
    return (
      <LoginScreenV2
        onAuthed={handleAuthed}
        onContinue={handleContinueSession}
        savedSession={savedSession}
        status={status}
      />
    );
  }

  return (
    <main
      ref={shellRef}
      className={`app-shell view-${activeView}`}
      onPointerMove={handleWorkbenchPointerMove}
      onPointerLeave={resetWorkbenchPointer}
    >
      <div className="ambient-image" />
      <div className="paper-wash" />
      <Sidebar
        activeView={activeView}
        query={query}
        user={auth.user}
        assistantHasUnread={assistantHasUnread}
        onLogout={handleLogout}
        onNavigate={handleNavigate}
      />
      <section className="workspace">
        <Topbar
          activeView={activeView}
          status={status}
          restoring={restoring}
          graphFocus={graphFocus}
          graph={graph}
        />
        {activeView === "assistant" && (
          <AssistantPanel
            messages={messages}
            prompt={prompt}
            setPrompt={setPrompt}
            onSubmit={handleChat}
            loading={chatLoading}
            thoughts={thoughts}
            thinkingProgress={thinkingProgress}
            threads={threads}
            activeThreadId={activeThreadId}
            onSelectThread={handleSelectThread}
            onNewThread={handleNewThread}
            onClearCurrentThread={handleClearCurrentThread}
            onDeleteThread={handleDeleteThread}
          />
        )}
        {activeView === "search" && (
          <SearchPanel
            query={query}
            setQuery={setQuery}
            onSubmit={handleSearch}
            results={filteredResults}
            allResults={results}
            loading={loading}
            selectedResult={selectedResult}
            onSelectResult={handleSelectResult}
            entityFilter={entityFilter}
            setEntityFilter={handleEntityFilterChange}
            sourceFilter={sourceFilter}
            setSourceFilter={handleSourceFilterChange}
            effectFilters={effectFilters}
            onToggleEffect={handleEffectFilterToggle}
            onClearFilters={handleClearSearchFilters}
            onQuickSearch={handleQuickSearch}
            onRotateHotQueries={handleRotateHotQueries}
            hotOffset={hotOffset}
            recentQueries={recentQueries}
            graphFocus={graphFocus}
          />
        )}
        {activeView === "graph" && (
          <GraphPanel
            graphData={graphData}
            rawGraph={graph}
            graphFocus={graphFocus}
            setGraphFocus={setGraphFocus}
            graphDepth={graphDepth}
            setGraphDepth={setGraphDepth}
            activeRelations={activeRelations}
            switchRelation={switchRelation}
            selectedNode={selectedNode}
            setSelectedNode={setSelectedNode}
            hasWebGL={hasWebGL}
            graphRef={graphRef}
            loading={loading}
          />
        )}
        {activeView === "admin" && auth.user?.role === "admin" && (
          <AdminPanel
            users={adminUsers}
            currentUser={auth.user}
            form={adminForm}
            setForm={setAdminForm}
            status={adminStatus}
            onCreate={handleCreateAdminUser}
            onDelete={handleDeleteAdminUser}
            onRefresh={refreshAdminUsers}
          />
        )}
      </section>
    </main>
  );
}

function Sidebar({ activeView, query, user, assistantHasUnread, onLogout, onNavigate }) {
  const tabs = [
    { id: "assistant", label: "问答", icon: MessageCircle, href: "/assistant" },
    { id: "search", label: "搜索", icon: Search, href: "/search" },
    { id: "graph", label: "图谱", icon: Network, href: "/graph" },
    ...(user?.role === "admin" ? [{ id: "admin", label: "用户", icon: Users, href: "/admin" }] : []),
  ];
  return <aside className="sidebar"><div className="brand"><span className="brand-mark"><b>{"药图"}</b></span><strong>{"中医知识图谱"}</strong><span>{user?.username || "未知用户"}</span></div><nav className="tabs" aria-label="主导航">{tabs.map((tab) => { const Icon = tab.icon; const href = tab.id === "graph" && query.trim() ? tab.href + "?q=" + encodeURIComponent(query.trim()) : tab.href; return <Link key={tab.id} className={["tab", activeView === tab.id ? "active" : "", tab.id === "assistant" && assistantHasUnread ? "has-unread" : ""].filter(Boolean).join(" ")} href={href} onClick={() => onNavigate(tab.id)} title={tab.label}><Icon size={18} /><span>{tab.label}</span></Link>; })}</nav><button className="logout-button" type="button" onClick={onLogout} title="退出登录"><LogOut size={17} /><span>{"退出"}</span></button></aside>;
}

function Topbar({ activeView, status, restoring, graphFocus, graph }) {
  return <header className="topbar"><div className="title-block"><h1>{activeTitle(activeView)}</h1>{restoring && <div className="status-row"><StatusPill icon={Clock} label="正在校验" tone="warm" /></div>}</div></header>;
}

function StatusPill({ icon: Icon, label, tone = "normal" }) { return <span className={"status-pill " + tone}><Icon size={14} />{label}</span>; }

function AssistantPanel(props) {
  const { messages, prompt, setPrompt, onSubmit, loading, thoughts, thinkingProgress, threads, activeThreadId, onSelectThread, onNewThread, onClearCurrentThread, onDeleteThread } = props;
  const activeThread = threads.find((thread) => thread.id === activeThreadId);
  return <div className="assistant-layout"><section className="history-panel"><div className="panel-heading"><div><p className="eyebrow">{"对话"}</p><h2>{"历史记录"}</h2></div><button className="icon-button" type="button" onClick={onNewThread} title="新建对话"><Plus size={17} /></button></div><div className="thread-list">{threads.map((thread) => <div key={thread.id} className={thread.id === activeThreadId ? "thread-item active" : "thread-item"}><button type="button" className="thread-main" onClick={() => onSelectThread(thread.id)}><strong>{thread.title || "未命名对话"}</strong><span>{thread.message_count} {"条"}</span></button><button className="thread-delete" type="button" onClick={() => onDeleteThread(thread.id)} title="删除对话"><Trash2 size={15} /></button></div>)}{!threads.length && <p className="empty-note">{"暂无历史对话，开始一次方药探索吧。"}</p>}</div></section><section className="chat-surface"><div className="history-strip"><span><History size={14} />{activeThread?.title || "当前对话"}</span><span><Brain size={14} />{loading ? "正在思考" : "就绪"}</span><button type="button" onClick={onClearCurrentThread} disabled={loading}>{"清空当前"}</button></div><div className="message-list">{messages.map((message, index) => <article key={message.role + "-" + index} className={["message", message.role].join(" ")}><span>{message.role === "assistant" ? "问" : "我"}</span><FormattedMessage content={message.content} /></article>)}</div><form className="composer" onSubmit={onSubmit}><input value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="请输入方剂、药材或症状问题" disabled={loading} /><button type="submit" title="发送" disabled={loading}><Send size={18} /></button></form></section><section className="thinking-panel strong"><div className="panel-heading"><div><p className="eyebrow">{"推理"}</p><h2>{"推理轨迹"}</h2></div><span className="progress-number">{thinkingProgress}%</span></div><div className="thinking-bar"><span style={{ width: String(thinkingProgress) + "%" }} /></div><div className="reasoning-steps">{["语义改写", "实体抽取", "图谱证据", "回答生成"].map((step, index) => <div key={step} className={thinkingProgress > index * 24 ? "reasoning-step active" : "reasoning-step"}><span /><div><strong>{step}</strong><small>{thinkingProgress > index * 24 ? "已完成" : "等待中"}</small></div></div>)}</div><div className="thinking-log">{thoughts.map((thought, index) => <p key={thought + "-" + index}>{thought}</p>)}{!thoughts.length && <p>{"等待模型输出推理链路…"}</p>}</div></section></div>;
}

function SearchPanel(props) {
  const { query, setQuery, results, allResults, selectedResult, entityFilter, setEntityFilter, sourceFilter, setSourceFilter, effectFilters, onToggleEffect, loading, onSubmit, onSelectResult, onClearFilters, onQuickSearch, onRotateHotQueries, hotOffset, graphFocus } = props;
  const entityOptions = ["全部", "方剂", "药材"];
  const sourceOptions = ["伤寒论", "金匮要略", "温病条辨", "太平惠民和剂局方"];
  const effectOptions = ["发汗解表", "清热解毒", "补气", "化痰止咳", "利水渗湿"];
  const visibleHotQueries = Array.from({ length: Math.min(5, hotQueries.length) }, (_, index) => hotQueries[(hotOffset + index) % hotQueries.length]);
  const detailEntries = Object.entries(selectedResult?.properties || {});
  const primaryDetailEntries = detailEntries.filter(([key]) => key !== "related").slice(0, 10);
  const relatedDetail = selectedResult?.properties?.related;
  return <div className="search-layout"><aside className="search-filter-panel"><div className="panel-heading"><h2>{"筛选"}</h2><button type="button" className="text-button" onClick={onClearFilters}>{"清空"}</button></div><div className="filter-section"><strong>{"实体类型"}</strong>{entityOptions.map((filter) => <label key={filter} className={entityFilter === filter ? "check-row active" : "check-row"}><input type="checkbox" checked={entityFilter === filter} onChange={() => setEntityFilter(filter)} /><span>{filter}</span></label>)}</div><div className="filter-section"><strong>{"方书来源"}</strong><label className={!sourceFilter ? "check-row active" : "check-row"}><input type="checkbox" checked={!sourceFilter} onChange={() => setSourceFilter("")} /><span>{"全部"}</span></label>{sourceOptions.map((source) => <label key={source} className={sourceFilter === source ? "check-row active" : "check-row"}><input type="checkbox" checked={sourceFilter === source} onChange={() => setSourceFilter(source)} /><span>{source}</span></label>)}</div><div className="filter-section"><strong>{"功效"}</strong>{effectOptions.map((effect) => <label key={effect} className={effectFilters.includes(effect) ? "check-row active" : "check-row"}><input type="checkbox" checked={effectFilters.includes(effect)} onChange={() => onToggleEffect(effect)} /><span>{effect}</span></label>)}</div></aside><section className="search-main"><form className="search-box" onSubmit={onSubmit}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索方剂、药材、功效或症状" /><button type="submit" disabled={loading}>{loading ? "搜索中" : "搜索"}</button></form><div className="facet-row"><strong>{"热门检索"}</strong>{visibleHotQueries.map((item) => <button key={item} type="button" className="facet" onClick={() => onQuickSearch(item)}>{item}</button>)}<button type="button" className="facet ghost" onClick={onRotateHotQueries}>{"换一组"}</button></div><div className="result-tools"><span>{"共 "}{allResults.length}{" 条结果"}</span></div><div className="result-list">{loading && <SearchSkeleton />}{!loading && results.map((item) => <button type="button" className={selectedResult?.id === item.id ? "result-card active" : "result-card"} key={item.id} onClick={() => onSelectResult(item)}><div className="result-title"><span className={["entity-chip", item.label].join(" ")}>{entityLabel(item.label)}</span><h2>{item.name}</h2><ChevronRight size={18} /></div><dl>{["source", "ingredients", "effect", "indication", "taboo"].map((key) => item.properties?.[key] ? <div key={key}><dt>{propertyLabel(key)}</dt><dd>{String(item.properties[key])}</dd></div> : null)}</dl><p className="relation-count">{countRelated(item)} {"条关系"}</p></button>)}{!results.length && !loading && <p className="empty-note">{"暂无匹配结果，请更换关键词或清空筛选。"}</p>}</div></section><aside className="search-side"><section className="sync-panel"><p className="eyebrow">{"图谱联动"}</p><h2>{"同步到知识图谱"}</h2><strong>{graphFocus || "未选实体"}</strong><span>{graphFocus ? "已准备查看 · 深度 1/2 · 上限 80" : "搜索后自动同步"}</span><Link className="primary-link" href={graphFocus ? "/graph?q=" + encodeURIComponent(graphFocus) : "/graph"}>{"打开图谱"}</Link></section><section className="detail-panel"><p className="eyebrow">{"实体详情"}</p>{selectedResult ? <><h2>{selectedResult.name}</h2><div className="detail-tabs"><span className={["entity-chip", selectedResult.label].join(" ")}>{entityLabel(selectedResult.label)}</span><span>{countRelated(selectedResult)} {"关系"}</span></div><dl>{primaryDetailEntries.map(([key, value]) => <div key={key}><dt>{propertyLabel(key)}</dt><dd>{String(value)}</dd></div>)}{relatedDetail && <div><dt>{"关联知识"}</dt><dd>{String(relatedDetail)}</dd></div>}</dl><Link className="secondary-link" href={"/assistant?q=" + encodeURIComponent(selectedResult.name)}>{"在问答中解释"}</Link></> : <p className="empty-note">{"请从左侧选择一个结果"}</p>}</section></aside></div>;
}

function GraphPanel(props) {
  const { graphData, rawGraph, graphFocus, setGraphFocus, graphDepth, setGraphDepth, activeRelations, switchRelation, selectedNode, setSelectedNode, hasWebGL, graphRef, loading } = props;
  const sceneRef = useRef(null);
  const [graphSize, setGraphSize] = useState({ width: 1, height: 1 });
  useEffect(() => { function measureScene() { const rect = sceneRef.current?.getBoundingClientRect(); if (!rect) return; setGraphSize({ width: Math.max(320, Math.floor(rect.width)), height: Math.max(360, Math.floor(rect.height)) }); } measureScene(); const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measureScene) : null; if (observer && sceneRef.current) observer.observe(sceneRef.current); window.addEventListener("resize", measureScene); return () => { observer?.disconnect(); window.removeEventListener("resize", measureScene); }; }, []);
  useEffect(() => { const timers = [700, 1600, 2800].map((delay) => window.setTimeout(() => centerGraphCamera(graphRef, 720), delay)); return () => { timers.forEach(window.clearTimeout); }; }, [graphData.nodes.length, graphData.links.length, graphFocus, graphRef]);
  return <div className="graph-layout"><section className="graph-toolbar"><div className="graph-meta"><span className="entity-chip Formula">{graphFocus}</span><strong>{rawGraph.nodes.length} {"节点"}</strong><strong>{rawGraph.edges.length} {"关系"}</strong>{loading && <strong>{"加载中"}</strong>}</div><div className="graph-controls"><label>{"深度"}<select value={graphDepth} onChange={(event) => setGraphDepth(Number(event.target.value))}><option value={1}>{"1 跳"}</option><option value={2}>{"2 跳"}</option></select></label><span className="graph-depth-help" title="1跳仅显示中心实体的直接关系；2跳会继续扩展到邻居的邻居。">{"1跳=直接关系，2跳=再扩展一层"}</span></div></section><section className="graph-scene" ref={sceneRef}><div className="relation-filters">{relationFilters.map((label) => <button key={label} type="button" className={activeRelations.includes(label) ? "relation-filter active" : "relation-filter"} onClick={() => switchRelation(label)}>{relationLabel(label)}</button>)}</div>{hasWebGL ? <ThreeKnowledgeGraph graphData={graphData} graphFocus={graphFocus} graphSize={graphSize} onSelect={(node) => { setSelectedNode(node); setGraphFocus(node.name); }} /> : <KnowledgeGraphFallback graph={{ nodes: graphData.nodes, edges: graphData.links }} focus={graphFocus} onSelect={(node) => { setSelectedNode(node); setGraphFocus(node.name); }} />}<div className="graph-legend">{["Formula", "Herb", "Symptom", "Effect", "Source"].map((label) => <span key={label}><i style={{ background: entityColor(label) }} />{entityLabel(label)}</span>)}</div></section><aside className="graph-inspector"><p className="eyebrow">{"实体详情"}</p>{selectedNode ? <><h2>{selectedNode.name}</h2><span className={["entity-chip", selectedNode.label].join(" ")}>{entityLabel(selectedNode.label)}</span><dl>{Object.entries(selectedNode.properties || {}).map(([key, value]) => <div key={key}><dt>{propertyLabel(key)}</dt><dd>{String(value)}</dd></div>)}{!Object.keys(selectedNode.properties || {}).length && <div><dt>{"提示"}</dt><dd>{"当前实体暂无更多属性，可继续扩展关联节点。"}</dd></div>}</dl><Link className="primary-link" href={"/assistant?q=" + encodeURIComponent(selectedNode.name)}>{"在问答中解释"}</Link><Link className="secondary-link" href={"/search?q=" + encodeURIComponent(selectedNode.name)}>{"返回搜索结果"}</Link></> : <p className="empty-note">{"点击图谱节点查看详情"}</p>}<div className="graph-state"><span><Layers3 size={14} />{"稳定布局"}</span><span><Activity size={14} />{"可拖动旋转"}</span><span><Network size={14} />{"关系可筛选"}</span></div></aside></div>;
}

function ThreeKnowledgeGraph({ graphData, graphFocus, graphSize, resetKey, onSelect }) {
  const mountRef = useRef(null);
  const [renderError, setRenderError] = useState("");

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !graphData.nodes.length) return undefined;
    mount.dataset.state = "starting";
    setRenderError("");

    let cleanup = () => {};
    try {
      mount.replaceChildren();

      const width = Math.max(320, graphSize.width || mount.clientWidth || 900);
      const height = Math.max(360, graphSize.height || mount.clientHeight || 640);
      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2(0x06251d, 0.0028);

      const camera = new THREE.PerspectiveCamera(46, width / height, 0.1, 1200);
      camera.position.set(0, 22, 330);
      camera.lookAt(0, 0, 0);

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
        preserveDrawingBuffer: false,
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
      renderer.setSize(width, height);
      renderer.domElement.className = "three-graph-canvas";
      mount.appendChild(renderer.domElement);
      mount.dataset.state = "canvas-ready";

      const sceneGroup = new THREE.Group();
      scene.add(sceneGroup);

      const ambient = new THREE.AmbientLight(0xfff4dc, 1.45);
      scene.add(ambient);
      const keyLight = new THREE.PointLight(0xffd0a4, 2.2, 520);
      keyLight.position.set(-120, 110, 210);
      scene.add(keyLight);
      const fillLight = new THREE.PointLight(0x8bd7ac, 1.6, 420);
      fillLight.position.set(150, -60, 130);
      scene.add(fillLight);

      const positions = placeNodes3D(graphData.nodes, graphFocus);
      const nodeObjects = new Map();
      graphData.nodes.forEach((node) => {
        const object = createLabeledGraphNode(node);
        const point = positions[node.id] || { x: 0, y: 0, z: 0 };
        object.position.set(point.x, point.y, point.z);
        object.userData.node = node;
        nodeObjects.set(node.id, object);
        sceneGroup.add(object);
      });

      graphData.links.forEach((edge) => {
      const sourceId = edgeEndpointId(edge.source);
      const targetId = edgeEndpointId(edge.target);
      const source = positions[sourceId];
      const target = positions[targetId];
      if (!source || !target) return;

      const geometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(source.x, source.y, source.z),
        new THREE.Vector3(target.x, target.y, target.z),
      ]);
      const material = new THREE.LineBasicMaterial({
        color: relationThreeColor(edge.label),
        transparent: true,
        opacity: 0.72,
      });
      const line = new THREE.Line(geometry, material);
      sceneGroup.add(line);
      });

      const raycaster = new THREE.Raycaster();
      const pointer = new THREE.Vector2();
      let dragging = false;
      let moved = false;
      let lastX = 0;
      let lastY = 0;
      let frameId = 0;

    function onPointerDown(event) {
      dragging = true;
      moved = false;
      lastX = event.clientX;
      lastY = event.clientY;
      renderer.domElement.setPointerCapture?.(event.pointerId);
    }

    function onPointerMove(event) {
      if (!dragging) return;
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      sceneGroup.rotation.y += dx * 0.006;
      sceneGroup.rotation.x += dy * 0.004;
      sceneGroup.rotation.x = Math.max(-0.72, Math.min(0.72, sceneGroup.rotation.x));
      lastX = event.clientX;
      lastY = event.clientY;
    }

    function onPointerUp(event) {
      dragging = false;
      renderer.domElement.releasePointerCapture?.(event.pointerId);
      if (moved) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const intersections = raycaster.intersectObjects([...nodeObjects.values()], true);
      const picked = intersections.find((hit) => {
        let object = hit.object;
        while (object) {
          if (object.userData?.node) return true;
          object = object.parent;
        }
        return false;
      });
      if (!picked) return;
      let object = picked.object;
      while (object && !object.userData?.node) object = object.parent;
      if (object?.userData?.node) onSelect(object.userData.node);
    }

    function onWheel(event) {
      event.preventDefault();
      camera.position.z = Math.max(180, Math.min(520, camera.position.z + event.deltaY * 0.28));
      camera.lookAt(0, 0, 0);
    }

      renderer.domElement.addEventListener("pointerdown", onPointerDown);
      renderer.domElement.addEventListener("pointermove", onPointerMove);
      renderer.domElement.addEventListener("pointerup", onPointerUp);
      renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

    function animate() {
      if (!dragging) sceneGroup.rotation.y += 0.0016;
      renderer.render(scene, camera);
      frameId = window.requestAnimationFrame(animate);
    }
      animate();

      cleanup = () => {
        window.cancelAnimationFrame(frameId);
        renderer.domElement.removeEventListener("pointerdown", onPointerDown);
        renderer.domElement.removeEventListener("pointermove", onPointerMove);
        renderer.domElement.removeEventListener("pointerup", onPointerUp);
        renderer.domElement.removeEventListener("wheel", onWheel);
        mount.replaceChildren();
        scene.traverse((object) => {
          object.geometry?.dispose?.();
          if (Array.isArray(object.material)) {
            object.material.forEach((material) => material.dispose?.());
          } else {
            object.material?.dispose?.();
          }
        });
        renderer.dispose();
      };
    } catch (error) {
      mount.dataset.state = "failed";
      setRenderError(error instanceof Error ? error.message : "图谱渲染失败");
    }
    return () => cleanup();
  }, [graphData, graphFocus, graphSize.width, graphSize.height, resetKey, onSelect]);

  if (!graphData.nodes.length) {
    return <div className="kg-canvas empty">{"暂无图谱数据"}</div>;
  }

  return (
    <div className="three-graph-mount" ref={mountRef} aria-label="三维知识图谱">
      {renderError && <div className="kg-canvas empty">{"三维图谱初始化失败："}{renderError}</div>}
    </div>
  );
}

function centerGraphCamera(graphRef, duration = 600) {
  const graph = graphRef.current;
  if (!graph) return;
  graph.centerAt?.(0, 0, duration);
  graph.cameraPosition?.({ x: 0, y: 0, z: 330 }, { x: 0, y: 0, z: 0 }, duration);
  window.setTimeout(() => {
    graph.centerAt?.(0, 0, Math.floor(duration / 2));
    graph.zoomToFit?.(Math.floor(duration / 2), 150);
  }, Math.max(80, Math.floor(duration * 0.55)));
}

function createLabeledGraphNode(node) {
  const radius = node.val >= 8 ? 10.6 : 7.4;
  const color = new THREE.Color(node.color || "#4E8F5A");
  const group = new THREE.Group();

  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 42, 42),
    new THREE.MeshPhysicalMaterial({
      color,
      roughness: 0.28,
      metalness: 0.08,
      clearcoat: 0.45,
      clearcoatRoughness: 0.38,
      transparent: true,
      opacity: 0.92,
      emissive: color.clone().multiplyScalar(0.24),
    }),
  );
  group.add(sphere);

  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(radius * 1.18, 32, 32),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: node.val >= 8 ? 0.2 : 0.12,
      depthWrite: false,
    }),
  );
  group.add(halo);

  const labelMaterial = new THREE.SpriteMaterial({
    map: createNodeLabelTexture(node.name, node.label, node.color),
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(labelMaterial);
  const displayName = String(node.name || "实体");
  const widthScale = Math.max(radius * 5.4, Math.min(radius * 8.2, displayName.length * radius * 1.7));
  sprite.scale.set(widthScale, radius * 2.02, 1);
  sprite.position.set(0, 0, radius + 0.62);
  sprite.renderOrder = 10;
  group.add(sprite);

  return group;
}

function createNodeLabelTexture(name, label, nodeColor) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 184;
  const ctx = canvas.getContext("2d");
  const displayName = String(name || "实体").slice(0, 10);
  const isLong = displayName.length > 4;
  const isFormula = label === "Formula";
  const accent = nodeColor || (isFormula ? "#B9472E" : "#4E8F5A");

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const gradient = ctx.createRadialGradient(256, 92, 16, 256, 92, 238);
  gradient.addColorStop(0, "rgba(255,250,240,0.99)");
  gradient.addColorStop(0.62, "rgba(255,250,240,0.92)");
  gradient.addColorStop(1, "rgba(255,250,240,0)");
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.ellipse(256, 88, 216, 62, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "rgba(255, 250, 240, 0.84)";
  ctx.beginPath();
  ctx.ellipse(256, 88, 196, 48, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = isFormula ? "rgba(255,250,240,0.96)" : "rgba(20,61,43,0.34)";
  ctx.lineWidth = isFormula ? 6 : 4;
  ctx.beginPath();
  ctx.ellipse(256, 88, 188, 44, 0, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = accent;
  ctx.globalAlpha = 0.28;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.ellipse(256, 88, 170, 36, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = 1;

  ctx.shadowColor = isFormula ? "rgba(72,25,16,0.55)" : "rgba(255,250,240,0.72)";
  ctx.shadowBlur = isFormula ? 10 : 5;
  ctx.shadowOffsetY = isFormula ? 2 : 1;

  ctx.fillStyle = "#143D2B";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `900 ${isLong ? 48 : 58}px STKaiti, KaiTi, "Microsoft YaHei", sans-serif`;
  ctx.fillText(displayName, 256, 84);

  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(20,61,43,0.68)";
  ctx.font = "700 21px Microsoft YaHei, sans-serif";
  ctx.fillText(entityLabel(label), 256, 128);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function LoginScreenV2({ onAuthed, onContinue, savedSession, status }) {
  const [showLogin, setShowLogin] = useState(() => Boolean(savedSession));
  const [loginKind, setLoginKind] = useState("user");
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const landingRef = useRef(null);
  const isAdmin = loginKind === "admin";

  useEffect(() => {
    if (savedSession) {
      setShowLogin(true);
    }
  }, [savedSession]);

  useEffect(() => {
    if (isAdmin) { setMode("login"); setUsername("admin"); setPassword("admin123"); }
    else { setUsername("demo"); setPassword("demo123"); }
  }, [isAdmin]);

  async function submit(event) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const data = isAdmin ? await adminLogin(username, password) : mode === "login" ? await login(username, password) : await register(username, password);
      await onAuthed({ token: data.token, user: data.user });
    } catch (err) {
      setError(isAdmin ? "管理员登录失败，请确认账号具备管理员权限。" : mode === "login" ? "登录失败，请检查账号密码。" : "注册失败，用户名可能已存在。");
    } finally { setLoading(false); }
  }

  function handleLandingPointerMove(event) {
    const element = landingRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
    const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    element.style.setProperty("--mx", x.toFixed(3));
    element.style.setProperty("--my", y.toFixed(3));
  }

  function resetLandingPointer() {
    const element = landingRef.current;
    if (!element) return;
    element.style.setProperty("--mx", "0");
    element.style.setProperty("--my", "0");
  }

  if (!showLogin) {
    return (
      <main className="landing-shell" ref={landingRef} onPointerMove={handleLandingPointerMove} onPointerLeave={resetLandingPointer}>
        <div className="landing-image-bg" />
        <div className="landing-paper" />
        <div className="landing-mist" aria-hidden="true">
          <span className="mist mist-a" />
          <span className="mist mist-b" />
          <span className="mist mist-c" />
        </div>
        <div className="landing-graph" aria-hidden="true">
          <span className="node node-a" />
          <span className="node node-b" />
          <span className="node node-c" />
          <span className="node node-d" />
          <i className="line line-a" />
          <i className="line line-b" />
          <i className="line line-c" />
          <span className="spark spark-a" />
          <span className="spark spark-b" />
          <span className="spark spark-c" />
        </div>
        <button className="landing-login-button" type="button" onClick={() => setShowLogin(true)}>{"登录"}</button>
        <section className="landing-hero" aria-label="中医图谱入口">
          <p>{"药图"}</p>
          <h1>{"中医图谱"}</h1>
          <strong>{"方药知识 · 图谱证据 · 智能问答"}</strong>
        </section>
      </main>
    );
  }

  return (
    <main className="login-shell login-shell-v2">
      <div className="login-image-bg" />
      <div className="paper-wash" />
      <section className="login-panel login-panel-v2">
        <h1>{isAdmin ? "登录管理员" : "登录用户"}</h1>
        <div className="login-kind-switch" role="tablist" aria-label="登录类型">
          <button type="button" className={loginKind === "user" ? "active" : ""} onClick={() => setLoginKind("user")}>{"用户登录"}</button>
          <button type="button" className={loginKind === "admin" ? "active" : ""} onClick={() => setLoginKind("admin")}>{"管理员登录"}</button>
        </div>
        {savedSession && <div className="session-card"><span>{"已检测到上次会话："}{savedSession.user?.username}</span><button type="button" onClick={() => onContinue(savedSession)}>{"继续进入"}</button></div>}
        <form onSubmit={submit} className="login-form">
          <label><span>{isAdmin ? "管理员账号" : "用户名"}</span><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
          <label><span>{"密码"}</span><input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" disabled={loading}>{loading ? "处理中" : isAdmin ? "进入管理后台" : mode === "login" ? "登录" : "创建账号"}</button>
        </form>
        {!isAdmin && <button className="mode-switch" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>{mode === "login" ? "没有账号？创建一个" : "已有账号？返回登录"}</button>}
      </section>
    </main>
  );
}

function AdminPanel({ users, currentUser, form, setForm, status, onCreate, onDelete, onRefresh }) {
  const userCount = users.filter((user) => user.role !== "admin").length;
  const adminCount = users.filter((user) => user.role === "admin").length;
  return <div className="admin-layout"><section className="admin-hero"><div><p className="eyebrow">{"管理员"}</p><h2>{"用户管理"}</h2><p>{"创建、删除平台账号，维护普通用户与管理员权限。"}</p></div><div className="admin-stats"><span><Users size={16} />{userCount} {"用户"}</span><span><ShieldCheck size={16} />{adminCount} {"管理员"}</span></div></section><section className="admin-create"><div className="panel-heading"><div><p className="eyebrow">{"创建账号"}</p><h2>{"新增用户"}</h2></div><UserPlus size={22} /></div><form className="admin-form" onSubmit={onCreate}><label><span>{"用户名"}</span><input value={form.username} onChange={(event) => setForm((item) => ({ ...item, username: event.target.value }))} /></label><label><span>{"初始密码"}</span><input type="password" value={form.password} onChange={(event) => setForm((item) => ({ ...item, password: event.target.value }))} /></label><label><span>{"角色"}</span><select value={form.role} onChange={(event) => setForm((item) => ({ ...item, role: event.target.value }))}><option value="user">{"普通用户"}</option><option value="admin">{"管理员"}</option></select></label><button type="submit">{"创建账号"}</button></form><p className="admin-status">{status}</p></section><section className="admin-users"><div className="panel-heading"><div><p className="eyebrow">{"账号列表"}</p><h2>{"用户列表"}</h2></div><button type="button" className="mode-switch compact" onClick={onRefresh}>{"刷新"}</button></div><div className="user-table">{users.map((user) => <article key={user.id} className="user-row"><div><strong>{user.username}</strong><span>{user.role === "admin" ? "管理员" : "普通用户"} {" · "}{user.message_count || 0}{" 条消息"}</span></div><small>{user.last_login_at ? "最近登录 " + user.last_login_at : "尚未登录"}</small><button type="button" disabled={user.id === currentUser?.id} onClick={() => onDelete(user.id)}>{"删除"}</button></article>)}{!users.length && <p className="empty-note">{"暂无用户记录"}</p>}</div></section></div>;
}

function LoginScreen({ onAuthed, status }) { return <LoginScreenV2 onAuthed={onAuthed} status={status} />; }

function SearchSkeleton() {
  return (
    <article className="result-card skeleton">
      <span />
      <strong />
      <p />
      <p />
    </article>
  );
}

function KnowledgeGraphFallback({ graph, focus, onSelect }) {
  const layout = placeNodes(graph.nodes, focus);
  if (!graph.nodes.length) return <div className="kg-canvas empty">{"暂无图谱数据"}</div>;
  return <div className="kg-canvas"><svg viewBox="0 0 720 460" role="img" aria-label="知识图谱">{graph.edges.map((edge) => { const source = layout[edge.source]; const target = layout[edge.target]; if (!source || !target) return null; return <g key={edge.id}><line x1={source.x} y1={source.y} x2={target.x} y2={target.y} /><text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2}>{relationLabel(edge.label)}</text></g>; })}</svg>{graph.nodes.map((node) => { const point = layout[node.id]; if (!point) return null; return <button type="button" className={["kg-node", node.label, node.name === focus ? "focused" : ""].filter(Boolean).join(" ")} key={node.id} style={{ left: String(point.x / 7.2) + "%", top: String(point.y / 4.6) + "%" }} onClick={() => onSelect(node)}><span>{node.name}</span><small>{entityLabel(node.label)}</small></button>; })}</div>;
}

function FormattedMessage({ content }) {
  if (!content) return <div className="formatted-answer muted">{"正在等待回答…"}</div>;
  const normalized = content.replace(/\s*###\s*/g, "\n\n### ").replace(/\s+-\s+\*\*/g, "\n- **").replace(/\s+-\s+/g, "\n- ");
  const lines = normalized.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  return <div className="formatted-answer">{lines.map((line, index) => { if (line.startsWith("### ")) return <h3 key={index}>{cleanMarkdown(line.replace(/^###\s*/, ""))}</h3>; if (/^[-*]\s+/.test(line)) return <p className="answer-list-item" key={index}>{cleanMarkdown(line.replace(/^[-*]\s+/, ""))}</p>; return <p key={index}>{cleanMarkdown(line)}</p>; })}</div>;
}

function activeTitle(view) { return { assistant: "智能问答", search: "方药知识搜索", graph: "知识图谱关联", admin: "管理员后台" }[view] || "中医知识图谱"; }
function appendToLastAssistant(messages, chunk) { const next = [...messages]; const lastIndex = next.length - 1; if (lastIndex >= 0 && next[lastIndex].role === "assistant") { next[lastIndex] = { ...next[lastIndex], content: next[lastIndex].content + chunk }; return next; } return [...next, { role: "assistant", content: chunk }]; }
function cleanMarkdown(text) { return text.replace(/\*\*/g, "").trim(); }
function countRelated(item) { const related = item.properties?.related; if (!related) return 0; return String(related).split(/[;；]/).filter(Boolean).length; }
function propertyLabel(key) { return { source: "出处", ingredients: "组成", effect: "功效", usage: "用法", taboo: "禁忌", indication: "主治", category: "分类", nature: "药性", flavor: "药味", meridian: "归经", dosage: "剂量", preparation: "炮制", alias: "别名", description: "说明", related: "关联知识", label: "类型" }[key] || key; }
function entityLabel(label) { return { Formula: "方剂", Herb: "药材", Symptom: "症状", Disease: "疾病", Effect: "功效", Source: "出处", FormulaCategory: "方剂分类", HerbNature: "药性", HerbFlavor: "药味", Meridian: "归经", Entity: "实体" }[label] || label; }
function entityFilterToBackendLabel(filter) { if (filter === "方剂") return "Formula"; if (filter === "药材") return "Herb"; return "Formula,Herb"; }
function relationLabel(label) { return { HAS_INGREDIENT: "组成", ALLEVIATES_SYMPTOM: "缓解症状", TREATS_DISEASE: "治疗疾病", HAS_EFFECT: "具有功效", BELONGS_TO_CATEGORY: "归属分类", FROM_SOURCE: "出自", HAS_NATURE: "药性", HAS_FLAVOR: "药味", ENTERS_MERIDIAN: "归经", RELATED_TO: "相关" }[label] || String(label || "").replaceAll("_", ""); }

function entityColor(label, focused = false) {
  if (focused) return "#B9472E";
  return {
    Formula: "#B9472E",
    Herb: "#4E8F5A",
    Symptom: "#C59A4A",
    Disease: "#6D4C8D",
    Effect: "#2D7680",
    Source: "#C8D8B8",
    FormulaCategory: "#8A6D3B",
    Meridian: "#67A98B",
  }[label] || "#E5D7BB";
}

function relationColor(label) {
  return {
    HAS_INGREDIENT: "rgba(200, 216, 184, 0.76)",
    HAS_EFFECT: "rgba(78, 143, 90, 0.78)",
    FROM_SOURCE: "rgba(229, 215, 187, 0.72)",
    ALLEVIATES_SYMPTOM: "rgba(197, 154, 74, 0.78)",
    TREATS_DISEASE: "rgba(185, 71, 46, 0.74)",
  }[label] || "rgba(255, 250, 240, 0.5)";
}

function relationThreeColor(label) {
  return {
    HAS_INGREDIENT: "#d6e3c5",
    HAS_EFFECT: "#74b87b",
    FROM_SOURCE: "#e5d7bb",
    ALLEVIATES_SYMPTOM: "#d6aa56",
    TREATS_DISEASE: "#d36a52",
  }[label] || "#fffaf0";
}

function edgeEndpointId(endpoint) {
  if (typeof endpoint === "string") return endpoint;
  return endpoint?.id || endpoint?.name || "";
}

function placeNodes3D(nodes, focus) {
  const center = nodes.find((node) => node.name === focus) || nodes[0];
  const positions = {};
  if (!center) return positions;
  positions[center.id] = { x: 0, y: 0, z: 0 };
  const outerNodes = nodes.filter((node) => node.id !== center.id);
  const radiusX = outerNodes.length > 6 ? 130 : 112;
  const radiusY = outerNodes.length > 6 ? 86 : 76;
  outerNodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(outerNodes.length, 1) - Math.PI / 2;
    positions[node.id] = {
      x: Math.cos(angle) * radiusX,
      y: Math.sin(angle) * radiusY,
      z: Math.sin(index * 1.7) * 46,
    };
  });
  return positions;
}

function placeNodes(nodes, focus) {
  const center = nodes.find((node) => node.name === focus) || nodes[0];
  const positions = {};
  if (!center) return positions;
  positions[center.id] = { x: 360, y: 230 };
  const radius = nodes.length > 5 ? 170 : 145;
  nodes.filter((node) => node.id !== center.id).forEach((node, index, outerNodes) => {
    const angle = (Math.PI * 2 * index) / Math.max(outerNodes.length, 1) - Math.PI / 2;
    positions[node.id] = { x: 360 + Math.cos(angle) * radius, y: 230 + Math.sin(angle) * radius };
  });
  return positions;
}
