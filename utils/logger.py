import logging
import sys

def get_logger(name=None):
    logger = logging.getLogger(name or 'bot')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(name)s %(message)s'))
        logger.addHandler(handler)
    return logger