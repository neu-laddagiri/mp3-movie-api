import io
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    MovieCache,
    MovieDataResponse,
    MovieProcessingReport,
    MovieStorage,
    MovieUploadInfo,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Movie Database API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()
cache = MovieCache()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return HealthResponse(status="ok", version=app.version)


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a movie CSV and replace the stored collection with it."""
    # 1. Same .csv check and CSV parsing as MP2
    extension = Path(file.filename or "").suffix.lower()
    if extension != ".csv":
        shown = extension or "(none)"
        logger.warning(f"Unsupported file format: {shown}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {shown}. Only .csv files are accepted.",
        )

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except pd.errors.EmptyDataError as error:
        logger.warning(f"Empty CSV upload: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="The CSV file is empty. Upload a file with a header row and data.",
        ) from error
    except pd.errors.ParserError as error:
        reason = str(error).strip()  # pandas adds a trailing newline to this message
        logger.warning(f"Could not parse CSV upload {file.filename}: {reason}")
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse the CSV file: {reason}",
        ) from error
    except UnicodeDecodeError as error:
        logger.warning(f"Could not decode CSV upload {file.filename}: {error}")
        raise HTTPException(
            status_code=400,
            detail="The file could not be read as text. Save it as a UTF-8 CSV and try again.",
        ) from error

    # 2. Quick checks before saving: exactly the 4 movie columns, and at least one row
    if sorted(df.columns) != sorted(MOVIE_COLUMNS):
        logger.warning(f"Wrong columns in {file.filename}: {list(df.columns)}")
        raise HTTPException(
            status_code=400,
            detail=f"The CSV must have exactly these columns: {MOVIE_COLUMNS}",
        )
    if df.empty:
        logger.warning(f"No data rows in {file.filename}")
        raise HTTPException(status_code=400, detail="The CSV has no data rows.")
    df = df[MOVIE_COLUMNS]  # same column order as the table

    # 3. Replace the stored collection with this upload
    storage.save(df)
    cache.invalidate()  # the stored movies changed, so old cached responses are wrong now
    logger.info(f"Uploaded movies: filename={file.filename}, rows={len(df)}")
    return MovieUploadInfo(
        filename=file.filename,
        rows=len(df),
        columns=len(df.columns),
        column_names=list(df.columns),
    )


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit stored movies plus the total count, using the cache when possible."""
    # 1. Cache hit: return the saved response and skip SQLite completely
    cached = cache.get(limit)
    if cached is not None:
        logger.info(f"Retrieved movies from cache: returned_rows={len(cached['data'])}")
        return cached

    # 2. Cache miss: same SQL retrieval and count as Part 1
    rows = storage.select_columns(MOVIE_COLUMNS, limit)
    total_rows = storage.count_movies()
    response = {"data": rows, "total_rows": total_rows}

    # 3. Save the complete response for next time, then return it
    cache.set(limit, response)
    logger.info(f"Retrieved movies: returned_rows={len(rows)}")
    return response


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1)
):
    """Return id plus the chosen columns for movies rated at least min_rating."""
    try:
        rows = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    logger.info(
        f"Queried movies: columns={columns}, min_rating={min_rating}, "
        f"returned_rows={len(rows)}"
    )
    return rows


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and process the stored movies with the MP1 functions, then save the result."""
    # 1. Get the stored movies; 400 if there is nothing to process
    df = storage.get()
    if df.empty:
        logger.warning("No movies to process")
        raise HTTPException(status_code=400, detail="No movies stored. Upload a CSV first.")

    # 2. Turn the request body into the same dictionary shape MP1's config.yaml had
    settings = config.model_dump()
    required_columns = settings["validation"]["required_columns"]
    numeric_columns = settings["validation"]["numeric_columns"]

    # 3. Every numeric column has to exist before validating
    missing_numeric = [col for col in numeric_columns if col not in df.columns]
    if missing_numeric:
        logger.warning(f"Numeric columns not found: {missing_numeric}")
        raise HTTPException(status_code=400, detail=f"Numeric columns not found: {missing_numeric}")

    # 4-6. Validate, count what validation removed, keep a copy, then process
    try:
        validated = validate_dataframe(df, required_columns, numeric_columns)
        validation_rows_removed = len(df) - len(validated)
        before_processing = validated.copy()
        processed = process_data(validated, settings)
    except ValueError as error:
        logger.warning(f"Could not process movies: {error}")
        raise HTTPException(status_code=400, detail=str(error)) from error

    # 7. Compare the validated copy with the processed result
    report = create_cleaning_report(before_processing, processed)

    # 8. Only now, after both steps worked, replace the stored movies
    storage.save(processed)
    cache.invalidate()  # same reason: the stored movies just changed
    logger.info(
        f"Processed movies: validation_removed={validation_rows_removed}, "
        f"rows_before={report['rows_before']}, rows_after={report['rows_after']}"
    )

    # 9. Same shape as MovieProcessingReport
    return {
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": report,
    }