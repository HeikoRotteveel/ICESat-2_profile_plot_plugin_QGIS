# ICESat-2 Profile Viewer (QGIS Plugin)

For my master thesis I needed a QGIS plugin for visualizing ICESat-2 point data. This plugin can plot a selection of the data as an along-track elevation profile.It generates an interactive cross-section plot where the points are colored based on their confidence. There is also the possibility to add optional overlay variables, and section highlighting (in this case water body highlighting).

---
## Install from ZIP

1.  Download the plugin as a `.zip` file
2.  Open QGIS → Plugins → Manage and Install Plugins
3.  Click **Install from ZIP**
4.  Select the `.zip` file
5.  Click **Install Plugin**

---
## Data preprocessing
This plugin does not automatically work on the HDF5 files provided by NASA. The data needs to be processed so that they can be loaded as vector layers in QGIS. The precise format does not matter, so the plugin works on file formats lke GeoParquet, GeoPackage, FlatGeoBuff, etc. Any numerical attributes can be added to the points and can be plotted. The minumum requirement is that the file contains points with a Latitude, Longitude and Height.  

---
## Usage
1. Load your ICESat-2 dataset (point layer)
2. Open the plugin
3. Configure the filed:
   * Latitude
   * Longitude
   * Height
   * Confidence (optional but recommended)
   * Water flag (or other feature you want to highlight)
4. (Optional) Add overlay fields:
   * Click: **"Add overlay field"**
   * Select numeric attributes
5. Click ▶ Plot profile

---
## Output
The plugin generates a profile plot with:

* **X-axis**: Along-track distance (meters)
* **Y-axis (left)**: Height (meters)
* **Y-axis (right)**: Overlay variables (multiple axes)

| **Element**         | **Description**                  |
|---------------------|----------------------------------|
| Colored points      | Elevation colored by confidence  |
| Diamond markers     | Water points                     |
| Blue shading        | Water regions                    |
| Lines               | Overlay variables                |
| Legend              | Optional, fully combined         |
