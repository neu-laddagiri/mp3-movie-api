# data_processor.py
import logging

import pandas as pd

logger = logging.getLogger(__name__)


def remove_duplicates(df):
    """Remove duplicate rows."""
    before = len(df)
    df = df.drop_duplicates()
    after = len(df)

    logger.debug(f"remove_duplicates: {before} → {after} rows")

    return df


def handle_missing(df, axis="rows"):
    """Drop rows or columns containing missing values."""
    if axis not in ("rows", "columns"):
        logger.error(f"Unsupported axis: {axis}")
        raise ValueError(f"Unsupported axis: {axis}")

    if axis == "rows":
        before = len(df)
        df = df.dropna()
        after = len(df)
        logger.debug(f"handle_missing: {before} → {after} rows")
    else:
        before = df.shape[1]
        df = df.dropna(axis=1)
        after = df.shape[1]
        logger.debug(f"handle_missing: {before} → {after} columns")

    return df


def remove_outliers(df, columns, method, threshold):
    """Remove outliers from the specified numeric columns."""
    if method not in ("iqr", "zscore"):
        logger.error(f"Unsupported outlier method: {method}")
        raise ValueError(f"Unsupported outlier method: {method}")

    try:
        threshold = float(threshold)
    except (TypeError, ValueError) as error:
        logger.error(f"Invalid outlier threshold: {threshold!r}")
        raise ValueError(f"Invalid outlier threshold: {threshold!r}") from error

    if threshold < 0:
        logger.error(f"Outlier threshold cannot be negative: {threshold}")
        raise ValueError(f"Outlier threshold cannot be negative: {threshold}")

    if columns is None:
        columns = []
    elif not isinstance(columns, (list, tuple)):
        columns = [columns]

    for column in columns:
        if column not in df.columns:
            logger.warning(f"Column not found: {column}")
            continue

        if not pd.api.types.is_numeric_dtype(df[column]):
            logger.warning(f"Column is not numeric: {column}")
            continue

        if method == "iqr":
            q1 = df[column].quantile(0.25)
            q3 = df[column].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
        else:
            mean = df[column].mean()
            std = df[column].std()
            lower = mean - threshold * std
            upper = mean + threshold * std

        if pd.isna(lower) or pd.isna(upper):
            logger.warning(f"Not enough data to compute outlier bounds for {column}")
            continue

        before = len(df)
        df = df[(df[column] >= lower) & (df[column] <= upper)].copy()
        removed = before - len(df)

        logger.debug(
            f"{column}: method={method}, threshold={threshold}, "
            f"lower={lower}, upper={upper}, removed={removed}"
        )

    return df


def _get_section(settings, name):
    """Return a config section as a dict ({} if it is missing or empty)."""
    section = settings.get(name)
    if section is None:
        return {}
    if not isinstance(section, dict):
        logger.error(f"Config section '{name}' must contain settings, got {section!r}")
        raise ValueError(f"Config section '{name}' must contain settings, got {section!r}")
    return section


def _is_enabled(value, name):
    """Read a true/false setting (also accepts the strings "true" and "false")."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    logger.error(f"{name} must be true or false, got {value!r}")
    raise ValueError(f"{name} must be true or false, got {value!r}")


def process_data(df, config):
    """Apply the processing steps enabled in the configuration."""
    settings = _get_section(config, "processing")

    if _is_enabled(settings.get("remove_duplicates"), "remove_duplicates"):
        df = remove_duplicates(df)

    missing = _get_section(settings, "missing")
    if _is_enabled(missing.get("enabled"), "missing.enabled"):
        df = handle_missing(df, missing.get("axis") or "rows")

    outliers = _get_section(settings, "outliers")
    if _is_enabled(outliers.get("enabled"), "outliers.enabled"):
        df = remove_outliers(
            df,
            outliers.get("columns"),
            outliers.get("method"),
            outliers.get("threshold"),
        )

    return df


def create_cleaning_report(df_before, df_after):
    """Return a dictionary summarizing the cleaning results."""
    return {
        "rows_before": len(df_before),
        "rows_after": len(df_after),
        "rows_removed": len(df_before) - len(df_after),
        "columns_before": df_before.shape[1],
        "columns_after": df_after.shape[1],
        "columns_removed": df_before.shape[1] - df_after.shape[1],
    }