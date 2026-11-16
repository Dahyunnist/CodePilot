import dask.array as da
import xarray as xr


def test_dataset_update_keeps_chunked_data_lazy():
    values = da.random.random((3, 3), chunks=(2, 2))
    ds = xr.Dataset({"foo": xr.DataArray(values, dims=("x", "y")), "bar": ("x", [1, 2, 3])})
    update = {
        "foo": (("x", "y"), ds.foo[1:, :]),
        "bar": ("x", ds.bar[1:]),
    }

    ds.update(update)

    assert isinstance(ds.foo.data, da.Array)
