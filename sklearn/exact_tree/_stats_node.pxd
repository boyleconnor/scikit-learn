cdef struct StatsNode:
    double sum_y
    double sum_sq_y
    int n_samples
    double sum_weighted_samples


cdef inline void stats_node_reset(StatsNode* stats_node,
                                  double sum_y, double sum_sq_y, int n_samples,
                                  double sum_weighted_samples):
    stats_node[0].sum_y = sum_y
    stats_node[0].sum_sq_y = sum_sq_y
    stats_node[0].n_samples = n_samples
    stats_node[0].sum_weighted_samples = sum_weighted_samples


cdef void stats_node_clear(StatsNode* stats_node)


cdef inline void stats_node_iadd(StatsNode* l_stats_node,
                                 StatsNode* r_stats_node):
    l_stats_node[0].sum_y += r_stats_node[0].sum_y
    l_stats_node[0].sum_sq_y += r_stats_node[0].sum_sq_y
    l_stats_node[0].n_samples += r_stats_node[0].n_samples
    l_stats_node[0].sum_weighted_samples += r_stats_node[0].sum_weighted_samples


cdef inline void stats_node_isub(StatsNode* l_stats_node,
                                 StatsNode* r_stats_node):
    l_stats_node[0].sum_y -= r_stats_node[0].sum_y
    l_stats_node[0].sum_sq_y -= r_stats_node[0].sum_sq_y
    l_stats_node[0].n_samples -= r_stats_node[0].n_samples
    l_stats_node[0].sum_weighted_samples -= r_stats_node[0].sum_weighted_samples


cdef void stats_node_copy_to(StatsNode* src_stats_node,
                             StatsNode* dst_stats_node)
