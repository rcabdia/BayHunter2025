#!/usr/bin/env python
from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext as _build_ext

# Import here so build isolation installs them first (via pyproject.toml)
from Cython.Build import cythonize
import numpy as np


class build_ext(_build_ext):
    """
    Build Cython/C++ extensions normally, then build the Fortran extension
    using f2py (NumPy 2.x) without numpy.distutils.
    """
    def run(self):
        # Build C/C++/Cython extensions first (handled by setuptools)
        super().run()

        # Then build the Fortran module with f2py and drop the .so/.pyd in the
        # right package folder inside build_lib so it gets included in the wheel.
        self._build_f2py_fortran()

    def _build_f2py_fortran(self):
        try:
            # NumPy 2.x entry point
            from numpy.f2py import main as f2py_main
        except Exception as exc:
            raise RuntimeError(
                "Failed to import numpy.f2py. Make sure NumPy >= 2.0 is available."
            ) from exc

        src = Path("src/extensions/surfdisp96.f")
        if not src.exists():
            raise FileNotFoundError(f"Fortran source not found: {src}")

        # Build/temp dirs
        build_temp = Path(self.build_temp) / "f2py"
        build_temp.mkdir(parents=True, exist_ok=True)
        build_lib_pkg = Path(self.build_lib) / "BayHunter"
        build_lib_pkg.mkdir(parents=True, exist_ok=True)

        # Module name WITHOUT package (f2py will create surfdisp96_ext.*)
        modulename = "surfdisp96_ext"

        # Fortran flags (tweak per compiler/platform as needed)
        # Users can override by setting FFLAGS in the environment.
        default_f77_flags = "-O3 -ffixed-line-length-none -fbounds-check -m64"
        f77_flags = os.environ.get("FFLAGS", default_f77_flags)

        # f2py CLI args: we run it like
        #   f2py -c src/extensions/surfdisp96.f -m surfdisp96_ext only: surfdisp96 : --f77flags="..."
        args = [
            "-c",
            str(src),
            "-m",
            modulename,
            "only:",
            "surfdisp96",
            ":",
            f"--f77flags={f77_flags}",
        ]

        # Build inside build_temp so artifacts don’t clutter the source tree
        cwd = os.getcwd()
        try:
            os.chdir(build_temp)
            # Run f2py. On success it drops a built extension (e.g. .so / .pyd) here.
            ret = f2py_main(args)
            if ret not in (0, None):
                raise RuntimeError(f"f2py build failed with exit code {ret}")
        finally:
            os.chdir(cwd)

        # Find the produced extension and copy it into build_lib/BayHunter
        produced = list(build_temp.glob(modulename + ".*"))
        # f2py may create intermediates; keep only the extension module
        produced = [p for p in produced if p.suffix in (".so", ".pyd", ".dll", ".dylib")]
        if not produced:
            # Try to search deeper (some toolchains place in subdirs)
            produced = list(build_temp.rglob(modulename + ".*"))
            produced = [p for p in produced if p.suffix in (".so", ".pyd", ".dll", ".dylib")]

        if not produced:
            raise RuntimeError("f2py did not produce an extension module.")

        # Copy the built extension into the package in build_lib
        for extfile in produced:
            shutil.copy2(extfile, build_lib_pkg / extfile.name)

        # Also record it so setuptools knows about it for install_lib (optional)
        # Not strictly necessary since we place it into build_lib already.


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
    # You can add extra compile/link args if needed:
    # extra_compile_args=["-O3"],
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