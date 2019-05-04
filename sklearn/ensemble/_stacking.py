"""Stacking classifier and regressor."""

# Authors: Guillaume Lemaitre <g.lemaitre58@gmail.com>
# License: BSD 3 clause

from abc import ABCMeta, abstractmethod
from copy import deepcopy

import numpy as np

from ..base import clone
from ..base import ClassifierMixin, RegressorMixin, TransformerMixin
from ..base import is_classifier, is_regressor
from ..base import MetaEstimatorMixin

from .base import _parallel_fit_estimator

from sklearn.linear_model import LogisticRegression
from sklearn.linear_model import LinearRegression

from ..model_selection import cross_val_predict
from ..model_selection import check_cv

from ..utils import check_random_state
from ..utils._joblib import Parallel, delayed
from ..utils.metaestimators import _BaseComposition
from ..utils.metaestimators import if_delegate_has_method
from ..utils.validation import check_is_fitted


class _BaseStacking(_BaseComposition, MetaEstimatorMixin, TransformerMixin,
                    metaclass=ABCMeta):
    """Base class for stacking method.

    Warning: This class should not be used directly. Use derived classes
    instead.
    """
    _required_parameters = ['estimators']

    @abstractmethod
    def __init__(self, estimators, final_estimator=None, cv=None,
                 predict_method='auto', passthrough=False, n_jobs=1,
                 random_state=None, verbose=0):
        self.estimators = estimators
        self.final_estimator = final_estimator
        self.cv = cv
        self.predict_method = predict_method
        self.passthrough = passthrough
        self.n_jobs = n_jobs
        self.random_state = random_state
        self.verbose = verbose

    def _validate_final_estimator(self, default=None):
        if self.final_estimator is not None:
            self.final_estimator_ = clone(self.final_estimator)
        else:
            self.final_estimator_ = clone(default)

    @property
    def named_estimators(self):
        return dict(self.estimators)

    @staticmethod
    def _method_name(name, estimator, method):
        if estimator in (None, 'drop'):
            return None
        if method == 'auto':
            if getattr(estimator, 'predict_proba', None):
                return 'predict_proba'
            elif getattr(estimator, 'decision_function', None):
                return 'decision_function'
            else:
                return 'predict'
        else:
            if not hasattr(estimator, method):
                raise ValueError('Underlying estimator {} does not implement '
                                 'the method {}.'.format(name, method))
            return method

    def _concatenate_predictions(self, X, y_pred):
        if self.passthrough:
            return np.concatenate([X] + [pred.reshape(-1, 1) if pred.ndim == 1
                                         else pred for pred in y_pred], axis=1)
        else:
            return np.concatenate([pred.reshape(-1, 1) if pred.ndim == 1
                                   else pred for pred in y_pred], axis=1)

    def set_params(self, **params):
        """ Setting the parameters for the stacking estimator.

        Valid parameter keys can be listed with get_params().

        Parameters
        ----------
        params : keyword arguments
            Specific parameters using e.g. set_params(parameter_name=new_value)
            In addition, to setting the parameters of the ``VotingClassifier``,
            the individual classifiers of the ``VotingClassifier`` can also be
            set or replaced by setting them to None.

        Examples
        --------
        # In this example, the RandomForestClassifier is removed
        clf1 = LogisticRegression()
        clf2 = RandomForestClassifier()
        eclf = StackingClassifier(estimators=[('lr', clf1), ('rf', clf2)]
        eclf.set_params(rf=None)

        """
        super()._set_params('estimators', **params)
        return self

    def get_params(self, deep=True):
        """ Get the parameters of the stacking estimator.

        Parameters
        ----------
        deep: bool
            Setting it to True gets the various classifiers and the parameters
            of the classifiers as well.
        """
        return super()._get_params('estimators', deep=deep)

    def fit(self, X, y, sample_weight=None):
        """ Fit the estimators.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Training vectors, where n_samples is the number of samples and
            n_features is the number of features.

        y : array-like, shape (n_samples,)
            Target values.

        sample_weight : array-like, shape (n_samples,) or None
            Sample weights. If None, then samples are equally weighted.
            Note that this is supported only if all underlying estimators
            support sample weights.

        Returns
        -------
        self : object
        """

        self._validate_meta_estimator()

        if self.estimators is None or len(self.estimators) == 0:
            raise AttributeError(
                "Invalid 'estimators' attribute, 'estimators' should be a list"
                " of (string, estimator) tuples."
            )

        if not isinstance(self.passthrough, bool):
            raise AttributeError(
                "Invalid 'passthrough' attribute, 'passthrough' should be a "
                "boolean. Got {!r} instead.".format(self.passthrough)
            )

        names, estimators_ = zip(*self.estimators)
        self._validate_names(names)

        n_isnone = np.sum(
            [est in (None, 'drop') for est in estimators_]
        )
        if n_isnone == len(self.estimators):
            raise ValueError(
                "All estimators are None or 'drop'. At least one is required "
                "to be an estimator."
            )

        if isinstance(self.predict_method, str):
            if self.predict_method != 'auto':
                raise AttributeError(
                    "When 'predict_method' is a string, it should be 'auto'. "
                    " Got {} instead.".format(self.predict_method)
                )
            predict_method = [self.predict_method] * len(estimators_)
        else:
            if len(self.estimators) != len(self.predict_method):
                raise AttributeError(
                    "When 'predict_method' is a list, it should be the same "
                    "length as the list of estimators. Provided {} methods "
                    "for {} estimators."
                    .format(len(self.predict_method), len(self.estimators))
                )
            predict_method = self.predict_method

        self.predict_method_ = [
            self._method_name(name, est, meth)
            for name, est, meth in zip(names, estimators_, predict_method)
        ]

        # Fit the base estimators on the whole training data. Those
        # base estimators will be used in transform, predict, and
        # predict_proba. They are exposed publicly.
        self.estimators_ = Parallel(n_jobs=self.n_jobs)(
            delayed(_parallel_fit_estimator)(clone(est), X, y, sample_weight)
            for est in estimators_ if est not in (None, 'drop')
        )

        # To train the meta-classifier using the most data as possible, we use
        # a cross-validation to obtain the output of the stacked estimators.

        # To ensure that the data provided to each estimator are the same, we
        # need to set the random state of the cv if there is one and we need to
        # take a copy.
        random_state = check_random_state(self.random_state)
        cv = check_cv(self.cv)
        if hasattr(cv, 'random_state'):
            cv.random_state = random_state

        X_meta = Parallel(n_jobs=self.n_jobs)(
            delayed(cross_val_predict)(clone(est), X, y, cv=deepcopy(cv),
                                       method=meth, n_jobs=self.n_jobs,
                                       verbose=self.verbose)
            for est, meth in zip(estimators_, self.predict_method_)
            if est not in (None, 'drop')
        )

        # Only not None or not 'drop' estimators will be used in transform.
        # Remove the None from the method as well.
        self.predict_method_ = [meth for meth in self.predict_method_
                                if meth is not None]

        X_meta = self._concatenate_predictions(X, X_meta)
        self.final_estimator_.fit(X_meta, y)

        return self

    def transform(self, X):
        """Return class labels or probabilities for X for each estimator.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Training vectors, where n_samples is the number of samples and
            n_features is the number of features.

        Returns
        -------
        y_preds : ndarray, shape (n_samples, n_estimators)
            Prediction outputs for each estimator.
        """
        check_is_fitted(self, 'estimators_')
        return self._concatenate_predictions(
            X, [getattr(est, meth)(X)
                for est, meth in zip(self.estimators_, self.predict_method_)
                if est not in (None, 'drop')]
        )

    @if_delegate_has_method(delegate='final_estimator_')
    def predict(self, X, **predict_params):
        """Predict target for X.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Training vectors, where n_samples is the number of samples and
            n_features is the number of features.

        **predict_params : dict of string -> object
            Parameters to the ``predict`` called by the ``final_estimator``.
            Note that while this may be
            used to return uncertainties from some models with ``return_std``
            or ``return_cov``.

        Returns
        -------
        y_pred : ndarray, shape (n_samples,) or (n_samples, n_output)
            Predicted targets.
        """

        check_is_fitted(self, ['estimators_', 'final_estimator_'])
        return self.final_estimator_.predict(self.transform(X))


class StackingClassifier(_BaseStacking, ClassifierMixin):
    """Stacked of estimators using a final classifier.

    Stacked generalization consists in stacking the output of individual
    estimator and use a classifier to compute the final prediction. Stacking
    allows to combine the strength of each individual estimator. It should be
    noted that the final estimator is trained through cross-validation.

    .. versionadded:: 0.20

    Read more in the :ref:`User Guide <stacking>`.

    Parameters
    ----------
    estimators : list of (string, estimator) tuples
        Base estimators which will be stacked together. An estimator can be set
        to None or 'drop' using ``set_params``.

    final_estimator : estimator object
        A classifier which will be used to combine the base estimators.

    cv : int, cross-validation generator or an iterable, optional
        Determines the cross-validation splitting strategy. Possible inputs for
        cv are:

        * None, to use the default 3-fold cross validation,
        * integer, to specify the number of folds in a (Stratified) KFold,
        * An object to be used as a cross-validation generator,
        * An iterable yielding train, test splits.

        For integer/None inputs, if the estimator is a classifier and y is
        either binary or multiclass, StratifiedKFold is used. In all other
        cases, KFold is used.

        Refer :ref:`User Guide <cross_validation>` for the various
        cross-validation strategies that can be used here.

    predict_method : list of string or 'auto', optional
        Methods called for each base estimator. It can be:

        * if a list of string in which each string is associated to the
          ``estimators``,
        * if ``auto``, it will try to invoke, for each estimator,
        ``predict_proba``, ``decision_function`` or ``predict`` in that order.

    passthrough : bool, optional
        Whether or not to concatenate the original data ``X`` with the output
        of ``estimators`` to feed the ``final_estimator``. The default is
        False.

    n_jobs : int, optional (default=1)
        The number of jobs to ``fit`` the ``estimators`` in parallel. If
        -1, then the number of jobs is set to the number of cores.

    random_state : int, RandomState instance or None, optional (default=None)
        If int, random_state is the seed used by the random number generator;
        If RandomState instance, random_state is the random number generator;
        If None, the random number generator is the RandomState instance used
        by `np.random`. Used to set the ``cv``.

    Attributes
    ----------
    estimators_ : list of estimator object
        The base estimators fitted.

    final_estimator_ : estimator object
        The classifier to stacked the base estimators fitted.

    predict_method_ : list of string
        The method used by each base estimator.

    References
    ----------
    .. [1] Wolpert, David H. "Stacked generalization." Neural networks 5.2
       (1992): 241-259.

    Examples
    --------
    >>> from sklearn.datasets import load_iris
    >>> X, y = load_iris(return_X_y=True)
    >>> from sklearn.linear_model import LogisticRegression
    >>> from sklearn.svm import LinearSVC
    >>> from sklearn.ensemble import RandomForestClassifier
    >>> from sklearn.ensemble import StackingClassifier
    >>> estimators = [
    ...     ('lr', LogisticRegression(solver='lbfgs', multi_class='auto',
    ...                               tol=1e-1)),
    ...     ('svr', LinearSVC(tol=1e-1, random_state=42))
    ... ]
    >>> clf = StackingClassifier(
    ...     estimators=estimators,
    ...     final_estimator=RandomForestClassifier(n_estimators=10,
    ...                                            random_state=42),
    ...     cv=5,
    ... )
    >>> from sklearn.model_selection import train_test_split
    >>> X_train, X_test, y_train, y_test = train_test_split(
    ... X, y, stratify=y, random_state=42
    ... )
    >>> clf.fit(X_train, y_train).score(X_test, y_test) # doctest: +ELLIPSIS
    0...

    """
    def __init__(self, estimators, final_estimator=None, cv=None,
                 predict_method='auto', passthrough=False, n_jobs=1,
                 random_state=None, verbose=0):
        super().__init__(
            estimators=estimators,
            final_estimator=final_estimator,
            cv=cv,
            predict_method=predict_method,
            passthrough=passthrough,
            n_jobs=n_jobs,
            random_state=random_state,
            verbose=verbose
        )

    def _validate_meta_estimator(self):
        # FIXME: remove the parameters in 0.23
        super()._validate_final_estimator(
            default=LogisticRegression(
                solver='lbfgs',
                max_iter=1000,
                multi_class='auto',
                random_state=self.random_state
            )
        )
        if not is_classifier(self.final_estimator_):
            raise AttributeError(
                "'final_estimator' attribute should be a classifier. Got {!r}"
                .format(self.final_estimator_)
            )

    @if_delegate_has_method(delegate='final_estimator_')
    def predict_proba(self, X):
        """Predict class probabilities for X.

        Parameters
        ----------
        X : {array-like, sparse matrix} of shape (n_samples, n_features)
            Training vectors, where n_samples is the number of samples and
            n_features is the number of features.

        Returns
        -------
        probabilities : ndarray, shape (n_samples, n_classes) or \
list of arrays n_output
            The class probabilities of the input samples.
        """
        check_is_fitted(self, ['estimators_', 'final_estimator_'])
        return self.final_estimator_.predict_proba(self.transform(X))


class StackingRegressor(_BaseStacking, RegressorMixin):
    """Stacked of estimators using a final regressor.

    Stacked generalization consists in stacking the output of individual
    estimator and use a regressor to compute the final prediction. Stacking
    allows to combine the strength of each individual estimator. It should be
    noted that the final estimator is trained through cross-validation.

    .. versionadded:: 0.20

    Read more in the :ref:`User Guide <stacking>`.

    Parameters
    ----------
    estimators : list of (string, estimator) tuples
        Base estimators which will be stacked together. An estimator can be set
        to None or 'drop using ``set_params``.

    final_estimator : estimator object
        A regressor which will be used to combine the base estimators.

    cv : int, cross-validation generator or an iterable, optional
        Determines the cross-validation splitting strategy. Possible inputs for
        cv are:

        * None, to use the default 3-fold cross validation,
        * integer, to specify the number of folds in a (Stratified) KFold,
        * An object to be used as a cross-validation generator,
        * An iterable yielding train, test splits.

        For integer/None inputs, if the estimator is a classifier and y is
        either binary or multiclass, StratifiedKFold is used. In all other
        cases, KFold is used.

        Refer :ref:`User Guide <cross_validation>` for the various
        cross-validation strategies that can be used here.

    predict_method : list of string or 'auto', optional
        Methods called for each base estimator. It can be:

        * if a list of string in which each string is associated to the
          ``estimators``,
        * if ``auto``, it will try to invoke, for each estimator,
        ``predict_proba``, ``decision_function`` or ``predict`` in that order.

    passthrough : bool, optional
        Whether or not to concatenate the original data ``X`` with the output
        of ``estimators`` to feed the ``final_estimator``. The default is
        False.

    n_jobs : int, optional (default=1)
        The number of jobs to ``fit`` the ``estimators`` in parallel. If
        -1, then the number of jobs is set to the number of cores.

    random_state : int, RandomState instance or None, optional (default=None)
        If int, random_state is the seed used by the random number generator;
        If RandomState instance, random_state is the random number generator;
        If None, the random number generator is the RandomState instance used
        by `np.random`. Used to set the ``cv``.

    Attributes
    ----------
    estimators_ : list of estimator object
        The base estimators fitted.

    final_estimator_ : estimator object
        The regressor to stacked the base estimators fitted.

    predict_method_ : list of string
        The method used by each base estimator.

    References
    ----------
    .. [1] Wolpert, David H. "Stacked generalization." Neural networks 5.2
       (1992): 241-259.

    Examples
    --------
    >>> from sklearn.datasets import load_diabetes
    >>> X, y = load_diabetes(return_X_y=True)
    >>> from sklearn.linear_model import LinearRegression
    >>> from sklearn.svm import LinearSVR
    >>> from sklearn.ensemble import RandomForestRegressor
    >>> from sklearn.ensemble import StackingRegressor
    >>> estimators = [
    ...     ('lr', LinearRegression()),
    ...     ('svr', LinearSVR(tol=1e-1, random_state=42))
    ... ]
    >>> reg = StackingRegressor(
    ...     estimators=estimators,
    ...     final_estimator=RandomForestRegressor(n_estimators=10,
    ...                                           random_state=42),
    ...     cv=5
    ... )
    >>> from sklearn.model_selection import train_test_split
    >>> X_train, X_test, y_train, y_test = train_test_split(
    ... X, y, random_state=42
    ... )
    >>> reg.fit(X_train, y_train).score(X_test, y_test) # doctest: +ELLIPSIS
    0...

    """
    def __init__(self, estimators, final_estimator=None, cv=None,
                 predict_method='auto', passthrough=False, n_jobs=1,
                 random_state=None, verbose=0):
        super().__init__(
            estimators=estimators,
            final_estimator=final_estimator,
            cv=cv,
            predict_method=predict_method,
            passthrough=passthrough,
            n_jobs=n_jobs,
            random_state=random_state,
            verbose=verbose
        )

    def _validate_meta_estimator(self):
        super()._validate_final_estimator(
            default=LinearRegression()
        )
        if not is_regressor(self.final_estimator_):
            raise AttributeError(
                "'final_estimator' attribute should be a regressor. Got {!r}"
                .format(self.final_estimator_)
            )
