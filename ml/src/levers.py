"""
Lever extraction — the actual personalisation engine.

The measured reason for this design:

    A reason classifier over the 20 `Churn Reason` values scores 0.348 accuracy
    against 0.331 for guessing the largest class, and 0.148 macro-F1 against
    0.140 for random. It has no signal, because the reason themes are
    indistinguishable on the features -- median monthly charges span $5.00
    across all seven themes and median tenure spans 3 months.

    The attributes the company can OBSERVE and ACT ON separate churn enormously:

        Contract     month-to-month 42.7%  |  one year 11.3%  |  two year  2.8%
        Tech Support             no 41.6%  |       yes 15.2%
        Payment      electronic check 45.3% | credit card (auto) 15.2%
        Internet          fiber 41.9%      |       DSL 19.0%

    15x versus 1.05x. So we personalise on levers, not on guessed motives -- and
    it needs no claim about what the customer is thinking.
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

BUNDLE_FIELDS = ["Online Security", "Online Backup", "Device Protection",
                 "Tech Support", "Streaming TV", "Streaming Movies"]


@dataclass(frozen=True)
class Lever:
    code: str
    label: str


LEVERS = {
    "NO_TECH_SUPPORT":      Lever("NO_TECH_SUPPORT", "No tech support add-on"),
    "NO_ONLINE_SECURITY":   Lever("NO_ONLINE_SECURITY", "No online security add-on"),
    "NO_DEVICE_PROTECTION": Lever("NO_DEVICE_PROTECTION", "No device protection"),
    "MONTH_TO_MONTH":       Lever("MONTH_TO_MONTH", "Rolling month-to-month contract"),
    "MANUAL_PAYMENT":       Lever("MANUAL_PAYMENT", "Manual payment method"),
    "HIGH_CHARGE_LOW_BUNDLE": Lever("HIGH_CHARGE_LOW_BUNDLE", "High bill, few add-ons"),
    "NEW_CUSTOMER":         Lever("NEW_CUSTOMER", "Under 12 months tenure"),
    "FIBER_PREMIUM":        Lever("FIBER_PREMIUM", "Premium fiber plan"),
    "NO_INTERNET":          Lever("NO_INTERNET", "Phone-only account"),
}


def bundle_count(row) -> int:
    return sum(1 for f in BUNDLE_FIELDS if row.get(f) == "Yes")


# ---------------------------------------------------------------------------
# THRESHOLD PROVENANCE — audited against the dataset, not guessed.
#
#   HIGH_CHARGE_USD = 80
#     churn by monthly-charge band:  <$30  9.8% | $30-45 27.9% | $45-60 25.1%
#                                    $60-70 20.7% | $70-80 39.4% | $80-90 36.2%
#                                    $90-100 37.9% | $100+ 28.0%
#     Churn crosses the 26.54% base rate around $70. Our $80 cut sits inside the
#     high-risk region but not at its edge, so the segment is TIGHTER than the data
#     would allow. Conservative by design: fewer, more clearly at-risk customers.
#
#   MAX_BUNDLES = 2  (of 6)
#     churn by bundle count: 0:21.4% | 1:45.8% | 2:35.8% | 3:27.4%
#                            4:22.3% | 5:12.4% | 6:5.3%
#     Falls monotonically from 1 onward. The <=2 cut is the last band above base
#     rate. Data-consistent. (Note bundle_count=0 is LOWER than 1-2 because those
#     are phone-only accounts with no internet -- see NO_INTERNET.)
#
#   NEW_CUSTOMER_MONTHS = 12
#     churn by tenure: 0-3: 58.4% | 3-6: 47.3% | 6-12: 36.5%
#                      12-18: 33.6% | 18-24: 24.6% | 24+: 15.6%
#     Churn only drops below base rate after month 18, so <18 would track the data
#     more closely. <12 is again the CONSERVATIVE choice and is kept deliberately:
#     a tighter segment means fewer customers offered an onboarding programme.
#
# All three err toward a smaller, higher-risk segment. That is the safe direction:
# it under-includes rather than over-spends. Change them only with a sensitivity run.
# ---------------------------------------------------------------------------
HIGH_CHARGE_USD = 80.0
MAX_BUNDLES = 2
NEW_CUSTOMER_MONTHS = 12


def extract(row: dict | pd.Series) -> list[str]:
    """Deterministic. No model, no inference -- these are facts you look up."""
    r = row if isinstance(row, dict) else row.to_dict()
    out: list[str] = []
    add = out.append

    if r.get("Tech Support") == "No":        add("NO_TECH_SUPPORT")
    if r.get("Online Security") == "No":     add("NO_ONLINE_SECURITY")
    if r.get("Device Protection") == "No":   add("NO_DEVICE_PROTECTION")
    if r.get("Contract") == "Month-to-month": add("MONTH_TO_MONTH")
    if r.get("Payment Method") in ("Electronic check", "Mailed check"):
        add("MANUAL_PAYMENT")
    if (float(r.get("Monthly Charges", 0)) > HIGH_CHARGE_USD
            and bundle_count(r) <= MAX_BUNDLES):
        add("HIGH_CHARGE_LOW_BUNDLE")
    if int(r.get("Tenure Months", 0)) < NEW_CUSTOMER_MONTHS: add("NEW_CUSTOMER")
    if r.get("Internet Service") == "Fiber optic": add("FIBER_PREMIUM")
    if r.get("Internet Service") == "No":     add("NO_INTERNET")
    return out


def extract_frame(df: pd.DataFrame) -> pd.Series:
    return df.apply(extract, axis=1)


def describe(codes: list[str]) -> str:
    return "; ".join(LEVERS[c].label for c in codes if c in LEVERS)
