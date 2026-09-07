// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { graphSaveMessage, persistGraphOperations, retryableGraphError } from "./graphPersistence";
vi.mock('../api/client', async importOriginal => ({...await importOriginal<typeof import('../api/client')>(), api:{PATCH:vi.fn(), GET:vi.fn()}}));
beforeEach(() => vi.clearAllMocks());
it('refreshes a stale revision once and preserves the exact user operations', async () => {
  const conflict = {error:{category:'integrity',message:'graph revision conflict; reload before saving'}};
  vi.mocked(api.PATCH).mockResolvedValueOnce({error:conflict} as never).mockResolvedValueOnce({data:{revision:9}} as never);
  vi.mocked(api.GET).mockResolvedValueOnce({data:{revision:8}} as never);
  const revisions = new Map([['session:1', 2]]);
  const operations = [{action:'remove',principle_id:'principle:1'}];
  await persistGraphOperations('session:1', operations, revisions);
  expect((vi.mocked(api.PATCH).mock.calls[1][1] as {body:unknown})?.body).toEqual({expected_revision:8,operations});
  expect(revisions.get('session:1')).toBe(9);
});
it('does not endlessly retry or claim to queue a permanent save error', async () => {
  vi.mocked(api.PATCH).mockResolvedValue({error:{category:'integrity', message:'unknown graph theme'}} as never);
  await expect(persistGraphOperations('session:1', [], new Map())).rejects.toThrow('unknown graph theme');
  expect(api.PATCH).toHaveBeenCalledTimes(1);
  const error = new ApiError({category:'security', message:'Read only'});
  expect(retryableGraphError(error)).toBe(false);
  expect(graphSaveMessage(error)).not.toContain('Saved on this device');
  expect(retryableGraphError(new TypeError('Failed to fetch'))).toBe(true);
});
