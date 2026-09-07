import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/schema";
import { api, dataOrThrow } from "../api/client";
import { FocusDialog, trapDialogFocus } from "./FocusDialog";
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
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = Number(window.localStorage.getItem("principia:sidebar-width"));
    return saved >= 240 && saved <= 600 ? saved : 304;
  });
  const resizeSidebar = (width: number) => {
    const next = Math.round(Math.max(240, Math.min(600, window.innerWidth - 400, width)));
    setSidebarWidth(next);
    window.localStorage.setItem("principia:sidebar-width", String(next));
  };
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [providerOpen, setProviderOpen] = useState(false);
  const [providerId, setProviderId] = useState("siliconflow");
  const [providerModel, setProviderModel] = useState("");
  const [providerKey, setProviderKey] = useState("");
  const [providerMessage, setProviderMessage] = useState("");
  const [sessionQuery, setSessionQuery] = useState("");
  const [sessionScope, setSessionScope] = useState<"recent" | "active" | "all" | "archived">("recent");
  const [sessionLimit, setSessionLimit] = useState(24);
  const [mobileProjectsOpen, setMobileProjectsOpen] = useState(false);
  const mobileProjectsTrigger = useRef<HTMLButtonElement>(null);
  const mobileProjectsSearch = useRef<HTMLInputElement>(null);
  const projectMenuTrigger = useRef<HTMLButtonElement | null>(null);
  const projectMenu = useRef<HTMLDivElement | null>(null);
  const [sessionMenu, setSessionMenu] = useState<{
    session: Record<string, unknown>;
    top: number;
    left: number;
  } | null>(null);
  const [projectDialog, setProjectDialog] = useState<{ session: Record<string, unknown>; action: "rename" | "delete" } | null>(null);
  const [projectTitle, setProjectTitle] = useState("");
  const [projectNotice, setProjectNotice] = useState("");
  useEffect(() => { if (sessionMenu) projectMenu.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus(); }, [sessionMenu]);
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: async () => dataOrThrow(await api.GET("/api/v1/runtime", {})),
  });
  const demoMode = Boolean(runtime.data?.demo_mode);
  const sessions = useQuery({
    queryKey: ["research-sessions", sessionScope === "archived"],
    queryFn: async () =>
      dataOrThrow(
        await api.GET("/api/v1/research-sessions", {
          params: { query: { project_id: null, include_archived: sessionScope === "archived" } },
        }),
      ) as { items?: Array<Record<string, unknown>> },
    refetchInterval: (query) => {
      const items = ((query.state.data as { items?: Array<Record<string, unknown>> } | undefined)?.items ?? []);
      return items.some((item) =>
        ["queued", "running", "paused", "cancelling"].includes(String(item.state || "")),
      )
        ? 2_000
        : 30_000;
    },
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
  const sessionItems = sessions.data?.items ?? [];
  const activeSessionStates = new Set(["queued", "running", "pausing", "paused", "resuming", "cancelling"]);
  const hiddenInRecent = (item: Record<string, unknown>) => {
    const state = String(item.state || "");
    // No findings is normal during startup. Failures also need to stay reachable.
    if (activeSessionStates.has(state) || ["failed", "interrupted", "data_insufficient"].includes(state)) return false;
    return item.is_empty === true || state === "cancelled";
  };
  const matchingSessions = sessionItems.filter((item) => {
    const matchesQuery = `${String(item.display_title || item.title || "")} ${String(item.summary || "")} ${String(item.objective || "")} ${Array.isArray(item.source_labels) ? item.source_labels.join(" ") : ""}`
      .toLocaleLowerCase()
      .includes(sessionQuery.trim().toLocaleLowerCase());
    if (!matchesQuery) return false;
    if (sessionScope === "archived") return Boolean(item.archived_at);
    if (item.archived_at) return false;
    if (sessionScope === "active") return activeSessionStates.has(String(item.state || ""));
    if (sessionScope === "recent")
      return !hiddenInRecent(item);
    return true;
  });
  const hiddenEmptyCount = sessionItems.filter(
    (item) => !item.archived_at && hiddenInRecent(item),
  ).length;
  const visibleSessions = matchingSessions.slice(0, sessionLimit);
  useEffect(() => setSessionLimit(24), [sessionQuery, sessionScope]);
  useEffect(() => {
    if (!mobileProjectsOpen) return;
    const focusSearch = window.requestAnimationFrame(() =>
      mobileProjectsSearch.current?.focus(),
    );
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMobileProjectsOpen(false);
      window.requestAnimationFrame(() => mobileProjectsTrigger.current?.focus());
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      window.cancelAnimationFrame(focusSearch);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileProjectsOpen]);
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
  const updateSession = useMutation({
    mutationFn: async ({
      sessionId,
      revision,
      title,
      archived,
    }: {
      sessionId: string;
      revision: number;
      title?: string;
      archived?: boolean;
    }) => {
      const body: Record<string, unknown> = { expected_revision: revision };
      if (title !== undefined) body.title = title;
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
      const pending = Number((_data as { artifact_cleanup_pending?: number })?.artifact_cleanup_pending || 0);
      setProjectNotice(pending ? `Project deleted. ${pending} generated-result folder${pending === 1 ? "" : "s"} could not be removed; check workspace file permissions.` : "");
      queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["activity-jobs"] });
      if (
        window.location.pathname ===
        `/research/${encodeURIComponent(variables.sessionId)}`
      )
        navigate("/research/new");
    },
  });
  const chooseWorkingDirectory = useMutation({
    mutationFn: async () =>
      dataOrThrow(
        await api.POST("/api/v1/runtime/working-directory/choose", {}),
      ),
    onSuccess: () => window.location.assign("/research/new"),
  });
  const renderSession = (
    session: Record<string, unknown>,
    onSelect?: () => void,
  ) => {
    const sessionId = String(session.session_id);
    const displayTitle = String(session.display_title || session.title || "Untitled research");
    const summary = String(session.summary || "");
    return (
      <div className="sidebar-session" key={sessionId}>
        <NavLink
          to={`/research/${encodeURIComponent(sessionId)}`}
          title={summary ? `${displayTitle} — ${summary}` : displayTitle}
          aria-label={summary ? `${displayTitle}. ${summary}` : displayTitle}
          onClick={onSelect}
        >
          <span className={`sidebar-session-dot ${String(session.state || "ready")}`} aria-hidden="true" />
          <span className="sidebar-session-copy">
            <em>{displayTitle}</em>
            <small>{summary || `${String(session.state || "ready").replaceAll("_", " ")} · ${new Date(String(session.updated_at || session.created_at || Date.now())).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`}</small>
          </span>
          <span className="sidebar-session-hovercard" role="tooltip">
            <strong>{displayTitle}</strong>
            {summary ? <small>{summary}</small> : null}
          </span>
        </NavLink>
        <div className="sidebar-session-actions">
        <button
          type="button"
          className="sidebar-session-menu-trigger"
          aria-label={`Organize ${displayTitle}`}
          aria-haspopup="menu"
          aria-expanded={sessionMenu?.session.session_id === session.session_id}
          onClick={(event) => {
            event.stopPropagation();
            projectMenuTrigger.current = event.currentTarget;
            const bounds = event.currentTarget.getBoundingClientRect();
            const width = 220;
            const height = 132;
            const top = bounds.bottom + 6 + height <= window.innerHeight
              ? bounds.bottom + 6
              : Math.max(12, bounds.top - height - 6);
            setSessionMenu((current) =>
              current?.session.session_id === session.session_id
                ? null
                : {
                    session,
                    top,
                    left: Math.max(12, Math.min(window.innerWidth - width - 12, bounds.right - width)),
                  },
            );
          }}
        >
            ⋯
        </button>
        <button
          type="button"
          className="sidebar-session-delete"
          aria-label={`Delete ${displayTitle}`}
          title="Delete project permanently"
          onClick={(event) => {
            projectMenuTrigger.current = event.currentTarget;
            setProjectDialog({ session, action: "delete" });
            setSessionMenu(null);
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" /></svg>
        </button>
        </div>
      </div>
    );
  };

  useEffect(() => {
    const closeMenus = (event: Event) => {
      if (
        !(event.target instanceof Element) ||
        !event.target.closest(".sidebar-session-popover, .sidebar-session-menu-trigger")
      )
        setSessionMenu(null);
    };
    document.addEventListener("click", closeMenus);
    window.addEventListener("resize", closeMenus);
    window.addEventListener("scroll", closeMenus, true);
    return () => {
      document.removeEventListener("click", closeMenus);
      window.removeEventListener("resize", closeMenus);
      window.removeEventListener("scroll", closeMenus, true);
    };
  }, []);

  const sessionMenuPortal = sessionMenu
    ? createPortal(
        <div
          className="sidebar-session-popover"
          ref={projectMenu}
          role="menu"
          onKeyDown={(event) => {
            const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]'));
            const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
            if (event.key === "Escape") { setSessionMenu(null); projectMenuTrigger.current?.focus(); return; }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); buttons[(index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length]?.focus(); }
          }}
          style={{ top: sessionMenu.top, left: sessionMenu.left }}
        >
          <strong>{String(sessionMenu.session.display_title || sessionMenu.session.title)}</strong>
          <button
            role="menuitem"
            onClick={() => {
              setProjectTitle(String(sessionMenu.session.display_title || sessionMenu.session.title));
              setProjectDialog({ session: sessionMenu.session, action: "rename" });
              setSessionMenu(null);
            }}
          >
            Rename
          </button>
          <button role="menuitem" onClick={() => {
            updateSession.mutate({ sessionId: String(sessionMenu.session.session_id), revision: Number(sessionMenu.session.revision || 1), archived: !Boolean(sessionMenu.session.archived_at) });
            setSessionMenu(null);
          }}>{sessionMenu.session.archived_at ? "Restore" : "Archive"}</button>
          <button
            role="menuitem"
            className="danger"
            onClick={() => {
              setProjectDialog({ session: sessionMenu.session, action: "delete" });
              setSessionMenu(null);
            }}
          >
            Delete permanently
          </button>
        </div>,
        document.body,
      )
    : null;

  const renderSessionFilters = () => (
    <div className="sidebar-session-scope" aria-label="Filter research sessions">
      {sessionScope === "archived" ? <>
        <button type="button" onClick={() => setSessionScope("recent")}>← Projects</button>
        <span className="sidebar-archive-label">Archived</span>
      </> : <>
        {(["recent", "active", "all"] as const).map((scope) => (
          <button key={scope} type="button" className={sessionScope === scope ? "selected" : ""}
            aria-pressed={sessionScope === scope} onClick={() => setSessionScope(scope)}>
            {scope[0].toUpperCase() + scope.slice(1)}
          </button>
        ))}
        <details className="sidebar-project-options" onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.currentTarget.open = false;
            event.currentTarget.querySelector<HTMLElement>("summary")?.focus();
          }
        }}>
          <summary aria-label="Project list options" title="Project list options">⋯</summary>
          <div><button type="button" onClick={(event) => {
            event.currentTarget.closest("details")?.removeAttribute("open");
            setSessionScope("archived");
          }}>View archived projects</button></div>
        </details>
      </>}
    </div>
  );

  return (
    <div className="app-shell" style={{ "--sidebar-width": `${sidebarWidth}px` } as React.CSSProperties}>
      <aside className="sidebar">
        <div role="separator" aria-label="Resize project sidebar" aria-orientation="vertical"
          aria-valuemin={240} aria-valuemax={600} aria-valuenow={sidebarWidth} tabIndex={0}
          className="sidebar-resize-handle"
          onDoubleClick={() => resizeSidebar(304)}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
              event.preventDefault(); resizeSidebar(sidebarWidth + (event.key === "ArrowRight" ? 24 : -24));
            } else if (event.key === "Home") resizeSidebar(240);
            else if (event.key === "End") resizeSidebar(600);
          }}
          onPointerDown={(event) => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); }}
          onPointerMove={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) resizeSidebar(event.clientX); }}
          onPointerUp={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        />
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
          <button
            ref={mobileProjectsTrigger}
            type="button"
            className={`mobile-project-trigger ${mobileProjectsOpen ? "active" : ""}`}
            aria-haspopup="dialog"
            aria-expanded={mobileProjectsOpen}
            onClick={() => setMobileProjectsOpen(true)}
          >
            <span aria-hidden="true">▤</span>
            Projects
          </button>
        </nav>
        <section
          className="research-sidebar-list"
          aria-label="Research sessions"
        >
          <header>
            <span>Projects</span>
            <small title={hiddenEmptyCount ? `${hiddenEmptyCount} empty or cancelled runs are hidden in Recent` : undefined}>
              {sessionScope === "all" ? sessionItems.length : matchingSessions.length}
            </small>
          </header>
          <label className="sidebar-session-search">
            <span className="visually-hidden">Search research sessions</span>
            <input
              type="search"
              value={sessionQuery}
              onChange={(event) => setSessionQuery(event.target.value)}
              placeholder="Find a project…"
            />
          </label>
          {renderSessionFilters()}
          <div className="sidebar-research-items">
            {projectNotice ? <p role="alert">{projectNotice}</p> : null}
            {sessions.isLoading ? <p role="status">Loading projects…</p> : sessions.isError ? <p role="alert">Projects could not be loaded. <button onClick={() => sessions.refetch()}>Retry</button></p> : null}
            {updateSession.isError && !projectDialog ? <p role="alert">Project update failed. Refresh and try again.</p> : null}
            {visibleSessions.map((session) => renderSession(session))}
            {!sessions.isLoading && !sessions.isError && !visibleSessions.length ? (
              <p className="sidebar-session-empty">
                {sessionScope === "active" ? "No research is running." : "No research matches this filter."}
              </p>
            ) : null}
            {sessionScope === "recent" && hiddenEmptyCount ? (
              <button
                type="button"
                className="sidebar-session-hidden-note"
                onClick={() => setSessionScope("all")}
              >
                {hiddenEmptyCount} empty or cancelled run{hiddenEmptyCount === 1 ? "" : "s"} hidden · Show all
              </button>
            ) : null}
            {matchingSessions.length > visibleSessions.length ? (
              <button
                type="button"
                className="sidebar-session-more"
                onClick={() => setSessionLimit((current) => current + 20)}
              >
                Show {Math.min(20, matchingSessions.length - visibleSessions.length)} more
              </button>
            ) : null}
          </div>
        </section>
      <button
        className="provider-trigger"
        aria-label="Open API and model settings"
        title="API and model settings"
        onClick={() => {
          setProviderMessage("");
          setProviderOpen(true);
        }}
      >
        <span aria-hidden="true">⚙</span>
        <strong>API & models</strong>
        <small>
          {activeProvider?.configured ? "Connected" : "Setup needed"}
        </small>
      </button>
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
              Cloud Principles · v{String(runtime.data?.version ?? "1.4.2")}
            </small>
          </div>
          <button
            title="Switch working directory"
            aria-label="Switch working directory"
            onClick={() => chooseWorkingDirectory.mutate()}
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17">
              <path
                d="M3.5 6.5h6l2 2h9v9h-17z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </aside>
      {sessionMenuPortal}
      {projectDialog ? <FocusDialog title={projectDialog.action === "rename" ? "Rename project" : "Delete project"} returnFocus={projectMenuTrigger.current} onClose={() => setProjectDialog(null)}>
        {projectDialog.action === "rename" ? <label>Project name<input value={projectTitle} onChange={(event) => setProjectTitle(event.target.value)} /></label> : <p>Permanently delete this project, its runs, and generated results? Original source files and shared Principles are kept. This cannot be undone.</p>}
        <footer><button onClick={() => setProjectDialog(null)}>Cancel</button><button disabled={updateSession.isPending || deleteSession.isPending || (projectDialog.action === "rename" && !projectTitle.trim())} onClick={() => {
          const variables = { sessionId: String(projectDialog.session.session_id), revision: Number(projectDialog.session.revision || 1) };
          const done = { onSuccess: () => setProjectDialog(null) };
          if (projectDialog.action === "rename") updateSession.mutate({ ...variables, title: projectTitle.trim() }, done);
          else deleteSession.mutate(variables, done);
        }}>{projectDialog.action === "rename" ? "Save name" : "Delete permanently"}</button></footer>
        {updateSession.isError || deleteSession.isError ? <p role="alert">The project could not be updated. Refresh its state and try again.</p> : null}
      </FocusDialog> : null}
      {mobileProjectsOpen ? (
        <div
          className="mobile-project-sheet-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target !== event.currentTarget) return;
            setMobileProjectsOpen(false);
            window.requestAnimationFrame(() => mobileProjectsTrigger.current?.focus());
          }}
        >
          <section
            className="mobile-project-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-project-sheet-title"
            onKeyDown={trapDialogFocus}
          >
            <header>
              <div>
                <span className="eyebrow">Saved research</span>
                <h2 id="mobile-project-sheet-title">Projects</h2>
                <p>Open a previous discovery or continue a running study.</p>
              </div>
              <button
                type="button"
                aria-label="Close projects"
                onClick={() => {
                  setMobileProjectsOpen(false);
                  window.requestAnimationFrame(() => mobileProjectsTrigger.current?.focus());
                }}
              >
                ×
              </button>
            </header>
            <div className="mobile-project-controls">
              <label className="sidebar-session-search">
                <span className="visually-hidden">Search research sessions</span>
                <input
                  ref={mobileProjectsSearch}
                  type="search"
                  value={sessionQuery}
                  onChange={(event) => setSessionQuery(event.target.value)}
                  placeholder="Search projects…"
                />
              </label>
              {renderSessionFilters()}
            </div>
            <div className="mobile-project-list" aria-live="polite">
              {visibleSessions.map((session) =>
                renderSession(session, () => setMobileProjectsOpen(false)),
              )}
              {sessions.isLoading ? (
                <p className="sidebar-session-empty">Loading projects…</p>
              ) : null}
              {!sessions.isLoading && !visibleSessions.length ? (
                <p className="sidebar-session-empty">
                  {sessionScope === "active"
                    ? "No research is running."
                    : "No research matches this filter."}
                </p>
              ) : null}
              {sessionScope === "recent" && hiddenEmptyCount ? (
                <button
                  type="button"
                  className="sidebar-session-hidden-note"
                  onClick={() => setSessionScope("all")}
                >
                  {hiddenEmptyCount} empty or cancelled run{hiddenEmptyCount === 1 ? "" : "s"} hidden · Show all
                </button>
              ) : null}
              {matchingSessions.length > visibleSessions.length ? (
                <button
                  type="button"
                  className="sidebar-session-more"
                  onClick={() => setSessionLimit((current) => current + 20)}
                >
                  Show {Math.min(20, matchingSessions.length - visibleSessions.length)} more
                </button>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}

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
