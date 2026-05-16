# DataStorm 7.0: Latent Maximum Monthly Volume Potential Estimation
## Team: Code_Stomers
### Final Technical Summary Report

---

*(PAGE BREAK)*

## Page 1: Executive Summary

### 1.1 Objective
The objective of this project is to accurately estimate the **Maximum Monthly Purchase Potential** (in liters) for 20,000 traditional trade retail outlets for the target month of January 2026. 

### 1.2 The Core Challenge: Censored Demand
Historical sales data alone is insufficient to predict true market potential. The observed historical volume is **left-censored**—it represents only the minimum of either the *True Demand* or the *Systemic Constraints* (e.g., credit limits, logistics delivery caps, stockouts, or physical cooler capacity). As a result, highly constrained outlets appear deceptively low in historical volume. 

Because there is no explicit target variable ($y$), we framed this as an unsupervised estimation challenge. Our solution mathematically infers the hidden ceiling by uncapping constrained outlets and benchmarking them against unconstrained peer groups in similar micro-environments.

### 1.3 Solution Architecture overview
We implemented a robust, production-grade **Lakehouse Architecture** to process the data, broken into three strict layers:
1. **Bronze (Ingestion)**: Byte-for-byte exact copies of the raw extract.
2. **Silver (Forensics & Hygiene)**: Parametric Data Quality (DQ) checks, standardizing typological errors, resolving spatial anomalies, and computationally quarantining invalid records.
3. **Gold (Feature Engineering)**: Enrichment via 3 distinct external data sources (OpenStreetMap, Open-Meteo, Spatial Clustering) resulting in a model-ready matrix of 57 features.

The final prediction utilizes a **4-Method Hybrid Ensemble** blending statistical heuristics (Quantile Uncapping, K-Means Peer Benchmarking, Constraint Uplift) with a supervised **LightGBM** gradient boosting model trained exclusively on unconstrained outlets.

---

*(PAGE BREAK)*

## Page 2: Data Forensics and Hygiene

### 2.1 The Lakehouse Quarantine System
Many analytical pipelines fail by silently dropping problematic rows (e.g., using `.dropna()`). In our Silver layer, we instituted a strict **Quarantine System**. Every record that fails a Data Quality check is preserved and computationally routed to a `rejected_records/` store. Each quarantined row is tagged with a specific `DQ_Failure_Reason` and timestamp, ensuring 100% transparency.

### 2.2 Reusable Data Quality Framework
Rather than hardcoding file-specific cleaning scripts, we developed a reusable Python module (`src/dq_checks.py`). This framework applies generic, parameterizable tests across all datasets:
- **Referential Integrity**: Ensuring every transaction maps to a valid Outlet and Distributor.
- **Value Bounds**: Identifying physically impossible numerical volumes.
- **Geospatial Boundaries**: Verifying coordinates fall within the exact bounding box of Sri Lanka (Lat: 5.9–9.9, Lon: 79.4–82.0).

### 2.3 Specific System Anomalies Trapped & Resolved
Through our forensic analysis, we neutralized several system artifacts that would have poisoned the latent potential model:

1. **Transaction Ghost Entries**: We quarantined 100 records reporting precisely zero volume.
2. **Reverse Logistics (Returns)**: We flagged and quarantined 4,753 transactions with negative `Volume_Liters`. These represent credit notes and product returns, not true consumer demand, and heavily skew statistical averages if left unchecked.
3. **Typological Inconsistencies**: We programmatically standardized over 1,500 string errors in the Outlet Master (e.g., mapping `Bakry` $\rightarrow$ `Bakery`, stripping leading whitespace from ` Eatery `, and fixing casing errors like `small` $\rightarrow$ `Small`).
4. **Spatial Inversions**: We detected 200 outlets where the Latitude and Longitude values were accidentally swapped (creating latitudes > 50°). We applied a mathematical transposition to repair these coordinates rather than dropping them.
5. **Null Coordinates**: 40 outlets reporting coordinates of exactly (0.0, 0.0) were quarantined.

---

*(PAGE BREAK)*

## Page 3: POI Data Acquisition

To accurately execute peer benchmarking, we needed to map the external micro-environment of each outlet. True latent potential is heavily driven by foot traffic, climate, and localized commercial density. We built three automated pipelines to pull and map external data.

### 3.1 Geospatial Scraping via OpenStreetMap (Overpass API)
Pulling data for 20,000 distinct coordinates typically triggers severe rate-limiting from public APIs. Instead of querying per-outlet, we engineered a **Batch Bounding-Box Strategy**. 
- We defined a rectangular geospatial grid encompassing Sri Lanka.
- We fetched all bulk POIs within that bounding box from the Kumi Systems Overpass API mirror.
- We computationally calculated the Haversine distance from every POI to our internal outlets, aggregating counts within a 1km catchment radius.

**Targeted POI Catchment Drivers**:
We successfully mapped over 32,000 POIs to the internal outlets across 10 distinct categories, specifically targeting:
- *Youth/Daily Foot Traffic*: Schools (2,628 found), Transit/Bus Stops (1,951 found).
- *Steady/Captive Traffic*: Hospitals (818 found), Banks (2,083 found).
- *Commercial Density*: Shops (10k+ found), Markets (224 found), Restaurants (3,581 found).

### 3.2 Climate Data (Open-Meteo API)
Beverage demand is causally linked to thirst and temperature. We integrated the Open-Meteo API to extract historical January climate data. To minimize API payload, we deduplicated the 20,000 outlets into 428 unique spatial grid cells, fetching the **January Average Temperature** and **January Total Precipitation** for each cell and mapping it back to the outlets.

### 3.3 Population Density Proxy (Spatial Clustering)
As high-resolution census data is difficult to align with arbitrary coordinates, we engineered a proxy for population density using the internal outlet network itself. Using a vectorized Haversine distance matrix, we calculated the total count of competing/adjacent outlets within a 500m, 1km, and 2km radius of every given shop, alongside the exact distance in kilometers to the nearest neighboring outlet.

---

*(PAGE BREAK)*

## Page 4: Causal Base Logic

### 4.1 Defining the Left-Censored Demand Curve
Our mathematical approach assumes historical data is a censored representation of true potential: $V_{obs} = \min(Demand_{true}, Constraint)$. Standard regression models fail here because they fit to the *average* of the censored data, naturally underpredicting the true ceiling. We designed a **4-Method Hybrid Ensemble** to calculate the uncapped potential.

### 4.2 Method 1: Quantile-Based Uncapping (Base Ceiling)
For outlets with sufficient historical data, the periods where constraints were least binding represent the truest observation of potential. 
- **Logic**: We calculate the 95th percentile ($P_{95}$) of historical monthly volumes for each outlet. We use $P_{95}$ rather than the absolute maximum to filter out extreme, one-off outlier spikes (such as a massive wholesale purchase or data error).
- **Growth Modifier**: We calculate an Ordinary Least Squares (OLS) slope over the 36-month period. For mathematically growing outlets, we apply a square-root momentum modifier to extrapolate the ceiling for 2026.

### 4.3 Method 2: Peer Benchmarking (K-Means)
Outlets with identical physical and environmental characteristics should theoretically have identical ceilings. 
- **Logic**: We utilized K-Means ($K=20$) to cluster outlets based on our 57 scaled features (Cooler Count, Size, POI Density, Temperature, Province). 
- **Uplift**: Within each cluster, we identify the high-performing "frontier" ($P_{75}$ of the cluster). Underperforming outlets are mathematically lifted to meet their peer group's frontier, removing systemic constraints tied to bad management or poor logistics.

### 4.4 Method 3: Constraint Detection & Capacity Uplift
We computationally flag outlets whose observed distributions prove they are hitting a hard physical or credit limit.
- **Signals**: We calculate the Coefficient of Variation ($CV = \frac{\sigma}{\mu}$) for monthly volume. Outlets with $CV < 0.3$ exhibit unnaturally flat variance, indicating a hard monthly cap. Similarly, if an outlet's $P_{95} / Max\_Volume > 0.95$, the distribution has a flat, truncated top.
- **Uplift**: Flagged outlets receive a volumetric multiplier based on physical capacity proxies (specifically, Cooler Count and ordinal Outlet Size).

### 4.5 Method 4: ML Ceiling Prediction (LightGBM)
To move beyond pure heuristics, we trained a **LightGBM gradient boosting regressor** (300 trees, max depth 6) exclusively on the 9,835 unconstrained outlets (CV > 0.3), where observed volumes closely approximate true latent demand. This model learns the non-linear relationship between the 57 environmental and transactional features and the demand ceiling. We then predict the ceiling for all 20,000 outlets, including the 10,165 constrained ones where heuristics alone would underpredict. Top features learned by the model: `txn_std_monthly_volume`, `txn_avg_monthly_volume`, `txn_min_monthly_volume`.

### 4.6 Final Hybrid Aggregation
The final latent potential uses **differentiated weighting** based on constraint status. For constrained outlets, ML and Constraint methods receive 70% of the weight. For unconstrained outlets, Quantile and ML methods dominate. Finally, we multiply the output by the outlet's specific January distributor seasonality index, producing the final `Maximum_Monthly_Liters` prediction for January 2026.

---

*(PAGE BREAK)*

## Page 5: GenAI Transparency Log

Generative AI (specifically Anthropic's Claude / Deepmind's Antigravity) was strategically utilized as an engineering accelerator during the 36-hour hackathon. All AI-generated outputs were critically evaluated, iteratively prompted, and rigorously validated against the raw data.

| Timestamp | Process Stage | How AI Was Utilized | Human Validation & Refinement |
| :--- | :--- | :--- | :--- |
| **May 15, 20:00** | Data Exploration & Forensics | Assisted in initial schema inspection and generating Python code for fast anomaly detection. | Cross-verified all AI-calculated row counts and statistics against the raw CSV files; manually validated the existence of coordinate inversions. |
| **May 15, 21:00** | Architecture Design | Brainstormed the repository structure to enforce strict Lakehouse (Bronze/Silver/Gold) separation. | Team reviewed the generated folder hierarchy against the competition rubric, adjusting boundaries to fit the exact deliverable constraints. |
| **May 15, 22:30** | Boilerplate Generation | Generated the structural boilerplate for the `src/dq_checks.py` framework to speed up typing. | Heavily refactored the generic AI functions to handle FMCG-specific edge cases (e.g., writing the custom logic to mathematically fix lat/lon swaps). |
| **May 16, 02:00** | Causal Math Ideation | Brainstormed statistical approaches to solving the left-censored demand curve. | Evaluated AI suggestions (Tobit regression vs. Quantile Uncapping). We manually chose to discard Tobit in favor of Peer Benchmarking due to time constraints and mathematical defensibility. |
| **May 16, 06:00** | API Scraping Optimization | Re-wrote the OpenStreetMap Overpass API scraper. The initial per-outlet script hit rate limits; AI assisted in rewriting it to use a vectorized Bounding Box approach. | Ran the script iteratively in a test environment; manually confirmed that the resulting 32,000 POIs were accurately mapped via Haversine distance to the 20,000 outlets. |
| **May 16, 10:00** | ML Model Integration | Integrated LightGBM as Method 4 in the hybrid ensemble. Trained on unconstrained outlets to predict the demand ceiling for constrained outlets. | Validated that size ordering held (Small < Medium < Large < XL), 100% of predictions exceeded historical average, and all 8 automated validation checks passed. |
| **May 16, 12:00** | Documentation & Reporting | Assisted in formatting the Markdown documentation (`architecture.md`, `README.md`) based on the team's completed work. | Manually audited all numbers, feature counts (57), and validation results in the documentation to ensure perfect accuracy. |
