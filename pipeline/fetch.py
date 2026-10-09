"""
STEP 1 — get the raw data.

Three inputs land in data/raw/:

  states.csv        the 50 states and DC, copied from the committed
                    data/source.csv
  irs_fstc.html     the IRS page listing states that have opted in to the
                    federal scholarship tax credit (refreshed every run)
  pss.csv           the NCES Private School Universe Survey public-use file,
                    used to count Catholic schools and students by state
                    (downloaded once and reused while it is on disk)
"""
import io
import shutil
import zipfile

import requests

from common import DATA, load_config

RAW_DIR = DATA / "raw"
RAW = RAW_DIR / "states.csv"
IRS_HTML = RAW_DIR / "irs_fstc.html"
PSS_CSV = RAW_DIR / "pss.csv"

# The IRS site turns away requests that do not look like a browser.
HEADERS = {"User-Agent": "Mozilla/5.0 (data-site pipeline; +https://github.com)"}


def fetch():
    cfg = load_config()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy(DATA / "source.csv", RAW)

    print(f"fetching {cfg['source_url']}")
    r = requests.get(cfg["source_url"], headers=HEADERS, timeout=60)
    r.raise_for_status()
    IRS_HTML.write_bytes(r.content)

    if PSS_CSV.exists():
        print("using the private school survey already in data/raw/")
    else:
        print(f"fetching {cfg['pss_data_url']}")
        r = requests.get(cfg["pss_data_url"], headers=HEADERS, timeout=300)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            PSS_CSV.write_bytes(z.read(name))

    print("raw data in data/raw/")
    return RAW


if __name__ == "__main__":
    fetch()
