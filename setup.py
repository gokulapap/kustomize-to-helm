from setuptools import setup, find_packages

setup(
    name="kustomize-to-helm",
    version="1.0.0",
    description="A framework to migrate Kustomize configurations to Helm charts",
    author="Migration Framework",
    packages=find_packages(),
    install_requires=[
        "PyYAML>=6.0",
        "click>=8.0",
        "jinja2>=3.0",
        "pathlib2>=2.3.7",
        "jsonschema>=4.0",
    ],
    entry_points={
        "console_scripts": [
            "k2h=kustomize_to_helm.cli:main",
        ],
    },
    python_requires=">=3.7",
)
