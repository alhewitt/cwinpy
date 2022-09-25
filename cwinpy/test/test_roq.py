"""
Test script for ROQ usage.
"""

import copy

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from bilby.core.prior import PriorDict, Sine, Uniform
from cwinpy.data import HeterodynedData, MultiHeterodynedData
from cwinpy.parfile import PulsarParameters
from cwinpy.pe.likelihood import TargetedPulsarLikelihood
from cwinpy.pe.roq import GenerateROQ
from cwinpy.utils import logfactorial


def full_log_likelihood(model, data, like="studentst", sigma=1.0):
    """
    Calculate the likelihood for the full data set.
    """

    dd = np.vdot(data, data).real
    mm = np.vdot(model, model).real
    dm = np.vdot(data, model).real

    chisq = (dd - 2.0 * dm + mm) / sigma**2

    if like == "studentst":
        return (
            logfactorial(len(data) - 1)
            - np.log(2.0)
            - len(data) * (np.log(np.pi * chisq))
        )
    else:
        N = len(data) if data.dtype == complex else len(data) / 2
        return -0.5 * chisq - N * np.log(2.0 * np.pi * sigma**2)


class TestGenericModelROQ:
    """
    Test the reduced order quadrature for a generic model function.
    """

    @staticmethod
    def generic_complex_model(t, A=0, phi0=0, m=0, c=0):
        """
        A (complex) sinusoid and a straight line model.
        """

        return A * np.exp(2.0 * np.pi * 1.4 * t * 1j + phi0) + m * t + c

    @staticmethod
    def generic_real_model(t, A=0, phi0=0, m=0, c=0):
        """
        A sinusoid and a straight line model.
        """

        return A * np.sin(2.0 * np.pi * 1.4 * t + phi0) + m * t + c

    @classmethod
    def setup_class(cls):
        # create some complex data using generic_complex_model
        cls.A_true = 1.2
        cls.phi0_true = 2.3
        cls.m_true = 0.7
        cls.c_true = -1.2

        cls.N = 100
        cls.times = np.linspace(0, 5, cls.N)

        cls.comp_model = cls.generic_complex_model(
            cls.times,
            A=cls.A_true,
            phi0=cls.phi0_true,
            m=cls.m_true,
            c=cls.c_true,
        )

        cls.sigma = 1.5

        cls.comp_data = cls.comp_model + (
            np.random.normal(loc=0.0, scale=cls.sigma, size=cls.N)
            + 1j * np.random.normal(loc=0.0, scale=cls.sigma, size=cls.N)
        )

        cls.real_model = cls.generic_real_model(
            cls.times,
            A=cls.A_true,
            phi0=cls.phi0_true,
            m=cls.m_true,
            c=cls.c_true,
        )

        cls.real_data = cls.real_model + np.random.normal(
            loc=0.0, scale=cls.sigma, size=cls.N
        )

        cls.priors = PriorDict()
        cls.priors["A"] = Uniform(0, 10, name="A")
        cls.priors["phi0"] = Uniform(0, 2.0 * np.pi, name="phi0")
        cls.priors["m"] = Uniform(-5, 5, name="m")
        cls.priors["c"] = Uniform(-5, 5, name="c")

    def test_exceptions(self):
        """
        Test exceptions for GenerateROQ class.
        """

        # x-value exceptions
        with pytest.raises(TypeError):
            GenerateROQ(self.real_data, "sdjf", self.priors)

        with pytest.raises(ValueError):
            GenerateROQ(self.real_data, np.array([[1.2, 2.3], [2.3, 4.5]]), self.priors)

        with pytest.raises(TypeError):
            GenerateROQ(self.real_data, ["1", "2"], self.priors)

        # data exceptions
        with pytest.raises(TypeError):
            GenerateROQ(1.2, self.times, self.priors)

        with pytest.raises(ValueError):
            GenerateROQ([[1.0, 2.0], [3.0, 4.0]], self.times, self.priors)

        with pytest.raises(TypeError):
            GenerateROQ(["1", "2"], self.times, self.priors)

        with pytest.raises(ValueError):
            GenerateROQ([1.0, 2.0], self.times, self.priors)

        with pytest.raises(TypeError):
            GenerateROQ(self.real_data, self.times, self.priors, sigma="blah")

        with pytest.raises(ValueError):
            GenerateROQ(self.real_data, self.times, self.priors, sigma=[-1.0, -1.0])

        # prior exceptions
        with pytest.raises(TypeError):
            GenerateROQ(self.real_data, self.times, 1.0)

        # model exceptions
        with pytest.raises(TypeError):
            GenerateROQ(self.real_data, self.times, self.priors, model=1.0)

    def test_real_model_roq(self):
        ntraining = 500

        # generate ROQ
        roq = GenerateROQ(
            self.real_data,
            self.times,
            self.priors,
            model=self.generic_real_model,
            store_training_data=True,
            ntraining=ntraining,
            sigma=self.sigma,
        )

        assert roq.training_data.shape == (ntraining, self.N)
        assert roq.nbases > 0
        assert roq.nbases2 > 0

        # check likelihood calculation
        Ntests = 100

        for _ in range(Ntests):
            # draw values from prior
            values = self.priors.sample()

            # students-t likelihood
            ll = roq.log_likelihood(**values)
            fullll = full_log_likelihood(
                self.generic_real_model(self.times, **values), self.real_data
            )

            assert np.abs(ll - fullll) < 1e-6

            # Gaussian likelihood
            ll = roq.log_likelihood(**values, likelihood="gaussian")
            fullll = full_log_likelihood(
                self.generic_real_model(self.times, **values),
                self.real_data,
                like="gaussian",
                sigma=self.sigma,
            )

            assert np.abs(ll - fullll) < 1e-6

    def test_complex_model_roq(self):
        ntraining = 500

        # generate ROQ
        roq = GenerateROQ(
            self.comp_data,
            self.times,
            self.priors,
            model=self.generic_complex_model,
            store_training_data=True,
            ntraining=ntraining,
            sigma=self.sigma,
        )

        assert roq.training_data.shape == (ntraining, self.N)
        assert roq.nbases_real > 0
        assert roq.nbases_imag > 0
        assert roq.nbases2 > 0

        # check likelihood calculation
        Ntests = 100

        for _ in range(Ntests):
            # draw values from prior
            values = self.priors.sample()

            # students-t likelihood
            ll = roq.log_likelihood(**values)
            fullll = full_log_likelihood(
                self.generic_complex_model(self.times, **values), self.comp_data
            )

            assert np.abs(ll - fullll) < 1e-6

            # Gaussian likelihood
            ll = roq.log_likelihood(**values, likelihood="gaussian")
            fullll = full_log_likelihood(
                self.generic_complex_model(self.times, **values),
                self.comp_data,
                like="gaussian",
                sigma=self.sigma,
            )

            assert np.abs(ll - fullll) < 1e-6


class TestHeterodynedCWModelROQ:
    """
    Test the reduced order quadrature for a heterodyned CW signal model
    function.
    """

    @classmethod
    def setup_class(cls):
        # create a pulsar
        cls.pulsar = PulsarParameters()
        cls.pulsar["PSRJ"] = "J0123-0123"

        coords = SkyCoord(ra="01:23:00.0", dec="01:23:00.0", unit=("hourangle", "deg"))
        cls.pulsar["RAJ"] = coords.ra.rad
        cls.pulsar["DECJ"] = coords.dec.rad
        cls.pulsar["F"] = [123.456]
        cls.pulsar["H0"] = 9.2e-24
        cls.pulsar["IOTA"] = 0.789
        cls.pulsar["PSI"] = 1.1010101
        cls.pulsar["PHI0"] = 2.87654

        # generate some fake data
        cls.times = np.arange(1000000000, 1000086400, 60)
        cls.detector = "H1"
        cls.het = HeterodynedData(
            times=cls.times,
            par=cls.pulsar,
            injpar=cls.pulsar,
            fakeasd=cls.detector,
            inject=True,
            bbminlength=len(cls.times),  # forced to a single chunk
        )

        # fake multi-detector data with multiple chunks
        het1chunked = HeterodynedData(
            times=cls.times,
            par=cls.pulsar,
            injpar=cls.pulsar,
            fakeasd="H1",
            inject=True,
            bbmaxlength=int(len(cls.times) / 2),  # forced into multiple chunks
        )

        het2chunked = HeterodynedData(
            times=cls.times,
            par=cls.pulsar,
            injpar=cls.pulsar,
            fakeasd="H1",
            inject=True,
            bbmaxlength=int(len(cls.times) / 2),  # forced into multiple chunks
        )

        cls.multihet = MultiHeterodynedData({"H1": het1chunked, "L1": het2chunked})

        # set the prior
        cls.priors = PriorDict()
        cls.priors["h0"] = Uniform(0, 1e-22, name="h0")
        cls.priors["phi0"] = Uniform(0, np.pi, name="phi0")
        cls.priors["psi"] = Uniform(0, np.pi / 2, name="psi")
        cls.priors["iota"] = Sine(name="iota")

    def test_builtin_heterodyned_cw_model(self):
        ntraining = 500

        # generate ROQ
        roq = GenerateROQ(
            self.het.data,
            self.het.times.value,
            self.priors,
            par=self.het.par,
            det=self.het.detector,
            ntraining=ntraining,
            sigma=self.het.stds[0],
        )

        # there should only be two real/imag basis vectors
        assert roq.nbases_real == 2 and roq.nbases_imag == 2
        assert roq.nbases2 == 3

        # check likelihood calculation
        Ntests = 100

        ll = np.zeros(Ntests)
        fullll = np.zeros(Ntests)
        llg = np.zeros(Ntests)
        fullllg = np.zeros(Ntests)

        for i in range(Ntests):
            # draw values from prior
            parcopy = copy.deepcopy(self.pulsar)
            for key, value in self.priors.sample().items():
                parcopy[key] = value

            model = roq.model(
                newpar=parcopy,
                outputampcoeffs=False,
                updateSSB=True,
                updateBSB=True,
                updateglphase=True,
                freqfactor=2,
            )

            # students-t likelihood
            ll[i] = roq.log_likelihood(par=parcopy)
            fullll[i] = full_log_likelihood(model, self.het.data)

            # Gaussian likelihood
            llg[i] = roq.log_likelihood(par=parcopy, likelihood="gaussian")
            fullllg[i] = full_log_likelihood(
                model,
                self.het.data,
                like="gaussian",
                sigma=self.het.stds[0],
            )

        assert np.all(
            np.abs(np.exp(ll - ll.max()) - np.exp(fullll - fullll.max())) < 1e-3
        )
        assert np.all(
            np.abs(np.exp(llg - llg.max()) - np.exp(fullllg - fullllg.max())) < 1e-3
        )

    def test_studentst_likelihood(self):
        ntraining = 500

        # original likelihood
        like_orig = TargetedPulsarLikelihood(self.multihet, self.priors, numba=False)

        # ROQ likelihood
        like_roq = TargetedPulsarLikelihood(
            self.multihet,
            self.priors,
            roq=True,
            ntraining=ntraining,
            likelihood="STUDENTS-T",
        )

        assert len(like_roq._roq_all_nodes) == len(self.multihet)
        for j, het in enumerate(self.multihet):
            # check ROQ has been calculated for each "chunk"
            assert len(like_roq._roq_all_real_node_indices[j]) == het.num_chunks
            assert len(like_roq._roq_all_imag_node_indices[j]) == het.num_chunks
            assert len(like_roq._roq_all_model2_node_indices[j]) == het.num_chunks

            for k in range(het.num_chunks):
                # check number of ROQ nodes is as expected
                assert len(like_roq._roq_all_real_node_indices[j][k]) == 2
                assert len(like_roq._roq_all_imag_node_indices[j][k]) == 2
                assert len(like_roq._roq_all_model2_node_indices[j][k]) == 3

        # check likelihood calculation
        Ntests = 100

        llo = np.zeros(Ntests)
        llr = np.zeros(Ntests)

        for i in range(Ntests):
            parameters = self.priors.sample()

            like_orig.parameters = parameters.copy()
            like_roq.parameters = parameters.copy()

            # get likelihoods
            llo[i] = like_orig.log_likelihood()
            llr[i] = like_roq.log_likelihood()

        assert np.all(np.abs(np.exp(llo - llo.max()) - np.exp(llr - llr.max())) < 1e-3)

    def test_gaussian_likelihood(self):
        ntraining = 500

        # original likelihood
        like_orig = TargetedPulsarLikelihood(
            self.multihet, self.priors, numba=False, likelihood="gaussian"
        )

        # ROQ likelihood
        like_roq = TargetedPulsarLikelihood(
            self.multihet,
            self.priors,
            roq=True,
            ntraining=ntraining,
            likelihood="Normal",
        )

        # check likelihood calculation
        Ntests = 100

        llo = np.zeros(Ntests)
        llr = np.zeros(Ntests)

        for i in range(Ntests):
            parameters = self.priors.sample()

            like_orig.parameters = parameters.copy()
            like_roq.parameters = parameters.copy()

            # get likelihoods
            llo[i] = like_orig.log_likelihood()
            llr[i] = like_roq.log_likelihood()

        assert np.all(np.abs(np.exp(llo - llo.max()) - np.exp(llr - llr.max())) < 1e-3)
