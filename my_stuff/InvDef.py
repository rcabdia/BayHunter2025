import gc
from typing import Optional
import pandas as pd
from multiprocessing import freeze_support
import matplotlib
from BayHunter import PlotFromStorage
from BayHunter import Targets
from BayHunter import MCMC_Optimizer
from BayHunter import ModelMatrix
import numpy as np
import os
from BayHunter import utils
from utils import PolygonGeoHelper
import logging
from contextlib import suppress
import warnings
warnings.filterwarnings("ignore")

# Configure logging
logging.basicConfig(
    filename="geopoints.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

#os.environ["MKL_NUM_THREADS"] = "6"
#os.environ["NUMEXPR_NUM_THREADS"] = "6"
#os.environ["OMP_NUM_THREADS"] = "6"

matplotlib.use("PDF")


class RunInv:
    def __init__(
        self,
        dsp_path: str,
        phv_path: str,
        results_dir: str,
        priors: Optional[dict] = None,
        initparams: Optional[dict] = None,
        initfile: Optional[str] = None,
        checkpoint_path: Optional[str] = None
    ):
        self.dsp_path = dsp_path
        self.phv_path = phv_path
        self.results_dir = results_dir
        self.checkpoint_path = checkpoint_path

        if isinstance(initparams, dict) and isinstance(priors, dict):
            self.initparams = initparams
            self.priors = priors
        elif isinstance(initfile, str):
            self.priors, self.initparams = utils.load_params(initfile)
        else:
            self.initparams = {}
            self.priors = {}

        os.makedirs(self.results_dir, exist_ok=True)

        if self.checkpoint_path and os.path.exists(self.checkpoint_path):
            self.check_point = pd.read_pickle(self.checkpoint_path)
        else:
            self.check_point = []

    def run_inv(self, trapezoid=None):
        # for Windows multiprocessing safety (no-op on POSIX)
        with suppress(Exception):
            freeze_support()

        self.df_dsp = pd.read_pickle(self.dsp_path)
        self.df_phv = pd.read_pickle(self.phv_path)
        try:
            self.invert(trapezoid)
        finally:
            # drop large inputs once done
            self.df_dsp = None
            self.df_phv = None
            gc.collect()

    def invert(self, trapezoid):
        # Optional spatial filter
        if trapezoid:
            helper = PolygonGeoHelper(trapezoid, lon_index=2, lat_index=3)
            self.df_dsp = helper.filter_dict(self.df_dsp)
            self.df_phv = helper.filter_dict(self.df_phv)

        progress = []
        progress_path = os.path.join(self.results_dir, "progres.pkl")

        # Iterate paired items
        for (dsp_k, dsp), (phv_k, phv) in zip(self.df_dsp.items(), self.df_phv.items()):
            lon = "{:.2f}".format(float(dsp[2]))
            lat = "{:.2f}".format(float(dsp[3]))

            if dsp_k in self.check_point:
                print("Point already done:", dsp_k)
                continue

            msg = f"Checking geographical point at lon={lon}, lat={lat}"
            print(msg)
            logging.info(msg)
            progress.append(dsp_k)

            point_name = f"{lat}_{lon}"
            # ensure per-point folder exists
            self.initparams["savepath"] = os.path.join(self.results_dir, point_name)
            self.initparams["station"] = point_name
            os.makedirs(os.path.join(self.initparams["savepath"], "data"), exist_ok=True)

            cfile = f"{self.initparams['station']}_config.pkl"
            configfile = os.path.join(self.initparams["savepath"], "data", cfile)

            # --- Build targets (use local vars; free them after use)
            TRU = np.array(dsp[0])
            RU = np.array(dsp[1])
            TRC = np.array(phv[0])
            RC = np.array(phv[1])

            target1 = Targets.RayleighDispersionPhase(TRC, RC)
            target2 = Targets.RayleighDispersionGroup(TRU, RU)
            targets = Targets.JointTarget(targets=[target1, target2])

            optimizer = None
            try:
                optimizer = MCMC_Optimizer(
                    targets, initparams=self.initparams, priors=self.priors, random_seed=None
                )
                optimizer.mp_inversion(nthreads=self.initparams["nthreads"])
                self.save_distribution(
                    configfile,
                    self.initparams["maxmodels"],
                    self.initparams["dev"],
                    name=point_name,
                )
                print("Saving Progress: ", dsp_k)
                pd.to_pickle(progress, progress_path)
            finally:
                # Aggressively drop per-iteration objects
                with suppress(Exception):
                    del targets, target1, target2
                with suppress(Exception):
                    del TRU, RU, TRC, RC
                if optimizer is not None:
                    with suppress(Exception):
                        del optimizer
                # close any figures created inside plotting routines
                with suppress(Exception):
                    import matplotlib.pyplot as plt
                    plt.close("all")
                gc.collect()

    def save_distribution(self, configfile, maxmodels, dev, name):
        obj = None
        try:
            # Plotting object
            obj = PlotFromStorage(configfile)
            # Save posterior distribution and plots
            obj.save_final_distribution(maxmodels=maxmodels, dev=dev)
            with suppress(Exception):
                obj.save_plots()
                # obj.merge_pdfs()
        finally:
            # drop plotting object ASAP
            if obj is not None:
                with suppress(Exception):
                    del obj
            # ensure any figures are closed even if PlotFromStorage forgets
            with suppress(Exception):
                import matplotlib.pyplot as plt
                plt.close("all")
            gc.collect()

        # Work with models using memory-mapped read to reduce peak RAM
        file_model = os.path.join(self.initparams["savepath"], "data/c_models.npy")
        models = np.load(file_model, mmap_mode="r")
        try:
            singlemodels = ModelMatrix.get_singlemodels(models)
            vs_mean, depth = singlemodels["mean"]
            vs_median, _ = singlemodels["median"]
            vs_minmax, _ = singlemodels["minmax"]
            vs_stdminmax, _ = singlemodels["stdminmax"]

            model_1d = np.zeros((len(vs_mean), 7))
            model_1d[:, 0] = depth
            model_1d[:, 1] = vs_mean
            model_1d[:, 2] = vs_median
            model_1d[:, 3] = vs_minmax[0, :]
            model_1d[:, 4] = vs_minmax[1, :]
            model_1d[:, 5] = vs_stdminmax[0, :]
            model_1d[:, 6] = vs_stdminmax[1, :]

            out_name = f"{name}_m.txt"
            model_address = os.path.join(self.results_dir, out_name)

            # Write header without '#'
            header = "depth vs_mean vs_median vs_min vs_max vs_stdmin vs_stdmax"
            np.savetxt(model_address, model_1d, header=header, comments="")
        finally:
            with suppress(Exception):
                del models
            gc.collect()

if __name__ == "__main__":
    freeze_support()

    dsp_path = "/data/katrina/Roberto/work_inversion/BayHunter2025/upflow/disp_dsp.pkl"
    phv_path = "/data/katrina/Roberto/work_inversion/BayHunter2025/upflow/disp_phv.pkl"
    # results_dir = "/home/ubuntu/workdir/BayHunter2025/upflow/output"
    results_dir = "/data/katrina/Roberto/work_inversion/BayHunter2025/upflow/output"
    # path_params = "/home/ubuntu/workdir/BayHunter2025/upflow/config_test.ini"
    path_params = "/data/katrina/Roberto/work_inversion/BayHunter2025/upflow/config.ini"
    #checkpoint_path = "/Users/roberto/Documents/sismologia/BayHunter/upflow/output/progres.pkl"
    # checkpoint_path = None
    checkpoint_path = "/data/katrina/Roberto/work_inversion/BayHunter2025/upflow/output/progres.pkl"
    
    trapezoid = [
        (-33.50, 41.00),  # top-left
        (-22.00, 41.00),  # top-right
        (-7.50, 32.50),  # bottom-right
        (-7.50, 26.50),
        (-19.00, 26.50),
        (-20.00, 29.50),
        (-33.50, 37.00) # bottom-left
    ]
    
    RI = RunInv(dsp_path, phv_path, results_dir, initfile=path_params, checkpoint_path=checkpoint_path)
    RI.run_inv(trapezoid)

    # iter_burnin = 50000
    # iter_main = 100000
    # maxmodels = 100000
    # nthreads = 6
    # nchains = 100 * nthreads


    # priors = {'vs': (2, 5.5), 'vpvs': (1.5, 2.1), 'layers': (1, 20), 'z': (0, 100),
    #           'swdnoise_sigma': (1e-5, 0.1), 'swdnoise_corr': (0, 0.3)}
    #
    # initparams = {'nchains': nchains, 'iter_burnin': iter_burnin, 'iter_main': iter_main,
    #               'propdist': (0.015, 0.015, 0.015, 0.005, 0.005),
    #               'acceptance': (40, 45), 'thickmin': 2, 'lvz': 0.1, 'hvz': 0.75,
    #               'rcond': 1e-5, 'station': "test", 'savepath': results_dir,
    #               'maxmodels': maxmodels}

    # Define a trapezoid around Madrid (lon, lat) in order (CW or CCW)
    # part1
    # full dataset