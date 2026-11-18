# Upload the Diesel Planner into the existing class project

This package uses `app.py` as its entrypoint, matching the existing Streamlit
Community Cloud deployment for `timgreger123/CS-Funproject-1`.

## Upload in the GitHub website

1. Unzip the download and open the extracted `CS-Funproject-1` folder.
2. Open https://github.com/timgreger123/CS-Funproject-1 and select branch `main`.
3. Click Add file > Upload files.
4. In Finder, press Command + Shift + . to reveal hidden items. Select all
   the contents of the extracted folder and drag them into GitHub's upload box.
   Upload the contents, not the outer `CS-Funproject-1` folder and not the ZIP.
5. Check the upload includes `app.py`, `diesel_engine.py`, `requirements.txt`,
   `data/diesel_history.csv`, `data/source_metadata.json`, the two files under
   `tests/`, `.streamlit/config.toml`, `.gitignore`, and this guide.
6. Enter the commit message `Add Diesel Budget Planner` and commit to `main`.
7. Your existing Streamlit app should rebuild from this commit. Wait for the
   dependency installation to finish and then reload the app page.

Existing `app.py` and `requirements.txt` are replaced. The existing `README.md`
and course notebook are not included in this package and remain in the repository.

The Streamlit deployment must keep these settings:

| Setting | Value |
| --- | --- |
| Repository | `timgreger123/CS-Funproject-1` |
| Branch | `main` |
| Main file path | `app.py` |

`app.py` is the original `Streamlitexample.py`, renamed for the deployed app.
The engine still expects the price CSV and JSON inside a folder called `data`.
`planner.sqlite` is created automatically on the computer running the app.
You do not need to upload an existing SQLite database, `__pycache__`, or `.pyc` files.
Use the full included requirements file, not the one-line list from the earlier
three-message test app. Built-in Python modules are not listed as packages.

## Working with your group

Your existing repository permissions and collaborators remain in place.
After an upload through the website, refresh the remote repository in VS Code
(or reload its window) so it sees the new files. Friends who use a local clone
should pull the latest `main` before editing.
Commit and push subsequent code changes to the deployed `main` branch to update
the Streamlit app. GitHub stores project versions; Live Share is optional if the
group wants to edit the same files live during a session.

## Cloud storage

Each browser has its own input state. Saved plans are shared by everyone using
the same deployed app, and are stored in its temporary runtime, not committed
back to GitHub. A runtime replacement or redeployment may discard them. The
bundled CSV and JSON rebuild the prices database on the next clean start.
This deployment remains a class-project demonstration with no user accounts.

## Troubleshooting the upload

- If the app still shows the earlier test messages, verify that GitHub's root
  `app.py` now contains the full Diesel Budget Planner and that the deployed
  branch is `main`. The new files must not be nested in an extra parent folder.
- If the data folder cannot be opened, verify the two `data/` paths above.
- If a dependency is missing, verify the full included `requirements.txt` was
  uploaded at the repository root. Consult Manage app > logs for the exact
  error; this error is different from a Python syntax error.
- If the page remains on the old deployment after a successful commit, use the
  app's Community Cloud management menu to reboot once, then inspect its logs.

---

# Diesel Budget Planner

A runnable Streamlit project for the diesel-cost planning idea: a small logistics business can estimate its monthly diesel bill and operating result, compare price shocks, inspect real historical prices, and train/evaluate a next-week price model.

## Start on your Mac

1. Unzip the project and open the extracted `CS-Funproject-1` folder in VS Code.
2. Open Terminal → New Terminal. Check that it is inside this folder, where `requirements.txt` and `app.py` are visible.
3. If your old Streamlit test is still running in that terminal, press Control + C to stop it.
4. Install the dependencies into the same Python environment you will use to run the app:

```bash
python -m pip install -r requirements.txt
```

5. Start the app:

```bash
python -m streamlit run app.py
```

6. Open `http://localhost:8501`. If Streamlit chooses a different port, use the address it prints.

The upload package was tested with Python 3.12.14 and Streamlit 1.67.0. Use the included requirements file. Python 3.10 or newer is required for the supported Streamlit versions. The Anaconda Python environment visible in your screenshot is suitable. `python -m ...` helps avoid installing into one environment and launching from another.

Keep the whole extracted folder together. Replacing only your old test file will not be enough: the app imports `diesel_engine.py` and reads the bundled `data` folder. No API key or account is needed. After installation, the app can run offline using the bundled prices.

## What is included

- Monthly diesel-cost, simplified operating-result, margin and break-even calculations.
- Fixed +10% / +30% fuel-price scenarios and a custom shock, including negative price shocks.
- Real historical weekly automotive diesel prices for the 27 EU countries, defaulting to Germany.
- A locally trained Ridge regression forecasting the next reporting week's price.
- A chronological walk-forward evaluation against an unchanged-price baseline.
- Optional removal of recoverable diesel VAT when preparing a net-cost budget.
- Local SQLite storage for historical prices, source metadata and saved business plans.
- Downloadable CSV history and scenario comparisons.
- A button to refresh the history directly from the European Commission.

The initial company inputs are illustrative and editable. The historical diesel prices are real observations, not generated sample data.

## Files and how to explain the project

| File | Purpose |
| --- | --- |
| `app.py` | The interface: inputs, metrics, charts, tabs and buttons. |
| `diesel_engine.py` | Data import, calculations, the forecasting model and database functions. |
| `requirements.txt` | Python packages needed to run the app. |
| `data/diesel_history.csv` | Bundled real data so the first launch does not depend on the source website. |
| `data/source_metadata.json` | Data source, retrieval time, units, latest reporting date and diesel VAT rates. |
| `data/planner.sqlite` | Created automatically on first launch; stores prices and saved plans. |
| `tests/` | Tests for arithmetic, data conversion, missing weeks, forecasting leakage and Streamlit interactions. |
| `.streamlit/config.toml` | Streamlit theme and local settings. |

The flow is: official historical data → SQLite → feature engineering → trained model → forecasts and budget scenarios → Streamlit interface.

## Data source and units

Source: European Commission, Directorate-General for Energy, Weekly Oil Bulletin.

- Source page: https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en
- Historical workbook: https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_matrici_4web.xlsx
- Reuse policy: https://commission.europa.eu/legal-notice_en

The importer selects `Prices with taxes` and the automotive diesel columns. It converts EUR per 1,000 litres to EUR per litre by dividing by 1,000. It does not confuse automotive diesel with heating oil. Prices are national weekly consumer benchmarks including taxes, not live station quotations or individual fleet contract prices. Source attribution is included in the app.

The original observations are preserved for charts. Only the model's feature inputs carry the previous price forward across missing publication weeks. Missing weeks are not invented target observations or scored in model evaluation.

Use the displayed observation date to judge freshness. The forecast date is the latest observation plus one week. Refreshing the source is an explicit button action; opening the app does not silently download the workbook. Failed downloads or validation failures preserve the previously stored dataset.

## Budget formulas and VAT

```text
Diesel cost = monthly litres × planning price per litre
Operating result = revenue − other operating costs − diesel cost
Operating margin (%) = operating result / revenue × 100
Break-even diesel price = (revenue − other operating costs) / litres
Scenario price = planning price × (1 + shock / 100)
```

Use a consistent VAT basis for revenue and costs. If diesel VAT is recoverable, the default net diesel benchmark is the published pump price divided by `(1 + VAT rate / 100)`. Country defaults come from the workbook's automotive-diesel VAT sheet; the rate is editable. Excise duties remain part of the price. These calculations do not model financing costs, income tax, changing sales volume, customer fuel surcharges or the timing of VAT cash flows.

If an automotive-diesel VAT rate is absent from the source sheet, the app defaults that market to gross planning and asks you to enter a rate before using a VAT-adjusted budget. It does not silently invent a tax rate.

The model and history chart always use published tax-inclusive pump prices. Applying a forecast to the budget converts it to the selected VAT basis. The resulting monthly budget assumes that price stays flat for the month; it is not a prediction of the whole month's prices.

## Machine learning without inflated claims

The model is trained in Python using scikit-learn. It predicts the next weekly price change, which is added to the latest known price. Inputs are the previous eight weekly prices, four/eight-week averages and one/four-week changes. A StandardScaler + Ridge pipeline is fitted on up to the latest 156 published target observations. Ridge alpha is fixed at 10 before evaluation.

For the last 26 published test observations, the model is refitted at each step using only observations available before that target week. The scaler is also fitted only on the training data. A simple baseline predicts an unchanged price. Both are compared with mean absolute error (EUR/L). The app reports when the baseline is better; it does not cherry-pick the model to claim success. The final next-week model is refitted on the available history after evaluation.

The geopolitical connection is stress testing: users can investigate how assumed conflict-related price rises affect their business. Historical-price ML does not predict a surprise escalation or the size/probability of its impact. No event-specific price shock is claimed as an observed fact or a model prediction.

## Run the checks

From the project folder, after installing requirements:

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and do not overwrite your saved plans. The optional `DIESEL_PLANNER_DB` environment variable can also choose a different database path.

## Troubleshooting

- ModuleNotFoundError: run the installation command above using the same `python` as the launch command.
- Can't find app.py: open the terminal in the extracted project folder. Do not run the app from inside the ZIP.
- An old page is still open: stop the old process with Control+C and launch this project, then open the URL printed by the new process.
- Refresh fails: the included dataset still works. The Commission may be unavailable or may have changed its workbook layout. The error is shown without deleting your data.
- Restoring or saving plans: files are local to the computer running Streamlit. All users of one deployed app share its saved plans. Community Cloud local storage is temporary: saved plans and refreshed prices can be lost when the runtime is replaced. CSV downloads can keep a copy of the scenario results; the bundled source files remain in GitHub.

For a class presentation, be able to explain the formulas, data conversion, SQLite tables, lag features, chronological backtest and the distinction between forecasts and stress assumptions.

## Package validation

On 18 November 2026, all 14 automated tests passed in a fresh Python 3.12.14 environment with Streamlit 1.67.0. These include startup through app.py, budget calculations, country changes, saving and restoring plans, data conversion, and chronological model checks. The live GitHub repository and Streamlit deployment have not been changed by this package preparation.
