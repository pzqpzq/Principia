import { useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, dataOrThrow } from '../api/client';

type Catalog = { available?: boolean; models?: string[]; vision_models?: string[]; message?: string };
export function VisionModelField({ value, onChange, models, defaultModel, provider, configured }: {
  value: string; onChange: (model: string) => void; models: string[]; defaultModel: string; provider: string; configured: boolean;
}) {
  const id = useId();
  const [active, setActive] = useState(false);
  const catalog = useQuery({ queryKey: ['provider-model-catalog', provider], enabled: active && configured,
    staleTime: 5 * 60_000, retry: false,
    queryFn: async () => dataOrThrow(await api.GET('/api/v1/provider-profiles/{provider_id}/models', {params:{path:{provider_id:provider}}})) as Catalog });
  const choices = catalog.data?.available ? catalog.data.vision_models || [] : models;
  const unavailable = catalog.data?.available && value.trim() && value !== 'auto' && !catalog.data.models?.includes(value.trim());
  return <div className="vision-model-picker"><label><span>Vision model</span>
    <input aria-label="Vision model" aria-describedby={`${id}-help`} list={id} value={value} onFocus={() => setActive(true)} onChange={event => onChange(event.target.value)} onBlur={() => { if (!value.trim()) onChange('auto'); }} placeholder="auto" />
    <datalist id={id}><option value="auto">Provider default</option>{choices.map(model => <option key={model} value={model} />)}</datalist>
    <small id={`${id}-help`}>{value === 'auto' || !value ? `Auto: ${defaultModel || 'no default configured'}. ` : ''}Choose a listed model or enter a compatible vision model ID. Used for image interpretation.</small>
  </label>
  <div className="vision-model-catalog"><button type="button" disabled={!configured || catalog.isFetching} onClick={() => { setActive(true); void catalog.refetch(); }}>{catalog.isFetching ? 'Loading models…' : 'Refresh model list'}</button><span>{catalog.data?.available ? 'Current provider catalog' : 'Suggested models'}</span></div>
  {unavailable ? <p className="vision-model-note" role="status">This model is absent from the current provider catalog. Choose another model to enable visual interpretation.</p> : catalog.error || catalog.data?.available === false ? <p className="vision-model-note" role="status">{catalog.data?.message || 'The model list could not be refreshed. You can retry or enter a known model ID.'}</p> : null}
  </div>;
}
