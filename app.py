"""Start from Terminal with: python -m streamlit run app.py"""

from datetime import date
import json

import matplotlib.pyplot as plt
from requests import RequestException
import streamlit as st

from diesel_engine import (
    COUNTRIES, FOLDER, budget_price, calculate_budget, country_currency, initialize_database,
    load_history, load_plans, save_plan, scenario_table,
)
from price_model import MONTH, WEEK, estimate_next_price
from refresh_data import SOURCE_PAGE, SWISS_SOURCE, SWISS_SOURCE_PAGE, refresh_history


CHART_SIZE = (7, 2.7)
CHART_WIDTH = 680


st.set_page_config(page_title="Diesel Budget Planner", page_icon="⛽", layout="wide")
st.title("Diesel Budget Planner")
st.write("Plan a monthly fuel budget and see how a diesel-price change affects profit.")

# 1. Select a saved starting point. SQLite stores plain columns (Lecture 7).
initialize_database()
plans = load_plans()
new_plan = {"id": 0, "country": "DE", "litres": 50000.0, "price": 1.9,
            "revenue": 180000.0, "other_costs": 65000.0,
            "exclude_vat": False, "vat_rate": 0.0, "shock": 20.0}
plan_options = ["New plan"]
saved_inputs = {}
for i in range(len(plans)):
    row = plans.iloc[i]
    label = f"#{row['id']} - {row['name']}"
    plan_options.append(label)
    saved_inputs[label] = row.to_dict()

selected_plan = st.sidebar.selectbox("Starting inputs", plan_options)
defaults = new_plan
if selected_plan != "New plan":
    defaults = saved_inputs[selected_plan]
    st.sidebar.caption("Saved numbers loaded. Edits do not overwrite the saved copy.")

# A key identifies a widget. Each starting plan gets its own input widgets.
# Streamlit handles their values; we do not write callbacks or session_state code.
key = f"plan_{defaults['id']}"
country_names = sorted(COUNTRIES.values())
country_name = st.sidebar.selectbox(
    "Reference country", country_names,
    index=country_names.index(COUNTRIES[defaults["country"]]), key=key + "_country",
)
for code, name in COUNTRIES.items():
    if name == country_name:
        country = code

is_swiss = country == "CH"
currency = country_currency(country)
price_column = f"price_{currency.lower()}_per_litre"
period = "month" if is_swiss else "week"
date_format = "%b %Y" if is_swiss else "%d %b %Y"
publisher = "Swiss Federal Statistical Office" if is_swiss else "European Commission"

# Give EUR and CHF amounts separate widgets. A saved price belongs to its currency.
budget_key = f"{key}_{currency}"
same_currency = currency == country_currency(defaults["country"])
budget_defaults = defaults if same_currency else new_plan

if st.sidebar.button("Refresh official history"):
    try:
        with st.spinner(f"Downloading the {publisher} workbook..."):
            refreshed = refresh_history(country)
        last_observation = date.fromisoformat(refreshed["last_observation"])
        st.sidebar.success(f"Updated through {last_observation:{date_format}}")
    except (RequestException, OSError, ValueError) as error:
        st.sidebar.error("Could not refresh the data. Try again later.")
        st.sidebar.caption(str(error))

# 2. Read and filter the CSV with pandas (Lecture 8).
try:
    history = load_history(country)
    if is_swiss:
        source, source_page = SWISS_SOURCE, SWISS_SOURCE_PAGE
    else:
        with open(FOLDER / "data" / "source_metadata.json", encoding="utf-8") as file:
            metadata = json.load(file)
        source = metadata["source"]
        source_page = metadata.get("source_page", SOURCE_PAGE)
except (OSError, ValueError) as error:
    st.error("Keep the complete data folder next to app.py.")
    st.caption(str(error))
    st.stop()

latest_date = history["date"].iloc[-1]
latest_pump_price = float(history[price_column].iloc[-1])
price_description = "Monthly average" if is_swiss else "Published price"
st.caption(f"{country_name} | Latest observation: {latest_date:{date_format}} | "
           f"{price_description}: {currency} {latest_pump_price:.3f}/L, including taxes")
reference_end = latest_date.date()
max_age_days = 21
if is_swiss:
    reference_end = reference_end.replace(day=latest_date.days_in_month)
    max_age_days = 45
if (date.today() - reference_end).days > max_age_days:
    st.warning("The latest benchmark may be out of date. The estimate starts from the observation shown above.")

# 3. A small, separate learning extension using fit() and predict().
enable_model = st.sidebar.checkbox("Enable price-estimate learning extension", value=False)
forecast = None
if enable_model:
    try:
        interval = MONTH if is_swiss else WEEK
        forecast = estimate_next_price(history, interval, price_column)
    except ValueError:
        forecast = None

# 4. Get the company's monthly inputs (Lectures 2-4 and Streamlit).
st.sidebar.header("Monthly business inputs")
litres = st.sidebar.number_input(
    "Diesel use (litres/month)", min_value=0.0, value=float(defaults["litres"]),
    step=1000.0, key=key + "_litres",
)
revenue = st.sidebar.number_input(
    f"Revenue ({currency}/month)", min_value=0.0, value=float(budget_defaults["revenue"]),
    step=1000.0, key=budget_key + "_revenue",
)
other_costs = st.sidebar.number_input(
    f"Other operating costs ({currency}/month)", min_value=0.0,
    value=float(budget_defaults["other_costs"]), step=1000.0, key=budget_key + "_costs",
)
exclude_vat = st.sidebar.checkbox(
    "Exclude recoverable diesel VAT", value=bool(budget_defaults["exclude_vat"]),
    key=budget_key + "_exclude_vat",
)
vat_rate = st.sidebar.number_input(
    "Recoverable diesel VAT rate (%)", min_value=0.0, max_value=40.0,
    value=float(budget_defaults["vat_rate"]), step=0.5, disabled=not exclude_vat,
    key=budget_key + "_vat",
)
st.sidebar.caption("If excluding recoverable VAT, enter and check your own rate. "
                   "Enter revenue and other costs on the same VAT basis.")

price_options = ["Latest benchmark", "Enter my own price"]
if forecast is not None and forecast["price"] > 0:
    price_options.append("Simple ML estimate")
source_index = 1 if selected_plan != "New plan" and same_currency else 0
price_source = st.sidebar.selectbox(
    "Planning price source", price_options, index=source_index,
    key=budget_key + "_price_source",
)
if price_source == "Enter my own price":
    price = st.sidebar.number_input(
        f"Your planning diesel price ({currency}/L)", min_value=0.0,
        value=float(budget_defaults["price"]), step=0.01, format="%.3f",
        key=budget_key + "_price",
    )
    st.sidebar.caption("Enter this price directly on your chosen VAT basis; "
                       "the app does not deduct VAT a second time.")
else:
    pump_price = latest_pump_price
    if price_source == "Simple ML estimate":
        pump_price = forecast["price"]
    price = budget_price(pump_price, exclude_vat, vat_rate)
st.sidebar.write(f"Planning price used: {currency} {price:.3f}/L")
shock = st.sidebar.slider(
    "Custom diesel-price change (%)", min_value=-100.0, max_value=150.0,
    value=float(defaults["shock"]), step=5.0, key=key + "_shock",
)

result = calculate_budget(litres, price, revenue, other_costs)
scenarios = scenario_table(litres, price, revenue, other_costs, shock, currency)
a, b, c = st.columns(3)
a.metric("Monthly diesel cost", f"{currency} {result['fuel_cost']:,.0f}")
b.metric("Monthly operating result", f"{currency} {result['profit']:,.0f}")
if result["margin"] is None:
    c.metric("Operating margin", "N/A (zero revenue)")
else:
    c.metric("Operating margin", f"{result['margin']:.1f}%")

budget_tab, history_tab, model_tab, saved_tab = st.tabs(
    ["Budget & scenarios", "Price history", "Simple ML estimate", "Saved plans"]
)

with budget_tab:
    st.subheader("What happens if diesel prices change?")
    st.write("Litres, revenue and other costs stay constant in these scenarios.")
    st.dataframe(scenarios.round(3), hide_index=True)
    fig, ax = plt.subplots(figsize=CHART_SIZE, layout="constrained")
    ax.bar(["Current", "+10%", "+30%", "Custom"], scenarios[f"Operating result ({currency})"])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel(f"Monthly operating result ({currency})")
    st.pyplot(fig, width=CHART_WIDTH)
    plt.close(fig)

    if result["break_even"] is None:
        st.info("With zero diesel use, diesel-price changes do not affect this budget.")
    elif result["break_even"] < 0:
        st.warning("Revenue does not cover other costs, even if diesel were free.")
    else:
        st.write(f"Break-even diesel price: {currency} {result['break_even']:.3f}/L")
    st.caption("Scenarios are assumptions, not predictions of a conflict or its consequences.")
    report = scenarios.copy()
    report["Country"] = country_name
    report["Monthly litres"] = litres
    report[f"Monthly revenue ({currency})"] = revenue
    report[f"Other monthly costs ({currency})"] = other_costs
    report["Exclude recoverable VAT"] = exclude_vat
    report["VAT rate (%)"] = vat_rate
    if is_swiss:
        report["Reference month"] = latest_date.strftime("%Y-%m")
    else:
        report["Reference date"] = latest_date.strftime("%Y-%m-%d")
    st.download_button("Download scenarios (CSV)", report.to_csv(index=False),
                       file_name="diesel_scenarios.csv", mime="text/csv")

with history_tab:
    st.subheader(f"Historical {period}ly pump prices")
    st.caption("National consumer benchmarks including taxes. Your fleet's actual price may differ.")
    lookbacks = [12, 36, 60] if is_swiss else [52, 156, 260]
    observations = st.selectbox(f"{period.capitalize()}s to display", lookbacks + [len(history)], index=1)
    displayed = history.tail(observations)
    fig, ax = plt.subplots(figsize=CHART_SIZE, layout="constrained")
    ax.plot(displayed["date"], displayed[price_column])
    ax.set_ylabel(f"Diesel pump price ({currency}/L)")
    ax.tick_params(axis="x", labelrotation=25)
    st.pyplot(fig, width=CHART_WIDTH)
    plt.close(fig)
    st.write(f"Displayed range: {currency} {displayed[price_column].min():.3f} "
             f"to {currency} {displayed[price_column].max():.3f}/L")
    st.download_button("Download country history (CSV)", history.to_csv(index=False),
                       file_name=f"diesel_history_{country}.csv", mime="text/csv")

with model_tab:
    st.subheader(f"A simple one-{period} price estimate")
    if not enable_model:
        st.info("Enable the price-estimate learning extension in the sidebar to try it.")
    elif forecast is None:
        st.info(f"At least 30 consecutive-{period} price pairs are needed for this model.")
    else:
        st.write(f"Estimate for {forecast['date']:{date_format}}: {currency} {forecast['price']:.3f}/L")
        st.write(f"Test mean absolute error is {currency} {forecast['model_error']:.4f}/L "
                 f"for the model and {currency} {forecast['baseline_error']:.4f}/L for the baseline.")
        if forecast["model_error"] < forecast["baseline_error"]:
            st.success("The model was more accurate than the baseline in this test.")
        else:
            st.info("The unchanged-price baseline was at least as accurate in this test.")
        comparison = forecast["comparison"]
        fig, ax = plt.subplots(figsize=CHART_SIZE, layout="constrained")
        for column in ["Observed price", "Model estimate", "Unchanged-price baseline"]:
            ax.plot(comparison["date"], comparison[column], label=column)
        ax.set_ylabel(f"Pump price ({currency}/L)")
        ax.legend()
        ax.tick_params(axis="x", labelrotation=25)
        st.pyplot(fig, width=CHART_WIDTH)
        plt.close(fig)
        st.caption(f"The model trains on the older {forecast['train_rows']} pairs and is tested on "
                   f"the newer {forecast['test_rows']} pairs "
                   f"({forecast['test_start']:{date_format}} to {forecast['test_end']:{date_format}}).")
        st.write("The model learns: next price = intercept + coefficient × previous price. "
                 f"Each test estimate uses the preceding {period}'s observed price. "
                 "The training model stays fixed throughout this test.")
        st.write("After testing, it is refitted on all available pairs (at most 156) "
                 f"for the next estimate. Missing {period}s are skipped. "
                 "Past accuracy does not guarantee future accuracy.")
        st.caption("Model prices include taxes. If selected for the budget, the estimate is "
                   "used as a single planning price for the whole month.")

with saved_tab:
    st.subheader("Save the current inputs")
    plan_name = st.text_input("Plan name", value="Monthly fleet budget", max_chars=100)
    inputs = {"country": country, "litres": litres, "price": price,
              "revenue": revenue, "other_costs": other_costs,
              "exclude_vat": exclude_vat, "vat_rate": vat_rate, "shock": shock}
    if st.button("Save plan"):
        try:
            save_plan(plan_name, inputs)
            st.success("Saved. Select it under Starting inputs on your next interaction.")
        except ValueError as error:
            st.error(str(error))
    saved_plans = load_plans()
    saved_plans.insert(3, "currency", saved_plans["country"].map(country_currency))
    st.dataframe(saved_plans, hide_index=True)
    st.caption("Everyone using the same deployed app can see its saved plans. "
               "Local cloud files can disappear after a restart or redeployment.")

st.caption(f"Source: {source}. Prices are in {currency} per litre.")
st.markdown(f"[Source and reporting methodology]({source_page})")
