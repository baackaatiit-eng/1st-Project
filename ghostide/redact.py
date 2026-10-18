import logging
import re

_PATTERNS = [re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"), re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")]
_secrets = set()


def register(*secrets):
    _secrets.update(s for s in secrets if s and len(s) >= 6)


def redact(text):
    text = str(text)
    for s in _secrets:
        text = text.replace(s, "***")
    for p in _PATTERNS:
        text = p.sub("***", text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup_logging(path=None):
    h = [logging.StreamHandler()]
    if path:
        h.append(logging.FileHandler(path))
    for x in h:
        x.addFilter(RedactFilter())
    logging.basicConfig(level=logging.INFO, handlers=h, force=True,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
