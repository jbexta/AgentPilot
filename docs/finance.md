# Finance Plugin

The Finance plugin (`src/plugins/finance`) is a crypto/market-data and portfolio-tracking plugin. It syncs asset, market, trade and price data from external APIs, stores portfolio records in a dedicated SQLite database, stores price history in HDF5 files, and presents everything through a `Finance` page with charts and tables.

Declared in `plugin.toml` (requires the `workflows` plugin) with dependencies: `binance-sdk-spot`, `coingecko-sdk`, `h5py`, `pyqtgraph`.

## Data Storage

### finance.db (SQLite)

A separate database, `finance.db`, located next to the main `data.db` (opened via `SqliteConnector` wherever needed). Tables:

| Table | Purpose |
|---|---|
| `apis` | Registry of external APIs (Binance = 5, CoinGecko = 31, TwelveData = 33, Massive = 34, Revolut X = 35) |
| `assets` | One row per asset per API (`api_id` + `api_asset_id`). `group_to` links duplicate assets across APIs to a canonical asset. `metadata` and `last_update` are JSON columns; `last_price` is in GBP |
| `api_markets` | Trading pairs per API (`market_id`, base/quote asset ids and symbols) |
| `trades` | Portfolio trades: sold/received/fee asset + amounts, exchange, unix, `ignored` flag |
| `depwiths` | Fund deposits/withdrawals (`depwith` 0 = deposit, 1 = withdrawal) per user, with shares (`ins_shares`), BTC amounts and asset amounts |
| `users` | Fund participants |
| `exchange_depwiths` | Per-exchange deposit/withdrawal transfers, used by the Fund Map's "marriage" matching (`married_id` links a withdrawal to its matching deposit) |
| `files` | file_id → file_path mapping |

**Balance model:** an asset's balance is never stored — it is always derived as *(deposits − withdrawals from `depwiths`) + (received − sold − fees from `trades`)*, aggregated onto the canonical asset via `COALESCE(group_to, id)`. This same aggregation appears in the Portfolio pie chart, the Assets tab, and `utils/assets.py` (with a `unix < ?` cutoff for point-in-time balances).

### HDF5 price files (`connectors/h5.py`)

Price history lives on disk under `DATA_DIR` (hardcoded `/media/jb/DATA`), as `PRICE/<API>/<API>_<MARKET>.h5`. `tea_kinds` defines the dataset structures:

- `trades` — raw trades (unix ns, trade_id, price, vol, buyer_is_maker)
- `ohlc` / `ohlcv` — candles per interval, stored as `ohlc/<seconds>` datasets
- `line` — daily price/market-cap/volume series (CoinGecko)

Key pieces:

- `PriceFile` — wrapper class around one .h5 file. Detects its base structure (trades / ohlc / line), exposes `append_batch()`, `get_available_intervals()`, `get_interval_data()`, `binary_search_unix_price(unix)` (price lookup at a timestamp), and `generate_intervals()` which incrementally aggregates candles for 1m→1Y intervals, each interval built from the largest smaller interval that divides it (vectorized with numpy `reduceat`, chunked, resumable from the last candle).
- `create_h5_file` / `create_h5_dataset` / `append_h5_dataset` — gzip-compressed, chunked, resizable datasets.
- `normalize_timestamp()` — normalizes s/ms/µs/ns timestamps to nanoseconds.
- `get_h5_path(api, market)` — canonical file path resolution.

## API Modules (`apis/`)

All inherit `FinanceAPI` (`apis/__init__.py`), which holds a DB connection + `api_id` and provides `get_existing_assets()`, `get_existing_markets()`, and `set_last_update()` (stamps a JSON field in `assets.last_update`). Each API implements some of: `sync()`, `sync_assets()`, `sync_asset_metadata()`, `sync_history()`, `sync_prices()`.

- **CoingeckoAPI** (id 31) — the primary source. Syncs the full coin list into `assets`, creates `<coin>_usd` markets, fetches per-coin metadata (rate-limited), writes daily `line` history to h5 (basic API keys limited to past ~2 years), and `sync_prices()` updates `assets.last_price` in GBP for currently *held* assets (crypto via `/simple/price`, fiat via exchange rates), applying the price to the whole `group_to` group. Uses `COINGECKO_DEMO_API_KEY` or `COINGECKO_API_KEY`.
- **BinanceAPI** (id 5) — syncs exchange info into assets/markets, then per market backfills full raw trade history: bulk-downloads daily zip archives from `data.binance.vision`, merges CSVs into the h5 `trades` dataset (verifying trade-id contiguity), tops up via the REST `historical_trades` endpoint, then regenerates OHLC intervals. Supports cooperative cancellation via `request_stop()`. Currently runs against a hardcoded market list in `sync_history()`. Uses `BINANCE_API_KEY`/`BINANCE_SECRET_KEY`.
- **TwelveDataAPI** (id 33) — stocks/forex/ETFs; assets, metadata, daily OHLCV history to h5, plus real-time price / indicator / fundamentals helpers. Note: some queries still use MySQL-style `%s` placeholders and legacy column names, so parts are not SQLite-ready.
- **RevolutXAPI** (id 35) — Revolut X exchange; signed requests (`REVOLUT_X_API_KEY` + DER private key), syncs pairs into assets/markets and trades.
- **`_revolut_api.py`, `_massive_api.py`** — underscore-prefixed = not loaded as modules; legacy/incomplete.

The `finance_apis` module type is registered by `controllers/finance_apis.py`, which loads modules to `plugins.finance.apis`. Three more controllers exist but are disabled (underscore-prefixed): `finance_operations`, `finance_features`, `finance_strategies`.

## Background Sync (`daemons/finance.py`)

`FinanceDaemon` is loaded by the DaemonManager. It creates a `finance.db` connector plus CoinGecko/Binance API instances and runs selected sync jobs under an `asyncio.TaskGroup` (currently only `coingecko.sync_history()` is enabled; others are commented out). `stop()` requests a Binance stop and cancels the task group.

## GUI

### Page_Finance (`pages/finance.py`)

A main-nav page (`ConfigTabs`) that creates one shared `SqliteConnector` to `finance.db` and injects it into its tabs:

- **Portfolio** — QtCharts pie of current asset allocation (top 8 + "Other") with total value in GBP.
- **Fund Map** — `FundMapWidget` (see below).
- **Assets** — `ConfigTable` of derived balances (filterable by API, limit combo). Selecting an asset opens a config panel with **History** sub-tabs (Trades, DepWiths, Distribution) and a **Chart** tab. Queries use `find_linked_assets()` (recursive CTE over `group_to`) so a selected asset includes all its linked duplicates. The *Distribution* tab replays movements chronologically to infer per-exchange holdings — a sell exceeding an exchange's running balance implies a prior transfer in, funded from the most recently active surplus.
- **Users** — fund participants with share totals from `depwiths`; per-user DepWiths sub-table.
- **Trades** — all trades, filterable by exchange and limit.
- **DepWiths** — all fund deposits/withdrawals; selecting one shows the fund's asset balances at that moment (`get_asset_balances_at_unix`).
- **Settings** — a config field plus an API sync table: one row per API (Binance, CoinGecko, TwelveData) with buttons for each available sync method, run via `asyncio.create_task` with a status label.

### Widgets

- **ChartWidget** (`widgets/chart_widget.py`) — pyqtgraph candlestick chart for a `PriceFile` (found via `find_attribute(self, 'h5_file')`). Timeframe combo populated from the file's available intervals; batch-rendered candle bodies (`BarGraphItem`) and wicks (`PlotCurveItem` with `connect='pairs'`); X-only wheel zoom unless hovering the Y axis; auto Y-scaling to the visible X range; view preserved across interval switches; themed from `gui.style`.
- **FundMapWidget** (`widgets/fund_map.py`, registered as a Widget module) — interactive exchange fund-flow map. Loads `exchange_depwiths`, runs a "marriage" algorithm matching withdrawals to deposits on another exchange (same asset, amount within 2%, within 24h; persisted to `married_id`), then draws exchanges as draggable nodes on a circle with bezier lines for matched transfers. Nodes tint red by their unmarried-transfer ratio. A time slider (debounced) scrubs history; a holdings table shows per-exchange balances at the selected time.

### H5Studio (`studios/h5_studio.py`)

A Studio module (registered for the `.h5` extension) for viewing/editing HDF5 files: a **Chart** tab (reuses `ChartWidget`) and a **Data** tab with a lazy-loading tree of groups/datasets, a paginated table viewer (compound dtypes, 1D/2D and slicing of >2D arrays, in-place cell editing), and a metadata/attributes panel.

## Operations (`operations/`)

An early streaming-indicator framework: `Operation` ABC (`on_datapoint(datapoint)`) with `SMA` and `EMA` implementations, each carrying a nested `ConfigFields` schema (period, source, offset) for UI configuration. Its controller (`_finance_operations.py`) is currently disabled, and `extrema.py` is empty.

## Legacy / Utility Files

- `crypto/utils/` (`filesystem.py`, `sql.py`, `helpers.py`, `file_syncer.py`) — carried over from an older MySQL/"teafile"-based system; not part of the current flow.
- `tea.py` — old `.config`-file-per-directory helpers for the price data tree.
- `et.py` — standalone offline Ethereum transaction signing script (env-var driven), unrelated to the module system.
- `utils/assets.py` — the shared balance/price helpers: `get_asset_balances_at_unix()`, `get_asset_prices_at_unix()` / `convert_asset_price()` (resolves a market between two assets via `api_markets`, then binary-searches the market's h5 file for the price at that time), `find_linked_assets()`, and `get_total_at_unix()` (total portfolio value at a timestamp).
