# Integrated energy planning modules

Public/reduced version of the integration code prepared for publication in GitHub. The main integration layer is:

`api/services/scripts/module_integration.py`

Only the modules required by the supplied entry scripts are included. Experimental files, historical versions, IDE metadata, caches and generated outputs from the development copy have been removed.

## Active integration functions

`module_integration.py` exposes the functions currently used by the examples:

- `kpi_calculation(...)`: calculates KPI scores.
- `computation_modules(...)`: runs the multi-energy optimisation model and obtains the climate vulnerabilities associated with the selected technologies.
- `barriers_calculation(...)`: calculates barrier scores and associated incentives.
- `outputs_to_front(...)`: groups the model, climate-vulnerability and barrier results.
- `demand_calculation(...)`: creates representative demand days from the building/community input.

The former `parse_demand(...)` function remains commented in `module_integration.py` because it is not used by either supplied entry point in this release.

## Repository structure

```text
.
├── README.md
├── LICENSE
├── requirements.txt
├── .env.example
├── .gitignore
├── _main_test.py
├── _main_demand.py
├── examples/
│   ├── inputs_kpis_moires.json
│   ├── input_computation_modules_moires.json
│   ├── barriers_input_example_moires.json
│   └── inputs_user.json
└── api/
    ├── constants.py
    └── services/scripts/
        ├── module_integration.py
        ├── computation_modules/
        ├── profiles_calculation/
        └── rat_rev_tool/
```

## Input files

There are exactly **three input files for `_main_test.py`**, matching the three files used by the original script:

1. `examples/inputs_kpis_moires.json` → input for `kpi_calculation(...)`.
2. `examples/input_computation_modules_moires.json` → input for `computation_modules(...)`. The climate vulnerabilities are derived from this same technology/model input; there is no additional climate input file in this workflow.
3. `examples/barriers_input_example_moires.json` → input for `barriers_calculation(...)`.

The demand workflow is independent and uses one additional file:

4. `examples/inputs_user.json` → input for `demand_calculation(...)`.

These four JSON files are copied from the original development version so that the public examples preserve the payloads used by the supplied `_main_test.py` and `_main_demand.py` flows.

## Installation

Python 3.11 or 3.12 is recommended.

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
pip install --upgrade pip
pip install -r requirements.txt
```

The optimisation uses the HiGHS solver through `highspy`, included in `requirements.txt`.

## Run `_main_test.py`

From the repository root:

```bash
python _main_test.py
```

The script loads the three JSON files listed above, executes KPIs, computation modules/climate vulnerabilities and barriers, and writes:

`outputs_test.json`

Generated output files are excluded by `.gitignore`.

## Run `_main_demand.py`

The demand workflow performs calls to external services and requires Thermagrid configuration. Set the required values before executing it:

```bash
export THERMAGRID_API_URL="https://..."
export THERMAGRID_API_KEY="..."
export SRID="4326"
python _main_demand.py
```

On Windows PowerShell, use `$env:VARIABLE_NAME="value"` instead of `export`.

`_main_demand.py` reads `examples/inputs_user.json` and writes `demand_output.json`.

Do not commit real credentials. `.env` and `.env.*` are ignored by Git, while `.env.example` is intentionally tracked.

## Notes for integration

- Run the entry scripts from the repository root, or ensure the repository root is available on `PYTHONPATH`.
- Downstream applications should import the public functions from `api.services.scripts.module_integration` rather than importing internal calculation files directly.
- Climate vulnerabilities do not require a fourth `_main_test.py` input: they are calculated from `input_computation_modules_moires.json`.
- The demand workflow depends on external services, so it also depends on network availability and valid credentials.

## License

The source files supplied in the development copy declare GNU GPLv3 licensing. The GPL license is included at repository root. Preserve the corresponding notices and attribution when redistributing or modifying the code.


Before committing, use `git status` to confirm that no credentials, local outputs, caches or confidential data are staged.
