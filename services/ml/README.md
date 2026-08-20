# ML service (FastAPI)

## Run
```bash
cd services/ml
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Try it
```bash
curl -X POST localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"ASML","exchange":"NASDAQ","horizon":"1m"}'
```

`app/routers/predict.py` returns a contract-shaped stub today. Port your
notebook into `app/features/engineer.py` and wire `_run_pipeline` to it.
