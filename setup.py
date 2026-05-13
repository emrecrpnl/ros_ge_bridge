from setuptools import setup
import os
from glob import glob

package_name = 'ros_ge_bridge'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='emre',
    maintainer_email='emre@todo.todo',
    description='ROS2 Game Engine Gateway',
    license='MIT',
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    entry_points={
        'console_scripts': [
            'bridge_node = ros_ge_bridge.bridge_node:main',
            'fake_turtle = ros_ge_bridge.turtle_sim_fake:main',
        ],
    },
)
