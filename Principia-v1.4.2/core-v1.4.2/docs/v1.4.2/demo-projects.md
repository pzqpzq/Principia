# Public discovery demos

The v1.4.2 demo distribution includes five projects from the twenty independent
public test scenarios, analyzed with DeepSeek-V4-Pro through SiliconFlow. Three
were selected in the initial twenty-scenario campaign; two additional projects
were retained by the project owner after local testing. The private
TJ scenario is excluded. See the bundled `src/principia/demo_projects/manifest.json`
for the selected projects, public source links, and attribution.

Open Principia and select a demo in the sidebar. Its Map, Results, observations,
Rules, equations, calibration metrics, test receipts, and derived figures are
stored locally. Browsing them does not require the author's data folders, API
key, or a remote inference call. Public literature links require internet access.

These are curated examples of interpretable data analysis. They do not imply
that all twenty scenarios succeeded, that the retained rules are newly discovered
laws of nature, or that retrospective validation is prospective confirmation.
Read each rule's scope, baselines, dependence assumptions, and limitations.

## Included examples

| Project | Compact relationship | Recorded validation | Interpretation |
| --- | --- | --- | --- |
| Hafnia wafer measurements | Spatial thickness response across a measured wafer | Held-out normalized RMSE 0.7471; 41.1% below a constant baseline | A specimen-specific spatial fit; replication on another wafer is pending. |
| Walking dynamics | Contact moment from normal load and pressure-center displacement | Promoted with recorded executable calibration and test receipts | A force-plate coordinate consistency rule, not a new biological mechanism. |
| Rydberg electric-field calibration | $E_r(P)=b_r+\kappa_r\sqrt{P}$ | Held-out RMSE 0.0825 and 0.0923 V/m for optical and ion readouts; 93.4% and 92.4% below their development-mean baselines | Two separately calibrated atomic readouts share a field-amplitude scaling form. |
| Earthquake magnitude scaling | $S(M)=\exp[-\beta(M-2.5)]$, $\beta\approx2.605$ | 18 development, 6 validation, and 7 test days; test normalized RMSE 0.1267 versus 0.6584 for the frozen linear baseline | One fitted rate describes conditional magnitude-exceedance fractions in the retained catalog. |
| ATLAS transverse momentum | $p_T=\sqrt{p_x^2+p_y^2}$ | Six period files; 78,227 events in two held-out files; 99th-percentile relative magnitude error approximately $1.17\times10^{-7}$ | A parameter-free vector identity checks the consistency of missing-momentum representations. |

The Rydberg example contains only two locked test power settings per readout;
the channels share an RF chain and are not independent apparatus replications.
Its calibration should not be extrapolated to a new power range or RF chain.
The earthquake example uses only the `ml` magnitude scale and days with at least
three recorded events above the query cutoff. That cutoff is not an independently
verified completeness threshold; aftershocks and geographic mixture can create
dependence. It estimates magnitude frequencies, not earthquake times or locations.
The ATLAS example recovers known geometry. Shared upstream reconstruction limits
its role to representation consistency, rather than independent detector or
new-particle validation.

Open **Dataset & evidence** in each project for its selection rationale and
publisher link. Open a Rule for the full-precision calibration, frozen split,
baseline comparison, negative controls, executable expression, and limitations.
Displayed rounding leaves the underlying numerical receipts unchanged.

## Discover from your own data

1. Open **New research**, then **Add data** and choose a local folder.
2. Enter your research goal and configure your own provider and API key in
   **Sources & model**. Select the reasoning and vision models you want to use.
3. Start discovery and approve the provider request for that run.
4. Use **View activity** to inspect progress, models, source sizes, and stop controls.

Raw files stay in your selected folder. The ASD dependencies are installed with
`pip install '.[asd,local]'` from the source directory. Provider credentials are
saved only in your private workspace.

## Repeat or remove a demo

**Discover again** keeps the original project by default. Add local data to run
a new attempt; the packaged source entries are provenance records, not connected
folders. The manifest links to the public publishers so you can obtain the source
datasets. A new run uses your own credentials and permission.

Delete a demo through its project menu to remove it from your workspace. It will
not return on restart. Bundled demos install once, only into an empty workspace
at UI startup. An existing workspace is never populated automatically with them.

## Portability and evidence

The release carries a compressed, checksummed data bundle rather than an old
runtime database. It includes selected study records, executable equation ASTs,
calibrations, validation decisions, linked evidence, graph records, and bounded
derived artifacts. It omits raw source folders, provider secrets, retrieved paper
files, caches, and bulk numerical intermediates. It does not execute imported code.

Scientific receipt digests identify the original computation. Machine paths are
redacted in exported copies; bundle and artifact hashes identify those portable
copies separately. Numerical results and scientific gates are not rewritten to
make a project qualify for the showcase. Original inputs must be reconnected for
full computational reproduction.
