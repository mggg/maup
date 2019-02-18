import numpy as np
import pandas as pd
import shapely
from pandas.api.extensions import (
    ExtensionArray,
    ExtensionDtype,
    register_extension_dtype,
)


@register_extension_dtype
class GeometryDtype(ExtensionDtype):
    name = "geometry"
    type = shapely.geometry.base.BaseGeometry

    @classmethod
    def construct_array_type(cls):
        return GeometryArray

    @classmethod
    def construct_from_string(cls, string):
        if string == cls.name:
            return cls()
        else:
            raise TypeError("Cannot construct a '{}' from " "'{}'".format(cls, string))


class GeometryArray(ExtensionArray):
    def __init__(self, geometries):
        self.geometries = np.array(geometries)

    def __iter__(self):
        return iter(self.geometries)

    def __getitem__(self, selector):
        return self.__class__(self.geometries[selector])

    def __len__(self):
        return len(self.geometries)

    def isna(self):
        return pd.array([geom.is_empty for geom in self.geometries], dtype=np.bool)

    @property
    def dtype(self):
        return GeometryDtype()

    @classmethod
    def _from_sequence(cls, scalars, dtype=None, copy=False):
        if dtype is not None and not isinstance(dtype, GeometryDtype):
            raise TypeError("GeometryArray is only compatible with GeometryDtype.")
        return cls(scalars)
