import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { terminalJobStates } from "./JobProgress";

type Job = components["schemas"]["JobRecord"];
type JobCheckpoint = Record<string, unknown>;

const providerIdentifier = (profile: Record<string, unknown>): string => {
  const value = profile.provider_id ?? profile.provider;
  return typeof value === "string" ? value : "";
};

export function jobDestination(job: Job): { path: string; label: string } {
  const checkpoint = (job.checkpoint ?? {}) as JobCheckpoint;
  const value = (key: string): string =>
    typeof checkpoint[key] === "string" ? String(checkpoint[key]) : "";
  const sourceId = value("source_id");
  const searchId = value("search_id");
  const runId = value("run_id");
  const sessionId = value("session_id");
  if (job.kind === "research_goal_run" && runId) {
    return {
      path: sessionId
        ? `/research/${encodeURIComponent(sessionId)}`
        : `/map?scope=combined&goal_run=${encodeURIComponent(runId)}`,
      label: terminalJobStates.has(job.state)
        ? "Open research"
        : "Open live research",
    };
  }
  if (job.kind === "local_extraction" && sourceId) {
    return {
      path: `/local?stage=results&source=${encodeURIComponent(sourceId)}&job=${encodeURIComponent(job.job_id)}`,
      label: terminalJobStates.has(job.state)
        ? "Review results"
        : "Open live extraction",
    };
  }
  if (job.kind === "literature_search") {
    return {
      path: `/research/new?online_search=${encodeURIComponent(searchId)}&job=${encodeURIComponent(job.job_id)}`,
      label: "Open paper search",
    };
  }
  if (job.kind === "literature_acquisition") {
    return { path: "/research/new", label: "Open downloaded papers" };
  }
  if (job.kind === "local_source_index") {
    return { path: "/research/new", label: "Open local data" };
  }
  if (job.kind === "relation_index")
    return { path: "/research/new", label: "Open graph" };
  return { path: "/research/new", label: "Open activity" };
}

export function Shell() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [providerOpen, setProviderOpen] = useState(false);
  const [providerId, setProviderId] = useState("siliconflow");
  const [providerModel, setProviderModel] = useState("");
  const [providerKey, setProviderKey] = useState("");
  const [providerMessage, setProviderMessage] = useState("");
  const [projectEditorOpen, setProjectEditorOpen] = useState(false);
  const [projectTitle, setProjectTitle] = useState("");
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/runtime", {})),
  });
  const demoMode = Boolean(runtime.data?.demo_mode);
  const projects = useQuery({
    queryKey: ["research-projects"],
    queryFn: async () =>
      dataOrThrow(
        await api.GET("/api/v1/research-projects", {
          params: { query: { include_archived: false } },
        }),
      ) as { items?: Array<Record<string, unknown>> },
  });
  const sessions = useQuery({
    queryKey: ["research-sessions"],
    queryFn: async () =>
      dataOrThrow(
        await api.GET("/api/v1/research-sessions", {
          params: { query: { project_id: null, include_archived: false } },
        }),
      ) as { items?: Array<Record<string, unknown>> },
    refetchInterval: 4_000,
  });
  const cloud = useQuery({
    queryKey: ["cloud-status"],
    queryFn: async () =>
      dataOrThrow(await api.GET("/api/v1/cloud/status", {})) as Record<
        string,
        unknown
      >,
    refetchInterval: 60_000,
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: async () =>
      dataOrThrow(await api.GET("/api/v1/providers", {})) as {
        profiles?: Array<Record<string, unknown>>;
      },
  });
  const providerRows = providers.data?.profiles ?? [];
  const activeProvider =
    providerRows.find((item) => providerIdentifier(item) === providerId) ??
    providerRows[0];
  const providerModels = Array.isArray(activeProvider?.models)
    ? activeProvider.models.map(String)
    : [];
  useEffect(() => {
    if (!providerId || !activeProvider) return;
    const saved = window.localStorage.getItem(`principia:model:${providerId}`);
    setProviderModel(
      saved || String(activeProvider.default_model || providerModels[0] || ""),
    );
  }, [providerId, activeProvider?.default_model]);
  useEffect(() => {
    const openProviderSettings = (event: Event) => {
      const requested = String(
        (event as CustomEvent<{ providerId?: string }>).detail?.providerId ||
          "",
      );
      const requestedModel = String(
        (event as CustomEvent<{ model?: string }>).detail?.model || "",
      );
      if (requested) setProviderId(requested);
      if (requestedModel) {
        setProviderModel(requestedModel);
        window.localStorage.setItem(
          `principia:model:${requested || providerId}`,
          requestedModel,
        );
      }
      setProviderMessage("");
      setProviderOpen(true);
    };
    window.addEventListener(
      "principia:open-provider-settings",
      openProviderSettings,
    );
    return () =>
      window.removeEventListener(
        "principia:open-provider-settings",
        openProviderSettings,
      );
  }, []);
  const applyProviderModel = () => {
    const exactModel = providerModel.trim();
    if (!exactModel) {
      setProviderMessage("Choose or enter the exact model ID first.");
      return;
    }
    window.localStorage.setItem(`principia:model:${providerId}`, exactModel);
    window.dispatchEvent(
      new CustomEvent("principia:provider-model-selected", {
        detail: { providerId, model: exactModel },
      }),
    );
    setProviderMessage(
      `${exactModel} is now the selected ${String(activeProvider?.label || providerId)} model for this research workspace.`,
    );
  };
  const saveProviderKey = useMutation({
    mutationFn: async () => {
      await dataOrThrow(
        await api.PUT("/api/v1/provider-profiles/{provider_id}/credential", {
          params: { path: { provider_id: providerId } },
          body: { api_key: providerKey },
        }),
      );
      const connection = (await dataOrThrow(
        await api.POST("/api/v1/provider-profiles/{provider_id}/test", {
          params: { path: { provider_id: providerId } },
        }),
      )) as Record<string, unknown>;
      if (!connection.ok) {
        if (connection.category === "authentication") {
          await api.DELETE(
            "/api/v1/provider-profiles/{provider_id}/credential",
            { params: { path: { provider_id: providerId } } },
          );
          throw new Error(
            "SiliconFlow rejected this key at both authorized endpoints. Please check the key and enter it again.",
          );
        }
        throw new Error(
          connection.category === "rate_limited"
            ? "The key was accepted, but SiliconFlow is rate-limiting requests. Try again shortly."
            : "The key was saved, but SiliconFlow could not be reached. Check the network and try again.",
        );
      }
      return connection;
    },
    onSuccess: (connection) => {
      setProviderKey("");
      setProviderMessage(
        `API key verified through ${String(connection.base_url || "an authorized endpoint")} and stored privately in this working directory.`,
      );
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      applyProviderModel();
    },
  });
  const createProject = useMutation({
    mutationFn: async () =>
      dataOrThrow(
        await api.POST("/api/v1/research-projects", {
          body: { title: projectTitle.trim() },
        }),
      ),
    onSuccess: () => {
      setProjectTitle("");
      setProjectEditorOpen(false);
      queryClient.invalidateQueries({ queryKey: ["research-projects"] });
    },
  });
  const updateProject = useMutation({
    mutationFn: async ({
      projectId,
      title,
      archived,
    }: {
      projectId: string;
      title?: string;
      archived?: boolean;
    }) =>
      dataOrThrow(
        await api.PATCH("/api/v1/research-projects/{project_id}", {
          params: { path: { project_id: projectId } },
          body: { title: title ?? null, archived: archived ?? null },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["research-projects"] });
      queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
    },
  });
  const updateSession = useMutation({
    mutationFn: async ({
      sessionId,
      revision,
      title,
      projectId,
      archived,
    }: {
      sessionId: string;
      revision: number;
      title?: string;
      projectId?: string | null;
      archived?: boolean;
    }) => {
      const body: Record<string, unknown> = { expected_revision: revision };
      if (title !== undefined) body.title = title;
      if (projectId !== undefined) body.project_id = projectId;
      if (archived !== undefined) body.archived = archived;
      return dataOrThrow(
        await api.PATCH("/api/v1/research-sessions/{session_id}", {
          params: { path: { session_id: sessionId } },
          body: body as never,
        }),
      );
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["research-sessions"] }),
  });
  const deleteSession = useMutation({
    mutationFn: async ({
      sessionId,
      revision,
    }: {
      sessionId: string;
      revision: number;
    }) =>
      dataOrThrow(
        await api.DELETE("/api/v1/research-sessions/{session_id}", {
          params: {
            path: { session_id: sessionId },
            query: { expected_revision: revision },
          },
        }),
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["activity-jobs"] });
      if (
        window.location.pathname ===
        `/research/${encodeURIComponent(variables.sessionId)}`
      )
        navigate("/research/new");
    },
  });
  const deleteProject = useMutation({
    mutationFn: async (projectId: string) =>
      dataOrThrow(
        await api.DELETE("/api/v1/research-projects/{project_id}", {
          params: { path: { project_id: projectId } },
        }),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["research-projects"] }),
  });
  const chooseWorkingDirectory = useMutation({
    mutationFn: async () =>
      dataOrThrow(
        await api.POST("/api/v1/runtime/working-directory/choose", {}),
      ),
    onSuccess: () => window.location.assign("/research/new"),
  });
  const renderSession = (session: Record<string, unknown>) => {
    const sessionId = String(session.session_id);
    const revision = Number(session.revision || 1);
    return (
      <div className="sidebar-session" key={sessionId}>
        <NavLink to={`/research/${encodeURIComponent(sessionId)}`}>
          <span>◦</span>
          <em>{String(session.title)}</em>
        </NavLink>
        <details>
          <summary aria-label={`Organize ${String(session.title)}`}>
            •••
          </summary>
          <div>
            <button
              onClick={() => {
                const title = window.prompt(
                  "Rename this research",
                  String(session.title),
                );
                if (title?.trim())
                  updateSession.mutate({
                    sessionId,
                    revision,
                    title: title.trim(),
                  });
              }}
            >
              Rename
            </button>
            <label>
              <span>Move to</span>
              <select
                value={String(session.project_id || "")}
                onChange={(event) =>
                  updateSession.mutate({
                    sessionId,
                    revision,
                    projectId: event.target.value || null,
                  })
                }
              >
                <option value="">Recent (no project)</option>
                {(projects.data?.items ?? []).map((project) => (
                  <option
                    key={String(project.project_id)}
                    value={String(project.project_id)}
                  >
                    {String(project.title)}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="danger"
              onClick={() => {
                if (
                  window.confirm(
                    `Permanently delete “${String(session.title)}”? Its results, graph, virtual work, and run history will be removed. This cannot be undone.`,
                  )
                )
                  deleteSession.mutate({ sessionId, revision });
              }}
            >
              Delete permanently
            </button>
          </div>
        </details>
      </div>
    );
  };

  useEffect(() => {
    const closeMenus = (event: MouseEvent) => {
      document.querySelectorAll<HTMLDetailsElement>(".research-sidebar-list details[open]").forEach((menu) => {
        if (!menu.contains(event.target as Node)) menu.open = false;
      });
    };
    document.addEventListener("click", closeMenus);
    return () => document.removeEventListener("click", closeMenus);
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            P
          </span>
          <div>
            <strong>Principia</strong>
            <small>Scientific Discovery</small>
          </div>
        </div>
        {demoMode ? <span className="demo-badge">Demo Data</span> : null}
        <nav aria-label="Primary navigation">
          {[{ path: "/research/new", icon: "＋", label: "New Research" }].map(
            (item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                <span aria-hidden="true">{item.icon}</span>
                {item.label}
              </NavLink>
            ),
          )}
        </nav>
        <section
          className="research-sidebar-list"
          aria-label="Research sessions"
        >
          <header>
            <span>Research</span>
            <button
              aria-label="New project"
              onClick={() => setProjectEditorOpen((value) => !value)}
            >
              ＋
            </button>
          </header>
          {projectEditorOpen ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (projectTitle.trim()) createProject.mutate();
              }}
            >
              <input
                autoFocus
                value={projectTitle}
                onChange={(event) => setProjectTitle(event.target.value)}
                placeholder="Project name"
              />
              <button>↵</button>
            </form>
          ) : null}
          {(projects.data?.items ?? []).map((project) => {
            const projectId = String(project.project_id);
            const projectSessions = (sessions.data?.items ?? []).filter(
              (session) => session.project_id === project.project_id,
            );
            return (
              <div className="sidebar-project" key={projectId}>
                <div className="sidebar-project-heading">
                  <strong>⌄ {String(project.title)}</strong>
                  <details>
                    <summary
                      aria-label={`Organize project ${String(project.title)}`}
                    >
                      •••
                    </summary>
                    <div>
                      <button
                        onClick={() => {
                          const title = window.prompt(
                            "Rename this project",
                            String(project.title),
                          );
                          if (title?.trim())
                            updateProject.mutate({
                              projectId,
                              title: title.trim(),
                            });
                        }}
                      >
                        Rename
                      </button>
                      <button
                        className="danger"
                        disabled={projectSessions.length > 0}
                        title={
                          projectSessions.length
                            ? "Delete or move its research sessions first"
                            : "Permanently delete this empty project"
                        }
                        onClick={() => {
                          if (
                            window.confirm(
                              `Permanently delete the empty project “${String(project.title)}”?`,
                            )
                          )
                            deleteProject.mutate(projectId);
                        }}
                      >
                        Delete project
                      </button>
                    </div>
                  </details>
                </div>
                {projectSessions.map(renderSession)}
              </div>
            );
          })}
          <div className="sidebar-project ungrouped">
            <strong>Recent</strong>
            {(sessions.data?.items ?? [])
              .filter((session) => !session.project_id)
              .slice(0, 12)
              .map(renderSession)}
          </div>
        </section>
        <div className="sidebar-footer">
          <span
            className={`status-dot ${runtime.isError ? "danger" : cloud.data?.available ? "online" : "warning"}`}
          />
          <div>
            <strong>
              {runtime.isError ? "Disconnected" : "Local runtime"}
            </strong>
            <small>
              {Number(
                cloud.data?.total_principle_count ??
                  cloud.data?.principle_count ??
                  0,
              ).toLocaleString()}{" "}
              Cloud Principles · v{String(runtime.data?.version ?? "1.4.1")}
            </small>
          </div>
          <button
            title="Switch working directory"
            onClick={() => chooseWorkingDirectory.mutate()}
          >
            ⌘
          </button>
        </div>
      </aside>
      <button
        className="provider-trigger"
        onClick={() => {
          setProviderMessage("");
          setProviderOpen(true);
        }}
      >
        <span aria-hidden="true">⌁</span>
        <strong>API & models</strong>
        <small>
          {activeProvider?.configured ? "Connected" : "Setup needed"}
        </small>
      </button>
      {providerOpen ? (
        <div
          className="provider-settings-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setProviderOpen(false);
          }}
        >
          <aside
            className="provider-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-label="API and model settings"
          >
            <header>
              <div>
                <span className="eyebrow">Private workspace settings</span>
                <h2>API & models</h2>
                <p>
                  Connect an OpenAI-compatible provider for local extraction and
                  virtual reasoning. Keys never enter the Global Cloud.
                </p>
              </div>
              <button
                aria-label="Close API settings"
                onClick={() => setProviderOpen(false)}
              >
                ×
              </button>
            </header>
            <label>
              <span>Provider</span>
              <select
                value={providerId}
                onChange={(event) => {
                  setProviderId(event.target.value);
                  setProviderMessage("");
                }}
              >
                {providerRows.map((item) => {
                  const id = providerIdentifier(item);
                  return (
                    <option key={id} value={id}>
                      {String(item.label || id)} ·{" "}
                      {item.configured ? "connected" : "not connected"}
                    </option>
                  );
                })}
              </select>
            </label>
            <div
              className={`provider-connection-state ${activeProvider?.configured ? "connected" : ""}`}
            >
              <span
                className={`status-dot ${activeProvider?.configured ? "online" : "warning"}`}
              />
              <div>
                <strong>
                  {activeProvider?.configured
                    ? "Ready for LLM tasks"
                    : "API key required"}
                </strong>
                <small>
                  {String(
                    activeProvider?.base_url || "OpenAI-compatible endpoint",
                  )}
                </small>
              </div>
            </div>
            <label>
              <span>Model</span>
              <input
                list="principia-provider-models"
                value={providerModel}
                onChange={(event) => {
                  setProviderModel(event.target.value);
                  setProviderMessage("");
                }}
                placeholder="Exact provider model ID"
                autoComplete="off"
              />
              <datalist id="principia-provider-models">
                {providerModels.map((modelId) => (
                  <option key={modelId} value={modelId} />
                ))}
              </datalist>
              <small className="provider-model-note">
                Choose a listed {String(activeProvider?.label || providerId)} model,
                or enter an exact model ID supported by this provider.
              </small>
            </label>
            <button
              className="secondary full"
              disabled={!providerModel.trim()}
              onClick={applyProviderModel}
            >
              Use this model
            </button>
            <label>
              <span>
                {activeProvider?.configured ? "Replace API key" : "API key"}
              </span>
              <input
                type="password"
                autoFocus
                value={providerKey}
                onChange={(event) => setProviderKey(event.target.value)}
                placeholder="Stored in the OS-backed local credential store"
                autoComplete="off"
              />
            </label>
            <button
              className="primary full"
              disabled={providerKey.length < 8 || saveProviderKey.isPending}
              onClick={() => saveProviderKey.mutate()}
            >
              {saveProviderKey.isPending
                ? "Saving & verifying…"
                : activeProvider?.configured
                  ? "Replace key"
                  : "Save API key"}
            </button>
            {providerMessage ? (
              <p className="inline-success" role="status">
                {providerMessage}
              </p>
            ) : null}
            {saveProviderKey.error ? (
              <p className="field-error" role="alert">
                {saveProviderKey.error instanceof Error
                  ? saveProviderKey.error.message
                  : "The key could not be saved."}
              </p>
            ) : null}
          </aside>
        </div>
      ) : null}
      <main className="workspace">
        <Outlet />
      </main>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="header-actions">{actions}</div> : null}
    </header>
  );
}
