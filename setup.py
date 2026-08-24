from pathlib import Path

from setuptools import find_packages, setup

README = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="kustomize-to-helm",
    version="2.0.0",
    description="Fidelity-first, verified Kustomize to Helm migration framework",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Migration Framework",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "PyYAML>=6.0",
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "k2h=kustomize_to_helm.cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: System :: Systems Administration",
    ],
)
