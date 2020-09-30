#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    readme = readme_file.read()

history = ""

requirements = ['websockets==8.1']

setup_requirements = [ ]

test_requirements = [ ]

setup(
    author="Lionell Loh",
    author_email='lionellloh@gmail.com',
    python_requires='>=3.5',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    description="Python Client for Phoenix Channels",
    install_requires=requirements,
    license="MIT license",
    long_description=readme + '\n\n' + history,
    include_package_data=True,
    keywords='realtime-py',
    name='realtime-py',
    packages=find_packages(include=['realtime', 'realtime_py.*', 'phoenix channels', 'phoenix', 'channels', 'websocket']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/lionellloh/realtime-py',
    version='0.1.0',
    zip_safe=False,
)
