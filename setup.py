from setuptools import setup, find_packages

setup(
    name="quantumbot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'Flask>=2.3.0',
        'python-dotenv>=1.0.0',
        'requests>=2.31.0',
        'cryptography>=41.0.0',
        'openpyxl>=3.1.0',
        'APScheduler>=3.10.0',
        'python-telegram-bot>=20.6',
        'numpy>=1.24.0',
    ],
)
