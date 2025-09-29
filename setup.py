#!/usr/bin/env python
from __future__ import annotations

import os
import sys
import shutil
import subprocess
from pathlib import Path

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext as _build_ext

from Cython.Build import cythonize
import numpy as np


class build_ext(_build_ext):
    """
    Build Cython/C++ extensions normally, then build the Fortran extension
    using the f2py CLI (NumPy 2.x).
    """
    def run(self):
        super().run()
        self._build_f2py_fortran()

    def _build_f2py_fortran(self):
        src = Path("src/extensions/surfdisp96.f")
        if not src.exists():
            raise FileNotFoundError(f"Fortran source not found: {src}")

        build_temp = Path(self.build_temp) / "f2py"
        build_temp.mkdir(parents=True, exist_ok=True)
        build_lib_pkg = Path(self.build_lib) / "BayHunter"
        build_lib_pkg.mkdir(parents=True, exist_ok=True)

        modulename = "surfdisp96_ext"
        default_f77_flags = "-O3 -ffixed-line-length-none -fbounds-check -m64"
        f77_flags = os.environ.get("FFLAGS", default_f77_flags)

        # Run: python -m numpy.f2py -c src/extensions/surfdisp96.f -m surfdisp96_ext only: surfdisp96 : --f77flags=...
        cmd = [
            sys.executable, "-m", "numpy.f2py",
            "-c", str(src),
            "-m", modulename,
            "only:", "surfdisp96", ":",
            f"--f77flags={f77_flags}",
        ]

        subprocess.run(cmd, cwd=build_temp, check=True)

        # Find built extension (e.g., .so / .pyd) and copy into BayHunter/
        produced = []
        for suf in (".so", ".pyd", ".dll", ".dylib"):
            produced += list(build_temp.glob(modulename + "*" + suf))
            produced += list(build_temp.rglob(modulename + "*" + suf))
        if not produced:
            raise RuntimeError("f2py did not produce an extension module.")

        for extfile in produced:
            shutil.copy2(extfile, build_lib_pkg / extfile.name)


# ---- Cython/C++ extension ----
rfmini_sources = [
    "src/extensions/rfmini/rfmini.pyx",
    "src/extensions/rfmini/greens.cpp",
    "src/extensions/rfmini/model.cpp",
    "src/extensions/rfmini/pd.cpp",
    "src/extensions/rfmini/synrf.cpp",
    "src/extensions/rfmini/wrap.cpp",
    "src/extensions/rfmini/fork.cpp",
]

rfmini_ext = Extension(
    "BayHunter.rfmini",
    sources=rfmini_sources,
    include_dirs=[np.get_include()],
    language="c++",
)

extensions = cythonize(
    rfmini_ext,
    compiler_directives={"language_level": "3"},
)

setup(
    name="BayHunter",
    version="2.1",
    author="Jennifer Dreiling",
    author_email="jennifer.dreiling@gfz-potsdam.de",
    description="Transdimensional Bayesian Inversion of RF and/or SWD.",
    url="https://github.com/jenndrei/BayHunter",
    packages=["BayHunter"],
    package_dir={"BayHunter": "src"},
    scripts=["src/scripts/baywatch"],
    package_data={"BayHunter": ["defaults/*"]},
    ext_modules=extensions,     # Cython/C++
    cmdclass={"build_ext": build_ext},  # adds the f2py build step
    install_requires=[],
    python_requires=">=3.9",
)