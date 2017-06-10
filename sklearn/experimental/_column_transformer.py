"""
The :mod:`sklearn.pipeline` module implements utilities to build a composite
estimator, as a chain of transforms and estimators.
"""
# Author: Andreas Mueller
#         Joris Van den Bossche
# License: BSD


import numpy as np

from ..externals import six
from ..pipeline import FeatureUnion

__all__ = ['ColumnTransformer']


_ERR_MSG_1DCOLUMN = ("1D data passed to a transformer that expects 2D data. "
                     "Try to specify the column selection as a list of one "
                     "item instead of a scalar.")


class ColumnTransformer(FeatureUnion):
    """Applies transformers to columns of an array or pandas DataFrame.

    This estimator applies transformer objects to columns or fields of the
    input, then concatenates the results. This is useful for heterogeneous or
    columnar data, to combine several feature extraction mechanisms into a
    single transformer.

    Read more in the :ref:`User Guide <column_transformer>`.

    Parameters
    ----------
    transformer_list : list of tuples
        List of (name, transformer, column) tuples specifying the transformer
        objects to be applied to subsets of the data. The columns can be
        specified as a scalar or slice/list (for multiple columns) of integer
        or string values. Integers are interpreted as the positional columns,
        strings as the keys (column labels) of `X`.
        When passing a single column to a transformer that expects 2D input
        data, the column should be specified a list of one element.

    n_jobs : int, optional
        Number of jobs to run in parallel (default 1).

    transformer_weights : dict, optional
        Multiplicative weights for features per transformer.
        Keys are transformer names, values the weights.

    Examples
    --------
    >>> from sklearn.experimental import ColumnTransformer
    >>> from sklearn.preprocessing import Normalizer
    >>> union = ColumnTransformer(
    ...     [("norm1", Normalizer(norm='l1'), [0, 1]),
    ...      ("norm2", Normalizer(norm='l1'), [2, 3])])
    >>> X = np.array([[0., 1., 2., 2.],
    ...               [1., 1., 0., 1.]])
    >>> union.fit_transform(X)    # doctest: +NORMALIZE_WHITESPACE
    array([[ 0. ,  1. ,  0.5,  0.5],
           [ 0.5,  0.5,  0. ,  1. ]])

    """
    def _iter(self, X=None, skip_none=True):
        """Generate (name, trans, column, weight) tuples
        """
        get_weight = (self.transformer_weights or {}).get
        return ((name, trans, _get_column(X, column), get_weight(name))
                for name, trans, column in self.transformer_list
                if not skip_none or trans is not None)

    def _update_transformer_list(self, transformers):
        transformers = iter(transformers)
        self.transformer_list[:] = [
            (name, None if old is None else next(transformers), column)
            for name, old, column in self.transformer_list
        ]

    def fit(self, X, y=None):
        """Fit all transformers using X.

        Parameters
        ----------
        X : array-like or DataFrame of shape [n_samples, n_features]
            Input data, of which specified subsets are used to fit the
            transformers.

        y : array-like, shape (n_samples, ...), optional
            Targets for supervised learning.

        Returns
        -------
        self : ColumnTransformer
            This estimator
        """
        try:
            return super(ColumnTransformer, self).fit(X, y=y)
        except ValueError as e:
            if "Got X with X.ndim=1. Reshape your data" in str(e):
                raise ValueError(_ERR_MSG_1DCOLUMN)
            else:
                raise e

    def fit_transform(self, X, y=None, **fit_params):
        """Fit all transformers, transform the data and concatenate results.

        Parameters
        ----------
        X : array-like or DataFrame of shape [n_samples, n_features]
            Input data, of which specified subsets are used to fit the
            transformers.

        y : array-like, shape (n_samples, ...), optional
            Targets for supervised learning.

        Returns
        -------
        X_t : array-like or sparse matrix, shape (n_samples, sum_n_components)
            hstack of results of transformers. sum_n_components is the
            sum of n_components (output dimension) over transformers.
        """
        try:
            return super(ColumnTransformer, self).fit_transform(X, y=y,
                                                                **fit_params)
        except ValueError as e:
            if "Got X with X.ndim=1. Reshape your data" in str(e):
                raise ValueError(_ERR_MSG_1DCOLUMN)
            else:
                raise e

    def transform(self, X):
        """Transform X separately by each transformer, concatenate results.

        Parameters
        ----------
        X : array-like or DataFrame of shape [n_samples, n_features]
            Input data, of which specified subsets are used to fit the
            transformers.

        Returns
        -------
        X_t : array-like or sparse matrix, shape (n_samples, sum_n_components)
            hstack of results of transformers. sum_n_components is the
            sum of n_components (output dimension) over transformers.
        """
        try:
            return super(ColumnTransformer, self).transform(X)
        except ValueError as e:
            if "Got X with X.ndim=1. Reshape your data" in str(e):
                raise ValueError(_ERR_MSG_1DCOLUMN)
            else:
                raise e


def _get_column(X, key):
    """
    Get feature column(s) from input data X.

    Supported input types (X): numpy arrays, sparse arrays and dataframes

    Supported key types (key):
    - scalar: output is 1D
    - lists, slices: output is 2D

    Supported key data types:

    - integer (positional):
        - supported for (sparse) arrays or dataframes
    - string (key-based):
        - only supported for dataframes
        - So no keys other than strings are allowed (while in principle you
          can use any hashable object as key).

    """
    if X is None:
        return X

    # check whether we have string column names or integers
    if (isinstance(key, int)
            or (isinstance(key, list)
                and all(isinstance(col, int) for col in key))
            or (isinstance(key, slice)
                and isinstance(key.start, (int, type(None)))
                and isinstance(key.stop, (int, type(None))))):
        column_names = False
    elif (isinstance(key, six.string_types)
            or (isinstance(key, list)
                and all(isinstance(col, six.string_types) for col in key))
            or (isinstance(key, slice)
                and isinstance(key.start, (six.string_types, type(None)))
                and isinstance(key.stop, (six.string_types, type(None))))):
        column_names = True
    else:
        raise ValueError("No valid specification of the columns. Only a "
                         "scalar, list or slice of all integers or all "
                         "strings is allowed")

    if column_names:
        if hasattr(X, 'loc'):
            # pandas dataframes
            return X.loc[:, key]
        else:
            raise ValueError("Specifying the columns using strings is only "
                             "supported for pandas DataFrames")
    else:
        if hasattr(X, 'iloc'):
            # pandas dataframes
            return X.iloc[:, key]
        else:
            # numpy arrays, sparse arrays
            return X[:, key]
