"""Run from this folder: python -m streamlit run app.py"""
from __future__ import annotations

import html
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from diesel_engine import (
    Budget, COUNTRIES, SOURCE_PAGE, ensure_database, forecast_next_week,
    list_plans, load_history, load_metadata, refresh_from_ec, save_plan,
    scenario_table,
)

st.set_page_config(page_title="Diesel Budget Planner", page_icon="⛽", layout="wide")

st.markdown("""
<style>
.block-container {padding-top:2rem; padding-bottom:3rem; max-width:1450px;}
[data-testid="stSidebar"] {border-right:1px solid #263548;}
.eyebrow {color:#28d7b0; font-size:.76rem; font-weight:700; letter-spacing:.16em; margin-bottom:.6rem;}
.hero-note {color:#a9b9ca; font-size:1.05rem; margin-top:-.5rem; margin-bottom:1.7rem;}
div[data-testid="stMetric"] {background:#152232; border:1px solid #29384b; border-radius:12px; padding:16px;}
div[data-testid="stMetricLabel"] {color:#adbdcf;}
.source-pill {display:inline-block; color:#a9b9ca; border:1px solid #2b3c50; padding:5px 10px; border-radius:20px; font-size:.77rem;}
div[data-testid="stTabs"] {margin-top:1.4rem;}
</style>
""", unsafe_allow_html=True)


def money(value):
    return f"€{value:,.0f}"


def style_chart(fig, height=360):
    fig.update_layout(
        template="plotly_dark", height=height, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#d5e3f2", family="Arial"),
        margin=dict(l=15, r=20, t=25, b=35), hovermode="x unified",
        legend=dict(orientation="h", y=-0.18),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#263449", zerolinecolor="#72849a")
    return fig


@st.cache_data(show_spinner=False, max_entries=32)
def cached_forecast(history):
    return forecast_next_week(history)


def apply_price(value):
    st.session_state["price"] = round(float(value), 3)


def restore_plan(payload):
    """Callbacks execute before widgets, so restoring widget values is safe."""
    state = st.session_state
    for key in ("country", "remove_vat", "vat_percent", "litres", "price", "revenue", "other_costs", "shock"):
        state[key] = payload[key]
    state["vat_country"] = payload["country"]
    state["budget_context"] = (payload["country"], payload["remove_vat"], float(payload["vat_percent"]))
    state["loaded_notice"] = "Saved inputs restored. The historical data and model use the current dataset."


try:
    ensure_database()
    metadata = load_metadata()
except (OSError, ValueError, KeyError) as exc:
    st.error("The bundled dataset could not be opened. Keep the data folder alongside this Python file.")
    st.caption(str(exc))
    st.stop()

state = st.session_state
state.setdefault("country", "DE")
for key, value in {"litres": 50000.0, "revenue": 180000.0, "other_costs": 65000.0,
                   "shock": 20, "remove_vat": True}.items():
    state.setdefault(key, value)

with st.sidebar:
    st.markdown('<div class="eyebrow">DIESEL / PLANNING DESK</div>', unsafe_allow_html=True)
    country = st.selectbox("Reference market", sorted(COUNTRIES, key=COUNTRIES.get),
                           format_func=lambda code: COUNTRIES[code], key="country")
    history = load_history(country)
    latest_date = history["date"].iloc[-1]
    latest_price = float(history["price_eur_per_litre"].iloc[-1])
    if state.get("vat_country") != country:
        state["vat_percent"] = float(metadata.get("vat_percent", {}).get(country, 0.0))
        state["vat_country"] = country
        if country not in metadata.get("vat_percent", {}):
            state["remove_vat"] = False
    st.caption(f"Published price: €{latest_price:.3f}/L · {latest_date:%d %b %Y}\n\nNational pump-price average, including taxes.")
    st.divider()
    st.subheader("Your monthly plan")
    st.caption("Editable example inputs. Replace them with your own fleet budget.")
    if country not in metadata.get("vat_percent", {}):
        st.info("A diesel VAT rate is unavailable for this market. Gross planning is the default; enter your own rate if you choose to exclude recoverable VAT.")
    remove_vat = st.checkbox("Exclude recoverable VAT", key="remove_vat",
        help="Select this when your company can reclaim diesel VAT and your revenue and other costs are also entered excluding VAT. Otherwise use gross amounts consistently.")
    vat_percent = st.number_input("Diesel VAT rate (%)", min_value=0.0, max_value=40.0,
                                  step=0.5, key="vat_percent", disabled=not remove_vat,
                                  help="Default from the Commission's diesel VAT sheet. Adjust for your own recoverable VAT treatment.")
    divisor = 1 + vat_percent / 100 if remove_vat else 1.0
    reference_budget_price = latest_price / divisor
    context = (country, remove_vat, float(vat_percent))
    if state.get("budget_context") != context:
        state["price"] = round(reference_budget_price, 3)
        state["budget_context"] = context
    basis = "excluding recoverable VAT" if remove_vat else "including VAT"
    st.number_input("Diesel use (litres/month)", min_value=0.0, max_value=1e9, step=1000.0, key="litres")
    st.number_input("Planning diesel price (EUR/L)", min_value=0.0, max_value=30.0,
                    step=0.01, format="%.3f", key="price",
                    help=f"Budget price {basis}. You can replace the national average with your own invoice or contract price.")
    st.button("Use latest benchmark", on_click=apply_price, args=(reference_budget_price,), key="use_benchmark")
    st.number_input("Revenue (EUR/month)", min_value=0.0, max_value=1e12, step=1000.0, key="revenue")
    st.number_input("Other operating costs (EUR/month)", min_value=0.0, max_value=1e12,
                    step=1000.0, key="other_costs", help="All operating costs other than diesel; for example staff, leases and insurance.")
    st.caption(f"Enter revenue and costs {basis}. Changing market or VAT basis resets the planning price to the benchmark.")
    st.divider()
    st.subheader("Custom price shock")
    st.slider("Change from your planning price (%)", min_value=-50, max_value=150,
               step=5, key="shock")
    st.caption("A stress assumption you choose, not a prediction of a conflict or its price impact.")
    st.divider()
    if st.button("Refresh official price data", key="refresh_data", width="stretch"):
        try:
            with st.spinner("Downloading the Commission's historical workbook..."):
                refreshed = refresh_from_ec()
            st.cache_data.clear()
            state["refresh_notice"] = f"Data refreshed. Latest published week: {refreshed['last_observation']}."
            st.rerun()
        except Exception as exc:
            st.error("Refresh failed. Your existing dataset is still available.")
            st.caption(str(exc)[:220])
    st.caption("Source: European Commission Weekly Oil Bulletin. The bundled copy also works offline.")

budget = Budget(float(state.litres), float(state.price), float(state.revenue), float(state.other_costs))
scenarios = scenario_table(budget, float(state.shock))
with st.spinner("Training and checking the weekly price model..."):
    try:
        forecast = cached_forecast(history)
    except ValueError as exc:
        forecast = None
        forecast_error = str(exc)

st.markdown('<div class="eyebrow">ENERGY COSTS. BUSINESS CONSEQUENCES.</div>', unsafe_allow_html=True)
st.title("Diesel Budget Planner")
st.markdown('<div class="hero-note">See what fuel-price changes mean for your costs, margins and next monthly budget.</div>', unsafe_allow_html=True)
st.markdown(f'<span class="source-pill">{html.escape(COUNTRIES[country])} &nbsp; · &nbsp; Reference week {latest_date:%d %b %Y} &nbsp; · &nbsp; Budget {html.escape(basis)}</span>', unsafe_allow_html=True)
for notice in ("refresh_notice", "loaded_notice"):
    if notice in state:
        st.success(state.pop(notice))
age_days = (date.today() - latest_date.date()).days
if age_days > 21:
    st.warning(f"The latest price observation is {age_days} days old. Refresh the data before treating the estimate as current.")

a, b, c, d = st.columns(4)
a.metric("Monthly diesel cost", money(budget.fuel_cost))
b.metric("Monthly operating result", money(budget.profit))
c.metric("Operating margin", f"{budget.margin:.1f}%" if budget.margin is not None else "N/A")
d.metric("Break-even diesel price", f"€{budget.break_even_price:.3f}/L" if budget.break_even_price is not None and budget.break_even_price >= 0 else "No positive threshold" if budget.break_even_price is not None else "N/A · no diesel use")

budget_tab, history_tab, model_tab, saved_tab = st.tabs([
    "Budget & scenarios", "Price history", "Next-week estimate", "Saved plans"
])

with budget_tab:
    st.subheader("How much pressure can your margin take?")
    st.caption("All results are monthly. Diesel volume, revenue and other operating costs stay constant across scenarios.")
    left, right = st.columns([1.65, 1])
    with left:
        fig = go.Figure(go.Bar(
            x=scenarios["Scenario"], y=scenarios["Operating result (EUR)"],
            marker_color=["#28d7b0" if p >= 0 else "#f27d7d" for p in scenarios["Operating result (EUR)"]],
            text=[money(p) for p in scenarios["Operating result (EUR)"]], textposition="outside",
            hovertemplate="%{x}<br>Monthly operating result: €%{y:,.0f}<extra></extra>",
        ))
        fig.update_yaxes(title="Monthly operating result (EUR)")
        st.plotly_chart(style_chart(fig), width="stretch")
    with right:
        st.markdown("#### Your margin buffer")
        if budget.litres == 0:
            st.info("With zero diesel use, a diesel-price change has no effect on this plan.")
        elif budget.profit <= 0:
            st.error("The current plan is already at or below break-even.")
            st.write("Adjust the revenue, operating costs or planning price to test an alternative budget.")
        elif budget.price > 0:
            headroom = (budget.break_even_price / budget.price - 1) * 100
            st.markdown(f"A diesel-price rise of **{headroom:.1f}%** would use up the current operating result.")
        else:
            st.write(f"The plan reaches break-even at €{budget.break_even_price:.3f} per litre.")
        st.write(f"Every additional **€0.10/L** adds **{money(budget.litres * 0.1)}** to your monthly diesel bill.")
        st.caption("Break-even price = (revenue − other operating costs) ÷ monthly litres.")
    st.dataframe(scenarios, hide_index=True, width="stretch", column_config={
        "Price change (%)": st.column_config.NumberColumn(format="%+.0f%%"),
        "Diesel price (EUR/L)": st.column_config.NumberColumn(format="€ %.3f"),
        "Diesel cost (EUR)": st.column_config.NumberColumn(format="€ %.0f"),
        "Extra fuel cost (EUR)": st.column_config.NumberColumn(format="€ %.0f"),
        "Operating result (EUR)": st.column_config.NumberColumn(format="€ %.0f"),
        "Operating margin (%)": st.column_config.NumberColumn(format="%.1f%%"),
    })
    st.caption("Stress scenarios describe assumed price changes. They do not assign probabilities to geopolitical events or forecast a war's consequences.")
    with st.expander("Save or export this plan", expanded=False):
        plan_name = st.text_input("Plan name", value="Monthly fleet budget", max_chars=100, key="plan_name")
        payload = {"country": country, "remove_vat": bool(remove_vat), "vat_percent": float(vat_percent),
                   "litres": budget.litres, "price": budget.price, "revenue": budget.revenue,
                   "other_costs": budget.other_costs, "shock": int(state.shock),
                   "reference_week": latest_date.date().isoformat()}
        if st.button("Save plan", key="save_plan"):
            try:
                save_plan(plan_name, payload)
                st.success("Plan saved. You can restore it in Saved plans.")
            except ValueError as exc:
                st.error(str(exc))
        report = scenarios.copy()
        report["Country"] = COUNTRIES[country]
        report["Budget price basis"] = basis
        report["Monthly litres"] = budget.litres
        report["Revenue (EUR)"] = budget.revenue
        report["Other costs (EUR)"] = budget.other_costs
        report["Reference week"] = latest_date.date().isoformat()
        st.download_button("Download scenario comparison (CSV)", report.to_csv(index=False).encode("utf-8-sig"),
                           file_name="diesel_budget_scenarios.csv", mime="text/csv", key="export_scenarios")

with history_tab:
    st.subheader(f"The price history behind your plan · {COUNTRIES[country]}")
    st.caption("Weekly national average automotive diesel prices, including VAT and excise duties. These are benchmarks, not live station quotes or negotiated fleet prices.")
    window = st.selectbox("Chart period", ["1 year", "3 years", "5 years", "All history"], index=1, key="history_window")
    chart_history = history if window == "All history" else history.loc[history.date >= latest_date - pd.DateOffset(years=int(window[0]))]
    fig = go.Figure(go.Scatter(x=chart_history.date, y=chart_history.price_eur_per_litre,
                   mode="lines", line=dict(color="#28d7b0", width=2.5), name="Published diesel price",
                   hovertemplate="€%{y:.3f}/L<extra></extra>"))
    fig.update_yaxes(title="Diesel pump-price benchmark (EUR/L)", tickformat=".2f")
    st.plotly_chart(style_chart(fig, 430), width="stretch")
    one, two, three = st.columns(3)
    one.metric("Latest published price", f"€{latest_price:.3f}/L")
    two.metric("Lowest in displayed period", f"€{chart_history.price_eur_per_litre.min():.3f}/L")
    three.metric("Highest in displayed period", f"€{chart_history.price_eur_per_litre.max():.3f}/L")
    st.download_button("Download this country's history (CSV)", history.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"diesel_history_{country}.csv", mime="text/csv", key="export_history")
    st.markdown(f"[European Commission source and methodology]({SOURCE_PAGE})")
    st.caption(f"{len(history):,} published observations · {history.date.min():%d %b %Y} to {latest_date:%d %b %Y}. Missing publication weeks are not fabricated in this chart.")

with model_tab:
    st.subheader("A short-term estimate, with an honest accuracy check")
    if forecast is None:
        st.warning(forecast_error)
    else:
        f1, f2, f3 = st.columns(3)
        f1.metric(f"Estimate for {forecast['date']:%d %b %Y}", f"€{forecast['price']:.3f}/L",
                  delta=f"{(forecast['price'] / latest_price - 1) * 100:+.1f}% vs latest publication", delta_color="inverse")
        f2.metric("ML average absolute error", f"€{forecast['mae']:.3f}/L")
        f3.metric("Unchanged-price baseline error", f"€{forecast['baseline_mae']:.3f}/L")
        st.caption(f"All three figures use pump prices including taxes. The estimate is one week after the latest observation, not a monthly price forecast.")
        if forecast["beats_baseline"]:
            st.success(f"The ML model beat the unchanged-price baseline over the last {forecast['evaluation_weeks']} published test weeks. This does not guarantee future performance.")
        else:
            st.info(f"Over the last {forecast['evaluation_weeks']} published test weeks, the simple unchanged-price baseline was at least as accurate as the ML model.")
        recent = history.tail(26)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=recent.date, y=recent.price_eur_per_litre, mode="lines", name="Published price", line=dict(color="#28d7b0", width=2.5)))
        fig.add_trace(go.Scatter(x=[latest_date, forecast["date"]], y=[latest_price, forecast["price"]],
                                mode="lines+markers", name="Next reporting week", line=dict(color="#f6c66b", dash="dot", width=2.5)))
        fig.update_yaxes(title="Pump price (EUR/L)", tickformat=".3f")
        st.plotly_chart(style_chart(fig, 320), width="stretch")
        st.button("Use ML estimate as the planning price", key="use_forecast",
                   on_click=apply_price, args=(forecast["price"] / divisor,))
        st.caption("This button applies that one-week estimate as a flat price assumption for your whole monthly budget. It does not predict every price during the month.")
        with st.expander("How the model is trained and evaluated", expanded=False):
            st.write("A Ridge regression is trained here on historical weekly price changes. It uses the previous eight weeks' prices, four/eight-week averages and recent changes. No pre-trained forecasting service or API key is used.")
            st.write(f"For each of the last {forecast['evaluation_weeks']} published test weeks, the model is fitted using only prices known before that week. The comparison model simply predicts the previous price. Both are measured using mean absolute error in EUR per litre.")
            st.write(f"The final model uses {forecast['train_rows']} published training observations, from {forecast['train_start']:%d %b %Y} to {forecast['train_end']:%d %b %Y}. Settings are fixed before testing; the model is then refitted on the available history for the next-week estimate.")
            st.write("Missing publication weeks are carried forward only to construct lag features. They are not treated as observed target prices or scored in the backtest.")
            st.write("The model does not use news or predict geopolitical escalation. Use the separately controlled stress scenarios to explore those assumptions.")
            bt = forecast["backtest"]
            fig = go.Figure()
            for column, color, dash in (("Actual", "#28d7b0", "solid"), ("ML forecast", "#f6c66b", "solid"), ("Unchanged-price baseline", "#8b9db3", "dot")):
                fig.add_trace(go.Scatter(x=bt.date, y=bt[column], name=column, mode="lines", line=dict(color=color, dash=dash)))
            fig.update_yaxes(title="Pump price (EUR/L)")
            st.plotly_chart(style_chart(fig), width="stretch")
            st.dataframe(bt, hide_index=True, width="stretch")

with saved_tab:
    st.subheader("Return to a saved monthly plan")
    st.caption("Plans are stored on the computer running this app. In a shared deployment, all users of that database can see these saved plans.")
    plans = list_plans()
    if not plans:
        st.info("No saved plans yet. Save one from the Budget & scenarios tab.")
    for plan in plans:
        p = plan["payload"]
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"**{plan['name']}**")
                st.caption(f"{COUNTRIES.get(p['country'], p['country'])} · {p['litres']:,.0f} L/month · €{p['price']:.3f}/L · saved {plan['created_at'][:10]}")
            with right:
                st.button("Restore inputs", key=f"restore_{plan['id']}", on_click=restore_plan, args=(p,))

st.divider()
st.caption("Planning calculation: revenue − other operating costs − diesel litres × diesel price. Financing costs, income taxes, changes in demand and customer fuel surcharges are not modelled.")
