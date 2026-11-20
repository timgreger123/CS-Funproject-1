"""Small learning extension: numeric regression instead of classification.

Assignments 10/11 teach features, targets, fit(), predict() and held-out data.
Here the target is a price rather than a flower/wine class. We also keep the
dates in order because a model must not train on future observations.
"""

from datetime import timedelta

import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error


def make_price_pairs(history):
    """Make examples: previous week's price -> this week's observed price."""
    history = history.sort_values("date").reset_index(drop=True)
    examples = []
    for i in range(1, len(history)):
        previous = history.iloc[i - 1]
        current = history.iloc[i]
        # Skip gaps rather than inventing a missing observation.
        if current["date"] - previous["date"] == timedelta(days=7):
            examples.append({
                "date": current["date"],
                "previous_price": previous["price_eur_per_litre"],
                "actual_price": current["price_eur_per_litre"],
            })
    return pd.DataFrame(examples, columns=["date", "previous_price", "actual_price"])


def estimate_next_week(history):
    """Train one model, check it once, then refit for the next-week estimate."""
    # Fixed in advance: at most 156 recent, valid weekly pairs, not tuned on test data.
    examples = make_price_pairs(history).tail(156).reset_index(drop=True)
    if len(examples) < 30:
        raise ValueError("The model needs at least 30 consecutive-week price pairs.")

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

    # Baseline: next week's price is unchanged from the previous week.
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
    next_input = pd.DataFrame({"previous_price": [latest["price_eur_per_litre"]]})
    next_price = float(model.predict(next_input)[0])

    return {
        "price": next_price,
        "date": latest["date"] + timedelta(days=7),
        "model_error": model_error,
        "baseline_error": baseline_error,
        "comparison": comparison,
        "train_rows": len(training),
        "test_rows": len(testing),
        "test_start": testing["date"].iloc[0],
        "test_end": testing["date"].iloc[-1],
        "refit_rows": len(examples),
    }
