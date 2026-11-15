# coldchain-rf-v1.0.0

Synthetic-data advisory excursion detector. Target: whether a policy-defined true excursion is active at the prediction timestamp. This is current-state classification, not forecasting.

Selected validation candidate: `rf_deeper`. Threshold: `0.7`; consecutive windows: `3`. Validation event precision 0.9286, recall 0.8125, false alarms/journey 0.0333.

The model only supports review. It cannot establish product safety or authorize quality release, quarantine or warehouse activity. Synthetic simulator behavior may not represent real sensors, routes, products or prevalence.
