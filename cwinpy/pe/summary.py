import os
from argparse import ArgumentParser
from pathlib import Path
from typing import Union

import numpy as np
from bilby.core.result import Result
from gwpy.plot.colors import GW_OBSERVATORY_COLORS
from matplotlib import pyplot as plt
from scipy.stats import hmean

from ..data import HeterodynedData
from ..parfile import PulsarParameters
from ..plot import Plot
from ..utils import get_psr_name, is_par_file
from .pe import pe_pipeline
from .peutils import UpperLimitTable, optimal_snr, results_odds, set_formats
from .webpage import SCRIPTS_AND_CSS, CWPage, make_html, open_html

PULSAR_HEADER_FORMATS = {
    "F0": {
        "html": r"\(f_{\rm rot}\) (Hz)",
        "ultablename": "F0ROT",
        "formatter": set_formats(name="F0ROT", type="html", dp=2),
    },
    "2F0": {
        "html": r"\(f_{\rm gw}\,[2f_{\rm rot}]\) (Hz)",
        "ultablename": "F0ROT",
        "formatter": lambda x: set_formats(name="F0ROT", type="html", dp=2)(2 * x),
    },
    "F1": {
        "html": r"\(\dot{f}_{\rm rot}\) (Hz/s)",
        "ultablename": "F1ROT",
        "formatter": set_formats(name="F1ROT", type="html", dp=2, scinot=True),
    },
    "DIST": {
        "html": "distance (kpc)",
        "ultablename": "DIST",
        "formatter": set_formats(name="DIST", type="html", dp=1),
    },
    "SDLIM": {
        "html": "\(h_0\) spin-down limit",
        "ultablename": "SDLIM",
        "formatter": set_formats(name="SDLIM", type="html", dp=1, scinot=True),
    },
}

RESULTS_HEADER_FORMATS = {
    "H0": {
        "html": r"\(h_0^{95\%}\) upper limit",
        "htmlshort": r"\(h_0^{{95\%}}\)",
        "ultablename": "H0_{}_95%UL",
        "formatter": set_formats(name="H0", type="html", dp=1, scinot=True),
    },
    "ELL": {
        "html": r"\(\varepsilon^{95\%}\) upper limit",
        "htmlshort": r"\(\varepsilon^{{95\%}}\)",
        "ultablename": "ELL_{}_95%UL",
        "formatter": set_formats(name="ELL", type="html", dp=1, scinot=True),
    },
    "Q22": {
        "html": r"\(Q_{22}^{95\%}\) upper limit (kg m<sup>2</sup>)",
        "htmlshort": r"\(Q_{{22}}^{{95\%}}\) kg m<sup>2</sup>",
        "ultablename": "Q22_{}_95%UL",
        "formatter": set_formats(name="Q22", type="html", dp=1, scinot=True),
    },
    "SDRAT": {
        "html": r"\(h_0^{95\%}\,/\,h_0^{\rm spin-down}\)",
        "htmlshort": r"spin-down ratio \(h_0^{95\%}\,/\,h_0^{\rm sd}\)",
        "ultablename": "SDRAT_{}_95%UL",
        "formatter": set_formats(name="SDRAT", type="html"),
    },
    "C21": {
        "html": r"\(C_{21}^{95\%}\) upper limit",
        "htmlshort": r"\(C_{{21}}^{{95\%}}\)",
        "ultablename": "C21_{}_95%UL",
        "formatter": set_formats(name="C21", type="html", dp=1, scinot=True),
    },
    "C22": {
        "html": r"\(C_{22}^{95\%}\) upper limit",
        "htmlshort": r"\(C_{{22}}^{{95\%}}\)",
        "ultablename": "C22_{}_95%UL",
        "formatter": set_formats(name="C22", type="html", dp=1, scinot=True),
    },
    "SNR": {
        "html": r"Optimal signal-to-noise ratio \(\rho\)",
        "htmlshort": r"\(\rho\)",
        "ultablename": "SNR_{}",
        "formatter": set_formats(name="SNR", type="html", dp=1, sf=2),
    },
    "ODDSSVN": {
        "html": r"\(\log{}_{10} \mathcal{O}\) signal vs. noise",
        "htmlshort": r"\(\log{}_{10} \mathcal{O}_{\rm SvN}\)",
        "ultablename": "ODDSSVN_{}",
        "formatter": set_formats(name="ODDS", type="html", dp=1, sf=2),
    },
    "ODDSCVI": {
        "html": r"\(\log{}_{10} \mathcal{O}\) coherent vs. incoherent",
        "htmlshort": r"\(\log{}_{10} \mathcal{O}_{\rm CvI}\)",
        "ultablename": "ODDSCVI",
        "formatter": set_formats(name="ODDS", type="html", dp=1, sf=2),
    },
}


def pulsar_summary_plots(
    parfile: Union[str, Path, PulsarParameters],
    heterodyneddata: Union[str, dict, HeterodynedData, Path] = None,
    posteriordata: Union[str, dict, Path, Result] = None,
    ulresultstable: UpperLimitTable = None,
    outdir: Union[str, Path] = None,
    outputsuffix: str = None,
    plotformat: str = ".png",
    showindividualparams: bool = False,
    webpage: CWPage = None,
    **kwargs,
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
    webpage: :class:`cwinpy.pe.webpage.CWPage`, dict
        A :class:`~cwinpy.pe.webpage.CWPage` onto which to add the
        plots/tables or a dictionary of pages, where the dictionary keys will
        be treated as the detector names.

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

    if isinstance(ulresultstable, UpperLimitTable):
        if isinstance(webpage, CWPage) and kwargs.get("det", None) is not None:
            tloc = ulresultstable.loc[pname]

            # create table of results for the pulsar
            det = kwargs["det"]  # get detector if passed as kwarg

            # construct table of pulsar information and results
            header = ["Pulsar information", ""]

            psrtable = []
            for key in PULSAR_HEADER_FORMATS:
                tname = PULSAR_HEADER_FORMATS[key]["ultablename"]
                if tname in ulresultstable.columns:
                    psrtable.append(
                        [
                            PULSAR_HEADER_FORMATS[key]["html"],
                            PULSAR_HEADER_FORMATS[key]["formatter"](tloc[tname].value),
                        ]
                    )

            webpage.make_container()  # div to contain tables
            webpage.make_div(_style="padding-top:10px")  # add some extra padding
            webpage.make_div(_class="row")
            webpage.make_div(_class="col")
            webpage.make_table(
                headings=header,
                accordian=False,
                contents=psrtable,
            )
            webpage.end_div()

            resheader = ["Results", ""]
            restable = []
            for key in RESULTS_HEADER_FORMATS:
                if key == "ODDSCVI" and len(det) == 2:
                    # only do CvI odds for multiple detectors
                    continue

                tname = RESULTS_HEADER_FORMATS[key]["ultablename"].format(det)
                if tname in ulresultstable.columns:
                    restable.append(
                        [
                            RESULTS_HEADER_FORMATS[key]["html"],
                            RESULTS_HEADER_FORMATS[key]["formatter"](
                                tloc[tname].value
                                if hasattr(tloc[tname], "value")
                                else tloc[tname]
                            ),
                        ]
                    )

            webpage.make_div(_class="col")
            webpage.make_table(
                headings=resheader,
                accordian=False,
                contents=restable,
            )
            webpage.end_div()
            webpage.end_div()
            webpage.end_div()
            webpage.end_container()
        elif isinstance(webpage, dict):
            for det in webpage:
                pulsar_summary_plots(
                    parfile,
                    ulresultstable=ulresultstable,
                    webpage=webpage[det],
                    det=det,
                )

    if heterodyneddata is not None:
        if isinstance(heterodyneddata, (str, Path, HeterodynedData)):
            if isinstance(heterodyneddata, HeterodynedData):
                het = heterodyneddata
            else:
                het = HeterodynedData.read(heterodyneddata)

            outsuf = "" if outputsuffix is None else f"{outputsuffix}"

            if isinstance(webpage, CWPage):
                webpage.make_div()
                webpage.make_heading("Heterodyned data", anchor="heterodyned-data")

            # plot time series
            hetfig = het.plot(
                which="abs",
                remove_outliers=True,
                color=GW_OBSERVATORY_COLORS.get(outsuf, "k"),
            )
            hetfig.tight_layout()
            filename = f"time_series_plot_{pname}_{outsuf}"
            hetfig.savefig(
                outpath / f"{filename}{plotformat}", dpi=kwargs.get("dpi", 150)
            )
            summaryfiles[filename] = outpath / f"{filename}{plotformat}"
            plt.close()

            if isinstance(webpage, CWPage):
                webpage.make_heading("Time series", hsize=2, anchor="time-series")
                webpage.insert_image(
                    os.path.relpath(summaryfiles[filename], webpage.web_dir), width=1200
                )

            # plot spectrogram
            specfig = het.spectrogram(remove_outliers=True)
            filename = f"spectrogram_plot_{pname}_{outsuf}"
            specfig[-1].savefig(
                outpath / f"{filename}{plotformat}", dpi=kwargs.get("dpi", 150)
            )
            summaryfiles[filename] = outpath / f"{filename}{plotformat}"
            plt.close()

            if isinstance(webpage, CWPage):
                webpage.make_heading("Spectrogram", hsize=2, anchor="spectrogram")
                webpage.insert_image(
                    os.path.relpath(summaryfiles[filename], webpage.web_dir),
                    width=1200,
                )

            # plot spectrum
            sfig = het.power_spectrum(remove_outliers=True, asd=True)
            filename = f"asd_plot_{pname}_{outsuf}"
            sfig[-1].savefig(
                outpath / f"{filename}{plotformat}", dpi=kwargs.get("dpi", 150)
            )
            summaryfiles[filename] = outpath / f"{filename}{plotformat}"
            plt.close()

            if isinstance(webpage, CWPage):
                webpage.make_heading(
                    "Amplitude spectrum", hsize=2, anchor="amplitude-spectrum"
                )
                webpage.insert_image(
                    os.path.relpath(summaryfiles[filename], webpage.web_dir), width=650
                )
                webpage.end_div()
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
                    webpage=webpage[suf],
                    **kwargs,
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
            tplotkwargs = kwargs.copy()

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

            if isinstance(webpage, CWPage):
                # add plots to webpage
                webpage.make_div()
                webpage.make_heading("Posteriors", anchor="posteriors")
                webpage.insert_image(
                    os.path.relpath(summaryfiles[filename], webpage.web_dir)
                )

                if showindividualparams:
                    webpage.make_div()
                    webpage.make_heading(
                        "Individual posteriors", hsize=2, anchor="individual-posteriors"
                    )
                    webpage.make_container()
                    webpage.make_div(_class="row")

            # plot individual parameter marginal posteriors if requested
            if showindividualparams:
                params = plot.parameters  # get all parameter names

                for k, param in enumerate(params):
                    plot = Plot(postdata, parameters=param, plottype="hist", kde=True)
                    plot.plot(hist_kwargs={"bins": tplotkwargs["bins"]})

                    filename = f"posteriors_{pname}_{param}_{outsuf}"
                    plot.savefig(outpath / f"{filename}{plotformat}", dpi=dpi)
                    summaryfiles[filename] = outpath / f"{filename}{plotformat}"
                    plt.close()

                    if isinstance(webpage, CWPage):
                        # add individual posterior plots to webpage in 2 column grid
                        webpage.make_div(_class="col")
                        webpage.add_content(
                            (
                                f"<img src='{os.path.relpath(summaryfiles[filename], webpage.web_dir)}' "
                                f"id='{filename}' alt='No image available' "
                                "style='align-items:center; width:450px; cursor: pointer' "
                                "class='mx-auto d-block'>\n"
                            )
                        )
                        webpage.end_div()

                        if k % 2:
                            webpage.end_div()

                            if k != len(params) - 1:
                                webpage.make_div(_class="row")

            if isinstance(webpage, CWPage):
                if showindividualparams:
                    webpage.end_container()
                    webpage.end_div()

                webpage.end_div()

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
                    webpage=webpage[suf] if isinstance(webpage, dict) else webpage,
                    **kwargs,
                )

                summaryfiles.update(sf)
        else:
            raise TypeError("posteriordata is not the correct type.")

    return summaryfiles


def copy_css_and_js_scripts(webdir: Union[str, Path]):
    """
    Copy CSS and js scripts from the PESummary package to the web directory.

    Adapted from :meth:`~pesummary.core.webpage.main._WebpageGeneration.copy_css_and_js_scripts`.

    Parameters
    ----------
    webdir: str, Path
        The path to the location for the files to be copied.
    """
    import shutil

    import pkg_resources

    files_to_copy = []

    path = Path(pkg_resources.resource_filename("pesummary", "core"))
    webdir = Path(webdir)

    scripts = (path / "js").glob("*.js")
    for i in scripts:
        if str(i) in SCRIPTS_AND_CSS:
            files_to_copy.append([i, webdir / "js" / i.name])

    csss = (path / "css").glob("*.css")
    for i in csss:
        if str(i) in SCRIPTS_AND_CSS:
            files_to_copy.append([i, webdir / "css" / i.name])

    for _dir in ["js", "css"]:
        (webdir / _dir).mkdir(exist_ok=True, parents=True)

    for ff in files_to_copy:
        shutil.copy(ff[0], ff[1])

        # remove offending unneccessary line from grab.js that causes it
        # to break in this use case
        if ff[0].name == "grab.js":
            with open(ff[1], "r") as fp:
                grab = fp.readlines()

            with open(ff[1], "w") as fp:
                for line in grab:
                    if "if ( param == approximant ) {" not in line:
                        if "var approx" in line:
                            line = line.replace("el.innerHTML", "param")

                        fp.write(line)


def generate_power_spectrum(
    heterodyneddata: dict,
    time_average: str = "median",
    freq_average: str = "median",
    asd: bool = False,
) -> Union[dict, dict]:
    """
    Extract the power spectral density at the frequencies of a set of analysed
    pulsars using their heterodyned data products.

    Parameters
    ----------
    heterodyneddata: dict
        The input should be a dictionary as provided by the
        :attr:`~cwinpy.pe.pe.PEDAGRunner.datadict`, i.e., a dictionary key by
        pulsar name, then heterodyned data frequency factor ("1f" or "2f"),
        then a detector name, pointing to a path to some
        :class:`~cwinpy.data.HeterodynedData`.
    time_average: str
        The method of averaging each pulsar's spectrogram over time. The
        default is "median", although "harmonic_mean" may be useful. Allowed
        values are: "median", "mean", "harmonic_mean", "max" or "min".
    freq_average: str
        The method of averaging each pulsar's spectrogram over frequency. The
        default is "median", although "harmonic_mean" may be useful. Allowed
        values are: "median", "mean", "harmonic_mean", "max" or "min".
    asd: bool
        If set to True, output the amplitude spectral density values rather
        than power spectral density values.

    Returns
    -------
    specs: dict
        A dictionary keyed on the detector names, followed by frequency factors
        ("1f" or "2f") with values being 2D arrays containing the frequency and
        power spectral density (from using a median over the frequency band of
        the heterodyned data).
    """

    if not isinstance(heterodyneddata, dict):
        raise TypeError("heterodyneddata must be a dictionary")

    if freq_average.lower() not in [
        "median",
        "mean",
        "harmonic_mean",
        "hmean",
        "max",
        "min",
    ]:
        raise ValueError(
            'freq_average must be one of "median", "mean", "harmonic_mean", "max" or "min"'
        )

    # frequency averaging functions
    favfunc = {
        "mean": np.mean,
        "min": np.min,
        "max": np.max,
        "median": np.median,
        "hmean": hmean,
        "harmonic_mean": hmean,
    }

    spec = {}
    freqs = {}
    for psr in heterodyneddata:
        if not isinstance(heterodyneddata[psr], dict):
            raise ValueError("heterodyneddata values must contain dictionaries")

        for ff in heterodyneddata[psr]:
            # check frequency factors of 1f or 2f
            if ff not in ["1f", "2f"]:
                raise KeyError("key must be either 1f or 2f")

            for det in heterodyneddata[psr][ff]:
                if isinstance(
                    heterodyneddata[psr][ff][det], (str, Path, HeterodynedData)
                ):
                    if isinstance(heterodyneddata[psr][ff][det], HeterodynedData):
                        het = heterodyneddata
                    else:
                        het = HeterodynedData.read(heterodyneddata[psr][ff][det])
                else:
                    raise ValueError("data is not a HeterodynedData object/path")

                if det not in freqs:
                    freqs[det] = {}
                    spec[det] = {}

                if ff not in freqs[det]:
                    freqs[det][ff] = []
                    spec[det][ff] = []

                # get power spectral densities
                _, power = het.power_spectrum(
                    remove_outliers=True,
                    plot=False,
                    average=time_average,
                    asd=asd,
                )
                spec[det][ff].append(favfunc[freq_average.lower()](power))

                # get the frequency
                freqs[det][ff].append(het.par["F0"] * int(ff[0]))

    # convert to arrays and sort by frequency
    specs = {}
    for det in freqs:
        specs[det] = {}
        for ff in freqs[det]:
            specs[det][ff] = np.array(sorted(zip(freqs[det][ff], spec[det][ff])))

    return specs


def plot_segments(segments: dict, outfile: Union[str, Path]):
    """
    Plot the science segments for a set of given detectors.

    Parameters
    ----------
    segments: dict
        A dictionary of segment lists keyed to detector names.
    outfile: str, Path
        A string giving the output filename for the plot.
    """

    # convert lists to arrays
    segs = {det: np.asarray(segments[det]) for det in segments}

    # get observing times from the segment lists
    tot = {det: segs[det][-1, 1] - segs[det][0, 0] for det in segs}
    obs = {det: np.diff(segs[det]).sum() for det in segs}

    # get epoch and end time for plot
    epoch = np.min([segs[det][0, 0] for det in segs])
    endtime = np.max([segs[det][-1, 1] for det in segs])

    fig, ax = plt.subplots(1, 1, figsize=(14, (4 / 3) * len(segs)))

    for i, det in enumerate(segs):
        ax.axhline(i, color=GW_OBSERVATORY_COLORS[det], lw=0.5)
        for row in segs[det]:
            ax.fill_between(
                row - epoch,
                [i - 0.25, i - 0.25],
                [i + 0.25, i + 0.25],
                color=GW_OBSERVATORY_COLORS[det],
                alpha=0.9,
            )

    ax.set_yticks(range(len(segs)))
    ax.set_yticklabels(list(segs.keys()))
    ax.set_ylim([-0.7, len(segs) - 0.3])
    ax.set_xlim([0, endtime - epoch])
    ax.set_xlabel("GPS Time (Epoch {0:d})".format(int(epoch)))

    for i, det in enumerate(segs):
        label = "$T_\\mathrm{{obs}}$ = {0:.1f} d, {1:d}\% duty factor".format(
            obs[det] / 86400.0, int(100 * (obs[det] / tot[det]))
        )
        ax.text(0.5 * (endtime - epoch), 0.34 + i, label, horizontalalignment="center")

    fig.tight_layout()
    fig.savefig(outfile, dpi=150)


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
    upperlimitplot: bool
        Set to enable/disable production of a plot of amplitude upper limits
        as a function of frequency. The default is True.
    showsnr: bool
        Set to calculate and show the optimal matched filter signal-to-noise
        ratio for the recovered maximum a-posteriori waveform. The default is
        False.
    showodds: bool
        Set to calculate and show the log Bayesian odds for the coherent signal
        model vs. noise/incoherent signals. The default is False.
    sortby: str
        Set the parameter on which to sort the table of results. The allowed
        parameters are: 'PSRJ', 'F0', 'F1', 'DIST', 'H0', 'H0SPINDOWN', 'ELL',
        'Q22', and 'ODDS'. When sorting on upper limits, if there are multiple
        detectors, the results from the detector with the most constraining
        limit will be sorted on.
    sortdescending: bool
        By default the table of results will be sorted in ascending order on
        the chosen parameter. Set this argument to True to instead sort in
        descending order.
    """

    if "cli" not in kwargs:
        configfile = kwargs.pop("config")
        outpath = Path(kwargs.pop("outpath"))
        url = kwargs.pop("url")

        showposteriors = kwargs.pop("showposteriors", True)
        showindividualparams = kwargs.pop("showindividualposteriors", False)
        showtimeseries = kwargs.pop("showtimeseries", True)

        pulsars = kwargs.pop("pulsar", None)
        if isinstance(pulsars, str):
            pulsars = [pulsars]

        upperlimitplot = kwargs.pop("upperlimitplot", True)
        showsnr = kwargs.pop("showsnr", False)
        showodds = kwargs.pop("showodds", False)

        sortby = kwargs.pop("sortby", "PSRJ")
        sortdes = kwargs.pop("sortdescending", False)
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
            "--disable-upper-limit-plot",
            action="store_true",
            default=False,
            help=(
                "Set this flag to disable production of a plot of amplitude "
                "upper limits as a function of frequency."
            ),
        )
        parser.add_argument(
            "--show-snr",
            action="store_true",
            default=False,
            help=(
                "Set this flag to calculate and show the optimal "
                "matched-filter signal-to-noise ratio for the recovered "
                "maximum a-posteriori waveform."
            ),
        )
        parser.add_argument(
            "--show-odds",
            action="store_true",
            default=False,
            help=(
                "Set this flag to calculate and show the log "
                "Bayesian odds for the coherent signal model vs. "
                "noise/incoherent signals."
            ),
        )
        parser.add_argument(
            "--sort-by",
            default="PSRJ",
            help=(
                "Set the parameter by which to sort the table of results. The "
                "default will be '%(default)s'. The allowed parameters are: "
                "'PSRJ', 'F0', 'F1', 'DIST', 'H0', 'SDLIM' (h0 spin-down "
                "limit), 'SDRAT' (spin-down ratio), 'ELL', 'Q22', 'SNR', and "
                "'ODDS'. When sorting on upper limits, if there are multiple "
                "detectors, the results from the detector with the most "
                "constraining limit will be sorted on."
            ),
        )
        parser.add_argument(
            "--sort-descending",
            action="store_true",
            default=False,
            help=(
                "By default the table of results will be sorted in ascending "
                "order on the chosen parameter. Set this flag to instead sort "
                "in descending order."
            ),
        )

        args = parser.parse_args()
        configfile = args.config
        outpath = Path(args.outpath)
        url = args.url

        showposteriors = not args.disable_posteriors
        showtimeseries = not args.disable_timeseries
        showindividualparams = args.enable_individual_posteriors

        pulsars = args.pulsars

        upperlimitplot = not args.disable_upper_limit_plot
        showsnr = args.show_snr
        showodds = args.show_odds

        sortby = args.sort_by
        sortdes = args.sort_descending

    # make the output directory
    outpath.mkdir(parents=True, exist_ok=True)

    # extract run information from configuration file
    pipeline_data = pe_pipeline(config=configfile, build=False)

    # get table of upper limits
    ultable = UpperLimitTable(
        resdir=pipeline_data.resultsbase,
        includesdlim=True,
        includeell=True,
        includeq22=True,
    )

    if upperlimitplot:
        # get power spectral densities
        asds = generate_power_spectrum(
            pipeline_data.datadict,
            time_average="mean",
            asd=True,
        )
    else:
        asds = None

    if showsnr:
        # switch frequency factor and detector in datadict
        datadicts = {psr: {} for psr in ultable["PSRJ"]}
        for psr, psrddict in pipeline_data.datadict.items():
            for ff in psrddict:
                for det in psrddict[ff]:
                    if det not in datadicts[psr]:
                        datadicts[psr].update({det: {}})

                    datadicts[psr][det][ff] = psrddict[ff][det]

        # get matched filter signal-to-noise ratios
        snrs = optimal_snr(pipeline_data.resultsfiles, datadicts)

        # add SNRs into the results table
        snrdets = list(list(snrs.values())[0].keys())
        snrcols = {f"SNR_{d}": [] for d in snrdets}
        for p in ultable["PSRJ"]:
            for d in snrdets:
                snrcols[f"SNR_{d}"].append(snrs[p][d])

        for snrc in snrcols:
            ultable[snrc] = snrcols[snrc]

    if showodds:
        oddsdets = []
        oddscols = {}
        for dets in pipeline_data.detcomb:
            if len(dets) == 1:
                cname = RESULTS_HEADER_FORMATS["ODDSSVN"]["ultablename"].format(dets[0])
                oddscols[cname] = []

                oddsdets.append(dets[0])
                # get single detector signal vs noise odds
                sodds = results_odds(
                    pipeline_data.resultsfiles,
                    oddstype="svn",
                    scale="log10",
                    det=dets[0],
                )

                for psr in ultable["PSRJ"]:
                    oddscols[cname].append(sodds[psr])
            else:
                # get multi-detector coherent vs incoherent odds
                codds = results_odds(
                    pipeline_data.resultsfiles, oddstype="cvi", scale="log10"
                )

                cname = RESULTS_HEADER_FORMATS["ODDSCVI"]["ultablename"]
                oddscols[cname] = [codds[psr] for psr in ultable["PSRJ"]]

        # add odds values into upper limit table
        for ocol in oddscols:
            ultable[ocol] = oddscols[ocol]

    # sort the table
    if sortby.upper() in ultable.colnames:
        ultable.sort(keys=sortby.upper(), reverse=sortdes)
    else:
        # get columns containing the given sort parameter
        scols = [cname for cname in ultable.colnames if sortby.upper() in cname]

        if not scols:
            raise ValueError(f"No results columns found for the parameter '{sortby}'.")

        # get column with most constraining (minimum value)
        mcol = scols[
            np.argmin(
                [
                    ultable[c].min().value
                    if hasattr(ultable[c], "value")
                    else ultable[c].min()
                    for c in scols
                ]
            )
        ]
        ultable.sort(keys=mcol, reverse=sortdes)

    # html table showing all results
    allresultstable = {}
    htmldir = outpath / "html"
    htmldir.mkdir(parents=True, exist_ok=True)
    pages = {}

    # get the detectors with results available
    dets = list(list(pipeline_data.resultsfiles.items())[0][1].keys())
    ldet = dets[np.argmax([len(d) for d in dets])]

    # generate pages for each pulsar
    for psr in ultable["PSRJ"]:
        if pulsars is not None and psr not in pulsars:
            continue

        # row containing this pulsar's results
        psrlink = f'<a href="../html/{psr}_{ldet}.html">{psr}</a>'
        allresultstable[psrlink] = {}

        # create webpage
        pages[psr] = {}
        for det in dets:
            # make the initial page
            htmlpage = make_html(outpath, psr, det, title=f"PSR {psr} ({det})")
            purl = f"{url}/html/{psr}_{det}.html"
            pages[psr][det] = open_html(
                outpath / "html",
                purl,
                htmldir / htmlpage.stem,
                label=f"{psr}_{det}",
            )

            pages[psr][det].make_heading(f"PSR {psr}", hsubtext=f"{det}")

        # add required results into a table for the main page
        # show upper limit results
        tloc = ultable.loc[psr]

        # show pulsar parameters
        for par in ["2F0", "F1", "DIST", "SDLIM"]:
            hname = PULSAR_HEADER_FORMATS[par]["html"]
            tname = PULSAR_HEADER_FORMATS[par]["ultablename"]

            quant = True if hasattr(tloc[tname], "value") else False
            tvalue = tloc[tname].value if quant else tloc[tname]
            rvalue = PULSAR_HEADER_FORMATS[par]["formatter"](tvalue)
            allresultstable[psrlink][hname] = rvalue

        # show upper limits
        for amp in ["H0", "C21", "C22", "ELL", "Q22", "SDRAT"]:
            for det in dets:
                tname = f"{amp}_{det}_95%UL"

                if tname in ultable.colnames:
                    hname = RESULTS_HEADER_FORMATS[amp]["htmlshort"]

                    if hname not in allresultstable[psrlink]:
                        allresultstable[psrlink][hname] = {}

                    quant = True if hasattr(tloc[tname], "value") else False
                    tvalue = tloc[tname].value if quant else tloc[tname]
                    rvalue = RESULTS_HEADER_FORMATS[amp]["formatter"](tvalue)

                    if tvalue == (
                        ultable[tname].min().value if quant else ultable[tname].min()
                    ):
                        # highlight minimum value (i.e., smallest upper limits)
                        rvalue = f"<b>{rvalue}</b>"

                    allresultstable[psrlink][hname][det] = rvalue

        # show odds if present in the table
        for det in dets:
            tname = f"ODDSSVN_{det}"

            if tname in ultable.colnames:
                hname = RESULTS_HEADER_FORMATS["ODDSSVN"]["htmlshort"]

                if hname not in allresultstable[psrlink]:
                    allresultstable[psrlink][hname] = {}

                tvalue = tloc[tname]
                rvalue = RESULTS_HEADER_FORMATS["ODDSSVN"]["formatter"](tvalue)

                # highlight largest odds
                if tvalue == ultable[tname].max():
                    rvalue = f"<b>{rvalue}</b>"

                allresultstable[psrlink][hname][det] = rvalue

        if "ODDSCVI" in ultable.colnames:
            hname = RESULTS_HEADER_FORMATS["ODDSCVI"]["htmlshort"]

            tvalue = tloc["ODDSCVI"]
            rvalue = RESULTS_HEADER_FORMATS["ODDSCVI"]["formatter"](tvalue)

            # highlight largest odds
            if tvalue == ultable["ODDSCVI"].max():
                rvalue = f"<b>{rvalue}</b>"

            allresultstable[psrlink][hname] = rvalue

        # add results tables to each page
        _ = pulsar_summary_plots(
            pipeline_data.pulsardict[psr],
            ulresultstable=ultable,
            webpage=pages[psr],
        )

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
                showindividualparams=showindividualparams,
                webpage=pages[psr],
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
                    webpage=pages[psr],
                )

        if not timeseriesplots:
            raise ValueError(
                "None of the specified pulsars were found in the analysis."
            )

    # create home page
    _ = make_html(outpath, "home", title="Home")
    homeurl = f"{url}/home.html"
    homepage = open_html(outpath / "html", homeurl, "home", "home")

    # create a plot of segment use (just use the first pulsar's data)
    hetdata = list(list(pipeline_data.datadict.values())[0].values())[0]
    segs = {
        det: HeterodynedData(hetdata[det], remove_outliers=False).segment_list()
        for det in hetdata
    }

    # get total observation time for each detector
    totobs = {det: np.diff(segs[det]).sum() for det in segs}

    segmentsplot = outpath / "html" / "segment_plot.png"
    plot_segments(segs, segmentsplot)
    homepage.make_heading("Data segments", anchor="data-segments")
    homepage.insert_image(segmentsplot.name, width=1200)

    ampulpages = {}
    ampt = {
        "H0": "\(h_0\)",
        "C21": "\(C_{21}\)",
        "C22": "\(C_{22}\)",
        "ELL": "Ellipticity",
    }

    # add the results table
    homepage.make_heading("Table of results", anchor="table-of-results")
    homepage.make_results_table(contents=allresultstable)

    # create upper limits plots
    if upperlimitplot:
        ulplotdir = outpath / "ulplots"
        ulplotdir.mkdir(parents=True, exist_ok=True)

        ulplots = {}
        for amp in ampt:
            for det in dets:
                p = RESULTS_HEADER_FORMATS[amp]["ultablename"].format(det)

                if p in ultable.colnames:
                    if amp not in ulplots:
                        ulplots[amp] = {}
                        ampulpages[amp] = {}

                    ampultitle = f"{amp}_{det}"
                    _ = make_html(
                        outpath, ampultitle, title=f"{ampt[amp]} upper limits"
                    )
                    amphomeurl = f"{url}/{ampultitle}.html"
                    ampulpage = open_html(
                        outpath / "html", amphomeurl, ampultitle, ampultitle
                    )
                    ampulpage.make_heading(
                        f"{ampt[amp]} upper limits",
                        hsubtext=f"{det}",
                        anchor=f"{amp.lower()}-upper-limits",
                    )

                    # try getting ASDs to include on plots
                    asd = None
                    tobs = None
                    if amp != "ELL":
                        try:
                            fkey = "2f" if amp in ["H0", "C22"] else "1f"
                            asd = (
                                [asds[det][fkey]]
                                if len(det) == 2
                                else [asds[d][fkey] for d in asds]
                            )
                            tobs = (
                                [totobs[det]]
                                if len(det) == 2
                                else [totobs[d] for d in totobs]
                            )
                        except KeyError:
                            pass

                    p = RESULTS_HEADER_FORMATS[amp]["ultablename"].format(det)
                    fig = ultable.plot(
                        p,
                        histogram=True,
                        asds=asd,
                        showq22=True if amp == "ELL" else False,
                        showtau=True if amp == "ELL" else False,
                        tobs=tobs,
                        asdkwargs={
                            "color": GW_OBSERVATORY_COLORS[det]
                            if det in GW_OBSERVATORY_COLORS
                            else "grey",
                            "alpha": 0.5,
                            "linewidth": 5,
                        },
                    )

                    ulplotfile = ulplotdir / f"{amp}_{det}.png"
                    fig.savefig(ulplotfile, dpi=200)
                    ulplots[amp][det] = ulplotfile

                    plt.close()

                    ampulpage.insert_image(
                        os.path.relpath(ulplotfile, ampulpage.web_dir), width=1200
                    )
                    ampulpages[amp][det] = ampulpage

    # create homepage navbar
    homelinks = {
        "Pulsars": {psr: {det: f"{psr}_{det}.html" for det in dets} for psr in pages}
    }
    if ampulpages:
        homelinks["Upper limit plots"] = {
            ampt[amp]: {d: f"{amp}_{d}.html" for d in ampulpages[amp]}
            for amp in ampulpages
        }
    homepage.make_navbar(homelinks, search=False)

    homepage.close()

    # copy required CSS and js files
    copy_css_and_js_scripts(outpath)

    # add nav bars and close results pages
    if ampulpages:
        pages.update(ampulpages)

    links = {
        "Home": "home.html",
        "Pulsars": homelinks["Pulsars"],
    }

    if ampulpages:
        links["Upper limit plots"] = homelinks["Upper limit plots"]

    for psramp in pages:
        curlinks = links.copy()

        if psramp not in ampt:
            # individual detector pages
            curlinks["Detector"] = {
                det: f"{psramp}_{det}.html" for det in pages[psramp]
            }

        for det, p in pages[psramp].items():
            if det in GW_OBSERVATORY_COLORS:
                # set navbar colour based on the observatory
                nbc = GW_OBSERVATORY_COLORS[det]
            else:
                nbc = "#777777"

            # nav bar
            p.make_navbar(curlinks, background_color=nbc)

            p.close()

    return ultable


def generate_summary_pages_cli(**kwargs):  # pragma: no cover
    """
    Entry point to ``cwinpy_generate_summary_pages`` script. This just calls
    :func:`~cwinpy.pe.summary.generate_summary_pages`.
    """

    kwargs["cli"] = True
    generate_summary_pages(**kwargs)
