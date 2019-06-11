"""
The :mod:`sklearn.utils` module includes various utilities.
"""
from collections.abc import Sequence
from contextlib import contextmanager
import numbers
import platform
import struct
import timeit

import warnings
import numpy as np
from scipy.sparse import issparse

from .murmurhash import murmurhash3_32
from .class_weight import compute_class_weight, compute_sample_weight
from . import _joblib
from ..exceptions import DataConversionWarning
from .deprecation import deprecated
from .validation import (as_float_array,
                         assert_all_finite,
                         check_random_state, column_or_1d, check_array,
                         check_consistent_length, check_X_y, indexable,
                         check_symmetric, check_scalar)
from .. import get_config


# Do not deprecate parallel_backend and register_parallel_backend as they are
# needed to tune `scikit-learn` behavior and have different effect if called
# from the vendored version or or the site-package version. The other are
# utilities that are independent of scikit-learn so they are not part of
# scikit-learn public API.
parallel_backend = _joblib.parallel_backend
register_parallel_backend = _joblib.register_parallel_backend

# deprecate the joblib API in sklearn in favor of using directly joblib
msg = ("deprecated in version 0.20.1 to be removed in version 0.23. "
       "Please import this functionality directly from joblib, which can "
       "be installed with: pip install joblib.")
deprecate = deprecated(msg)

delayed = deprecate(_joblib.delayed)
cpu_count = deprecate(_joblib.cpu_count)
hash = deprecate(_joblib.hash)
effective_n_jobs = deprecate(_joblib.effective_n_jobs)


# for classes, deprecated will change the object in _joblib module so we need
# to subclass them.
@deprecate
class Memory(_joblib.Memory):
    pass


@deprecate
class Parallel(_joblib.Parallel):
    pass


__all__ = ["murmurhash3_32", "as_float_array",
           "assert_all_finite", "check_array",
           "check_random_state",
           "compute_class_weight", "compute_sample_weight",
           "column_or_1d", "safe_indexing",
           "check_consistent_length", "check_X_y", "check_scalar", 'indexable',
           "check_symmetric", "indices_to_mask", "deprecated",
           "cpu_count", "Parallel", "Memory", "delayed", "parallel_backend",
           "register_parallel_backend", "hash", "effective_n_jobs",
           "resample", "shuffle", "check_matplotlib_support"]

IS_PYPY = platform.python_implementation() == 'PyPy'
_IS_32BIT = 8 * struct.calcsize("P") == 32


class Bunch(dict):
    """Container object for datasets

    Dictionary-like object that exposes its keys as attributes.

    >>> b = Bunch(a=1, b=2)
    >>> b['b']
    2
    >>> b.b
    2
    >>> b.a = 3
    >>> b['a']
    3
    >>> b.c = 6
    >>> b['c']
    6

    """

    def __init__(self, **kwargs):
        super().__init__(kwargs)

    def __setattr__(self, key, value):
        self[key] = value

    def __dir__(self):
        return self.keys()

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setstate__(self, state):
        # Bunch pickles generated with scikit-learn 0.16.* have an non
        # empty __dict__. This causes a surprising behaviour when
        # loading these pickles scikit-learn 0.17: reading bunch.key
        # uses __dict__ but assigning to bunch.key use __setattr__ and
        # only changes bunch['key']. More details can be found at:
        # https://github.com/scikit-learn/scikit-learn/issues/6196.
        # Overriding __setstate__ to be a noop has the effect of
        # ignoring the pickled __dict__
        pass


def safe_mask(X, mask):
    """Return a mask which is safe to use on X.

    Parameters
    ----------
    X : {array-like, sparse matrix}
        Data on which to apply mask.

    mask : array
        Mask to be used on X.

    Returns
    -------
        mask
    """
    mask = np.asarray(mask)
    if np.issubdtype(mask.dtype, np.signedinteger):
        return mask

    if hasattr(X, "toarray"):
        ind = np.arange(mask.shape[0])
        mask = ind[mask]
    return mask


def axis0_safe_slice(X, mask, len_mask):
    """
    This mask is safer than safe_mask since it returns an
    empty array, when a sparse matrix is sliced with a boolean mask
    with all False, instead of raising an unhelpful error in older
    versions of SciPy.

    See: https://github.com/scipy/scipy/issues/5361

    Also note that we can avoid doing the dot product by checking if
    the len_mask is not zero in _huber_loss_and_gradient but this
    is not going to be the bottleneck, since the number of outliers
    and non_outliers are typically non-zero and it makes the code
    tougher to follow.

    Parameters
    ----------
    X : {array-like, sparse matrix}
        Data on which to apply mask.

    mask : array
        Mask to be used on X.

    len_mask : int
        The length of the mask.

    Returns
    -------
        mask
    """
    if len_mask != 0:
        return X[safe_mask(X, mask), :]
    return np.zeros(shape=(0, X.shape[1]))


def safe_indexing(X, indices, axis=0):
    """Return rows, items or columns of X using indices.

    Parameters
    ----------
    X : array-like, sparse-matrix, list, pandas.DataFrame, pandas.Series
        Data from which to sample rows, items or columns.
    indices : see below
        When ``axis=0``, indices need to be an array of integer.
        When ``axis=1``, indices can be one of:
            Supported key types (key):
            - scalar: output is 1D
            - lists, slices, boolean masks: output is 2D
            - callable that returns any of the above
            Supported key data types:
            - integer or boolean mask (positional):
                - supported for arrays, sparse matrices and dataframes
            - string (key-based):
                - only supported for dataframes
                - So no keys other than strings are allowed (while in principle
                  you can use any hashable object as key).
    axis : int, default=0
        The axis along which the X will be subsampled. ``axis=0`` will select
        rows while ``axis=1`` will select columns.

    Notes
    -----
    CSR, CSC, and LIL sparse matrices are supported. COO sparse matrices are
    not supported.
    """
    if axis == 0:
        return _safe_indexing_row(X, indices)
    return _safe_indexing_column(X, indices)


def _safe_indexing_row(X, indices):
    """Return items or rows from X using indices.

    Allows simple indexing of lists or arrays.

    Parameters
    ----------
    X : array-like, sparse-matrix, list, pandas.DataFrame, pandas.Series
        Data from which to sample rows or items.
    indices : array-like of int
        Indices according to which X will be subsampled.

    Returns
    -------
    subset
        Subset of X on first axis.

    Notes
    -----
    CSR, CSC, and LIL sparse matrices are supported. COO sparse matrices are
    not supported.
    """
    indices = np.asarray(indices)
    if hasattr(X, "iloc"):
        # Work-around for indexing with read-only indices in pandas
        indices = indices if indices.flags.writeable else indices.copy()
        # Pandas Dataframes and Series
        try:
            return X.iloc[indices]
        except ValueError:
            # Cython typed memoryviews internally used in pandas do not support
            # readonly buffers.
            warnings.warn("Copying input dataframe for slicing.",
                          DataConversionWarning)
            return X.copy().iloc[indices]
    elif hasattr(X, "shape"):
        if hasattr(X, 'take') and (hasattr(indices, 'dtype') and
                                   indices.dtype.kind == 'i'):
            # This is often substantially faster than X[indices]
            return X.take(indices, axis=0)
        else:
            return X[indices]
    else:
        return [X[idx] for idx in indices]


def _check_key_type(key, superclass):
    """Check that scalar, list or slice is of a certain type.

    This is only used in _safe_indexing_column and _get_column_indices to check
    if the ``key`` (column specification) is fully integer or fully
    string-like.

    Parameters
    ----------
    key : scalar, list, slice, array-like
        The column specification to check.
    superclass : int or str
        The type for which to check the `key`.
    """
    if isinstance(key, superclass):
        return True
    if isinstance(key, slice):
        return (isinstance(key.start, (superclass, type(None))) and
                isinstance(key.stop, (superclass, type(None))))
    if isinstance(key, list):
        return all(isinstance(x, superclass) for x in key)
    if hasattr(key, 'dtype'):
        if superclass is int:
            return key.dtype.kind == 'i'
        else:
            # superclass = str
            return key.dtype.kind in ('O', 'U', 'S')
    return False


def _safe_indexing_column(X, key):
    """Get feature column(s) from input data X.

    Supported input types (X): numpy arrays, sparse arrays and DataFrames.

    Supported key types (key):
    - scalar: output is 1D;
    - lists, slices, boolean masks: output is 2D;
    - callable that returns any of the above.

    Supported key data types:
    - integer or boolean mask (positional):
        - supported for arrays, sparse matrices and dataframes.
    - string (key-based):
        - only supported for dataframes;
        - So no keys other than strings are allowed (while in principle you
          can use any hashable object as key).
    """
    # check whether we have string column names or integers
    if _check_key_type(key, int):
        column_names = False
    elif _check_key_type(key, str):
        column_names = True
    elif hasattr(key, 'dtype') and np.issubdtype(key.dtype, np.bool_):
        # boolean mask
        column_names = False
        if hasattr(X, 'loc'):
            # pandas boolean masks don't work with iloc, so take loc path
            column_names = True
    else:
        raise ValueError("No valid specification of the columns. Only a "
                         "scalar, list or slice of all integers or all "
                         "strings, or boolean mask is allowed")

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


def _get_column_indices(X, key):
    """Get feature column indices for input data X and key.

    For accepted values of `key`, see the docstring of
    :func:`_safe_indexing_column`.
    """
    n_columns = X.shape[1]

    if (_check_key_type(key, int)
            or hasattr(key, 'dtype') and np.issubdtype(key.dtype, np.bool_)):
        # Convert key into positive indexes
        try:
            idx = np.arange(n_columns)[key]
        except IndexError as e:
            raise ValueError(
                'all features must be in [0, %d]' % (n_columns - 1)
            ) from e
        return np.atleast_1d(idx).tolist()
    elif _check_key_type(key, str):
        try:
            all_columns = list(X.columns)
        except AttributeError:
            raise ValueError("Specifying the columns using strings is only "
                             "supported for pandas DataFrames")
        if isinstance(key, str):
            columns = [key]
        elif isinstance(key, slice):
            start, stop = key.start, key.stop
            if start is not None:
                start = all_columns.index(start)
            if stop is not None:
                # pandas indexing with strings is endpoint included
                stop = all_columns.index(stop) + 1
            else:
                stop = n_columns + 1
            return list(range(n_columns)[slice(start, stop)])
        else:
            columns = list(key)

        try:
            column_indices = [all_columns.index(col) for col in columns]
        except ValueError as e:
            if 'not in list' in str(e):
                raise ValueError(
                    "A given feature is not a column of the dataframe"
                ) from e
            raise

        return column_indices
    else:
        raise ValueError("No valid specification of the columns. Only a "
                         "scalar, list or slice of all integers or all "
                         "strings, or boolean mask is allowed")


def resample(*arrays, **options):
    """Resample arrays or sparse matrices in a consistent way

    The default strategy implements one step of the bootstrapping
    procedure.

    Parameters
    ----------
    *arrays : sequence of indexable data-structures
        Indexable data-structures can be arrays, lists, dataframes or scipy
        sparse matrices with consistent first dimension.

    Other Parameters
    ----------------
    replace : boolean, True by default
        Implements resampling with replacement. If False, this will implement
        (sliced) random permutations.

    n_samples : int, None by default
        Number of samples to generate. If left to None this is
        automatically set to the first dimension of the arrays.
        If replace is False it should not be larger than the length of
        arrays.

    random_state : int, RandomState instance or None, optional (default=None)
        The seed of the pseudo random number generator to use when shuffling
        the data.  If int, random_state is the seed used by the random number
        generator; If RandomState instance, random_state is the random number
        generator; If None, the random number generator is the RandomState
        instance used by `np.random`.

    stratify : array-like or None (default=None)
        If not None, data is split in a stratified fashion, using this as
        the class labels.

    Returns
    -------
    resampled_arrays : sequence of indexable data-structures
        Sequence of resampled copies of the collections. The original arrays
        are not impacted.

    Examples
    --------
    It is possible to mix sparse and dense arrays in the same run::

      >>> X = np.array([[1., 0.], [2., 1.], [0., 0.]])
      >>> y = np.array([0, 1, 2])

      >>> from scipy.sparse import coo_matrix
      >>> X_sparse = coo_matrix(X)

      >>> from sklearn.utils import resample
      >>> X, X_sparse, y = resample(X, X_sparse, y, random_state=0)
      >>> X
      array([[1., 0.],
             [2., 1.],
             [1., 0.]])

      >>> X_sparse
      <3x2 sparse matrix of type '<... 'numpy.float64'>'
          with 4 stored elements in Compressed Sparse Row format>

      >>> X_sparse.toarray()
      array([[1., 0.],
             [2., 1.],
             [1., 0.]])

      >>> y
      array([0, 1, 0])

      >>> resample(y, n_samples=2, random_state=0)
      array([0, 1])

    Example using stratification::

      >>> y = [0, 0, 1, 1, 1, 1, 1, 1, 1]
      >>> resample(y, n_samples=5, replace=False, stratify=y,
      ...          random_state=0)
      [1, 1, 1, 0, 1]


    See also
    --------
    :func:`sklearn.utils.shuffle`
    """

    random_state = check_random_state(options.pop('random_state', None))
    replace = options.pop('replace', True)
    max_n_samples = options.pop('n_samples', None)
    stratify = options.pop('stratify', None)
    if options:
        raise ValueError("Unexpected kw arguments: %r" % options.keys())

    if len(arrays) == 0:
        return None

    first = arrays[0]
    n_samples = first.shape[0] if hasattr(first, 'shape') else len(first)

    if max_n_samples is None:
        max_n_samples = n_samples
    elif (max_n_samples > n_samples) and (not replace):
        raise ValueError("Cannot sample %d out of arrays with dim %d "
                         "when replace is False" % (max_n_samples,
                                                    n_samples))

    check_consistent_length(*arrays)

    if stratify is None:
        if replace:
            indices = random_state.randint(0, n_samples, size=(max_n_samples,))
        else:
            indices = np.arange(n_samples)
            random_state.shuffle(indices)
            indices = indices[:max_n_samples]
    else:
        # Code adapted from StratifiedShuffleSplit()
        y = check_array(stratify, ensure_2d=False, dtype=None)
        if y.ndim == 2:
            # for multi-label y, map each distinct row to a string repr
            # using join because str(row) uses an ellipsis if len(row) > 1000
            y = np.array([' '.join(row.astype('str')) for row in y])

        classes, y_indices = np.unique(y, return_inverse=True)
        n_classes = classes.shape[0]

        class_counts = np.bincount(y_indices)

        # Find the sorted list of instances for each class:
        # (np.unique above performs a sort, so code is O(n logn) already)
        class_indices = np.split(np.argsort(y_indices, kind='mergesort'),
                                 np.cumsum(class_counts)[:-1])

        n_i = _approximate_mode(class_counts, max_n_samples, random_state)

        indices = []

        for i in range(n_classes):
            indices_i = random_state.choice(class_indices[i], n_i[i],
                                            replace=replace)
            indices.extend(indices_i)

        indices = random_state.permutation(indices)


    # convert sparse matrices to CSR for row-based indexing
    arrays = [a.tocsr() if issparse(a) else a for a in arrays]
    resampled_arrays = [safe_indexing(a, indices) for a in arrays]
    if len(resampled_arrays) == 1:
        # syntactic sugar for the unit argument case
        return resampled_arrays[0]
    else:
        return resampled_arrays


def shuffle(*arrays, **options):
    """Shuffle arrays or sparse matrices in a consistent way

    This is a convenience alias to ``resample(*arrays, replace=False)`` to do
    random permutations of the collections.

    Parameters
    ----------
    *arrays : sequence of indexable data-structures
        Indexable data-structures can be arrays, lists, dataframes or scipy
        sparse matrices with consistent first dimension.

    Other Parameters
    ----------------
    random_state : int, RandomState instance or None, optional (default=None)
        The seed of the pseudo random number generator to use when shuffling
        the data.  If int, random_state is the seed used by the random number
        generator; If RandomState instance, random_state is the random number
        generator; If None, the random number generator is the RandomState
        instance used by `np.random`.

    n_samples : int, None by default
        Number of samples to generate. If left to None this is
        automatically set to the first dimension of the arrays.

    Returns
    -------
    shuffled_arrays : sequence of indexable data-structures
        Sequence of shuffled copies of the collections. The original arrays
        are not impacted.

    Examples
    --------
    It is possible to mix sparse and dense arrays in the same run::

      >>> X = np.array([[1., 0.], [2., 1.], [0., 0.]])
      >>> y = np.array([0, 1, 2])

      >>> from scipy.sparse import coo_matrix
      >>> X_sparse = coo_matrix(X)

      >>> from sklearn.utils import shuffle
      >>> X, X_sparse, y = shuffle(X, X_sparse, y, random_state=0)
      >>> X
      array([[0., 0.],
             [2., 1.],
             [1., 0.]])

      >>> X_sparse
      <3x2 sparse matrix of type '<... 'numpy.float64'>'
          with 3 stored elements in Compressed Sparse Row format>

      >>> X_sparse.toarray()
      array([[0., 0.],
             [2., 1.],
             [1., 0.]])

      >>> y
      array([2, 1, 0])

      >>> shuffle(y, n_samples=2, random_state=0)
      array([0, 1])

    See also
    --------
    :func:`sklearn.utils.resample`
    """
    options['replace'] = False
    return resample(*arrays, **options)


def safe_sqr(X, copy=True):
    """Element wise squaring of array-likes and sparse matrices.

    Parameters
    ----------
    X : array like, matrix, sparse matrix

    copy : boolean, optional, default True
        Whether to create a copy of X and operate on it or to perform
        inplace computation (default behaviour).

    Returns
    -------
    X ** 2 : element wise square
    """
    X = check_array(X, accept_sparse=['csr', 'csc', 'coo'], ensure_2d=False)
    if issparse(X):
        if copy:
            X = X.copy()
        X.data **= 2
    else:
        if copy:
            X = X ** 2
        else:
            X **= 2
    return X


def gen_batches(n, batch_size, min_batch_size=0):
    """Generator to create slices containing batch_size elements, from 0 to n.

    The last slice may contain less than batch_size elements, when batch_size
    does not divide n.

    Parameters
    ----------
    n : int
    batch_size : int
        Number of element in each batch
    min_batch_size : int, default=0
        Minimum batch size to produce.

    Yields
    ------
    slice of batch_size elements

    Examples
    --------
    >>> from sklearn.utils import gen_batches
    >>> list(gen_batches(7, 3))
    [slice(0, 3, None), slice(3, 6, None), slice(6, 7, None)]
    >>> list(gen_batches(6, 3))
    [slice(0, 3, None), slice(3, 6, None)]
    >>> list(gen_batches(2, 3))
    [slice(0, 2, None)]
    >>> list(gen_batches(7, 3, min_batch_size=0))
    [slice(0, 3, None), slice(3, 6, None), slice(6, 7, None)]
    >>> list(gen_batches(7, 3, min_batch_size=2))
    [slice(0, 3, None), slice(3, 7, None)]
    """
    start = 0
    for _ in range(int(n // batch_size)):
        end = start + batch_size
        if end + min_batch_size > n:
            continue
        yield slice(start, end)
        start = end
    if start < n:
        yield slice(start, n)


def gen_even_slices(n, n_packs, n_samples=None):
    """Generator to create n_packs slices going up to n.

    Parameters
    ----------
    n : int
    n_packs : int
        Number of slices to generate.
    n_samples : int or None (default = None)
        Number of samples. Pass n_samples when the slices are to be used for
        sparse matrix indexing; slicing off-the-end raises an exception, while
        it works for NumPy arrays.

    Yields
    ------
    slice

    Examples
    --------
    >>> from sklearn.utils import gen_even_slices
    >>> list(gen_even_slices(10, 1))
    [slice(0, 10, None)]
    >>> list(gen_even_slices(10, 10))
    [slice(0, 1, None), slice(1, 2, None), ..., slice(9, 10, None)]
    >>> list(gen_even_slices(10, 5))
    [slice(0, 2, None), slice(2, 4, None), ..., slice(8, 10, None)]
    >>> list(gen_even_slices(10, 3))
    [slice(0, 4, None), slice(4, 7, None), slice(7, 10, None)]
    """
    start = 0
    if n_packs < 1:
        raise ValueError("gen_even_slices got n_packs=%s, must be >=1"
                         % n_packs)
    for pack_num in range(n_packs):
        this_n = n // n_packs
        if pack_num < n % n_packs:
            this_n += 1
        if this_n > 0:
            end = start + this_n
            if n_samples is not None:
                end = min(n_samples, end)
            yield slice(start, end, None)
            start = end


def tosequence(x):
    """Cast iterable x to a Sequence, avoiding a copy if possible.

    Parameters
    ----------
    x : iterable
    """
    if isinstance(x, np.ndarray):
        return np.asarray(x)
    elif isinstance(x, Sequence):
        return x
    else:
        return list(x)


def indices_to_mask(indices, mask_length):
    """Convert list of indices to boolean mask.

    Parameters
    ----------
    indices : list-like
        List of integers treated as indices.
    mask_length : int
        Length of boolean mask to be generated.
        This parameter must be greater than max(indices)

    Returns
    -------
    mask : 1d boolean nd-array
        Boolean array that is True where indices are present, else False.

    Examples
    --------
    >>> from sklearn.utils import indices_to_mask
    >>> indices = [1, 2 , 3, 4]
    >>> indices_to_mask(indices, 5)
    array([False,  True,  True,  True,  True])
    """
    if mask_length <= np.max(indices):
        raise ValueError("mask_length must be greater than max(indices)")

    mask = np.zeros(mask_length, dtype=np.bool)
    mask[indices] = True

    return mask


def _message_with_time(source, message, time):
    """Create one line message for logging purposes

    Parameters
    ----------
    source : str
        String indicating the source or the reference of the message

    message : str
        Short message

    time : int
        Time in seconds
    """
    start_message = "[%s] " % source

    # adapted from joblib.logger.short_format_time without the Windows -.1s
    # adjustment
    if time > 60:
        time_str = "%4.1fmin" % (time / 60)
    else:
        time_str = " %5.1fs" % time
    end_message = " %s, total=%s" % (message, time_str)
    dots_len = (70 - len(start_message) - len(end_message))
    return "%s%s%s" % (start_message, dots_len * '.', end_message)


@contextmanager
def _print_elapsed_time(source, message=None):
    """Log elapsed time to stdout when the context is exited

    Parameters
    ----------
    source : str
        String indicating the source or the reference of the message

    message : str or None
        Short message. If None, nothing will be printed

    Returns
    -------
    context_manager
        Prints elapsed time upon exit if verbose
    """
    if message is None:
        yield
    else:
        start = timeit.default_timer()
        yield
        print(
            _message_with_time(source, message,
                               timeit.default_timer() - start))


def get_chunk_n_rows(row_bytes, max_n_rows=None,
                     working_memory=None):
    """Calculates how many rows can be processed within working_memory

    Parameters
    ----------
    row_bytes : int
        The expected number of bytes of memory that will be consumed
        during the processing of each row.
    max_n_rows : int, optional
        The maximum return value.
    working_memory : int or float, optional
        The number of rows to fit inside this number of MiB will be returned.
        When None (default), the value of
        ``sklearn.get_config()['working_memory']`` is used.

    Returns
    -------
    int or the value of n_samples

    Warns
    -----
    Issues a UserWarning if ``row_bytes`` exceeds ``working_memory`` MiB.
    """

    if working_memory is None:
        working_memory = get_config()['working_memory']

    chunk_n_rows = int(working_memory * (2 ** 20) // row_bytes)
    if max_n_rows is not None:
        chunk_n_rows = min(chunk_n_rows, max_n_rows)
    if chunk_n_rows < 1:
        warnings.warn('Could not adhere to working_memory config. '
                      'Currently %.0fMiB, %.0fMiB required.' %
                      (working_memory, np.ceil(row_bytes * 2 ** -20)))
        chunk_n_rows = 1
    return chunk_n_rows


def is_scalar_nan(x):
    """Tests if x is NaN

    This function is meant to overcome the issue that np.isnan does not allow
    non-numerical types as input, and that np.nan is not np.float('nan').

    Parameters
    ----------
    x : any type

    Returns
    -------
    boolean

    Examples
    --------
    >>> is_scalar_nan(np.nan)
    True
    >>> is_scalar_nan(float("nan"))
    True
    >>> is_scalar_nan(None)
    False
    >>> is_scalar_nan("")
    False
    >>> is_scalar_nan([np.nan])
    False
    """
    # convert from numpy.bool_ to python bool to ensure that testing
    # is_scalar_nan(x) is True does not fail.
    return bool(isinstance(x, numbers.Real) and np.isnan(x))


def _approximate_mode(class_counts, n_draws, rng):
    """Computes approximate mode of multivariate hypergeometric.

    This is an approximation to the mode of the multivariate
    hypergeometric given by class_counts and n_draws.
    It shouldn't be off by more than one.

    It is the mostly likely outcome of drawing n_draws many
    samples from the population given by class_counts.

    Parameters
    ----------
    class_counts : ndarray of int
        Population per class.
    n_draws : int
        Number of draws (samples to draw) from the overall population.
    rng : random state
        Used to break ties.

    Returns
    -------
    sampled_classes : ndarray of int
        Number of samples drawn from each class.
        np.sum(sampled_classes) == n_draws

    Examples
    --------
    >>> import numpy as np
    >>> from sklearn.utils import _approximate_mode
    >>> _approximate_mode(class_counts=np.array([4, 2]), n_draws=3, rng=0)
    array([2, 1])
    >>> _approximate_mode(class_counts=np.array([5, 2]), n_draws=4, rng=0)
    array([3, 1])
    >>> _approximate_mode(class_counts=np.array([2, 2, 2, 1]),
    ...                   n_draws=2, rng=0)
    array([0, 1, 1, 0])
    >>> _approximate_mode(class_counts=np.array([2, 2, 2, 1]),
    ...                   n_draws=2, rng=42)
    array([1, 1, 0, 0])
    """
    rng = check_random_state(rng)
    # this computes a bad approximation to the mode of the
    # multivariate hypergeometric given by class_counts and n_draws
    continuous = n_draws * class_counts / class_counts.sum()
    # floored means we don't overshoot n_samples, but probably undershoot
    floored = np.floor(continuous)
    # we add samples according to how much "left over" probability
    # they had, until we arrive at n_samples
    need_to_add = int(n_draws - floored.sum())
    if need_to_add > 0:
        remainder = continuous - floored
        values = np.sort(np.unique(remainder))[::-1]
        # add according to remainder, but break ties
        # randomly to avoid biases
        for value in values:
            inds, = np.where(remainder == value)
            # if we need_to_add less than what's in inds
            # we draw randomly from them.
            # if we need to add more, we add them all and
            # go to the next value
            add_now = min(len(inds), need_to_add)
            inds = rng.choice(inds, size=add_now, replace=False)
            floored[inds] += 1
            need_to_add -= add_now
            if need_to_add == 0:
                break
    return floored.astype(np.int)


def check_matplotlib_support(caller_name):
    """Raise ImportError with detailed error message if mpl is not installed.

    Plot utilities like :func:`plot_partial_dependence` should lazily import
    matplotlib and call this helper before any computation.

    Parameters
    ----------
    caller_name : str
        The name of the caller that requires matplotlib.
    """
    try:
        import matplotlib  # noqa
    except ImportError as e:
        raise ImportError(
            "{} requires matplotlib. You can install matplotlib with "
            "`pip install matplotlib`".format(caller_name)
        ) from e
