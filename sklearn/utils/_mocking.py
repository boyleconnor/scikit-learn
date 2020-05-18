import numpy as np

from ..base import BaseEstimator, ClassifierMixin
from .validation import _num_samples, check_array


class ArraySlicingWrapper:
    """
    Parameters
    ----------
    array
    """
    def __init__(self, array):
        self.array = array

    def __getitem__(self, aslice):
        return MockDataFrame(self.array[aslice])


class MockDataFrame:
    """
    Parameters
    ----------
    array
    """
    # have shape and length but don't support indexing.
    def __init__(self, array):
        self.array = array
        self.values = array
        self.shape = array.shape
        self.ndim = array.ndim
        # ugly hack to make iloc work.
        self.iloc = ArraySlicingWrapper(array)

    def __len__(self):
        return len(self.array)

    def __array__(self, dtype=None):
        # Pandas data frames also are array-like: we want to make sure that
        # input validation in cross-validation does not try to call that
        # method.
        return self.array

    def __eq__(self, other):
        return MockDataFrame(self.array == other.array)

    def __ne__(self, other):
        return not self == other


class CheckingClassifier(ClassifierMixin, BaseEstimator):
    """Dummy classifier to test pipelining and meta-estimators.

    Checks some property of X and y in fit / predict.
    This allows testing whether pipelines / cross-validation or metaestimators
    changed the input.

    Parameters
    ----------
    check_y
    check_y_params
    check_X
    check_X_params
    foo_param
    expected_fit_params

    Attributes
    ----------
    classes_
    """
    def __init__(self, *, check_y=None, check_y_params=None,
                 check_X=None, check_X_params=None, foo_param=0,
                 expected_fit_params=None):
        self.check_y = check_y
        self.check_y_params = check_y_params
        self.check_X = check_X
        self.check_X_params = check_X_params
        self.foo_param = foo_param
        self.expected_fit_params = expected_fit_params

    def fit(self, X, y, **fit_params):
        """
        Fit classifier

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Training vector, where n_samples is the number of samples and
            n_features is the number of features.

        y : array-like of shape (n_samples, n_output) or (n_samples,), optional
            Target relative to X for classification or regression;
            None for unsupervised learning.

        **fit_params : dict of string -> object
            Parameters passed to the ``fit`` method of the estimator
        """
        assert _num_samples(X) == _num_samples(y)
        if self.check_X is not None:
            params = {} if self.check_X_params is None else self.check_X_params
            assert self.check_X(X, **params)
        if self.check_y is not None:
            params = {} if self.check_y_params is None else self.check_y_params
            assert self.check_y(y)
        self.n_features_in_ = np.shape(X)[1]
        self.classes_ = np.unique(check_array(y, ensure_2d=False,
                                              allow_nd=True))
        if self.expected_fit_params:
            missing = set(self.expected_fit_params) - set(fit_params)
            assert len(missing) == 0, (
                f'Expected fit parameter(s) {list(missing)} not seen.'
            )
            for key, value in fit_params.items():
                assert _num_samples(value) == _num_samples(X), (
                    f'Fit parameter {key} has length {_num_samples(value)}; '
                    f'expected {_num_samples(X)}.'
                )

        return self

    def predict(self, T):
        """
        Parameters
        ----------
        T : indexable, length n_samples
        """
        if self.check_X is not None:
            params = {} if self.check_X_params is None else self.check_X_params
            assert self.check_X(T, **params)
        return self.classes_[np.zeros(_num_samples(T), dtype=np.int)]

    def predict_proba(self, T):
        """Predict probabilities for each class.

        Parameters
        ----------
        T : array-like of shape (n_samples, n_features)
            The input data.

        Returns
        -------
        proba : ndarray of shape (n_samples, n_classes)
            The probabilities for each sample and class.
        """
        proba = np.zeros((_num_samples(T), len(self.classes_)))
        proba[:, 0] = 1
        return proba

    def decision_function(self, T):
        """Confidence score.

        Parameters
        ----------
        T : array-like of shape (n_samples, n_features)
            The input data.

        Returns
        -------
        decision : ndarray of shape (n_samples,) if n_classes == 2\
                else (n_samples, n_classes)
            Confidence score.
        """
        if len(self.classes_) == 2:
            return np.zeros(_num_samples(T))
        else:
            return self.predict_proba(T)

    def score(self, X=None, Y=None):
        """
        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Input data, where n_samples is the number of samples and
            n_features is the number of features.

        Y : array-like of shape (n_samples, n_output) or (n_samples,), optional
            Target relative to X for classification or regression;
            None for unsupervised learning.
        """
        if self.foo_param > 1:
            score = 1.
        else:
            score = 0.
        return score

    def _more_tags(self):
        return {'_skip_test': True, 'X_types': ['1dlabel']}


class NoSampleWeightWrapper(BaseEstimator):
    """Wrap estimator which will not expose `sample_weight`.

    Parameters
    ----------
    est : estimator, default=None
        The estimator to wrap.
    """
    def __init__(self, est=None):
        self.est = est

    def fit(self, X, y):
        return self.est.fit(X, y)

    def predict(self, X):
        return self.est.predict(X)

    def predict_proba(self, X):
        return self.est.predict_proba(X)

    def _more_tags(self):
        return {'_skip_test': True}
