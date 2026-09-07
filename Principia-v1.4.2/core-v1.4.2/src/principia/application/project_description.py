"""Short, local display descriptions. Never used for scientific dispatch."""

from __future__ import annotations

import re
from typing import Any


def describe_project(labels: list[str], blueprint: dict[str, Any]) -> tuple[str, str]:
    """Explain source metadata without presenting a hypothesis as a result."""
    label = " + ".join(labels[:2]) or "Local data"
    label = re.sub(r"^Discovery\s*·\s*", "", label, flags=re.I)
    label = re.sub(r"^\d{1,3}[\s_.·-]+", "", label)
    label = re.sub(r"\b(?:gse\d+|sector\d+|\d{5,})\b", "", label, flags=re.I)
    label = " ".join(label.replace("_", " ").split()).strip(" ·-")
    # These are presentation vocabulary, not executor applicability rules.
    subjects = (
        ("oeis", "Integer sequences", "Integer sequences and their recurrence and growth patterns."),
        ("tars", "Stellar light curves", "Stellar brightness measurements over time, including variability and periodic signals."),
        ("gwosc", "Gravitational-wave strain", "Detector strain time series, quality masks, and the frequency structure of the measured signal."),
        ("atlas", "Particle collision kinematics", "Four-lepton collision events and their measured momentum and angular relationships."),
        ("multiomics", "Host–microbe measurements", "Host and microbial measurements for investigating relationships between biological responses."),
        ("rydberg", "Rydberg RF sensing", "Radio-frequency power and atomic-sensor responses used to calibrate electric-field measurements."),
        ("gait", "Walking dynamics", "Recorded walking signals for comparing movement timing, periodicity, and coordination."),
        ("tcia", "Breast imaging", "Medical image series and their acquisition geometry; image measurements require an explicit anatomical target."),
        ("dandi", "Neural activity recordings", "Neuroscience recordings with time-aligned activity and acquisition metadata."),
        ("nvd", "Software vulnerabilities", "Published vulnerability records, severity measures, and affected software characteristics."),
        ("mlperf", "Inference performance", "Machine-learning inference benchmarks across models, systems, and test configurations."),
        ("hafnia", "Hafnia wafer measurements", "Wafer characterization measurements for examining spatial variation and material structure."),
        ("encapsulant", "Encapsulant curing", "Thermal and curing measurements for investigating reaction kinetics and temperature dependence."),
        ("htops", "Household survey responses", "Household survey responses for examining economic conditions and reported experiences."),
        ("shed", "Household financial well-being", "Household survey measures of financial circumstances, spending, and economic well-being."),
        ("bls", "Prices and employment", "Economic time series for studying price changes and employment dynamics."),
        ("comcat", "Earthquake patterns", "Earthquake locations, times, and magnitudes for studying event distributions and clustering."),
        ("storm", "Storm impacts", "Storm-event records and reported human impacts, with linked event and fatality information."),
        ("nhtsa", "Vehicle safety", "Vehicle-safety records across reporting channels for examining their agreement and coverage."),
        ("coral", "Ocean temperature anomalies", "Gridded sea-surface temperature anomalies for examining large-scale spatial patterns."),
        ("shd", "Thin-film thickness distribution", "Paired process and film-thickness measurements across wafers and operating conditions."),
    )
    for token, title, summary in subjects:
        if token in label.casefold().split() or token == "shd" and "shd" in label.casefold():
            return title, summary
    targets = list(dict.fromkeys(str(x.get("variable") or x.get("name") or "") for x in (blueprint.get("target_bindings") or [])))
    targets = [x for x in targets if x][:3]
    title = label[:1].upper() + label[1:]
    summary = f"Measurements of {', '.join(targets)} in {title}." if targets else f"Data from {title}, with source measurements and context for scientific analysis."
    return title[:96], summary[:320]
