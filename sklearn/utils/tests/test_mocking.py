import numpy as np
import pytest
from scipy import sparse

from numpy.testing import assert_array_equal
from numpy.testing import assert_allclose

from sklearn.datasets import load_iris
from sklearn.utils import check_array
from sklearn.utils import _safe_indexing
from sklearn.utils._testing import _convert_container

from sklearn.utils._mocking import (
    _DummyScorer,
    _EstimatorWithFit,
    _EstimatorWithFitAndPredict,
    _EstimatorWithFitAndScore,
    _EstimatorWithoutFit,
    _MockEstimatorOnOffPrediction,
    CheckingClassifier,
)


@pytest.fixture
def iris():
    return load_iris(return_X_y=True)


def _success(x):
    return True


def _fail(x):
    return False


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"check_X": _success},
        {"check_y": _success},
        {"check_X": _success, "check_y": _success},
    ],
)
def test_check_on_fit_success(iris, kwargs):
    X, y = iris
    CheckingClassifier(**kwargs).fit(X, y)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"check_X": _fail},
        {"check_y": _fail},
        {"check_X": _success, "check_y": _fail},
        {"check_X": _fail, "check_y": _success},
        {"check_X": _fail, "check_y": _fail},
    ],
)
def test_check_on_fit_fail(iris, kwargs):
    X, y = iris
    clf = CheckingClassifier(**kwargs)
    with pytest.raises(AssertionError):
        clf.fit(X, y)


@pytest.mark.parametrize(
    "pred_func", ["predict", "predict_proba", "decision_function", "score"]
)
def test_check_X_on_predict_success(iris, pred_func):
    X, y = iris
    clf = CheckingClassifier(check_X=_success).fit(X, y)
    getattr(clf, pred_func)(X)


@pytest.mark.parametrize(
    "pred_func", ["predict", "predict_proba", "decision_function", "score"]
)
def test_check_X_on_predict_fail(iris, pred_func):
    X, y = iris
    clf = CheckingClassifier(check_X=_success).fit(X, y)
    clf.set_params(check_X=_fail)
    with pytest.raises(AssertionError):
        getattr(clf, pred_func)(X)


@pytest.mark.parametrize("input_type", ["list", "array", "sparse", "dataframe"])
def test_checking_classifier(iris, input_type):
    # Check that the CheckingClassifier outputs what we expect
    X, y = iris
    X = _convert_container(X, input_type)
    clf = CheckingClassifier()
    clf.fit(X, y)

    assert_array_equal(clf.classes_, np.unique(y))
    assert len(clf.classes_) == 3
    assert clf.n_features_in_ == 4

    y_pred = clf.predict(X)
    assert_array_equal(y_pred, np.zeros(y_pred.size, dtype=int))

    assert clf.score(X) == pytest.approx(0)
    clf.set_params(foo_param=10)
    assert clf.fit(X, y).score(X) == pytest.approx(1)

    y_proba = clf.predict_proba(X)
    assert y_proba.shape == (150, 3)
    assert_allclose(y_proba[:, 0], 1)
    assert_allclose(y_proba[:, 1:], 0)

    y_decision = clf.decision_function(X)
    assert y_decision.shape == (150, 3)
    assert_allclose(y_decision[:, 0], 1)
    assert_allclose(y_decision[:, 1:], 0)

    # check the shape in case of binary classification
    first_2_classes = np.logical_or(y == 0, y == 1)
    X = _safe_indexing(X, first_2_classes)
    y = _safe_indexing(y, first_2_classes)
    clf.fit(X, y)

    y_proba = clf.predict_proba(X)
    assert y_proba.shape == (100, 2)
    assert_allclose(y_proba[:, 0], 1)
    assert_allclose(y_proba[:, 1], 0)

    y_decision = clf.decision_function(X)
    assert y_decision.shape == (100,)
    assert_allclose(y_decision, 0)


def test_checking_classifier_with_params(iris):
    X, y = iris
    X_sparse = sparse.csr_matrix(X)

    clf = CheckingClassifier(check_X=sparse.issparse)
    with pytest.raises(AssertionError):
        clf.fit(X, y)
    clf.fit(X_sparse, y)

    clf = CheckingClassifier(
        check_X=check_array, check_X_params={"accept_sparse": False}
    )
    clf.fit(X, y)
    with pytest.raises(TypeError, match="A sparse matrix was passed"):
        clf.fit(X_sparse, y)


def test_checking_classifier_fit_params(iris):
    # check the error raised when the number of samples is not the one expected
    X, y = iris
    clf = CheckingClassifier(expected_fit_params=["sample_weight"])
    sample_weight = np.ones(len(X) // 2)

    with pytest.raises(AssertionError, match="Fit parameter sample_weight"):
        clf.fit(X, y, sample_weight=sample_weight)


def test_checking_classifier_missing_fit_params(iris):
    X, y = iris
    clf = CheckingClassifier(expected_fit_params=["sample_weight"])
    with pytest.raises(AssertionError, match="Expected fit parameter"):
        clf.fit(X, y)


@pytest.mark.parametrize(
    "methods_to_check",
    [["predict"], ["predict", "predict_proba"]],
)
@pytest.mark.parametrize(
    "predict_method", ["predict", "predict_proba", "decision_function", "score"]
)
def test_checking_classifier_methods_to_check(iris, methods_to_check, predict_method):
    # check that methods_to_check allows to bypass checks
    X, y = iris

    clf = CheckingClassifier(
        check_X=sparse.issparse,
        methods_to_check=methods_to_check,
    )

    clf.fit(X, y)
    if predict_method in methods_to_check:
        with pytest.raises(AssertionError):
            getattr(clf, predict_method)(X)
    else:
        getattr(clf, predict_method)(X)


def test_estimator_without_fit():
    estimator = _EstimatorWithoutFit(random_state=42)
    assert estimator.random_state == 42
    assert not hasattr(estimator, "fit")
    assert not hasattr(estimator, "predict")
    assert not hasattr(estimator, "score")


def test_estimator_with_fit(iris):
    X, y = iris
    estimator = _EstimatorWithFit(random_state=42)
    assert estimator.random_state == 42
    assert hasattr(estimator, "fit")
    estimator.fit(X, y)
    assert hasattr(estimator, "random_state_")
    assert hasattr(estimator, "classes_")
    assert_array_equal(estimator.classes_, np.unique(y))


def test_estimator_with_fit_and_score(iris):
    X, y = iris
    estimator = _EstimatorWithFitAndScore(random_state=42)
    assert estimator.random_state == 42
    assert hasattr(estimator, "fit")
    estimator.fit(X, y)
    assert hasattr(estimator, "random_state_")
    assert hasattr(estimator, "classes_")
    assert_array_equal(estimator.classes_, np.unique(y))
    assert hasattr(estimator, "score")
    assert estimator.score(X, y) == pytest.approx(1)


def test_estimator_with_fit_and_predict(iris):
    X, y = iris
    estimator = _EstimatorWithFitAndPredict(random_state=42)
    assert estimator.random_state == 42
    assert hasattr(estimator, "fit")
    estimator.fit(X, y)
    assert hasattr(estimator, "random_state_")
    assert hasattr(estimator, "classes_")
    assert_array_equal(estimator.classes_, np.unique(y))
    assert hasattr(estimator, "predict")
    y_pred = estimator.predict(X)
    assert y_pred.shape == y.shape
    assert_array_equal(np.unique(y_pred), np.unique(y))


@pytest.mark.parametrize(
    "response_methods",
    [
        ["predict"],
        ["predict", "predict_proba"],
        ["predict", "decision_function"],
        ["predict", "predict_proba", "decision_function"],
    ],
)
def test_mock_estimator_on_off_prediction(iris, response_methods):
    X, y = iris
    estimator = _MockEstimatorOnOffPrediction(response_methods=response_methods)

    estimator.fit(X, y)
    assert hasattr(estimator, "classes_")
    assert_array_equal(estimator.classes_, np.unique(y))

    possible_responses = ["predict", "predict_proba", "decision_function"]
    for response in possible_responses:
        if response in response_methods:
            assert hasattr(estimator, response)
        else:
            assert not hasattr(estimator, response)


def test_dummy_scorer(iris):
    X, y = iris
    estimator = _EstimatorWithFit()
    scorer = _DummyScorer()
    score = scorer(estimator, X, y)
    assert score == pytest.approx(1)
