#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""========================================================
Effect of smoothing noise when using QuantileTransformer
========================================================

This example shows the effect of applying a small noise before
computing the quantiles in the QuantileTransformer. This parameter can
be used if a constant feature value is predominant in the dataset. It
will lead to a difficult interpretation when the quantiles computed
are introspected.

"""

# Author:  Guillaume Lemaitre <g.lemaitre58@gmail.com>
# License: BSD 3 clause

import numpy as np
import matplotlib.pyplot as plt

from sklearn.preprocessing import QuantileTransformer

print(__doc__)

N_QUANTILES = 1000
FEAT_VAL = 3.0


def plot_transform_feat_val(ax, transformer, title):
    """Plot the full transformation mapping the feature values as well as
    a single feature."""
    ref = np.linspace(0, 1, num=N_QUANTILES)

    ax.plot(transformer.quantiles_, ref)
    ax.scatter(FEAT_VAL, transformer.transform(FEAT_VAL), c='r',
               label=r'$f({0}) = {1:.2f}$'.format(
                   FEAT_VAL,
                   np.ravel(transformer.transform(FEAT_VAL))[0]))
    ax.set_xlabel('Feature values')
    ax.set_ylabel('Quantiles in %')
    ax.set_title(title)
    ax.legend(loc=4)
    # make nice axis layout
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.get_xaxis().tick_bottom()
    ax.get_yaxis().tick_left()
    ax.set_xlim([1, 5.1])
    ax.set_ylim([0, 1])
    ax.spines['left'].set_position(('outward', 10))
    ax.spines['bottom'].set_position(('outward', 10))


###############################################################################
# We can create a synthetic dataset which could represent the
# customers' ratings for restaurant. The scale used is ranging from 1
# to 5 and a large number of customers attributed a grade of 3 to the
# current restaurant.

X = np.array([1] * 1000 +
             [2] * 2000 +
             [3] * 7000 +
             [4] * 2000 +
             [5] * 1000).reshape(-1, 1)

# create the subplots
_, (ax1, ax2) = plt.subplots(1, 2)

###############################################################################
# By default, the ``QuantileTransformer`` does not apply any smoothing
# noise.  Dealing with dataset with predominant values, the quantile
# return for such value will correspond to the largest quantile
# computed. In practise, marchine learning algorithms will usually not
# be affected by such characteristics. However, manual interpretation
# might be counter intuitive.

qt = QuantileTransformer(n_quantiles=N_QUANTILES)
qt.fit(X)
plot_transform_feat_val(ax1, qt, 'Mapping without using smoothing noise')

###############################################################################
# From the above plot, we would expect that a vote corresponding to
# the value 3 would be mapped to the median (e.g., 0.5). However, the
# default behaviour of the 'interp' numpy function will map this
# feature value to the greater quantile as show by the marker in the
# figure.
#
# A solution is to applied a small smoothing noise before the
# computation of the quantiles. The parameter 'smoothing_noise' offers
# this possibility as illustrated below.

qt = QuantileTransformer(n_quantiles=N_QUANTILES,
                         smoothing_noise=1e-7)
qt.fit(X)
plot_transform_feat_val(ax2, qt, 'Mapping using smoothing noise')

plt.show()
