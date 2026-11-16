import logging
import sqlite3

import pandas as pd

from .database import get_connection, initialize_database

logger = logging.getLogger(__name__)
MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


class MovieStorage:
    def __init__(self, db_path="data/movies.db"):
        self.db_path = db_path
        initialize_database(self.db_path)

    def save(self, df):
        """Replace all movie rows in one transaction."""
        # Line the columns up in table order, make every value a plain Python value,
        # and swap pandas' missing values (NaN) for None, which SQLite stores as NULL
        movies = df.reindex(columns=MOVIE_COLUMNS).astype(object)
        movies = movies.where(movies.notna(), None)
        rows = movies.values.tolist()

        connection = get_connection(self.db_path)
        try:
            connection.execute("DELETE FROM movies")
            sql_statement = """
            INSERT INTO movies (title, release_year, rating, genre)
            VALUES (?, ?, ?, ?)
            """
            connection.executemany(sql_statement, rows)
            connection.commit()
            logger.debug(f"Stored movies in SQLite: rows={len(rows)}")
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self):
        """Return the four movie columns as a DataFrame, ordered by id."""
        connection = get_connection(self.db_path)
        try:
            sql_statement = """
            SELECT title, release_year, rating, genre
            FROM movies ORDER BY id
            """
            rows = connection.execute(sql_statement).fetchall()
            df = pd.DataFrame([tuple(row) for row in rows], columns=MOVIE_COLUMNS)
            logger.debug(f"Loaded movies from SQLite: rows={len(df)}")
            return df
        finally:
            connection.close()

    def select_columns(self, columns, limit=5):
        """Return id plus the requested movie columns, ordered by id."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")

        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error(f"Unsupported column: {column}")
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            sql_statement = f"SELECT {selected_columns} FROM movies ORDER BY id LIMIT ?"
            rows = connection.execute(sql_statement, (limit,)).fetchall()
            records = [dict(row) for row in rows]
            logger.debug(f"Selected columns: columns={columns}, rows={len(records)}")
            return records
        finally:
            connection.close()

    def count_movies(self):
        """Return the number of stored movies using SQL COUNT(*)."""
        connection = get_connection(self.db_path)
        try:
            row = connection.execute("SELECT COUNT(*) AS total FROM movies").fetchone()
            logger.debug(f"Counted movies: total={row['total']}")
            return row["total"]
        finally:
            connection.close()

    def query_movies(self, columns, min_rating, limit):
        """Return selected fields from matching movies using SQL."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")

        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error(f"Unsupported column: {column}")
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            sql_statement = f"""
            SELECT {selected_columns} FROM movies
            WHERE rating >= ?
            ORDER BY rating DESC, id ASC
            LIMIT ?
            """
            rows = connection.execute(sql_statement, (min_rating, limit)).fetchall()
            records = [dict(row) for row in rows]
            logger.debug(f"Queried movies: columns={columns}, rows={len(records)}")
            return records
        finally:
            connection.close()