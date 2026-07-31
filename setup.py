from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = [
        line
        for line in f.read().strip().split("\n")
        if line and not line.startswith("#") and line != "frappe"
    ]

setup(
    name="dcr",
    version="0.0.1",
    description="Dealer Capital Resources — Home Builder Lending Platform",
    author="DCR",
    author_email="hello@example.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    package_data={
        "dcr": [
            "*.txt",
            "fixtures/*.json",
            "public/css/*.css",
            "public/js/*.js",
            "public/html/*.html",
            "public/images/*.png",
            "public/images/*.svg",
            "public/images/*.ico",
            "www/*.html",
            "www/*.css",
            "www/*.js",
            "dcr/doctype/*/*.json",
            "dcr/report/*/*.json",
            "dcr/print_format/*/*.json",
            "dcr/dashboard_chart_source/*/*.json",
            "dcr/dashboard_chart_source/*/*.js",
        ],
    },
    install_requires=install_requires,
)
