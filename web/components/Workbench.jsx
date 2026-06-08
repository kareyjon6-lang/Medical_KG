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
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  clearThreadMessages,
  createChatThread,
  deleteChatThread,
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

const chatRuntime = {
  activeThreadId: "",
  activeView: "assistant",
  loading: false,
  messages: defaultMessages,
  progress: 0,
  subscribers: new Set(),
  thoughts: [],
  unread: false,
};

function snapshotChatRuntime() {
  return {
    activeThreadId: chatRuntime.activeThreadId,
    loading: chatRuntime.loading,
    messages: chatRuntime.messages,
    progress: chatRuntime.progress,
    thoughts: chatRuntime.thoughts,
    unread: chatRuntime.unread,
  };
}

function patchChatRuntime(patch) {
  Object.assign(chatRuntime, patch);
  const snapshot = snapshotChatRuntime();
  chatRuntime.subscribers.forEach((subscriber) => subscriber(snapshot));
}

function subscribeChatRuntime(subscriber) {
  chatRuntime.subscribers.add(subscriber);
  subscriber(snapshotChatRuntime());
  return () => chatRuntime.subscribers.delete(subscriber);
}

export default function Workbench({ initialView = "assistant" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const graphRef = useRef(null);
  const runtimeSnapshot = snapshotChatRuntime();
  const [auth, setAuth] = useState({ token: "", user: null });
  const [restoring, setRestoring] = useState(true);
  const [activeView, setActiveView] = useState(initialView);
  const [status, setStatus] = useState("等待登录");
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

  useEffect(() => {
    const token = window.localStorage.getItem("tcm_kg_token");
    const savedQuery = window.localStorage.getItem("tcm_kg_query");
    const urlQuery = searchParams.get("q");
    const nextQuery = urlQuery || savedQuery || "";

    setQuery(nextQuery);
    setGraphFocus(nextQuery);

    if (!token) {
      setRestoring(false);
      return;
    }

    setAuth({ token, user: null });
    setStatus("正在验证登录状态");
    fetchMe(token)
      .then((data) => {
        setAuth({ token, user: data.user });
        setStatus("会话已连接");
      })
      .catch(() => {
        window.localStorage.removeItem("tcm_kg_token");
        setAuth({ token: "", user: null });
        setStatus("登录已过期，请重新登录");
      })
      .finally(() => setRestoring(false));
  }, [searchParams]);

  useEffect(() => {
    setActiveView(initialView);
  }, [initialView]);

  useEffect(() => subscribeChatRuntime((snapshot) => {
    setMessages(snapshot.messages);
    setThoughts(snapshot.thoughts);
    setThinkingProgress(snapshot.progress);
    setChatLoading(snapshot.loading);
    setAssistantHasUnread(snapshot.unread);
    if (snapshot.activeThreadId) {
      setActiveThreadId(snapshot.activeThreadId);
    }
  }), []);

  useEffect(() => {
    chatRuntime.activeView = activeView;
    if (activeView === "assistant" && chatRuntime.unread) {
      patchChatRuntime({ unread: false });
    }
  }, [activeView]);

  useEffect(() => {
    if (!auth.token) return;
    refreshUserContext(auth.token);
  }, [auth.token]);

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

  async function handleAuthed(data) {
    window.localStorage.setItem("tcm_kg_token", data.token);
    setAuth({ token: data.token, user: data.user });
    setStatus("登录成功");
    await refreshUserContext(data.token);
  }

  async function handleLogout() {
    const token = auth.token;
    window.localStorage.removeItem("tcm_kg_token");
    setAuth({ token: "", user: null });
    setThreads([]);
    setActiveThreadId("");
    patchChatRuntime({ activeThreadId: "", loading: false, messages: defaultMessages, progress: 0, thoughts: [], unread: false });
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
      patchChatRuntime({
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
      patchChatRuntime({ activeThreadId: thread.id, messages: defaultMessages, progress: 0, thoughts: [], unread: false });
      setStatus("已创建新对话");
    } catch (error) {
      setStatus("新建对话失败");
    }
  }

  async function handleClearCurrentThread() {
    if (chatLoading) return;
    patchChatRuntime({ messages: defaultMessages, progress: 0, thoughts: [], unread: false });
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
        patchChatRuntime({ activeThreadId: "", messages: defaultMessages, progress: 0, thoughts: [], unread: false });
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
    patchChatRuntime({ activeThreadId: thread.id });
    return thread.id;
  }

  async function handleChat(event) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || chatRuntime.loading) return;

    setPrompt("");
    patchChatRuntime({
      loading: true,
      messages: [...chatRuntime.messages, { role: "user", content: text }, { role: "assistant", content: "" }],
      progress: 8,
      thoughts: [],
      unread: false,
    });
    setStatus("模型正在流式回答");

    try {
      const threadId = await ensureThreadForPrompt(text);
      patchChatRuntime({ activeThreadId: threadId });
      await postChatStream(
        text,
        auth.token,
        (eventMessage) => {
          if (eventMessage.type === "think") {
            const nextThoughts = appendThoughtChunk(chatRuntime.thoughts, eventMessage.msg || "");
            if (nextThoughts !== chatRuntime.thoughts) {
              patchChatRuntime({
                progress: Math.min(92, chatRuntime.progress + 8),
                thoughts: nextThoughts,
              });
            }
          }
          if (eventMessage.type === "stream") {
            patchChatRuntime({
              messages: appendToLastAssistant(chatRuntime.messages, eventMessage.msg || ""),
            });
          }
          if (eventMessage.type === "done") {
            patchChatRuntime({ progress: 100 });
          }
        },
        { threadId },
      );
      await refreshUserContext(auth.token);
      setStatus("回答生成完成");
      if (chatRuntime.activeView !== "assistant") {
        patchChatRuntime({ unread: true });
      }
    } catch (error) {
      patchChatRuntime({
        messages: appendToLastAssistant(chatRuntime.messages, "服务暂时不可用，请稍后再试。"),
        unread: chatRuntime.activeView !== "assistant",
      });
      setStatus("问答连接异常");
    } finally {
      patchChatRuntime({ loading: false, progress: chatRuntime.progress ? 100 : 0 });
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
    setActiveView(view);
    chatRuntime.activeView = view;
    if (view === "assistant") {
      patchChatRuntime({ unread: false });
    }
  }

  if (!auth.token && !restoring) {
    return <LoginScreen onAuthed={handleAuthed} status={status} />;
  }

  return (
    <main className={`app-shell view-${activeView}`}>
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
      </section>
    </main>
  );
}

function Sidebar({ activeView, query, user, assistantHasUnread, onLogout, onNavigate }) {
  const tabs = [
    { id: "assistant", label: "问答", icon: MessageCircle, href: "/assistant" },
    { id: "search", label: "搜索", icon: Search, href: "/search" },
    { id: "graph", label: "图谱", icon: Network, href: "/graph" },
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">药图<i>理问</i></span>
        <strong>中医知识图谱</strong>
        <span>{user?.username || "验证中"}</span>
      </div>
      <nav className="tabs" aria-label="主要页面">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const href = tab.id === "graph" && query.trim() ? `${tab.href}?q=${encodeURIComponent(query.trim())}` : tab.href;
          return (
            <Link
              key={tab.id}
              className={[
                "tab",
                activeView === tab.id ? "active" : "",
                tab.id === "assistant" && assistantHasUnread ? "has-unread" : "",
              ].filter(Boolean).join(" ")}
              href={href}
              onClick={() => onNavigate(tab.id)}
              title={tab.label}
            >
              <Icon size={18} />
              <span>{tab.label}</span>
            </Link>
          );
        })}
      </nav>
      <button className="logout-button" type="button" onClick={onLogout} title="退出登录">
        <LogOut size={17} />
        <span>退出</span>
      </button>
    </aside>
  );
}

function Topbar({ activeView, status, restoring, graphFocus, graph }) {
  return (
    <header className="topbar">
      <div className="title-block">
        <h1>{activeTitle(activeView)}</h1>
        <div className="status-row">
          {restoring && <StatusPill icon={Clock} label="验证登录" tone="warm" />}
          <StatusPill icon={Database} label="会话已连接" />
          <StatusPill icon={Activity} label="推理流式中" />
          <StatusPill icon={Network} label={`${graphFocus} · ${graph.nodes.length} 节点`} tone="focus" />
          <StatusPill icon={Clock} label={status} tone="warm" />
        </div>
      </div>
    </header>
  );
}

function StatusPill({ icon: Icon, label, tone = "normal" }) {
  return (
    <span className={`status-pill ${tone}`}>
      <Icon size={14} />
      {label}
    </span>
  );
}

function AssistantPanel(props) {
  const {
    messages,
    prompt,
    setPrompt,
    onSubmit,
    loading,
    thoughts,
    thinkingProgress,
    threads,
    activeThreadId,
    onSelectThread,
    onNewThread,
    onClearCurrentThread,
    onDeleteThread,
  } = props;

  const activeThread = threads.find((thread) => thread.id === activeThreadId);

  return (
    <div className="assistant-layout">
      <section className="history-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">对话</p>
            <h2>历史对话</h2>
          </div>
          <button className="icon-button" type="button" onClick={onNewThread} title="新建对话">
            <Plus size={17} />
          </button>
        </div>
        <div className="thread-list">
          {threads.map((thread) => (
            <div
              key={thread.id}
              className={thread.id === activeThreadId ? "thread-item active" : "thread-item"}
            >
              <button type="button" className="thread-main" onClick={() => onSelectThread(thread.id)}>
                <strong>{thread.title || "新的中医问答"}</strong>
                <span>{thread.message_count} 条</span>
              </button>
              <button className="thread-delete" type="button" onClick={() => onDeleteThread(thread.id)} title="删除历史对话">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
          {!threads.length && <p className="empty-note">暂无历史对话，发送问题后会自动保存。</p>}
        </div>
      </section>

      <section className="chat-surface">
        <div className="history-strip">
          <span><History size={14} />{activeThread?.title || "当前新对话"}</span>
          <span><Brain size={14} />{loading ? "模型思考中" : "等待提问"}</span>
          <button type="button" onClick={onClearCurrentThread} disabled={loading}>清空当前对话</button>
        </div>
        <div className="message-list">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <span>{message.role === "assistant" ? "助" : "我"}</span>
              <FormattedMessage content={message.content} />
            </article>
          ))}
        </div>
        <form className="composer" onSubmit={onSubmit}>
          <input
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="例如：麻黄汤适合什么症状？有哪些禁忌？"
            disabled={loading}
          />
          <button type="submit" title="发送" disabled={loading}>
            <Send size={18} />
          </button>
        </form>
      </section>

      <section className="thinking-panel strong">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">推理</p>
            <h2>推理轨迹</h2>
          </div>
          <span className="progress-number">{thinkingProgress}%</span>
        </div>
        <div className="thinking-bar">
          <span style={{ width: `${thinkingProgress}%` }} />
        </div>
        <div className="reasoning-steps">
          {["语义改写", "实体抽取", "图谱证据", "回答生成"].map((step, index) => (
            <div key={step} className={thinkingProgress > index * 24 ? "reasoning-step active" : "reasoning-step"}>
              <span />
              <div>
                <strong>{step}</strong>
                <small>{thinkingProgress > index * 24 ? "已完成" : "等待中"}</small>
              </div>
            </div>
          ))}
        </div>
        <div className="thinking-log">
          {thoughts.map((thought, index) => (
            <p key={`${thought}-${index}`}>{thought}</p>
          ))}
          {!thoughts.length && <p>模型思考过程会在流式回答时显示在这里。</p>}
        </div>
      </section>
    </div>
  );
}

function SearchPanel(props) {
  const {
    query,
    setQuery,
    onSubmit,
    results,
    allResults,
    loading,
    selectedResult,
    onSelectResult,
    entityFilter,
    setEntityFilter,
    sourceFilter,
    setSourceFilter,
    effectFilters,
    onToggleEffect,
    onClearFilters,
    onQuickSearch,
    onRotateHotQueries,
    hotOffset,
    graphFocus,
  } = props;

  const entityOptions = ["全部", "方剂", "药材"];
  const sourceOptions = ["《伤寒论》", "《金匮要略》", "《温病条辨》", "《本草纲目》"];
  const effectOptions = ["发汗解表", "宣肺平喘", "温阳散寒", "清热解毒", "补益气血"];
  const visibleHotQueries = Array.from({ length: Math.min(5, hotQueries.length) }, (_, index) => (
    hotQueries[(hotOffset + index) % hotQueries.length]
  ));
  const detailEntries = Object.entries(selectedResult?.properties || {});
  const primaryDetailEntries = detailEntries.filter(([key]) => key !== "related").slice(0, 10);
  const relatedDetail = selectedResult?.properties?.related;

  return (
    <div className="search-layout">
      <aside className="search-filter-panel">
        <div className="panel-heading">
          <h2>筛选条件</h2>
          <button type="button" className="text-button" onClick={onClearFilters}>清空</button>
        </div>
        <div className="filter-section">
          <strong>实体类别</strong>
          {entityOptions.map((filter) => (
            <label key={filter} className={entityFilter === filter ? "check-row active" : "check-row"}>
              <input type="checkbox" checked={entityFilter === filter} onChange={() => setEntityFilter(filter)} />
              <span>{filter}</span>
            </label>
          ))}
        </div>
        <div className="filter-section">
          <strong>来源出处</strong>
          <label className={!sourceFilter ? "check-row active" : "check-row"}>
            <input type="checkbox" checked={!sourceFilter} onChange={() => sourceFilter && setSourceFilter(sourceFilter)} />
            <span>不限</span>
          </label>
          {sourceOptions.map((source) => (
            <label key={source} className={sourceFilter === source ? "check-row active" : "check-row"}>
              <input type="checkbox" checked={sourceFilter === source} onChange={() => setSourceFilter(source)} />
              <span>{source}</span>
            </label>
          ))}
        </div>
        <div className="filter-section">
          <strong>功效</strong>
          {effectOptions.map((effect) => (
            <label key={effect} className={effectFilters.includes(effect) ? "check-row active" : "check-row"}>
              <input type="checkbox" checked={effectFilters.includes(effect)} onChange={() => onToggleEffect(effect)} />
              <span>{effect}</span>
            </label>
          ))}
        </div>
      </aside>
      <section className="search-main">
        <form className="search-box" onSubmit={onSubmit}>
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索方剂、药材、症状、功效" />
          <button type="submit" disabled={loading}>{loading ? "检索中" : "检索"}</button>
        </form>

        <div className="facet-row">
          <strong>热门搜索</strong>
          {visibleHotQueries.map((item) => (
            <button key={item} type="button" className="facet" onClick={() => onQuickSearch(item)}>{item}</button>
          ))}
          <button type="button" className="facet ghost" onClick={onRotateHotQueries}>换一换</button>
        </div>

        <div className="result-tools">
          <span>找到 {allResults.length} 条结果</span>
        </div>

        <div className="result-list">
          {loading && <SearchSkeleton />}
          {!loading && results.map((item) => (
            <button
              type="button"
              className={selectedResult?.id === item.id ? "result-card active" : "result-card"}
              key={item.id}
              onClick={() => onSelectResult(item)}
            >
              <div className="result-title">
                <span className={`entity-chip ${item.label}`}>{entityLabel(item.label)}</span>
                <h2>{item.name}</h2>
                <ChevronRight size={18} />
              </div>
              <dl>
                {["source", "ingredients", "effect", "indication", "taboo"].map((key) => (
                  item.properties?.[key] ? (
                    <div key={key}>
                      <dt>{propertyLabel(key)}</dt>
                      <dd>{String(item.properties[key])}</dd>
                    </div>
                  ) : null
                ))}
              </dl>
              <p className="relation-count">{countRelated(item)} 条关联线索</p>
            </button>
          ))}
          {!results.length && !loading && <p className="empty-note">暂无匹配结果，试试更短的药名或方剂名。</p>}
        </div>
      </section>

      <aside className="search-side">
        <section className="sync-panel">
          <p className="eyebrow">图谱同步</p>
          <h2>当前图谱焦点</h2>
          <strong>{graphFocus || "未选择"}</strong>
          <span>{graphFocus ? "图谱页已同步 · 深度 1/2 · 上限 80" : "搜索为空，图谱页同步为空"}</span>
          <Link className="primary-link" href={graphFocus ? `/graph?q=${encodeURIComponent(graphFocus)}` : "/graph"}>切换到图谱</Link>
        </section>

        <section className="detail-panel">
          <p className="eyebrow">实体详情</p>
          {selectedResult ? (
            <>
              <h2>{selectedResult.name}</h2>
              <div className="detail-tabs">
                {["成分药材", "功效", "主治", "出处", "禁忌"].map((label) => <span key={label}>{label}</span>)}
              </div>
              <dl>
                {primaryDetailEntries.map(([key, value]) => (
                  <div key={key}>
                    <dt>{propertyLabel(key)}</dt>
                    <dd>{String(value)}</dd>
                  </div>
                ))}
              </dl>
              {relatedDetail && (
                <details className="detail-expand">
                  <summary>{propertyLabel("related")}</summary>
                  <p>{String(relatedDetail)}</p>
                </details>
              )}
              <Link className="secondary-link" href={`/assistant?q=${encodeURIComponent(selectedResult.name)}`}>在问答中追问</Link>
            </>
          ) : (
            <p className="empty-note">选择一个检索结果后查看详情。</p>
          )}
        </section>
      </aside>
    </div>
  );
}

function GraphPanel(props) {
  const {
    graphData,
    rawGraph,
    graphFocus,
    setGraphFocus,
    graphDepth,
    setGraphDepth,
    activeRelations,
    switchRelation,
    selectedNode,
    setSelectedNode,
    hasWebGL,
    graphRef,
    loading,
  } = props;
  const sceneRef = useRef(null);
  const [graphSize, setGraphSize] = useState({ width: 1, height: 1 });

  useEffect(() => {
    function measureScene() {
      const rect = sceneRef.current?.getBoundingClientRect();
      if (!rect) return;
      setGraphSize({
        width: Math.max(320, Math.floor(rect.width)),
        height: Math.max(360, Math.floor(rect.height)),
      });
    }

    measureScene();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measureScene) : null;
    if (observer && sceneRef.current) {
      observer.observe(sceneRef.current);
    }
    window.addEventListener("resize", measureScene);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measureScene);
    };
  }, []);

  useEffect(() => {
    const timers = [700, 1600, 2800].map((delay) => window.setTimeout(() => {
      centerGraphCamera(graphRef, 720);
    }, delay));
    return () => {
      timers.forEach(window.clearTimeout);
    };
  }, [graphData.nodes.length, graphData.links.length, graphFocus, graphRef]);

  return (
    <div className="graph-layout">
      <section className="graph-toolbar">
        <div className="graph-meta">
          <span className="entity-chip Formula">{graphFocus}</span>
          <strong>{rawGraph.nodes.length} 节点</strong>
          <strong>{rawGraph.edges.length} 关系</strong>
          {loading && <strong>加载中</strong>}
        </div>
        <div className="graph-controls">
          <label>
            深度
            <select value={graphDepth} onChange={(event) => setGraphDepth(Number(event.target.value))}>
              <option value={1}>1 跳</option>
              <option value={2}>2 跳</option>
            </select>
          </label>
        </div>
      </section>

      <section className="graph-scene" ref={sceneRef}>
        <div className="relation-filters">
          {relationFilters.map((label) => (
            <button
              key={label}
              type="button"
              className={activeRelations.includes(label) ? "relation-filter active" : "relation-filter"}
              onClick={() => switchRelation(label)}
            >
              {relationLabel(label)}
            </button>
          ))}
        </div>
        {hasWebGL ? (
          <ThreeKnowledgeGraph
            graphData={graphData}
            graphFocus={graphFocus}
            graphSize={graphSize}
            onSelect={(node) => {
              setSelectedNode(node);
              setGraphFocus(node.name);
            }}
          />
        ) : (
          <KnowledgeGraphFallback
            graph={{ nodes: graphData.nodes, edges: graphData.links }}
            focus={graphFocus}
            onSelect={(node) => {
              setSelectedNode(node);
              setGraphFocus(node.name);
            }}
          />
        )}
        <div className="graph-legend">
          {["Formula", "Herb", "Symptom", "Effect", "Source"].map((label) => (
            <span key={label}><i style={{ background: entityColor(label) }} />{entityLabel(label)}</span>
          ))}
        </div>
      </section>

      <aside className="graph-inspector">
        <p className="eyebrow">实体详情</p>
        {selectedNode ? (
          <>
            <h2>{selectedNode.name}</h2>
            <span className={`entity-chip ${selectedNode.label}`}>{entityLabel(selectedNode.label)}</span>
            <dl>
              {Object.entries(selectedNode.properties || {}).map(([key, value]) => (
                <div key={key}>
                  <dt>{propertyLabel(key)}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
              {!Object.keys(selectedNode.properties || {}).length && (
                <div>
                  <dt>状态</dt>
                  <dd>该实体暂无更多属性，关系仍可用于证据链分析。</dd>
                </div>
              )}
            </dl>
            <Link className="primary-link" href={`/assistant?q=${encodeURIComponent(selectedNode.name)}`}>在问答中解释</Link>
            <Link className="secondary-link" href={`/search?q=${encodeURIComponent(selectedNode.name)}`}>返回搜索结果</Link>
          </>
        ) : (
          <p className="empty-note">点击图谱节点查看实体详情。</p>
        )}
        <div className="graph-state">
          <span><Layers3 size={14} />三维力导向</span>
          <span><Activity size={14} />关系高亮</span>
          <span><Network size={14} />节点聚焦</span>
        </div>
      </aside>
    </div>
  );
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
      setRenderError(error instanceof Error ? error.message : "三维图谱初始化失败");
    }
    return () => cleanup();
  }, [graphData, graphFocus, graphSize.width, graphSize.height, resetKey, onSelect]);

  if (!graphData.nodes.length) {
    return <div className="kg-canvas empty">暂无图谱数据</div>;
  }

  return (
    <div className="three-graph-mount" ref={mountRef} aria-label="三维知识图谱">
      {renderError && <div className="kg-canvas empty">三维图谱初始化失败：{renderError}</div>}
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

function LoginScreen({ onAuthed, status }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = mode === "login" ? await login(username, password) : await register(username, password);
      await onAuthed({ token: data.token, user: data.user });
    } catch (err) {
      setError(mode === "login" ? "登录失败，请检查账号密码。" : "注册失败，用户名可能已存在。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <div className="ambient-image" />
      <div className="paper-wash" />
      <section className="login-panel">
        <p className="eyebrow">中医知识图谱</p>
        <h1>登录中医图谱工作台</h1>
        <p className="login-copy">以图谱证据、推理链和历史对话辅助方药知识探索。</p>
        <form onSubmit={submit} className="login-form">
          <label>
            <span>用户名</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>密码</span>
            <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </label>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" disabled={loading}>{loading ? "处理中" : mode === "login" ? "登录" : "注册"}</button>
        </form>
        <button className="mode-switch" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "没有账号？创建一个" : "已有账号？返回登录"}
        </button>
        {status && <p className="login-status">{status}</p>}
      </section>
    </main>
  );
}

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
  if (!graph.nodes.length) {
    return <div className="kg-canvas empty">暂无图谱数据</div>;
  }
  return (
    <div className="kg-canvas">
      <svg viewBox="0 0 720 460" role="img" aria-label="知识图谱关联">
        {graph.edges.map((edge) => {
          const source = layout[edge.source];
          const target = layout[edge.target];
          if (!source || !target) return null;
          return (
            <g key={edge.id}>
              <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} />
              <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2}>{relationLabel(edge.label)}</text>
            </g>
          );
        })}
      </svg>
      {graph.nodes.map((node) => {
        const point = layout[node.id];
        if (!point) return null;
        return (
          <button
            type="button"
            className={`kg-node ${node.label} ${node.name === focus ? "focused" : ""}`}
            key={node.id}
            style={{ left: `${point.x / 7.2}%`, top: `${point.y / 4.6}%` }}
            onClick={() => onSelect(node)}
          >
            <span>{node.name}</span>
            <small>{entityLabel(node.label)}</small>
          </button>
        );
      })}
    </div>
  );
}

function FormattedMessage({ content }) {
  if (!content) {
    return <div className="formatted-answer muted">正在整理回答...</div>;
  }
  const normalized = content
    .replace(/\s*###\s*/g, "\n\n### ")
    .replace(/\s+-\s+\*\*/g, "\n- **")
    .replace(/\s+-\s+/g, "\n- ");
  const lines = normalized.split(/\n+/).map((line) => line.trim()).filter(Boolean);

  return (
    <div className="formatted-answer">
      {lines.map((line, index) => {
        if (line.startsWith("### ")) {
          return <h3 key={index}>{cleanMarkdown(line.replace(/^###\s*/, ""))}</h3>;
        }
        if (/^[-*]\s+/.test(line)) {
          return <p className="answer-list-item" key={index}>{cleanMarkdown(line.replace(/^[-*]\s+/, ""))}</p>;
        }
        return <p key={index}>{cleanMarkdown(line)}</p>;
      })}
    </div>
  );
}

function activeTitle(view) {
  return {
    assistant: "中医知识图谱问答",
    search: "方药与药材检索",
    graph: "知识图谱关联",
  }[view];
}

function appendToLastAssistant(messages, chunk) {
  const next = [...messages];
  const lastIndex = next.length - 1;
  if (lastIndex >= 0 && next[lastIndex].role === "assistant") {
    next[lastIndex] = { ...next[lastIndex], content: `${next[lastIndex].content}${chunk}` };
    return next;
  }
  return [...next, { role: "assistant", content: chunk }];
}

function appendThoughtChunk(thoughts, chunk) {
  const raw = String(chunk ?? "");
  if (!raw) return thoughts;

  const compact = raw.trim();
  if (!compact) return thoughts;

  const looksLikeCypherOrJsonChunk = /^(["{}[\]:,]|MATCH\b|MAT$|CH$|WHERE\b|RETURN\b|WITH\b|OPTIONAL\b|CALL\b|query\b|params\b|cypher\b)/i.test(compact)
    || /^[A-Za-z0-9_.$:`'"\-\s()[\]{}=<>*,]+$/.test(compact);
  const isMilestone = /^(开始|完成|正在|进入|识别|抽取|匹配|生成|执行|校验|查询|回答|意图|实体|图谱|Cypher|CYPHER)/.test(compact)
    && compact.length > 6
    && !looksLikeCypherOrJsonChunk;
  const lastThought = thoughts[thoughts.length - 1] || "";
  const shouldAppend = looksLikeCypherOrJsonChunk
    && thoughts.length > 0
    && !isMilestone
    && isStreamThoughtLine(lastThought);

  if (shouldAppend) {
    const next = [...thoughts];
    const glue = needsThoughtSpace(lastThought, raw) ? " " : "";
    next[next.length - 1] = `${lastThought}${glue}${raw}`.replace(/\s{3,}/g, " ");
    return next;
  }

  return [...thoughts, compact];
}

function isStreamThoughtLine(text) {
  return /[{[\]}":,]|MATCH|WHERE|RETURN|WITH|OPTIONAL|CALL|query|params|cypher/i.test(String(text || ""));
}

function needsThoughtSpace(left, right) {
  if (!left || !right) return false;
  return /[A-Za-z0-9_\u4e00-\u9fa5]$/.test(left) && /^[A-Za-z0-9_\u4e00-\u9fa5]/.test(right);
}

function cleanMarkdown(text) {
  return text.replace(/\*\*/g, "").trim();
}

function countRelated(item) {
  const related = item.properties?.related;
  if (!related) return 0;
  return String(related).split("；").filter(Boolean).length;
}

function propertyLabel(key) {
  return {
    source: "出处",
    ingredients: "组成",
    effect: "功效",
    usage: "用法",
    taboo: "禁忌",
    indication: "主治",
    category: "分类",
    nature: "药性",
    flavor: "药味",
    meridian: "归经",
    dosage: "剂量",
    preparation: "炮制",
    alias: "别名",
    description: "简介",
    related: "关联信息",
    label: "类型",
  }[key] || key;
}

function entityLabel(label) {
  return {
    Formula: "方剂",
    Herb: "药材",
    Symptom: "症状",
    Disease: "疾病",
    Effect: "功效",
    Source: "出处",
    FormulaCategory: "方剂分类",
    HerbNature: "药性",
    HerbFlavor: "药味",
    Meridian: "归经",
    Entity: "实体",
  }[label] || label;
}

function entityFilterToBackendLabel(filter) {
  return {
    全部: "Formula,Herb",
    方剂: "Formula",
    药材: "Herb",
  }[filter] || "Formula,Herb";
}

function relationLabel(label) {
  return {
    HAS_INGREDIENT: "组成",
    ALLEVIATES_SYMPTOM: "缓解症状",
    TREATS_DISEASE: "治疗疾病",
    HAS_EFFECT: "具有功效",
    BELONGS_TO_CATEGORY: "属于分类",
    FROM_SOURCE: "出自",
    HAS_NATURE: "药性",
    HAS_FLAVOR: "药味",
    ENTERS_MERIDIAN: "归经",
    RELATED_TO: "相关",
  }[label] || String(label || "").replaceAll("_", "");
}

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
