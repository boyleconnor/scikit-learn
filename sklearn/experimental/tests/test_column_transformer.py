"""
Test the ColumnTransformer.
"""

import numpy as np
from scipy import sparse

from sklearn.utils.testing import assert_raise_message
from sklearn.utils.testing import assert_equal
from sklearn.utils.testing import assert_true
from sklearn.utils.testing import assert_false
from sklearn.utils.testing import assert_dict_equal
from sklearn.utils.testing import assert_array_equal
from sklearn.utils.testing import assert_allclose_dense_sparse
from sklearn.utils.testing import SkipTest

from sklearn.base import BaseEstimator
from sklearn.experimental import ColumnTransformer, make_column_transformer

from sklearn.preprocessing import StandardScaler, Normalizer


class Trans(BaseEstimator):
    def fit(self, X, y=None):
        return self

    def transform(self, X, y=None):
        return X


class SparseMatrixTrans(BaseEstimator):
    def fit(self, X, y=None):
        return self

    def transform(self, X, y=None):
        n_samples = len(X)
        return sparse.eye(n_samples, n_samples).tocsr()


def test_column_transformer():
    X_array = np.array([[0, 1, 2], [2, 4, 6]]).T

    X_res_first1D = np.array([0, 1, 2])
    X_res_second1D = np.array([2, 4, 6])
    X_res_first2D = X_res_first1D.reshape(-1, 1)
    X_res_both = X_array

    cases = [
        # single column 1D / 2D
        (0, X_res_first1D),
        ([0], X_res_first2D),
        # list-like
        ([0, 1], X_res_both),
        (np.array([0, 1]), X_res_both),
        # slice
        (slice(0, 1), X_res_first2D),
        (slice(0, 2), X_res_both),
        # boolean mask
        (np.array([True, False]), X_res_first2D),
    ]

    for selection, res in cases:
        ct = ColumnTransformer([('trans', Trans(), selection)])
        assert_array_equal(ct.fit_transform(X_array), res)
        assert_array_equal(ct.fit(X_array).transform(X_array), res)

    ct = ColumnTransformer([('trans1', Trans(), [0]),
                            ('trans2', Trans(), [1])])
    assert_array_equal(ct.fit_transform(X_array), X_res_both)
    assert_array_equal(ct.fit(X_array).transform(X_array), X_res_both)

    # test with transformer_weights
    transformer_weights = {'trans1': .1, 'trans2': 10}
    both = ColumnTransformer([('trans1', Trans(), [0]),
                              ('trans2', Trans(), [1])],
                             transformer_weights=transformer_weights)
    res = np.vstack([transformer_weights['trans1'] * X_res_first1D,
                     transformer_weights['trans2'] * X_res_second1D]).T
    assert_array_equal(both.fit_transform(X_array), res)
    assert_array_equal(both.fit(X_array).transform(X_array), res)

    both = ColumnTransformer([('trans', Trans(), [0, 1])],
                             transformer_weights={'trans': .1})
    assert_array_equal(both.fit_transform(X_array), 0.1 * X_res_both)
    assert_array_equal(both.fit(X_array).transform(X_array), 0.1 * X_res_both)


def test_column_transformer_dataframe():
    try:
        import pandas as pd
    except ImportError:
        raise SkipTest("pandas is not installed: skipping ColumnTransformer "
                       "tests for DataFrames.")

    X_array = np.array([[0, 1, 2], [2, 4, 6]]).T
    X_df = pd.DataFrame(X_array, columns=['first', 'second'])

    X_res_first1D = np.array([0, 1, 2])
    X_res_first2D = X_res_first1D.reshape(-1, 1)
    X_res_both = X_array

    cases = [
        # String keys: label based

        # scalar
        ('first', X_res_first1D),
        # list
        (['first'], X_res_first2D),
        (['first', 'second'], X_res_both),
        # slice
        (slice('first', 'second'), X_res_both),

        # int keys: positional

        # scalar
        (0, X_res_first1D),
        # list
        ([0], X_res_first2D),
        ([0, 1], X_res_both),
        (np.array([0, 1]), X_res_both),
        # slice
        (slice(0, 1), X_res_first2D),
        (slice(0, 2), X_res_both),

        # boolean mask
        (np.array([True, False]), X_res_first2D),
        (pd.Series([True, False], index=['first', 'second']), X_res_first2D),
    ]

    for selection, res in cases:
        ct = ColumnTransformer([('trans', Trans(), selection)])
        assert_array_equal(ct.fit_transform(X_df), res)
        assert_array_equal(ct.fit(X_df).transform(X_df), res)

    ct = ColumnTransformer([('trans1', Trans(), ['first']),
                            ('trans2', Trans(), ['second'])])
    assert_array_equal(ct.fit_transform(X_df), X_res_both)
    assert_array_equal(ct.fit(X_df).transform(X_df), X_res_both)

    ct = ColumnTransformer([('trans1', Trans(), [0]),
                            ('trans2', Trans(), [1])])
    assert_array_equal(ct.fit_transform(X_df), X_res_both)
    assert_array_equal(ct.fit(X_df).transform(X_df), X_res_both)

    # test with transformer_weights
    transformer_weights = {'trans1': .1, 'trans2': 10}
    both = ColumnTransformer([('trans1', Trans(), ['first']),
                              ('trans2', Trans(), ['second'])],
                             transformer_weights=transformer_weights)
    res = np.vstack([transformer_weights['trans1'] * X_df['first'],
                     transformer_weights['trans2'] * X_df['second']]).T
    assert_array_equal(both.fit_transform(X_df), res)
    assert_array_equal(both.fit(X_df).transform(X_df), res)

    # test multiple columns
    both = ColumnTransformer([('trans', Trans(), ['first', 'second'])],
                             transformer_weights={'trans': .1})
    assert_array_equal(both.fit_transform(X_df), 0.1 * X_res_both)
    assert_array_equal(both.fit(X_df).transform(X_df), 0.1 * X_res_both)

    both = ColumnTransformer([('trans', Trans(), [0, 1])],
                             transformer_weights={'trans': .1})
    assert_array_equal(both.fit_transform(X_df), 0.1 * X_res_both)
    assert_array_equal(both.fit(X_df).transform(X_df), 0.1 * X_res_both)

    # ensure pandas object is passes through

    class TransAssert(BaseEstimator):

        def fit(self, X, y=None):
            return self

        def transform(self, X, y=None):
            assert_true(isinstance(X, (pd.DataFrame, pd.Series)))

    ct = ColumnTransformer([('trans', TransAssert(), 'first')])
    ct.fit_transform(X_df)
    ct = ColumnTransformer([('trans', TransAssert(), ['first', 'second'])])
    ct.fit_transform(X_df)

    # integer column spec + integer column names -> still use positional
    X_df2 = X_df.copy()
    X_df2.columns = [1, 0]
    ct = ColumnTransformer([('trans', Trans(), 0)])
    assert_array_equal(ct.fit_transform(X_df), X_res_first1D)
    assert_array_equal(ct.fit(X_df).transform(X_df), X_res_first1D)


def test_column_transformer_sparse_array():
    X_sparse = sparse.eye(3, 2).tocsr()

    # no distinction between 1D and 2D
    X_res_first = X_sparse[:, 0]
    X_res_both = X_sparse

    for col in [0, [0], slice(0, 1)]:
        ct = ColumnTransformer([('trans', Trans(), col)])
        assert_true(sparse.issparse(ct.fit_transform(X_sparse)))
        assert_allclose_dense_sparse(ct.fit_transform(X_sparse), X_res_first)
        assert_allclose_dense_sparse(ct.fit(X_sparse).transform(X_sparse),
                                     X_res_first)

    for col in [[0, 1], slice(0, 2)]:
        ct = ColumnTransformer([('trans', Trans(), col)])
        assert_true(sparse.issparse(ct.fit_transform(X_sparse)))
        assert_allclose_dense_sparse(ct.fit_transform(X_sparse), X_res_both)
        assert_allclose_dense_sparse(ct.fit(X_sparse).transform(X_sparse),
                                     X_res_both)


def test_column_transformer_sparse_stacking():
    X_array = np.array([[0, 1, 2], [2, 4, 6]]).T
    col_trans = ColumnTransformer([('trans1', Trans(), [0]),
                                   ('trans2', SparseMatrixTrans(), 1)])
    col_trans.fit(X_array)
    X_trans = col_trans.transform(X_array)
    assert_true(sparse.issparse(X_trans))
    assert_equal(X_trans.shape, (X_trans.shape[0], X_trans.shape[0] + 1))
    assert_array_equal(X_trans.toarray()[:, 1:], np.eye(X_trans.shape[0]))


def test_column_transformer_error_msg_1D():
    X_array = np.array([[0., 1., 2.], [2., 4., 6.]]).T

    col_trans = ColumnTransformer([('trans', StandardScaler(), 0)])
    assert_raise_message(ValueError, "1D data passed to a transformer",
                         col_trans.fit, X_array)
    assert_raise_message(ValueError, "1D data passed to a transformer",
                         col_trans.fit_transform, X_array)

    class TransRaise(BaseEstimator):

        def fit(self, X, y=None):
            raise ValueError("specific message")

        def transform(self, X, y=None):
            raise ValueError("specific message")

    col_trans = ColumnTransformer([('trans', TransRaise(), 0)])
    for func in [col_trans.fit, col_trans.transform, col_trans.fit_transform]:
        assert_raise_message(ValueError, "specific message", func, X_array)


def test_column_transformer_invalid_columns():
    X_array = np.array([[0, 1, 2], [2, 4, 6]]).T

    # general invalid
    for col in [1.5, ['string', 1], slice(1, 's')]:
        ct = ColumnTransformer([('trans', Trans(), col)])
        assert_raise_message(ValueError, "No valid specification",
                             ct.fit, X_array)

    # invalid for arrays
    for col in ['string', ['string', 'other'], slice('a', 'b')]:
        ct = ColumnTransformer([('trans', Trans(), col)])
        assert_raise_message(ValueError, "Specifying the columns",
                             ct.fit, X_array)


def test_make_column_transformer():
    scaler = StandardScaler()
    norm = Normalizer()
    ct = make_column_transformer({scaler: 'first', norm: ['second']})
    names, transformers, columns = zip(*ct.transformer_list)
    assert_equal(names, ("normalizer", "standardscaler"))
    assert_equal(transformers, (norm, scaler))
    assert_equal(columns, (['second'], 'first'))


def test_make_column_transformer_kwargs():
    scaler = StandardScaler()
    norm = Normalizer()
    ct = make_column_transformer({scaler: 'first', norm: ['second']}, n_jobs=3)
    assert_equal(
        ct.transformer_list,
        make_column_transformer({scaler: 'first',
                                 norm: ['second']}).transformer_list)
    assert_equal(ct.n_jobs, 3)
    # invalid keyword parameters should raise an error message
    assert_raise_message(
        TypeError,
        'Unknown keyword arguments: "transformer_weights"',
        make_column_transformer, {scaler: 'first', norm: ['second']},
        transformer_weights={'pca': 10, 'Transf': 1}
    )


def test_column_transformer_get_set_params():
    ct = ColumnTransformer([('trans1', StandardScaler(), [0]),
                            ('trans2', StandardScaler(), [1])])

    exp = {'n_jobs': 1,
           'trans1': ct.transformer_list[0][1],
           'trans1__copy': True,
           'trans1__with_mean': True,
           'trans1__with_std': True,
           'trans2': ct.transformer_list[1][1],
           'trans2__copy': True,
           'trans2__with_mean': True,
           'trans2__with_std': True,
           'transformer_list': ct.transformer_list,
           'transformer_weights': None}

    assert_dict_equal(ct.get_params(), exp)

    ct.set_params(trans1__with_mean=False)
    assert_false(ct.get_params()['trans1__with_mean'])

    ct.set_params(trans1=None)
    exp = {'n_jobs': 1,
           'trans1': None,
           'trans2': ct.transformer_list[1][1],
           'trans2__copy': True,
           'trans2__with_mean': True,
           'trans2__with_std': True,
           'transformer_list': ct.transformer_list,
           'transformer_weights': None}

    assert_dict_equal(ct.get_params(), exp)
