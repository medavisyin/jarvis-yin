import type { ColDef, GetRowIdParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { clampGridHeight } from "@/lib/dataGrid";
import { stockGridTheme } from "@/lib/stockGridTheme";

export function DataGrid<T extends object>({
  rows,
  columnDefs,
  noRows = "暂无",
  getRowId,
  context,
  maxHeight = 420,
}: {
  rows: T[];
  columnDefs: ColDef<T>[];
  noRows?: string;
  getRowId?: (p: GetRowIdParams<T>) => string;
  context?: unknown;
  maxHeight?: number;
}) {
  const height = clampGridHeight(rows.length, 36, 40, maxHeight);
  return (
    <div className="border-border overflow-hidden rounded-xl border" style={{ height }}>
      <AgGridReact<T>
        theme={stockGridTheme}
        rowData={rows}
        columnDefs={columnDefs}
        context={context}
        getRowId={getRowId}
        animateRows
        rowHeight={36}
        headerHeight={40}
        suppressCellFocus
        defaultColDef={{ sortable: true, resizable: true }}
        overlayNoRowsTemplate={noRows}
      />
    </div>
  );
}
