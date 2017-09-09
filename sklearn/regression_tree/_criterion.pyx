# cython: boundscheck=False
# cython: cdivision=True

from ._stats_node cimport StatsNode


cdef float _impurity_mse(StatsNode stats_node):
    """Compute the impurity in MSE sense

    Parameters
    ----------
    stats_node: StatsNode,
        The split record from which to compute the impurity

    Returns
    -------
    impurity: float,
        The impurity.
    """
    cdef float impurity
    impurity = (stats_node.sum_sq_y /
                stats_node.sum_weighted_samples)
    impurity -= ((stats_node.sum_y /
                  stats_node.sum_weighted_samples) ** 2.0)

    return impurity


cpdef float impurity_mse(float sum_y, float sum_sq_y, int n_samples,
                         float sum_weighted_samples):
    """Compute the impurity in MSE sense

    Parameters
    ----------
    stats_node: StatsNode,
        The split record from which to compute the impurity

    Returns
    -------
    impurity: float,
        The impurity.
    """

    cdef StatsNode stats_node = StatsNode(sum_y, sum_sq_y,
                                          n_samples, sum_weighted_samples)
    return _impurity_mse(stats_node)


cpdef float impurity_improvement(StatsNode c_stats,
                                 StatsNode r_stats,
                                 StatsNode l_stats,
                                 float sum_total_weighted_samples,
                                 criterion):
    """Compute the impurity improvement.

    Parameters
    ----------
    c_split_record: SplitRecord,
        Split record of the current node.

    sum_total_weighted_samples: float,
        The sum of all the weights for all samples.

    criterion: str, optional(default='mse')
        The criterion to use to compute the impurity improvement.

    Returns
    -------
    impurity_improvement: float,
        Impurity improvement
    """
    if criterion == 'mse':
        _impurity_func = _impurity_mse

    # impurity current node
    c_impurity = _impurity_func(c_stats)
    # impurity left child
    l_impurity = _impurity_func(l_stats)
    # impurity right child
    r_impurity = _impurity_func(r_stats)

    return ((c_stats.sum_weighted_samples /
             sum_total_weighted_samples) *
            (c_impurity -
             (l_stats.sum_weighted_samples /
              sum_total_weighted_samples * l_impurity) -
             (r_stats.sum_weighted_samples /
              sum_total_weighted_samples * r_impurity)))
