# MP3 Movie API

This project is a FastAPI service that stores one movie collection in SQLite, filters it with SQL, cleans it with the MP1 data pipeline, and caches repeated reads. `POST /upload` accepts a CSV with exactly the columns `title`, `release_year`, `rating`, and `genre`, and `src/storage.py` replaces the whole `movies` table with it in one transaction, so a failed save never leaves half the data behind. `src/database.py` creates the `data/movies.db` file and the table, and because the movies live in that file, they are still there after the server restarts. `GET /movies` returns the stored movies with a total count, while `GET /movies/search` uses a SQL `WHERE` clause to return only movies at or above a minimum rating, with just the columns you ask for. `POST /movies/process` loads the stored movies into pandas, runs the MP1 validation and cleaning functions in `data_pipeline/`, and saves the cleaned result back to SQLite. `src/cache.py` keeps each `GET /movies` response in fakeredis for 90 seconds, keyed by `limit`, so a repeated request skips the database entirely (search is never cached). Every successful upload or processing run clears the cache, so the next request reads fresh data from SQLite instead of an outdated copy. The Pydantic models in `src/models.py` define the request and response shapes, and `src/middleware.py` logs every request with its own request ID.

## Start the API

```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/docs.

## Run the tests

```bash
python -m pytest tests -v
```

## Sample processing request

Upload `fixtures/sample_movies.csv`, then send this body to `POST /movies/process`:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {"enabled": true, "columns": ["rating"], "method": "iqr", "threshold": 1.5}
  }
}
```

Expected result:

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```

Processing drops the duplicate copies of Movie B and Movie D and the two low-rated outliers (Movie Q at 1.0 and Movie R at 0.5), so `GET /movies` then returns 16 movies, Movie A through Movie P.