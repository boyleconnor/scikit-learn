# cython: language_level=3
"""This module contains njitted routines for building histograms.

A histogram is an array with n_bins entry of type HISTOGRAM_DTYPE. Each
feature has its own histogram. A histogram contains the sum of gradients and
hessians of all the samples belonging to each bin.
"""
import numpy as np
cimport numpy as np

from .types import HISTOGRAM_DTYPE
from .types cimport X_BINNED_DTYPE_C
from .types cimport Y_DTYPE_C
from .types cimport hist_struct

"""compute (hist_a - hist_b) in out"""
cpdef void _subtract_histograms(
    unsigned int n_bins,
    const hist_struct [::1] hist_a,  # IN
    const hist_struct [::1] hist_b,  # IN
    hist_struct [::1] out) nogil  # OUT


"""Return histogram for a given feature."""
cpdef void _build_histogram(
    unsigned int n_bins,
    const unsigned int [::1] sample_indices,  # IN
    const X_BINNED_DTYPE_C [::1] binned_feature,  # IN
    const Y_DTYPE_C [::1] ordered_gradients,  # IN
    const Y_DTYPE_C [::1] ordered_hessians,  # IN
    hist_struct [::1] out) nogil  # OUT


"""Return histogram for a given feature, not updating hessians.
Used when the hessians of the loss are constant (tipycally LS loss)."""
cpdef void _build_histogram_no_hessian(
    unsigned int n_bins,
    const unsigned int [::1] sample_indices,  # IN
    const X_BINNED_DTYPE_C [::1] binned_feature,  # IN
    const Y_DTYPE_C [::1] ordered_gradients,  # IN
    hist_struct [::1] out) nogil  # OUT

"""Compute histogram of the root node.
Unlike other nodes, the root node has to find the split among *all* the
samples from the training set. binned_feature and all_gradients /
all_hessians already have a consistent ordering."""
cpdef void _build_histogram_root(
    unsigned int n_bins,
    const X_BINNED_DTYPE_C [::1] binned_feature,  # IN
    const Y_DTYPE_C [::1] all_gradients,  # IN
    const Y_DTYPE_C [::1] all_hessians,  # IN
    hist_struct [::1] out) nogil  # OUT

"""Compute histogram of the root node, not updating hessians.
Used when the hessians of the loss are constant (tipycally LS loss)."""
cpdef void _build_histogram_root_no_hessian(
    unsigned int n_bins,
    const X_BINNED_DTYPE_C [::1] binned_feature,  # IN
    const Y_DTYPE_C [::1] all_gradients,  # IN
    hist_struct [::1] out) nogil  # OUT
