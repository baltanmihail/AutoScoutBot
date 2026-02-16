import logging


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    encoding="utf-8",
)
logger = logging.getLogger(__name__)