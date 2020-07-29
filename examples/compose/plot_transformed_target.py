#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
======================================================
Effect of transforming the targets in regression model
======================================================

In this example, we give an overview of
:class:`~sklearn.compose.TransformedTargetRegressor`. We use two examples
to illustrate the benefit of transforming the targets before learning a linear
regression model. The first example uses synthetic data while the second
example is based on the Ames housing data set.
"""

# Author: Guillaume Lemaitre <guillaume.lemaitre@inria.fr>
# License: BSD 3 clause

# %%
print(__doc__)

# %% [markdown]
# Synthetic example
##############################################################################
#
# A synthetic random regression dataset is generated. The targets ``y`` are
# modified by:
#
#   1. translating all targets such that all entries are
#      non-negative (by adding the absolute value of the lowest ``y``) and
#   2. applying an exponential function to obtain non-linear
#      targets which cannot be fitted using a simple linear model.
#
# Therefore, a logarithmic (`np.log1p`) and an exponential function
# (`np.expm1`) will be used to transform the targets before training a linear
# regression model and using it for prediction.

# %%
import numpy as np
from sklearn.datasets import make_regression

X, y = make_regression(n_samples=10000, noise=100, random_state=0)
y = np.expm1((y + abs(y.min())) / 200)
y_trans = np.log1p(y)

# %% [mardown]
# Below we plot the probability density functions of the target
# before and after applying the logarithmic functions.

# %%
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split

f, (ax0, ax1) = plt.subplots(1, 2)

ax0.hist(y, bins=100, density=True)
ax0.set_xlim([0, 2000])
ax0.set_ylabel('Probability')
ax0.set_xlabel('Target')
ax0.set_title('Target distribution')

ax1.hist(y_trans, bins=100, density=True)
ax1.set_ylabel('Probability')
ax1.set_xlabel('Target')
ax1.set_title('Transformed target distribution')

f.suptitle("Synthetic data", y=0.06, x=0.53)
f.tight_layout(rect=[0.05, 0.05, 0.95, 0.95])

X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=0)

# %% [markdown]
# At first, a linear model will be applied on the original targets. Due to the
# non-linearity, the model trained will not be precise during
# prediction. Subsequently, a logarithmic function is used to linearize the
# targets, allowing better prediction even with a similar linear model as
# reported by the median absolute error (MAE).

# %%
from sklearn.compose import TransformedTargetRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import plot_prediction_error

f, (ax0, ax1) = plt.subplots(1, 2, sharey=True)

ridge_cv = RidgeCV().fit(X_train, y_train)
ridge_cv_with_trans_target = TransformedTargetRegressor(
    regressor=RidgeCV(), func=np.log1p, inverse_func=np.expm1
).fit(X_train, y_train)

scorers = {"R2": "r2", "MAE": "neg_median_absolute_error"}

plot_prediction_error(ridge_cv, X_test, y_test, scoring=scorers, ax=ax0)
plot_prediction_error(
    ridge_cv_with_trans_target, X_test, y_test, scoring=scorers, ax=ax1
)

ax0.set_title('Ridge regression \n without target transformation')
ax1.set_title('Ridge regression \n with target transformation')
f.suptitle("Synthetic data", y=0.035)
f.tight_layout(rect=[0.05, 0.05, 0.95, 0.95])

# %% [markdown]
# Real-world data set
###############################################################################
#
# In a similar manner, the Ames housing data set is used to show the impact
# of transforming the targets before learning a model. In this example, the
# target to be predicted is the selling price of each house.

# %%
from sklearn.datasets import fetch_openml
from sklearn.preprocessing import quantile_transform

ames = fetch_openml(name="house_prices", as_frame=True)
# Keep only numeric columns
X = ames.data.select_dtypes(np.number)
# Remove columns with NaN or Inf values
X = X.drop(columns=['LotFrontage', 'GarageYrBlt', 'MasVnrArea'])
# Let's the price being in k$
y = ames.target / 1000
y_trans = quantile_transform(y.to_frame(),
                             n_quantiles=900,
                             output_distribution='normal',
                             copy=True).squeeze()
# %% [markdown]
# A :class:`~sklearn.preprocessing.QuantileTransformer` is used to normalize
# the target distribution before applying a
# :class:`~sklearn.linear_model.RidgeCV` model.

# %%
f, (ax0, ax1) = plt.subplots(1, 2)

ax0.hist(y, bins=100, density=True)
ax0.set_ylabel('Probability')
ax0.set_xlabel('Target')
ax0.text(s='Target distribution', x=1.2e5, y=9.8e-6, fontsize=12)
ax0.ticklabel_format(axis="both", style="sci", scilimits=(0, 0))

ax1.hist(y_trans, bins=100, density=True)
ax1.set_ylabel('Probability')
ax1.set_xlabel('Target')
ax1.text(s='Transformed target distribution', x=-6.8, y=0.479, fontsize=12)

f.suptitle("Ames housing data: selling price", y=0.04)
f.tight_layout(rect=[0.05, 0.05, 0.95, 0.95])

X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=1)

# %% [markdown]
# The effect of the transformer is weaker than on the synthetic data. However,
# the transformation results in an increase in :math:`R^2` and large decrease
# of the MAE. The residual plot (predicted target - true target vs predicted
# target) without target transformation takes on a curved, 'reverse smile'
# shape due to residual values that vary depending on the value of predicted
# target. With target transformation, the shape is more linear indicating
# better model fit.

# %%
from sklearn.preprocessing import QuantileTransformer

f, (ax0, ax1) = plt.subplots(2, 2, sharey="row", figsize=(6.5, 8))

ridge_cv = RidgeCV().fit(X_train, y_train)
ridge_cv_with_trans_target = TransformedTargetRegressor(
    regressor=RidgeCV(),
    transformer=QuantileTransformer(
        n_quantiles=900, output_distribution="normal"
    ),
).fit(X_train, y_train)

# plot the actual vs predicted values
scorers = {"R2": "r2", "MAE": "neg_median_absolute_error"}
plot_prediction_error(ridge_cv, X_test, y_test, scoring=scorers, ax=ax0[0])
plot_prediction_error(
    ridge_cv_with_trans_target, X_test, y_test, scoring=scorers, ax=ax0[1]
)
ax0[0].set_title("Ridge regression \n without target transformation")
ax0[1].set_title("Ridge regression \n with target transformation")

# plot the residuals vs the predicted values
y_pred = ridge_cv.predict(X_test)
ax1[0].scatter(y_pred, (y_pred - y_test), s=8, c="k")
ax1[0].set_ylabel('Residual')
ax1[0].set_xlabel('Predicted target')
ax1[0].ticklabel_format(axis="both", style="sci", scilimits=(0, 0))

y_pred = ridge_cv_with_trans_target.predict(X_test)
ax1[1].scatter(y_pred, (y_pred - y_test), s=8, c="k")
ax1[1].set_ylabel('Residual')
ax1[1].set_xlabel('Predicted target')
ax1[1].ticklabel_format(axis="both", style="sci", scilimits=(0, 0))

f.suptitle("Ames housing data: selling price", y=0.035)

plt.show()
