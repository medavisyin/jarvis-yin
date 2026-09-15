import type { ReactNode } from "react";
import { asPickList, changeDirection, extractScanSections, formatChangePct, type ScanPick } from "@/lib/stockFormat";
import { qvEmptyCopy, qvHorizonLabel, scanSectionRan } from "@/lib/scannerResults";
import { Button } from "@/components/ui/button";

type Obj = Record<string, unknown>;
type AnalyzeFn = (symbol: string) => void;

function asObj(v: unknown): Obj {
  return v && typeof v === "object" ? (v as Obj) : {};
}

function num(v: unknown): number | undefined {
  return typeof v === "number" && !Number.isNaN(v) ? v : undefined;
}

function chgClass(chg: number | undefined): string {
  const dir = changeDirection(chg);
  return dir === "up" ? "text-[#dc2626]" : dir === "down" ? "text-[#16a34a]" : "text-muted-foreground";
}

function EmptyBlock({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="space-y-1 py-6 text-center">
      <p className="text-sm font-medium text-amber-600 dark:text-amber-400">{title}</p>
      <p className="text-muted-foreground text-xs">{detail}</p>
    </div>
  );
}

function SymButton({ symbol, name, onAnalyze }: { symbol?: string; name?: string; onAnalyze?: AnalyzeFn }) {
  if (!symbol) return <span>{name || ""}</span>;
  if (!onAnalyze) {
    return (
      <span>
        <span className="font-medium">{name || symbol}</span>{" "}
        <span className="text-muted-foreground">({symbol})</span>
      </span>
    );
  }
  return (
    <button type="button" className="text-left" onClick={() => onAnalyze(symbol)}>
      <span className="text-primary font-medium underline-offset-2 hover:underline">{name || symbol}</span>{" "}
      <span className="text-muted-foreground">({symbol})</span>
    </button>
  );
}

function CardShell({ children }: { children: ReactNode }) {
  return <div className="space-y-1 rounded-lg border p-3">{children}</div>;
}

export function ScanPickCards({
  picks,
  onAnalyze,
  emptyTitle = "本次扫描：暂无推荐",
  emptyDetail = "经过三层筛选，没有找到估值合理且值得买入的股票。这是正常的 — “不推荐” 本身就是最好的建议。",
  heading = "推荐买入",
}: {
  picks: ScanPick[];
  onAnalyze?: AnalyzeFn;
  emptyTitle?: string;
  emptyDetail?: string;
  heading?: string;
}) {
  if (!picks.length) return <EmptyBlock title={emptyTitle} detail={emptyDetail} />;
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">
        {heading}: {picks.length} 只
      </p>
      {picks.map((p, i) => {
        const row = p as ScanPick & Obj;
        const chg = num(row.change_pct);
        return (
          <CardShell key={`${row.symbol || "p"}-${i}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-muted-foreground mr-1 text-xs">#{i + 1}</span>
                <SymButton symbol={row.symbol} name={row.name} onAnalyze={onAnalyze} />
              </div>
              {num(row.final_score) != null ? (
                <span className="text-sm font-semibold tabular-nums">{num(row.final_score)!.toFixed(1)}/100</span>
              ) : null}
            </div>
            <div className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-xs">
              {row.price != null ? <span>¥{String(row.price)}</span> : null}
              {chg != null ? <span className={chgClass(chg)}>{formatChangePct(chg)}</span> : null}
              {row.pe != null ? <span>PE: {String(row.pe)}</span> : null}
              {row.fund_score != null ? <span>基本面: {String(row.fund_score)}</span> : null}
              {row.tech_score != null ? <span>技术: {String(row.tech_score)}</span> : null}
              {row.sentiment_score != null ? <span>情绪: {String(row.sentiment_score)}</span> : null}
              {row.is_hot ? <span className="text-amber-600">热门</span> : null}
            </div>
            {row.buy_low && row.buy_high ? (
              <p className="text-xs">建议买入区间: ¥{String(row.buy_low)} ~ ¥{String(row.buy_high)}</p>
            ) : null}
            {row.reasoning ? <p className="text-xs">{String(row.reasoning)}</p> : null}
            {row.risk ? <p className="text-destructive text-xs">风险: {String(row.risk)}</p> : null}
            {row.strategy ? <p className="text-xs">策略: {String(row.strategy)}</p> : null}
          </CardShell>
        );
      })}
    </div>
  );
}

export function RightPickCards({ picks, onAnalyze }: { picks: ScanPick[]; onAnalyze?: AnalyzeFn }) {
  if (!picks.length) {
    return (
      <EmptyBlock
        title="本次扫描：暂无右侧推荐"
        detail="今日无主力资金反转+趋势确认的右侧标的。右侧交易讲究耐心等待确认信号，无信号即不入场。"
      />
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">右侧推荐买入: {picks.length} 只</p>
      <p className="text-muted-foreground text-xs">入场类型: 右侧（资金反转+趋势确认后跟进）</p>
      {picks.map((p, i) => {
        const row = p as ScanPick & Obj;
        const ff = asObj(row.ff_signals);
        const mn3 = (num(ff.main_net_3d) || 0) / 1e8;
        const pct3 = num(ff.main_pct_3d) || 0;
        return (
          <CardShell key={`${row.symbol || "r"}-${i}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-muted-foreground mr-1 text-xs">#{i + 1}</span>
                <SymButton symbol={row.symbol} name={row.name} onAnalyze={onAnalyze} />
              </div>
              {num(row.final_score) != null ? (
                <span className="text-sm font-semibold tabular-nums">{num(row.final_score)!.toFixed(1)}/100</span>
              ) : null}
            </div>
            <div className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-xs">
              {row.price != null ? <span>¥{String(row.price)}</span> : null}
              <span>
                资金反转: 3日净流入 {mn3.toFixed(2)}亿 / 占比 {pct3.toFixed(2)}%
              </span>
              {row.price_above_ma5 ? <span>站上MA5</span> : null}
              {row.ma20 != null ? <span>MA20: ¥{String(row.ma20)}</span> : null}
            </div>
            {row.buy_low && row.buy_high ? (
              <p className="text-xs">建议买入区间: ¥{String(row.buy_low)} ~ ¥{String(row.buy_high)}</p>
            ) : null}
            {row.stop_loss != null ? <p className="text-destructive text-xs">严格止损: ¥{String(row.stop_loss)}</p> : null}
            {row.target_price != null ? <p className="text-xs">2-3个月目标: ¥{String(row.target_price)}</p> : null}
            {row.reasoning ? <p className="text-xs">{String(row.reasoning)}</p> : null}
            {row.risk ? <p className="text-destructive text-xs">风险: {String(row.risk)}</p> : null}
          </CardShell>
        );
      })}
    </div>
  );
}

export function AthPickCards({ result, onAnalyze }: { result: Obj; onAnalyze?: AnalyzeFn }) {
  const picks = asPickList(result.picks || result.top_picks);
  const watch = Array.isArray(result.watch) ? (result.watch as Obj[]) : [];
  return (
    <div className="space-y-2">
      {!picks.length ? (
        <p className="text-muted-foreground text-xs">
          暂无近5年高二次突破可买标的。第一次站上只是标杆，回踩后再突破才是买点。
        </p>
      ) : (
        <>
          {result.ai_reviewed ? null : <p className="text-xs text-amber-600">未经 AI 终审</p>}
          {picks.map((p, i) => {
            const row = p as ScanPick & Obj;
            const tags = Array.isArray(row.pullback_tags) ? (row.pullback_tags as string[]) : [];
            return (
              <CardShell key={`${row.symbol || "a"}-${i}`}>
                <SymButton symbol={row.symbol} name={row.name} onAnalyze={onAnalyze} />
                {row.price != null ? <p className="text-muted-foreground text-xs">现价 ¥{String(row.price)}</p> : null}
                {tags.length ? <p className="text-xs">回踩: {tags.join(", ")}</p> : null}
                {row.tradeable === false ? <p className="text-destructive text-xs">买不到（涨停）</p> : null}
                {row.reasoning ? <p className="text-xs">{String(row.reasoning)}</p> : null}
                {row.risk ? <p className="text-destructive text-xs">风险: {String(row.risk)}</p> : null}
              </CardShell>
            );
          })}
        </>
      )}
      {watch.length ? (
        <div>
          <p className="text-xs text-amber-600">观察（涨停买不到）:</p>
          {watch.map((w, i) => (
            <p key={`${String(w.symbol)}-${i}`} className="text-muted-foreground text-xs">
              {String(w.name || "")} ({String(w.symbol || "")})
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function QualityValueResult({ result, onAnalyze }: { result: Obj; onAnalyze?: AnalyzeFn }) {
  const picks = asPickList(result.picks);
  const hz = qvHorizonLabel(String(result.horizon || "long"));
  const empty = qvEmptyCopy(result);
  if (!picks.length && result.error) {
    return (
      <div className="space-y-2">
        <p className="text-muted-foreground text-xs">不构成投资建议。持有口径{hz}。已排除创业板。</p>
        <EmptyBlock title={String(result.error)} detail="扫描未产出结果页。若行情快照失败，请稍后重试。" />
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs">
        不构成投资建议。持有口径{hz}。已排除创业板。
        {result.use_deepseek || picks.some((p) => asObj(p).prediction) ? "买卖价为约1～2周操作参考。" : ""}
      </p>
      {!picks.length ? (
        <EmptyBlock title={empty.title} detail={empty.detail} />
      ) : (
        <>
          <p className="text-sm font-medium">优质低估 ({picks.length} 只)</p>
          {picks.map((p, i) => {
            const row = p as ScanPick & Obj;
            const llm = asObj(row.llm);
            const pred = asObj(row.prediction);
            return (
              <CardShell key={`${row.symbol || "q"}-${i}`}>
                <div>
                  <span className="text-muted-foreground mr-1 text-xs">#{i + 1}</span>
                  <SymButton symbol={row.symbol} name={row.name} onAnalyze={onAnalyze} />
                  {row.industry ? <span className="text-muted-foreground ml-2 text-xs">{String(row.industry)}</span> : null}
                </div>
                <p className="text-muted-foreground text-xs">
                  PE {row.pe != null ? String(row.pe) : "-"} / PB {row.pb != null ? String(row.pb) : "-"} / 股息{" "}
                  {row.div_yield != null ? String(row.div_yield) : "-"}% / ROE {row.roe != null ? String(row.roe) : "-"} /
                  PB-ROE {row.pb_roe != null ? String(row.pb_roe) : "-"}
                </p>
                {row.pe_percentile_5y != null ? (
                  <p className="text-xs">近5年PE分位: {String(row.pe_percentile_5y)}%</p>
                ) : null}
                {llm.cycle ? (
                  <p className="text-xs">
                    周期: {String(llm.cycle)}
                    {llm.trap ? " · 价值陷阱" : ""}
                  </p>
                ) : null}
                {llm.reason || row.recommendation_reason ? (
                  <p className="text-xs">{String(llm.reason || row.recommendation_reason)}</p>
                ) : null}
                {llm.risk ? <p className="text-destructive text-xs">风险: {String(llm.risk)}</p> : null}
                {pred.ok ? (
                  <div className="space-y-0.5 border-t pt-2 text-xs">
                    <p>
                      约1～2周操作参考 · 短线判断: <b>{String(pred.verdict || "-")}</b>
                    </p>
                    <p>
                      建议买入区间: ¥{pred.buy_low != null ? String(pred.buy_low) : "-"} ~ ¥
                      {pred.buy_high != null ? String(pred.buy_high) : "-"}
                    </p>
                    <p className="text-destructive">止损: ¥{pred.stop_loss != null ? String(pred.stop_loss) : "-"}</p>
                    <p>目标抛售参考: ¥{pred.target_price != null ? String(pred.target_price) : "-"}</p>
                    {pred.reason ? <p className="text-muted-foreground">{String(pred.reason)}</p> : null}
                  </div>
                ) : pred.error || pred.ok === false ? (
                  <p className="text-xs text-amber-600">预测未出</p>
                ) : null}
                {row.llm_skipped ? <p className="text-xs text-amber-600">未经 AI 终审</p> : null}
              </CardShell>
            );
          })}
        </>
      )}
    </div>
  );
}

export function MiddayResult({ result, onAnalyze }: { result: Obj; onAnalyze?: AnalyzeFn }) {
  const picks = asPickList(result.picks);
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">午盘极速内参 (隔夜 T+1 套利)</p>
      <p className="text-muted-foreground text-xs">分析截止: {String(result.ended_at || result.date || "")}</p>
      {!picks.length ? (
        <EmptyBlock
          title="今日暂无推荐标的"
          detail="经过上午盘资金量价的严苛筛选，没有找到满足突破且隔夜高期望值的个股。“不交易、守住现金” 是超短线极高的智慧。"
        />
      ) : (
        <>
          <p className="text-sm font-medium">AI 终极买入推荐: {picks.length} 只 (仓位建议: 1-2成底仓小试)</p>
          {picks.map((p, i) => {
            const row = p as ScanPick & Obj;
            const chg = num(row.change_pct);
            return (
              <CardShell key={`${row.symbol || "m"}-${i}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="mr-1 text-xs">#{i + 1}</span>
                    <SymButton symbol={row.symbol} name={row.name} onAnalyze={onAnalyze} />
                  </div>
                  {num(row.final_score) != null ? (
                    <span className="text-sm font-semibold">{num(row.final_score)!.toFixed(0)}分</span>
                  ) : null}
                </div>
                <div className="text-muted-foreground flex flex-wrap gap-x-3 text-xs">
                  <span>上午盘价: ¥{String(row.price ?? "-")}</span>
                  {chg != null ? <span className={chgClass(chg)}>{formatChangePct(chg)}</span> : null}
                  {row.turnover_rate != null ? <span>换手率: {String(row.turnover_rate)}%</span> : null}
                  {row.volume_ratio != null ? <span>量比: {String(row.volume_ratio)}</span> : null}
                  <span>行业: {String(row.industry || "未指定")}</span>
                </div>
                <div className="grid gap-1 text-xs sm:grid-cols-2">
                  <p>建议限价介入价: ¥{String(row.limit_buy_price || row.price || "-")}</p>
                  <p>明日止盈目标: ¥{String(row.take_profit_target || "N/A")}</p>
                  <p className="text-destructive">明日严格止损: ¥{String(row.stop_loss_target || "N/A")}</p>
                  <p>信心评级: {String(row.confidence_level || "中")}</p>
                </div>
                {row.reasoning ? <p className="text-xs">推荐逻辑：{String(row.reasoning)}</p> : null}
                {row.risk ? <p className="text-destructive text-xs">隔夜风险：{String(row.risk)}</p> : null}
                <p className="rounded-md border border-orange-800/40 bg-orange-950/20 p-2 text-xs">
                  冲高失败退场预案：若明日早盘 9:30-10:00 冲高受阻，或开盘直接无量低开跌破严格止损价，超短线盘口套利应在开盘半小时内（10:00前）果断清仓了结。切忌心存幻想，严防短线单做成长期套牢单！
                </p>
              </CardShell>
            );
          })}
        </>
      )}
    </div>
  );
}

export function LongTermResult({ result, onAnalyze }: { result: Obj; onAnalyze?: AnalyzeFn }) {
  const picks = asPickList(result.picks);
  const metals = asObj(result.precious_metals);
  const themes = Array.isArray(result.themes) ? (result.themes as Obj[]) : [];
  return (
    <div className="space-y-4">
      {metals.gold || metals.silver ? (
        <div className="space-y-2">
          <p className="text-sm font-medium">贵金属分析</p>
          {(["gold", "silver"] as const).map((key) => {
            const m = asObj(metals[key]);
            if (!m.data_available) return null;
            return (
              <CardShell key={key}>
                <div className="flex justify-between text-sm">
                  <span className="font-medium">
                    {key === "gold" ? "黄金" : "白银"} ¥{String(m.latest_price ?? "-")}
                  </span>
                  <span>
                    {String(m.trend || "")} (空间{String(m.upside_score ?? "?")}/100)
                  </span>
                </div>
                <p className="text-muted-foreground text-xs">
                  14天: {formatChangePct(num(m.change_14d_pct))} · 60天: {formatChangePct(num(m.change_60d_pct))} · RSI:{" "}
                  {String(m.rsi_14 ?? "-")} · 52周位: {String(m.position_vs_52w ?? "-")}%
                </p>
              </CardShell>
            );
          })}
        </div>
      ) : null}
      {themes.length ? (
        <div className="space-y-2">
          <p className="text-sm font-medium">投资主题 ({themes.length})</p>
          {themes.map((t, i) => (
            <CardShell key={`${String(t.name)}-${i}`}>
              <p className="text-sm font-medium">
                {i + 1}. {String(t.name || "")}
              </p>
              {t.logic ? <p className="text-muted-foreground text-xs">{String(t.logic)}</p> : null}
              {Array.isArray(t.recommended_stocks)
                ? (t.recommended_stocks as Obj[]).map((s, j) => (
                    <p key={`${String(s.symbol)}-${j}`} className="text-xs">
                      <SymButton symbol={String(s.symbol || "")} name={String(s.name || "")} onAnalyze={onAnalyze} />:{" "}
                      {String(s.logic || "")}
                    </p>
                  ))
                : null}
            </CardShell>
          ))}
        </div>
      ) : null}
      {!picks.length ? (
        <EmptyBlock title="本次分析: 暂无个股推荐" detail="未找到空间充裕且趋势明确的标的, 请参考贵金属分析和投资主题。" />
      ) : (
        <div className="space-y-2">
          <p className="text-sm font-medium">长期推荐 ({picks.length} 只)</p>
          {picks.map((p, i) => {
            const row = p as ScanPick & Obj;
            const upside = asObj(row.upside);
            const us = num(upside.upside_score) ?? 0;
            return (
              <CardShell key={`${row.symbol || "l"}-${i}`}>
                <div className="flex justify-between gap-2">
                  <div>
                    <span className="text-muted-foreground mr-1 text-xs">#{i + 1}</span>
                    <SymButton symbol={row.symbol} name={row.name} onAnalyze={onAnalyze} />
                  </div>
                  <span className="text-sm font-semibold">空间 {us}/100</span>
                </div>
                <p className="text-muted-foreground text-xs">
                  主题: {String(row.theme || "")}
                  {row.time_horizon ? ` | ${String(row.time_horizon)}` : ""}
                </p>
                {row.recommendation_reason ? <p className="text-xs">{String(row.recommendation_reason)}</p> : null}
                {row.recommendation_risk ? (
                  <p className="text-destructive text-xs">{String(row.recommendation_risk)}</p>
                ) : null}
                {row.watch_price ? <p className="text-xs">关注价位: {String(row.watch_price)}</p> : null}
              </CardShell>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function UnifiedResult({ result, onAnalyze }: { result: Obj; onAnalyze?: AnalyzeFn }) {
  const sections = extractScanSections(result);
  const athObj = asObj(result.ath);
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <div className="space-y-1">
        <p className="text-xs font-medium">左侧 · 短期</p>
        {scanSectionRan(result.left) ? (
          <ScanPickCards picks={sections.left} onAnalyze={onAnalyze} heading="推荐买入" />
        ) : (
          <p className="text-muted-foreground text-xs">暂无左侧扫描结果（尚未扫描或正在运行）。</p>
        )}
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium">右侧 · 交易推荐</p>
        {scanSectionRan(result.right) ? (
          <RightPickCards picks={sections.right} onAnalyze={onAnalyze} />
        ) : (
          <p className="text-muted-foreground text-xs">暂无右侧扫描结果（尚未扫描或正在运行）。</p>
        )}
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium">近5年高 · 二次突破</p>
        {scanSectionRan(result.ath) ? (
          <AthPickCards result={athObj} onAnalyze={onAnalyze} />
        ) : (
          <p className="text-muted-foreground text-xs">暂无近5年高二次突破结果（尚未扫描或正在运行）。</p>
        )}
      </div>
    </div>
  );
}

export function ScannerResultBody({
  kindId,
  result,
  onAnalyze,
}: {
  kindId: string;
  result: Obj | null;
  onAnalyze?: AnalyzeFn;
}) {
  if (!result) {
    return <p className="text-muted-foreground text-xs">点击 Start 开始扫描。完成后这里显示该扫描器自己的结果页。</p>;
  }
  if (kindId === "unified") return <UnifiedResult result={result} onAnalyze={onAnalyze} />;
  if (kindId === "qv") return <QualityValueResult result={result} onAnalyze={onAnalyze} />;
  if (kindId === "long-term") return <LongTermResult result={result} onAnalyze={onAnalyze} />;
  if (kindId === "midday") return <MiddayResult result={result} onAnalyze={onAnalyze} />;
  if (kindId === "right") return <RightPickCards picks={asPickList(result.picks || result.top_picks)} onAnalyze={onAnalyze} />;
  return <ScanPickCards picks={asPickList(result.picks || result.top_picks)} onAnalyze={onAnalyze} />;
}

export function HistoryList({
  entries,
  onPickDate,
}: {
  entries: { date?: string; picks?: unknown[] }[];
  onPickDate: (date: string) => void;
}) {
  if (!entries.length) return <p className="text-muted-foreground text-xs">暂无历史记录</p>;
  return (
    <div className="space-y-1">
      {entries
        .slice()
        .reverse()
        .map((e) => (
          <Button
            key={String(e.date)}
            size="sm"
            variant="outline"
            className="w-full justify-between"
            onClick={() => e.date && onPickDate(e.date)}
          >
            <span>{e.date}</span>
            <span className="text-muted-foreground">{Array.isArray(e.picks) ? e.picks.length : 0} 只</span>
          </Button>
        ))}
    </div>
  );
}
