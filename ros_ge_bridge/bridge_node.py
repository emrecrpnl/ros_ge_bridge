#!/usr/bin/env python3
"""
bridge_node.py
──────────────
ROS2 ↔ Godot 4.4 köprü düğümü.

Kontrol kanalı : TCP :9001  (discovery, subscribe/unsubscribe komutları)
Veri kanalı    : UDP :9000  (msgpack ile serialize edilmiş topic verisi)

Çalıştır:
    python3 bridge_node.py
    veya
    ros2 run <paket> bridge_node
"""

import json
import socket
import struct
import threading
import time
import traceback
from enum import IntEnum

import msgpack
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rosidl_runtime_py import message_to_ordereddict


# ══════════════════════════════════════════════════════════
# Protokol sabitleri
# ══════════════════════════════════════════════════════════

MAGIC = 0x5244          # "RD" — her pakette imza

# Kontrol mesaj tipleri (TCP) — Godot → Bridge
class CtrlCmd(IntEnum):
    DISCOVER_REQUEST = 0x01   # topic listesi iste
    SUBSCRIBE        = 0x02   # topic'e abone ol
    UNSUBSCRIBE      = 0x03   # aboneliği kes
    PUBLISH          = 0x04   # topic'e yayınla (Godot → ROS2)

# Kontrol mesaj tipleri (TCP) — Bridge → Godot
class CtrlResp(IntEnum):
    DISCOVER_RESPONSE = 0x81  # topic listesi cevabı
    ACK               = 0x82  # komut onayı
    ERROR             = 0x83  # hata

# Veri paketi tipi (UDP)
class DataMsg(IntEnum):
    STREAM_DATA = 0x10        # topic verisi

TCP_HOST = '0.0.0.0'
TCP_PORT = 9001
UDP_PORT = 9000

# ══════════════════════════════════════════════════════════
# Paket yardımcıları
# ══════════════════════════════════════════════════════════

# Header: magic(2) + msg_type(1) + payload_len(4) = 7 bayt
CTRL_HEADER_FMT  = '!HBI'
CTRL_HEADER_SIZE = struct.calcsize(CTRL_HEADER_FMT)  # 7

def pack_ctrl(msg_type: int, payload: bytes) -> bytes:
    """Kontrol paketi oluştur (TCP)."""
    header = struct.pack(CTRL_HEADER_FMT, MAGIC, msg_type, len(payload))
    return header + payload

def unpack_ctrl_header(data: bytes):
    """Header'ı çöz, (magic, msg_type, payload_len) döner."""
    return struct.unpack(CTRL_HEADER_FMT, data[:CTRL_HEADER_SIZE])

def pack_stream(topic: str, payload_bytes: bytes) -> bytes:
    """
    UDP veri paketi:
      magic(2) + type(1) + topic_len(1) + topic(N) + payload_len(4) + payload
    """
    topic_enc = topic.encode('utf-8')
    header = struct.pack(
        f'!HBB{len(topic_enc)}sI',
        MAGIC,
        DataMsg.STREAM_DATA,
        len(topic_enc),
        topic_enc,
        len(payload_bytes)
    )
    return header + payload_bytes


# ══════════════════════════════════════════════════════════
# ROS2 tip → sınıf yükleyici
# ══════════════════════════════════════════════════════════

def load_ros_msg_class(type_str: str):
    """
    'geometry_msgs/msg/Twist' → geometry_msgs.msg.Twist sınıfı
    Bulunamazsa None döner.
    """
    try:
        parts = type_str.split('/')   # ['geometry_msgs', 'msg', 'Twist']
        if len(parts) != 3:
            return None
        pkg, _, cls_name = parts
        module = __import__(f'{pkg}.msg', fromlist=[cls_name])
        return getattr(module, cls_name)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
# Ana Bridge Node
# ══════════════════════════════════════════════════════════

class BridgeNode(Node):
    def __init__(self):
        super().__init__('ros_godot_bridge')

        # topic_name → rclpy subscription nesnesi
        self._active_subs: dict[str, object] = {}
        self._subs_lock = threading.Lock()

        # UDP soketi — Godot'a veri gönderir
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._godot_udp_addr: tuple | None = None   # (ip, port) — TCP bağlantısından öğrenilir

        # TCP sunucusu — ayrı thread'de çalışır
        self._tcp_thread = threading.Thread(target=self._tcp_server, daemon=True)
        self._tcp_thread.start()

        self.get_logger().info('Bridge node başladı.')
        self.get_logger().info(f'  TCP kontrol : {TCP_HOST}:{TCP_PORT}')
        self.get_logger().info(f'  UDP veri    : → Godot:{UDP_PORT}')


    # ──────────────────────────────────────────────────────
    # TCP Sunucusu
    # ──────────────────────────────────────────────────────

    def _tcp_server(self):
        """Godot bağlantılarını dinler. Her bağlantı için ayrı thread açar."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((TCP_HOST, TCP_PORT))
        srv.listen(5)
        self.get_logger().info(f'TCP sunucu dinliyor: {TCP_PORT}')

        while True:
            try:
                conn, addr = srv.accept()
                self.get_logger().info(f'Godot bağlandı: {addr}')
                # UDP cevapları bu IP'ye gönderilecek
                self._godot_udp_addr = (addr[0], UDP_PORT)
                t = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True
                )
                t.start()
            except Exception:
                traceback.print_exc()

    def _handle_client(self, conn: socket.socket, addr):
        """Tek bir Godot bağlantısını yönetir."""
        try:
            while True:
                # Header oku
                raw = self._recv_exact(conn, CTRL_HEADER_SIZE)
                if not raw:
                    break

                magic, msg_type, payload_len = unpack_ctrl_header(raw)

                if magic != MAGIC:
                    self.get_logger().warning(f'Geçersiz magic: 0x{magic:04X}')
                    break

                # Payload oku
                payload = self._recv_exact(conn, payload_len) if payload_len > 0 else b''

                self._dispatch(conn, msg_type, payload)

        except Exception:
            traceback.print_exc()
        finally:
            self.get_logger().info(f'Godot bağlantısı kapandı: {addr}')
            conn.close()

    def _recv_exact(self, conn: socket.socket, n: int) -> bytes | None:
        """Tam olarak n bayt okur. Bağlantı kopunca None döner."""
        buf = b''
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    # ──────────────────────────────────────────────────────
    # Komut yönlendirici
    # ──────────────────────────────────────────────────────

    def _dispatch(self, conn: socket.socket, msg_type: int, payload: bytes):
        if msg_type == CtrlCmd.DISCOVER_REQUEST:
            self._cmd_discover(conn)

        elif msg_type == CtrlCmd.SUBSCRIBE:
            data = json.loads(payload.decode('utf-8'))
            self._cmd_subscribe(conn, data['topic'], data['type'])

        elif msg_type == CtrlCmd.UNSUBSCRIBE:
            data = json.loads(payload.decode('utf-8'))
            self._cmd_unsubscribe(conn, data['topic'])

        elif msg_type == CtrlCmd.PUBLISH:
            data = msgpack.unpackb(payload, raw=False)
            self._cmd_publish(data['topic'], data['type'], data['data'])
            self._send_ack(conn, data['topic'])

        else:
            self.get_logger().warning(f'Bilinmeyen komut: 0x{msg_type:02X}')
            self._send_error(conn, 'unknown_command')

    # ──────────────────────────────────────────────────────
    # DISCOVER — ROS2 topic listesi
    # ──────────────────────────────────────────────────────

    def _cmd_discover(self, conn: socket.socket):
        """
        Sistemdeki tüm topic'leri, tiplerini ve yönlerini listeler.
        direction: 'pub' = ROS2 yayınlıyor (Godot okur)
                   'sub' = ROS2 bekliyor  (Godot yazar)
                   'both' = her ikisi de var
        """
        topic_names_and_types = self.get_topic_names_and_types()

        # Hangi node'ların publisher/subscriber'ı var öğren
        publishers  = {}   # topic → [node_names]
        subscribers = {}

        for name, types in topic_names_and_types:
            pub_info = self.get_publishers_info_by_topic(name)
            sub_info = self.get_subscriptions_info_by_topic(name)
            publishers[name]  = [p.node_name for p in pub_info]
            subscribers[name] = [s.node_name for s in sub_info]

        topics = []
        for name, types in topic_names_and_types:
            has_pub = len(publishers.get(name, [])) > 0
            has_sub = len(subscribers.get(name, [])) > 0

            if has_pub and has_sub:
                direction = 'both'
            elif has_pub:
                direction = 'pub'    # ROS2 yayınlıyor → Godot abone olabilir
            else:
                direction = 'sub'    # ROS2 bekliyor   → Godot yayınlayabilir

            topics.append({
                'topic':     name,
                'type':      types[0] if types else 'unknown',
                'direction': direction,
                'active':    name in self._active_subs,
            })

        payload = json.dumps({'topics': topics}).encode('utf-8')
        conn.sendall(pack_ctrl(CtrlResp.DISCOVER_RESPONSE, payload))
        self.get_logger().info(f'Discovery: {len(topics)} topic gönderildi.')

    # ──────────────────────────────────────────────────────
    # SUBSCRIBE — dinamik abone ol
    # ──────────────────────────────────────────────────────

    def _cmd_subscribe(self, conn: socket.socket, topic: str, type_str: str):
        with self._subs_lock:
            if topic in self._active_subs:
                self._send_ack(conn, topic)
                return

            msg_class = load_ros_msg_class(type_str)
            if msg_class is None:
                self._send_error(conn, f'Tip yüklenemedi: {type_str}')
                return

            # Best-effort QoS — sensor verisi için uygun
            qos = QoSProfile(
                depth=10,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE
            )

            sub = self.create_subscription(
                msg_class,
                topic,
                lambda msg, t=topic: self._on_ros_msg(t, msg),
                qos
            )
            self._active_subs[topic] = sub

        self._send_ack(conn, topic)
        self.get_logger().info(f'Abone olundu: {topic} [{type_str}]')

    # ──────────────────────────────────────────────────────
    # UNSUBSCRIBE
    # ──────────────────────────────────────────────────────

    def _cmd_unsubscribe(self, conn: socket.socket, topic: str):
        with self._subs_lock:
            if topic in self._active_subs:
                self.destroy_subscription(self._active_subs.pop(topic))
                self.get_logger().info(f'Abonelik kaldırıldı: {topic}')
        self._send_ack(conn, topic)

    # ──────────────────────────────────────────────────────
    # PUBLISH — Godot → ROS2
    # ──────────────────────────────────────────────────────

    def _cmd_publish(self, topic: str, type_str: str, data: dict):
        msg_class = load_ros_msg_class(type_str)
        if msg_class is None:
            self.get_logger().error(f'Publish: tip yüklenemedi: {type_str}')
            return

        # Dict → ROS2 mesajı
        msg = msg_class()
        self._dict_to_msg(data, msg)

        # Tek seferlik publisher oluştur ve yayınla
        pub = self.create_publisher(msg_class, topic, 10)
        pub.publish(msg)
        self.get_logger().debug(f'Publish: {topic}')

    def _dict_to_msg(self, data: dict, msg):
        """Recursive dict → ROS2 mesaj alanlarına doldur."""
        for key, value in data.items():
            if hasattr(msg, key):
                attr = getattr(msg, key)
                if isinstance(value, dict):
                    self._dict_to_msg(value, attr)
                else:
                    try:
                        setattr(msg, key, value)
                    except Exception:
                        pass

    # ──────────────────────────────────────────────────────
    # ROS2 mesajı geldi → Godot'a UDP ile gönder
    # ──────────────────────────────────────────────────────

    def _on_ros_msg(self, topic: str, msg):
        if self._godot_udp_addr is None:
            return

        try:
            # ROS2 mesajı → OrderedDict → msgpack bytes
            msg_dict = message_to_ordereddict(msg)
            payload  = msgpack.packb(msg_dict, use_bin_type=True)
            packet   = pack_stream(topic, payload)
            self._udp_sock.sendto(packet, self._godot_udp_addr)
        except Exception:
            traceback.print_exc()

    # ──────────────────────────────────────────────────────
    # ACK / ERROR yardımcıları
    # ──────────────────────────────────────────────────────

    def _send_ack(self, conn: socket.socket, topic: str):
        payload = json.dumps({'status': 'ok', 'topic': topic}).encode('utf-8')
        conn.sendall(pack_ctrl(CtrlResp.ACK, payload))

    def _send_error(self, conn: socket.socket, reason: str):
        payload = json.dumps({'status': 'error', 'reason': reason}).encode('utf-8')
        conn.sendall(pack_ctrl(CtrlResp.ERROR, payload))

    # ──────────────────────────────────────────────────────
    # Temizlik
    # ──────────────────────────────────────────────────────

    def destroy_node(self):
        self._udp_sock.close()
        super().destroy_node()


# ══════════════════════════════════════════════════════════
# Giriş noktası
# ══════════════════════════════════════════════════════════

def main(args=None):
    rclpy.init(args=args)
    node = BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
