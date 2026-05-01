import { apiFetch } from './contracts/shared';
import type { Tag } from '@/state/tags';

export interface FetchAllTagsResponse {
  tags: Tag[];
  attachments: Record<string, string[]>;
}

export const tagsApi = {
  fetchAll: (): Promise<FetchAllTagsResponse> =>
    apiFetch<FetchAllTagsResponse>('/api/tags'),

  create: (input: { name: string; color: string }): Promise<Tag> =>
    apiFetch<Tag>('/api/tags', { method: 'POST', body: JSON.stringify(input) }),

  delete: (id: string): Promise<void> =>
    apiFetch<void>(`/api/tags/${encodeURIComponent(id)}`, { method: 'DELETE' }).then(() => undefined),

  attach: (conceptId: string, tagId: string): Promise<void> =>
    apiFetch<void>(`/api/concepts/${encodeURIComponent(conceptId)}/tags/${encodeURIComponent(tagId)}`, { method: 'POST' }).then(() => undefined),

  detach: (conceptId: string, tagId: string): Promise<void> =>
    apiFetch<void>(`/api/concepts/${encodeURIComponent(conceptId)}/tags/${encodeURIComponent(tagId)}`, { method: 'DELETE' }).then(() => undefined),
};
