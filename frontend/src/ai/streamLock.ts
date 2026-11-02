// frontend/src/ai/streamLock.ts
import { useSyncExternalStore } from "react";

let holder: symbol | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function isBusy(): boolean {
  return holder !== null;
}

export function acquireAiStream(): symbol | null {
  if (holder !== null) {
    return null;
  }
  holder = Symbol("ai-stream");
  emit();
  return holder;
}

export function releaseAiStream(slot: symbol): void {
  if (holder === slot) {
    holder = null;
    emit();
  }
}

export function useAiStreamBusy(): boolean {
  return useSyncExternalStore(subscribe, isBusy, () => false);
}
