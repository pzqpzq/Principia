import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({ ...await importOriginal<typeof import("../api/client")>(), api: { GET: mock.get, POST: mock.post, PATCH: mock.patch }, dataOrThrow: (response: { data?: unknown; error?: unknown }) => {
  if (response.error) throw new Error("The server could not be reached");
  return response.data;
} }));
vi.mock("../components/ResearchGraph", () => ({ ResearchGraph: ({ items }: { items: Array<{ principle_id: string }> }) => <div data-testid="graph-nodes">{items.map(item => <span key={item.principle_id}>{item.principle_id}</span>)}</div> }));
vi.mock("../components/CloudStatusControl", () => ({ CloudStatusControl: () => <span>Cloud ready</span> }));
import { ResearchWorkspacePage } from "./ResearchWorkspacePage";

let client: QueryClient;
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  focusManager.setFocused(true);
  vi.stubGlobal("EventSource", class { close() {} addEventListener() {} removeEventListener() {} });
  localStorage.clear();
});
afterEach(() => { cleanup(); client.clear(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

function open(path: string) {
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/research/new" element={<ResearchWorkspacePage />} /><Route path="/research/:sessionId" element={<ResearchWorkspacePage />} /></Routes>
  </MemoryRouter></QueryClientProvider>);
}

describe("research workspace lifecycle", () => {
  it("shows pending submission and its error inside the local-folder consent dialog", async () => {
    let finish: (response: { error: string }) => void = () => {};
    const source = { source_id: "src:trial", display_name: "Calibration data", readiness: "ready", documents: 1, status_counts: {} };
    mock.get.mockImplementation(async (path: string) => ({ data: path === "/api/v1/providers"
      ? { profiles: [{ provider: "siliconflow", configured: true, models: [] }] }
      : { items: [], sources: [source] } }));
    mock.post.mockImplementation(async (path: string) => path.endsWith("/multiple")
      ? { data: { sources: [source] } }
      : new Promise(resolve => { finish = resolve; }));
    open("/research/new");
    fireEvent.click(await screen.findByText("Add data"));
    fireEvent.click(screen.getByText("Add local folders"));
    fireEvent.change(screen.getByLabelText("Research goal"), { target: { value: "Explain the calibration response" } });
    fireEvent.click(await screen.findByText("Discover data"));
    const dialog = screen.getByRole("dialog", { name: "Discover from local data" });
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.click(within(dialog).getByText("Start discovery"));
    expect(await within(dialog).findByText("Starting…")).not.toBeNull();
    finish({ error: "offline" });
    await waitFor(() => expect(within(dialog).getByRole("alert").textContent).toContain("server could not be reached"));
    expect(within(dialog).getByText("Start discovery").hasAttribute("disabled")).toBe(false);
  });

  it("keeps refreshing until the owning session publishes the graph", async () => {
    let published = false;
    mock.get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/research-sessions") return { data: { items: [{ session_id: "search", kind: "research", state: published ? "succeeded" : "running" }] } };
      if (path.endsWith("/{session_id}")) return { data: { session_id: "search", state: published ? "succeeded" : "running", active_run_id: "run:one", active_run: { run_id: "run:one", state: "succeeded", goal: "Find scientific relationships" } } };
      if (path.endsWith("/graph")) return { data: { revision: published ? 1 : 0, items: published ? [{ principle_id: "prn:automatic", payload: { title: "Published Principle" } }] : [] } };
      return { data: { items: [], sources: [], profiles: [] } };
    });
    open("/research/search");
    await screen.findByText("Preparing the map and publishing search results…");
    expect(screen.queryByText("Your study map is empty")).toBeNull();
    published = true;
    await screen.findByText("prn:automatic", {}, { timeout: 5000 });
    expect(mock.post).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByLabelText("Search progress")).toBeNull());
  });

  it("shows lightweight progress in Map and refreshes final results without an SSE connection", async () => {
    let complete = false;
    const study = { study_id: "study:one", session_id: "local", state: "running", phase: "execute", created_at: new Date().toISOString(), job: {} };
    mock.get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/research-sessions") return { data: { items: [{ session_id: "local", kind: "data_discovery", state: "running", active_data_study: { study_id: "study:one" } }] } };
      if (path.endsWith("/workspace")) return { data: { project: { title: "Synthetic local data" }, selected_run: { ...study, state: complete ? "succeeded" : "running" }, runs: [study], records: [], graph: { items: complete ? [{ principle_id: "finding:ready", payload: { title: "Computed finding" } }] : [] } } };
      if (path.endsWith("/status")) return { data: { ...study, state: complete ? "succeeded" : "running", counts: { tests: 9, supported_findings: complete ? 1 : 0 }, job: { state: complete ? "succeeded" : "running", status_message: complete ? "Results are ready" : "Checking nine candidate tests", last_activity_at: new Date().toISOString() } } };
      if (path.endsWith("/{study_id}")) return { data: { ...study, state: complete ? "succeeded" : "running" } };
      return { data: { items: [], sources: [], profiles: [] } };
    });
    open("/research/local?run=study%3Aone&surface=map");
    const progress = await screen.findByLabelText("Discovery progress");
    await waitFor(() => expect(progress.textContent).toContain("9 tests completed"));
    expect(progress.textContent).toContain("Checking nine candidate tests");
    expect(screen.queryByText("Your study map is empty")).toBeNull();
    expect(progress.closest(".research-toolbar")).not.toBeNull();
    complete = true;
    await screen.findByText("Discovery complete", {}, { timeout: 6000 });
    await screen.findByText("finding:ready", {}, { timeout: 6000 });
    fireEvent.click(screen.getByText("View results"));
    expect(screen.getByLabelText("Project workspace view").textContent).toContain("Results");
  });

  it("surfaces failed status polling instead of silently appearing stalled", async () => {
    mock.get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/research-sessions") return { data: { items: [{ session_id: "local", kind: "data_discovery", state: "running" }] } };
      if (path.endsWith("/{study_id}")) return { data: { study_id: "study:one", state: "running" } };
      if (path.endsWith("/status")) return { error: "offline" };
      return { data: { items: [], sources: [], profiles: [] } };
    });
    open("/research/local?run=study%3Aone&surface=map");
    await screen.findByText("Progress connection interrupted");
    expect(screen.getByText("Reconnect")).not.toBeNull();
  });
});

function mockLocalProject(complete: () => boolean, withRule = false, demo = false) {
  const source = { source_id:'src:first', display_name:'Measured signals', readiness:'ready', status:demo?'demo':'ready', documents:1, status_counts:{} };
  const rule = () => ({rule_id:'law:live', record_kind:'data_rule', title:'Linear response with history', expression_latex:'y=a x+b', scientific_law:true, finding_id:complete()?'finding:ready':'', finding_pending:!complete(), test:{passed:true, normalized_rmse:.12}, interpretation:'History predicts the next measurement.', parameter_estimates:{}, test_ids:['test:live']});
  const study = () => ({study_id:'study:one', session_id:'local', state:complete()?'succeeded':'running', phase:'synthesize', request:{objective:'Predict the next signal',source_ids:['src:first'], provider:'siliconflow', reasoning_model:'old-model',vision_model:'vision-previous',...(demo?{portable_demo:{raw_data_included:false}}:{})}, source_ids:['src:first'], created_at:new Date().toISOString()});
  mock.get.mockImplementation(async (path: string) => {
    if(path==='/api/v1/providers')return {data:{profiles:[{provider:'siliconflow', configured:true, models:['old-model','new-model']}]}};
    if(path==='/api/v1/research-sessions')return {data:{items:[{session_id:'local',kind:'data_discovery',state:study().state,revision:7,source_ids:['src:first'],provider_profile_id:'siliconflow',model:'old-model'}]}};
    if(path.endsWith('/{session_id}'))return {data:{session_id:'local',kind:'data_discovery',title:'Measured signals',revision:7,source_ids:['src:first'],active_data_study:study(),data_runs:[study()],provider_profile_id:'siliconflow',model:'old-model'}};
    if(path.endsWith('/workspace'))return {data:{project:{title:'Measured signals'},selected_run:study(),runs:[study()],records:withRule?[{record_id:'law:live',record_kind:'data_rule',category:'rules',payload:rule()}]:[],graph:{items:[]}}};
    if(path.endsWith('/{study_id}')||path.endsWith('/status'))return {data:{...study(),counts:{},job:{}}};
    if(path.endsWith('/rules'))return {data:{items:withRule?[rule()]:[],candidates:[]}};
    if(path.endsWith('/laws/{law_id}'))return {data:{law_id:'law:live',tests:[{test_id:'test:live',estimate:{r_squared:.9}}]}};
    if(path.endsWith('/findings/{finding_id}'))return complete()?{data:{finding_id:'finding:ready',title:'Reviewed context',claim:'The response is stable.',interpretation:'Context is complete',mechanism:'Empirical relationship'}}:{error:'unknown data finding'};
    return {data:{items:[],sources:[source],profiles:[]}};
  });
}

it('opens a live Rule without requesting a missing finding, then hydrates its completed context', async () => {
  let complete=false;
  mockLocalProject(()=>complete,true);
  open('/research/local?run=study%3Aone&surface=results&tab=rules&record=law%3Alive');
  const dialog=await screen.findByRole('dialog',{name:'Linear response with history'});
  await within(dialog).findByText('General symbolic form');
  expect(dialog.querySelector('.katex')).not.toBeNull();
  expect(mock.get.mock.calls.some(call=>String(call[0]).endsWith('/findings/{finding_id}'))).toBe(false);
  complete=true;
  await client.invalidateQueries({queryKey:['canonical-workspace']});
  await within(dialog).findByText('Context is complete',{}, {timeout:8000});
  expect(screen.queryByText(/unknown data finding/)).toBeNull();
});

it('defaults Discover again to a separate project and submits edited inputs', async () => {
  mockLocalProject(()=>true);
  mock.post.mockResolvedValue({error:'test submission boundary'});
  open('/research/local?run=study%3Aone');
  const button=await screen.findByRole('button',{name:'Discover again'});
  await waitFor(()=>expect(button.hasAttribute('disabled')).toBe(false));
  fireEvent.click(button);
  const dialog=screen.getByRole('dialog',{name:'Discover again'});
  expect((within(dialog).getByRole('radio',{name:/New project/}) as HTMLInputElement).checked).toBe(true);
  fireEvent.change(within(dialog).getByLabelText('Research goal'),{target:{value:'Predict a changed response'}});
  fireEvent.change(within(dialog).getByLabelText('Reasoning model'),{target:{value:'new-model'}});
  expect((within(dialog).getByLabelText('Vision model') as HTMLInputElement).value).toBe('vision-previous');
  fireEvent.change(within(dialog).getByLabelText('Vision model'),{target:{value:'vision-custom'}});
  fireEvent.click(within(dialog).getByLabelText('I allow this provider request for this run only.'));
  fireEvent.click(within(dialog).getByText('Start discovery'));
  await waitFor(()=>expect(mock.post).toHaveBeenCalled());
  const request=mock.post.mock.calls.find(call=>call[0]==='/api/v1/data-discoveries')![1].body;
  expect(request).toMatchObject({project_mode:'new',objective:'Predict a changed response',reasoning_model:'new-model',vision_model:'vision-custom',source_ids:['src:first']});
  fireEvent.click(within(dialog).getByRole('radio',{name:/Overwrite current project/}));
  fireEvent.click(within(dialog).getByText('Start discovery'));
  await waitFor(()=>expect(mock.post.mock.calls.filter(call=>call[0]==='/api/v1/data-discoveries').length).toBe(2));
  expect(mock.post.mock.calls.filter(call=>call[0]==='/api/v1/data-discoveries')[1][1].body).toMatchObject({project_mode:'replace',session_id:'local',expected_session_revision:7});
});

it('requires connected local data before rerunning a portable demo', async () => {
  mockLocalProject(()=>true, false, true);
  open('/research/local?run=study%3Aone');
  await screen.findByText('Public demo project');
  const button=await screen.findByRole('button',{name:'Discover again'});
  await waitFor(()=>expect(button.hasAttribute('disabled')).toBe(false));
  fireEvent.click(button);
  const dialog=screen.getByRole('dialog',{name:'Discover again'});
  expect(within(dialog).getByText(/original dataset is not bundled/)).not.toBeNull();
  expect(within(dialog).queryByRole('checkbox',{name:'Measured signals'})).toBeNull();
  fireEvent.click(within(dialog).getByLabelText('I allow this provider request for this run only.'));
  expect(within(dialog).getByText('Start discovery').hasAttribute('disabled')).toBe(true);
  expect(mock.post).not.toHaveBeenCalled();
});

it('keeps Semantic Cloud search open through successive graph additions', async () => {
  const principles = ['one','two'].map(id=>({id:`prn:${id}`,entity:'principle',title:`Principle ${id}`,claim:`Measured ${id}`}));
  const graph: Array<Record<string,unknown>>=[];
  mock.get.mockImplementation(async (path:string)=>{
    if(path==='/api/v1/research-sessions') return {data:{items:[{session_id:'search',kind:'research',state:'succeeded'}]}};
    if(path.endsWith('/{session_id}')) return {data:{session_id:'search',state:'succeeded',active_run:{state:'succeeded',goal:'Explore relationships'}}};
    if(path.endsWith('/graph')) return {data:{revision:graph.length,items:[...graph]}};
    if(path.endsWith('/principles/search')) return {data:{items:principles,total:2}};
    return {data:{items:[],sources:[],profiles:[]}};
  });
  mock.patch.mockImplementation(async (_path:string, options:{body:{operations:Array<Record<string,unknown>>}})=>{
    for(const operation of options.body.operations) if(operation.action==='add') graph.push({...operation,record_kind:'principle'});
    return {data:{revision:graph.length}};
  });
  open('/research/search');
  await screen.findByText('Your study map is empty');
  fireEvent.click(screen.getByRole('button',{name:'＋ Add Principle'}));
  const dialog=screen.getByRole('dialog',{name:'Semantic Cloud search'});
  const input=within(dialog).getByPlaceholderText('Search mechanisms, applications, or scientific questions');
  fireEvent.change(input,{target:{value:'measurement'}});
  fireEvent.click(within(dialog).getByRole('button',{name:'Search'}));
  await within(dialog).findByText('Principle one');
  fireEvent.click(within(dialog).getAllByRole('button',{name:'Add to graph'})[0]);
  await within(dialog).findByText('Added to the map. You can continue adding Principles.');
  expect((input as HTMLInputElement).value).toBe('measurement');
  fireEvent.click(within(dialog).getByRole('button',{name:'Add to graph'}));
  await waitFor(()=>expect(graph.length).toBe(2));
  expect(screen.getByRole('dialog',{name:'Semantic Cloud search'})).toBe(dialog);
  expect(within(dialog).getAllByRole('button',{name:'Added · show on graph'})).toHaveLength(2);
  fireEvent.click(within(dialog).getByRole('button',{name:'Close'}));
  expect(screen.queryByRole('dialog',{name:'Semantic Cloud search'})).toBeNull();
});


it('refreshes activity inventory while faster status polling continues', async () => {
  mockLocalProject(() => false);
  const original = mock.get.getMockImplementation()!;
  let detailReads = 0;
  mock.get.mockImplementation(async (path: string) => {
    const response = await original(path);
    if(path.endsWith('/{study_id}')) {
      detailReads++;
      return {data:{...response.data, coverage:detailReads > 1 ? {asset_count:2,total_bytes:2048,sources:[{source_id:'src:first',asset_count:2,total_bytes:2048}]} : {}}};
    }
    return response;
  });
  open('/research/local?run=study%3Aone&surface=map');
  fireEvent.click((await screen.findAllByRole('button',{name:'View activity'}))[0]);
  const dialog=await screen.findByRole('dialog',{name:'Discovery activity'});
  await within(dialog).findByText('2 files · 2 KiB',{}, {timeout:6500});
  expect(detailReads).toBeGreaterThan(1);
  expect(mock.get.mock.calls.filter(call=>String(call[0]).endsWith('/status')).length).toBeGreaterThan(1);
  expect(within(dialog).getByText('old-model')).not.toBeNull();
}, 10000);

it('keeps generated hypotheses out of the connection studio without losing the principle draft', async () => {
  const principles = ['one', 'two'].map(id => ({
    principle_id: `prn:${id}`, record_kind: 'principle',
    payload: { title: `Principle ${id}`, claim: `Measured ${id}` },
  }));
  mock.get.mockImplementation(async (path: string) => {
    if (path === '/api/v1/providers') return { data: { profiles: [{ provider: 'siliconflow', configured: true, models: [] }] } };
    if (path === '/api/v1/research-sessions') return { data: { items: [{ session_id: 'search', kind: 'research', state: 'succeeded' }] } };
    if (path.endsWith('/{session_id}')) return { data: { session_id: 'search', state: 'succeeded', active_run: { state: 'succeeded', goal: 'Explore relationships' } } };
    if (path.endsWith('/graph')) return { data: { revision: 1, items: principles } };
    return { data: { items: [], sources: [], profiles: [] } };
  });
  mock.post.mockResolvedValue({ data: { items: [{ virtual_id: 'virtual:one', proposal: { title: 'Generated hypothesis', claim: 'A falsifiable connection' } }] } });
  open('/research/search');
  await screen.findByText('prn:one');
  fireEvent.click(screen.getByRole('button', { name: 'Derive Principles' }));
  fireEvent.click(screen.getByRole('button', { name: 'Add Principle one to selection' }));
  fireEvent.click(screen.getByRole('button', { name: 'Add Principle two to selection' }));
  fireEvent.click(screen.getByRole('button', { name: 'Derive virtual Principles' }));
  await screen.findByText('Generated hypothesis');
  fireEvent.click(screen.getByRole('button', { name: 'Derive connection' }));
  expect(screen.queryByText('Generated hypothesis')).toBeNull();
  expect(screen.queryByText('Virtual hypothesis')).toBeNull();
  expect(screen.getByRole('button', { name: 'Manage Principles' }).textContent).toBe('Manage Principles');
  fireEvent.click(screen.getByRole('button', { name: 'Derive Principles' }));
  expect(screen.getByText('Generated hypothesis')).not.toBeNull();
});

it('samples the initial map again on reopening, without search or focus resampling', async () => {
  let samples = 0;
  mock.get.mockImplementation(async (path: string) => {
    if (path === '/api/v1/cloud/graph/sample') {
      samples += 1;
      return { data: { seeds: [{id:`prn:seed-${samples}`}],
        nodes: [{id:`prn:seed-${samples}`,title:'Sampled Principle'}, {id:'prn:neighbor',title:'Direct neighbor'}],
        edges:[{source:`prn:seed-${samples}`,target:'prn:neighbor'}] } };
    }
    return { data: { items:[],sources:[],profiles:[] } };
  });
  const first = open('/research/new');
  await screen.findByText('prn:seed-1');
  expect(screen.getByText('prn:neighbor')).not.toBeNull();
  expect(screen.queryByLabelText('Search Principles by meaning')).toBeNull();
  focusManager.setFocused(false);
  focusManager.setFocused(true);
  await waitFor(() => expect(samples).toBe(1));
  first.unmount();
  open('/research/new');
  await screen.findByText('prn:seed-2');
  expect(mock.get.mock.calls.some(call => call[0] === '/api/v1/cloud/graph/search')).toBe(false);
});

it('allows Custom without an AI provider and saves human provenance through the existing API', async () => {
  const graph = ['one','two'].map(id=>({principle_id:`prn:${id}`,payload:{title:`Principle ${id}`}}));
  mock.get.mockImplementation(async (path: string) => {
    if(path==='/api/v1/research-sessions')return {data:{items:[{session_id:'search',kind:'research',state:'succeeded'}]}};
    if(path.endsWith('/{session_id}'))return {data:{session_id:'search',state:'succeeded',active_run:{state:'succeeded',goal:'Explore relationships'}}};
    if(path.endsWith('/graph'))return {data:{revision:1,items:graph}};
    return {data:{items:[],sources:[],profiles:[]}};
  });
  mock.post.mockResolvedValue({data:{candidate_id:'cand:custom'}});
  mock.patch.mockResolvedValue({data:{revision:2}});
  open('/research/search');
  await screen.findByText('prn:one');
  fireEvent.click(screen.getByRole('button',{name:'Derive Principles'}));
  fireEvent.click(screen.getByRole('button',{name:'Custom'}));
  expect(screen.queryByText('Add API key')).toBeNull();
  expect(screen.queryByPlaceholderText('Search results to add')).toBeNull();
  expect(screen.queryByText('Selected · 0/20')).toBeNull();
  expect(screen.queryByRole('button', {name:'Add Principle one to selection'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'AI Polish'}));
  expect(screen.getByPlaceholderText('Search results to add')).not.toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Custom'}));
  for(const label of ['Title','Claim','Scope statement','Falsifier','Synthesis summary','Reliability rationale','Novelty rationale'])
    fireEvent.change(screen.getByLabelText(label),{target:{value:`${label} describes a bounded scientific hypothesis.`}});
  fireEvent.change(screen.getByLabelText('Area'),{target:{value:'test-area'}});
  for(const label of ['Reliability score','Novelty score'])fireEvent.change(screen.getByLabelText(label),{target:{value:'70'}});
  fireEvent.submit(screen.getByRole('button',{name:'Save locally & add to graph'}).closest('form')!);
  await screen.findByText('Custom Principle saved locally and added to the graph.');
  const saved=mock.post.mock.calls.find(call=>String(call[0]).endsWith('/virtual-principles/save'));
  expect(saved?.[1].body).toMatchObject({provider:'human',model:'custom',proposal:{contributing_principle_ids:[]}});
  expect(mock.post.mock.calls.some(call=>String(call[0]).endsWith('/generate'))).toBe(false);
  expect(mock.patch).toHaveBeenCalledWith('/api/v1/research-sessions/{session_id}/graph', expect.objectContaining({
    body: expect.objectContaining({operations: expect.arrayContaining([expect.objectContaining({action:'add', principle_id:'cand:custom'})])}),
  }));
});
