from src.operations.action import BaseAction, ActionInput, ActionSuccess
from twilio.rest import Client

from src.utils import api


# class Send_Email(BaseAction):
#     def __init__(self, agent):
#         super().__init__(agent, example='send an email to john')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Send an Email'
#         self.inputs = [
#             ActionInput('what_to_send'),
#             ActionInput('who_to_send_to'),
#             ActionInput('email_subject', required=False),
#             ActionInput('when_to_send', required=False, time_based=True)
#         ]
#         self.character_confirmation = True
#
#     def run_action(self):
#         # when_to_time_expression()
#         return True


class Send_SMS_Or_Text_Message(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='send sms')
        self.desc_prefix = 'requires me to'
        self.desc = 'Send an SMS'
        self.inputs.add('sms_message_to_send')
        self.inputs.add('phone_number_to', required=False)

    def run_action(self):
        try:
            # Your Twilio Account SID and Auth Token, which can be found in your account settings on the Twilio dashboard
            account_sid = api.apis['twilio']['client_key']
            auth_token = api.apis['twilio']['priv_key']
            client = Client(account_sid, auth_token)

            # Fetching the user inputs
            message = self.inputs.get(0).value
            phone_number = self.inputs.get(1).value

            if phone_number == '':
                phone_number = '+447709033212'
            # is_valid_phone_number = False  # self.validate_phone_number(phone_number)
            # if not is_valid_phone_number:
            #     yield ActionResult(f"[ERR]Invalid phone number: {phone_number}")

            # Sending the SMS
            client.messages.create(
                body=message.strip('"'),
                from_='+447723364458',
                to=phone_number)

            yield ActionSuccess("[SAY]Message sent successfully.")
        except Exception as e:
            yield ActionSuccess("[SAY]There was an error sending the message.")
