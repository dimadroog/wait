"""FCEUX bridge IPC transports (v1 JSON files, v2 binary inline obs)."""
from __future__ import annotations

import json
import os
import struct
from typing import Any

V2_REQ_MAGIC = b"WQST"
V2_RESP_MAGIC = b"WAIT"
V2_HEADER = struct.Struct("<4sIBH")  # magic, seq, ok, json_len
V2_OBS_LEN = struct.Struct("<I")


def resolve_ipc_transport(value: str | None = None) -> str:
    """CLI/env override; train default v1 — см. fceux/profiles/train.yaml."""
    if value:
        return value.strip().lower()
    env = os.environ.get("WAIT_FCEUX_IPC")
    if env:
        return env.strip().lower()
    return "v1"


def encode_request_v2(seq: int, cmd: str, arg: str = "") -> bytes:
    cmd_b = cmd.encode("utf-8")
    arg_b = arg.encode("utf-8")
    if len(cmd_b) > 255:
        raise ValueError("cmd too long for v2 IPC")
    if len(arg_b) > 65535:
        raise ValueError("arg too long for v2 IPC")
    return V2_REQ_MAGIC + struct.pack("<IBH", seq, len(cmd_b), len(arg_b)) + cmd_b + arg_b


def decode_request_v2(data: bytes) -> dict[str, Any]:
    if len(data) < 11 or data[:4] != V2_REQ_MAGIC:
        raise ValueError("invalid v2 request")
    seq, cmd_len, arg_len = struct.unpack("<IBH", data[4:11])
    pos = 11
    cmd = data[pos : pos + cmd_len].decode("utf-8")
    pos += cmd_len
    arg = data[pos : pos + arg_len].decode("utf-8")
    return {"seq": seq, "cmd": cmd, "arg": arg}


def encode_response_v2(seq: int, ok: bool, fields: dict[str, Any], obs: bytes | None = None) -> bytes:
    response_fields = dict(fields)
    response_fields.pop("obs_file", None)
    payload = json.dumps(response_fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 65535:
        raise ValueError("v2 response json too large")
    obs_blob = obs or b""
    return (
        V2_RESP_MAGIC
        + struct.pack("<IBH", seq, 1 if ok else 0, len(payload))
        + payload
        + V2_OBS_LEN.pack(len(obs_blob))
        + obs_blob
    )


def decode_response_v2(data: bytes) -> dict[str, Any]:
    if len(data) < 15 or data[:4] != V2_RESP_MAGIC:
        raise ValueError("invalid v2 response")
    seq, ok_byte, json_len = struct.unpack("<IBH", data[4:11])
    pos = 11
    response_fields = json.loads(data[pos : pos + json_len].decode("utf-8"))
    pos += json_len
    obs_len = V2_OBS_LEN.unpack_from(data, pos)[0]
    pos += 4
    obs = data[pos : pos + obs_len] if obs_len else b""
    out: dict[str, Any] = dict(response_fields)
    out["seq"] = seq
    out["ok"] = bool(ok_byte)
    if obs:
        out["obs_inline"] = True
        out["_obs_bytes"] = obs
    return out
