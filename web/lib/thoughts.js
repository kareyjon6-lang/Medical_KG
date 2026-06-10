const CYPHER_OR_JSON_PREFIX = /^(["{}[\]:,\]]|MATCH\b|MAT$|CH$|WHERE\b|RETURN\b|WITH\b|OPTIONAL\b|CALL\b|query\b|params\b|cypher\b)/i;
const ASCII_CYPHER_FRAGMENT = /^[A-Za-z0-9_.$:`'"\-\s()[\]{}=<>*,]+$/;
const MILESTONE_PREFIX = /^(开始|完成|正在|进入|识别|抽取|匹配|生成|执行|校验|查询|回答|意图|实体|图谱|Cypher|CYPHER|寮€濮|瀹屾垚|姝ｅ湪|杩涘叆|璇嗗埆|鎶藉彇|鍖归厤|鐢熸垚|鎵ц|鏍￠獙|鏌ヨ|鍥炵瓟|鎰忓浘|瀹炰綋|鍥捐氨)/;

export function appendThoughtChunk(thoughts, chunk) {
  const raw = String(chunk ?? "");
  if (!raw) return thoughts;

  const compact = raw.replace(/\s*\n+\s*/g, "").trim();
  if (!compact) return thoughts;

  const looksLikeCypherOrJsonChunk = CYPHER_OR_JSON_PREFIX.test(compact) || ASCII_CYPHER_FRAGMENT.test(compact);
  const isMilestone = MILESTONE_PREFIX.test(compact) && compact.length > 6 && !looksLikeCypherOrJsonChunk;
  const lastThought = thoughts[thoughts.length - 1] || "";
  const lastIsCypher = isStreamThoughtLine(lastThought);
  const shortContinuation = compact.length <= 14 && !/[。！？!?]$/.test(compact);
  const shouldAppend = thoughts.length > 0
    && !isMilestone
    && (looksLikeCypherOrJsonChunk || (lastIsCypher && shortContinuation));

  if (shouldAppend) {
    const next = [...thoughts];
    const glue = needsThoughtSpace(lastThought, compact) ? " " : "";
    next[next.length - 1] = `${lastThought}${glue}${compact}`.replace(/\s{3,}/g, " ");
    return next;
  }

  return [...thoughts, compact];
}

export function isStreamThoughtLine(text) {
  return /[{[\]}":,]|MATCH|WHERE|RETURN|WITH|OPTIONAL|CALL|query|params|cypher/i.test(String(text || ""));
}

function needsThoughtSpace(left, right) {
  if (!left || !right) return false;
  if (/[\u4e00-\u9fff]$/.test(left) && /^[\u4e00-\u9fff]/.test(right)) return false;
  return /[A-Za-z0-9_]$/.test(left) && /^[A-Za-z0-9_]/.test(right);
}
