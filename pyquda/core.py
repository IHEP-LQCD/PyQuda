from typing import Sequence, Union
from enum import IntEnum
from math import sqrt

import numpy as np
import cupy as cp

from pyquda.enum_quda import QudaLinkType

from . import pyquda as quda
from .pyquda import getDataPointers, getDataPointer, getEvenPointer, getOddPointer


class LatticeConstant(IntEnum):
    Nc = 3
    Nd = 4
    Ns = 4


Nc = LatticeConstant.Nc
Nd = LatticeConstant.Nd
Ns = LatticeConstant.Ns


def newLatticeFieldData(latt_size: Sequence[int], dtype: str) -> cp.ndarray:
    Lx, Ly, Lz, Lt = latt_size
    if dtype.capitalize() == "Gauge":
        return cp.zeros((Nd, 2, Lt, Lz, Ly, Lx // 2, Nc, Nc), "<c16")
    elif dtype.capitalize() == "Fermion":
        return cp.zeros((2, Lt, Lz, Ly, Lx // 2, Ns, Nc), "<c16")
    elif dtype.capitalize() == "Propagator":
        return cp.zeros((2, Lt, Lz, Ly, Lx // 2, Ns, Ns, Nc, Nc), "<c16")


class LatticeField:
    def __init__(self) -> None:
        pass


class LatticeGauge(LatticeField):
    def __init__(self, latt_size: Sequence[int], value=None, t_boundary=True) -> None:
        self.latt_size = latt_size
        if value is None:
            self.data = newLatticeFieldData(latt_size, "Gauge").reshape(-1)
        else:
            self.data = value.reshape(-1)
        self.t_boundary = t_boundary

    def setAntiPeroidicT(self):
        if self.t_boundary:
            Lt = self.latt_size[Nd - 1]
            data = self.data.reshape(Nd, 2, Lt, -1)
            data[Nd - 1, :, Lt - 1] *= -1

    def setAnisotropy(self, anisotropy: float):
        data = self.data.reshape(Nd, -1)
        data[:Nd - 1] /= anisotropy

    def lexico(self):
        Lx, Ly, Lz, Lt = self.latt_size
        data_cb2 = self.data.reshape(Nd, 2, Lt, Lz, Ly, Lx // 2, Nc, Nc).get()
        data_lex = np.zeros((Nd, Lt, Lz, Ly, Lx, Nc, Nc), "<c16")
        for t in range(Lt):
            for z in range(Lz):
                for y in range(Ly):
                    eo = (t + z + y) % 2
                    if eo == 0:
                        data_lex[:, t, z, y, 0::2] = data_cb2[:, 0, t, z, y, :]
                        data_lex[:, t, z, y, 1::2] = data_cb2[:, 1, t, z, y, :]
                    else:
                        data_lex[:, t, z, y, 1::2] = data_cb2[:, 0, t, z, y, :]
                        data_lex[:, t, z, y, 0::2] = data_cb2[:, 1, t, z, y, :]
        return data_lex.reshape(-1)

    @property
    def data_ptr(self):
        return getDataPointers(self.data.reshape(4, -1), 4)

    @property
    def data_ptrs(self):
        return getDataPointers(self.data.reshape(4, -1), 4)


class LatticeFermion(LatticeField):
    def __init__(self, latt_size: Sequence[int]) -> None:
        self.latt_size = latt_size
        self.data = newLatticeFieldData(latt_size, "Fermion").reshape(-1)

    @property
    def even(self):
        return self.data.reshape(2, -1)[0]

    @even.setter
    def even(self, value):
        data = self.data.reshape(2, -1)
        data[0] = value.reshape(-1)

    @property
    def odd(self):
        return self.data.reshape(2, -1)[1]

    @odd.setter
    def odd(self, value):
        data = self.data.reshape(2, -1)
        data[1] = value.reshape(-1)

    @property
    def data_ptr(self):
        return getDataPointer(self.data)

    @property
    def even_ptr(self):
        return getEvenPointer(self.data.reshape(2, -1))

    @property
    def odd_ptr(self):
        return getOddPointer(self.data.reshape(2, -1))


class LatticePropagator(LatticeField):
    def __init__(self, latt_size: Sequence[int]) -> None:
        self.latt_size = latt_size
        self.data = newLatticeFieldData(latt_size, "Propagator").reshape(-1)

    def lexico(self):
        Lx, Ly, Lz, Lt = self.latt_size
        data_cb2 = self.data.reshape(2, Lt, Lz, Ly, Lx // 2, Ns, Ns, Nc, Nc).get()
        data_lex = np.zeros((Lt, Lz, Ly, Lx, Ns, Ns, Nc, Nc), "<c16")
        for t in range(Lt):
            for z in range(Lz):
                for y in range(Ly):
                    eo = (t + z + y) % 2
                    if eo == 0:
                        data_lex[t, z, y, 0::2] = data_cb2[0, t, z, y, :]
                        data_lex[t, z, y, 1::2] = data_cb2[1, t, z, y, :]
                    else:
                        data_lex[t, z, y, 1::2] = data_cb2[0, t, z, y, :]
                        data_lex[t, z, y, 0::2] = data_cb2[1, t, z, y, :]
        return data_lex.reshape(-1)

    def transpose(self):
        Lx, Ly, Lz, Lt = self.latt_size
        Vol = Lx * Ly * Lz * Lt
        data = self.data.reshape(Vol, Ns, Ns, Nc, Nc)
        data_T = data.transpose(0, 2, 1, 4, 3).copy()
        return data_T.reshape(-1)


def smear(latt_size: Sequence[int], gauge: LatticeGauge, nstep: int, rho: float):
    loader = QudaFieldLoader(latt_size, 0, 0, 0)
    loader.loadGauge(gauge)
    quda.performSTOUTnStep(nstep, rho, 1)
    loader.gauge_param.type = QudaLinkType.QUDA_SMEARED_LINKS
    quda.saveGaugeQuda(gauge.data_ptr, loader.gauge_param)


class QudaFieldLoader:
    def __init__(
        self,
        latt_size: Sequence[int],
        mass: Union[float, Sequence[float]],
        tol: Union[float, Sequence[float]],
        maxiter: int,
        xi_0: float = 1.0,
        nu: float = 1.0,
        clover_coeff_t: float = 0.0,
        clover_coeff_r: float = 1.0,
    ) -> None:

        Lx, Ly, Lz, Lt = latt_size
        volume = Lx * Ly * Lz * Lt
        xi = xi_0 / nu
        kappa = 1 / (2 * (mass + 1 + (Nd - 1) / xi))
        if xi != 1.0:
            clover_coeff = xi_0 * clover_coeff_t**2 / clover_coeff_r
            clover_xi = sqrt(xi_0 * clover_coeff_t / clover_coeff_r)
        else:
            clover_coeff = clover_coeff_t
            clover_xi = 1.0
        clover = clover_coeff != 0.0

        self.latt_size = latt_size
        self.volume = volume
        self.xi_0 = xi_0
        self.nu = nu
        self.xi = xi
        self.mass = mass
        self.kappa = kappa
        self.clover_coeff = kappa * clover_coeff
        self.clover_xi = clover_xi
        self.clover = clover
        if isinstance(mass, float):
            if not clover:
                from .dslash import wilson as loader
                self.invert_param = loader.newQudaInvertParam(kappa, tol, maxiter)
            else:
                from .dslash import clover_wilson as loader
                self.invert_param = loader.newQudaInvertParam(kappa, tol, maxiter, clover_xi, kappa * clover_coeff)
        else:
            from .dslash import wilson_multishift as loader
            self.invert_param = loader.newQudaInvertParam(kappa, tol, maxiter)
        self.loader = loader
        self.gauge_param = loader.newQudaGaugeParam(latt_size, xi)

    def loadGauge(self, gauge: LatticeGauge):
        self.loader.loadGauge(gauge, self.gauge_param, self.invert_param)

    def invert(self, b: LatticeFermion):
        return self.loader.invert(b, self.invert_param)

    def invert12(self, b12: LatticePropagator):
        latt_size = self.latt_size
        Lx, Ly, Lz, Lt = latt_size
        Vol = Lx * Ly * Lz * Lt

        x12 = LatticePropagator(latt_size)
        for spin in range(Ns):
            for color in range(Nc):
                b = LatticeFermion(latt_size)
                data = b.data.reshape(Vol, Ns, Nc)
                data[:] = b12.data.reshape(Vol, Ns, Ns, Nc, Nc)[:, :, spin, :, color]
                x = self.invert(b)
                data = x12.data.reshape(Vol, Ns, Ns, Nc, Nc)
                data[:, :, spin, :, color] = x.data.reshape(Vol, Ns, Nc)

        return x12
