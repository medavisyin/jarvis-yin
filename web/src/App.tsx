import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/layouts/AppShell";
import { ChatPage } from "@/pages/ChatPage";
import { NewsLayout, NewsToolPage } from "@/pages/NewsPage";
import { ReadingPage } from "@/pages/ReadingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { MedavisLayout, MedavisToolPage } from "@/pages/MedavisPage";

const StockRoutes = lazy(() => import("@/pages/StockRoutes"));

function StockFallback() {
  return <p className="text-muted-foreground p-6 text-sm">Loading…</p>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/news" element={<NewsLayout />}>
            <Route index element={<Navigate to="daily" replace />} />
            <Route path=":tab" element={<NewsToolPage />} />
          </Route>
          <Route
            path="stock/*"
            element={
              <Suspense fallback={<StockFallback />}>
                <StockRoutes />
              </Suspense>
            }
          />
          <Route path="/reading" element={<ReadingPage />} />
          <Route path="/medavis" element={<MedavisLayout />}>
            <Route index element={<Navigate to="wiki" replace />} />
            <Route path=":tab" element={<MedavisToolPage />} />
          </Route>
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
