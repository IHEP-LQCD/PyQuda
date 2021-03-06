from distutils.core import Extension, setup
from Cython.Build import cythonize
import numpy

VERSION = "0.0.2"
LICENSE = "MIT"
DESCRIPTION = "Python wrapper for quda written in Cython."

ext_modules = cythonize(
    [
        Extension(
            "pyquda.pyquda",
            ["pyquda/src/pyquda.pyx"],
            language="c",
            include_dirs=["pyquda/include", numpy.get_include()],
            define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")],
            library_dirs=["."],
            libraries=["quda"],
        )
    ],
    language_level="3",
)

packages = [
    "pyquda",
    "pyquda.dslash",
    "pyquda.utils",
]
package_dir = {
    "pyquda": "pyquda",
}
package_data = {
    "pyquda": ["*.pyi", "src/*.pxd", "include/*.h"],
}

setup(
    name="PyQuda",
    version=VERSION,
    description=DESCRIPTION,
    author="SaltyChiang",
    author_email="SaltyChiang@users.noreply.github.com",
    packages=packages,
    ext_modules=ext_modules,
    license=LICENSE,
    package_dir=package_dir,
    package_data=package_data,
)
