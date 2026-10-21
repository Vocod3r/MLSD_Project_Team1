"""FNOL data contract (F1, F2, D1).

Every request is checked against this before a run is created. A request that fails
any rule is quarantined with field-level errors and never reaches the agents.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# Indian registration: state code, RTO number, optional series, number. e.g. KA-11-AB-1234, MH 02 CD 5678
REG_RE = re.compile(r"^[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{0,3}[ -]?\d{1,4}$", re.I)
# Bharat series: 22-BH-1234-AA
BH_RE = re.compile(r"^\d{2}[ -]?BH[ -]?\d{4}[ -]?[A-Z]{1,2}$", re.I)

MAX_ESTIMATE_INR = 5_00_00_000   # 5 crore: anything above is almost certainly a typo
MAX_REPORT_DELAY_DAYS = 365      # beyond this the request is rejected, not just flagged


class FNOL(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    policy_number: str = Field(min_length=5, max_length=40)
    insured_name: str = Field(min_length=2, max_length=100)
    vehicle_registration: str = Field(min_length=4, max_length=15)
    channel: Literal["web", "app", "call_centre"]
    date_of_loss: dt.date
    date_of_report: dt.date
    place_of_loss: str = Field(min_length=2, max_length=200)
    estimated_loss_inr: float = Field(ge=0, le=MAX_ESTIMATE_INR)
    description: str = Field(min_length=15, max_length=5000)
    garage_name: str | None = Field(default=None, max_length=120)
    fir_number: str | None = Field(default=None, max_length=60)
    cashless_requested: bool = False
    third_party_involved: bool = False
    injuries: bool = False
    police_report_filed: bool = False

    @field_validator("vehicle_registration")
    @classmethod
    def valid_registration(cls, v: str) -> str:
        if not (REG_RE.match(v) or BH_RE.match(v)):
            raise ValueError("not a valid Indian registration number (e.g. KA-11-AB-1234)")
        return v.upper()

    @field_validator("date_of_loss", "date_of_report")
    @classmethod
    def not_in_future(cls, v: dt.date) -> dt.date:
        if v > dt.date.today():
            raise ValueError("cannot be in the future")
        return v

    @model_validator(mode="after")
    def cross_field_rules(self):
        errors = []
        if self.date_of_report < self.date_of_loss:
            errors.append(("date_of_report", "must be on or after date_of_loss"))
        elif (self.date_of_report - self.date_of_loss).days > MAX_REPORT_DELAY_DAYS:
            errors.append(("date_of_report", f"more than {MAX_REPORT_DELAY_DAYS} days after date_of_loss"))
        if self.cashless_requested and not self.garage_name:
            errors.append(("garage_name", "required when cashless_requested is true"))
        if self.police_report_filed and not self.fir_number:
            errors.append(("fir_number", "required when police_report_filed is true"))
        if errors:
            raise CrossFieldError(errors)
        return self


class CrossFieldError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(f"{f}: {m}" for f, m in errors))


def validate_fnol(payload) -> tuple[dict | None, list[dict]]:
    """Returns (clean_fnol, []) or (None, [{field, message}, ...])."""
    if not isinstance(payload, dict):
        return None, [{"field": "(body)", "message": "request body must be a JSON object"}]
    try:
        fnol = FNOL.model_validate(payload)
    except ValidationError as e:
        out = []
        for err in e.errors():
            ctx_err = (err.get("ctx") or {}).get("error")
            if isinstance(ctx_err, CrossFieldError):
                out += [{"field": f, "message": m} for f, m in ctx_err.errors]
                continue
            field = ".".join(str(p) for p in err["loc"]) or "(body)"
            msg = err["msg"].removeprefix("Value error, ")
            if err["type"] == "missing" or (err["type"] in ("string_type", "float_type", "date_type")
                                            and err.get("input") is None):
                msg = "required"
            elif err["type"] == "extra_forbidden":
                msg = "unexpected field"
            out.append({"field": field, "message": msg})
        return None, out
    return fnol.model_dump(mode="json"), []