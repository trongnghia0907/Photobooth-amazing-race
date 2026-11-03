import logging
import re


class ShareTokenFilter(logging.Filter):
    """Avoid leaking possession tokens through Uvicorn's default access log."""
    def filter(self, record):
        if record.name=='uvicorn.access' and isinstance(record.args,tuple) and len(record.args)>=3:
            args=list(record.args)
            args[2]=re.sub(r'/p/[^/?\s]+', '/p/[redacted]', str(args[2]))
            record.args=tuple(args)
        elif '/p/' in record.getMessage():
            record.msg=re.sub(r'/p/[^/?\s]+','/p/[redacted]',record.getMessage());record.args=()
        return True


def install_log_filter():
    logger=logging.getLogger('uvicorn.access')
    if not any(isinstance(item,ShareTokenFilter) for item in logger.filters):
        logger.addFilter(ShareTokenFilter())
