# src/data_output.py
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def save_data(df, filepath):
    """Save a DataFrame as a CSV file."""
    path = Path(filepath)

    if path.is_dir():
        logger.error(f"Output path is a folder, not a file: {path}")
        raise ValueError(f"Output path is a folder, not a file: {path}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    except OSError as error:
        logger.error(f"Could not save output to {path}: {error}")
        raise ValueError(f"Could not save output to {path}: {error}") from error

    logger.debug(f"Saved {len(df)} rows to {path}")

    return path