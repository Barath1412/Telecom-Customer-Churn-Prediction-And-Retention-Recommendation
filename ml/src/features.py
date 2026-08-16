"""
The feature transform.

Everything here lives inside a scikit-learn ColumnTransformer so that the FITTED
transform is serialized together with the model. The notebook's fatal production
bug was dumping the model but not the LabelEncoders or the StandardScaler --
leaving artifacts that cannot score a raw customer. One Pipeline object fixes it.

Why OneHotEncoder and not LabelEncoder for nominal columns:

    LabelEncoder invented this ordering on Payment Method --
        Bank transfer=0 | Credit card=1 | Electronic check=2 | Mailed check=3
    while the real churn rates are --
        16.7%           | 15.2%         | 45.3%             | 19.1%

    The spike is in the MIDDLE. Telling a linear model "higher code = more" when
    the relationship is non-monotone actively destroys signal. Trees can carve
    around it; logistic regression cannot, which is a large part of why it was
    the weakest model in the notebook.

`Contract` is the ONE column with a genuine order (Month-to-month < One year <
Two year), so an integer code is meaningful there and is used deliberately.
"""
from __future__ import annotations
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from .contracts import NOMINAL, ORDINAL, NUMERIC, assert_no_leakage


def build_preprocessor(scale_numeric: bool = True) -> ColumnTransformer:
    """
    scale_numeric=True  -> for logistic regression (needs standardised inputs)
    scale_numeric=False -> for tree models (scaling is a no-op that costs clarity)
    """
    cols = NOMINAL + list(ORDINAL) + NUMERIC
    assert_no_leakage(cols)

    numeric_steps = [("scale", StandardScaler())] if scale_numeric else [("noop", "passthrough")]

    return ColumnTransformer(
        transformers=[
            (
                "nominal",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist",  # unseen level at serve time
                    min_frequency=1,
                    sparse_output=False,
                ),
                NOMINAL,
            ),
            (
                "ordinal",
                OrdinalEncoder(
                    categories=[ORDINAL[c] for c in ORDINAL],
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
                list(ORDINAL),
            ),
            (
                "numeric",
                Pipeline(numeric_steps) if scale_numeric else "passthrough",
                NUMERIC,
            ),
        ],
        remainder="drop",          # anything not named above CANNOT sneak through
        verbose_feature_names_out=False,
    )


def feature_names(fitted_preprocessor: ColumnTransformer) -> list[str]:
    names = list(fitted_preprocessor.get_feature_names_out())
    assert_no_leakage(names)       # final guard, on the expanded matrix
    return names
