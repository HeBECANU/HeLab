"""Parameters an analysis declares: defaults, limits and units, validated before a run.

A ``choice`` parameter picks one of its ``choices`` and a ``text`` one holds free text the
analysis reads itself (e.g. mask circles, ``masks``); another parameter can say it applies
only under one of them (``when``, and ``shown_with`` for a condition on several), so the parameter tree shows it only then and the dock's
source line leaves it out otherwise. ``group`` names the tree section it sits in ("/" nests one in another:
``"Blur/Median"``), and
``page`` the settings tab (a plot whose parameters name more than one page gets a tab each).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, Sequence

from helab.analysis.display_units import number_text

Kind = Literal["float", "int", "bool", "choice", "text"]  # "text": free text (multi-line)
"""A parameter's type: a number, a switch, one of ``choices``, or free (multi-line) text."""
# The prefixes ``unit_prefix`` may name, with their factors.
SI_FACTORS = {"G": 1e9, "M": 1e6, "k": 1e3, "": 1.0, "m": 1e-3, "µ": 1e-6, "n": 1e-9}
"""The SI prefixes ``ParameterSpec.unit_prefix`` may name, with their factors."""
Value = float | int | bool | str
"""A parameter's value: a plain JSON value."""


@dataclass(frozen=True)
class ParameterSpec:
    """One parameter an analysis declares (``DatasetAnalysis.parameters``).

    Example:
        ``ParameterSpec("bins", "Bins", "int", 100, (10, 10_000), tip="Histogram bins.")``

    Attributes:
        name: The key the analysis reads in ``context.parameters``.
        title: What the plot's settings show.
        kind: The type (``Kind``).
        default: The value when none is set.
        limits: (min, max) a number is clamped to; None for no limits.
        suffix: The unit shown after a number (e.g. " %", " s").
        tip: The tooltip in the plot's settings.
        choices: For kind "choice": the allowed values, shown as a drop-down.
        group: The settings section it belongs to ("" for the top level); "/" nests sections
            (``"Blur/Median"``: the Median section inside Blur).
        when: (choice parameter, value): the parameter applies only while that choice
            parameter has that value; None for always.
        si: A float in a base unit (s, m), shown with SI prefixes (4 mm) and stepped by decade.
        page: The settings tab it is on ("" for the first); a group goes on its first
            parameter's page.
        unit_prefix: With ``si``, the one SI prefix the value is always shown with ("m": a T in
            s shown in ms), its digits grouped by thousands; the value itself stays in the base
            unit. None: the prefix follows the value.
        shown_with: A further condition on all the values, beside ``when``: the parameter
            applies only while it holds too. Not compared.
    """
    name: str  # the key the analysis reads
    title: str  # what the parameter tree shows
    kind: Kind
    default: Value
    limits: tuple[float, float] | None = None
    suffix: str = ""
    tip: str = ""
    choices: tuple[str, ...] = ()  # kind "choice": the allowed values, a drop-down in the tree
    group: str = ""  # the parameter tree section this belongs to ("" = top level; "/" nests sections)
    when: tuple[str, str] | None = None  # (choice parameter, value) this applies under; None = always
    si: bool = False  # a float in a base unit (s, m): shown with SI prefixes (4 mm), stepped by decade
    page: str = ""  # the settings tab this is on ("" = the first); a group goes on its first parameter's page
    # With ``si``: the one SI prefix the value is always shown with ("m": a T in s shown in ms, an X
    # in m in mm), its digits grouped by thousands (``display_units``). The value stays in the base
    # unit, so saved settings keep their meaning. None: the prefix follows the value.
    unit_prefix: str | None = None
    # A further condition on the values, beside ``when``, for what one choice can't say (e.g. "a fit
    # with a bimodal model is on"): the parameter applies only while it holds too. Not compared.
    shown_with: Callable[[Mapping[str, Any]], bool] | None = field(default=None, compare=False, repr=False)

    def coerce(self, value: Any) -> Value:
        """``value`` as this parameter's type, clamped to its limits (a choice outside
        ``choices`` becomes the default)."""
        if self.kind == "bool":
            return bool(value)
        if self.kind == "text":
            return str(value)
        if self.kind == "choice":
            text = str(value)
            return text if text in self.choices else str(self.default)
        number: float | int = int(value) if self.kind == "int" else float(value)
        if self.limits is not None:
            lower, upper = self.limits
            number = min(max(number, type(number)(lower)), type(number)(upper))
        return number

    def applies(self, values: Mapping[str, Any]) -> bool:
        """Whether this parameter is in use under ``values`` (its ``when`` holds, or it has none)."""
        if self.when is not None and str(values.get(self.when[0])) != self.when[1]:
            return False
        return self.shown_with is None or bool(self.shown_with(values))

    def tree_item(self, value: Any = None) -> dict[str, Any]:
        """A pyqtgraph ``Parameter`` definition."""
        item: dict[str, Any] = {"name": self.name, "title": self.title,
                                "type": "list" if self.kind == "choice" else self.kind,
                                "value": self.coerce(self.default if value is None else value),
                                "default": self.default}
        if self.kind == "choice":
            item["limits"] = list(self.choices)
        elif self.limits is not None:
            item["limits"] = self.limits
        if self.suffix:
            item["suffix"] = self.suffix.strip()  # the spin box adds its own space
        if self.si:
            # Steps of a tenth of the value's decade: 4 mm → 5 mm, 3.85 s → 3.95 s.
            item.update(siPrefix=True, dec=True, step=0.1, decimals=6)
            if self.unit_prefix is not None:
                item["fixedPrefix"] = self.unit_prefix  # UnitSpinBox's option
        if self.tip:
            item["tip"] = self.tip
        return item

    def text(self, value: Any) -> str:
        """``title value suffix`` for a source line."""
        if self.kind == "bool":
            shown = "on" if value else "off"
        elif self.kind == "text":
            lines = [line.strip() for line in str(value).splitlines() if line.strip()]
            shown = "; ".join(lines) if lines else "(empty)"
        elif isinstance(value, float) and self.si and self.unit_prefix is not None:
            unit = f"{self.unit_prefix}{self.suffix.strip()}"
            return f"{self.title} {number_text(value / SI_FACTORS[self.unit_prefix])} {unit}"
        elif isinstance(value, float):
            shown = f"{value:g}"
        elif isinstance(value, int):
            shown = f"{value:,}"
        else:
            shown = str(value)
        return f"{self.title} {shown}{self.suffix.strip() and ' ' + self.suffix.strip()}"


def effective(specs: Sequence[ParameterSpec], values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Every declared parameter, from ``values`` where given, else its default; unknown keys dropped."""
    values = values or {}
    return {spec.name: spec.coerce(values.get(spec.name, spec.default)) for spec in specs}


def describe(specs: Sequence[ParameterSpec], values: Mapping[str, Any], every: bool = False) -> str:
    """``title value suffix`` pairs for a source line, in declaration order: the parameters
    in use under ``values`` (``every``: all of them, for the record)."""
    return ", ".join(spec.text(values[spec.name]) for spec in specs
                     if spec.name in values and (every or spec.applies(values)))


def tree_children(specs: Sequence[ParameterSpec]) -> list[dict[str, Any]]:
    """pyqtgraph ``Parameter`` definitions, grouped by ``group`` in declaration order ("/" nests a group in
    another)."""
    children: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    for spec in specs:
        item = spec.tree_item()
        if not spec.group:
            children.append(item)
            continue
        siblings, path = children, ""
        for name in group_path(spec.group):
            path = f"{path}/{name}" if path else name
            group = groups.get(path)
            if group is None:
                group = groups[path] = {"name": name, "type": "group", "children": []}
                siblings.append(group)
            siblings = group["children"]
        siblings.append(item)
    return children


def group_path(group: str) -> tuple[str, ...]:
    """A ``group``'s sections, outermost first (``"Blur/Median"`` → ``("Blur", "Median")``; "" → ())."""
    return tuple(name for name in group.split("/") if name)


def unused_parameters(specs: Sequence[ParameterSpec], values: Mapping[str, Any]) -> frozenset[str]:
    """The names of the parameters not in use under ``values`` (``ParameterSpec.applies``: hidden by
    their ``when`` or ``shown_with``), which a result's reuse key leaves out (a setting the run
    didn't use never makes its result look different)."""
    return frozenset(spec.name for spec in specs if not spec.applies(values))
