const PHASES = ["inventory", "understand", "analyze", "challenge", "synthesize"] as const;

export function DataDiscoveryPhases({
  phase,
  complete = false,
  runState = "",
}: {
  phase: string;
  complete?: boolean;
  runState?: string;
}) {
  const current = Math.max(0, PHASES.indexOf(phase as (typeof PHASES)[number]));
  return (
    <ol className="data-phases" aria-label="Discovery phases">
      {PHASES.map((value, index) => {
        const stopped = ["failed", "cancelled", "interrupted"].includes(runState);
        const state = stopped
          ? index < current ? "done" : index === current ? "stopped" : "pending"
          : complete
          ? "done"
          : index < current
            ? "done"
            : index === current
              ? "active"
              : "pending";
        return (
          <li key={value} className={state} aria-current={state === "active" ? "step" : undefined}>
            <span>{index + 1}</span>
            {value}
            <small className="visually-hidden">{state}</small>
          </li>
        );
      })}
    </ol>
  );
}
