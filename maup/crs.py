from functools import wraps


def require_same_crs(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        geoms1, geoms2, *rest = args
        if not geoms1.crs == geoms2.crs:
            raise TypeError(
                "the source and target geometries must have the same CRS. {} {}".format(
                    geoms1.crs, geoms2.crs
                )
            )
        return f(*args, **kwargs)

    return wrapped
