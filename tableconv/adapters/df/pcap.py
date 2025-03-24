import json
import os
import subprocess
import sys
from io import IOBase

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import InvalidParamsError
from tableconv.uri import parse_uri


@register_adapter(["pcap", "pcapng"], read_only=True)
class PcapAdapter(FileAdapterMixin, Adapter):
    @classmethod
    def load(cls, uri: str, query: str | None) -> pd.DataFrame:
        parsed_uri = parse_uri(uri)
        if parsed_uri.authority == "-" or parsed_uri.path == "-" or parsed_uri.path == "/dev/fd/0":
            path: str | IOBase = sys.stdin  # type: ignore[assignment]
        else:
            path = os.path.expanduser(parsed_uri.path)
        params = parsed_uri.query

        impl = params.get("implementation", params.get("impl", "tshark"))
        if impl == "tshark":
            records = tshark_load(path, query)  # type: ignore[attr-defined]
            df = pd.json_normalize(records)
            return df
        # elif impl == "scapy":
        #     records = scapy_load(path)
        #     df = pd.json_normalize(records)
        #     return cls._query_in_memory(df, query)
        else:
            raise InvalidParamsError("valid options for ?impl= are tshark or scapy")


def walk_pcap_dict(new_record, data):
    for key, value in data.items():
        if key.startswith("_ws."):
            continue
        if isinstance(value, dict):
            walk_pcap_dict(new_record, value)
            continue
        new_record[key] = value


def tshark_load(path, query=None):
    query_args = ["-Y", query] if query else []
    proc = subprocess.run(
        ["tshark", "-N", "dnN", "-r", path, "-T", "json"] + query_args, capture_output=True, check=True, text=True
    )
    records = []
    for record in json.loads(proc.stdout):
        new_record = {}
        walk_pcap_dict(new_record, record["_source"]["layers"])
        records.append(new_record)
    return records


# def scapy_load(path):
#     from scapy.all import rdpcap  # inlined for startup performance
#     from scapy.base_classes import SetGen
#     from scapy.fields import ConditionalField
#     from scapy.packet import Packet
#
#     def scapy_layer_to_dict(packet, top_layer=True):
#         record = {}
#         if top_layer:
#             record["timestamp"] = datetime.datetime.fromtimestamp(float(packet.time), tz=datetime.UTC)
#         # record['layer_name'] = packet.name
#         for f in packet.fields_desc:
#             if isinstance(f, ConditionalField) and not f._evalcond(packet):
#                 continue
#             fvalue = packet.getfieldval(f.name)
#             if isinstance(fvalue, Packet) or (f.islist and f.holds_packets and isinstance(fvalue, list)):
#                 fvalue_gen = SetGen(fvalue, _iterpacket=0)
#                 record[f.name] = [scapy_layer_to_dict(fvalue, top_layer=False) for fvalue in fvalue_gen]
#             else:
#                 record[f.name] = f.i2repr(packet, fvalue)
#         if packet.payload:
#             record[packet.payload.name.lower()] = scapy_layer_to_dict(packet.payload, top_layer=False)
#         return record
#
#     records = []
#     packets = rdpcap(path)
#     for packet in packets:
#         records.append(scapy_layer_to_dict(packet))
#     return records
