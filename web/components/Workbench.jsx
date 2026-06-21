"use client";

import * as THREE from "three";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  Brain,
  ChevronRight,
  CheckCircle2,
  Clock,
  Database,
  Eye,
  EyeOff,
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
  Sparkles,
  Trash2,
  UploadCloud,
  UserPlus,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  adminLogin,
  cancelChatJob,
  clearThreadMessages,
  createAdminUser,
  createChatThread,
  deleteAdminUser,
  deleteChatThread,
  deleteKnowledge,
  extractKnowledge,
  fetchAdminUsers,
  fetchChatJob,
  fetchChatThreads,
  fetchKnowledgeImports,
  fetchKnowledgeGraph,
  fetchMe,
  fetchSearchResults,
  formatShanghaiDateTime,
  fetchThreadMessages,
  importKnowledge,
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

const emptyKnowledgeDraft = {
  herb: {
    name: "",
    label: "Formula",
    source: "",
    ingredients: "",
    origin: "",
    property_flavor: "",
    effect: "",
    indication: "",
    meridian: "",
    dosage: "",
    usage: "",
    taboo: "",
    note: "",
  },
  relations: [],
};

function cloneKnowledgeDraft(draft = emptyKnowledgeDraft) {
  return {
    herb: { ...emptyKnowledgeDraft.herb, ...(draft.herb || {}) },
    relations: Array.isArray(draft.relations) ? draft.relations.map((relation) => ({ ...relation })) : [],
  };
}

const knowledgeRuntimeStore = {
  busy: false,
  deleteName: "",
  draft: cloneKnowledgeDraft(),
  file: null,
  jobId: "",
  previewGraph: { nodes: [], edges: [] },
  status: "等待录入药材资料",
  text: "",
};

function snapshotKnowledgeRuntime() {
  return {
    busy: knowledgeRuntimeStore.busy,
    deleteName: knowledgeRuntimeStore.deleteName,
    draft: cloneKnowledgeDraft(knowledgeRuntimeStore.draft),
    file: knowledgeRuntimeStore.file,
    jobId: knowledgeRuntimeStore.jobId,
    previewGraph: {
      nodes: [...(knowledgeRuntimeStore.previewGraph.nodes || [])],
      edges: [...(knowledgeRuntimeStore.previewGraph.edges || [])],
    },
    status: knowledgeRuntimeStore.status,
    text: knowledgeRuntimeStore.text,
  };
}

function patchKnowledgeRuntime(patch) {
  Object.assign(knowledgeRuntimeStore, patch);
}

const relationTypeLabels = {
  HAS_INGREDIENT: "组成",
  HAS_EFFECT: "功效",
  TREATS_DISEASE: "治疗疾病",
  ALLEVIATES_SYMPTOM: "缓解症状",
  FROM_SOURCE: "出处",
};

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
const chatStreamErrorMessage = "回答生成中断，请稍后重试。";

function cloneDefaultMessages() {
  return defaultMessages.map((message) => ({ ...message }));
}

function createThreadRuntimeState(messages = cloneDefaultMessages(), loaded = false) {
  return {
    abortController: null,
    activeStreamToken: null,
    draft: "",
    jobId: "",
    loaded,
    loading: false,
    messages,
    progress: 0,
    requestId: 0,
    status: "idle",
    thoughts: [],
    unread: false,
  };
}

function createChatRuntime() {
  return {
    activeThreadId: "",
    activeView: "assistant",
    pendingDraft: "",
    subscribers: new Set(),
    threads: {},
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
  const activeState = runtime.activeThreadId ? runtime.threads[runtime.activeThreadId] : null;
  const visibleState = activeState || createThreadRuntimeState();
  return {
    activeThreadId: runtime.activeThreadId,
    loading: visibleState.loading,
    messages: visibleState.messages,
    prompt: activeState ? (visibleState.draft || "") : (runtime.pendingDraft || ""),
    progress: visibleState.progress,
    threadStates: { ...runtime.threads },
    thoughts: visibleState.thoughts,
    unread: Object.values(runtime.threads).some((state) => state.unread),
  };
}

function notifyChatRuntime(runtime) {
  const snapshot = snapshotChatRuntime(runtime);
  runtime.subscribers.forEach((subscriber) => subscriber(snapshot));
}

function patchChatRuntime(runtime, patch) {
  Object.assign(runtime, patch);
  notifyChatRuntime(runtime);
}

function getThreadRuntimeState(runtime, threadId) {
  if (!threadId) return createThreadRuntimeState();
  if (!runtime.threads[threadId]) {
    runtime.threads[threadId] = createThreadRuntimeState();
  }
  return runtime.threads[threadId];
}

function patchThreadRuntime(runtime, threadId, patch) {
  if (!threadId) return;
  Object.assign(getThreadRuntimeState(runtime, threadId), patch);
  notifyChatRuntime(runtime);
}

function resetChatRuntime(runtime) {
  Object.values(runtime.threads).forEach((state) => state.abortController?.abort());
  patchChatRuntime(runtime, {
    activeThreadId: "",
    pendingDraft: "",
    threads: {},
  });
}

function interruptThreadRuntime(runtime, threadId) {
  const state = runtime.threads[threadId];
  if (!state) return null;
  state.abortController?.abort();
  state.abortController = null;
  state.activeStreamToken = null;
  state.loading = false;
  state.status = "cancelled";
  state.requestId += 1;
  notifyChatRuntime(runtime);
  return state.jobId || null;
}

function clampProgress(value, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.max(0, Math.min(100, Math.round(number)));
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
  const knowledgeRuntimeSnapshot = snapshotKnowledgeRuntime();
  const [auth, setAuth] = useState(() => ({ token: authRuntime.token, user: authRuntime.user }));
  const runtimeKey = useMemo(() => getRuntimeKey(auth), [auth.token, auth.user?.id, auth.user?.role, auth.user?.username]);
  const [savedSession, setSavedSession] = useState(null);
  const [restoring, setRestoring] = useState(() => !authRuntime.token);
  const [silentRestoring, setSilentRestoring] = useState(false);
  const [activeView, setActiveView] = useState(initialView);
  const [status, setStatus] = useState(() => (authRuntime.token ? "登录成功" : "等待登录"));
  const [messages, setMessages] = useState(runtimeSnapshot.messages);
  const [prompt, setPrompt] = useState(runtimeSnapshot.prompt);
  const [thoughts, setThoughts] = useState(runtimeSnapshot.thoughts);
  const [thinkingProgress, setThinkingProgress] = useState(runtimeSnapshot.progress);
  const [chatLoading, setChatLoading] = useState(runtimeSnapshot.loading);
  const [assistantHasUnread, setAssistantHasUnread] = useState(runtimeSnapshot.unread);
  const [threadStates, setThreadStates] = useState(runtimeSnapshot.threadStates);
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
  const [adminTab, setAdminTab] = useState("knowledge");
  const [knowledgeText, setKnowledgeText] = useState(knowledgeRuntimeSnapshot.text);
  const [knowledgeFile, setKnowledgeFile] = useState(knowledgeRuntimeSnapshot.file);
  const [knowledgeDraft, setKnowledgeDraft] = useState(knowledgeRuntimeSnapshot.draft);
  const [knowledgeJobId, setKnowledgeJobId] = useState(knowledgeRuntimeSnapshot.jobId);
  const [knowledgeDeleteName, setKnowledgeDeleteName] = useState(knowledgeRuntimeSnapshot.deleteName);
  const [knowledgePreviewGraph, setKnowledgePreviewGraph] = useState(knowledgeRuntimeSnapshot.previewGraph);
  const [knowledgeImports, setKnowledgeImports] = useState([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState(knowledgeRuntimeSnapshot.status);
  const [knowledgeBusy, setKnowledgeBusy] = useState(knowledgeRuntimeSnapshot.busy);

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
      setPrompt(snapshot.prompt);
      setThoughts(snapshot.thoughts);
      setThinkingProgress(snapshot.progress);
      setChatLoading(snapshot.loading);
      setAssistantHasUnread(snapshot.unread);
      setActiveThreadId(snapshot.activeThreadId);
      setThreadStates(snapshot.threadStates);
    });
  }, [runtimeKey]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    runtime.activeView = activeView;
    if (activeView === "assistant" && runtime.activeThreadId) {
      const state = runtime.threads[runtime.activeThreadId];
      if (state?.unread) {
        patchThreadRuntime(runtime, runtime.activeThreadId, { unread: false });
      } else {
        notifyChatRuntime(runtime);
      }
    }
  }, [activeView]);

  useEffect(() => {
    if (!auth.token) return;
    refreshUserContext(auth.token);
  }, [auth.token]);

  useEffect(() => {
    if (!auth.token || auth.user?.role !== "admin") return;
    refreshAdminUsers();
    refreshKnowledgeImports();
  }, [auth.token, auth.user?.role]);

  useEffect(() => {
    patchKnowledgeRuntime({
      busy: knowledgeBusy,
      deleteName: knowledgeDeleteName,
      draft: knowledgeDraft,
      file: knowledgeFile,
      jobId: knowledgeJobId,
      previewGraph: knowledgePreviewGraph,
      status: knowledgeStatus,
      text: knowledgeText,
    });
  }, [knowledgeBusy, knowledgeDeleteName, knowledgeDraft, knowledgeFile, knowledgeJobId, knowledgePreviewGraph, knowledgeStatus, knowledgeText]);

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

  async function refreshKnowledgeImports() {
    if (!auth.token || auth.user?.role !== "admin") return;
    try {
      const data = await fetchKnowledgeImports(auth.token, 80);
      setKnowledgeImports(data.items || []);
    } catch (error) {
      setKnowledgeStatus("操作记录读取失败");
    }
  }

  function applyKnowledgeState(patch) {
    patchKnowledgeRuntime(patch);
    if (Object.prototype.hasOwnProperty.call(patch, "text")) setKnowledgeText(patch.text);
    if (Object.prototype.hasOwnProperty.call(patch, "file")) setKnowledgeFile(patch.file);
    if (Object.prototype.hasOwnProperty.call(patch, "draft")) setKnowledgeDraft(cloneKnowledgeDraft(patch.draft));
    if (Object.prototype.hasOwnProperty.call(patch, "jobId")) setKnowledgeJobId(patch.jobId);
    if (Object.prototype.hasOwnProperty.call(patch, "deleteName")) setKnowledgeDeleteName(patch.deleteName);
    if (Object.prototype.hasOwnProperty.call(patch, "previewGraph")) setKnowledgePreviewGraph(patch.previewGraph);
    if (Object.prototype.hasOwnProperty.call(patch, "status")) setKnowledgeStatus(patch.status);
    if (Object.prototype.hasOwnProperty.call(patch, "busy")) setKnowledgeBusy(patch.busy);
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
    const nextView = data.user?.role === "admin" ? "admin" : "assistant";
    setActiveView(nextView);
    router.push(nextView === "admin" ? "/admin" : "/assistant");
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
      setAdminStatus(error?.message ? `创建失败：${error.message}` : "创建失败，请检查输入后重试");
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

  async function handleExtractKnowledge(event) {
    event.preventDefault();
    if (!knowledgeText.trim() && !knowledgeFile) {
      applyKnowledgeState({ status: "请先输入文本或上传文档" });
      return;
    }
    applyKnowledgeState({ busy: true, status: "AI 正在识别方药知识并生成图谱预览" });
    try {
      const data = await extractKnowledge(auth.token, { text: knowledgeText, file: knowledgeFile });
      const nextDraft = normalizeKnowledgeDraft(data.extracted);
      applyKnowledgeState({
        draft: nextDraft,
        jobId: "",
        previewGraph: data.preview_graph?.nodes?.length ? data.preview_graph : buildPreviewGraphFromDraft(data.extracted),
        status: "识别完成，右侧已生成图谱预览；确认后才会正式入库并生成记录",
      });
    } catch (error) {
      applyKnowledgeState({ previewGraph: { nodes: [], edges: [] }, status: "识别失败：" + (error?.message || "请检查资料格式") });
    } finally {
      applyKnowledgeState({ busy: false });
    }
  }

  async function handleImportKnowledge() {
    if (!knowledgeDraft.herb.name.trim()) {
      applyKnowledgeState({ status: "请先填写药材名称" });
      return;
    }
    applyKnowledgeState({ busy: true, status: "正在写入 Neo4j 知识图谱，并增量更新实体索引" });
    try {
      const data = await importKnowledge(auth.token, knowledgeJobId, knowledgeDraft);
      const entityName = data.job?.entity_name || knowledgeDraft.herb.name;
      if (data.job) {
        setKnowledgeImports((items) => [data.job, ...items.filter((item) => item.id !== data.job.id)]);
      }
      applyKnowledgeState({
        file: null,
        jobId: "",
        status: `已确认导入：${entityName}，正式记录已生成；实体索引已增量更新`,
        text: "",
      });
      await loadKnowledgePreviewGraph(entityName);
      await refreshKnowledgeImports();
    } catch (error) {
      applyKnowledgeState({ status: "导入失败：" + (error?.message || "请检查 Neo4j 或抽取字段") });
    } finally {
      applyKnowledgeState({ busy: false });
    }
  }

  async function handleDeleteKnowledge() {
    const cleanName = knowledgeDeleteName.trim();
    if (!cleanName) {
      applyKnowledgeState({ status: "请输入要删除的方药名称" });
      return;
    }
    applyKnowledgeState({ busy: true, status: "正在从 Neo4j 知识图谱删除方药，并同步屏蔽实体索引映射" });
    try {
      const deletedData = await deleteKnowledge(auth.token, cleanName);
      if (deletedData.job) {
        setKnowledgeImports((items) => [deletedData.job, ...items.filter((item) => item.id !== deletedData.job.id)]);
      }
      applyKnowledgeState({
        deleteName: "",
        draft: cloneKnowledgeDraft(),
        previewGraph: { nodes: [], edges: [] },
        status: `已删除方药：${cleanName}，正式删除记录已生成；实体索引映射已同步屏蔽`,
      });
      await refreshKnowledgeImports();
      if (graphFocus === cleanName) {
        setGraph({ nodes: [], edges: [] });
      }
    } catch (error) {
      applyKnowledgeState({ status: "删除失败：" + (error?.message || "未找到该方药") });
    } finally {
      applyKnowledgeState({ busy: false });
    }
  }

  async function loadKnowledgePreviewGraph(entityName) {
    const cleanName = String(entityName || "").trim();
    if (!cleanName) {
      applyKnowledgeState({ previewGraph: { nodes: [], edges: [] } });
      return;
    }
    try {
      const nextGraph = await fetchKnowledgeGraph(cleanName, { depth: 2, limit: 80 });
      applyKnowledgeState({ previewGraph: nextGraph.nodes?.length ? nextGraph : buildPreviewGraphFromDraft(knowledgeDraft) });
    } catch (error) {
      applyKnowledgeState({ previewGraph: buildPreviewGraphFromDraft(knowledgeDraft) });
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
    if (!threadId) return;
    const runtime = runtimeRef.current;
    setActiveThreadId(threadId);
    setStatus("正在读取历史对话");
    runtime.activeThreadId = threadId;
    const existingState = runtime.threads[threadId];
    if (existingState?.loading || existingState?.loaded) {
      patchThreadRuntime(runtime, threadId, { unread: false });
      setStatus(existingState.loading ? "已回到正在生成的对话" : "历史对话已载入");
      return;
    }
    try {
      const data = await fetchThreadMessages(auth.token, threadId, 100);
      patchThreadRuntime(runtime, threadId, {
        loaded: true,
        messages: data.items?.length ? data.items.map(({ role, content }) => ({ role, content })) : cloneDefaultMessages(),
        progress: 0,
        status: "idle",
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
      const runtime = runtimeRef.current;
      runtime.activeThreadId = thread.id;
      runtime.pendingDraft = "";
      runtime.threads[thread.id] = createThreadRuntimeState(cloneDefaultMessages(), true);
      notifyChatRuntime(runtime);
      setStatus("已创建新对话");
    } catch (error) {
      setStatus("新建对话失败");
    }
  }

  async function handleClearCurrentThread() {
    const runtime = runtimeRef.current;
    const currentState = runtime.threads[activeThreadId];
    const jobId = currentState?.loading ? interruptThreadRuntime(runtime, activeThreadId) : null;
    if (jobId) {
      cancelChatJob(auth.token, jobId).catch(() => {});
    }
    if (activeThreadId) {
      patchThreadRuntime(runtime, activeThreadId, {
        abortController: null,
        activeStreamToken: null,
        draft: "",
        jobId: "",
        loaded: true,
        loading: false,
        messages: cloneDefaultMessages(),
        progress: 0,
        status: "idle",
        thoughts: [],
        unread: false,
      });
    }
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
    if (!threadId) return;
    const runtime = runtimeRef.current;
    const deletingState = runtime.threads[threadId];
    const jobId = deletingState?.loading ? interruptThreadRuntime(runtime, threadId) : null;
    if (jobId) {
      cancelChatJob(auth.token, jobId).catch(() => {});
    }
    try {
      await deleteChatThread(auth.token, threadId);
      const nextThreads = threads.filter((thread) => thread.id !== threadId);
      setThreads(nextThreads);
      delete runtime.threads[threadId];
      if (threadId === activeThreadId) {
        setActiveThreadId("");
        runtime.activeThreadId = "";
      }
      notifyChatRuntime(runtime);
      setStatus("历史对话已删除");
    } catch (error) {
      setStatus("删除历史对话失败");
    }
  }

  async function ensureThreadForPrompt(text) {
    const runtime = runtimeRef.current;
    if (runtime.activeThreadId) return runtime.activeThreadId;
    const title = text.slice(0, 28);
    const data = await createChatThread(auth.token, title, graphFocus);
    const thread = data.thread;
    setThreads((items) => [thread, ...items]);
    setActiveThreadId(thread.id);
    runtime.activeThreadId = thread.id;
    runtime.pendingDraft = "";
    runtime.threads[thread.id] = createThreadRuntimeState(cloneDefaultMessages(), true);
    notifyChatRuntime(runtime);
    return thread.id;
  }

  function handlePromptChange(value) {
    setPrompt(value);
    const runtime = runtimeRef.current;
    const threadId = runtime.activeThreadId;
    if (threadId) {
      patchThreadRuntime(runtime, threadId, { draft: value });
    } else {
      runtime.pendingDraft = value;
      notifyChatRuntime(runtime);
    }
  }

  async function handleChat(event) {
    event.preventDefault();
    const text = prompt.trim();
    const runtime = runtimeRef.current;
    const requestToken = auth.token;
    if (!text) return;

    let activeStreamThreadId = "";

    try {
      const threadId = await ensureThreadForPrompt(text);
      activeStreamThreadId = threadId;
      const wasThreadRunning = Boolean(runtime.threads[threadId]?.loading);
      const previousJobId = wasThreadRunning ? interruptThreadRuntime(runtime, threadId) : null;
      if (previousJobId) {
        cancelChatJob(auth.token, previousJobId).catch(() => {});
      }

      const abortController = new AbortController();
      const streamToken = Symbol("chat-stream");
      const threadState = getThreadRuntimeState(runtime, threadId);
      const requestId = threadState.requestId + 1;
      let streamMessages = [
        ...(wasThreadRunning ? markInterruptedAssistant(threadState.messages) : threadState.messages),
        { role: "user", content: text },
        { role: "assistant", content: "" },
      ];
      let streamThoughts = [];
      let streamProgress = 8;
      const isCurrentRequest = () => {
        const state = runtime.threads[threadId];
        return Boolean(
          state &&
          state.requestId === requestId &&
          state.activeStreamToken === streamToken &&
          !abortController.signal.aborted
        );
      };
      const streamIsVisible = () => runtime.activeThreadId === threadId;

      patchThreadRuntime(runtime, threadId, {
        abortController,
        activeStreamToken: streamToken,
        draft: "",
        jobId: "",
        loaded: true,
        loading: true,
        messages: streamMessages,
        progress: streamProgress,
        requestId,
        status: "running",
        thoughts: streamThoughts,
        unread: false,
      });
      setPrompt("");
      setStatus("模型正在流式回答");

      await postChatStream(
        text,
        auth.token,
        (eventMessage) => {
          if (!isCurrentRequest()) return;
          const eventThreadId = eventMessage.thread_id || threadId;
          if (eventThreadId !== threadId) return;
          const nextJobId = eventMessage.job_id || runtime.threads[threadId]?.jobId || "";
          if (eventMessage.type === "think") {
            const nextThoughts = appendThoughtChunk(streamThoughts, eventMessage.msg || "");
            streamProgress = clampProgress(eventMessage.progress, streamProgress);
            if (nextThoughts !== streamThoughts) {
              streamThoughts = nextThoughts;
              patchThreadRuntime(runtime, threadId, {
                jobId: nextJobId,
                loading: true,
                progress: streamProgress,
                status: "running",
                thoughts: streamThoughts,
              });
            } else {
              patchThreadRuntime(runtime, threadId, { jobId: nextJobId, loading: true, progress: streamProgress, status: "running" });
            }
          }
          if (eventMessage.type === "stream") {
            streamProgress = clampProgress(eventMessage.progress, streamProgress);
            streamMessages = appendToLastAssistant(streamMessages, eventMessage.msg || "");
            patchThreadRuntime(runtime, threadId, {
              jobId: nextJobId,
              loading: true,
              messages: streamMessages,
              progress: streamProgress,
              status: "running",
              unread: false,
            });
          }
          if (eventMessage.type === "done") {
            streamProgress = clampProgress(eventMessage.progress, 100);
            patchThreadRuntime(runtime, threadId, {
              jobId: nextJobId,
              loading: false,
              progress: streamProgress,
              status: "done",
              unread: !streamIsVisible() || runtime.activeView !== "assistant",
            });
          }
          if (eventMessage.type === "error") {
            streamProgress = clampProgress(eventMessage.progress, 100);
            streamMessages = appendAssistantError(streamMessages, eventMessage.msg || chatStreamErrorMessage);
            patchThreadRuntime(runtime, threadId, {
              abortController: null,
              activeStreamToken: null,
              jobId: nextJobId,
              loading: false,
              messages: streamMessages,
              progress: streamProgress,
              status: "failed",
              unread: !streamIsVisible() || runtime.activeView !== "assistant",
            });
          }
        },
        { threadId, signal: abortController.signal, useJobEndpoint: true },
      );
      if (!isCurrentRequest()) return;
      if (authRuntime.token === requestToken) {
        await refreshUserContext(requestToken);
        setStatus("回答生成完成");
      }
      patchThreadRuntime(runtime, threadId, {
        abortController: null,
        activeStreamToken: null,
        loading: false,
        progress: 100,
        status: "done",
        unread: runtime.activeView !== "assistant" || runtime.activeThreadId !== threadId,
      });
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      const threadId = activeStreamThreadId;
      const state = threadId ? runtime.threads[threadId] : null;
      if (!state) return;
      let errorText = error?.message?.includes("后端问答任务接口不存在")
        ? "后端仍在运行旧版本，请重启 FastAPI 后端后再试。"
        : chatStreamErrorMessage;
      const failedJobId = state.jobId;
      if (failedJobId) {
        try {
          const data = await fetchChatJob(auth.token, failedJobId);
          if (data?.job?.error) {
            errorText = chatStreamErrorMessage;
          }
        } catch (jobError) {
          // Keep the local connection error when the job status cannot be loaded.
        }
      }
      const streamMessages = appendAssistantError(state.messages, errorText);
      patchThreadRuntime(runtime, threadId, {
        abortController: null,
        activeStreamToken: null,
        loading: false,
        messages: streamMessages,
        status: "failed",
        unread: runtime.activeView !== "assistant" || runtime.activeThreadId !== threadId,
      });
      if (authRuntime.token === requestToken) {
        setStatus("问答连接异常");
      }
    } finally {
      notifyChatRuntime(runtime);
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
            setPrompt={handlePromptChange}
            onSubmit={handleChat}
            loading={chatLoading}
            thoughts={thoughts}
            thinkingProgress={thinkingProgress}
            threads={threads}
            activeThreadId={activeThreadId}
            threadStates={threadStates}
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
            activeTab={adminTab}
            setActiveTab={setAdminTab}
            knowledgeText={knowledgeText}
            setKnowledgeText={setKnowledgeText}
            knowledgeFile={knowledgeFile}
            setKnowledgeFile={setKnowledgeFile}
            knowledgeDraft={knowledgeDraft}
            knowledgePreviewGraph={knowledgePreviewGraph}
            knowledgeStatus={knowledgeStatus}
            knowledgeBusy={knowledgeBusy}
            hasWebGL={hasWebGL}
            deleteName={knowledgeDeleteName}
            setDeleteName={setKnowledgeDeleteName}
            knowledgeImports={knowledgeImports}
            onExtractKnowledge={handleExtractKnowledge}
            onImportKnowledge={handleImportKnowledge}
            onDeleteKnowledge={handleDeleteKnowledge}
            onRefreshKnowledgeImports={refreshKnowledgeImports}
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
    ...(user?.role === "admin" ? [{ id: "admin", label: "后台", icon: ShieldCheck, href: "/admin" }] : []),
  ];
  return <aside className="sidebar"><div className="brand"><span className="brand-mark"><b>{"药图"}</b></span><strong>{"中医知识图谱"}</strong><span>{user?.username || "未知用户"}</span></div><nav className="tabs" aria-label="主导航">{tabs.map((tab) => { const Icon = tab.icon; const href = tab.id === "graph" && query.trim() ? tab.href + "?q=" + encodeURIComponent(query.trim()) : tab.href; return <Link key={tab.id} className={["tab", activeView === tab.id ? "active" : "", tab.id === "assistant" && assistantHasUnread ? "has-unread" : ""].filter(Boolean).join(" ")} href={href} onClick={() => onNavigate(tab.id)} title={tab.label}><Icon size={18} /><span>{tab.label}</span></Link>; })}</nav><button className="logout-button" type="button" onClick={onLogout} title="退出登录"><LogOut size={17} /><span>{"退出"}</span></button></aside>;
}

function Topbar({ activeView, status, restoring, graphFocus, graph }) {
  return <header className="topbar"><div className="title-block"><h1>{activeTitle(activeView)}</h1>{restoring && <div className="status-row"><StatusPill icon={Clock} label="正在校验" tone="warm" /></div>}</div></header>;
}

function StatusPill({ icon: Icon, label, tone = "normal" }) { return <span className={"status-pill " + tone}><Icon size={14} />{label}</span>; }

function AssistantPanel(props) {
  const { messages, prompt, setPrompt, onSubmit, loading, thoughts, thinkingProgress, threads, activeThreadId, threadStates, onSelectThread, onNewThread, onClearCurrentThread, onDeleteThread } = props;
  const activeThread = threads.find((thread) => thread.id === activeThreadId);
  const reasoningSteps = buildReasoningSteps(thoughts, thinkingProgress, loading);
  return (
    <div className="assistant-layout">
      <section className="history-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">{"对话"}</p><h2>{"历史记录"}</h2></div>
          <button className="icon-button" type="button" onClick={onNewThread} title="新建对话"><Plus size={17} /></button>
        </div>
        <div className="thread-list">
          {threads.map((thread) => {
            const state = threadStates?.[thread.id];
            const stateLabel = threadStateLabel(state, thread.message_count);
            return (
              <div key={thread.id} className={["thread-item", thread.id === activeThreadId ? "active" : "", state?.unread ? "unread" : "", state?.loading ? "running" : "", state?.status === "failed" ? "failed" : ""].filter(Boolean).join(" ")}>
                <button type="button" className="thread-main" onClick={() => onSelectThread(thread.id)}>
                  <strong>{thread.title || "未命名对话"}</strong>
                  <span>{thread.message_count} {"条 · "}{stateLabel}</span>
                </button>
                <button className="thread-delete" type="button" onClick={() => onDeleteThread(thread.id)} title="删除对话"><Trash2 size={15} /></button>
              </div>
            );
          })}
          {!threads.length && <p className="empty-note">{"暂无历史对话，开始一次方药探索吧。"}</p>}
        </div>
      </section>
      <section className="chat-surface">
        <div className="history-strip">
          <span><History size={14} />{activeThread?.title || "当前对话"}</span>
          <span><Brain size={14} />{loading ? "正在思考" : "就绪"}</span>
          <button type="button" onClick={onClearCurrentThread}>{"清空当前"}</button>
        </div>
        <div className="message-list">
          {messages.map((message, index) => (
            <article key={message.role + "-" + index} className={["message-row", message.role].join(" ")}>
              <div className="message-cluster">
                <span>{message.role === "assistant" ? "问" : "我"}</span>
                <FormattedMessage content={message.content} />
              </div>
            </article>
          ))}
        </div>
        <form className="composer" onSubmit={onSubmit}>
          <input value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={loading ? "可继续输入新问题，发送后会打断当前思考" : "请输入方剂、药材或症状问题"} />
          <button type="submit" title={loading ? "打断并发送" : "发送"}><Send size={18} /></button>
        </form>
      </section>
      <section className="thinking-panel strong">
        <div className="panel-heading">
          <div><p className="eyebrow">{"推理"}</p><h2>{"推理轨迹"}</h2></div>
          <span className="progress-number">{thinkingProgress}%</span>
        </div>
        <div className="thinking-bar"><span style={{ width: String(thinkingProgress) + "%" }} /></div>
        <div className="reasoning-steps">
          {reasoningSteps.map((step) => (
            <div key={step.label} className={["reasoning-step", step.status].filter(Boolean).join(" ")}>
              <span />
              <div><strong>{step.label}</strong><small>{step.text}</small></div>
            </div>
          ))}
        </div>
        <div className="thinking-log">
          {thoughts.map((thought, index) => <p key={thought + "-" + index}>{thought}</p>)}
          {!thoughts.length && <p>{"等待模型输出推理链路…"}</p>}
        </div>
      </section>
    </div>
  );
}

function buildReasoningSteps(thoughts, progress, loading) {
  const log = thoughts.join("\n");
  const done = progress >= 100 && !loading;
  const stages = [
    { label: "语义改写", start: ["开始生成语义转写"], complete: ["完成生成语义转写"] },
    { label: "实体抽取", start: ["开始从用户输入中抽取中医实体"], complete: ["完成从用户输入中抽取中医实体"] },
    { label: "图谱证据", start: ["开始匹配知识图谱中的实体", "开始生成Cypher查询语句"], complete: ["完成执行Cypher查询语句"] },
    { label: "回答生成", start: ["开始生成基于知识图谱的回答", "开始生成直接回答"], complete: ["完成生成基于知识图谱的回答", "完成生成直接回答"] },
  ];
  return stages.map((stage, index) => {
    const isComplete = done || stage.complete.some((item) => log.includes(item));
    const isActive = !isComplete && stage.start.some((item) => log.includes(item));
    if (isComplete) return { label: stage.label, status: "complete", text: "已完成" };
    if (isActive) return { label: stage.label, status: "active", text: "进行中" };
    if (index === 0 && loading) return { label: stage.label, status: "active", text: "进行中" };
    return { label: stage.label, status: "", text: "等待中" };
  });
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

const landingSpotlightRadius = 260;

function LandingRevealLayer({ image, cursorX, cursorY }) {
  const canvasRef = useRef(null);
  const revealRef = useRef(null);

  useEffect(() => {
    function resizeCanvas() {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.ceil(window.innerWidth * ratio);
      canvas.height = Math.ceil(window.innerHeight * ratio);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    return () => window.removeEventListener("resize", resizeCanvas);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const reveal = revealRef.current;
    if (!canvas || !reveal) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

    if (cursorX > -100 && cursorY > -100) {
      const gradient = ctx.createRadialGradient(cursorX, cursorY, 0, cursorX, cursorY, landingSpotlightRadius);
      gradient.addColorStop(0, "rgba(255,255,255,1)");
      gradient.addColorStop(0.4, "rgba(255,255,255,1)");
      gradient.addColorStop(0.6, "rgba(255,255,255,0.75)");
      gradient.addColorStop(0.75, "rgba(255,255,255,0.4)");
      gradient.addColorStop(0.88, "rgba(255,255,255,0.12)");
      gradient.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(cursorX, cursorY, landingSpotlightRadius, 0, Math.PI * 2);
      ctx.fill();
    }

    const mask = `url(${canvas.toDataURL()})`;
    reveal.style.maskImage = mask;
    reveal.style.webkitMaskImage = mask;
  }, [cursorX, cursorY]);

  return (
    <>
      <canvas ref={canvasRef} className="landing-reveal-canvas" aria-hidden="true" />
      <div
        ref={revealRef}
        className="landing-reveal-layer"
        aria-hidden="true"
        style={{ backgroundImage: `url(${image})` }}
      />
    </>
  );
}

function LoginScreenV2({ onAuthed, onContinue, savedSession, status }) {
  const [showLogin, setShowLogin] = useState(false);
  const [loginKind, setLoginKind] = useState("user");
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const landingRef = useRef(null);
  const loginRef = useRef(null);
  const landingMouse = useRef({ x: -999, y: -999 });
  const landingSmooth = useRef({ x: -999, y: -999 });
  const landingRafRef = useRef(0);
  const [landingCursor, setLandingCursor] = useState({ x: -999, y: -999 });
  const [focusedField, setFocusedField] = useState("");
  const isAdmin = loginKind === "admin";
  const authMode = isAdmin ? "admin" : mode === "register" ? "register" : "login";

  useEffect(() => {
    if (savedSession) {
      setShowLogin(true);
    }
  }, [savedSession]);

  useEffect(() => {
    if (isAdmin) setMode("login");
    setUsername("");
    setPassword("");
  }, [isAdmin]);

  useEffect(() => {
    if (showLogin) return undefined;

    function animateCursor() {
      landingSmooth.current.x += (landingMouse.current.x - landingSmooth.current.x) * 0.1;
      landingSmooth.current.y += (landingMouse.current.y - landingSmooth.current.y) * 0.1;
      setLandingCursor({ x: landingSmooth.current.x, y: landingSmooth.current.y });
      landingRafRef.current = requestAnimationFrame(animateCursor);
    }

    landingRafRef.current = requestAnimationFrame(animateCursor);
    return () => cancelAnimationFrame(landingRafRef.current);
  }, [showLogin]);

  function chooseAuthMode(nextMode) {
    setError("");
    if (nextMode === "admin") {
      setLoginKind("admin");
      setMode("login");
      setUsername("");
      setPassword("");
      return;
    }
    setLoginKind("user");
    setMode(nextMode === "register" ? "register" : "login");
    setUsername("");
    setPassword("");
  }

  async function submit(event) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const data = isAdmin ? await adminLogin(username, password) : mode === "login" ? await login(username, password) : await register(username, password);
      await onAuthed({ token: data.token, user: data.user });
    } catch (err) {
      const fallback = isAdmin ? "管理员登录失败，请检查输入后重试。" : mode === "login" ? "登录失败，请检查账号密码后重试。" : "注册失败，请检查输入后重试。";
      setError(err?.message || fallback);
    } finally { setLoading(false); }
  }

  function handleLandingPointerMove(event) {
    const element = landingRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
    const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    landingMouse.current = { x: event.clientX, y: event.clientY };
    element.style.setProperty("--mx", x.toFixed(3));
    element.style.setProperty("--my", y.toFixed(3));
    element.style.setProperty("--mouse-x", `${((event.clientX - rect.left) / rect.width) * 100}%`);
    element.style.setProperty("--mouse-y", `${((event.clientY - rect.top) / rect.height) * 100}%`);
  }

  function resetLandingPointer() {
    const element = landingRef.current;
    landingMouse.current = { x: -999, y: -999 };
    if (!element) return;
    element.style.setProperty("--mx", "0");
    element.style.setProperty("--my", "0");
    element.style.setProperty("--mouse-x", "50%");
    element.style.setProperty("--mouse-y", "50%");
  }

  function handleLoginPointerMove(event) {
    const element = loginRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
    const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    element.style.setProperty("--mx", x.toFixed(3));
    element.style.setProperty("--my", y.toFixed(3));
  }

  function resetLoginPointer() {
    const element = loginRef.current;
    if (!element) return;
    element.style.setProperty("--mx", "0");
    element.style.setProperty("--my", "0");
  }

  if (!showLogin) {
    return (
      <main className="landing-shell" ref={landingRef} onPointerMove={handleLandingPointerMove} onPointerLeave={resetLandingPointer}>
        <div className="landing-image-bg hero-zoom" />
        <LandingRevealLayer image="/images/workspace-tcm-vivid-bg.png" cursorX={landingCursor.x} cursorY={landingCursor.y} />
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
          <p className="hero-anim hero-fade" style={{ animationDelay: "0.18s" }}>{"药图"}</p>
          <h1>
            <span className="hero-anim hero-reveal" style={{ animationDelay: "0.25s" }}>{"药图"}</span>
          </h1>
          <strong className="hero-anim hero-fade" style={{ animationDelay: "0.68s" }}>{"方药知识 · 图谱证据 · 智能问答"}</strong>
        </section>
        <section className="landing-copy-left hero-anim hero-fade" style={{ animationDelay: "0.78s" }}>
          {"每一味药材都藏着性味、归经、功效与方剂之间的线索，沿着图谱脉络逐层显影。"}
        </section>
      </main>
    );
  }

  return (
    <main className={["login-shell", "login-shell-v2", focusedField ? "is-typing" : "", password ? "has-password" : "", passwordVisible ? "password-visible" : "password-hidden"].filter(Boolean).join(" ")} ref={loginRef} onPointerMove={handleLoginPointerMove} onPointerLeave={resetLoginPointer}>
      <div className="login-image-bg" />
      <div className="paper-wash" />
      <section className="login-creature-stage" aria-hidden="true">
        <div className="stage-brand"><span>{"药图"}</span><strong>{"中医知识图谱"}</strong></div>
        <div className="herb-creatures">
          <div className="creature creature-bottle">
            <i className="eye left" /><i className="eye right" /><span className="herb-stem" />
          </div>
          <div className="creature creature-cabinet">
            <i className="eye left" /><i className="eye right" /><span className="drawer one" /><span className="drawer two" />
          </div>
          <div className="creature creature-bowl">
            <i className="pupil left" /><i className="pupil right" />
          </div>
          <div className="creature creature-tea">
            <i className="pupil left" /><i className="pupil right" /><span className="mouth" />
          </div>
        </div>
      </section>
      <section className="login-panel login-panel-v2">
        <h1>{isAdmin ? "登录管理员" : mode === "register" ? "注册用户" : "登录用户"}</h1>
        <div className="login-kind-switch login-entry-switch" role="tablist" aria-label="登录与注册入口">
          <button type="button" className={authMode === "login" ? "active" : ""} onClick={() => chooseAuthMode("login")}>{"登录用户"}</button>
          <button type="button" className={authMode === "register" ? "active" : ""} onClick={() => chooseAuthMode("register")}>{"注册用户"}</button>
          <button type="button" className={authMode === "admin" ? "active" : ""} onClick={() => chooseAuthMode("admin")}>{"管理员登录"}</button>
        </div>
        {savedSession && <div className="session-card"><span>{"已检测到上次会话："}{savedSession.user?.username}</span><button type="button" onClick={() => onContinue(savedSession)}>{"继续进入"}</button></div>}
        <form onSubmit={submit} className="login-form">
          <label><span>{isAdmin ? "管理员账号" : "用户名"}</span><input value={username} onFocus={() => setFocusedField("username")} onBlur={() => setFocusedField("")} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
          <label><span>{"密码"}</span><div className="password-field"><input value={password} onFocus={() => setFocusedField("password")} onBlur={() => setFocusedField("")} onChange={(event) => setPassword(event.target.value)} type={passwordVisible ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} /><button type="button" className={passwordVisible ? "visible" : ""} onClick={() => setPasswordVisible((visible) => !visible)} title={passwordVisible ? "隐藏密码" : "显示密码"}>{passwordVisible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" disabled={loading}>{loading ? "处理中" : isAdmin ? "进入管理后台" : mode === "login" ? "登录" : "创建账号"}</button>
        </form>
      </section>
    </main>
  );
}

function AdminPanel({
  users,
  currentUser,
  form,
  setForm,
  status,
  onCreate,
  onDelete,
  onRefresh,
  activeTab,
  setActiveTab,
  knowledgeText,
  setKnowledgeText,
  knowledgeFile,
  setKnowledgeFile,
  knowledgeDraft,
  knowledgePreviewGraph,
  knowledgeStatus,
  knowledgeBusy,
  hasWebGL,
  deleteName,
  setDeleteName,
  knowledgeImports,
  onExtractKnowledge,
  onImportKnowledge,
  onDeleteKnowledge,
  onRefreshKnowledgeImports,
}) {
  const userCount = users.filter((user) => user.role !== "admin").length;
  const adminCount = users.filter((user) => user.role === "admin").length;
  const tabs = [
    { id: "knowledge", label: "知识入库", icon: Database },
    { id: "users", label: "用户管理", icon: Users },
    { id: "imports", label: "操作记录", icon: History },
  ];
  return (
    <div className="admin-layout admin-scroll-layout">
      <section className="admin-hero admin-knowledge-hero">
        <div>
          <p className="eyebrow">{"管理员后台"}</p>
          <h2>{activeTab === "users" ? "用户管理" : activeTab === "imports" ? "操作记录" : "知识入库"}</h2>
          <p>{"识别、确认导入或删除方药知识，并用正式记录追踪每一次图谱变更。"}</p>
        </div>
        <div className="admin-stats">
          <span><Database size={16} />{"图谱入库"}</span>
          <span><Users size={16} />{userCount} {"用户"}</span>
          <span><ShieldCheck size={16} />{adminCount} {"管理员"}</span>
        </div>
      </section>
      <nav className="admin-tabs" aria-label="管理员后台页签">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return <button key={tab.id} type="button" className={activeTab === tab.id ? "active" : ""} onClick={() => setActiveTab(tab.id)}><Icon size={16} />{tab.label}</button>;
        })}
      </nav>
      {activeTab === "users" && (
        <div className="admin-users-workspace">
          <section className="admin-create"><div className="panel-heading"><div><p className="eyebrow">{"创建账号"}</p><h2>{"新增用户"}</h2></div><UserPlus size={22} /></div><form className="admin-form" onSubmit={onCreate}><label><span>{"用户名"}</span><input value={form.username} onChange={(event) => setForm((item) => ({ ...item, username: event.target.value }))} /></label><label><span>{"初始密码"}</span><input type="password" value={form.password} onChange={(event) => setForm((item) => ({ ...item, password: event.target.value }))} /></label><label><span>{"角色"}</span><select value={form.role} onChange={(event) => setForm((item) => ({ ...item, role: event.target.value }))}><option value="user">{"普通用户"}</option><option value="admin">{"管理员"}</option></select></label><button type="submit">{"创建账号"}</button></form><p className="admin-status">{status}</p></section>
          <section className="admin-users"><div className="panel-heading"><div><p className="eyebrow">{"账号列表"}</p><h2 className="admin-users-title">{"用户列表"}</h2></div><button type="button" className="mode-switch compact" onClick={onRefresh}>{"刷新"}</button></div><div className="user-table">{users.map((user) => <article key={user.id} className="user-row"><div><strong>{user.username}</strong><span>{user.role === "admin" ? "管理员" : "普通用户"} {" · "}{user.message_count || 0}{" 条消息"}</span></div><small>{user.last_login_at ? "最近登录 " + formatShanghaiDateTime(user.last_login_at) : "尚未登录"}</small><button type="button" disabled={user.id === currentUser?.id} onClick={() => onDelete(user.id)}>{"删除"}</button></article>)}{!users.length && <p className="empty-note">{"暂无用户记录"}</p>}</div></section>
        </div>
      )}
      {activeTab === "knowledge" && (
        <KnowledgeImportPanel
          text={knowledgeText}
          setText={setKnowledgeText}
          file={knowledgeFile}
          setFile={setKnowledgeFile}
          draft={knowledgeDraft}
          previewGraph={knowledgePreviewGraph}
          status={knowledgeStatus}
          busy={knowledgeBusy}
          hasWebGL={hasWebGL}
          deleteName={deleteName}
          setDeleteName={setDeleteName}
          onExtract={onExtractKnowledge}
          onImport={onImportKnowledge}
          onDelete={onDeleteKnowledge}
        />
      )}
      {activeTab === "imports" && (
        <KnowledgeImportHistory imports={knowledgeImports} onRefresh={onRefreshKnowledgeImports} />
      )}
    </div>
  );
}

function KnowledgeImportPanel({ text, setText, file, setFile, draft, previewGraph, status, busy, hasWebGL, deleteName, setDeleteName, onExtract, onImport, onDelete }) {
  const entityName = draft.herb.name.trim();
  return (
    <form className="knowledge-import-workbench" onSubmit={onExtract}>
      <div className="knowledge-workbench-head">
        <div>
          <p className="eyebrow">{"知识入库"}</p>
          <h2>{"识别并导入方药"}</h2>
        </div>
        <Sparkles size={24} />
      </div>
      <div className="knowledge-journey"><span>{"输入"}</span><span>{"AI识别"}</span><span>{"图谱预览"}</span><span>{"确认入库"}</span></div>
      <div className="knowledge-unified-grid">
        <section className="knowledge-source-zone">
          <div className="knowledge-zone-title">
            <div><p className="eyebrow">{"输入"}</p><h3>{"资料来源"}</h3></div>
            <button type="submit" disabled={busy}>{busy ? "识别中" : "AI识别"}</button>
          </div>
          <label className="knowledge-textarea">
            <span>{"手动输入"}</span>
            <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="粘贴方剂或药材资料，例如方剂名称、出处、组成、功用、主治、用法等" />
          </label>
          <label className="knowledge-upload">
            <UploadCloud size={22} />
            <strong>{file?.name || "上传文档"}</strong>
            <span>{"TXT / MD / PDF / DOCX，20MB 内"}</span>
            <input type="file" accept=".txt,.txtx,.md,.pdf,.docx" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          </label>
          <div className="knowledge-delete-tool">
            <span>{"删除方药"}</span>
            <input
              value={deleteName}
              onChange={(event) => setDeleteName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  if (!busy && deleteName.trim()) onDelete();
                }
              }}
              placeholder="输入方药名称"
            />
            <button type="button" className="danger" disabled={busy || !deleteName.trim()} onClick={onDelete}>{"删除"}</button>
          </div>
          <small className="knowledge-status">{status}</small>
          <button type="button" className="knowledge-confirm-button" disabled={busy || !entityName} onClick={onImport}>{"确认导入图谱"}</button>
        </section>
        <KnowledgeGraphPreview graph={previewGraph} focus={entityName} draft={draft} hasWebGL={hasWebGL} />
      </div>
    </form>
  );
}

function KnowledgeImportHistory({ imports, onRefresh }) {
  return (
    <section className="knowledge-history-panel">
      <div className="knowledge-workbench-head">
        <div><p className="eyebrow">{"记录"}</p><h2>{"图谱操作记录"}</h2></div>
        <button type="button" className="mode-switch compact" onClick={onRefresh}>{"刷新"}</button>
      </div>
      <div className="knowledge-history-list">
        {imports.map((item) => (
          <article key={item.id} className={["knowledge-history-row", item.operation_type, item.is_committed || item.status === "committed" ? "committed" : "draft"].join(" ")}>
            <span className={["operation-badge", item.operation_type].join(" ")}>{item.operation_type === "delete" ? "删除" : "添加"}</span>
            <strong>{item.entity_name || item.extracted?.herb?.name || "未命名方药"}</strong>
            <span>{formatShanghaiDateTime(item.finished_at || item.created_at)}</span>
            <small>{item.is_committed || item.status === "committed" ? "正式生效" : "未生效"}</small>
          </article>
        ))}
        {!imports.length && <p className="empty-note">{"暂无正式图谱操作记录。"}</p>}
      </div>
    </section>
  );
}

function KnowledgeGraphPreview({ graph, focus, draft, hasWebGL }) {
  const sceneRef = useRef(null);
  const [graphSize, setGraphSize] = useState({ width: 1, height: 1 });
  const [selectedNode, setSelectedNode] = useState(null);
  const [previewDepth, setPreviewDepth] = useState(2);
  const previewGraph = useMemo(() => sliceGraphByDepth(graph, focus, previewDepth), [graph, focus, previewDepth]);
  const previewData = useMemo(() => toRenderableGraph(previewGraph, focus), [previewGraph, focus]);
  useEffect(() => {
    function measureScene() {
      const rect = sceneRef.current?.getBoundingClientRect();
      if (!rect) return;
      setGraphSize({ width: Math.max(320, Math.floor(rect.width)), height: Math.max(360, Math.floor(rect.height)) });
    }
    measureScene();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measureScene) : null;
    if (observer && sceneRef.current) observer.observe(sceneRef.current);
    window.addEventListener("resize", measureScene);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measureScene); };
  }, []);
  useEffect(() => {
    if (!selectedNode) return;
    if (!previewGraph.nodes.some((node) => node.id === selectedNode.id)) {
      setSelectedNode(null);
    }
  }, [previewGraph, selectedNode]);
  const hasGraph = previewData.nodes.length > 0;
  const title = focus || "等待识别";
  return (
    <section className="knowledge-preview-zone">
      <div className="knowledge-zone-title">
        <div><p className="eyebrow">{"3D 图谱预览"}</p><h3>{title}</h3></div>
        <div className="knowledge-preview-toolbar">
          <label className="knowledge-preview-controls">
            <span>{"深度"}</span>
            <select value={previewDepth} onChange={(event) => setPreviewDepth(Number(event.target.value))}>
              <option value={1}>{"1 跳"}</option>
              <option value={2}>{"2 跳"}</option>
            </select>
          </label>
          <span className="knowledge-preview-count">{hasGraph ? `${previewData.nodes.length} 节点 · ${previewData.links.length} 关系` : "空状态"}</span>
        </div>
      </div>
      <span className="graph-depth-help knowledge-preview-depth-help" title="1跳仅显示中心实体的直接关系；2跳会继续扩展到邻居的邻居。">{"1跳=直接关系，2跳=再扩展一层"}</span>
      <div className="knowledge-preview-scene" ref={sceneRef}>
        {hasGraph ? (
          hasWebGL ? (
            <ThreeKnowledgeGraph graphData={previewData} graphFocus={focus} graphSize={graphSize} onSelect={setSelectedNode} />
          ) : (
            <KnowledgeGraphFallback graph={{ nodes: previewData.nodes, edges: previewData.links }} focus={focus} onSelect={setSelectedNode} />
          )
        ) : (
          <div className="knowledge-preview-empty">
            <Network size={34} />
            <strong>{"识别后将在这里展示方药图谱"}</strong>
            <span>{"AI识别只生成预览；点击确认导入图谱后才写入 Neo4j 并生成正式记录。"}</span>
          </div>
        )}
        {hasGraph && (
          <div className="knowledge-preview-legend" aria-label="图谱图例">
            <div>
              <b>{"节点"}</b>
              {["Formula", "Herb", "Effect", "Symptom", "Disease", "Source"].map((label) => (
                <span key={label}><i style={{ background: entityColor(label) }} />{entityLabel(label)}</span>
              ))}
            </div>
            <div>
              <b>{"关系"}</b>
              {["HAS_INGREDIENT", "HAS_EFFECT", "FROM_SOURCE", "ALLEVIATES_SYMPTOM", "TREATS_DISEASE"].map((label) => (
                <span key={label}><i className="line-swatch" style={{ background: relationColor(label) }} />{relationLabel(label)}</span>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="knowledge-preview-summary">
        <strong>{selectedNode?.name || draft.herb.name || "尚未识别方药"}</strong>
        <span>{selectedNode ? entityLabel(selectedNode.label) : draft.herb.ingredients ? `组成：${draft.herb.ingredients}` : "支持方剂文档、药材文本和手动粘贴资料"}</span>
      </div>
    </section>
  );
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
  return <div className="kg-canvas"><svg viewBox="0 0 720 460" role="img" aria-label="知识图谱">{graph.edges.map((edge) => { const source = layout[edge.source]; const target = layout[edge.target]; if (!source || !target) return null; return <g key={edge.id}><line x1={source.x} y1={source.y} x2={target.x} y2={target.y} style={{ stroke: relationColor(edge.label) }} /><text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2}>{relationLabel(edge.label)}</text></g>; })}</svg>{graph.nodes.map((node) => { const point = layout[node.id]; if (!point) return null; return <button type="button" className={["kg-node", node.label, node.name === focus ? "focused" : ""].filter(Boolean).join(" ")} key={node.id} style={{ left: String(point.x / 7.2) + "%", top: String(point.y / 4.6) + "%" }} onClick={() => onSelect(node)}><span>{node.name}</span><small>{entityLabel(node.label)}</small></button>; })}</div>;
}

function FormattedMessage({ content }) {
  if (!content) return <div className="formatted-answer compact-answer muted">{"正在等待回答…"}</div>;
  const normalized = content.replace(/\s*###\s*/g, "\n\n### ").replace(/\s+-\s+\*\*/g, "\n- **").replace(/\s+-\s+/g, "\n- ");
  const lines = normalized.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const compact = lines.length === 1 && cleanMarkdown(lines[0]).length <= 40;
  return <div className={["formatted-answer", compact ? "compact-answer" : ""].filter(Boolean).join(" ")}>{lines.map((line, index) => { if (line.startsWith("### ")) return <h3 key={index}>{cleanMarkdown(line.replace(/^###\s*/, ""))}</h3>; if (/^[-*]\s+/.test(line)) return <p className="answer-list-item" key={index}>{cleanMarkdown(line.replace(/^[-*]\s+/, ""))}</p>; return <p key={index}>{cleanMarkdown(line)}</p>; })}</div>;
}

function activeTitle(view) { return { assistant: "智能问答", search: "方药知识搜索", graph: "知识图谱关联", admin: "管理员后台" }[view] || "中医知识图谱"; }
function threadStateLabel(state, messageCount = 0) {
  if (state?.loading) return "思考中";
  if (state?.status === "failed") return "失败";
  if (state?.unread) return "已完成未读";
  if (state?.status === "done") return "已完成";
  return messageCount ? "已保存" : "空对话";
}
function normalizeKnowledgeDraft(payload) {
  const herb = { ...emptyKnowledgeDraft.herb, ...(payload?.herb || {}) };
  const relations = Array.isArray(payload?.relations) ? payload.relations : [];
  const subjectType = herb.label || "Herb";
  return {
    herb,
    relations: relations.map((relation) => ({
      subject: relation.subject || herb.name || "",
      subject_type: relation.subject_type || subjectType,
      relation: relation.relation || "HAS_EFFECT",
      object: relation.object || "",
      object_type: relation.object_type || "Effect",
    })),
  };
}

function buildPreviewGraphFromDraft(payload) {
  const draft = normalizeKnowledgeDraft(payload);
  const label = draft.herb.label || "Formula";
  const centerId = `${label}:${draft.herb.name || "未命名方药"}`;
  if (!draft.herb.name) return { nodes: [], edges: [] };
  const nodes = [{
    id: centerId,
    name: draft.herb.name,
    label,
    properties: Object.fromEntries(Object.entries(draft.herb).filter(([, value]) => value)),
  }];
  const edges = [];
  const known = new Set([centerId]);
  draft.relations.forEach((relation) => {
    const subjectLabel = relation.subject_type || label;
    const subjectName = relation.subject || draft.herb.name || "";
    const subjectId = `${subjectLabel}:${subjectName}`;
    if (subjectName && !known.has(subjectId)) {
      known.add(subjectId);
      nodes.push({ id: subjectId, name: subjectName, label: subjectLabel, properties: subjectId === centerId ? Object.fromEntries(Object.entries(draft.herb).filter(([, value]) => value)) : {} });
    }
    if (!relation.object) return;
    const objectLabel = relation.object_type || "Entity";
    const objectId = `${objectLabel}:${relation.object}`;
    if (!known.has(objectId)) {
      known.add(objectId);
      nodes.push({ id: objectId, name: relation.object, label: objectLabel, properties: {} });
    }
    edges.push({ id: `${subjectId}-${relation.relation}-${objectId}`, source: subjectId, target: objectId, label: relation.relation });
  });
  return { nodes, edges };
}

function sliceGraphByDepth(graph, focus, depth = 2) {
  const rawNodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const rawEdges = Array.isArray(graph?.edges) ? graph.edges : [];
  if (!rawNodes.length) return { nodes: [], edges: [] };

  const centerNode = rawNodes.find((node) => node.name === focus) || rawNodes[0];
  if (!centerNode?.id) return { nodes: rawNodes, edges: rawEdges };

  const maxDepth = Math.max(1, Math.min(Number(depth) || 1, 2));
  const adjacency = new Map(rawNodes.map((node) => [node.id, new Set()]));
  rawEdges.forEach((edge) => {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set());
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set());
    adjacency.get(edge.source).add(edge.target);
    adjacency.get(edge.target).add(edge.source);
  });

  const distances = new Map([[centerNode.id, 0]]);
  const queue = [centerNode.id];
  while (queue.length) {
    const nodeId = queue.shift();
    const nextDepth = distances.get(nodeId) + 1;
    if (nextDepth > maxDepth) continue;
    (adjacency.get(nodeId) || []).forEach((neighborId) => {
      if (distances.has(neighborId)) return;
      distances.set(neighborId, nextDepth);
      queue.push(neighborId);
    });
  }

  const visibleIds = new Set(distances.keys());
  return {
    nodes: rawNodes.filter((node) => visibleIds.has(node.id)),
    edges: rawEdges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
  };
}

function toRenderableGraph(graph, focus) {
  const rawNodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const rawEdges = Array.isArray(graph?.edges) ? graph.edges : [];
  const nodes = rawNodes.map((node) => ({
    ...node,
    val: node.name === focus ? 8 : 4,
    color: entityColor(node.label, node.name === focus),
  }));
  return {
    nodes,
    links: rawEdges.map((edge) => ({ ...edge, source: edge.source, target: edge.target, color: relationColor(edge.label) })),
  };
}
function appendToLastAssistant(messages, chunk) { const next = [...messages]; const lastIndex = next.length - 1; if (lastIndex >= 0 && next[lastIndex].role === "assistant") { next[lastIndex] = { ...next[lastIndex], content: next[lastIndex].content + chunk }; return next; } return [...next, { role: "assistant", content: chunk }]; }
function appendAssistantError(messages, message = chatStreamErrorMessage) {
  const next = [...messages];
  const lastIndex = next.length - 1;
  if (lastIndex < 0 || next[lastIndex].role !== "assistant") {
    return [...next, { role: "assistant", content: message }];
  }
  const content = String(next[lastIndex].content || "").trim();
  next[lastIndex] = {
    ...next[lastIndex],
    content: content ? `${next[lastIndex].content}\n\n${message}` : message,
  };
  return next;
}
function markInterruptedAssistant(messages) {
  const next = [...messages];
  const lastIndex = next.length - 1;
  if (lastIndex < 0 || next[lastIndex].role !== "assistant") return next;
  const content = String(next[lastIndex].content || "").trim();
  next[lastIndex] = {
    ...next[lastIndex],
    content: content ? `${next[lastIndex].content}\n\n（已中断，转为处理新的问题。）` : "已中断，转为处理新的问题。",
  };
  return next;
}
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
