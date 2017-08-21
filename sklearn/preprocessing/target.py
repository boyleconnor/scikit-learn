# Authors: Andreas Mueller <andreas.mueller@columbia.edu>
#          Guillaume Lemaitre <guillaume.lemaitre@inria.fr>
# License: BSD 3 clause

import numpy as np

from ..base import BaseEstimator, RegressorMixin, is_regressor, clone
from ..utils.validation import check_is_fitted
from ..utils import check_X_y, safe_indexing
from ._function_transformer import FunctionTransformer

__all__ = ['TransformTargetRegressor']


class TransformTargetRegressor(BaseEstimator, RegressorMixin):
    """Meta-estimator to regress on a transformed target.

    Useful for applying a non-linear transformation in regression
    problems. This transformation can be given as a Transformer such as the
    QuantileTransformer or as a function and its inverse such as ``np.log`` and
    ``np.exp``.

    The computation during ``fit`` is::

        regressor.fit(X, func(y))

    or::

        regressor.fit(X, transformer.transform(y))

    The computation during ``predict`` is::

        inverse_func(regressor.predict(X))

    or::

        transformer.inverse_transform(regressor.predict(X))

    Read more in the :ref:`User Guide <preprocessing_targets>`.

    Parameters
    ----------
    regressor : object, (default=LinearRegression())
        Regressor object such as derived from ``RegressorMixin``. This
        regressor will be cloned during fitting.

    transformer : object, (default=None)
        Estimator object such as derived from ``TransformerMixin``. Cannot be
        set at the same time as ``func`` and ``inverse_func``. If
        ``transformer`` is ``None`` as well as ``func`` and ``inverse_func``,
        the transformer will be an identity transformer. Note that the
        transformer will be cloned during fitting.

    func : function, optional

        Function to apply to ``y`` before passing to ``fit``. Cannot be set at
        the same time as ``transformer``. The function needs to return a
        2-dimensional array. If ``func`` is ``None``, the function used will be
        the identity function.

    inverse_func : function, optional
        Function to apply to the prediction of the regressor. Cannot be set at
        the same time as ``transformer`` as well. The function needs to return
        a 2-dimensional array. If ``inverse_func is ``None``, the function used
        will be the identity function. The inverse function is used to return
        to the same space of the original training labels during prediction.

    check_inverse : bool, (default=True)
        Whether to check that ``transform`` followed by ``inverse_transform``
        or ``func`` followed by ``inverse_func`` leads to the original targets.

    Attributes
    ----------
    regressor_ : object
        Fitted regressor.

    transformer_ : object
        Transformer used in ``fit`` and ``predict``.

    Examples
    --------
    >>> import numpy as np
    >>> from sklearn.linear_model import LinearRegression
    >>> from sklearn.preprocessing import TransformTargetRegressor
    >>> tt = TransformTargetRegressor(regressor=LinearRegression(),
    ...                               func=np.log, inverse_func=np.exp)
    >>> X = np.arange(4).reshape(-1, 1)
    >>> y = np.exp(2 * X).ravel()
    >>> tt.fit(X, y)
    ... # doctest: +NORMALIZE_WHITESPACE
    TransformTargetRegressor(check_inverse=True,
                             func=<ufunc 'log'>,
                             inverse_func=<ufunc 'exp'>,
                             random_state=None,
                             regressor=LinearRegression(copy_X=True,
                                                        fit_intercept=True,
                                                        n_jobs=1,
                                                        normalize=False),
                             transformer=None)
    >>> tt.score(X, y)
    1.0
    >>> tt.regressor_.coef_
    array([ 2.])

    Notes
    -----
    Internally, the target ``y`` is always converted into a 2-dimensional array
    to be used by scikit-learn transformers. At the time of prediction, the
    output will be reshape to a have the same number of dimension than ``y``.

    See :ref:`examples/preprocessing/plot_transform_target.py
    <sphx_glr_auto_examples_preprocessing_plot_transform_target.py> `.

    """
    def __init__(self, regressor=None, transformer=None,
                 func=None, inverse_func=None, check_inverse=True,
                 random_state=None):
        self.regressor = regressor
        self.transformer = transformer
        self.func = func
        self.inverse_func = inverse_func
        self.check_inverse = check_inverse
        self.random_state = random_state

    def _fit_transformer(self, y):
        if (self.transformer is not None and
                (self.func is not None or self.inverse_func is not None)):
            raise ValueError("'transformer' and functions 'func'/"
                             "'inverse_func' cannot both be set.")
        elif self.transformer is not None:
            self.transformer_ = clone(self.transformer)
        else:
            self.transformer_ = FunctionTransformer(
                func=self.func, inverse_func=self.inverse_func, validate=True)
        # XXX: sample_weight is not currently passed to the
        # transformer. However, if transformer starts using sample_weight, the
        # code should be modified accordingly. At the time to consider the
        # sample_prop feature, it is also a good use case to be considered.
        self.transformer_.fit(y)
        if self.check_inverse:
            idx_selected = slice(None, None, max(1, y.shape[0] // 10))
            if not np.allclose(
                    safe_indexing(y, idx_selected),
                    self.transformer_.inverse_transform(
                        self.transformer_.transform(
                            safe_indexing(y, idx_selected)))):
                raise ValueError("The provided functions or transformer are"
                                 " not strictly inverse of each other. If"
                                 " you are sure you want to proceed regardless"
                                 ", set 'check_inverse=False'")

    def fit(self, X, y, sample_weight=None):
        """Fit the model according to the given training data.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Training vector, where n_samples is the number of samples and
            n_features is the number of features.

        y : array-like, shape (n_samples,)
            Target values.

        sample_weight : array-like, shape (n_samples,) optional
            Array of weights that are assigned to individual samples.
            If not provided, then each sample is given unit weight.

        Returns
        -------
        self : object
            Returns self.
        """
        X, y = check_X_y(X, y, multi_output=True, y_numeric=True)

        # transformers are designed to modify X which is a 2d dimensional, we
        # need to modify y accordingly.
        if y.ndim == 1:
            y_2d = y.reshape(-1, 1)
        else:
            y_2d = y
        self._fit_transformer(y_2d)

        if self.regressor is None:
            from ..linear_model import LinearRegression
            self.regressor_ = LinearRegression()
        else:
            if not is_regressor(self.regressor):
                raise TypeError("The regressor {} is of type {}. Provide"
                                " a regressor instead.".format(
                                    self.regressor.__class__.__name__,
                                    self.regressor._estimator_type))
            self.regressor_ = clone(self.regressor)

        # transform y and convert back to 1d array if needed
        y_trans = self.transformer_.fit_transform(y_2d)
        # FIXME: a FunctionTransformer can return a 1D array even when validate
        # is set to True. Therefore, we need to check the number of dimension
        # first.
        if y_trans.ndim == 2 and y_trans.shape[1] == 1:
            y_trans = y_trans.squeeze(axis=1)
        if sample_weight is None:
            self.regressor_.fit(X, y_trans)
        else:
            self.regressor_.fit(X, y_trans, sample_weight=sample_weight)

        return self

    def predict(self, X):
        """Predict using the base regressor, applying inverse.

        The regressor is used to predict and the ``inverse_func`` or
        ``inverse_transform`` is applied before returning the prediction.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = (n_samples, n_features)
            Samples.

        Returns
        -------
        y_hat : array, shape = (n_samples,)
            Predicted values.

        """
        check_is_fitted(self, "regressor_")
        pred = self.regressor_.predict(X)
        if pred.ndim == 1:
            pred_trans = self.transformer_.inverse_transform(
                pred.reshape(-1, 1))
        else:
            pred_trans = self.transformer_.inverse_transform(pred)
        if pred_trans.ndim == 2 and pred_trans.shape[1] == 1:
            pred_trans = pred_trans.squeeze(axis=1)

        return pred_trans
