from setuptools import setup, Extension
import numpy as np
from setuptools.command.build_ext import build_ext as _build_ext
from pathlib import Path
import os, sys, shutil, subprocess

class build_ext(_build_ext):
    def run(self):
        super().run()
        self._build_f2py_fortran()

    def _build_f2py_fortran(self):
        project_root = Path(__file__).parent.resolve()
        src_f = project_root / "src/extensions/surfdisp96.f"
        if not src_f.exists():
            raise FileNotFoundError(f"Fortran source not found: {src_f}")

        build_temp = Path(self.build_temp).resolve() / "f2py"
        build_temp.mkdir(parents=True, exist_ok=True)

        modulename = "surfdisp96_ext"
        default_f77_flags = "-O3 -ffixed-line-length-none -fbounds-check -m64"
        f77_flags = os.environ.get("FFLAGS", default_f77_flags)

        cmd = [
            sys.executable, "-m", "numpy.f2py",
            "-c", str(src_f),
            "-m", modulename,
            "only:", "surfdisp96", ":",
            f"--f77flags={f77_flags}",
        ]
        subprocess.run(cmd, cwd=build_temp, check=True)

        produced = []
        for suf in (".so", ".pyd", ".dll", ".dylib"):
            produced += list(build_temp.glob(modulename + "*" + suf))
            produced += list(build_temp.rglob(modulename + "*" + suf))
        if not produced:
            raise RuntimeError("f2py did not produce an extension module.")

        # Put it where BayHunter.surfdisp96_ext is expected to live
        ext_fullpath = Path(self.get_ext_fullpath("BayHunter.surfdisp96_ext"))
        ext_fullpath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(produced[0], ext_fullpath)


rfmini_sources = [
    "src/extensions/rfmini/rfmini.c",
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
    extra_compile_args=["-O3"],
)

setup(
    name="BayHunter",
    version="2.1",
    # THIS is the important mapping for your current layout:
    packages=["BayHunter"],
    package_dir={"BayHunter": "src"},   # BayHunter => src/
    package_data={"BayHunter": ["defaults/*"]},
    scripts=["src/scripts/baywatch"],
    ext_modules=[rfmini_ext],
    cmdclass={"build_ext": build_ext},
    python_requires=">=3.11",
)