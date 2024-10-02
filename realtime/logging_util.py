import copy
import logging
import re

# redaction regex for detecting JWT tokens
# <header>.<payload>.<signature>
# character set [a-zA-Z0-9_-]
# \w covers [a-zA-Z0-9]
redact = r"(eyJh[-_\w]*\.)([-_\w]*)\."


def gred(g):
    """Redact the payload of the JWT, keeping the header and signature"""
    return f"{g.group(1)}REDACTED." if len(g.groups()) > 1 else g


class TokenMaskingFilter(logging.Filter):
    """Mask access_tokens in logs"""

    def filter(self, record):
        record.msg = self.sanitize_line(record.msg)
        record.args = self.sanitize_args(record.args)
        return True

    @staticmethod
    def sanitize_args(d):
        if isinstance(d, dict):
            d = d.copy()  # so we don't overwrite anything
            for k, v in d.items():
                d[k] = self.sanitize_line(v)
        elif isinstance(d, tuple):
            # need a deepcopy of tuple turned to a list, as to not change the original values
            # otherwise we end up changing the items at the original memory location of the passed in tuple
            y = copy.deepcopy(list(d))
            for x, value in enumerate(y):
                if isinstance(value, str):
                    y[x] = re.sub(redact, gred, value)
            return tuple(y)  # convert the list back to a tuple
        return d

    @staticmethod
    def sanitize_line(line):
        return re.sub(redact, gred, line)
