import os

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.gui_utils.layouts import CVBoxLayout
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import set_module_type


# Pinned CesiumJS release served from the official CDN. Bump deliberately;
# letting it float to "latest" risks the globe silently breaking on a
# Cesium API change.
CESIUM_VERSION = '1.118'
CESIUM_BASE = f'https://cesium.com/downloads/cesiumjs/releases/{CESIUM_VERSION}/Build/Cesium'

# The token is read from the environment for now (secrets handling is a
# later improvement). When present we use Cesium ion's premium imagery and
# the full default Viewer UI. When absent we fall back to token-free
# OpenStreetMap imagery and disable the ion-dependent widgets (geocoder,
# base-layer picker) so the globe still renders instead of erroring.
_GLOBE_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="__CESIUM_BASE__/Cesium.js"></script>
    <link href="__CESIUM_BASE__/Widgets/widgets.css" rel="stylesheet">
    <style>
        html, body, #cesiumContainer {
            width: 100%; height: 100%;
            margin: 0; padding: 0;
            overflow: hidden;
            background: #000;
        }
        #hint {
            position: absolute; bottom: 30px; left: 10px;
            color: #fff; font-family: sans-serif; font-size: 12px;
            background: rgba(0,0,0,0.5); padding: 6px 10px;
            border-radius: 4px; z-index: 1000;
        }
    </style>
</head>
<body>
    <div id="cesiumContainer"></div>
    <script>
        const ionToken = "__CESIUM_TOKEN__";
        let viewer;
        if (ionToken) {
            Cesium.Ion.defaultAccessToken = ionToken;
            viewer = new Cesium.Viewer('cesiumContainer');
        } else {
            // No ion token: OSM imagery, and hide widgets that require ion.
            const osm = new Cesium.ImageryLayer(
                new Cesium.OpenStreetMapImageryProvider({
                    url: 'https://tile.openstreetmap.org/'
                })
            );
            viewer = new Cesium.Viewer('cesiumContainer', {
                baseLayer: osm,
                baseLayerPicker: false,
                geocoder: false,
            });
            const hint = document.createElement('div');
            hint.id = 'hint';
            hint.textContent =
                'Set the CESIUM_ION_TOKEN environment variable for ' +
                'premium imagery, terrain and search.';
            document.body.appendChild(hint);
        }
    </script>
</body>
</html>
"""


@set_module_type('Pages')
class Page_WorldView(ConfigWidget):
    """A 3D globe (Google Earth-style) rendered with CesiumJS in a web view."""

    display_name = 'World View'
    icon_path = ':/resources/icon-globe3.png'
    page_type = 'any'

    def __init__(self, parent):
        super().__init__(parent=parent)

        self.web_view = QWebEngineView(self)
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)

        token = os.environ.get('CESIUM_ION_TOKEN', '')
        html = (_GLOBE_HTML
                .replace('__CESIUM_BASE__', CESIUM_BASE)
                .replace('__CESIUM_TOKEN__', token))
        # An https base URL lets the page pull the Cesium CDN scripts and
        # use browser storage that Cesium expects.
        self.web_view.setHtml(html, QUrl('https://localhost/'))

        self.layout = CVBoxLayout(self)
        self.layout.addWidget(self.web_view)
