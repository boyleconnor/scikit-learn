import html
from contextlib import closing
from inspect import isclass
from io import StringIO
from pathlib import Path
from string import Template

from .. import config_context


class _IDCounter:
    """Generate sequential ids with a prefix."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.count = 0

    def get_id(self):
        self.count += 1
        return f"{self.prefix}-{self.count}"


_CONTAINER_ID_COUNTER = _IDCounter("sk-container-id")
_ESTIMATOR_ID_COUNTER = _IDCounter("sk-estimator-id")


class _VisualBlock:
    """HTML Representation of Estimator

    Parameters
    ----------
    kind : {'serial', 'parallel', 'single'}
        kind of HTML block

    estimators : list of estimators or `_VisualBlock`s or a single estimator
        If kind != 'single', then `estimators` is a list of
        estimators.
        If kind == 'single', then `estimators` is a single estimator.

    names : list of str, default=None
        If kind != 'single', then `names` corresponds to estimators.
        If kind == 'single', then `names` is a single string corresponding to
        the single estimator.

    name_details : list of str, str, or None, default=None
        If kind != 'single', then `name_details` corresponds to `names`.
        If kind == 'single', then `name_details` is a single string
        corresponding to the single estimator.

    dash_wrapped : bool, default=True
        If true, wrapped HTML element will be wrapped with a dashed border.
        Only active when kind != 'single'.
    """

    def __init__(
        self, kind, estimators, *, names=None, name_details=None, dash_wrapped=True
    ):
        self.kind = kind
        self.estimators = estimators
        self.dash_wrapped = dash_wrapped

        if self.kind in ("parallel", "serial"):
            if names is None:
                names = (None,) * len(estimators)
            if name_details is None:
                name_details = (None,) * len(estimators)

        self.names = names
        self.name_details = name_details

    def _sk_visual_block_(self):
        return self


def _write_label_html(
    out,
    name,
    name_details,
    outer_class="sk-label-container",
    inner_class="sk-label",
    checked=False,
    doc_link="",
    is_fitted=False,
    is_fitted_icon="",
):
    """Write labeled html with or without a dropdown with named details"""

    # If the estimator is fitted, add `fitted` to the class to change colors.
    if is_fitted:
        fitted_str = "fitted"
    else:  # Estimator is not fitted, use default colors
        fitted_str = ""

    out.write(
        f'<div class="{outer_class}"><div'
        f' class="{inner_class} {fitted_str} sk-toggleable">'
    )
    name = html.escape(name)

    if name_details is not None:
        name_details = html.escape(str(name_details))
        label_class = f"sk-toggleable__label {fitted_str} sk-toggleable__label-arrow"

        checked_str = "checked" if checked else ""
        est_id = _ESTIMATOR_ID_COUNTER.get_id()

        if doc_link:  # if the doc_link is valid, use it
            doc_label = "<span>Online documentation</span>"
            if name is not None:
                doc_label = f"<span>Documentation for {name}</span>"
            doc_link = (
                f'<a class="sk-estimator-doc-link {fitted_str}" target="_blank"'
                f' href="{doc_link}">?{doc_label}</a>'
            )
        else:  # no doc_link, add no link to the documentation
            doc_link = ""

        fmt_str = (
            '<input class="sk-toggleable__control sk-hidden--visually"'
            f' id="{est_id}" '
            f'type="checkbox" {checked_str}><label for="{est_id}" '
            f'class="{label_class} {fitted_str}">{name}'
            f"{doc_link}{is_fitted_icon}</label><div "
            f'class="sk-toggleable__content {fitted_str}">'
            f"<pre>{name_details}</pre></div> "
        )
        out.write(fmt_str)
    else:
        out.write(f"<label>{name}</label>")
    out.write("</div></div>")  # outer_class inner_class


def _get_visual_block(estimator):
    """Generate information about how to display an estimator."""
    if hasattr(estimator, "_sk_visual_block_"):
        try:
            return estimator._sk_visual_block_()
        except Exception:
            return _VisualBlock(
                "single",
                estimator,
                names=estimator.__class__.__name__,
                name_details=str(estimator),
            )

    if isinstance(estimator, str):
        return _VisualBlock(
            "single", estimator, names=estimator, name_details=estimator
        )
    elif estimator is None:
        return _VisualBlock("single", estimator, names="None", name_details="None")

    # check if estimator looks like a meta estimator (wraps estimators)
    if hasattr(estimator, "get_params") and not isclass(estimator):
        estimators = [
            (key, est)
            for key, est in estimator.get_params(deep=False).items()
            if hasattr(est, "get_params") and hasattr(est, "fit") and not isclass(est)
        ]
        if estimators:
            return _VisualBlock(
                "parallel",
                [est for _, est in estimators],
                names=[f"{key}: {est.__class__.__name__}" for key, est in estimators],
                name_details=[str(est) for _, est in estimators],
            )

    return _VisualBlock(
        "single",
        estimator,
        names=estimator.__class__.__name__,
        name_details=str(estimator),
    )


def _write_estimator_html(
    out,
    estimator,
    estimator_label,
    estimator_label_details,
    is_fitted,
    is_fitted_icon="",
    first_call=False,
):
    """Write estimator to html in serial, parallel, or by itself (single)."""
    # Delayed to avoid circular import
    from sklearn.base import BaseEstimator

    if first_call:
        est_block = _get_visual_block(estimator)
    else:
        is_fitted_icon = ""
        with config_context(print_changed_only=True):
            est_block = _get_visual_block(estimator)
    # `estimator` can also be an instance of `_VisualBlock`
    if isinstance(estimator, BaseEstimator):
        doc_link = estimator._get_doc_link()
    else:
        doc_link = ""
    if est_block.kind in ("serial", "parallel"):
        dashed_wrapped = first_call or est_block.dash_wrapped
        dash_cls = " sk-dashed-wrapped" if dashed_wrapped else ""
        out.write(f'<div class="sk-item{dash_cls}">')

        if estimator_label:
            _write_label_html(
                out,
                estimator_label,
                estimator_label_details,
                doc_link=doc_link,
                is_fitted=is_fitted,
                is_fitted_icon=is_fitted_icon,
            )

        kind = est_block.kind
        out.write(f'<div class="sk-{kind}">')
        est_infos = zip(est_block.estimators, est_block.names, est_block.name_details)

        for est, name, name_details in est_infos:
            if kind == "serial":
                _write_estimator_html(out, est, name, name_details, is_fitted=is_fitted)
            else:  # parallel
                out.write('<div class="sk-parallel-item">')
                # wrap element in a serial visualblock
                serial_block = _VisualBlock("serial", [est], dash_wrapped=False)
                _write_estimator_html(
                    out, serial_block, name, name_details, is_fitted=is_fitted
                )
                out.write("</div>")  # sk-parallel-item

        out.write("</div></div>")
    elif est_block.kind == "single":
        _write_label_html(
            out,
            est_block.names,
            est_block.name_details,
            outer_class="sk-item",
            inner_class="sk-estimator",
            checked=first_call,
            doc_link=doc_link,
            is_fitted=is_fitted,
        )


with open(Path(__file__).with_suffix(".css"), "r") as style_file:
    _STYLE = style_file.read()


def estimator_html_repr(estimator):
    """Build a HTML representation of an estimator.

    Read more in the :ref:`User Guide <visualizing_composite_estimators>`.

    Parameters
    ----------
    estimator : estimator object
        The estimator to visualize.

    Returns
    -------
    html: str
        HTML representation of estimator.
    """
    from sklearn.exceptions import NotFittedError
    from sklearn.utils.validation import check_is_fitted

    if not hasattr(estimator, "fit"):
        # The estimator has no fit method, it's considered unfitted.
        is_fitted = False
        status_label = "<span>Estimator is not fitted</span>"
        fitted_str = ""
    else:
        # The estimator has a proper fit method, so we can check if it's fitted.
        try:
            check_is_fitted(estimator)  # check if the estimator is fitted
            is_fitted = True
            status_label = "<span>Estimator is fitted</span>"
            fitted_str = "fitted"  # `fitted_str` specifies the css class to use
        except NotFittedError:  # estimator is not fitted
            is_fitted = False
            status_label = "<span>Estimator is not fitted</span>"
            fitted_str = ""

    is_fitted_icon = (
        f'<span class="sk-estimator-fit-status {fitted_str}">i{status_label}</span>'
    )
    with closing(StringIO()) as out:
        container_id = _CONTAINER_ID_COUNTER.get_id()
        style_template = Template(_STYLE)

        style_with_id = style_template.substitute(
            id=container_id,
        )
        estimator_str = str(estimator)

        # The fallback message is shown by default and loading the CSS sets
        # div.sk-text-repr-fallback to display: none to hide the fallback message.
        #
        # If the notebook is trusted, the CSS is loaded which hides the fallback
        # message. If the notebook is not trusted, then the CSS is not loaded and the
        # fallback message is shown by default.
        #
        # The reverse logic applies to HTML repr div.sk-container.
        # div.sk-container is hidden by default and the loading the CSS displays it.
        fallback_msg = (
            "In a Jupyter environment, please rerun this cell to show the HTML"
            " representation or trust the notebook. <br />On GitHub, the"
            " HTML representation is unable to render, please try loading this page"
            " with nbviewer.org."
        )
        html_template = (
            f"<style>{style_with_id}</style>"
            f'<div id="{container_id}" class="sk-top-container">'
            '<div class="sk-text-repr-fallback">'
            f"<pre>{html.escape(estimator_str)}</pre><b>{fallback_msg}</b>"
            "</div>"
            '<div class="sk-container" hidden>'
        )

        out.write(html_template)

        _write_estimator_html(
            out,
            estimator,
            estimator.__class__.__name__,
            estimator_str,
            first_call=True,
            is_fitted=is_fitted,
            is_fitted_icon=is_fitted_icon,
        )
        out.write("</div></div>")

        html_output = out.getvalue()
        return html_output
