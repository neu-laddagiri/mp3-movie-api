# src/data_validator.py
import logging
import pandas as pd


logger = logging.getLogger(__name__)


def _as_list(value):
    """Return a config value as a list: None becomes [] and a single name becomes [name]."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def validate_dataframe(df, required_columns, numeric_columns):
    """Validate the DataFrame and return valid data.

    required_columns: a list of column names that must exist.
    numeric_columns: a list of column names whose values should be numeric.
    """
    if not isinstance(df, pd.DataFrame):
        logger.error(f"Expected a DataFrame from a CSV file, got {type(df).__name__}")
        raise ValueError(f"Expected a DataFrame from a CSV file, got {type(df).__name__}")

    required_columns = _as_list(required_columns)
    numeric_columns = _as_list(numeric_columns)

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.error(f"Missing required columns: {missing_columns}")
        raise ValueError(f"Missing required columns: {missing_columns}")

    missing_numeric = [col for col in numeric_columns if col not in df.columns]
    if missing_numeric:
        logger.error(f"Numeric columns not found: {missing_numeric}")
        raise ValueError(f"Numeric columns not found: {missing_numeric}")

    rows_before = len(df)

    for col in numeric_columns:
        invalid_rows = []
        for i, value in df[col].items():
            if pd.notna(value):
                try:
                    float(value)
                except ValueError:
                    logger.warning(f"Invalid numeric value in {col} at row {i}: {value!r}")
                    invalid_rows.append(i)

        df = df.drop(index=invalid_rows)
        if invalid_rows:
            logger.warning(
                f"Removed {len(invalid_rows)} rows with invalid numeric values in {col}"
            )

        # convert to a numeric data type
        try:
            df[col] = pd.to_numeric(df[col])
        except ValueError as error:
            logger.error(f"Could not convert {col} to numbers: {error}")
            raise ValueError(f"Could not convert {col} to numbers: {error}") from error

    rows_after = len(df)
    logger.debug(
        f"Validation: {rows_before} → {rows_after} rows "
        f"({rows_before - rows_after} removed)"
    )

    return df