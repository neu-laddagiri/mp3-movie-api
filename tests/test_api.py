import pandas as pd
import pytest

from src import MovieStorage
import main


def test_movies_persist(client, test_storage, uploaded_movies):
    # A second MovieStorage on the same file acts like restarting the server
    reopened = MovieStorage(test_storage.db_path)

    # The data survived: 20 rows, the 4 columns, and the same title order as the CSV
    df = reopened.get()
    assert reopened.count_movies() == 20
    assert len(df) == 20
    assert list(df.columns) == ["title", "release_year", "rating", "genre"]
    original_titles = pd.read_csv("fixtures/sample_movies.csv")["title"].tolist()
    assert df["title"].tolist() == original_titles

    # The IDs match between the storage object and the API: 1 through 20, in row order
    stored_ids = [row["id"] for row in reopened.select_columns(["title"], limit=100)]
    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    api_ids = [record["id"] for record in response.json()["data"]]
    assert stored_ids == list(range(1, 21))
    assert api_ids == stored_ids


def test_cache_and_processing(client, uploaded_movies, processing_body):
    # 1. Two different limits make two separate cache entries
    full = client.get("/movies", params={"limit": 100})
    one = client.get("/movies", params={"limit": 1})
    assert full.status_code == 200
    assert one.status_code == 200
    assert main.cache.get(100) == full.json()
    assert main.cache.get(1) == one.json()

    # 2. Asking again gives back the same response
    repeat = client.get("/movies", params={"limit": 100})
    assert repeat.status_code == 200
    assert repeat.json() == full.json()

    # 3. Processing saves new data, so both old cache entries must be gone
    response = client.post("/movies/process", json=processing_body)
    assert response.status_code == 200
    report = response.json()
    assert report["validation_rows_removed"] == 0
    assert report["cleaning_report"]["rows_before"] == 20
    assert report["cleaning_report"]["rows_after"] == 16
    assert report["cleaning_report"]["rows_removed"] == 4
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None

    # 4. The next request reads the 16 processed rows from SQLite and caches them
    updated = client.get("/movies", params={"limit": 100})
    assert updated.status_code == 200
    body = updated.json()
    assert body["total_rows"] == 16
    titles = [record["title"] for record in body["data"]]
    assert titles == [f"Movie {letter}" for letter in "ABCDEFGHIJKLMNOP"]
    ids = [record["id"] for record in body["data"]]
    assert ids == list(range(1, 17))
    assert main.cache.get(100) == body


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    # 1. The first request fills the cache
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200

    # 2. From here on, touching the database makes the test fail
    def fail_if_called(*args, **kwargs):
        pytest.fail("A cache hit should not query the database")

    monkeypatch.setattr(main.storage, "select_columns", fail_if_called)
    monkeypatch.setattr(main.storage, "count_movies", fail_if_called)

    # 3. The same request is answered from the cache with the same body
    second = client.get("/movies", params={"limit": 100})
    assert second.status_code == 200
    assert second.json() == first.json()