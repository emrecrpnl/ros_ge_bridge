from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='ros_ge_bridge',
            executable='fake_turtle',
            name='fake_turtle',
            output='screen'
        ),
        Node(
            package='ros_ge_bridge',
            executable='bridge_node',
            name='ros_ge_bridge',
            output='screen'
        ),
    ])
