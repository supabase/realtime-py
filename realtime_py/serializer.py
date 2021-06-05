import json


class Serializer:
    HEADER_LENGTH = 1

    def decode(raw_payload):
        if type(raw_payload) == str:
            return json.loads(raw_payload)
