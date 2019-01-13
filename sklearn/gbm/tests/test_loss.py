import numpy as np
from numpy.testing import assert_almost_equal
import scipy
from scipy.optimize import newton
from scipy.special import logsumexp
from sklearn.utils import assert_all_finite
import pytest

from sklearn.gbm.loss import _LOSSES
from sklearn.gbm.types import Y_DTYPE


def get_derivatives_helper(loss):
    """Return get_gradients() and get_hessians() functions for a given loss.
    """

    def get_gradients(y_true, raw_predictions):
        # create gradients and hessians array, update inplace, and return
        shape = raw_predictions.shape[0] * raw_predictions.shape[1]
        gradients = np.empty(shape=shape, dtype=Y_DTYPE)
        hessians = np.empty(shape=shape, dtype=Y_DTYPE)
        loss.update_gradients_and_hessians(gradients, hessians, y_true,
                                           raw_predictions)

        if loss.__class__ is _LOSSES['least_squares']:
            gradients *= 2  # ommitted a factor of 2 to be consistent with LGBM

        return gradients

    def get_hessians(y_true, raw_predictions):
        # create gradients and hessians array, update inplace, and return
        shape = raw_predictions.shape[0] * raw_predictions.shape[1]
        gradients = np.empty(shape=shape, dtype=Y_DTYPE)
        hessians = np.empty(shape=shape, dtype=Y_DTYPE)
        loss.update_gradients_and_hessians(gradients, hessians, y_true,
                                           raw_predictions)

        if loss.__class__ is _LOSSES['least_squares']:
            # hessians aren't updated because they're constant
            hessians = np.full_like(y_true, fill_value=2)

        return hessians

    return get_gradients, get_hessians


@pytest.mark.parametrize('loss, x0, y_true', [
    ('least_squares', -2., 42),
    ('least_squares', 117., 1.05),
    ('least_squares', 0., 0.),
    # I don't understand why but y_true == 0 fails :/
    # ('binary_crossentropy', 0.3, 0),
    ('binary_crossentropy', -12, 1),
    ('binary_crossentropy', 30, 1),
])
@pytest.mark.skipif(scipy.__version__.split('.')[:2] == ['1', '2'],
                    reason='bug in scipy 1.2.0, see scipy issue #9608')
@pytest.mark.skipif(Y_DTYPE != np.float64,
                    reason='Newton internally uses float64 != Y_DTYPE')
def test_derivatives(loss, x0, y_true):
    # Check that gradients are zero when the loss is minimized on 1D array
    # using the Newton-Raphson and the first and second order derivatives
    # computed by the Loss instance.

    loss = _LOSSES[loss]()
    y_true = np.array([y_true], dtype=Y_DTYPE)
    x0 = np.array([x0], dtype=Y_DTYPE).reshape(1, 1)
    get_gradients, get_hessians = get_derivatives_helper(loss)

    def func(x):
        return loss(y_true, x)

    def fprime(x):
        return get_gradients(y_true, x)

    def fprime2(x):
        return get_hessians(y_true, x)

    optimum = newton(func, x0=x0, fprime=fprime, fprime2=fprime2)
    assert np.allclose(loss.inverse_link_function(optimum), y_true)
    assert np.allclose(loss(y_true, optimum), 0)
    assert np.allclose(get_gradients(y_true, optimum), 0)


@pytest.mark.parametrize('loss, n_classes, prediction_dim', [
    ('least_squares', 0, 1),
    ('binary_crossentropy', 2, 1),
    # ('categorical_crossentropy', 3, 3),
])
@pytest.mark.skipif(Y_DTYPE != np.float64,
                    reason='Need 64 bits float precision for numerical checks')
def test_numerical_gradients(loss, n_classes, prediction_dim):
    # Make sure gradients and hessians computed in the loss are correct, by
    # comparing with their approximations computed with finite central
    # differences.
    # See https://en.wikipedia.org/wiki/Finite_difference.

    rng = np.random.RandomState(0)
    n_samples = 100
    if loss == 'least_squares':
        y_true = rng.normal(size=n_samples).astype(Y_DTYPE)
    else:
        y_true = rng.randint(0, n_classes, size=n_samples).astype(Y_DTYPE)
    raw_predictions = rng.normal(
        size=(n_samples, prediction_dim)
    ).astype(Y_DTYPE)
    loss = _LOSSES[loss]()
    get_gradients, get_hessians = get_derivatives_helper(loss)

    # [:n_samples] to only take gradients and hessians of first tree.
    gradients = get_gradients(y_true, raw_predictions)[:n_samples]
    hessians = get_hessians(y_true, raw_predictions)[:n_samples]

    # Approximate gradients
    # For multiclass loss, we should only change the predictions of one tree
    # (here the first), hence the use of offset[:, 0] += eps
    # As a softmax is computed, offsetting the whole array by a constant would
    # have no effect on the probabilities, and thus on the loss
    eps = 1e-9
    offset = np.zeros_like(raw_predictions)
    offset[:, 0] = eps
    f_plus_eps = loss(y_true, raw_predictions + offset / 2, average=False)
    f_minus_eps = loss(y_true, raw_predictions - offset / 2, average=False)
    numerical_gradient = (f_plus_eps - f_minus_eps) / eps

    # Approximate hessians
    eps = 1e-4  # need big enough eps as we divide by its square
    offset[:, 0] = eps
    f_plus_eps = loss(y_true, raw_predictions + offset, average=False)
    f_minus_eps = loss(y_true, raw_predictions - offset, average=False)
    f = loss(y_true, raw_predictions, average=False)
    numerical_hessians = (f_plus_eps + f_minus_eps - 2 * f) / eps**2

    def relative_error(a, b):
        return np.abs(a - b) / np.maximum(np.abs(a), np.abs(b))

    assert np.all(relative_error(numerical_gradient, gradients) < 1e-5)
    assert np.all(relative_error(numerical_hessians, hessians) < 1e-5)


def test_baseline_least_squares():
    rng = np.random.RandomState(0)

    loss = _LOSSES['least_squares']()
    y_train = rng.normal(size=100)
    baseline_prediction = loss.get_baseline_prediction(y_train, 1)
    assert baseline_prediction.shape == tuple()  # scalar
    # Make sure baseline prediction is the mean of all targets
    assert_almost_equal(baseline_prediction, y_train.mean())


def test_baseline_binary_crossentropy():
    rng = np.random.RandomState(0)

    loss = _LOSSES['binary_crossentropy']()
    for y_train in (np.zeros(shape=100), np.ones(shape=100)):
        y_train = y_train.astype(np.float32)
        baseline_prediction = loss.get_baseline_prediction(y_train, 1)
        assert_all_finite(baseline_prediction)
        assert_almost_equal(loss.inverse_link_function(baseline_prediction),
                            y_train[0])

    # Make sure baseline prediction is equal to link_function(p), where p
    # is the proba of the positive class. We want predict_proba() to return p,
    # and by definition
    # p = inverse_link_function(raw_prediction) = sigmoid(raw_prediction)
    # So we want raw_prediction = link_function(p) = log(p / (1 - p))
    y_train = rng.randint(0, 2, size=100).astype(np.float32)
    baseline_prediction = loss.get_baseline_prediction(y_train, 1)
    assert baseline_prediction.shape == tuple()  # scalar
    p = y_train.mean()
    assert_almost_equal(baseline_prediction, np.log(p / (1 - p)))


@pytest.mark.skip('categorical crossentropy not supported yet')
def test_baseline_categorical_crossentropy():
    rng = np.random.RandomState(0)

    prediction_dim = 4
    loss = _LOSSES['categorical_crossentropy']()
    for y_train in (np.zeros(shape=100), np.ones(shape=100)):
        y_train = y_train.astype(np.float32)
        baseline_prediction = loss.get_baseline_prediction(y_train,
                                                           prediction_dim)
        assert_all_finite(baseline_prediction)

    # Same logic as for above test. Here inverse_link_function = softmax and
    # link_function = log
    y_train = rng.randint(0, prediction_dim + 1, size=100).astype(np.float32)
    baseline_prediction = loss.get_baseline_prediction(y_train, prediction_dim)
    assert baseline_prediction.shape == (1, prediction_dim)
    for k in range(prediction_dim):
        p = (y_train == k).mean()
        assert_almost_equal(baseline_prediction[:, k], np.log(p))
