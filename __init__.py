def classFactory(iface):
    from .plugin import ICESat2ProfilePlugin
    return ICESat2ProfilePlugin(iface)
