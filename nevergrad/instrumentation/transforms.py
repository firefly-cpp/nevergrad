# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import uuid
from typing import Optional
import numpy as np
from scipy import stats


class Transform:
    """Base class for transforms implementing a forward and a backward (inverse)
    method.
    This provide a default representation, and a short representation should be implemented
    for each transform.
    """

    def __init__(self) -> None:
        self.name = uuid.uuid4().hex  # a name for easy identification. This random uuid should be overriden

    def forward(self, x: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def backward(self, y: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def reverted(self) -> 'Transform':
        return Reverted(self)

    def __repr__(self) -> str:
        args = ", ".join(f"{x}={y}" for x, y in sorted(self.__dict__.items()) if not x.startswith("_"))
        return f"{self.__class__.__name__}({args})"


class Reverted(Transform):
    """Inverse of a transform.

    Parameters
    ----------
    transform: Transform
    """

    def __init__(self, transform: Transform) -> None:
        super().__init__()
        self.transform = transform
        self.name = f"Rv({self.transform.name})"

    def forward(self, x: np.ndarray) -> np.ndarray:
        return self.transform.backward(x)

    def backward(self, y: np.ndarray) -> np.ndarray:
        return self.transform.forward(y)


class Affine(Transform):
    """Affine transform a * x + b

    Parameters
    ----------
    a: float
    b: float
    """

    def __init__(self, a: float, b: float) -> None:
        super().__init__()
        if not a:
            raise ValueError('"a" parameter should be non-zero to prevent information loss.')
        self.a = a
        self.b = b
        self.name = f"Af({self.a},{self.b})"

    def forward(self, x: np.ndarray) -> np.ndarray:
        return self.a * x + self.b  # type: ignore

    def backward(self, y: np.ndarray) -> np.ndarray:
        return (y - self.b) / self.a  # type: ignore


class Exponentiate(Transform):
    """Exponentiation transform base ** (coeff * x)
    This can for instance be used for to get a logarithmicly distruted values 10**(-[1, 2, 3]).

    Parameters
    ----------
    base: float
    coeff: float
    """

    def __init__(self, base: float = 10., coeff: float = 1.) -> None:
        super().__init__()
        self.base = base
        self.coeff = coeff
        self.name = f"Ex({self.base},{self.coeff})"

    def forward(self, x: np.ndarray) -> np.ndarray:
        return self.base ** (float(self.coeff) * x)  # type: ignore

    def backward(self, y: np.ndarray) -> np.ndarray:
        return np.log(y) / (float(self.coeff) * np.log(self.base))  # type: ignore


class TanhBound(Transform):
    """Bounds all real values into [a_min, a_max] using a tanh transform.
    Beware, tanh goes very fast to its limits.

    Parameters
    ----------
    a_min: float
    a_max: float
    """

    def __init__(self, a_min: float, a_max: float) -> None:
        super().__init__()
        assert a_min < a_max
        self.a_min = a_min
        self.a_max = a_max
        self._b = .5 * (self.a_max + self.a_min)
        self._a = .5 * (self.a_max - self.a_min)
        self.name = f"Th({self.a_min},{self.a_max})"

    def forward(self, x: np.ndarray) -> np.ndarray:
        return self._b + self._a * np.tanh(x)  # type: ignore

    def backward(self, y: np.ndarray) -> np.ndarray:
        if np.max(y) > self.a_max or np.min(y) < self.a_min:
            raise ValueError(f"Only data between {self.a_min} and {self.a_max} "
                             "can be transformed back (bounds lead to infinity).")
        return np.arctanh((y - self._b) / self._a)  # type: ignore


class Clipping(Transform):
    """Bounds all real values into [a_min, a_max] using clipping (not bijective).

    Parameters
    ----------
    a_min: float or None
    a_max: float or None
    """

    def __init__(self, a_min: Optional[float] = None, a_max: Optional[float] = None) -> None:
        super().__init__()
        if a_min is not None and a_max is not None:
            assert a_min < a_max
        assert not (a_min is None and a_max is None), "At least one side should be clipped"
        self.a_min = a_min
        self.a_max = a_max
        self.name = f"Cl({self.a_min},{self.a_max})"

    def forward(self, x: np.ndarray) -> np.ndarray:
        return np.clip(x, self.a_min, self.a_max)  # type: ignore

    def backward(self, y: np.ndarray) -> np.ndarray:
        if (self.a_max is not None and np.max(y) > self.a_max) or (self.a_min is not None and np.min(y) < self.a_min):
            raise ValueError(f"Only data between {self.a_min} and {self.a_max} "
                             "can be transformed back.")
        return y


class ArctanBound(Transform):
    """Bounds all real values into [a_min, a_max] using an arctan transform.
    This is a much softer approach compared to tanh.

    Parameters
    ----------
    a_min: float
    a_max: float
    """

    def __init__(self, a_min: float, a_max: float) -> None:
        super().__init__()
        assert a_min < a_max
        self.a_min = a_min
        self.a_max = a_max
        self._b = .5 * (self.a_max + self.a_min)
        self._a = (self.a_max - self.a_min) / np.pi
        self.name = f"At({self.a_min},{self.a_max})"

    def forward(self, x: np.ndarray) -> np.ndarray:
        return self._b + self._a * np.arctan(x)  # type: ignore

    def backward(self, y: np.ndarray) -> np.ndarray:
        if np.max(y) > self.a_max or np.min(y) < self.a_min:
            raise ValueError(f"Only data between {self.a_min} and {self.a_max} can be transformed back.")
        return np.tan((y - self._b) / self._a)  # type: ignore


class CumulativeDensity(Transform):
    """Bounds all real values into [0, 1] using a gaussian cumulative density function (cdf)
    Beware, cdf goes very fast to its limits.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "Cd()"

    def forward(self, x: np.ndarray) -> np.ndarray:
        return stats.norm.cdf(x)  # type: ignore

    def backward(self, y: np.ndarray) -> np.ndarray:
        if np.max(y) > 1 or np.min(y) < 0:
            raise ValueError("Only data between 0 and 1 can be transformed back (bounds lead to infinity).")
        return stats.norm.ppf(y)  # type: ignore
