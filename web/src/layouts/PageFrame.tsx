import type { ReactNode } from "react";

export function PageFrame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="h-full overflow-y-auto bg-muted/40">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
        <h1 className="text-xl font-medium tracking-tight">{title}</h1>
        {children}
      </div>
    </div>
  );
}
