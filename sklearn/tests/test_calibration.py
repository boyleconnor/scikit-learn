# Authors: Alexandre Gramfort <alexandre.gramfort@telecom-paristech.fr>
# License: BSD 3 clause

import pytest
import numpy as np
from scipy import sparse

from sklearn.base import BaseEstimator
from sklearn.model_selection import LeaveOneOut

from sklearn.datasets import make_classification, make_blobs
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import brier_score_loss
from sklearn.metrics import confusion_matrix
from sklearn.metrics import f1_score
from sklearn.metrics import log_loss
from sklearn.metrics import recall_score
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.utils._testing import assert_array_almost_equal
from sklearn.utils._testing import assert_almost_equal
from sklearn.utils._testing import assert_array_equal
from sklearn.utils._testing import assert_raises
from sklearn.utils._testing import ignore_warnings

from sklearn.calibration import CalibratedClassifierCV
from sklearn.calibration import CutoffClassifier
from sklearn.calibration import _get_binary_score
from sklearn.calibration import _sigmoid_calibration, _SigmoidCalibration
from sklearn.calibration import calibration_curve


def test_calibration():
    """Test calibration objects with isotonic and sigmoid"""
    n_samples = 100
    X, y = make_classification(n_samples=2 * n_samples, n_features=6,
                               random_state=42)
    sample_weight = np.random.RandomState(seed=42).uniform(size=y.size)

    X -= X.min()  # MultinomialNB only allows positive X

    # split train and test
    X_train, y_train, sw_train = \
        X[:n_samples], y[:n_samples], sample_weight[:n_samples]
    X_test, y_test = X[n_samples:], y[n_samples:]

    # Naive-Bayes
    clf = MultinomialNB().fit(X_train, y_train, sample_weight=sw_train)
    prob_pos_clf = clf.predict_proba(X_test)[:, 1]

    pc_clf = CalibratedClassifierCV(clf, cv=y.size + 1)
    assert_raises(ValueError, pc_clf.fit, X, y)

    # Naive Bayes with calibration
    for this_X_train, this_X_test in [(X_train, X_test),
                                      (sparse.csr_matrix(X_train),
                                       sparse.csr_matrix(X_test))]:
        for method in ['isotonic', 'sigmoid']:
            pc_clf = CalibratedClassifierCV(clf, method=method, cv=2)
            # Note that this fit overwrites the fit on the entire training
            # set
            pc_clf.fit(this_X_train, y_train, sample_weight=sw_train)
            prob_pos_pc_clf = pc_clf.predict_proba(this_X_test)[:, 1]

            # Check that brier score has improved after calibration
            assert (brier_score_loss(y_test, prob_pos_clf) >
                           brier_score_loss(y_test, prob_pos_pc_clf))

            # Check invariance against relabeling [0, 1] -> [1, 2]
            pc_clf.fit(this_X_train, y_train + 1, sample_weight=sw_train)
            prob_pos_pc_clf_relabeled = pc_clf.predict_proba(this_X_test)[:, 1]
            assert_array_almost_equal(prob_pos_pc_clf,
                                      prob_pos_pc_clf_relabeled)

            # Check invariance against relabeling [0, 1] -> [-1, 1]
            pc_clf.fit(this_X_train, 2 * y_train - 1, sample_weight=sw_train)
            prob_pos_pc_clf_relabeled = pc_clf.predict_proba(this_X_test)[:, 1]
            assert_array_almost_equal(prob_pos_pc_clf,
                                      prob_pos_pc_clf_relabeled)

            # Check invariance against relabeling [0, 1] -> [1, 0]
            pc_clf.fit(this_X_train, (y_train + 1) % 2,
                       sample_weight=sw_train)
            prob_pos_pc_clf_relabeled = \
                pc_clf.predict_proba(this_X_test)[:, 1]
            if method == "sigmoid":
                assert_array_almost_equal(prob_pos_pc_clf,
                                          1 - prob_pos_pc_clf_relabeled)
            else:
                # Isotonic calibration is not invariant against relabeling
                # but should improve in both cases
                assert (brier_score_loss(y_test, prob_pos_clf) >
                               brier_score_loss((y_test + 1) % 2,
                                                prob_pos_pc_clf_relabeled))

        # Check failure cases:
        # only "isotonic" and "sigmoid" should be accepted as methods
        clf_invalid_method = CalibratedClassifierCV(clf, method="foo")
        assert_raises(ValueError, clf_invalid_method.fit, X_train, y_train)

        # base-estimators should provide either decision_function or
        # predict_proba (most regressors, for instance, should fail)
        clf_base_regressor = \
            CalibratedClassifierCV(RandomForestRegressor(), method="sigmoid")
        assert_raises(RuntimeError, clf_base_regressor.fit, X_train, y_train)


def test_sample_weight():
    n_samples = 100
    X, y = make_classification(n_samples=2 * n_samples, n_features=6,
                               random_state=42)

    sample_weight = np.random.RandomState(seed=42).uniform(size=len(y))
    X_train, y_train, sw_train = \
        X[:n_samples], y[:n_samples], sample_weight[:n_samples]
    X_test = X[n_samples:]

    for method in ['sigmoid', 'isotonic']:
        base_estimator = LinearSVC(random_state=42)
        calibrated_clf = CalibratedClassifierCV(base_estimator, method=method)
        calibrated_clf.fit(X_train, y_train, sample_weight=sw_train)
        probs_with_sw = calibrated_clf.predict_proba(X_test)

        # As the weights are used for the calibration, they should still yield
        # a different predictions
        calibrated_clf.fit(X_train, y_train)
        probs_without_sw = calibrated_clf.predict_proba(X_test)

        diff = np.linalg.norm(probs_with_sw - probs_without_sw)
        assert diff > 0.1


def test_calibration_multiclass():
    """Test calibration for multiclass """
    # test multi-class setting with classifier that implements
    # only decision function
    clf = LinearSVC()
    X, y_idx = make_blobs(n_samples=100, n_features=2, random_state=42,
                          centers=3, cluster_std=3.0)

    # Use categorical labels to check that CalibratedClassifierCV supports
    # them correctly
    target_names = np.array(['a', 'b', 'c'])
    y = target_names[y_idx]

    X_train, y_train = X[::2], y[::2]
    X_test, y_test = X[1::2], y[1::2]

    clf.fit(X_train, y_train)
    for method in ['isotonic', 'sigmoid']:
        cal_clf = CalibratedClassifierCV(clf, method=method, cv=2)
        cal_clf.fit(X_train, y_train)
        probas = cal_clf.predict_proba(X_test)
        assert_array_almost_equal(np.sum(probas, axis=1), np.ones(len(X_test)))

        # Check that log-loss of calibrated classifier is smaller than
        # log-loss of naively turned OvR decision function to probabilities
        # via softmax
        def softmax(y_pred):
            e = np.exp(-y_pred)
            return e / e.sum(axis=1).reshape(-1, 1)

        uncalibrated_log_loss = \
            log_loss(y_test, softmax(clf.decision_function(X_test)))
        calibrated_log_loss = log_loss(y_test, probas)
        assert uncalibrated_log_loss >= calibrated_log_loss

    # Test that calibration of a multiclass classifier decreases log-loss
    # for RandomForestClassifier
    X, y = make_blobs(n_samples=100, n_features=2, random_state=42,
                      cluster_std=3.0)
    X_train, y_train = X[::2], y[::2]
    X_test, y_test = X[1::2], y[1::2]

    clf = RandomForestClassifier(n_estimators=10, random_state=42)
    clf.fit(X_train, y_train)
    clf_probs = clf.predict_proba(X_test)
    loss = log_loss(y_test, clf_probs)

    for method in ['isotonic', 'sigmoid']:
        cal_clf = CalibratedClassifierCV(clf, method=method, cv=3)
        cal_clf.fit(X_train, y_train)
        cal_clf_probs = cal_clf.predict_proba(X_test)
        cal_loss = log_loss(y_test, cal_clf_probs)
        assert loss > cal_loss


def test_calibration_prefit():
    """Test calibration for prefitted classifiers"""
    n_samples = 50
    X, y = make_classification(n_samples=3 * n_samples, n_features=6,
                               random_state=42)
    sample_weight = np.random.RandomState(seed=42).uniform(size=y.size)

    X -= X.min()  # MultinomialNB only allows positive X

    # split train and test
    X_train, y_train, sw_train = \
        X[:n_samples], y[:n_samples], sample_weight[:n_samples]
    X_calib, y_calib, sw_calib = \
        X[n_samples:2 * n_samples], y[n_samples:2 * n_samples], \
        sample_weight[n_samples:2 * n_samples]
    X_test, y_test = X[2 * n_samples:], y[2 * n_samples:]

    # Naive-Bayes
    clf = MultinomialNB()
    clf.fit(X_train, y_train, sw_train)
    prob_pos_clf = clf.predict_proba(X_test)[:, 1]

    # Naive Bayes with calibration
    for this_X_calib, this_X_test in [(X_calib, X_test),
                                      (sparse.csr_matrix(X_calib),
                                       sparse.csr_matrix(X_test))]:
        for method in ['isotonic', 'sigmoid']:
            pc_clf = CalibratedClassifierCV(clf, method=method, cv="prefit")

            for sw in [sw_calib, None]:
                pc_clf.fit(this_X_calib, y_calib, sample_weight=sw)
                y_prob = pc_clf.predict_proba(this_X_test)
                y_pred = pc_clf.predict(this_X_test)
                prob_pos_pc_clf = y_prob[:, 1]
                assert_array_equal(y_pred,
                                   np.array([0, 1])[np.argmax(y_prob, axis=1)])

                assert (brier_score_loss(y_test, prob_pos_clf) >
                               brier_score_loss(y_test, prob_pos_pc_clf))


def test_sigmoid_calibration():
    """Test calibration values with Platt sigmoid model"""
    exF = np.array([5, -4, 1.0])
    exY = np.array([1, -1, -1])
    # computed from my python port of the C++ code in LibSVM
    AB_lin_libsvm = np.array([-0.20261354391187855, 0.65236314980010512])
    assert_array_almost_equal(AB_lin_libsvm,
                              _sigmoid_calibration(exF, exY), 3)
    lin_prob = 1. / (1. + np.exp(AB_lin_libsvm[0] * exF + AB_lin_libsvm[1]))
    sk_prob = _SigmoidCalibration().fit(exF, exY).predict(exF)
    assert_array_almost_equal(lin_prob, sk_prob, 6)

    # check that _SigmoidCalibration().fit only accepts 1d array or 2d column
    # arrays
    assert_raises(ValueError, _SigmoidCalibration().fit,
                  np.vstack((exF, exF)), exY)


def test_calibration_curve():
    """Check calibration_curve function"""
    y_true = np.array([0, 0, 0, 1, 1, 1])
    y_pred = np.array([0., 0.1, 0.2, 0.8, 0.9, 1.])
    prob_true, prob_pred = calibration_curve(y_true, y_pred, n_bins=2)
    prob_true_unnormalized, prob_pred_unnormalized = \
        calibration_curve(y_true, y_pred * 2, n_bins=2, normalize=True)
    assert len(prob_true) == len(prob_pred)
    assert len(prob_true) == 2
    assert_almost_equal(prob_true, [0, 1])
    assert_almost_equal(prob_pred, [0.1, 0.9])
    assert_almost_equal(prob_true, prob_true_unnormalized)
    assert_almost_equal(prob_pred, prob_pred_unnormalized)

    # probabilities outside [0, 1] should not be accepted when normalize
    # is set to False
    assert_raises(ValueError, calibration_curve, [1.1], [-0.1],
                  normalize=False)

    # test that quantiles work as expected
    y_true2 = np.array([0, 0, 0, 0, 1, 1])
    y_pred2 = np.array([0., 0.1, 0.2, 0.5, 0.9, 1.])
    prob_true_quantile, prob_pred_quantile = calibration_curve(
        y_true2, y_pred2, n_bins=2, strategy='quantile')

    assert len(prob_true_quantile) == len(prob_pred_quantile)
    assert len(prob_true_quantile) == 2
    assert_almost_equal(prob_true_quantile, [0, 2 / 3])
    assert_almost_equal(prob_pred_quantile, [0.1, 0.8])

    # Check that error is raised when invalid strategy is selected
    assert_raises(ValueError, calibration_curve, y_true2, y_pred2,
                  strategy='percentile')


def test_calibration_nan_imputer():
    """Test that calibration can accept nan"""
    X, y = make_classification(n_samples=10, n_features=2,
                               n_informative=2, n_redundant=0,
                               random_state=42)
    X[0, 0] = np.nan
    clf = Pipeline(
        [('imputer', SimpleImputer()),
         ('rf', RandomForestClassifier(n_estimators=1))])
    clf_c = CalibratedClassifierCV(clf, cv=2, method='isotonic')
    clf_c.fit(X, y)
    clf_c.predict(X)


def test_calibration_prob_sum():
    # Test that sum of probabilities is 1. A non-regression test for
    # issue #7796
    num_classes = 2
    X, y = make_classification(n_samples=10, n_features=5,
                               n_classes=num_classes)
    clf = LinearSVC(C=1.0)
    clf_prob = CalibratedClassifierCV(clf, method="sigmoid", cv=LeaveOneOut())
    clf_prob.fit(X, y)

    probs = clf_prob.predict_proba(X)
    assert_array_almost_equal(probs.sum(axis=1), np.ones(probs.shape[0]))


def test_calibration_less_classes():
    # Test to check calibration works fine when train set in a test-train
    # split does not contain all classes
    # Since this test uses LOO, at each iteration train set will not contain a
    # class label
    X = np.random.randn(10, 5)
    y = np.arange(10)
    clf = LinearSVC(C=1.0)
    cal_clf = CalibratedClassifierCV(clf, method="sigmoid", cv=LeaveOneOut())
    cal_clf.fit(X, y)

    for i, calibrated_classifier in \
            enumerate(cal_clf.calibrated_classifiers_):
        proba = calibrated_classifier.predict_proba(X)
        assert_array_equal(proba[:, i], np.zeros(len(y)))
        assert np.all(np.hstack([proba[:, :i],
                                 proba[:, i + 1:]]))


@ignore_warnings(category=FutureWarning)
@pytest.mark.parametrize('X', [np.random.RandomState(42).randn(15, 5, 2),
                               np.random.RandomState(42).randn(15, 5, 2, 6)])
def test_calibration_accepts_ndarray(X):
    """Test that calibration accepts n-dimensional arrays as input"""
    y = [1, 0, 0, 1, 1, 0, 1, 1, 0, 0, 1, 0, 0, 1, 0]

    class MockTensorClassifier(BaseEstimator):
        """A toy estimator that accepts tensor inputs"""

        def fit(self, X, y):
            self.classes_ = np.unique(y)
            return self

        def decision_function(self, X):
            # toy decision function that just needs to have the right shape:
            return X.reshape(X.shape[0], -1).sum(axis=1)

    calibrated_clf = CalibratedClassifierCV(MockTensorClassifier())
    # we should be able to fit this classifier with no error
    calibrated_clf.fit(X, y)


def test_cutoff_prefit():
    calibration_samples = 200
    X, y = make_classification(n_samples=1000, n_features=6, random_state=42,
                               n_classes=2)

    X_train, X_test, y_train, y_test = train_test_split(X, y,
                                                        test_size=0.4,
                                                        random_state=42)
    lr = LogisticRegression(solver='liblinear').fit(X_train, y_train)

    clf_roc = CutoffClassifier(lr, strategy='roc', cv='prefit').fit(
        X_test[:calibration_samples], y_test[:calibration_samples]
    )

    y_pred = lr.predict(X_test[calibration_samples:])
    y_pred_roc = clf_roc.predict(X_test[calibration_samples:])

    tn, fp, fn, tp = confusion_matrix(
        y_test[calibration_samples:], y_pred).ravel()
    tn_roc, fp_roc, fn_roc, tp_roc = confusion_matrix(
        y_test[calibration_samples:], y_pred_roc).ravel()

    tpr = tp / (tp + fn)
    tnr = tn / (tn + fp)

    tpr_roc = tp_roc / (tp_roc + fn_roc)
    tnr_roc = tn_roc / (tn_roc + fp_roc)

    # check that the sum of tpr and tnr has improved
    assert tpr_roc + tnr_roc > tpr + tnr

    clf_f1 = CutoffClassifier(
        lr, strategy='f_beta', method='predict_proba', beta=1,
        cv='prefit').fit(
        X_test[:calibration_samples], y_test[:calibration_samples]
    )

    y_pred_f1 = clf_f1.predict(X_test[calibration_samples:])
    assert (f1_score(y_test[calibration_samples:], y_pred_f1) >
            f1_score(y_test[calibration_samples:], y_pred))

    clf_fbeta = CutoffClassifier(
        lr, strategy='f_beta', method='predict_proba', beta=2,
        cv='prefit').fit(
        X_test[:calibration_samples], y_test[:calibration_samples]
    )

    y_pred_fbeta = clf_fbeta.predict(X_test[calibration_samples:])
    assert (recall_score(y_test[calibration_samples:], y_pred_fbeta) >
            recall_score(y_test[calibration_samples:], y_pred))

    clf_max_tpr = CutoffClassifier(
        lr, strategy='max_tpr', threshold=0.7, cv='prefit'
    ).fit(X_test[:calibration_samples], y_test[:calibration_samples])

    y_pred_max_tpr = clf_max_tpr.predict(X_test[calibration_samples:])

    tn_max_tpr, fp_max_tpr, fn_max_tpr, tp_max_tpr = confusion_matrix(
        y_test[calibration_samples:], y_pred_max_tpr).ravel()

    tpr_max_tpr = tp_max_tpr / (tp_max_tpr + fn_max_tpr)
    tnr_max_tpr = tn_max_tpr / (tn_max_tpr + fp_max_tpr)

    # check that the tpr increases with tnr >= min_val_tnr
    assert tpr_max_tpr > tpr
    assert tpr_max_tpr > tpr_roc
    assert tnr_max_tpr >= 0.7

    clf_max_tnr = CutoffClassifier(
        lr, strategy='max_tnr', threshold=0.7, cv='prefit'
    ).fit(X_test[:calibration_samples], y_test[:calibration_samples])

    y_pred_clf = clf_max_tnr.predict(X_test[calibration_samples:])

    tn_clf, fp_clf, fn_clf, tp_clf = confusion_matrix(
        y_test[calibration_samples:], y_pred_clf).ravel()

    tnr_clf_max_tnr = tn_clf / (tn_clf + fp_clf)
    tpr_clf_max_tnr = tp_clf / (tp_clf + fn_clf)

    # check that the tnr increases with tpr >= min_val_tpr
    assert tnr_clf_max_tnr > tnr
    assert tnr_clf_max_tnr > tnr_roc
    assert tpr_clf_max_tnr >= 0.7

    # check error cases
    clf_bad_base_estimator = CutoffClassifier([])
    with pytest.raises(TypeError):
        clf_bad_base_estimator.fit(X_train, y_train)

    X_non_binary, y_non_binary = make_classification(
        n_samples=20, n_features=6, random_state=42, n_classes=4,
        n_informative=4
    )
    with pytest.raises(ValueError):
        clf_roc.fit(X_non_binary, y_non_binary)


def test_cutoff_cv():
    X, y = make_classification(n_samples=1000, n_features=6, random_state=42,
                               n_classes=2)

    X_train, X_test, y_train, y_test = train_test_split(X, y,
                                                        test_size=0.4,
                                                        random_state=42)
    lr = LogisticRegression(solver='liblinear').fit(X_train, y_train)
    clf_roc = CutoffClassifier(LogisticRegression(solver='liblinear'),
                               strategy='roc',
                               cv=3).fit(
        X_train, y_train
    )

    assert clf_roc.decision_threshold_ != 0
    assert clf_roc.std_ is not None and clf_roc.std_ != 0

    y_pred = lr.predict(X_test)
    y_pred_roc = clf_roc.predict(X_test)

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    tn_roc, fp_roc, fn_roc, tp_roc = confusion_matrix(
        y_test, y_pred_roc
    ).ravel()

    tpr = tp / (tp + fn)
    tnr = tn / (tn + fp)

    tpr_roc = tp_roc / (tp_roc + fn_roc)
    tnr_roc = tn_roc / (tn_roc + fp_roc)

    # check that the sum of tpr + tnr has improved
    assert tpr_roc + tnr_roc > tpr + tnr


# def test_get_binary_score():
#     X, y = make_classification(n_samples=200, n_features=6, random_state=42,
#                                n_classes=2)

#     X_train, X_test, y_train, _ = train_test_split(X, y, test_size=0.4,
#                                                    random_state=42)
#     lr = LogisticRegression(solver='liblinear').fit(X_train, y_train)
#     y_pred_proba = lr.predict_proba(X_test)
#     y_pred_score = lr.decision_function(X_test)

#     assert_array_equal(
#         y_pred_score, _get_binary_score(
#             lr, X_test, method='decision_function', pos_label=1)
#     )

#     assert_array_equal(
#         - y_pred_score, _get_binary_score(
#             lr, X_test, method='decision_function', pos_label=0)
#     )

#     assert_array_equal(
#         y_pred_proba[:, 1], _get_binary_score(
#             lr, X_test, method='predict_proba', pos_label=1)
#     )

#     assert_array_equal(
#         y_pred_proba[:, 0], _get_binary_score(
#             lr, X_test, method='predict_proba', pos_label=0)
#     )

#     assert_array_equal(
#         y_pred_score,
#         _get_binary_score(lr, X_test, method=None, pos_label=1)
#     )

#     with pytest.raises(ValueError):
#         _get_binary_score(lr, X_test, method='foo')

#     # classifier that does not have a decision_function
#     rf = RandomForestClassifier(n_estimators=10).fit(X_train, y_train)
#     y_pred_proba_rf = rf.predict_proba(X_test)
#     assert_array_equal(
#         y_pred_proba_rf[:, 1],
#         _get_binary_score(rf, X_test, method=None, pos_label=1)
#     )

#     X_non_binary, y_non_binary = make_classification(
#         n_samples=20, n_features=6, random_state=42, n_classes=4,
#         n_informative=4
#     )

#     rf_non_bin = RandomForestClassifier(n_estimators=10).fit(X_non_binary,
#                                                              y_non_binary)
#     with pytest.raises(ValueError):
#         _get_binary_score(rf_non_bin, X_non_binary)


class MockNoPredictorClassifier:
    pass


@pytest.mark.parametrize(
    "Estimator, params, err_type, err_msg",
    [
        (LogisticRegression, {"method": "xxx"}, ValueError,
         "'method' should be one of"),
        (MockNoPredictorClassifier, {"method": "auto"}, TypeError,
         "'base_estimator' must implement one of the"),
        (RandomForestRegressor, {"method": "predict_proba"}, TypeError,
         "'base_estimator' does not implement predict_proba"),
        (LogisticRegression, {"strategy": "xxx"}, ValueError,
         "'strategy' must be of"),
        (LogisticRegression, {"strategy": "max_tpr"}, TypeError,
         "When strategy is max_tpr or max_tnr"),
        (LogisticRegression, {"strategy": "f_beta"}, TypeError,
         "When strategy is f_beta"),
        (LogisticRegression, {"strategy": "max_tnr"}, TypeError,
         "When strategy is max_tpr or max_tnr"),
        (LogisticRegression, {"strategy": "max_tpr", "threshold": 10},
         ValueError, r"threshold should be in the range \[0, 1\]"),
        (LogisticRegression, {"strategy": "max_tnr", "threshold": 10},
         ValueError, r"threshold should be in the range \[0, 1\]"),
        (LogisticRegression,
         {"strategy": "constant", "method": "predict_proba",
          "decision_threshold": 10},
         ValueError, r"decision_threshold should be in the range \[0, 1\]")
    ]
)
def test_cutoffclassifier_valid_params_error(Estimator, params, err_type,
                                             err_msg):
    X, y = make_classification(n_samples=200, n_features=6, random_state=42,
                               n_classes=2)
    with pytest.raises(err_type, match=err_msg):
        clf = CutoffClassifier(base_estimator=Estimator(), **params)
        clf.fit(X, y)
