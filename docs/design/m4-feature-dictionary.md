# M4 observable feature dictionary

Feature schema: `coldchain-window-v1`. Order in `feature_spec.json` is authoritative and is asserted by the feature builder. All temperatures use °C, durations use minutes, slopes use units per hour. The input is a 60-minute window ending at prediction time. Temperature inputs are observed sensor readings only; context inputs are observed context records only. Every record must have both `event_at` and `received_at` no later than prediction time.

| Order | Feature | Definition |
|---:|---|---|
| 1 | `temperature_mean_c` | Arithmetic mean of observed window temperatures; zero only when no readings, which then abstains. |
| 2 | `temperature_min_c` | Minimum observed temperature; zero only when empty. |
| 3 | `temperature_max_c` | Maximum observed temperature; zero only when empty. |
| 4 | `temperature_std_c` | Population standard deviation of observed temperatures. |
| 5 | `temperature_last_c` | Temperature at greatest eligible `event_at`. |
| 6 | `temperature_range_c` | Observed maximum minus minimum. |
| 7 | `temperature_slope_c_per_hour` | Endpoint temperature change divided by elapsed observed hours; zero for fewer than two points. |
| 8 | `largest_step_c` | Largest absolute change between adjacent event-time readings. |
| 9 | `observed_above_max_sample_minutes` | Five minutes per observed sample strictly above policy maximum, capped at the 60-minute window span. Sample-equivalent evidence, not interpolated exposure duration. |
| 10 | `observed_below_min_sample_minutes` | Five minutes per observed sample strictly below policy minimum, capped at the window span. |
| 11 | `longest_out_of_range_run_minutes` | Longest same-direction observed run, broken by an in-range reading or an event-time gap over 7m30s; duration is last minus first event time. |
| 12 | `observed_reading_count` | Number of eligible temperature readings. |
| 13 | `missing_fraction` | `1 - observed_count / 13`; absent and not-yet-received slots both remain unavailable in this as-of view. |
| 14 | `coverage_ratio` | `min(1, observed_count / 13)`. It does not imply product safety. |
| 15 | `longest_observed_gap_minutes` | Largest excess over the nominal five-minute interval between adjacent eligible readings; no value is filled. |
| 16 | `spike_score_c` | Maximum absolute local residual from the median of the current point and its immediate observed neighbors within the available window. No point after prediction time is available. |
| 17 | `ambient_mean_c` | Mean of reported ambient context values received by prediction time; no ambient value is imputed. |
| 18 | `product_minus_ambient_mean_c` | Mean paired observed product-minus-ambient temperature difference. |
| 19 | `door_open_fraction` | Fraction of reported door states marked OPEN. |
| 20 | `battery_min_pct` | Minimum reported battery percentage. |
| 21 | `battery_slope_pct_per_hour` | Endpoint slope of reported battery level over elapsed hours. |
| 22 | `latest_received_age_minutes` | Prediction time minus receipt time of the latest eligible temperature reading. |
| 23 | `ambient_observation_count` | Number of ambient observations used. |
| 24 | `door_observation_count` | Number of door observations used. |
| 25 | `battery_observation_count` | Number of battery observations used. |

Missing context is encoded as 0 for the associated summary plus its explicit observation count. The frozen preprocessing median-imputer and missing indicators remain in the model pipeline. Route, upload cadence, upload IDs, scenario, shipment/journey identity, sensor identity, labels, hidden truth and partition metadata are excluded. Route/upload metadata was excluded because it is simulator-correlated and unnecessary for the excursion target.
