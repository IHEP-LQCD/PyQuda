import os
import sys
import numpy as np
import cupy as cp

test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(test_dir, ".."))
from pyquda import core, quda
from pyquda.core import Nc, Ns
from pyquda.utils import gauge_utils, source

os.environ["QUDA_RESOURCE_PATH"] = ".cache"

latt_size = [4, 4, 4, 8]
Lx, Ly, Lz, Lt = latt_size
Vol = Lx * Ly * Lz * Lt

xi_0, nu = 2.464, 0.95
kappa = 0.115
coeff = 1.17
coeff_r, coeff_t = 0.91, 1.07

mass = 1 / (2 * kappa) - 4

loader = core.QudaFieldLoader(latt_size, mass, 1e-9, 1000, xi_0, nu, coeff_t, coeff_r)
gauge = gauge_utils.readIldg(os.path.join(test_dir, "weak_field.lime"))

quda.initQuda(-1)

loader.loadGauge(gauge)

propagator = core.LatticePropagator(latt_size)
data = propagator.data.reshape(Vol, Ns, Ns, Nc, Nc)
for spin in range(Ns):
    for color in range(Nc):
        b = source.source(latt_size, "point", [0, 0, 0, 0], spin, color)
        x = loader.invert(b)
        data[:, :, spin, :, color] = x.data.reshape(Vol, Ns, Nc)

quda.endQuda()

propagator_chroma = cp.array(np.fromfile("pt_prop_1", ">c16", offset=8).astype("<c16"))
print(cp.linalg.norm(propagator.transpose() - propagator_chroma))
