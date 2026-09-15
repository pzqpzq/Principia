# P100-037: Carrier-router power under packet and load changes

How do traffic load and operating history affect measured router power?

Source: https://zenodo.org/records/17282065

Version: 17282065

Measurement coverage: Physical lab experiments released 2025-10-06; native DateTime columns give run-specific observation times.

Data origin: measured_or_observed

Source processing: Instrument/lab-measurement CSV exports with source traffic-control settings; energy is not directly a separate measured response unless time integration is performed later.

Interpretation limits: The source was collected for network-equipment energy modeling. Throughput, packet size and packet rate have structural dependencies. Run histories and repeated rows cannot be treated as independent laboratory replicates. Fifteen router-power CSVs; time-correlated operating transients must stay within run groups.

Terms: Creative Commons Attribution 4.0 International (CC BY 4.0)
