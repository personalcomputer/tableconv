import subprocess
import datetime
import json

import pandas as pd
import yaml

from tableconv.exceptions import SourceParseError
from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin



# TSHARK-based Implementation:

@register_adapter(["pcap", "pcapng"], read_only=True)
class PcapAdapter(FileAdapterMixin, Adapter):

    @staticmethod
    def load_file(scheme, path, params):
        impl = params.get('implementation', params.get('impl', 'tshark'))
        if impl == 'tshark':
            records = tshark_load(path)
        elif impl == 'scapy':
            records = scapy_load(path)
        else:
            raise InvalidParamsError('valid options for ?impl= are tshark or scapy')
        return pd.json_normalize(records)


def tshark_load(path):
    proc = subprocess.run(['tshark', '-r', path, '-T', 'json'], capture_output=True, check=True, text=True)
    records = []
    for record in json.loads(proc.stdout):
        new_record = {}
        for value in record['_source']['layers'].values():
            for key, subvalue in list(value.items()):
                if key == 'Timestamps':
                    value = {**value, **subvalue}
                    del value[key]
            new_record = {**new_record, **value}
        # records.append(record)  # [for debug]
        records.append(new_record)
    return records


def scapy_load(path):
    from scapy.all import rdpcap
    from scapy.fields import ConditionalField
    from scapy.packet import Packet
    from scapy.base_classes import SetGen

    def scapy_layer_to_dict(packet, top_layer=False):
        record = {}
        if top_layer:
            record['timestamp'] = datetime.datetime.fromtimestamp(float(packet.time), tz=datetime.timezone.utc)
        # record['layer_name'] = packet.name
        for f in packet.fields_desc:
            if isinstance(f, ConditionalField) and not f._evalcond(packet):
                continue
            fvalue = packet.getfieldval(f.name)
            if isinstance(fvalue, Packet) or (f.islist and f.holds_packets and isinstance(fvalue, list)):  # noqa: E501
                fvalue_gen = SetGen(
                    fvalue,
                    _iterpacket=0
                )  # type: SetGen[Packet]
                record[f.name] = [scapy_layer_to_dict(fvalue) for fvalue in fvalue_gen]
            else:
                record[f.name] = f.i2repr(packet, fvalue)
        if packet.payload:
            record[packet.payload.name.lower()] = scapy_layer_to_dict(packet.payload)
        return record

    records = []
    packets = rdpcap(path)
    for packet in packets:
        records.append(scapy_layer_to_dict(packet, top_layer=True))
    return records


