import logging
import sys

def setup_logger():
    logger = logging.getLogger('bot')
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(name)s %(message)s'))
    logger.addHandler(handler)
    return logger