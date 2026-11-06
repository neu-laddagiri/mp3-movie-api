import logging


def setup_logging(verbose=False):
    """Turn on logging: DEBUG when verbose, otherwise INFO."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )