"""Custom luigi.Parameter subclasses for PlanExe.

Plain `luigi.Parameter` warns ("not of type string") whenever the
value isn't a `str`. The check auto-skips any subclass — Luigi's
`Parameter._warn_on_wrong_param_type` returns early when
`self.__class__ != Parameter`. Subclassing is enough to silence
the warning while keeping the rest of the parameter behaviour.
"""
from pathlib import Path
import luigi


class PathParameter(luigi.Parameter):
    """Path-valued task parameter. Accepts str or Path; stores Path."""

    def parse(self, x):
        return Path(x)

    def serialize(self, x):
        return str(x)

    def normalize(self, x):
        if x is None:
            return None
        return Path(x)


class CallableParameter(luigi.Parameter):
    """Holds an arbitrary Python object (e.g. a bound method).

    Intended for non-significant private parameters where Luigi's
    string-type warning would otherwise fire.
    """
