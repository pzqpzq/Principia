type QueuedMutation = {
  id: string;
  sessionId: string;
  expectedRevision: number;
  operations: Array<Record<string, unknown>>;
  createdAt: number;
};

const DATABASE = "principia-research-autosave";
const STORE = "graph-mutations";

function openQueue(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function queueGraphMutation(value: Omit<QueuedMutation, "id" | "createdAt">): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const database = await openQueue();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).put({ ...value, id: crypto.randomUUID(), createdAt: Date.now() });
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

export async function queuedGraphMutations(sessionId: string): Promise<QueuedMutation[]> {
  if (typeof indexedDB === "undefined") return [];
  const database = await openQueue();
  const rows = await new Promise<QueuedMutation[]>((resolve, reject) => {
    const request = database.transaction(STORE, "readonly").objectStore(STORE).getAll();
    request.onsuccess = () => resolve(request.result as QueuedMutation[]);
    request.onerror = () => reject(request.error);
  });
  database.close();
  return rows.filter((row) => row.sessionId === sessionId).sort((left, right) => left.createdAt - right.createdAt);
}

export async function removeQueuedGraphMutation(id: string): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const database = await openQueue();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).delete(id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}
