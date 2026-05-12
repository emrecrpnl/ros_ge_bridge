# ros_ge_bridge

**ROS2 ↔ Game Engine Gateway**

`ros_ge_bridge` is a ROS2 package that acts as a middleware gateway between ROS2 ecosystems and game engines (Godot, Unity, Unreal Engine). It allows game engines to communicate with ROS2 topics, manage nodes, and stream sensor data — all over a local network connection.

---

## Why?

Existing ROS2 simulation tools (Gazebo, Isaac Sim) focus on sensor simulation but lack photorealistic environment modeling. Game engines excel at realistic environments but have no native ROS2 support.

`ros_ge_bridge` fills this gap by providing:
- A stable, protocol-defined communication layer between ROS2 and any game engine
- Dynamic topic subscription and publishing without hardcoded message types
- Remote node lifecycle management from the game engine side
- A foundation for photorealistic robot simulation, synthetic training data generation, and RL environments

---

## Architecture

```
Game Engine (Godot / Unity / Unreal)
            │
            │  TCP :9001  (control channel)
            │  UDP :9000  (data stream)
            ▼
      ros_ge_bridge
        ├── Topic Manager    — subscribe / publish / list topics
        ├── Node Manager     — start / stop / monitor nodes
        ├── Stream Manager   — high-frequency UDP data relay
        └── ROS2 Interface   — dynamic message serialization
            │
            ▼
       ROS2 Ecosystem
```

**Control channel (TCP)** — Commands and responses. Discovery, subscribe/unsubscribe, node management.

**Data channel (UDP)** — High-frequency sensor data. Pose, IMU, LiDAR, camera frames.

---

## Features

### v1.0 (current)
- [x] Dynamic topic discovery — list all active topics with type and direction
- [x] Dynamic subscription — subscribe to any topic without restarting the bridge
- [x] Dynamic publishing — publish to any topic from the game engine
- [x] Automatic message serialization — all ROS2 message types supported via msgpack
- [x] UDP data streaming — low-latency sensor data relay
- [x] Local network operation (no authentication required)

### v1.5 (planned)
- [ ] Node lifecycle management — start, stop, monitor ROS2 nodes remotely
- [ ] Static token authentication + permission levels (read-only / full-control)
- [ ] Multi-client support
- [ ] Camera frame streaming (sensor_msgs/Image → UDP)

### v2.0 (planned)
- [ ] API key authentication
- [ ] Headless game engine support (offscreen render → ROS2 image topic)
- [ ] Sensor noise simulation layer (IMU drift, LiDAR dropout, motor backlash)
- [ ] TF2 transform relay

---

## Protocol

### Header (7 bytes, big-endian)

```
magic(2B) + msg_type(1B) + payload_len(4B)
```

`magic = 0x5244` ("RD") — identifies ros_ge_bridge packets.

### Control Messages (TCP)

| Direction | Type | Value | Payload |
|---|---|---|---|
| GE → Bridge | DISCOVER_REQUEST | 0x01 | empty |
| GE → Bridge | SUBSCRIBE | 0x02 | JSON `{topic, type}` |
| GE → Bridge | UNSUBSCRIBE | 0x03 | JSON `{topic}` |
| GE → Bridge | PUBLISH | 0x04 | msgpack `{topic, type, data}` |
| Bridge → GE | DISCOVER_RESPONSE | 0x81 | JSON `{topics[]}` |
| Bridge → GE | ACK | 0x82 | JSON `{status, topic}` |
| Bridge → GE | ERROR | 0x83 | JSON `{status, reason}` |

### Data Stream (UDP)

```
magic(2B) + type(1B) + topic_len(1B) + topic(NB) + payload_len(4B) + msgpack_payload
```

---

## Installation

### Requirements
- ROS2 Humble
- Python 3.10+
- `msgpack` Python package

```bash
# Install msgpack
pip3 install msgpack

# Clone into your ROS2 workspace
cd ~/ros2_ws/src
git clone https://github.com/yourusername/ros_ge_bridge.git

# Build
cd ~/ros2_ws
colcon build --symlink-install --packages-select ros_ge_bridge
source install/setup.bash
```

### Running with Docker / Podman

```bash
# Build image
docker build -t ros-ge-bridge .

# Run with host network (required for UDP)
docker run -it \
  --network=host \
  --name ros-ge-bridge \
  -v /your/workspace:/root/ws \
  ros-ge-bridge bash
```

---

## Usage

### Start the bridge

```bash
ros2 run ros_ge_bridge bridge_node
```

Or use the launch file to start bridge + a test publisher together:

```bash
ros2 launch ros_ge_bridge simulation.launch.py
```

### Connect from Godot

See [godot_ros_bridge](https://github.com/yourusername/godot_ros_bridge) for the Godot 4 client.

### Connect from Unity

Coming in a future release.

### Connect from Unreal Engine

Coming in a future release.

---

## Game Engine Clients

| Engine | Repository | Status |
|---|---|---|
| Godot 4 | [godot_ros_bridge](https://github.com/yourusername/godot_ros_bridge) | Active |
| Unity | unity_ros_bridge | Planned |
| Unreal Engine | unreal_ros_bridge | Planned |

---

## Tested With

- ROS2 Humble (Ubuntu 22.04)
- Godot 4.4
- Podman 4.x / Docker 24.x
- Fedora 43 (host)

---

## Roadmap

```
v1.0  Topic discovery, subscribe, publish, UDP stream     ← current
v1.5  Node lifecycle management, auth layer
v2.0  Camera streaming, sensor noise, TF2, headless GE
v3.0  Multi-robot, cloud deployment, RL training pipeline
```

---

## Contributing

This project is in early development. Contributions, issues, and discussions are welcome.

If you are implementing a client for a new game engine, feel free to open an issue to coordinate.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Author

Emre — CNC operator turning into a robotics software developer.
Building tools I wish existed when I started.
```
