import rclpy
from rclpy.node import Node
from turtlesim.msg import Pose
import math

class FakeTurtle(Node):
    def __init__(self):
        super().__init__('fake_turtle')
        self.pub = self.create_publisher(Pose, '/turtle1/pose', 10)
        self.timer = self.create_timer(0.1, self.tick)
        self.t = 0.0

    def tick(self):
        msg = Pose()
        # Daire çizen sahte turtle
        msg.x = 5.0 + 2.0 * math.cos(self.t)
        msg.y = 5.0 + 2.0 * math.sin(self.t)
        msg.theta = self.t
        msg.linear_velocity = 1.0
        msg.angular_velocity = 0.5
        self.pub.publish(msg)
        self.t += 0.05

def main(args=None):
    rclpy.init(args=args)
    node = FakeTurtle()
    rclpy.spin(node)
    rclpy.shutdown()
