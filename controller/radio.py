"""Authorized, bounded physical RF provider; defaults to disabled until setup passes."""
from tellstick_local.transmit import RFClient,RFError,RFUncertainError,waveform


class RadioProvider:
    def __init__(self,store):self.store=store

    def __call__(self,device,method,value,repeats):
        if not (self.store.setting('rf_authorized',False) and self.store.setting('rf_enabled',False)):
            return 'blocked','Physical RF control is held until firmware/control validation completes'
        try:waveform(device,method,value,repeats)
        except RFError:return 'failed','Device parameters or method are not supported'
        client=RFClient(self.store.setting('target','192.168.1.193'),bind_address=self.store.setting('bind','192.168.1.149'))
        try:client.probe()
        except (RFError,OSError):return 'offline','RF firmware did not answer the non-transmitting probe'
        try:client.send(device,method,value,repeats)
        except RFUncertainError:return 'unknown','Command sent but firmware acknowledgment missing; not replayed'
        except RFError:return 'failed','Firmware rejected the transmit request'
        except OSError:return 'unknown','Transmit delivery is uncertain; not replayed'
        return 'sent','Firmware completed RF transmission; receiver state is unconfirmed'
