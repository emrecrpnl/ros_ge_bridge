# ros_ge_bridge Protocol Specification

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-05 | Initial specification |

---

## Overview

ros_ge_bridge uses two channels:

```
TCP :9001  →  Control channel (commands, responses)
UDP :9000  →  Data stream (sensor data, pose, etc.)
```

All multi-byte integers are **big-endian**.

---

## Versioning Policy

Version format: `MAJOR.MINOR`

- **MAJOR** change → breaking change, old clients will not work
- **MINOR** change → backward compatible, old clients keep working

Compatibility rule:
```
client.MAJOR == bridge.MAJOR  →  connect, warn if MINOR differs
client.MAJOR != bridge.MAJOR  →  reject connection, VERSION_ERROR
```

---

## Connection Sequence

```
GE                          Bridge
──                          ──────
TCP connect()         →
                      ←     (connection accepted)
HELLO {version}       →
                      ←     HELLO_ACK {version}   (if compatible)
                      ←     VERSION_ERROR          (if incompatible)
DISCOVER_REQUEST      →
                      ←     DISCOVER_RESPONSE {topics}
SUBSCRIBE {topic}     →
                      ←     ACK {topic}
                            (data flows via UDP)
UNSUBSCRIBE {topic}   →
                      ←     ACK {topic}
TCP disconnect()      →
```

---

## Control Channel (TCP)

### Header — 7 bytes

```
┌──────────┬──────────┬─────────────────────────┐
│ magic    │ msg_type │ payload_len             │
│ 2 bytes  │ 1 byte   │ 4 bytes                 │
│ 0x5244   │ enum     │ uint32 big-endian        │
└──────────┴──────────┴─────────────────────────┘
```

`magic = 0x5244` ("RD") identifies ros_ge_bridge packets.

---

### Message Types

#### GE → Bridge (Commands)

| Name | Value | Payload |
|---|---|---|
| HELLO | 0x00 | JSON `{"version": "1.0"}` |
| DISCOVER_REQUEST | 0x01 | empty |
| SUBSCRIBE | 0x02 | JSON `{"topic": "/name", "type": "pkg/msg/Type"}` |
| UNSUBSCRIBE | 0x03 | JSON `{"topic": "/name"}` |
| PUBLISH | 0x04 | msgpack `{"topic": "/name", "type": "pkg/msg/Type", "data": {...}}` |

#### Bridge → GE (Responses)

| Name | Value | Payload |
|---|---|---|
| HELLO_ACK | 0x80 | JSON `{"version": "1.0"}` |
| DISCOVER_RESPONSE | 0x81 | JSON `{"topics": [...]}` |
| ACK | 0x82 | JSON `{"status": "ok", "topic": "/name"}` |
| ERROR | 0x83 | JSON `{"status": "error", "reason": "..."}` |
| VERSION_ERROR | 0x84 | JSON `{"expected": "1.0", "got": "2.0"}` |

---

### DISCOVER_RESPONSE topic object

```json
{
  "topic": "/turtle1/pose",
  "type": "turtlesim/msg/Pose",
  "direction": "pub",
  "active": false
}
```

`direction` values:
- `pub` — ROS2 is publishing, GE can subscribe
- `sub` — ROS2 is subscribing, GE can publish
- `both` — both directions active

---

## Data Channel (UDP)

### Packet format

```
┌────────┬──────────┬───────────┬───────────────┬─────────────┬─────────┐
│ magic  │ msg_type │ topic_len │ topic         │ payload_len │ payload │
│ 2B     │ 1B       │ 1B        │ topic_len B   │ 4B          │ N B     │
│ 0x5244 │ 0x10     │ uint8     │ UTF-8 string  │ uint32      │ msgpack │
└────────┴──────────┴───────────┴───────────────┴─────────────┴─────────┘
```

### Data message types

| Name | Value |
|---|---|
| STREAM_DATA | 0x10 |

Payload is **msgpack** encoded ROS2 message as a dictionary.

Example for `turtlesim/msg/Pose`:
```json
{
  "x": 6.5,
  "y": 5.2,
  "theta": 1.3,
  "linear_velocity": 1.0,
  "angular_velocity": 0.5
}
```

---

## Error Codes

| Reason string | Meaning |
|---|---|
| `unknown_command` | Unrecognized msg_type byte |
| `type_load_failed` | ROS2 message type not found |
| `version_mismatch` | MAJOR version incompatible |
| `invalid_payload` | Payload could not be parsed |

---

## Implementation Notes

### Port configuration

Default ports can be overridden via ROS2 parameters:
```bash
ros2 run ros_ge_bridge bridge_node \
  --ros-args -p tcp_port:=9001 -p udp_port:=9000
```

### Network requirement

Bridge must run with `--network=host` in container environments
to avoid UDP port conflicts with container network stack (e.g. Podman pasta).

### msgpack types

All standard ROS2 message fields are supported:
- `bool`, `int8`–`int64`, `uint8`–`uint64`
- `float32`, `float64`
- `string`
- Fixed and variable length arrays
- Nested message types

Custom message types are supported as long as the package
is installed in the ROS2 environment.
