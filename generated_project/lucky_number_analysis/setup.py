from setuptools import setup, find_packages

setup(
    name="lucky_number_analysis",
    version="0.1.0",
    description="FlowForge generated project for lucky_number_analysis",
    author="FlowForge",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "pyyaml>=6.0",
        "requests>=2.25.0",
    ],
    entry_points={
        'console_scripts': [
            'lucky_number_analysis=workflow.run:main',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
