# BEGIN AI-GENERATED CODE [AI-02]
# Source: OpenAI. (2026). ChatGPT [Large language model]. https://chatgpt.com/
# Initial version delivered on 20 November 2026.
# Swiss monthly estimates added on 24 November 2026.
# Retained output: CS-Funproject-1/price_model.py in
# Diesel_Planner_HSG_Updated.zip.
# Scope: The entire module, including pairing consecutive prices, training
# and testing the linear regression in date order, comparing it with the
# unchanged-price baseline, and estimating the next week's or month's price.


"""Small learning extension: numeric regression instead of classification.

Assignments 10/11 teach features, targets, fit(), predict() and held-out data.
Here the target is a price rather than a flower/wine class. We also keep the
dates in order because a model must not train on future observations.
"""

from datetime import timedelta

import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error


WEEK = timedelta(days=7)
MONTH = pd.DateOffset(months=1)


def make_price_pairs(history, interval=WEEK, price_column="price_eur_per_litre"):
    """Pair each observed price with the previous week or month's price."""
    history = history.sort_values("date").reset_index(drop=True)
    examples = []
    for i in range(1, len(history)):
        previous = history.iloc[i - 1]
        current = history.iloc[i]
        # Skip gaps rather than inventing a missing observation.
        if previous["date"] + interval == current["date"]:
            examples.append({
                "date": current["date"],
                "previous_price": previous[price_column],
                "actual_price": current[price_column],
            })
    return pd.DataFrame(examples, columns=["date", "previous_price", "actual_price"])


def estimate_next_price(history, interval=WEEK, price_column="price_eur_per_litre"):
    """Test the model once, then refit it to estimate the next period's price."""
    # Use a fixed cap of 156 recent, consecutive price pairs.
    examples = make_price_pairs(history, interval, price_column).tail(156).reset_index(drop=True)
    if len(examples) < 30:
        raise ValueError("The model needs at least 30 consecutive price pairs.")

    # Older 70% for training, newer 30% for testing. No random shuffle.
    split = int(len(examples) * 0.70)
    training = examples.iloc[:split]
    testing = examples.iloc[split:]
    X_train = training[["previous_price"]]
    y_train = training["actual_price"]
    X_test = testing[["previous_price"]]
    y_test = testing["actual_price"]

    model = LinearRegression()
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    # The baseline carries the previous observed price forward.
    baseline = testing["previous_price"]
    model_error = mean_absolute_error(y_test, predictions)
    baseline_error = mean_absolute_error(y_test, baseline)
    comparison = pd.DataFrame({
        "date": testing["date"],
        "Observed price": y_test,
        "Model estimate": predictions,
        "Unchanged-price baseline": baseline,
    })

    # Only AFTER measuring test performance do we refit on all available pairs.
    model.fit(examples[["previous_price"]], examples["actual_price"])
    latest = history.sort_values("date").iloc[-1]
    next_input = pd.DataFrame({"previous_price": [latest[price_column]]})
    next_price = float(model.predict(next_input)[0])

    return {
        "price": next_price,
        "date": latest["date"] + interval,
        "model_error": model_error,
        "baseline_error": baseline_error,
        "comparison": comparison,
        "train_rows": len(training),
        "test_rows": len(testing),
        "test_start": testing["date"].iloc[0],
        "test_end": testing["date"].iloc[-1],
        "refit_rows": len(examples),
    }


def estimate_next_week(history):
    """Estimate the next weekly EUR price for existing callers."""
    return estimate_next_price(history)


# END AI-GENERATED CODE [AI-02]