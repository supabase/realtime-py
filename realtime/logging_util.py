import logging
import re

# redaction regex for detecting JWT tokens
# <header>.<payload>.<signature>
# character set [a-zA-Z0-9_-]
# \w covers [a-zA-Z0-9]
redact = r"(eyJh[-_\w]*\.)([-_\w]*)\."


class TokenMaskingFilter(logging.Filter):
    """Mask access_tokens in logs"""

    def filter(self, record):
        record.msg = self.sanitize_line(record.msg)
        return True

    @staticmethod
    def sanitize_line(line):
        def gred(g):
            """Redact the payload of the JWT, keeping the header and signature"""
            return f"{g.group(1)}REDACTED." if len(g.groups()) > 1 else g

        return re.sub(redact, gred, line)
