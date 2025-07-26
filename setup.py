from setuptools import setup, find_packages

setup(
    name="MetPlot",
    version="0.1.2",
    author="Mohameme7",
    author_email="mohameme7@gmail.com",
    description="Meteorological plotting/downloading toolkit",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/mohameme7/metplot",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "beautifulsoup4==4.13.4",
        "cartopy",
        "customtkinter==5.2.2",
        "httpx==0.28.1",
        "matplotlib==3.10.3",
        "numpy==2.3.2",
        "Pillow==11.3.0",
        "pygrib==2.1.5",
        "requests==2.32.4",
        "scipy==1.16.0",
        "nicegui==2.21.1",
        "pywebview==5.4"
    ],
    python_requires=">=3.11",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Atmospheric Science",
        "Development Status :: 3 - Alpha"
    ],
    package_data={
        'MetPlot.wgrib': ['*.dll', '*.exe'],
    },
)
