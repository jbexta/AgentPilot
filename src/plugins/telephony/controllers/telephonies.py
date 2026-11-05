from core.managers.modules import ModulesController


class TelephoniesController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='telephonies',
            load_to_path='plugins.telephony.telephonies',
            class_based=True,
            inherit_from='Telephony',
            description="Phone call providers",
            long_description="Telephony modules place and receive phone calls through a carrier "
                             "and bridge them to the OpenAI SIP endpoint for live agents",
        )
