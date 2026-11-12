# Connect the running agents to the policy corpus

The agent tools now use `corpus.py`'s FAISS index whenever it is available. In `CORPUS_BACKEND=auto` mode, the
app warns and uses the small sample corpus if no index exists. Set `CORPUS_BACKEND=faiss` to require the real index
and stop with a clear error if it is missing or incomplete.

## Build the index

Use the policy wording and claims procedure that match the vehicle and insurer you want to demonstrate. The PDF
currently named `insurance_policy_pdf.pdf` in this repository is a two-wheeler policy; it does not match the sample
private-car claim scenarios. Do not use it as a substitute for a private-car policy.

In PowerShell, place the correct PDFs in the ignored `data/policies` folder and build the index:

```powershell
New-Item -ItemType Directory -Force data/policies | Out-Null
Copy-Item "C:\path\to\your-private-car-policy.pdf" data/policies\
Copy-Item "C:\path\to\your-claims-procedure.pdf" data/policies\
python -m pip install -r requirements.txt
python corpus.py index
python corpus.py search "limits on using the insured vehicle for hire or reward"
```

The index files are written to `index/`, which is ignored by Git. Policy PDFs in `data/policies/` are also ignored so
private documents are not accidentally committed.

## Run the app

For Docker Compose, set `CORPUS_BACKEND=faiss` in `.env` after building the index, then start or rebuild the stack:

```powershell
docker compose up --build
```

Compose mounts `index/` read-only into the worker. The worker loads the MiniLM model into a named Docker volume during
startup, so the first start needs internet access and may take a while. Once healthy, jobs reuse the loaded FAISS
index and model. Rebuild the index on the host and recreate the worker to load changed policy files.

For running the Python app directly on the host, set `CORPUS_BACKEND=faiss` in `.env` and run the app from the
project directory. The host needs the dependencies in `requirements.txt` as well as `requirements-app.txt`.

The evaluation labels in `eval/scenarios.json` still refer to the sample clauses. Update their supporting quotes,
clause IDs, and expected outcomes to match your selected policy before treating evaluation scores as results for that
policy.
