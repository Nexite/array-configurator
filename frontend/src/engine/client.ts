type Pending = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
};

type Reply = { id: number; result?: unknown; error?: string };

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, Pending>();

function engineWorker(): Worker {
  if (!worker) {
    worker = new Worker(new URL("./geometry.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<Reply>) => {
      const job = pending.get(event.data.id);
      if (!job) return;
      pending.delete(event.data.id);
      if (event.data.error) job.reject(new Error(event.data.error));
      else job.resolve(event.data.result);
    };
    worker.onerror = (event) => {
      const error = new Error(event.message || "Geometry engine failed");
      for (const job of pending.values()) job.reject(error);
      pending.clear();
    };
  }
  return worker;
}

export function geometry<T>(op: string, payload: unknown): Promise<T> {
  const id = nextId++;
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve: (value) => resolve(value as T), reject });
    engineWorker().postMessage({ id, op, payload });
  });
}

/** Start the engine before the first edit so packing does not pay the load on click. */
export function preloadGeometry(): Promise<{ ok: boolean }> {
  return geometry("ping", {});
}
