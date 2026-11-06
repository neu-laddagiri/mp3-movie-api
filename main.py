import io
import json
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    DatasetInfo,
    DatasetStorage,
    HealthResponse,
    ProcessConfig,
    ProcessingReport,
    log_requests,
    setup_logging,
)

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")
app.middleware("http")(log_requests)
storage = DatasetStorage()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return HealthResponse(status="ok", version=app.version)


@app.post("/upload", response_model=DatasetInfo)
async def upload_dataset(file: UploadFile = File(...)):
    """Read and store a CSV upload."""
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

    dataset_id = storage.save(df, file.filename)
    logger.info(f"Uploaded dataset: id={dataset_id}, filename={file.filename}, rows={len(df)}")
    return DatasetInfo(**storage.get_metadata(dataset_id))


@app.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int, limit: int = Query(default=100, ge=1)):
    """Return up to limit rows from a stored dataset."""
    df = storage.get(dataset_id)
    if df is None:
        logger.warning(f"Dataset not found: {dataset_id}")
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    records = json.loads(df.head(limit).to_json(orient="records"))
    logger.info(f"Retrieved dataset: id={dataset_id}, returned_rows={len(records)}")
    return {"id": dataset_id, "data": records, "total_rows": len(df)}


@app.post(
    "/datasets/{dataset_id}/process",
    response_model=ProcessingReport
)
def process_dataset(dataset_id: int, config: ProcessConfig):
    """Validate and process a stored dataset using MP1 functions."""
    # 1. Get a copy of the stored data; 404 if that ID doesn't exist
    df = storage.get(dataset_id)
    if df is None:
        logger.warning(f"Dataset not found: {dataset_id}")
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    # 2. Turn the request body into the same dictionary shape MP1's config.yaml had
    settings = config.model_dump()
    required_columns = settings["validation"]["required_columns"]
    numeric_columns = settings["validation"]["numeric_columns"]

    # 3. Every numeric column has to exist before validating
    missing_numeric = [col for col in numeric_columns if col not in df.columns]
    if missing_numeric:
        logger.warning(f"Numeric columns not found in dataset {dataset_id}: {missing_numeric}")
        raise HTTPException(status_code=400, detail=f"Numeric columns not found: {missing_numeric}")

    # 4-6. Validate, count what validation removed, save a copy, then process
    try:
        validated = validate_dataframe(df, required_columns, numeric_columns)
        validation_rows_removed = len(df) - len(validated)
        before_processing = validated.copy()
        processed = process_data(validated, settings)
    except ValueError as error:
        logger.warning(f"Could not process dataset {dataset_id}: {error}")
        raise HTTPException(status_code=400, detail=str(error)) from error

    # 7. Compare the validated copy with the processed result
    report = create_cleaning_report(before_processing, processed)

    # 8. Only now, after both steps worked, replace the stored data
    storage.update(dataset_id, processed)
    logger.info(
        f"Processed dataset: id={dataset_id}, validation_removed={validation_rows_removed}, "
        f"rows_before={report['rows_before']}, rows_after={report['rows_after']}"
    )

    # 9. Same shape as ProcessingReport
    return {
        "id": dataset_id,
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": report,
    }