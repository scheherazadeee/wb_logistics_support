# WB Logistics — Inventory Distribution Decision Support System

A web-based decision support system for optimising inventory allocation across Wildberries fulfilment warehouses. Built as a course project using real seller data. *Data was provided by a WB marketplace seller and used with permission for academic purposes only. The dataset is not publicly available*

---

## What it does


| Module            | Description                                                                                  |
| ----------------- | -------------------------------------------------------------------------------------------- |
| **Dashboard**     | Portfolio KPIs — total stock, critical SKU count, 26-week sales chart, activity feed         |
| **SKU Portfolio** | Full article list sorted by stockout risk with risk donut chart                              |
| **Geo Analytics** | Interactive map of WB warehouses with delivery/storage coefficients; regional demand heatmap |
| **SKU Analyzer**  | Per-article stockout simulation and demand history                                           |
| **Optimizer**     | LP-based allocation — minimises storage cost + lost-sales cost simultaneously                |


---

## Tech stack

**Backend** — Python 3.12, FastAPI, SQLAlchemy, PostgreSQL  
**Optimisation** — PuLP (CBC solver)  
**Demand models** — LightGBM, Holt-Winters (statsmodels), baseline models  
**Frontend** — Vanilla JS, Chart.js 4, Leaflet  
**Data ingestion** — Wildberries Seller API v1, Celery

---

## Project structure

```
wb_logistics_support/
├── backend/
│   └── main.py          # FastAPI app — all /api/* endpoints
├── frontend/
│   ├── WB Logistics.html
│   ├── app.js
│   └── style.css
├── src/
│   ├── ingestion/       # WB API client, raw data loaders, Celery tasks
│   ├── preprocessing/   # Data normalisation
│   ├── demand_model/    # Baseline, Holt-Winters, LightGBM, backtest
│   ├── simulation/      # Stockout simulation
│   ├── optimization/    # LP allocation (PuLP)
│   └── cost_model/      # Storage & stockout cost functions
├── scripts/             # One-off backfill scripts
├── notebooks/           # EDA and model analysis
├── db/
│   └── schema.sql       # PostgreSQL schema
├── config/
│   └── celery_config.py
└── requirements.txt
```

---

## Data & WB API

This project uses the **Wildberries Seller API** to collect historical data. The following endpoints were used during data collection:


| WB API endpoint                              | Data collected                                 | Table                |
| -------------------------------------------- | ---------------------------------------------- | -------------------- |
| `POST /api/v1/supplier/reportDetailByPeriod` | Weekly realization report (sales & returns)    | `realization_report` |
| `POST /api/v1/warehouse_remains`             | Current stock per warehouse                    | `warehouse_remains`  |
| `POST /api/v1/paid_storage`                  | Daily paid storage with warehouse coefficients | `paid_storage`       |
| `GET /api/v1/analytics/region-sale`          | Sales by region                                | `region_sale`        |
| `GET /api/v1/tariffs/box`                    | Live delivery & storage tariffs                | used at runtime      |


> **Note:** The app starts and the UI is fully functional, but without the data the dashboard will be empty.  
> To run with data you need a WB seller account and a valid `WB_API_KEY`.

---

## Setup

### 1. Prerequisites

- Python 3.12+
- PostgreSQL 14+
- A Wildberries seller account with API access *(required for data collection; not required to just start the server)*

### 2. Clone & install

```bash
git clone https://github.com/<your-username>/wb-logistics-support.git
cd wb-logistics-support
pip install -r requirements.txt
```

### 3. Environment

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://localhost/wb_logistics
WB_API_KEY=your_wildberries_api_key
```

`WB_API_KEY` is your Wildberries seller token from *Личный кабинет → Настройки → Доступ к API*.  
If the key is absent or invalid the app still runs — live tariffs degrade gracefully to historical values stored in `paid_storage`.

### 4. Database schema

```bash
psql -d wb_logistics -f db/schema.sql
```

### 5. Populate data *(optional — requires WB_API_KEY)*

```bash
python scripts/backfill.py          # historical realization report
```

Or run the Celery ingestion tasks for incremental updates.

### 6. Run

```bash
uvicorn backend.main:app --reload
```

Open **[http://localhost:8000](http://localhost:8000)**

---

## API reference


| Method | Path               | Description                                               |
| ------ | ------------------ | --------------------------------------------------------- |
| `GET`  | `/api/overview`    | Dashboard KPIs + 26-week sales chart                      |
| `GET`  | `/api/skus`        | Full SKU portfolio with stockout risk                     |
| `GET`  | `/api/sku/{nm_id}` | Single SKU detail + stockout simulation                   |
| `GET`  | `/api/warehouses`  | Warehouse list with tariff coefficients + regional demand |
| `POST` | `/api/optimize`    | LP allocation for a given SKU and supply quantity         |
| `GET`  | `/api/docs`        | Interactive Swagger UI                                    |


---

## Notes

- All queries use `SNAPSHOT = "2024-12-31"` as the reference date — the system reflects the exact state of the seller's inventory at year-end 2024.
- The LP optimiser minimises `Σ storage_cost × units + Σ lost_margin × unmet_demand` subject to a supply cap.
- Demand is forecast as a rolling average over the 4 weeks prior to the snapshot date, normalised by the number of calendar weeks in the window (not just weeks with sales) to avoid overstating demand for stocked-out SKUs.

