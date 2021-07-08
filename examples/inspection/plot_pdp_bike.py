"""
===============================================================
Partial Dependence and Individual Conditional Expectation Plots
===============================================================

Partial dependence plots show the dependence between the target function [2]_
and a set of features of interest, marginalizing over the values of all other
features (the complement features). Due to the limits of human perception, the
size of the set of features of interest must be small (usually, one or two)
thus they are usually chosen among the most important features.

Similarly, an individual conditional expectation (ICE) plot [3]_
shows the dependence between the target function and a feature of interest.
However, unlike partial dependence plots, which show the average effect of the
features of interest, ICE plots visualize the dependence of the prediction on a
feature for each :term:`sample` separately, with one line per sample.
Only one feature of interest is supported for ICE plots.

This example shows how to obtain partial dependence and ICE plots from a
:class:`~sklearn.neural_network.MLPRegressor` and a
:class:`~sklearn.ensemble.HistGradientBoostingRegressor` trained on the
bike sharing dataset. The example is inspired from [1]_.

.. [1] `Molnar, Christoph. "Interpretable machine learning.
       A Guide for Making Black Box Models Explainable",
       2019. <https://christophm.github.io/interpretable-ml-book/>`_

.. [2] For classification you can think of it as the regression score before
       the link function.

.. [3] `Goldstein, A., Kapelner, A., Bleich, J., and Pitkin, E., Peeking Inside
       the Black Box: Visualizing Statistical Learning With Plots of
       Individual Conditional Expectation. (2015) Journal of Computational and
       Graphical Statistics, 24(1): 44-65 <https://arxiv.org/abs/1309.6392>`_
"""

# Authors : Guillaume Lemaitre <g.lemaitre58@gmail.com>
#           Madhura Jayaratne
#           Nicolas Hug <contact@nicolas-hug.com>
#           Olivier Grisel <olivier.grisel@ensta.org>
# License : BSD 3 clause

print(__doc__)

# %%
# Bike sharing dataset preprocessing
# ----------------------------------
#
# We will use the bike sharing dataset. The goal is to predict the number of bike
# rentals using weather and season data as well as the datetime information.
from sklearn.datasets import fetch_openml

bikes = fetch_openml("Bike_Sharing_Demand", version=2, as_frame=True)
X, y = bikes.data, bikes.target

# %%
# The feature `"weather"` have a particularity: the category `"heavy_rain"` is a rare
# category.
X["weather"].value_counts()

# %%
# Because of this rare category, we will collapse it into `"rain"`.
X["weather"].replace(to_replace="heavy_rain", value="rain", inplace=True)

# %%
# We will have a closer look regarding the `"year"` feature.
X["year"].value_counts()

# %%
# We see that we have data from two years. We will use the first year to  train the
# model and the second year to test the model.
mask_training = X["year"] == 0.0
X_train, y_train = X[mask_training], y[mask_training]
X_test, y_test = X[~mask_training], y[~mask_training]
X_train = X_train.drop(columns=["year"])
X_test = X_test.drop(columns=["year"])

# %%
# We can check the dataset information to see that we have heterogeneous data type. We
# will have to preprocess the different columns accordingly.
X_train.info()

# %%
# From the previous information, we will consider the `category` columns as nominal
# categorical features. In addition, we will consider the date and time information as
# categorical features as well.
#
# So we will manually defined the columns containing the numerical and categorical
# features.
numerical_features = [
    "temp",
    "feel_temp",
    "humidity",
    "windspeed",
]
categorical_features = X_train.columns.drop(numerical_features)

# %%
# Before to go into details regarding the preprocessing of the different machine
# learning pipeline, we will try to get some additional intuitions regarding the dataset
# that could be helpful to understand the model statistical performance and results of
# the partial dependence analysis.
#
# We will plot the average number of bike rentals by grouping the data by season and
# by year.
from itertools import product
import numpy as np
import matplotlib.pyplot as plt

days = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
hours = tuple(range(24))
xticklabels = [f"{day}\n{hour}:00" for day, hour in product(days, hours)]
xtick_start, xtick_period = 6, 12

fig, axs = plt.subplots(nrows=2, figsize=(8, 6), sharey=True, sharex=True)
average_bike_rentals = bikes.frame.groupby(
    ["year", "season", "weekday", "hour"]
).mean()["count"]
for ax, (idx, df) in zip(axs, average_bike_rentals.groupby("year")):
    df.groupby("season").plot(ax=ax, legend=True)

    # decorate the plot
    ax.set_xticks(
        np.linspace(
            start=xtick_start,
            stop=len(xticklabels),
            step=len(xticklabels) // xtick_period,
        )
    )
    ax.set_xticklabels(xticklabels[xtick_start::xtick_period])
    ax.set_xlabel("")
    ax.set_ylabel("Average number of bike rentals")
    ax.set_title(
        f"Bike rental for {'2010 (train set)' if idx == 0.0 else '2011 (test set)'}"
    )
    ax.set_ylim(0, 1_000)
    ax.set_xlim(0, len(xticklabels))
    ax.legend(loc=2)

# %%
# The first striking difference between the train and test set is that the number of
# bike rentals is higher in the test set. For this reason, it will not be surprising to
# get a machine learning model that will be underestimate the number of bike rentals. We
# also observe that the number of bike rentals is lower during the spring season. In
# addition, we see that during the working day, there is a specific pattern around 6-7
# am and 5-6 pm with some peaks of bike rentals. We can keep in mind these different
# intuitions and use them to understand the partial dependence plot.
#
# Preprocessor for machine-learning models
# ----------------------------------------
#
# Since we will use later two different models, a
# :class:`~sklearn.neural_network.MLPRegressor` and a
# :class:`~sklearn.ensemble.HistGradientBoostingRegressor`, we will create two different
# preprocessors, specific for each model.
#
# Preprocessor for the neural network model
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# We will use a :class:`~sklearn.preprocessing.QuantileTransformer` to scale the
# numerical features and encode the categorical features with a
# :class:`~sklearn.preprocessing.OneHotEncoder`.
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import QuantileTransformer
from sklearn.preprocessing import OneHotEncoder

mlp_preprocessor = ColumnTransformer(
    transformers=[
        ("num", QuantileTransformer(n_quantiles=100), numerical_features),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
    ]
)

# %%
# Preprocessor for the gradient boosting model
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# For the gradient boosting model, we will let as-is the numerical features and only
# end-encode the categorical features using a
# :class:`~sklearn.preprocessing.OrdinalEncoder`.
from sklearn.preprocessing import OrdinalEncoder

hgbdt_preprocessor = ColumnTransformer(
    transformers=[("cat", OrdinalEncoder(), categorical_features)],
    remainder="passthrough",
    sparse_threshold=1,
)

# %%
# 1-way partial dependence with different models
# ----------------------------------------------
#
# In this section, we will compute 1-way partial dependence with two different
# machine-learning models: (i) a multi-layer perceptron and (ii) a
# gradient-boosting. With these two models, we illustrate how to compute and
# interpret both partial dependence plot (PDP) for both numerical and categorical
# features and individual conditional expectation (ICE).
#
# Multi-layer perceptron
# ......................
#
# Let's fit a :class:`~sklearn.neural_network.MLPRegressor` and compute
# single-variable partial dependence plots.
from time import time
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline

print("Training MLPRegressor...")
tic = time()
mlp_model = make_pipeline(
    mlp_preprocessor,
    MLPRegressor(
        hidden_layer_sizes=(50, 50), learning_rate_init=0.01, early_stopping=True
    ),
)
mlp_model.fit(X_train, y_train)
print(f"done in {time() - tic:.3f}s")
print(f"Test R2 score: {mlp_model.score(X_test, y_test):.2f}")

# %%
# We configured a pipeline using the preprocessor that we created specifically for the
# neural network and tuned the neural network size and learning rate to get a reasonable
# compromise between training time and predictive performance on a test set.
#
# Importantly, this tabular dataset has very different dynamic ranges for its
# features. Neural networks tend to be very sensitive to features with varying
# scales and forgetting to preprocess the numeric feature would lead to a very
# poor model.
#
# It would be possible to get even higher predictive performance with a larger
# neural network but the training would also be significantly more expensive.
#
# Note that it is important to check that the model is accurate enough on a
# test set before plotting the partial dependence since there would be little
# use in explaining the impact of a given feature on the prediction function of
# a poor model. In this regard, our model is working reasonably well.
import matplotlib.pyplot as plt
from sklearn.inspection import plot_partial_dependence

print("Computing partial dependence plots...")
features = [
    "temp",
    "humidity",
    "windspeed",  # numerical features
    "season",
    "weather",
    "hour",  # categorical features
]
tic = time()
_, ax = plt.subplots(ncols=3, nrows=2, figsize=(9, 8))
display = plot_partial_dependence(
    mlp_model,
    X_train,
    features,
    categorical_features=categorical_features,
    kind="average",
    grid_resolution=100,
    n_jobs=3,
    ax=ax,
)
print(f"done in {time() - tic:.3f}s")
_ = display.figure_.suptitle(
    "Partial dependence of the number of bike rentals\n"
    "for the bike rental dataset with an MLPRegressor",
    fontsize=16,
)

# %%
# Gradient boosting
# .................
#
# Let's now fit a :class:`~sklearn.ensemble.HistGradientBoostingRegressor` and
# compute the partial dependence on the same features. We will also use the
# specific preprocessor we created for this model.
from sklearn.ensemble import HistGradientBoostingRegressor

print("Training HistGradientBoostingRegressor...")
tic = time()
hgbdt_model = make_pipeline(hgbdt_preprocessor, HistGradientBoostingRegressor())
hgbdt_model.fit(X_train, y_train)
print(f"done in {time() - tic:.3f}s")
print(f"Test R2 score: {hgbdt_model.score(X_test, y_test):.2f}")

# %%
# Here, we used the default hyperparameters for the gradient boosting model
# without any preprocessing as tree-based models are naturally robust to
# monotonic transformations of numerical features.
#
# Note that on this tabular dataset, Gradient Boosting Machines are both
# significantly faster to train and more accurate than neural networks. It is
# also significantly cheaper to tune their hyperparameters (the defaults tend
# to work well while this is not often the case for neural networks).
#
# We will plot the partial dependence for some of the numerical and categorical
# features.
print("Computing partial dependence plots...")
tic = time()
_, ax = plt.subplots(ncols=3, nrows=2, figsize=(9, 8))
display = plot_partial_dependence(
    hgbdt_model,
    X_train,
    features,
    categorical_features=categorical_features,
    kind="average",
    grid_resolution=100,
    n_jobs=3,
    ax=ax,
    method="brute",
)
print(f"done in {time() - tic:.3f}s")
_ = display.figure_.suptitle(
    "Partial dependence of the number of bike rentals\n"
    "for the bike rental dataset with a gradient boosting",
    fontsize=16,
)

# %%
# Analysis of the plots
# .....................
# In all plots, the tick marks on the x-axis represent the deciles of the
# feature values in the training data.
#
# We will first look at the PDPs for the numerical features. For both models, the
# general trend of the PDP of the temperature is that the number of bike rentals is
# increasing with temperature. We can make a similar analysis but with the opposite
# trend for the humidity features. The number of bike rentals is decreasing when the
# humidity increases. Finally, we see the same trend for the windspeed feature. The
# number of bike rentals is decreasing when the windspeed is increasing for both models.
# We also observe that :class:`~sklearn.neural_network.MLPRegressor` has much
# smoother predictions than :class:`~sklearn.ensemble.HistGradientBoostingRegressor`.
#
# Now, we will look at the partial dependence plots for the categorical features.
#
# We observe that the spring season is the lowest bar for the season feature. With the
# weather feature, the rain category is the lowest bar. Regarding the hour feature,
# we see two peaks around the 7 am and 6 pm. These findings are in line with the
# with the observations we made earlier on the dataset.
#
# However, it is worth noting that we are creating potential meaningless
# synthetic samples if features are correlated.
#
# 2D interaction plots
# --------------------
#
# PDPs with two features of interest enable us to visualize interactions among
# them. However, ICEs cannot be plotted in an easy manner and thus interpreted.
# Another consideration is linked to the performance to compute the PDPs. With
# the tree-based algorithm, when only PDPs are requested, they can be computed
# on an efficient way using the `'recursion'` method.
print("Computing partial dependence plots...")
features = ["season", "weather"]
tic = time()
display = plot_partial_dependence(
    hgbdt_model,
    X_test,
    features,
    kind="average",
    subsample=20,
    n_jobs=-1,
    grid_resolution=20,
    random_state=0,
    categorical_features=categorical_features,
)
print(f"done in {time() - tic:.3f}s")
display.figure_.suptitle(
    "XXX",
)
display.figure_.subplots_adjust(hspace=1.0)

# %%
print("Computing partial dependence plots...")
features = ["temp", "humidity", ("temp", "humidity")]
_, ax = plt.subplots(ncols=3, figsize=(9, 4))
tic = time()
display = plot_partial_dependence(
    hgbdt_model,
    X_train,
    features,
    kind="average",
    n_jobs=-1,
    grid_resolution=30,
    random_state=0,
    ax=ax,
)
print(f"done in {time() - tic:.3f}s")
display.figure_.suptitle(
    "XXX",
)
display.figure_.subplots_adjust(wspace=0.5, hspace=0.5)

# %%

# %%

average_week_demand = bikes.frame.groupby(["year", "season", "weekday", "hour"]).mean()
# average_week_demand["count"].groupby(["year", "season"]).plot.bar(figsize=(12, 4))
average_week_demand["count"].groupby(["season"]).plot(figsize=(12, 4))

# %%
average_week_demand["count"].groupby(["season"]).plot.bar(figsize=(12, 4))

# %%
y_pred = mlp_model.predict(X)

# %%
from sklearn.metrics import r2_score

plt.scatter(y_train, y_pred[mask_training], alpha=0.2)
plt.title(f"Training set: {r2_score(y_train, y_pred[mask_training]):.3f}")

# %%
plt.scatter(y_test, y_pred[~mask_training], alpha=0.2)
plt.title(f"Training set: {r2_score(y_test, y_pred[~mask_training]):.3f}")

# %%
residuals = y - y_pred
plt.scatter(y_train, residuals[mask_training], alpha=0.2)

# %%
plt.scatter(y_test, residuals[~mask_training], alpha=0.2)

# %%
