import { ApiError, getAuthSessionId, request } from './client/core';

const COLLECTION_MS = 10;
const MAX_BATCH = 200;
const activeBatches = new Set<Promise<void>>();

export function batchesSettled(): Promise<void> {
  return Promise.allSettled([...activeBatches]).then(() => undefined);
}

type Reply<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
};

function checkSession(session: number) {
  if (session !== getAuthSessionId()) {
    throw new DOMException('Credentials changed while loading data', 'AbortError');
  }
}

/** Coalesce simultaneous reads while preserving each caller's response and credential session. */
export function batched<T>(
  single: (id: number) => Promise<T>,
  many: (ids: number[]) => Promise<Map<number, T>>,
): (id: number) => Promise<T> {
  const pending = new Map<number, Map<number, Reply<T>>>();

  const flush = async (session: number, replies: Map<number, Reply<T>>) => {
    const ids = [...replies.keys()];
    async function fetchChunk(chunk: number[]) {
      const settleSingle = async (id: number) => {
        const reply = replies.get(id)!;
        try {
          checkSession(session);
          const value = await single(id);
          checkSession(session);
          reply.resolve(value);
        } catch (error) {
          reply.reject(error);
        }
      };

      if (chunk.length === 1) {
        await settleSingle(chunk[0]);
        return;
      }

      let result: Map<number, T>;
      try {
        checkSession(session);
        result = await many(chunk);
        checkSession(session);
      } catch (error) {
        if (session !== getAuthSessionId() || (error instanceof ApiError && [401, 403, 429].includes(error.status))) {
          for (const id of chunk) replies.get(id)!.reject(error);
          return;
        }
        await Promise.all(chunk.map(settleSingle));
        return;
      }
      await Promise.all(chunk.map((id) => {
        if (result.has(id)) {
          replies.get(id)!.resolve(result.get(id)!);
          return;
        }
        return settleSingle(id);
      }));
    }

    const chunks = [];
    for (let start = 0; start < ids.length; start += MAX_BATCH) {
      chunks.push(fetchChunk(ids.slice(start, start + MAX_BATCH)));
    }
    await Promise.all(chunks);
  };

  return (id) => {
    const session = getAuthSessionId();
    let replies = pending.get(session);
    if (!replies) {
      replies = new Map();
      pending.set(session, replies);
      const batch = replies;
      const operation = new Promise<void>((resolve) => {
        setTimeout(() => {
          pending.delete(session);
          void flush(session, batch)
            .catch((error: unknown) => {
              for (const reply of batch.values()) reply.reject(error);
            })
            .finally(resolve);
        }, COLLECTION_MS);
      });
      activeBatches.add(operation);
      void operation.then(() => activeBatches.delete(operation));
    }
    const existing = replies.get(id);
    if (existing) return existing.promise;
    let resolve!: Reply<T>['resolve'];
    let reject!: Reply<T>['reject'];
    const promise = new Promise<T>((ok, fail) => {
      resolve = ok;
      reject = fail;
    });
    replies.set(id, { promise, resolve, reject });
    return promise;
  };
}

function bulkUrl(endpoint: string, ids: number[]) {
  const params = new URLSearchParams({ ids: ids.join(',') });
  return `${endpoint}${endpoint.includes('?') ? '&' : '?'}${params}`;
}

export async function readBulkRecord<T>(endpoint: string, ids: number[]): Promise<Map<number, T>> {
  const response = await request<Record<string, T>>(bulkUrl(endpoint, ids));
  return new Map(Object.entries(response).map(([id, value]) => [Number(id), value]));
}

export function batchedRecord<T>(single: (id: number) => Promise<T>, endpoint: string) {
  return batched(single, (ids) => readBulkRecord<T>(endpoint, ids));
}

export function batchedList<T>(single: (id: number) => Promise<T>, endpoint: string, idOf: (item: T) => number) {
  return batched(single, async (ids) => {
    const response = await request<T[]>(bulkUrl(endpoint, ids));
    return new Map(response.map((value) => [idOf(value), value]));
  });
}
