"""Protocol-neutral description of a writable local inverter setting.

Local mode was read-only for its whole life, and the reason was never that the
tunnel cannot carry a write: ``FC_FORWARD_TO_DEVICE`` is opaque to the
collector and an inverter answers a setter the same way it answers a query.
The reason was that a cloud write is accepted by the platform whether or not
the inverter applies it, so there was no way to tell an owner that a setting
had actually moved. Locally there is: the inverter acknowledges the command and
then reports the setting in its own rating response, which is the same response
the driver already reads during discovery.

Two rules follow from that, and every table in this package keeps them.

* **A setting is exposed only if the inverter reports its current value.** The
  rating response is the evidence; a command no read-back confirms is not
  offered at all, however well documented it is. ``index`` below is the field
  the value is read from, so the declaration cannot exist without it.
* **A write is not finished until the read-back agrees.** ``writer.py`` sends
  the command, requires the acknowledgement, re-reads the rating response and
  compares. An accepted command that moved nothing is reported as a failure
  rather than cached as a success.

The template this module builds is deliberately the same shape the cloud
control API returns from ``queryDeviceCtrlField`` (see
``api.get_device_control_fields``), so the number and select platforms consume
a local device through exactly the path they already use for a cloud one.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

_DECIMAL_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")

# The two control types the cloud template uses; local settings reuse them so
# the entity platforms need no local-specific branch.
KIND_VALUE = "value"
KIND_OPTIONS = "options"


class SettingNotWritable(ValueError):
    """Raised when a value cannot be encoded for this inverter's protocol."""


#: Encodes one accepted value as the vendor command text, without framing.
#:
#: ``readback`` carries every setting's current wire value, because several
#: protocols write two settings in one command and the partner's value has to
#: be sent along unchanged.
Encoder = Callable[["LocalSetting", str, Mapping[str, str]], str]


@dataclass(frozen=True, slots=True)
class LocalSetting:
    """One setting an inverter both reports and accepts a command for."""

    key: str
    name: str
    kind: str
    index: int
    command: str
    encode: Encoder
    unit: str | None = None
    # Read-back scale: the reported field times this is the value shown.
    scale: float = 1.0
    decimals: int = 0
    options: Mapping[str, str] = field(default_factory=dict)
    # Name of a query whose reply enumerates the values this inverter accepts,
    # for a setting whose allowed set is per-model rather than per-protocol.
    # Nothing is offered until that reply arrives: a charging-current limit
    # the hardware does not list is refused by the inverter, and publishing a
    # slider that silently NAKs half its range is worse than publishing
    # nothing.
    options_from: str = ""
    minimum: float | None = None
    maximum: float | None = None
    # Discrete values a numeric setting accepts outside its range, such as a
    # zero that means "off" or "until the battery is full". They are accepted
    # and reported, but left out of the published range: a slider cannot show
    # a gap, and a range widened to include the zero would offer every value
    # in between, none of which the inverter takes.
    extra_values: tuple[float, ...] = ()
    # Settings this command writes alongside the named one. A write refuses to
    # proceed while any of them is unknown, because the command has to carry
    # their current values and guessing one would change a second setting.
    writes_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject a declaration that could not be verified after a write."""
        if self.kind not in (KIND_VALUE, KIND_OPTIONS):
            raise ValueError(f"{self.key}: unsupported setting kind {self.kind!r}")
        if self.index < 0:
            raise ValueError(f"{self.key}: a setting needs a read-back field")
        if (
            self.kind == KIND_OPTIONS
            and len(self.options) < 2
            and not self.options_from
        ):
            raise ValueError(f"{self.key}: an option setting needs at least two values")
        if self.options and self.options_from:
            raise ValueError(f"{self.key}: declare fixed options or a query, not both")
        if self.kind == KIND_VALUE:
            if self.minimum is None or self.maximum is None:
                raise ValueError(
                    f"{self.key}: a numeric setting needs a declared range"
                )
            if self.minimum > self.maximum:
                raise ValueError(f"{self.key}: declared range is inverted")

    @property
    def hint(self) -> str | None:
        """Return the range in the hint spelling the number platform parses.

        ``number_range.compute_range_and_step`` distrusts a cloud hint that
        does not bracket the live value, because the platform has been seen to
        send a 24 V range for a 48 V system (#22). This hint is the inverter's
        own documented range for the protocol it identified as, so it is
        offered in the same spelling and the same scepticism applies to it.
        """
        if self.kind != KIND_VALUE or self.minimum is None or self.maximum is None:
            return None
        return (
            f"{self.minimum:.{self.decimals}f}~{self.maximum:.{self.decimals}f}"
            f"{self.unit or ''}"
        )

    def options_in(self, enumerations: Mapping[str, tuple[str, ...]]) -> dict[str, str]:
        """Return the option set this inverter offers for this setting."""
        if not self.options_from:
            return dict(self.options)
        offered = enumerations.get(self.options_from, ())
        # The key is the inverter's own spelling, which is what a write sends;
        # the label drops its padding so a select does not read "002 A".
        return {
            value: _option_label(value, self.unit)
            for value in offered
            if self._encodable(value)
        }

    def _encodable(self, value: str) -> bool:
        """Return whether a declared bound excludes an enumerated value.

        An inverter may list a limit its own setter command has no documented
        form for, which is a reason to leave that one value out, not to drop
        the setting.
        """
        if self.minimum is None and self.maximum is None:
            return True
        try:
            number = float(value)
        except ValueError:
            return False
        if self.minimum is not None and number < self.minimum:
            return False
        return self.maximum is None or number <= self.maximum

    def decode(
        self, raw: str, enumerations: Mapping[str, tuple[str, ...]] | None = None
    ) -> str | None:
        """Return the reported field as the template's own wire value."""
        text = raw.strip()
        if not text:
            return None
        options = self.options_in(enumerations or {})
        if self.kind == KIND_OPTIONS:
            if text in options:
                return text
            # A reported limit and the list of offered limits are not always
            # spelled alike: QPIRI answers "30" where QMUCHGCR offers "030".
            # The offered spelling is what a write has to send.
            for offered in options:
                if _same_number(offered, text):
                    return offered
            return None
        number = _as_number(text)
        if number is None:
            return None
        value = round(number * self.scale, 3)
        # A field outside the documented range is not this setting: a protocol
        # whose field order differs would otherwise be published as a value
        # and written back to whatever the index really holds.
        if not self._in_range(value):
            return None
        return f"{value:.{self.decimals}f}" if self.decimals else f"{value:g}"

    def accept(
        self, value: str, enumerations: Mapping[str, tuple[str, ...]] | None = None
    ) -> str:
        """Validate an incoming value and return it in its wire spelling."""
        text = str(value).strip()
        if not text:
            raise SettingNotWritable(f"{self.name} cannot be set to an empty value")
        if self.kind == KIND_OPTIONS:
            options = self.options_in(enumerations or {})
            if text in options:
                return text
            for wire, label in options.items():
                if text == label or _same_number(wire, text):
                    return wire
            raise SettingNotWritable(
                f"{self.name} does not offer {value!r}; this inverter accepts "
                f"{', '.join(sorted(options)) or 'nothing it has reported'}"
            )
        number = _as_number(text)
        if number is None:
            raise SettingNotWritable(f"{self.name} expects a number")
        assert self.minimum is not None and self.maximum is not None
        if not self._in_range(number):
            accepted = f"{self.minimum:g} to {self.maximum:g}{self.unit or ''}"
            if self.extra_values:
                extras = ", ".join(f"{extra:g}" for extra in self.extra_values)
                accepted = f"{accepted}, or exactly {extras}"
            raise SettingNotWritable(f"{self.name} accepts {accepted}, not {number:g}")
        return f"{number:.{self.decimals}f}" if self.decimals else f"{number:g}"

    def _in_range(self, value: float) -> bool:
        """Return whether a numeric value is one this setting accepts."""
        if self.minimum is None or self.maximum is None:
            return True
        if self.minimum <= value <= self.maximum:
            return True
        return any(value == extra for extra in self.extra_values)

    def command_for(
        self,
        value: str,
        readback: Mapping[str, str],
        enumerations: Mapping[str, tuple[str, ...]] | None = None,
    ) -> str:
        """Return the vendor command text that writes ``value``."""
        accepted = self.accept(value, enumerations)
        missing = [key for key in self.writes_with if not readback.get(key)]
        if missing:
            # The command carries the partner setting too. Sending a guess for
            # it would change a second setting the owner did not touch.
            raise SettingNotWritable(
                f"{self.name} is written together with "
                f"{', '.join(missing)}, which the inverter has not reported yet"
            )
        return self.encode(self, accepted, readback)


def _as_number(text: str) -> float | None:
    """Parse a plain decimal figure, or return None for anything else.

    Deliberately stricter than ``float``: a field arriving from an inverter,
    or a value arriving from a service call, must be a plain decimal figure.
    Exponent forms and the infinities ``float`` accepts are not values any of
    these protocols carries, and a setting is not the place to find out what
    an inverter does with one.
    """
    if _DECIMAL_RE.fullmatch(text) is None:
        return None
    return float(text)


def _option_label(value: str, unit: str | None) -> str:
    """Label an enumerated value without its wire padding."""
    try:
        shown: str = f"{int(value, 10):d}"
    except ValueError:
        shown = value
    return f"{shown} {unit}" if unit else shown


def _same_number(left: str, right: str) -> bool:
    """Compare two option spellings as numbers when both are numeric."""
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def local_option_for(
    setting: LocalSetting,
    value: str,
    cloud_options: Mapping[str, str],
    enumerations: Mapping[str, tuple[str, ...]] | None = None,
    declared: Mapping[str, str] | None = None,
) -> str | None:
    """Return the wire value this setting takes for a cloud control's value.

    A cloud control and a local setting are the same register under two names,
    and their option vocabularies are two different things as well: devcode
    2449 offers Output Source Priority as 12336, 12337 and 12338 while the
    PI30 command behind it takes 0, 1 and 2. Handing the platform's code
    straight to the inverter was refused outright in that case (#87), and the
    quieter half of the same defect is worse: where a platform code happens to
    be a value the local setting also offers, the inverter accepts it, reports
    it back, and the write is reported as verified although it set something
    the owner did not choose.

    So nothing is positional and nothing is assumed. ``None`` means this write
    has no local route, which sends it down the cloud path it has always taken:

    * A setpoint is a figure in both vocabularies and passes through, where
      ``accept`` judges it against the inverter's own range.
    * A quantity offered as a list - a charging current, an output frequency -
      is matched as a number, against the platform's code and then against
      its label, because one of the two is the figure.
    * A selection code means nothing outside its own vocabulary. It pairs only
      on a declaration in the devcode profile, or on a label that is the same
      word on both sides.
    """
    if setting.kind != KIND_OPTIONS:
        return value
    options = setting.options_in(enumerations or {})
    label = cloud_options.get(value)
    if declared is not None:
        mapped = declared.get(value)
        # A profile that declares this control's vocabulary and not this value
        # has said that this option is not one the local command covers.
        return mapped if mapped is not None and mapped in options else None
    if setting.unit:
        for candidate in (value, label):
            if not candidate:
                continue
            for wire in options:
                if wire == candidate or _same_number(wire, candidate):
                    return wire
        return None
    if label:
        for wire, option_label in options.items():
            if normalized_name(option_label) == normalized_name(label):
                return wire
    return None


def template_for(
    settings: tuple[LocalSetting, ...],
    readback: Mapping[str, str],
    enumerations: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build a cloud-shaped control template from reported settings only.

    The pair returned is what ``async_get_controls_with_values`` contracts for:
    controls keyed by display name, and current values keyed by control id.
    """
    controls: dict[str, Any] = {}
    values: dict[str, str] = {}
    for setting in settings:
        current = readback.get(setting.key)
        if current is None:
            # Not reported, so a write to it could not be verified.
            continue
        if setting.kind == KIND_OPTIONS:
            options = setting.options_in(enumerations or {})
            if len(options) < 2:
                # Either the inverter listed nothing or it listed one value,
                # which is not a choice to publish an entity for.
                continue
            controls[setting.name] = {
                "id": setting.key,
                "type": KIND_OPTIONS,
                "options": options,
            }
        else:
            controls[setting.name] = {
                "id": setting.key,
                "type": KIND_VALUE,
                "unit": setting.unit,
                "hint": setting.hint,
            }
        values[setting.key] = current
    return controls, values


def normalized_name(name: str) -> str:
    """Normalise a control name the way ``sensor_titles`` normalises a title."""
    return " ".join(str(name).split()).casefold()


def pairing_candidates(
    settings: tuple[LocalSetting, ...],
    values: Mapping[str, str],
    cloud_controls: Mapping[str, Any],
    cloud_values: Mapping[str, Any],
    enumerations: Mapping[str, tuple[str, ...]] | None = None,
    declared_settings: Mapping[str, str] | None = None,
    declared_option_values: Mapping[str, Mapping[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Report which cloud control each local setting looks like.

    A cloud control and a local setting are the same register under two names,
    and only a download shows which pairs with which. This is that download's
    evidence, built the way ``tools/analysis_coverage.py`` pairs an unresolved
    reading with the control sitting at its value: a name that normalises to
    the same string is reported as a match, a figure that agrees is reported
    as a candidate, and neither is turned into a declaration here.

    A maintainer reads this and adds the pairing to the devcode profile's
    ``local_control_settings``, after which that control's writes take the
    local link on every installation of that devcode.

    What the profile already declares is reported too, because inference and
    declaration are the only two ways a pairing exists and a report showing
    one of them reads as an absence. Devcode 2449's charger priority is
    declared, since "Charging Source Priority" and the command's "Charger
    Source Priority" differ by a letter, and its entry still said
    ``paired_by_name`` null against an empty candidate list - the shape of a
    setting nothing pairs with (#88).
    """
    by_name = {
        normalized_name(name): (name, config) for name, config in cloud_controls.items()
    }
    declared_by_setting = {
        setting: field_id for field_id, setting in (declared_settings or {}).items()
    }
    report: list[dict[str, Any]] = []
    for setting in settings:
        local_value = values.get(setting.key)
        matched = by_name.get(normalized_name(setting.name))
        candidates = [
            {
                "control": name,
                "id": config.get("id"),
                "value": str(cloud_values.get(config.get("id"), "")),
                "name_matches": normalized_name(name) == normalized_name(setting.name),
            }
            for name, config in cloud_controls.items()
            if (
                normalized_name(name) == normalized_name(setting.name)
                or (
                    # Only a setpoint is paired by its figure. Selection codes
                    # are 0, 1 and 2 on every one of these settings, so a
                    # code that agrees is not evidence of anything.
                    setting.kind == KIND_VALUE
                    and local_value is not None
                    and _same_number(
                        str(cloud_values.get(config.get("id"), "")), local_value
                    )
                )
            )
        ]
        entry: dict[str, Any] = {
            "setting": setting.key,
            "name": setting.name,
            "command": setting.command,
            "kind": setting.kind,
            "unit": setting.unit,
            "reported": local_value,
            "paired_by_name": matched[1].get("id") if matched else None,
            "declared_by_profile": declared_by_setting.get(setting.key),
            "candidates": candidates,
        }
        if setting.kind == KIND_OPTIONS:
            # Which value the command takes for each of its own options. A
            # cloud control offers a different vocabulary for the same
            # register - devcode 2449 offers 12336, 12337 and 12338 where the
            # PI30 command takes 0, 1 and 2 - and a report showing one side
            # only is not enough to declare the mapping from (#87).
            entry["options"] = dict(setting.options_in(enumerations or {}))
            # And which of them the profile says each cloud option code is.
            # A pairing alone does not send a selection down the local link:
            # without this vocabulary the write takes the cloud path, so the
            # two declarations have to be readable apart (#87, #88).
            paired = entry["declared_by_profile"] or entry["paired_by_name"]
            declared_options = (declared_option_values or {}).get(paired)
            if declared_options:
                entry["declared_option_values"] = dict(declared_options)
        report.append(entry)
    return report
