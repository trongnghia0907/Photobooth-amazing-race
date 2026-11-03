"""Private rotating logs. Never used as a public diagnostics API."""
import logging
from logging.handlers import RotatingFileHandler
from .logging_filters import ShareTokenFilter, install_log_filter


def configure(settings, role):
    install_log_filter()
    directory=settings.log_directory or settings.storage_root/'logs'
    directory.mkdir(parents=True,exist_ok=True)
    directory.chmod(0o700)
    path=directory/f'{role}.log'
    handler=RotatingFileHandler(path,maxBytes=5*1024*1024,backupCount=3,encoding='utf-8')
    path.chmod(0o600)
    handler.setLevel(settings.log_level.upper());handler.addFilter(ShareTokenFilter())
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    for name in ('uvicorn','uvicorn.access','app'):
        logging.getLogger(name).addHandler(handler)
    return handler
