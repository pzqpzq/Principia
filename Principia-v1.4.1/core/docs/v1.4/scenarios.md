# Scenario Mode

Scenarios are append-only, copy-on-write overlays. They can set maturity, support pressure, a version pin or scope; add a virtual Principle or relation; and disable a relation. Replay and `impact-v1` are deterministic, limited to two hops and 500 nodes, and never update canonical Global or Local Principle tables.

The UI supports create, replay/diff, branch, compare, and discard. The Python surface is available at `Principia.open(...).scenarios`.

For acceptance, compare the logical hash of canonical Principle tables and the exact bytes of installed `.pcp` files before and after scenario work. Scenario tables are expected to change; canonical knowledge is not.
