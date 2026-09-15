import { Navigate, Route, Routes } from "react-router-dom";
import {
  StockAnalyzePage,
  StockLayout,
  StockNationalPage,
  StockScanPage,
  StockTrainPage,
  StockWatchPage,
  StockWeeklyPage,
} from "@/pages/StockPage";

export default function StockRoutes() {
  return (
    <Routes>
      <Route element={<StockLayout />}>
        <Route index element={<Navigate to="/stock/watch" replace />} />
        <Route path="watch" element={<StockWatchPage />} />
        <Route path="scan" element={<StockScanPage />} />
        <Route path="weekly" element={<StockWeeklyPage />} />
        <Route path="analyze" element={<StockAnalyzePage />} />
        <Route path="national" element={<StockNationalPage />} />
        <Route path="train" element={<StockTrainPage />} />
        <Route path="*" element={<Navigate to="/stock/watch" replace />} />
      </Route>
    </Routes>
  );
}
