import { useMemo } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { api, type PrintQueueHistoryFilters, type PrintQueueItem } from '../api/client';

const PAGE_SIZE = 50;

export function useQueueHistory(
  filters: PrintQueueHistoryFilters,
  sortBy: 'date' | 'name' | 'printer',
  reverse: boolean,
  active: boolean,
) {
  const summary = useQuery({
    queryKey: ['queue', 'history-summary', filters],
    queryFn: () => api.getQueueHistory({ ...filters, limit: 0 }),
    enabled: !active,
  });
  const pages = useInfiniteQuery({
    queryKey: ['queue', 'history', filters, sortBy, reverse],
    queryFn: ({ pageParam }) => api.getQueueHistory({ ...filters, sortBy, reverse, limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, _pages, offset) => {
      const next = offset + last.items.length;
      return last.items.length && next < last.total ? next : undefined;
    },
    enabled: active,
    refetchInterval: active ? 30_000 : false,
  });

  const { items, relatedItems } = useMemo(() => {
    const primary = new Map<number, PrintQueueItem>();
    const related = new Map<number, PrintQueueItem>();
    for (const page of pages.data?.pages ?? []) {
      for (const item of page.items) primary.set(item.id, item);
      for (const item of page.related_items) related.set(item.id, item);
    }
    for (const id of primary.keys()) related.delete(id);
    return { items: [...primary.values()], relatedItems: [...related.values()] };
  }, [pages.data]);

  const current = active ? pages.data?.pages[0] ?? summary.data : summary.data;
  return {
    items,
    relatedItems,
    total: current?.total ?? 0,
    locations: current?.locations,
    isLoading: pages.isLoading,
    isError: pages.isError,
    canShowMore: pages.hasNextPage,
    isFetchingMore: pages.isFetchingNextPage,
    showMore: pages.fetchNextPage,
  };
}
