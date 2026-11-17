// frontend/src/ui/Tabs.tsx
import {
  createContext,
  type KeyboardEvent,
  type ReactNode,
  useContext,
  useEffect,
  useId,
  useRef,
} from "react";
import { cx } from "./threat.ts";

interface TabsContextValue {
  readonly baseId: string;
  readonly value: string;
  readonly onValueChange: (nextValue: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext(): TabsContextValue {
  const ctx = useContext(TabsContext);
  if (ctx === null) {
    throw new Error("Tab components must be rendered inside <Tabs>.");
  }
  return ctx;
}

export function tabElementId(baseId: string, value: string): string {
  return `${baseId}-tab-${value}`;
}

export function panelElementId(baseId: string, value: string): string {
  return `${baseId}-panel-${value}`;
}

export interface TabsProps {
  readonly value: string;
  readonly onValueChange: (nextValue: string) => void;
  readonly idPrefix?: string;
  readonly className?: string;
  readonly children: ReactNode;
}

// WAI-ARIA tabs pattern: controlled by value and onValueChange, rendering only
// the active TabPanel, and setting no inline style.
export function Tabs({
  value,
  onValueChange,
  idPrefix,
  className,
  children,
}: TabsProps) {
  const generatedId = useId();
  const baseId = idPrefix ?? generatedId;

  return (
    <TabsContext.Provider value={{ baseId, value, onValueChange }}>
      <div className={cx("space-y-4", className)}>{children}</div>
    </TabsContext.Provider>
  );
}

export interface TabListProps {
  readonly "aria-label"?: string;
  readonly "aria-labelledby"?: string;
  readonly className?: string;
  readonly children: ReactNode;
}

export function TabList({
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
  className,
  children,
}: TabListProps) {
  const { onValueChange } = useTabsContext();

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (
      event.key !== "ArrowRight" &&
      event.key !== "ArrowLeft" &&
      event.key !== "Home" &&
      event.key !== "End"
    ) {
      return;
    }

    const tabs = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>(
        '[role="tab"]:not([disabled])',
      ),
    );
    if (tabs.length === 0) {
      return;
    }

    const activeElement = document.activeElement;
    const currentIndex = tabs.findIndex(
      (btn) =>
        btn === activeElement || btn.getAttribute("aria-selected") === "true",
    );
    const startIndex = currentIndex >= 0 ? currentIndex : 0;

    let nextIndex = startIndex;
    switch (event.key) {
      case "ArrowRight":
        nextIndex = (startIndex + 1) % tabs.length;
        break;
      case "ArrowLeft":
        nextIndex = (startIndex - 1 + tabs.length) % tabs.length;
        break;
      case "Home":
        nextIndex = 0;
        break;
      case "End":
        nextIndex = tabs.length - 1;
        break;
    }

    const targetTab = tabs.at(nextIndex);
    if (!targetTab) {
      return;
    }
    event.preventDefault();
    targetTab.focus();
    const nextValue = targetTab.getAttribute("data-tab-value");
    if (nextValue !== null) {
      onValueChange(nextValue);
    }
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledBy}
      onKeyDown={handleKeyDown}
      className={cx(
        "flex max-w-full items-center gap-1 overflow-x-auto rounded-card border border-line bg-surface-card p-1.5 shadow-card",
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface TabProps {
  readonly value: string;
  readonly disabled?: boolean;
  readonly className?: string;
  readonly children: ReactNode;
}

export function Tab({
  value,
  disabled = false,
  className,
  children,
}: TabProps) {
  const { baseId, value: activeValue, onValueChange } = useTabsContext();
  const isSelected = activeValue === value;
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const button = buttonRef.current;
    const list = button?.closest<HTMLElement>('[role="tablist"]');
    if (!isSelected || !button || !list) return;
    // Reveal a hash-selected tab horizontally without scrolling the page.
    const tabBox = button.getBoundingClientRect();
    const listBox = list.getBoundingClientRect();
    if (tabBox.left < listBox.left) list.scrollLeft -= listBox.left - tabBox.left + 6;
    else if (tabBox.right > listBox.right) list.scrollLeft += tabBox.right - listBox.right + 6;
  }, [isSelected]);

  return (
    <button
      type="button"
      role="tab"
      ref={buttonRef}
      id={tabElementId(baseId, value)}
      aria-selected={isSelected}
      aria-controls={panelElementId(baseId, value)}
      tabIndex={isSelected ? 0 : -1}
      disabled={disabled}
      data-tab-value={value}
      data-testid={`tab-${value}`}
      onClick={() => {
        if (!disabled && !isSelected) {
          onValueChange(value);
        }
      }}
      className={cx(
        "inline-flex min-h-6 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-control px-3 py-1.5 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60",
        isSelected
          ? "bg-brand text-on-brand"
          : "text-ink-muted hover:bg-surface-inset hover:text-ink",
        className,
      )}
    >
      {children}
    </button>
  );
}

export interface TabPanelProps {
  readonly value: string;
  readonly className?: string;
  readonly children: ReactNode;
}

export function TabPanel({ value, className, children }: TabPanelProps) {
  const { baseId, value: activeValue } = useTabsContext();
  if (activeValue !== value) {
    return null;
  }

  return (
    <div
      role="tabpanel"
      id={panelElementId(baseId, value)}
      aria-labelledby={tabElementId(baseId, value)}
      tabIndex={0}
      data-testid={`tabpanel-${value}`}
      className={cx(
        "space-y-6 rounded-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        className,
      )}
    >
      {children}
    </div>
  );
}
