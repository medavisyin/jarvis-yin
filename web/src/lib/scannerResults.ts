export type ScannerId = "unified" | "scan" | "long-term" | "qv" | "midday" | "right";

export type ScannerResultMode = ScannerId;

const MODES = new Set<ScannerId>(["unified", "scan", "long-term", "qv", "midday", "right"]);

export function scannerResultMode(id: string): ScannerResultMode {
  if (MODES.has(id as ScannerId)) return id as ScannerId;
  return "scan";
}

const QV_STEPS: Record<string, string> = {
  layer1: "估值粗筛（排除创业板）...",
  layer2: "基本面排雷...",
  layer3: "PB-ROE 排序...",
  layer4: "DeepSeek 终审...",
  predict: "A股分析买卖价...",
};

const LT_PHASES: Record<string, string> = {
  collecting_signals: "收集近14天新闻信号...",
  analyzing_metals: "贵金属分析 (黄金/白银)...",
  analyzing_factors: "宏观/油/美元/利率/加密分析...",
  analyzing_themes: "LLM 趋势研判...",
  mapping_stocks: "投资主题 → 候选个股...",
  assessing_upside: "空间评估...",
  final_selection: "LLM 精选推荐...",
};

const UNIFIED_PHASES: Record<string, string> = {
  left: "左侧短期扫描...",
  right: "右侧扫描...",
};

function localizeDetail(detail: string, kind?: string): string {
  if (kind === "qv" && QV_STEPS[detail]) return QV_STEPS[detail];
  if (kind === "unified" && UNIFIED_PHASES[detail]) return UNIFIED_PHASES[detail];
  if (LT_PHASES[detail]) return LT_PHASES[detail];
  return detail;
}

export function formatScannerStatus(job: Record<string, unknown>, kind?: string): string {
  const status = String(job.status || "").toLowerCase();
  if (!status || status === "none" || status === "idle") return "";
  if (status === "done" || status === "complete" || status === "completed") return "扫描完成";
  if (status === "stopped") return "已停止";
  if (status === "error" || status === "failed") {
    const err = String(job.error || "").trim();
    return err ? `扫描失败: ${err}` : "扫描失败";
  }
  const pct = job.progress ?? job.progress_pct;
  const pctStr = typeof pct === "number" ? ` ${pct}%` : "";
  if (LT_PHASES[status]) return `${LT_PHASES[status]}${pctStr}`.trim();
  let detail = String(job.phase || job.step || job.message || "").trim();
  detail = localizeDetail(detail, kind);
  if (status === "running" || status === "starting") {
    if (detail && detail.toLowerCase() !== status) return `${detail}${pctStr}`.trim();
    return `扫描进行中${pctStr}`.trim();
  }
  return detail && detail.toLowerCase() !== status ? detail : String(job.status || "");
}

export function scanSectionRan(raw: unknown): boolean {
  if (!raw || typeof raw !== "object") return false;
  const o = raw as Record<string, unknown>;
  if (o.date) return true;
  return Array.isArray(o.picks) || Array.isArray(o.top_picks);
}

export function qvHorizonLabel(horizon: string | undefined): string {
  return horizon === "medium" ? "约 1 个月～6 个月" : "约 6 个月～2 年";
}

export function qvEmptyCopy(result: Record<string, unknown>): { title: string; detail: string } {
  const stats = result.stats && typeof result.stats === "object" ? (result.stats as Record<string, unknown>) : {};
  if (stats.snapshot_failed) {
    return {
      title: "行情快照拉取失败",
      detail: "东财、akshare、新浪均未拉到实时行情，且没有当天本地快照。漏斗未执行。请稍后重试，这不是宁缺毋滥。",
    };
  }
  return {
    title: "本次扫描: 暂无推荐（宁缺毋滥）",
    detail: "漏斗过严或当天没有同时满足优质+低估的标的——这是功能，不是故障。",
  };
}
