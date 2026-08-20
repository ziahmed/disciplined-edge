"""Contract conformance: the predict endpoint must return a valid Prediction
that satisfies the interval/scenario invariants."""

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Prediction

client = TestClient(app)


def test_predict_returns_valid_contract():
    r = client.post("/predict",
                    json={"symbol": "ASML", "exchange": "NASDAQ", "horizon": "1m"})
    assert r.status_code == 200
    Prediction.model_validate(r.json())  # raises if invariants break


def test_unknown_symbol_404():
    r = client.post("/predict",
                    json={"symbol": "NOPE", "exchange": "NASDAQ", "horizon": "1m"})
    assert r.status_code == 404
