#!/usr/bin/env python

import os
import sys
import getopt
import importlib
import time

"""
Output metadata and model files based on an input parameter file and a given CSV data file. The output can be one more of the following:
    -- Metadata in GeoCSV
    -- Metadata in JSON
    -- Model in GeoCSV
    -- Model in netCDF

Author: Manochehr Bahavar / EarthScope
"""
# Get the directory paths.
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PROP_DIR = os.path.join(ROOT_DIR, "prop")
sys.path.append(PROP_DIR)
import shared_prop as prop
import writer_prop as writer_prop

LIB_DIR = os.path.join(ROOT_DIR, prop.LIB_DIR)
sys.path.append(LIB_DIR)
import shared_lib as lib
import writer_lib as meta_lib

# Set up the logger.
logger = lib.get_logger()
line_break = "\n"


def usage():
    logger.info(
        f"""
    Output metadata and model based on an input parameter file and a given CSV data file. The output can be one or more of the following:
        -- Metadata in GeoCSV
        -- Metadata in JSON
        -- Model in GeoCSV
        -- Model in netCDF

    Call arguments:
        -h, --help: this message.
        -m, --meta: [required] a text parameter file based on the parameter template files under the template directory.
        -g, --global: [required] a text global parameter file based on the parameter template files under the template directory.
        -d, --data: [required] a CSV data filename with a header
        -o, --output: [required] the output filename without extension. The metadata output files will add "_metadata" to this output filename.
        -t, --output_types: [default netcdf] a comma separated string of output types. The valid output types are: "metadata", "geocsv", "netcdf"
             metadata: output metadata as GeoCSV and JSON files.
             geocsv: output the model in GeoCSV format.
             netcdf: output the model in netCDF format.
"""
    )


def main():
    # Capture the input parameters.
    try:
        argv = sys.argv[1:]
        opts, args = getopt.getopt(
            argv,
            "hg:m:d:o:t:",
            ["help", "global=", "meta=", "data=", "output=", "output_types="],
        )
    except getopt.GetoptError as err:
        # Print the error, and help information and exit:
        logger.error(err)
        usage()
        sys.exit(2)

    # Initialize the variables.
    meta_file = None
    global_meta_file = None
    output = None
    data_file = None
    output_types = "netcdf"
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-m", "--meta"):
            meta_file = a
            if not os.path.isfile(meta_file):
                logger.error(
                    f"[ERR] Invalid metadata file: {meta_file}. File not found!"
                )
                sys.exit(2)
        elif o in ("-g", "--global"):
            global_meta_file = a
            if not os.path.isfile(global_meta_file):
                logger.error(
                    f"[ERR] Invalid global metadata file: {global_meta_file}. File not found!"
                )
                sys.exit(2)
        elif o in ("-d", "--data"):
            data_file = a
        elif o in ("-o", "--output"):
            output = a
        elif o in ("-t", "--output_types"):
            output_types = a.strip()
        else:
            assert False, "unhandled option"

    # The output file is required.
    if output is None:
        usage()
        logger.error(f"[ERR] output file is required.")
        sys.exit(1)

    # Global metadata file is required.
    if global_meta_file is None:
        usage()
        logger.error(f"[ERR] global metadata file is required.")
        sys.exit(1)
    else:
        params = lib.read_model_metadata(global_meta_file)

    # Metadata file is required.
    if meta_file is None:
        usage()
        logger.error(f"[ERR] metadata file is required.")
        sys.exit(1)
    else:
        params = lib.read_model_metadata(meta_file, params=params)

    # Data file is required.
    if data_file is None and ("netcdf" in output_types or "geocsv" in output_types):
        usage()
        logger.error(f"[ERR] data file is required.")
        sys.exit(1)

    # Check the output types.
    output_types = output_types.split(",")
    for _type in output_types:
        if _type not in writer_prop.valid_output_types:
            usage()
            logger.error(
                f"[ERR] Invalid output type [{_type}] requested. Must be one of {list(writer_prop.valid_output_types)}."
            )
            sys.exit(1)
    if "netcdf" in output_types:
        nc_format = params["netcdf_format"]
        if nc_format not in writer_prop.netcdf_format:
            usage()
            logger.error(
                f"[ERR] Invalid netcdf option: {nc_format}. Must be one of {list(writer_prop.netcdf_format.keys)}."
            )
            sys.exit(1)
        nc_format = writer_prop.netcdf_format[nc_format]

    # Parse the metadata .
    metadata_dict, metadata, var_dict, data_variables = meta_lib.get_metadata(params)

    # Initialize the timer.
    t0 = time.time()
    file_size_kb = None
    # NetCDF or geocsv model files requested?
    if "netcdf" in output_types or "geocsv" in output_types:
        # Proceed only if a data file is given
        if data_file is None:
            logger.warning(f"[WARN] No data file was provided.")
            sys.exit(0)
        elif not os.path.isfile(data_file):
            logger.error(f"[ERR] data file '{data_file}' not found!")
            sys.exit(1)
        else:
            df, params = meta_lib.read_csv(
                data_file,
                params,
            )
            t0, time_txt = lib.time_it(t0)
            logger.info(f"[{time_txt}] data in DataFrame")
            # See if we have to decimate data.
            unique_z = None
            # Create a list of decimation factors)
            decimation_factors = list()
            try:
                x_decimation_factor = 1
                unique_x = sorted(df[metadata["x"]["column"]].unique())

                if "decimation_factor" in metadata["x"]:
                    metadata["x"]["decimation_factor"] = int(
                        metadata["x"]["decimation_factor"]
                    )
                    x_decimation_factor = metadata["x"]["decimation_factor"]
                    if x_decimation_factor > 1:
                        if "geospatial" in metadata:
                            metadata["geospatial"][
                                "geospatial_lon_resolution"
                            ] *= x_decimation_factor
                    logger.info(
                        f"[INFO] X decimation factor {x_decimation_factor} for {len(unique_x)} unique X"
                    )
                    unique_x = unique_x[::x_decimation_factor]
                    logger.info(f"[INFO] {len(unique_x)} unique X ")
                decimation_factors.append(x_decimation_factor)

                y_decimation_factor = 1
                unique_y = sorted(df[metadata["y"]["column"]].unique())
                if "decimation_factor" in metadata["y"]:
                    metadata["y"]["decimation_factor"] = int(
                        metadata["y"]["decimation_factor"]
                    )
                    y_decimation_factor = metadata["y"]["decimation_factor"]
                    if y_decimation_factor > 1:
                        if "geospatial" in metadata:
                            metadata["geospatial"][
                                "geospatial_lat_resolution"
                            ] *= y_decimation_factor

                    logger.info(
                        f"[INFO] Y decimation factor {y_decimation_factor} for {len(unique_y)} unique Y"
                    )
                    unique_y = unique_y[::y_decimation_factor]
                    logger.info(f"[INFO]{len(unique_y)} unique Y ")
                decimation_factors.append(y_decimation_factor)

                z_decimation_factor = 1
                if metadata.get("z") is not None:
                    if "decimation_factor" in metadata["z"]:
                        metadata["z"]["decimation_factor"] = int(
                            metadata["z"]["decimation_factor"]
                        )
                        z_decimation_factor = metadata["z"]["decimation_factor"]

                    unique_z = sorted(df[metadata["z"]["column"]].unique())
                    logger.info(
                        f"[INFO] Z decimation factor {z_decimation_factor} for {len(unique_z)} unique Z"
                    )
                    unique_z = unique_z[::z_decimation_factor]
                    logger.info(f"[INFO] {len(unique_z)} unique Z")
                    decimation_factors.append(z_decimation_factor)
                if unique_z:
                    # Filter the dataframe based on decimated x, y, z values
                    df = df[
                        (df[metadata["x"]["column"]].isin(unique_x))
                        & (df[metadata["y"]["column"]].isin(unique_y))
                        & (df[metadata["z"]["column"]].isin(unique_z))
                    ]
                else:
                    # Filter the dataframe based on decimated x, y values
                    df = df[
                        (df[metadata["x"]["column"]].isin(unique_x))
                        & (df[metadata["y"]["column"]].isin(unique_y))
                    ]

            except Exception as ex:
                logger.error(f"[ERR] Decimation setting failed {ex}")
                sys.exit(3)

            logger.info(
                f"[INFO] Decimation factors are:{decimation_factors}; DF size: {df.size}, shape: {df.shape}"
            )
            logger.info(f"[{time_txt}] Getting the coordinates")
            coords = meta_lib.get_coords(df, metadata, verbose=True)
            t0, time_txt = lib.time_it(t0)
            logger.info(f"[{time_txt}] Got the coordinates")

            # Model output as netCDF.
            if "netcdf" in output_types:
                # Initialize a 2D or 3D grid.
                grid = meta_lib.init_grid(coords)
                t0, time_txt = lib.time_it(t0)
                logger.info(f"[{time_txt}] Initialized the grid")

                # Create a grid for each variable.
                var_grid = meta_lib.create_var_grid(df, data_variables, coords, grid)

                t0, time_txt = lib.time_it(t0)
                logger.info(f"[{time_txt}] Created a grid for each variable")

                # Create the Xarray DataFrame.
                xr_df = meta_lib.build_dataframe(
                    data_variables, coords, var_grid, metadata
                )
                t0, time_txt = lib.time_it(t0)
                logger.info(f"[{time_txt}] Created the DataFrame")

                # Convert the xr DataFrame to an xr Dataset
                xr_dset = meta_lib.build_dataset(xr_df, coords, metadata)
                t0, time_txt = lib.time_it(t0)
                logger.info(f"[{time_txt}] Converted the DataFrame to Dataset")

                # Output the netCDF file.
                # For the coordinate variables, CF convention requires excluding the _FillValue.
                # So, we have to  explicitly disable it via encoding.
                for _var in xr_dset.coords:
                    xr_dset.coords[_var].encoding["_FillValue"] = None
                message = meta_lib.write_netcdf_file(output, xr_dset, nc_format)
                t0, time_txt = lib.time_it(t0)
                logger.info(f"[{time_txt}] {message}")

                # Get the file size in bytes
                file_size = os.path.getsize(f"{output}.nc")

                # Convert the size to a more readable format (e.g., kB)
                file_size_kb = file_size / 1024

            # Model as GeoCSV.
            if "geocsv" in output_types:
                df = meta_lib.add_aux_coord_columns(df, coords)

                # Write metadata as GeoCSV.
                message = meta_lib.write_geocsv_file(
                    df, params, output, metadata_dict, var_dict
                )
                t0, time_txt = lib.time_it(t0)
                logger.info(f"[{time_txt}] {message}")

    # Metadata outputs, if requested.
    if "metadata" in output_types:
        # Write metadata as JSON.
        vars = var_dict.copy()

        # Make sure the column fields are populated.
        for _var in vars:
            if "column" in vars[_var].keys():
                if not vars[_var]["column"].strip():
                    vars[_var]["column"] = vars[_var]["variable"]

        # What is the z variable?
        z_var = ""
        if "z" in metadata:
            if metadata["z"] is not None:
                try:
                    z_var = metadata["z"]["variable"]
                except Exception as ex:
                    logger.error(f"[ERR] Missing metadata['z']['variable']")
                    sys.exit()
        message = meta_lib.write_json_metadata(
            f"{output}_metadata",
            metadata_dict,
            vars,
            data_variables,
            z_var,
            file_size_kb,
        )
        t0, time_txt = lib.time_it(t0)
        logger.info(f"[{time_txt}] {message}")

        # Write metadata as GeoCSV.
        message = meta_lib.write_geocsv_metadata(
            params, f"{output}_metadata", metadata_dict, vars
        )
        t0, time_txt = lib.time_it(t0)
        logger.info(f"[{time_txt}] {message}")


if __name__ == "__main__":
    main()
