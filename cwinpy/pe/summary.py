from argparse import ArgumentParser
from pathlib import Path
from typing import Union

from bilby.core.result import Result
from matplotlib import pyplot as plt

from ..data import HeterodynedData
from ..parfile import PulsarParameters
from ..plot import Plot
from ..utils import get_psr_name, is_par_file
from .pe import pe_pipeline
from .peutils import (  # , optimal_snr, read_in_result_wrapper, results_odds
    UpperLimitTable,
)


def pulsar_summary_plots(
    parfile: Union[str, Path, PulsarParameters],
    heterodyneddata: Union[str, dict, HeterodynedData, Path] = None,
    posteriordata: Union[str, dict, Path, Result] = None,
    ulresultstable: UpperLimitTable = None,
    oddstable: dict = None,
    snrtable: dict = None,
    outdir: Union[str, Path] = None,
    outputsuffix: str = None,
    plotformat: str = ".png",
    showindividualparams: bool = False,
    **plotkwargs,
):
    """
    Produce plots summarising the information from a pulsar analysis.

    Parameters
    ----------
    parfile: :class:`cwinpy.parfile.PulsarParameters`, str
        The pulsar parameters or a file containing pulsar the pulsar
        parameters.
    heterodyneddata: :class:`cwinpy.data.HeterodynedData`, str, dict
        A :class:`~cwinpy.data.HeterodynedData` object, path to a file
        containing heterodyned data, or a dictionary to multiple
        :class:`~cwinpy.data.HeterodynedData` objects (or file paths). If this
        is given, summary time series and spectrogram plots will be created.
        The dictionary keys will be treated as the data's names, e.g., detector
        names, and used as a suffix for the output plot file name if one is not
        given.
    posteriordata: :class:`bilby.core.results.Result`, str, dict
        A :class:`~bilby.core.result.Result` object, path to a results file, or
        dictionary containing multiple :class:`~bilby.core.result.Result`
        objects (or file paths). If this is given, posterior plots will be
        created. The dictionary keys will be treated as the data's names, e.g.,
        detector names, and used as a suffix for the output plot file name if
        one is not given.
    ulresultstable: UpperLimitTable
        A table of upper limits from which limits for the given pulsar can be
        extracted. If given, this will be included in a summary table for that
        pulsar.
    oddstable: dict
        A dictionary of odds results from which the value for the given pulsar
        can be extracted. If given, this will be included in a summary table for
        that pulsar.
    snrtable: dict
        A dictionary of SNR values from which the value for the given pulsar
        can be extracted. If given, this will be included in a summary table
        for that pulsar.
    outdir: str, Path
        The output directory into which to save the plots/summary table. If not
        given, the current working directory will be used.
    outputsuffix: str
        An suffix to append to the output files names. Default is None.
    plotformat: str
        The file format with which the save the figures. The default is ".png".
    showindividualparams: bool
        Set to true to produce posterior plots for all individual parameters as
        well as the joint posterior plot. Default is False.

    Returns
    -------
    summaryfiles: dict
        A dictionary containing to paths to all the summary files.
    """

    if is_par_file(parfile):
        par = PulsarParameters(parfile)
    elif isinstance(parfile, PulsarParameters):
        par = parfile
    else:
        raise ValueError(f"Supplied pulsar .par file '{parfile}' is invalid.")

    if outdir is None:
        outpath = Path.cwd()
    else:
        outpath = Path(outdir)
        outpath.mkdir(parents=True, exist_ok=True)

    pname = get_psr_name(par)

    summaryfiles = {}

    if heterodyneddata is not None:
        if isinstance(heterodyneddata, (str, Path, HeterodynedData)):
            if isinstance(heterodyneddata, HeterodynedData):
                het = heterodyneddata
            else:
                het = HeterodynedData.read(heterodyneddata)

            outsuf = "" if outputsuffix is None else f"{outputsuffix}"

            # plot time series
            hetfig = het.plot(which="abs", remove_outliers=True)
            hetfig.tight_layout()
            filename = f"time_series_plot_{pname}_{outsuf}"
            hetfig.savefig(
                outpath / f"{filename}{plotformat}", dpi=plotkwargs.get("dpi", 150)
            )
            summaryfiles[filename] = outpath / f"{filename}{plotformat}"
            plt.close()

            # plot spectrogram
            specfig = het.spectrogram(remove_outliers=True)
            filename = f"spectrogram_plot_{pname}_{outsuf}"
            specfig[-1].savefig(
                outpath / f"{filename}{plotformat}", dpi=plotkwargs.get("dpi", 150)
            )
            summaryfiles[filename] = outpath / f"{filename}{plotformat}"
            plt.close()

            # plot spectrum
            sfig = het.power_spectrum(remove_outliers=True, asd=True)
            filename = f"asd_plot_{pname}_{outsuf}"
            sfig[-1].savefig(
                outpath / f"{filename}{plotformat}", dpi=plotkwargs.get("dpi", 150)
            )
            summaryfiles[filename] = outpath / f"{filename}{plotformat}"
            plt.close()
        elif isinstance(heterodyneddata, dict):
            for suf in heterodyneddata:
                if outputsuffix is None:
                    outsuf = suf
                else:
                    outsuf = f"{outputsuffix}_{suf}"

                sf = pulsar_summary_plots(
                    par,
                    heterodyneddata=heterodyneddata[suf],
                    outputsuffix=outsuf,
                    outdir=outdir,
                    plotformat=plotformat,
                    **plotkwargs,
                )

                summaryfiles.update(sf)
        else:
            raise TypeError("heterodyneddata is not the correct type.")

    if posteriordata is not None:
        if isinstance(posteriordata, (str, Path, Result)):
            postdata = posteriordata

            if outputsuffix is not None:
                postdata = {outputsuffix: postdata}

            # copy of plotting kwargs
            tplotkwargs = plotkwargs.copy()

            # get output dpi
            dpi = tplotkwargs.pop("dpi", 150)

            # set default number of histogram bins for plots
            if "bins" not in tplotkwargs:
                tplotkwargs["bins"] = 30

            # plot posteriors for all parameters
            plot = Plot(postdata, plottype="corner")
            plot.plot(**tplotkwargs)

            outsuf = "" if outputsuffix is None else f"{outputsuffix}"
            filename = f"posteriors_{pname}_{outsuf}"
            plot.savefig(outpath / f"{filename}{plotformat}", dpi=dpi)
            summaryfiles[filename] = outpath / f"{filename}{plotformat}"
            plt.close()

            # plot individual parameter marginal posteriors if requested
            if showindividualparams:
                params = plot.parameters  # get all parameter names

                for param in params:
                    plot = Plot(postdata, parameters=param, plottype="hist", kde=True)
                    plot.plot(hist_kwargs={"bins": tplotkwargs["bins"]})

                    filename = f"posteriors_{pname}_{param}_{outsuf}"
                    plot.savefig(outpath / f"{filename}{plotformat}", dpi=dpi)
                    summaryfiles[filename] = outpath / f"{filename}{plotformat}"
                    plt.close()
        elif isinstance(posteriordata, dict):
            for suf in posteriordata:
                if outputsuffix is None:
                    outsuf = suf
                else:
                    outsuf = f"{outputsuffix}_{suf}"

                sf = pulsar_summary_plots(
                    par,
                    posteriordata=posteriordata[suf],
                    outputsuffix=outsuf,
                    outdir=outdir,
                    plotformat=plotformat,
                    showindividualparams=showindividualparams,
                    **plotkwargs,
                )

                summaryfiles.update(sf)
        else:
            raise TypeError("posteriordata is not the correct type.")

    return summaryfiles


def generate_summary_pages(**kwargs):
    """
    Generate summary webpages following a ``cwinpy_knope_pipeline`` analysis
    (see :func:`~cwinpy.knope.knope_pipeline`).

    Parameters
    ----------
    config: str, Path
        The configuration file used for the ``cwinpy_knope_pipeline`` analysis.
    outpath: str, Path
        The output path for the summary results webpages and plots.
    url: str
        The URL from which the summary results pages will be accessed.
    showposteriors: bool
        Set to enable/disable production of plots showing the joint posteriors
        for all parameters. The default is True.
    showindividualposteriors: bool
        Set to enable/disable production of plots showing the marginal
        posteriors for each individual parameter. The default is False.
    showtimeseries: bool
        Set to enable/disable production of plots showing the heterodyned time
        series data (and spectral representations). The default is True.
    pulsars: list, str
        A list of pulsars to show. By default all pulsars analysed will be
        shown.
    upperlimittable: bool
        Set to enable/disable production of a table of amplitude upper limits.
        The default is True.
    upperlimitplot: bool
        Set to enable/disable production of a plot of amplitude upper limits
        as a function of frequency. The default is True.
    """

    if "cli" not in kwargs:
        configfile = kwargs.pop("config")
        outpath = Path(kwargs.pop("outpath"))
        # url = kwargs.pop("url")

        showposteriors = kwargs.pop("showposteriors", True)
        showindividualparams = kwargs.pop("showindividualposteriors", False)
        showtimeseries = kwargs.pop("showtimeseries", True)

        pulsars = kwargs.pop("pulsar", None)
        if isinstance(pulsars, str):
            pulsars = [pulsars]

        upperlimittable = kwargs.pop("upperlimittable", True)
        # upperlimitplot = kwargs.pop("upperlimitplot", True)
    else:  # pragma: no cover
        parser = ArgumentParser(
            description=(
                "A script to create results summary pages from a "
                "cwinpy_knope_pipeline analysis."
            )
        )
        parser.add_argument(
            "config",
            help=("The configuration file from the cwinpy_knope_pipeline analysis."),
        )
        parser.add_argument(
            "--outpath",
            "-o",
            help=("The output path for the summary results webpages and plots."),
            required=True,
        )
        parser.add_argument(
            "--url",
            "-u",
            help=("The URL from which the summary results pages will be accessed."),
            required=True,
        )
        parser.add_argument(
            "--pulsars",
            "-p",
            nargs="+",
            help=(
                "Provide the pulsars for which to produces summary results. "
                "By default, all pulsars from the analysis will be used."
            ),
        )
        parser.add_argument(
            "--disable-posteriors",
            action="store_true",
            default=False,
            help="Set this flag to disable production of posterior plots.",
        )
        parser.add_argument(
            "--enable-individual-posteriors",
            action="store_true",
            default=False,
            help=(
                "Set this flag to enable to produciton of marginal posterior "
                "plots for each individual parameters."
            ),
        )
        parser.add_argument(
            "--disable-timeseries",
            action="store_true",
            default=False,
            help="Set this flag to disable production of time series plots.",
        )
        parser.add_argument(
            "--disable-upper-limit-table",
            action="store_true",
            default=False,
            help=(
                "Set this flag to disable production of a table of amplitude "
                "upper limits."
            ),
        )
        parser.add_argument(
            "--disable-upper-limit-plot",
            action="store_true",
            default=False,
            help=(
                "Set this flag to disable production of a plot of amplitude "
                "upper limits as a function of frequency."
            ),
        )

        args = parser.parse_args()
        configfile = args.config
        outpath = Path(args.outpath)
        # url = args.url

        showposteriors = not args.disable_posteriors
        showtimeseries = not args.disable_timeseries
        showindividualparams = args.enable_individual_posteriors

        pulsars = args.pulsars

        upperlimittable = not args.disable_upper_limit_table
        # upperlimitplot = not args.disable_upper_limit_plot

    # make the output directory
    outpath.mkdir(parents=True, exist_ok=True)

    # extract run information from configuration file
    pipeline_data = pe_pipeline(config=configfile, build=False)

    if upperlimittable:
        # try and get base directory for results:
        ultable = UpperLimitTable(resdir=pipeline_data.resultsbase)
    else:
        ultable = None

    # plot posteriors
    if showposteriors:
        posteriorplots = {}

        if not pipeline_data.resultsfiles:
            raise ValueError("No results files given in pipeline configuration!")

        posteriorplotdir = outpath / "posterior_plots"

        for psr in pipeline_data.resultsfiles:
            if pulsars is not None and psr not in pulsars:
                continue

            posteriorplots[psr] = pulsar_summary_plots(
                pipeline_data.pulsardict[psr],
                posteriordata=pipeline_data.resultsfiles[psr],
                outdir=posteriorplotdir / psr,
                ulresultstable=ultable,
                showindividualparams=showindividualparams,
            )

        if not posteriorplots:
            raise ValueError(
                "None of the specified pulsars were found in the analysis."
            )

    if showtimeseries:
        timeseriesplots = {}

        if not pipeline_data.datadict:
            raise ValueError(
                "No heterodyned data files given in pipeline configuration!"
            )

        timeseriesplotdir = outpath / "timeseries_plots"

        for psr in pipeline_data.datadict:
            if pulsars is not None and psr not in pulsars:
                continue

            timeseriesplots[psr] = {}
            for freqfactor in pipeline_data.datadict[psr]:
                timeseriesplots[psr][freqfactor] = pulsar_summary_plots(
                    pipeline_data.pulsardict[psr],
                    heterodyneddata=pipeline_data.datadict[psr][freqfactor],
                    outdir=timeseriesplotdir / psr / freqfactor,
                )

        if not timeseriesplots:
            raise ValueError(
                "None of the specified pulsars were found in the analysis."
            )


def generate_summary_pages_cli(**kwargs):  # pragma: no cover
    """
    Entry point to ``cwinpy_generate_summary_pages`` script. This just calls
    :func:`~cwinpy.pe.summary.generate_summary_pages`.
    """

    kwargs["cli"] = True
    generate_summary_pages(**kwargs)
