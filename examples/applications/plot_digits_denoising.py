"""
================================
Image denoising using kernel PCA
================================

This example shows how to use :class:`~sklearn.decomposition.kernelPCA` to
denoise images. In short, we take advantage of the approximation function
learned during `fit` to reconstruct the original image.

We will compare the results with an exact reconstruction using
:class:`~sklearn.decomposition.PCA`.

We will use USPS digits dataset to reproduce presented in Sect. 4 of [1]_.

.. topic:: References

   .. [1] `Bakır, Gökhan H., Jason Weston, and Bernhard Schölkopf.
      "Learning to find pre-images."
      Advances in neural information processing systems 16 (2004): 449-456.
      <https://papers.nips.cc/paper/2003/file/ac1ad983e08ad3304a97e147f522747e-Paper.pdf>`_
"""

print(__doc__)

# Authors: Guillaume Lemaitre <guillaume.lemaitre@inria.fr>
# Licence: BSD 3 clause

# %%
# Load the dataset via OpenML
# ---------------------------
#
# The USPS digits datasets in available in OpenML. We use
# :func:`~sklearn.datasets.fetch_openml` to get this dataset. In addition, we
# normalize the dataset such that all pixel values are in the range (0, 1).
import numpy as np
from sklearn.datasets import fetch_openml
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split

X, y = fetch_openml(data_id=41082, as_frame=False, return_X_y=True)
X = MinMaxScaler().fit_transform(X)

# %%
# The idea will be to learn a PCA basis (with and without a kernel) on denoised
# images and then used these models to reconstruct images corrupted with some
# additional noise.
#
# Thus, we split our dataset into a training and testing set composed of 1,000
# samples for the training and 100 samples for testing. In addition, we create
# a copy of the testing subset to which we an additional Gaussian noise.

# %%
# The idea of this application, is to show that we can denoise corrupted images
# by learning a PCA basis on some uncorrupted images. We will use both a PCA
# and a kernel-based PCA to solve this problem.
#
# Our experimental setup will be the following: create a training set with
# uncorrupted data, a testing set with uncorrupted data as well, and make a
# copy of this test to which we will add a Gaussian noise to corrupt it.
#
# We create a training and testing of 1,000 samples and a test set of 100
# samples.

X_train, X_test, y_train, y_test = train_test_split(
    X, y, stratify=y, random_state=0, train_size=1_000, test_size=100
)

rng = np.random.RandomState(0)
noise = rng.normal(scale=0.25, size=X_test.shape)
X_test_noisy = X_test + noise


# %%
# In addition, we will create a helper function to qualitatively assess the
# image reconstruction by plotting the test images.
import matplotlib.pyplot as plt


def plot_digits(X, title):
    """Small helper function to plot 100 digits."""
    fig, axs = plt.subplots(nrows=10, ncols=10, figsize=(8, 8))
    for img, ax in zip(X, axs.ravel()):
        ax.imshow(img.reshape((16, 16)), cmap="Greys")
        ax.axis("off")
    fig.suptitle(title, fontsize=24)


# %%
# In addition, we will use the mean squared error (MSE) to quantitatively
# assess the image reconstruction.
#
# Let's first have a look at our entire dataset.
plot_digits(X_train, "Uncorrupted train images")
plot_digits(X_test, "Uncorrupted test images")
plot_digits(X_test_noisy,
            f"Noisy test images\n"
            f"MSE: {np.mean((X_test - X_test_noisy) ** 2):.2f}")

# %%
# We can now learn our PCA basis using both a linear PCA and a kernel PCA that
# uses a radial basis function (RBF) kernel.
from sklearn.decomposition import PCA, KernelPCA

pca = PCA(n_components=32)
kernel_pca = KernelPCA(n_components=200, kernel="rbf", gamma=1e-3,
                       fit_inverse_transform=True, alpha=5e-3)

pca.fit(X_train)
_ = kernel_pca.fit(X_train)

# %%
# Now, we can transform and reconstruct the noisy test set. Since we used less
# components than the number of original features, we will get an approximation
# of the original set. Indeed, by dropping the components explaining less
# variance in PCA, we hope to remove noise. Similar thinking happen in kernel
# PCA; however, we expect a better reconstruction because we use a non-linear
# kernel to learn the PCA basis and a kernel ridge to learn the mapping
# function.
X_reconstructed_kernel_pca = kernel_pca.inverse_transform(
    kernel_pca.transform(X_test_noisy))
X_reconstructed_pca = pca.inverse_transform(pca.transform(X_test_noisy))

# %%
plot_digits(X_test, "Uncorrupted test images")
plot_digits(X_reconstructed_pca,
            f"PCA reconstruction\n"
            f"MSE: {np.mean((X_test - X_reconstructed_pca) ** 2):.2f}")
plot_digits(X_reconstructed_kernel_pca,
            f"Kernel PCA reconstruction\n"
            f"MSE: {np.mean((X_test - X_reconstructed_kernel_pca) ** 2):.2f}")

# %%
# Even if both PCA and kernel PCA have the same MSE, a qualitative analysis
# will favor the output of the kernel PCA. However, it should be noted that
# the results of the denoising with kernel PCA will depend of the parameters
# `n_components`, `gamma`, and `alpha`.
