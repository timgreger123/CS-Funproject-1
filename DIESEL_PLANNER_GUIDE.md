# Diesel Budget Planner - HSG course version

## Is your course material enough?

Yes, for the core project. The material you uploaded covers functions, loops,
lists, dictionaries, Streamlit, object-oriented programming, HTTP requests,
SQL/SQLite, NumPy, pandas, plotting and basic machine learning. Building a
budget calculator with a web interface, historical data and saved plans is
within that scope. It does not require advanced Python architecture.

The earlier version was unnecessarily complicated for this purpose. Its
dataclass, custom database context manager, caching decorator, widget callbacks,
automatic VAT-rate selection, Plotly styling, twelve forecasting features,
Ridge pipeline and repeated weekly retraining are not needed to demonstrate
the skills in your uploaded exercises.

This rewrite uses ordinary functions and dictionaries. A class would also be
within Lecture 5, but is not necessary for these calculations.

The files are a runnable study version. They are not evidence that HSG permits
every library call or that a particular project rubric is satisfied: you did
not upload the project assessment brief.

## What is directly supported, and what is an extension?

| Project part | Uploaded course material | Assessment |
| --- | --- | --- |
| Cost, profit, margin and break-even calculations | Unit02 sections 3-5; Unit03 sections 1-2 | Direct application of arithmetic, conditions and functions |
| Lists of scenarios and dictionaries of results | Unit03 sections 3-5; Unit04 sections 2-4 | Direct application of loops and data structures |
| Browser interface | Unit04 section 5; streamlit_db_demo.py | Same framework; individual input widgets/layouts require looking up their arguments |
| SQLite saved plans | Unit07 sections 3-4; streamlit_db_demo.py | Same connect/execute/read_sql/close pattern |
| Country filtering, sorting and CSV reading | Unit08 sections 3-4 | Direct pandas application |
| Line and bar charts | Assignment 09, tasks 6-7 | Direct matplotlib application |
| HTTP download and JSON metadata | Assignment 06 | Same requests/response pattern |
| Reading the source Excel workbook | pandas.read_csv taught in Unit08 | Small extension: read_excel and BytesIO |
| Numeric price prediction | Assignments 10-11 teach classification, fit/predict and held-out data | Extension: LinearRegression predicts a number instead of a class |
| Evaluating the price estimate | Assignments 10-11 teach train/test evaluation | Extension: preserve time order and use a regression error metric |
| Widget keys, paths and SQL ? placeholders | Applications of taught Python with library-specific APIs | Small practical additions explained in the code |

In particular, basic machine learning is already in your material. It would
be inaccurate to call all ML beyond your course. What your uploaded ML tasks
do not teach directly is a complete time-series forecasting system.

The numeric model is therefore isolated in price_model.py and disabled by
default in the interface. The budget, history and saved plans work without
enabling it. If your instructor requires only explicitly demonstrated methods,
leave that feature off and discuss the extension before presenting it.

## Start on your Mac

1. Unzip the download.
2. Open the extracted CS-Funproject-1 folder in VS Code.
3. Open a terminal in that folder, where app.py and requirements.txt are visible.
4. Install the packages and run the application:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Use Python 3.10 or newer. If your system uses python3 instead of python, use
python3 in both commands. Keep the entire project folder together. No API key
is required. The bundled price history works offline.

To stop the application, press Control+C in its terminal.

## Files

| File | Purpose |
| --- | --- |
| app.py | Inputs, displayed results, charts and buttons |
| diesel_engine.py | Budget functions, CSV reading and SQLite saved plans |
| price_model.py | Optional one-feature regression extension |
| refresh_data.py | Optional HTTP download and source workbook conversion |
| checks.py | Small checks for arithmetic, SQL storage and model time order |
| requirements.txt | Packages to install |
| data/diesel_history.csv | The original uploaded historical data, unchanged |
| data/diesel_history_ch.csv | Monthly Swiss diesel prices from the Federal Statistical Office in CHF/L |
| data/source_metadata.json | The original uploaded source information, unchanged |
| data/student_plans.sqlite | Created on first run; not distributed in the ZIP |

Read diesel_engine.py first, then app.py. Read price_model.py after reviewing
Assignments 10 and 11. Code comments identify the main steps.

## How the budget works

```text
Diesel cost = litres per month * planning price per litre
Operating result = monthly revenue - other operating costs - diesel cost
Operating margin (%) = operating result / revenue * 100
Break-even price = (revenue - other operating costs) / litres per month
Scenario price = planning price * (1 + price change / 100)
```

Example: 50,000 litres at EUR 1.90/L cost EUR 95,000. With revenue of
EUR 180,000 and other costs of EUR 65,000, the operating result is EUR 20,000.
A 10% diesel-price increase reduces it to EUR 10,500. A 30% increase makes
the result EUR -8,500. The break-even diesel price is EUR 2.30/L.

Zero revenue gives an undefined percentage margin, displayed as N/A.
Zero diesel use gives no break-even fuel-price threshold. If other costs
already exceed revenue, even free diesel cannot make the plan profitable.

This is a simplified operating budget. Revenue, consumption and other costs
stay constant in the price scenarios. It does not model changes in sales,
financing costs, income tax or customer fuel surcharges.

### Price selection and VAT

The published history and model estimate are tax-inclusive pump benchmarks.
You can choose the latest benchmark, enter your own price, or enable and
choose the simple model estimate.

VAT is included by default. If recoverable diesel VAT should be excluded,
check the box and enter the applicable rate yourself. For a benchmark/model
price the conversion is:

```text
Budget price = tax-inclusive price / (1 + VAT rate / 100)
```

For example, EUR 1.19 including 19% VAT becomes EUR 1.00 excluding VAT.
The app does not automatically select or verify national tax rates.

A manually entered price is already on your chosen VAT basis; VAT is not
deducted from it again. Revenue and other costs must use the same basis.
Selecting Switzerland switches the budget to CHF. Enter revenue, costs and
any manual planning price in the currency displayed beside each input.
Switching between EUR and CHF starts the currency-specific inputs with the
sample values. Saved plans take their currency from their saved country.

## How the optional model works

The model uses the preceding period's observed diesel price to estimate the
next period. The period is one week for EU countries and one calendar month
for Switzerland. A loop creates pairs of consecutive observations and skips
gaps in the data.

It uses at most the most recent 156 valid pairs. This fixed choice is
not optimized against the test set. The older 70% train one LinearRegression
model. The newer 30% test that fixed model. This follows the train/test idea
in Assignment 10, with chronological slicing instead of random shuffling.

The fitted rule is:

```text
Predicted price = fitted intercept + fitted coefficient * previous period's price
```

The model's mean absolute error (MAE) is the average absolute distance between
each test estimate and the corresponding actual price. It is compared with
the simple baseline that carries forward the previous observed price.
A smaller MAE is better. The interface reports when the baseline wins.

Each test prediction uses the actual preceding period's price. This is a
sequence of one-step estimates with a fixed fitted model. It is not a forecast
of the entire test period made at the beginning of that period.

Only after recording test performance is the model refitted on all available
pairs for the next estimate. There is no model selection, parameter
tuning, feature scaling or repeated walk-forward retraining in this version.

The estimate is dated one week or one month after the latest observation.
The monthly budget uses the estimate as a single planning price for the whole
month.
The model does not predict wars, news shocks or probabilities of price rises.

## Data and refreshing

The included EU CSV has 28,681 observations across 27 countries, from
3 January 2005 to 19 October 2026.

Source: European Commission, DG Energy, Weekly Oil Bulletin.
https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en

The source workbook quotes EUR per 1,000 litres. The importer selects
automotive diesel WITH taxes and divides by 1,000. Prices in the supplied CSV
are already EUR/L: do not divide them again. These are national consumer
benchmarks, not live station quotations or individual fleet contract prices.

For Switzerland, the included CSV has 402 monthly retail diesel prices from
May 1993 through October 2026. The last average is CHF 2.41/L. The Federal
Statistical Office reports these averages in CHF per litre including VAT and
other taxes. The importer reads the Diesel column from the Monat - Mois sheet
of table su-d-05.02.91. The first day of each month is the CSV's date label.
https://statistik.admin.ch/de/asset/36970598

Use the Refresh official history button to update the source for the selected
country. To update the EU history from a terminal, run:

```bash
python refresh_data.py
```

A refresh requires an internet connection. The app validates the downloaded
workbook before replacing the corresponding history. The Swiss download uses
the FSO table number to retrieve the latest release.

## Saved plans and GitHub

Save the current inputs in the Saved plans tab. On the next interaction,
select that saved plan under Starting inputs to load a starting copy.
Editing a loaded plan does not modify its original database row. Saving again
creates another row. Each selected plan has its own input widgets, so returning
to it in the same session can retain your unsaved edits. Reload the page for
a fresh copy from the database.

SQLite stores the numeric inputs in columns. SQL ? placeholders keep plan
names separate from SQL commands, including names containing apostrophes.
The new student_plans.sqlite file does not migrate or overwrite the old
planner.sqlite database.

For the existing timgreger123/CS-Funproject-1 deployment, upload the CONTENTS
of the extracted folder to the repository root, preserving the data folder.
Keep the main file path app.py. For the Switzerland update, include app.py,
diesel_engine.py, price_model.py, refresh_data.py and
data/diesel_history_ch.csv in the same commit.

Do not mix the old engine tests with this rewrite: their function names and
schema belong to the previous version. For this version use checks.py; remove
the previous tests directory when replacing the project. An old custom
.streamlit/config.toml can be removed if you want Streamlit's standard theme.
The live GitHub repository and deployment have not been modified here.

All users of a shared deployment can see its saved plans. Cloud runtime files
can disappear on restart/redeployment. Download the scenario CSV if you need
to keep results. For durable shared storage, Lecture 7's external database
approach would be the appropriate further step.

## Check the project

```bash
python checks.py
```

The checks cover budget results, VAT conversion, saved plans, missing periods,
and separation of training data from the first test target. They also check
the Swiss history, the next-month estimate date and CHF scenario columns.
Checks use a temporary database.

The rewrite was also checked on Python 3.12, Streamlit 1.67.0, pandas 2.2.3,
matplotlib 3.10.8 and scikit-learn 1.8.0. Interface checks passed for startup,
editing the budget, zero inputs, VAT/manual-price treatment, saving/loading
plans, switching countries, enabling the model and a failed refresh. The model
ran for all 27 countries. The live Commission download and unit conversion
were checked; no refreshed data was written into the distributed snapshot.

For a presentation, explain each budget formula, how the country filter works,
the SELECT and INSERT statements, and why a scenario is different from a
prediction. If you enable the model, also explain its input/target, chronological
split, fit/predict steps and comparison with the unchanged-price baseline.
