import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { apiJson } from "@/lib/api";
import { accordionValuesForPath, defaultChildPath, isNavGroup, NAV } from "@/lib/nav";
import { ReadingFocusProvider, useReadingFocus } from "@/lib/readingFocus";
import { hideReadingSidebar } from "@/lib/readingPrefs";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
    isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
  );

export function AppShell() {
  return (
    <ReadingFocusProvider>
      <AppShellInner />
    </ReadingFocusProvider>
  );
}

function AppShellInner() {
  const [health, setHealth] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const { focus, bookOpen } = useReadingFocus();
  const hideSidebar = hideReadingSidebar(focus, bookOpen, location.pathname);
  const required = accordionValuesForPath(location.pathname);
  const [open, setOpen] = useState<string[]>(required);

  useEffect(() => {
    apiJson<{ ollama?: boolean; model?: string }>("/api/health")
      .then((h) => setHealth(`${h.model || "?"} · ollama ${h.ollama ? "up" : "down"}`))
      .catch(() => setHealth("health unavailable"));
  }, []);

  const requiredKey = required.join(",");
  useEffect(() => {
    const extra = requiredKey ? requiredKey.split(",") : [];
    setOpen((prev) => Array.from(new Set([...prev, ...extra])));
  }, [requiredKey]);

  return (
    <div className="bg-background text-foreground flex h-svh min-h-0 overflow-hidden">
      <aside
        className={cn(
          "border-border bg-sidebar text-sidebar-foreground flex w-64 shrink-0 flex-col border-r",
          hideSidebar && "hidden",
        )}
      >
        <div className="px-4 py-4">
          <p className="text-lg font-medium tracking-tight">Jarvis</p>
          <p className="text-muted-foreground text-xs">{health || "…"}</p>
        </div>
        <Separator />
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-2">
          {NAV.map((item) =>
            isNavGroup(item) ? (
              <Accordion
                key={item.id}
                type="multiple"
                value={open.filter((id) => id === item.id)}
                onValueChange={(next) => {
                  setOpen((prev) => {
                    const others = prev.filter((id) => id !== item.id);
                    return next.includes(item.id) ? [...others, item.id] : others;
                  });
                }}
              >
                <AccordionItem value={item.id}>
                  <AccordionTrigger
                    className={cn(
                      "text-muted-foreground hover:bg-muted/60 hover:text-foreground hover:no-underline",
                      required.includes(item.id) && "text-foreground",
                    )}
                    onClick={() => {
                      if (location.pathname !== item.to && !location.pathname.startsWith(`${item.to}/`)) {
                        navigate(defaultChildPath(item));
                      }
                    }}
                  >
                    <span className="flex items-center gap-2">
                      <item.icon className="size-4" />
                      {item.label}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="flex flex-col gap-0.5 pl-4">
                      {item.children.map((child) => (
                        <NavLink key={child.to} to={child.to} className={linkClass}>
                          {child.label}
                        </NavLink>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            ) : (
              <NavLink key={item.id} to={item.to} end={item.end} className={linkClass}>
                <item.icon className="size-4" />
                {item.label}
              </NavLink>
            ),
          )}
        </nav>
      </aside>
      <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
