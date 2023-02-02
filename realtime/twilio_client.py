from twilio.rest import Client as cli

class Client:
    account_sid = 'AC587bf00b58e91b1496cf98086e6ac507'
    auth_token = 'c542d44166359cc499d018d51a0a050b'
    def __init__(self):
        self.client = cli(self.account_sid, self.auth_token)

    def send_message(self, _to, msg):
        try:
            message = self.client.messages \
                            .create(
                                body=msg,
                                from_='+17819964562',
                                to=_to
                            )
            return message.sid
        except:
            return None
