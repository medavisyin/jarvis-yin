import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { readReadingPrefs } from "@/lib/readingPrefs";

type ReadingFocusCtx = {
  focus: boolean;
  setFocus: (value: boolean) => void;
  bookOpen: boolean;
  setBookOpen: (value: boolean) => void;
};

const ReadingFocusContext = createContext<ReadingFocusCtx>({
  focus: false,
  setFocus: () => {},
  bookOpen: false,
  setBookOpen: () => {},
});

export function ReadingFocusProvider({ children }: { children: ReactNode }) {
  const [focus, setFocus] = useState(() => readReadingPrefs().focus);
  const [bookOpen, setBookOpen] = useState(false);
  const value = useMemo(() => ({ focus, setFocus, bookOpen, setBookOpen }), [focus, bookOpen]);
  return <ReadingFocusContext.Provider value={value}>{children}</ReadingFocusContext.Provider>;
}

export function useReadingFocus() {
  return useContext(ReadingFocusContext);
}
