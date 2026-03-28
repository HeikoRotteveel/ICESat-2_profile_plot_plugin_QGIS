from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
import os


class ICESat2ProfilePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dock = None
        self.action = None

    def initGui(self):
        self.action = QAction("ICESat-2 Profile Viewer", self.iface.mainWindow())
        self.action.triggered.connect(self.toggle_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("ICESat-2 Profile", self.action)

    def toggle_dock(self):
        if self.dock is None:
            from .dock_widget import ProfileDockWidget
            self.dock = ProfileDockWidget(self.iface)
            self.iface.addDockWidget(0x2, self.dock)  # Right side
        self.dock.setVisible(not self.dock.isVisible())

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("ICESat-2 Profile", self.action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
