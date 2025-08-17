# Description
MetPlot is a library/tool that allows users to install meteorlogical data in a flexable way with various tools, and also there's a ready GUI App using it in the Repo that uses and abstracts its features.

# Installation
You can install it by Conda
`conda install mohameme7::metplot`

Or Build it by source:
   `conda build recipe`
   Then you can install it locally:
   `conda install --use-local metplot`

 And you can build the GUI to an executable From main.spec by:
   - Install Pyinstaller `pip install pyinstaller`
   - Then `pyinstaller main.spec`
   - Then run main.exe at the dist generated folder and everything should work fine.
   - # Note : For the GUI you must build MetPlot locally from the repo

# TODO
- ~~Add Functionality for GEM Model~~
- Add ECMWF Model
- Create documentation for adding models and making it a simpler process
- ~~Adding a size estimation for the downloaded files and a progressbar~~
