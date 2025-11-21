#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
plot_all
"""

#!/usr/bin/env python3
"""
Batch BayHunter plotter.

Scans a root directory (e.g., /path/to/output or /path/to/results) for config
files that match */data/*_config.pkl, then generates:
  <basename>_bestfit.pdf
  <basename>_bestmodel.pdf
in an output directory (defaults to <root>/plots).

Example layout it supports:
  output/36.50_-31.23/data/36.50_-31.23_config.pkl
  output/36.55_-31.28/data/36.55_-31.28_config.pkl
  results/lat_long/data/lat_long_config.pkl
"""

import argparse
import glob

from pathlib import Path

# Import once at top so we fail fast if BayHunter isn't available
try:
    from BayHunter import PlotFromStorage
except Exception as e:
    raise SystemExit(f"Failed to import BayHunter.PlotFromStorage: {e}")

def find_config_files(root: Path, suffix: str = "_config.pkl") -> list[Path]:
    """
    Find all config files named *<suffix> that live under a 'data' folder.
    Uses glob recursion for speed and simplicity.
    """
    pattern = str(root / "**" / f"*{suffix}")
    candidates = [Path(p) for p in glob.glob(pattern, recursive=True)]
    # Keep only those inside a 'data' directory
    return [p for p in candidates if "data" in p.parts]

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def process_config(config_path: Path, out_dir: Path, overwrite: bool = False, verbose: bool = True) -> None:
    """
    Given a single *_config.pkl path, render and save the two PDFs.
    """
    # Basename without the _config.pkl
    stem = config_path.name
    if not stem.endswith("_config.pkl"):
        # If it's some other suffix, try to derive a sensible base anyway
        base = stem.replace(".pkl", "").replace("_config", "")
    else:
        base = stem[: -len("_config.pkl")]

    # Output filenames
    out_bestfit = out_dir / f"{base}_bestfit.pdf"
    out_bestmodel = out_dir / f"{base}_bestmodel.pdf"

    if not overwrite and out_bestfit.exists() and out_bestmodel.exists():
        if verbose:
            print(f"Skipping {base}: both outputs already exist.")
        return

    if verbose:
        print(f"Processing: {config_path}  ->  {out_bestfit.name}, {out_bestmodel.name}")

    # Plot + save
    obj = PlotFromStorage(str(config_path))
    # best data fits
    fig1 = obj.plot_bestdatafits()
    ensure_dir(out_dir)
    obj.savefig(fig1, str(out_bestfit))
    # best models
    fig2 = obj.plot_bestmodels()
    obj.savefig(fig2, str(out_bestmodel))

def main():


    parser = argparse.ArgumentParser(description="Batch-generate BayHunter PDFs from stored configs.")
    parser.add_argument("root", type=Path, help="Root directory to scan (e.g., /path/to/output or /path/to/results)")
    parser.add_argument("-o", "--outdir", type=Path, default=None,
                        help="Directory to write PDFs (default: <root>/plots)")
    parser.add_argument("--suffix", type=str, default="_config.pkl",
                        help="Config filename suffix to match (default: _config.pkl)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing PDFs")
    parser.add_argument("--quiet", action="store_true", help="Less console output")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    root = args.root.resolve()
    outdir = (args.outdir.resolve() if args.outdir else (root / "plots"))
    verbose = not args.quiet

    if verbose:
        print(f"Scanning: {root}")
        print(f"Output dir: {outdir}")

    configs = find_config_files(root, suffix=args.suffix)
    if verbose:
        print(f"Found {len(configs)} config file(s).")

    if args.dry_run:
        for c in configs:
            base = c.name.replace(args.suffix, "") if c.name.endswith(args.suffix) else c.stem
            print(f"[DRY RUN] Would write: {outdir / (base + '_bestfit.pdf')} and {outdir / (base + '_bestmodel.pdf')}")
        return

    ensure_dir(outdir)
    for c in sorted(configs):
        try:
            process_config(c, outdir, overwrite=args.overwrite, verbose=verbose)
        except Exception as e:
            print(f"ERROR processing {c}: {e}")

if __name__ == "__main__":
    main()