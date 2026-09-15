import { useMemo } from "react";
import { type ColDef, type ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Button } from "@/components/ui/button";
import { changeDirection, formatChangePct, formatPrice } from "@/lib/stockFormat";
import { stockGridTheme } from "@/lib/stockGridTheme";

export type WatchlistRow = {
  symbol: string;
  name?: string;
  sector?: string;
  latest_price?: number | null;
  change_pct?: number | null;
  volume?: number | null;
};

function ChangeCell(p: ICellRendererParams<WatchlistRow, number | null>) {
  const dir = changeDirection(p.value);
  const color = dir === "up" ? "#dc2626" : dir === "down" ? "#16a34a" : undefined;
  return <span style={{ color, fontVariantNumeric: "tabular-nums" }}>{formatChangePct(p.value)}</span>;
}

function PriceCell(p: ICellRendererParams<WatchlistRow, number | null>) {
  return <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatPrice(p.value)}</span>;
}

function RemoveCell(p: ICellRendererParams<WatchlistRow>) {
  const onRemove = p.context?.onRemove as ((symbol: string) => void) | undefined;
  if (!p.data?.symbol) return null;
  return (
    <Button size="xs" variant="ghost" onClick={() => onRemove?.(p.data!.symbol)}>
      ×
    </Button>
  );
}

export function WatchlistGrid({
  rows,
  onRemove,
  onAnalyze,
}: {
  rows: WatchlistRow[];
  onRemove: (symbol: string) => void;
  onAnalyze?: (symbol: string) => void;
}) {
  const columnDefs = useMemo<ColDef<WatchlistRow>[]>(
    () => [
      {
        field: "symbol",
        headerName: "代码",
        width: 110,
        pinned: "left",
        filter: true,
        cellRenderer: (p: ICellRendererParams<WatchlistRow>) => {
          const sym = p.data?.symbol;
          if (!sym) return null;
          if (!onAnalyze) return sym;
          return (
            <button type="button" className="text-primary underline" onClick={() => onAnalyze(sym)}>
              {sym}
            </button>
          );
        },
      },
      { field: "name", headerName: "名称", flex: 1, minWidth: 140, filter: true },
      {
        field: "latest_price",
        headerName: "现价",
        width: 110,
        type: "rightAligned",
        cellRenderer: PriceCell,
      },
      {
        field: "change_pct",
        headerName: "涨跌幅",
        width: 110,
        type: "rightAligned",
        cellRenderer: ChangeCell,
      },
      { field: "sector", headerName: "行业", flex: 1, minWidth: 110, filter: true },
      {
        field: "volume",
        headerName: "成交量",
        width: 130,
        type: "rightAligned",
        valueFormatter: (p) => (p.value == null ? "—" : Number(p.value).toLocaleString()),
      },
      {
        colId: "remove",
        headerName: "",
        width: 64,
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: RemoveCell,
      },
    ],
    [onAnalyze],
  );

  return (
    <div className="border-border h-[min(28rem,calc(100svh-18rem))] min-h-64 overflow-hidden rounded-xl border">
      <AgGridReact<WatchlistRow>
        theme={stockGridTheme}
        rowData={rows}
        columnDefs={columnDefs}
        context={{ onRemove, onAnalyze }}
        getRowId={(p) => p.data.symbol}
        animateRows
        rowHeight={36}
        headerHeight={40}
        suppressCellFocus
        defaultColDef={{ sortable: true, resizable: true }}
        overlayNoRowsTemplate="自选股为空"
      />
    </div>
  );
}
