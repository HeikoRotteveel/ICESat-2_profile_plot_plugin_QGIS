"""
ICESat-2 Profile Viewer
Plots selected features as a height cross-section, colored by confidence.
Overlay fields are plotted as lines with individual twin y-axes.
Water body regions are highlighted as a shaded band + diamond markers.

Thanks to the great documentation provided by QGIS: https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/plugins/index.html

Author: H.B. Rotteveel
Date: 28/03/2026
"""

import math
import numpy as np

from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QCheckBox,
    QGroupBox, QSizePolicy, QSpinBox,
    QScrollArea, QToolButton
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.lines as mlines
import matplotlib.patches as mpatches

# Helper functions
def haversine_meters(lat1, lon1, lat2, lon2):
    R = 6_371_008.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def cumulative_distance(lats, lons):
    dist = [0.0]
    for i in range(1, len(lats)):
        dist.append(dist[-1] + haversine_meters(lats[i - 1], lons[i - 1], lats[i], lons[i]))
    return np.array(dist)

# Color map used based on ICESat-2 variables
CONF_COLORS = {
    -1: "#9e9e9e",   # grey       — invalid
     0: "#e0e0e0",   # light grey — noise
     1: "#ffeb3b",   # yellow     — low
     2: "#ff9800",   # orange     — medium
     3: "#4caf50",   # green      — high
     4: "#00bcd4",   # cyan       — very high
}

CONF_LABELS = {
    -1: "-1  invalid",
     0:  "0  noise",
     1:  "1  low",
     2:  "2  medium",
     3:  "3  high",
     4:  "4  very high",
}

# Cycling palette for overlay lines
OVERLAY_PALETTE = [
    "#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff",
    "#f08cff", "#ff9f43", "#48dbfb", "#ff9ff3",
]

# Used to identify different possible names that people might use for their fields
def _find_field(fields, candidates):
    names = {f.name().lower(): f.name() for f in fields}
    for c in candidates:
        if c.lower() in names:
            return names[c.lower()]
    return None


CONFIDENCE_CANDIDATES = [
    "confidence", "conf", "signal_conf_ph", "signal_conf_land",
    "signal_confidence", "quality_ph", "quality"
]
HEIGHT_CANDIDATES = [
    "height", "h", "z", "elevation", "elev", "h_ph",
    "h_te_best_fit", "h_li", "h_mean", "h_canopy"
]
LAT_CANDIDATES  = ["lat", "latitude", "y", "lat_ph"]
LON_CANDIDATES  = ["lon", "longitude", "x", "lon_ph"]
WATER_CANDIDATES = [
    "water", "water_body", "is_water", "inland_water",
    "water_flag", "segment_watermask", "lake_flag"
]



# Overlay row widget
class OverlayFieldRow(QWidget):
    """Checkbox + field selector + remove button for one overlay line."""

    def __init__(self, field_names, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(4)

        self.enabled_cb = QCheckBox()
        self.enabled_cb.setChecked(True)
        self.enabled_cb.setToolTip("Enable/disable this overlay")
        lay.addWidget(self.enabled_cb)

        self.field_combo = QComboBox()
        self.field_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for name in field_names:
            self.field_combo.addItem(name, name)
        lay.addWidget(self.field_combo)

        self.remove_btn = QToolButton()
        self.remove_btn.setText("✕")
        self.remove_btn.setFixedWidth(22)
        self.remove_btn.setToolTip("Remove this overlay")
        lay.addWidget(self.remove_btn)

    def field_name(self):
        return self.field_combo.currentData()

    def is_enabled(self):
        return self.enabled_cb.isChecked()



# Main dock
class ProfileDockWidget(QDockWidget):
    def __init__(self, iface):
        super().__init__("ICESat-2 Profile Viewer")
        self.iface = iface
        self.setMinimumWidth(540)
        self.setObjectName("ICESat2ProfileDock")
        self._overlay_rows = []

        # Outer scroll so controls stay accessible when the dock is narrow
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(scroll)

        main = QWidget()
        scroll.setWidget(main)
        outer = QVBoxLayout(main)
        outer.setSpacing(6)
        outer.setContentsMargins(8, 8, 8, 8)

        # Data source
        src_box = QGroupBox("Data source")
        src_lay = QVBoxLayout(src_box)
        src_lay.setSpacing(4)

        row_layer = QHBoxLayout()
        row_layer.addWidget(QLabel("Layer:"))
        self.layer_combo = QComboBox()
        self.layer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_layer.addWidget(self.layer_combo)
        ref_btn = QPushButton("↺")
        ref_btn.setFixedWidth(28)
        ref_btn.setToolTip("Refresh layer list")
        ref_btn.clicked.connect(self._populate_layers)
        row_layer.addWidget(ref_btn)
        src_lay.addLayout(row_layer)

        def field_row(label):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setMinimumWidth(115)
            row.addWidget(lbl)
            combo = QComboBox()
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row.addWidget(combo)
            src_lay.addLayout(row)
            return combo

        self.lat_combo   = field_row("Latitude field:")
        self.lon_combo   = field_row("Longitude field:")
        self.h_combo     = field_row("Height field:")
        self.conf_combo  = field_row("Confidence field:")
        self.water_combo = field_row("Water flag field:")

        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)

        self.sel_only_cb = QCheckBox("Plot selected features only  (uncheck = all visible)")
        self.sel_only_cb.setChecked(True)
        src_lay.addWidget(self.sel_only_cb)

        outer.addWidget(src_box)

        # Overlay lines
        ov_box = QGroupBox("Overlay lines  (each gets its own right-hand y-axis)")
        ov_lay = QVBoxLayout(ov_box)
        ov_lay.setSpacing(4)

        hint = QLabel("Add numeric attributes to overlay as lines on the profile.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 8pt;")
        ov_lay.addWidget(hint)

        self.overlay_container = QWidget()
        self.overlay_container_lay = QVBoxLayout(self.overlay_container)
        self.overlay_container_lay.setContentsMargins(0, 0, 0, 0)
        self.overlay_container_lay.setSpacing(2)
        ov_lay.addWidget(self.overlay_container)

        add_btn = QPushButton("＋  Add overlay field")
        add_btn.clicked.connect(self._add_overlay_row)
        ov_lay.addWidget(add_btn)

        outer.addWidget(ov_box)

        # Display options
        disp_box = QGroupBox("Display options")
        disp_lay = QHBoxLayout(disp_box)
        disp_lay.setSpacing(10)

        self.show_water_cb = QCheckBox("Highlight water regions")
        self.show_water_cb.setChecked(True)
        disp_lay.addWidget(self.show_water_cb)

        self.show_legend_cb = QCheckBox("Legend")
        self.show_legend_cb.setChecked(True)
        disp_lay.addWidget(self.show_legend_cb)

        disp_lay.addWidget(QLabel("Point size:"))
        self.pt_size_spin = QSpinBox()
        self.pt_size_spin.setRange(1, 20)
        self.pt_size_spin.setValue(5)
        disp_lay.addWidget(self.pt_size_spin)

        outer.addWidget(disp_box)

        # Plot button & status
        self.plot_btn = QPushButton("▶  Plot profile")
        self.plot_btn.setFixedHeight(34)
        f = self.plot_btn.font(); f.setBold(True); self.plot_btn.setFont(f)
        self.plot_btn.clicked.connect(self.plot_profile)
        outer.addWidget(self.plot_btn)

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.status_lbl)

        # Canvas
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setMinimumHeight(320)
        outer.addWidget(self.canvas)

        self.toolbar = NavigationToolbar(self.canvas, main)
        outer.addWidget(self.toolbar)

        # Init
        self._populate_layers()
        QgsProject.instance().layersAdded.connect(self._populate_layers)
        QgsProject.instance().layersRemoved.connect(self._populate_layers)

    # Layer helpers
    def _populate_layers(self):
        prev = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.VectorLayer:
                self.layer_combo.addItem(layer.name(), layer.id())
        idx = self.layer_combo.findData(prev)
        if idx >= 0:
            self.layer_combo.setCurrentIndex(idx)
        self.layer_combo.blockSignals(False)
        self._on_layer_changed()

    def _on_layer_changed(self):
        layer = self._current_layer()
        if layer is None:
            return
        fields = layer.fields()

        def populate(combo, candidates):
            combo.clear()
            combo.addItem("(none)", "")
            auto = _find_field(fields, candidates)
            for f in fields:
                combo.addItem(f.name(), f.name())
            if auto:
                i = combo.findData(auto)
                if i >= 0:
                    combo.setCurrentIndex(i)

        populate(self.lat_combo,   LAT_CANDIDATES)
        populate(self.lon_combo,   LON_CANDIDATES)
        populate(self.h_combo,     HEIGHT_CANDIDATES)
        populate(self.conf_combo,  CONFIDENCE_CANDIDATES)
        populate(self.water_combo, WATER_CANDIDATES)

        # Refresh existing overlay rows' field lists
        field_names = [f.name() for f in fields]
        for row in self._overlay_rows:
            cur = row.field_name()
            row.field_combo.blockSignals(True)
            row.field_combo.clear()
            for name in field_names:
                row.field_combo.addItem(name, name)
            i = row.field_combo.findData(cur)
            if i >= 0:
                row.field_combo.setCurrentIndex(i)
            row.field_combo.blockSignals(False)

    def _current_layer(self):
        lid = self.layer_combo.currentData()
        return QgsProject.instance().mapLayer(lid) if lid else None

    # Overlay rows

    def _add_overlay_row(self):
        layer = self._current_layer()
        if not layer:
            self._status("⚠ Select a layer first.", error=True)
            return
        field_names = [f.name() for f in layer.fields()]
        row = OverlayFieldRow(field_names, self.overlay_container)
        row.remove_btn.clicked.connect(lambda: self._remove_overlay_row(row))
        self._overlay_rows.append(row)
        self.overlay_container_lay.addWidget(row)

    def _remove_overlay_row(self, row):
        self._overlay_rows.remove(row)
        self.overlay_container_lay.removeWidget(row)
        row.deleteLater()

    # Plot

    def plot_profile(self):
        layer = self._current_layer()
        if layer is None:
            self._status("⚠ No layer selected.", error=True)
            return

        lat_f   = self.lat_combo.currentData()
        lon_f   = self.lon_combo.currentData()
        h_f     = self.h_combo.currentData()
        conf_f  = self.conf_combo.currentData()
        water_f = self.water_combo.currentData()

        if not lat_f or not lon_f or not h_f:
            self._status("⚠ Please set Latitude, Longitude and Height fields.", error=True)
            return

        overlay_fields = [
            r.field_name() for r in self._overlay_rows
            if r.is_enabled() and r.field_name()
        ]

        # Gather features
        if self.sel_only_cb.isChecked():
            features = list(layer.selectedFeatures())
            if not features:
                self._status("⚠ No features selected.", error=True)
                return
        else:
            features = list(layer.getFeatures())

        if not features:
            self._status("⚠ No features found.", error=True)
            return

        # Extract attributes
        lats, lons, heights, confs, waters = [], [], [], [], []
        overlay_vals = {f: [] for f in overlay_fields}

        for feat in features:
            try:
                lat = float(feat[lat_f])
                lon = float(feat[lon_f])
                h   = float(feat[h_f])
            except (TypeError, ValueError):
                continue

            lats.append(lat); lons.append(lon); heights.append(h)
            confs.append(int(feat[conf_f]) if conf_f else 0)

            if water_f:
                try:
                    w = feat[water_f]
                    waters.append(bool(int(w)) if w is not None else False)
                except (TypeError, ValueError):
                    waters.append(False)
            else:
                waters.append(False)

            for of in overlay_fields:
                try:
                    overlay_vals[of].append(float(feat[of]))
                except (TypeError, ValueError):
                    overlay_vals[of].append(float("nan"))

        if not lats:
            self._status("⚠ Could not extract any valid points.", error=True)
            return

        # Sort along-track by latitude
        order   = np.argsort(lats)
        lats    = [lats[i]  for i in order]
        lons    = [lons[i]  for i in order]
        heights = np.array([heights[i] for i in order])
        confs   = np.array([confs[i]   for i in order])
        waters  = np.array([waters[i]  for i in order], dtype=bool)
        for of in overlay_fields:
            overlay_vals[of] = np.array([overlay_vals[of][i] for i in order])

        dist_m = cumulative_distance(lats, lons)
        n_ov   = len(overlay_fields)

        # Figure margins — widen right side for each twin axis
        right = max(0.78 - (n_ov - 1) * 0.09, 0.50) if n_ov > 0 else 0.93
        self.figure.clear()
        self.figure.subplots_adjust(left=0.09, right=right, top=0.91, bottom=0.10)
        ax = self.figure.add_subplot(111)
        self._style_ax(ax)

        pt_size = self.pt_size_spin.value()

        # Water region shading (background)
        if self.show_water_cb.isChecked() and water_f and waters.any():
            in_water  = False
            seg_start = 0.0
            for i, w in enumerate(waters):
                if w and not in_water:
                    seg_start = dist_m[i]
                    in_water  = True
                elif not w and in_water:
                    ax.axvspan(seg_start, dist_m[i - 1],
                               color="#1a6fa8", alpha=0.18, zorder=1, linewidth=0)
                    in_water = False
            if in_water:
                ax.axvspan(seg_start, dist_m[-1],
                           color="#1a6fa8", alpha=0.18, zorder=1, linewidth=0)

        # Elevation scatter coloured by confidence
        legend_handles = []
        legend_labels  = []

        for cv in sorted(set(confs.tolist())):
            color = CONF_COLORS.get(cv, "#ffffff")
            label = CONF_LABELS.get(cv, str(cv))
            mask  = confs == cv
            sc = ax.scatter(
                dist_m[mask], heights[mask],
                c=color, s=pt_size ** 1.6,
                marker="o", edgecolors="none", linewidths=0, zorder=3
            )
            legend_handles.append(sc)
            legend_labels.append(label)

        # Water point markers (diamond outline)
        if self.show_water_cb.isChecked() and water_f and waters.any():
            ax.scatter(
                dist_m[waters], heights[waters],
                c="none", s=(pt_size * 1.7) ** 1.6,
                marker="D", edgecolors="#7ecfff",
                linewidths=0.9, zorder=5
            )
            wh = mlines.Line2D(
                [], [], color="#7ecfff", marker="D",
                markerfacecolor="none", markeredgewidth=0.9,
                linestyle="None", markersize=6
            )
            legend_handles.append(wh)
            legend_labels.append("water point")

        ax.set_xlabel("Along-track distance (m)", fontsize=9, color="#cccccc")
        ax.set_ylabel("Height (m)",               fontsize=9, color="#cccccc")
        ax.set_title(
            f"ICESat-2 Elevation Profile  —  {len(lats):,} points  |  "
            f"{dist_m[-1]/1000:.2f} km",
            fontsize=10, fontweight="bold", color="#ffffff", pad=8
        )

        # Overlay lines — each on its own twin y-axis
        for idx_ov, of in enumerate(overlay_fields):
            color = OVERLAY_PALETTE[idx_ov % len(OVERLAY_PALETTE)]
            vals  = overlay_vals[of]
            valid = ~np.isnan(vals)

            tax = ax.twinx()
            self._style_twin_ax(tax, color)

            # Shift successive axes further right
            if idx_ov > 0:
                offset = 1.0 + idx_ov * 0.10
                tax.spines["right"].set_position(("axes", offset))
                tax.spines["right"].set_visible(True)

            tax.plot(dist_m[valid], vals[valid],
                     color=color, linewidth=1.4, alpha=0.85, zorder=6)
            tax.set_ylabel(of, fontsize=8, color=color, labelpad=4)
            tax.tick_params(axis="y", colors=color, labelsize=8)

            lh = mlines.Line2D([], [], color=color, linewidth=1.8)
            legend_handles.append(lh)
            legend_labels.append(of)

        # Legend
        if self.show_legend_cb.isChecked() and legend_handles:
            if self.show_water_cb.isChecked() and water_f and waters.any():
                rh = mpatches.Patch(
                    facecolor="#1a6fa8", alpha=0.40,
                    edgecolor="none"
                )
                legend_handles.append(rh)
                legend_labels.append("water region")

            leg = ax.legend(
                legend_handles, legend_labels,
                title="Legend", title_fontsize=8,
                fontsize=8, loc="upper left",
                framealpha=0.65, facecolor="#1e1e3a",
                edgecolor="#444", labelcolor="#dddddd"
            )
            leg.get_title().set_color("#aaaaaa")

        self.canvas.draw()
        self._status(
            f"✔  {len(lats):,} points  |  {dist_m[-1]/1000:.2f} km  |  "
            f"{int(waters.sum())} water points"
        )

    # Styling

    def _style_ax(self, ax):
        ax.set_facecolor("#1a1a2e")
        self.figure.patch.set_facecolor("#12121f")
        for spine in ("bottom", "left"):
            ax.spines[spine].set_color("#555")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.tick_params(colors="#cccccc", labelsize=8)
        ax.grid(True, linestyle="--", alpha=0.35, linewidth=0.5, zorder=0)

    def _style_twin_ax(self, tax, color):
        tax.set_facecolor("none")
        for sp in ("top", "left", "bottom"):
            tax.spines[sp].set_visible(False)
        tax.spines["right"].set_color(color)
        tax.tick_params(axis="y", colors=color, labelsize=8)

    def _status(self, msg, error=False):
        self.status_lbl.setText(msg)
        color = "#d32f2f" if error else "#388e3c"
        self.status_lbl.setStyleSheet(f"color: {color}; font-size: 9pt;")
