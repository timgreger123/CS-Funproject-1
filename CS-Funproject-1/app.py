"""Start from Terminal with: python -m streamlit run app.py"""

from datetime import date
import json

import matplotlib.pyplot as plt
from requests import RequestException
import streamlit as st

from diesel_engine import (
    COUNTRIES, FOLDER, budget_price, calculate_budget, initialize_database,
    load_history, load_plans, save_plan, scenario_table,
)
from price_model import estimate_next_week
from refresh_data import SOURCE_PAGE, refresh_history


st.set_page_config(page_title="Diesel Budget Planner", page_icon="⛽", layout="wide")
st.title("Diesel Budget Planner")
st.write("Plan a monthly fuel budget and see how a diesel-price change affects profit.")

# 1. Select a saved starting point. SQLite stores plain columns (Lecture 7).
initialize_database()
plans = load_plans()
defaults = {"id": 0, "country": "DE", "litres": 50000.0, "price": 1.9,
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

if st.sidebar.button("Refresh official history"):
    try:
        with st.spinner("Downloading the European Commission workbook..."):
            refreshed = refresh_history()
        st.sidebar.success("Updated through " + refreshed["last_observation"])
    except (RequestException, OSError, ValueError) as error:
        st.sidebar.error("Could not refresh the data. Try again later.")
        st.sidebar.caption(str(error))

# 2. Read and filter the CSV with pandas (Lecture 8).
try:
    history = load_history(country)
    with open(FOLDER / "data" / "source_metadata.json", encoding="utf-8") as file:
        metadata = json.load(file)
except (OSError, ValueError) as error:
    st.error("Keep the complete data folder next to app.py.")
    st.caption(str(error))
    st.stop()

latest_date = history["date"].iloc[-1]
latest_pump_price = float(history["price_eur_per_litre"].iloc[-1])
st.caption(f"{country_name} | Latest observation: {latest_date:%d %b %Y} | "
           f"Published price: EUR {latest_pump_price:.3f}/L, including taxes")
if (date.today() - latest_date.date()).days > 21:
    st.warning("The latest observation is more than three weeks old. "
               "The estimate is dated from that observation, not from today.")

# 3. A small, separate learning extension using fit() and predict().
enable_model = st.sidebar.checkbox("Enable price-estimate learning extension", value=False)
forecast = None
if enable_model:
    try:
        forecast = estimate_next_week(history)
    except ValueError:
        forecast = None

# 4. Get the company's monthly inputs (Lectures 2-4 and Streamlit).
st.sidebar.header("Monthly business inputs")
litres = st.sidebar.number_input(
    "Diesel use (litres/month)", min_value=0.0, value=float(defaults["litres"]),
    step=1000.0, key=key + "_litres",
)
revenue = st.sidebar.number_input(
    "Revenue (EUR/month)", min_value=0.0, value=float(defaults["revenue"]),
    step=1000.0, key=key + "_revenue",
)
other_costs = st.sidebar.number_input(
    "Other operating costs (EUR/month)", min_value=0.0,
    value=float(defaults["other_costs"]), step=1000.0, key=key + "_costs",
)
exclude_vat = st.sidebar.checkbox(
    "Exclude recoverable diesel VAT", value=bool(defaults["exclude_vat"]),
    key=key + "_exclude_vat",
)
vat_rate = st.sidebar.number_input(
    "Recoverable diesel VAT rate (%)", min_value=0.0, max_value=40.0,
    value=float(defaults["vat_rate"]), step=0.5, disabled=not exclude_vat,
    key=key + "_vat",
)
st.sidebar.caption("If excluding recoverable VAT, enter and check your own rate. "
                   "Enter revenue and other costs on the same VAT basis.")

price_options = ["Latest benchmark", "Enter my own price"]
if forecast is not None and forecast["price"] > 0:
    price_options.append("Simple ML estimate")
source_index = 0
if selected_plan != "New plan":
    source_index = 1
price_source = st.sidebar.selectbox(
    "Planning price source", price_options, index=source_index,
    key=key + "_price_source",
)
if price_source == "Enter my own price":
    price = st.sidebar.number_input(
        "Your planning diesel price (EUR/L)", min_value=0.0,
        value=float(defaults["price"]), step=0.01, format="%.3f",
        key=key + "_price",
    )
    st.sidebar.caption("Enter this price directly on your chosen VAT basis; "
                       "the app does not deduct VAT a second time.")
else:
    pump_price = latest_pump_price
    if price_source == "Simple ML estimate":
        pump_price = forecast["price"]
    price = budget_price(pump_price, exclude_vat, vat_rate)
st.sidebar.write(f"Planning price used: EUR {price:.3f}/L")
shock = st.sidebar.slider(
    "Custom diesel-price change (%)", min_value=-100.0, max_value=150.0,
    value=float(defaults["shock"]), step=5.0, key=key + "_shock",
)

result = calculate_budget(litres, price, revenue, other_costs)
scenarios = scenario_table(litres, price, revenue, other_costs, shock)
a, b, c = st.columns(3)
a.metric("Monthly diesel cost", f"EUR {result['fuel_cost']:,.0f}")
b.metric("Monthly operating result", f"EUR {result['profit']:,.0f}")
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
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.bar(["Current", "+10%", "+30%", "Custom"], scenarios["Operating result (EUR)"])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Monthly operating result (EUR)")
    st.pyplot(fig)
    plt.close(fig)

    if result["break_even"] is None:
        st.info("With zero diesel use, diesel-price changes do not affect this budget.")
    elif result["break_even"] < 0:
        st.warning("Revenue does not cover other costs, even if diesel were free.")
    else:
        st.write(f"Break-even diesel price: EUR {result['break_even']:.3f}/L")
    st.caption("Scenarios are assumptions, not predictions of a conflict or its consequences.")
    report = scenarios.copy()
    report["Country"] = country_name
    report["Monthly litres"] = litres
    report["Monthly revenue (EUR)"] = revenue
    report["Other monthly costs (EUR)"] = other_costs
    report["Exclude recoverable VAT"] = exclude_vat
    report["VAT rate (%)"] = vat_rate
    report["Reference date"] = latest_date.strftime("%Y-%m-%d")
    st.download_button("Download scenarios (CSV)", report.to_csv(index=False),
                       file_name="diesel_scenarios.csv", mime="text/csv")

with history_tab:
    st.subheader("Historical weekly pump prices")
    st.caption("National consumer benchmarks including taxes. Your fleet's actual price may differ.")
    observations = st.selectbox("Observations to display", [52, 156, 260, len(history)], index=1)
    displayed = history.tail(observations)
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.plot(displayed["date"], displayed["price_eur_per_litre"])
    ax.set_ylabel("Diesel pump price (EUR/L)")
    fig.autofmt_xdate()
    st.pyplot(fig)
    plt.close(fig)
    st.write(f"Displayed range: EUR {displayed['price_eur_per_litre'].min():.3f} "
             f"to EUR {displayed['price_eur_per_litre'].max():.3f}/L")
    st.download_button("Download country history (CSV)", history.to_csv(index=False),
                       file_name=f"diesel_history_{country}.csv", mime="text/csv")

with model_tab:
    st.subheader("A simple one-week price estimate")
    if not enable_model:
        st.info("Enable the price-estimate learning extension in the sidebar to try it.")
    elif forecast is None:
        st.info("At least 30 consecutive-week price pairs are needed for this model.")
    else:
        st.write(f"Estimate for {forecast['date']:%d %b %Y}: EUR {forecast['price']:.3f}/L")
        st.write(f"Test mean absolute error - model: EUR {forecast['model_error']:.4f}/L; "
                 f"unchanged-price baseline: EUR {forecast['baseline_error']:.4f}/L.")
        if forecast["model_error"] < forecast["baseline_error"]:
            st.success("The model was more accurate than the baseline in this test.")
        else:
            st.info("The unchanged-price baseline was at least as accurate in this test.")
        comparison = forecast["comparison"]
        fig, ax = plt.subplots(figsize=(9, 3.5))
        for column in ["Observed price", "Model estimate", "Unchanged-price baseline"]:
            ax.plot(comparison["date"], comparison[column], label=column)
        ax.set_ylabel("Pump price (EUR/L)")
        ax.legend()
        fig.autofmt_xdate()
        st.pyplot(fig)
        plt.close(fig)
        st.caption(f"Older {forecast['train_rows']} pairs train the test model; "
                   f"newer {forecast['test_rows']} pairs test it "
                   f"({forecast['test_start']:%d %b %Y} to {forecast['test_end']:%d %b %Y}).")
        st.write("The model learns: next price = intercept + coefficient × previous price. "
                 "Each test estimate uses the preceding observed week's price. "
                 "The training model stays fixed throughout this test.")
        st.write("After testing, it is refitted on all available pairs (at most 156) "
                 "for the next estimate. Missing weeks are skipped. "
                 "Past accuracy does not guarantee future accuracy.")
        st.caption("All model prices include taxes. Selecting the estimate in the sidebar "
                   "uses it as a flat assumption for the monthly budget, not a monthly forecast.")

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
    st.dataframe(load_plans(), hide_index=True)
    st.caption("Everyone using the same deployed app can see its saved plans. "
               "Local cloud files can disappear after a restart or redeployment.")

st.caption("Source: " + metadata["source"] + ". Prices are in EUR per litre.")
st.markdown(f"[Source and reporting methodology]({SOURCE_PAGE})")
