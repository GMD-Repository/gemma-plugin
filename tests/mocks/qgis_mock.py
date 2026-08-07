# -*- coding: utf-8 -*-
"""
Mock implementation of qgis.core, qgis.gui, qgis.PyQt, PyQt5, and processing classes
for non-QGIS Python test execution environments.
Allows unit tests to run in standard Python CLI without throwing ModuleNotFoundError.
"""

import sys
import types
import os

# Ensure Qt offscreen platform plugin is used in headless/CI environments
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class DynamicMockModule(types.ModuleType):
    """Module proxy that returns MockGenericClass for any unassigned attribute."""
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MockGenericClass


class MockMetaClass(type):
    """Metaclass that returns 1 / MockGenericClass for any unassigned class attribute."""
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name in ("HLine", "VLine", "Sunken", "Raised", "NoFrame", "Plain", "Box", "Horizontal", "Vertical", "AlignLeft", "AlignRight", "AlignCenter"):
            return 1
        return MockGenericClass


class MockGenericClass(metaclass=MockMetaClass):
    HLine = 1
    VLine = 2
    Horizontal = 1
    Vertical = 2

    def __init__(self, *args, **kwargs):
        pass

    def setWindowTitle(self, title): pass
    def setLayout(self, layout): pass
    def exec_(self): return 1
    def exec(self): return 1
    def show(self): pass
    def hide(self): pass
    def connect(self, *args): pass
    def count(self): return 0

    def __int__(self): return 0
    def __index__(self): return 0
    def __len__(self): return 0
    def __bool__(self): return True

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MockGenericClass

    def __call__(self, *args, **kwargs):
        return MockGenericClass()


class QgsPointXY:
    def __init__(self, x=0.0, y=0.0):
        self._x = float(x)
        self._y = float(y)

    def x(self): return self._x
    def y(self): return self._y

    def __repr__(self):
        return f"QgsPointXY({self._x}, {self._y})"


class QgsPolygon:
    def __init__(self):
        self._points = []


class QgsGeometry:
    def __init__(self, geom_type="Polygon", polygons=None):
        self.geom_type = geom_type
        self.polygons = polygons or []

    @staticmethod
    def fromPointXY(point):
        return QgsGeometry("Point")

    @staticmethod
    def fromPolylineXY(polyline):
        return QgsGeometry("LineString")

    @staticmethod
    def fromPolygonXY(polygons):
        return QgsGeometry("Polygon", polygons=polygons)

    def type(self):
        if self.geom_type == "Point": return 0
        elif self.geom_type in ("LineString", "Line"): return 1
        return 2  # PolygonGeometry

    def wkbType(self): return 3
    def isNull(self): return False
    def isEmpty(self): return False
    def isSimple(self): return True
    def isValid(self): return True
    def isGeosValid(self): return True
    def isMultipart(self): return False
    def makeValid(self): return self
    def touches(self, other): return True
    def intersects(self, other): return True
    def combine(self, other): return QgsGeometry("Polygon")
    def buffer(self, distance, segments=3): return QgsGeometry("Polygon")
    def area(self): return 100.0
    def length(self): return 40.0

    def centroid(self): return QgsGeometry("Point")
    def asPoint(self): return QgsPointXY(0.0, 0.0)

    def boundingBox(self):
        class MockBox:
            def xMinimum(self): return 0.0
            def xMaximum(self): return 10.0
            def yMinimum(self): return 0.0
            def yMaximum(self): return 10.0
            def width(self): return 10.0
            def height(self): return 10.0
            def center(self): return QgsPointXY(5.0, 5.0)
            def scale(self, factor): pass
        return MockBox()

    def __repr__(self):
        return f"<QgsGeometry {self.geom_type}>"


class QgsField:
    def __init__(self, name="", field_type=None, comment="", length=0, precision=0):
        self._name = name
        self._type = field_type
        self._length = length
        self._precision = precision

    def name(self): return self._name
    def type(self): return self._type
    def length(self): return self._length
    def precision(self): return self._precision


class QgsFields:
    def __init__(self, fields=None):
        self._fields = fields or []

    def append(self, field):
        self._fields.append(field)

    def names(self):
        return [f.name() for f in self._fields]

    def indexOf(self, name):
        names = self.names()
        return names.index(name) if name in names else -1

    def count(self):
        return len(self._fields)

    def __iter__(self):
        return iter(self._fields)

    def __len__(self):
        return len(self._fields)


class QgsFeature:
    def __init__(self, fields=None):
        self._attributes = []
        self._geometry = None
        self._id = 0
        self._fields = fields

    def setAttributes(self, attrs):
        self._attributes = attrs

    def attributes(self):
        return self._attributes

    def setGeometry(self, geom):
        self._geometry = geom

    def geometry(self):
        return self._geometry

    def id(self):
        return self._id

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._attributes[key]
        if self._fields and hasattr(self._fields, "names"):
            names = self._fields.names()
            if key in names:
                return self._attributes[names.index(key)]
        return None


class QgsVectorLayer:
    def __init__(self, path="Polygon?crs=EPSG:4326", name="MockLayer", provider="memory"):
        self._path = path
        self._name = name
        self._provider = provider
        self._fields = QgsFields()
        self._features = []

    def name(self): return self._name
    def isValid(self): return True
    def featureCount(self): return len(self._features)
    def fields(self): return self._fields
    def setFields(self, fields): self._fields = fields
    def setFeatures(self, features): self._features = features
    def getFeatures(self, request=None): return iter(self._features)
    def crs(self): return MockGenericClass()
    def sourceCrs(self): return self.crs()
    def wkbType(self): return 3  # Polygon
    def id(self): return f"layer_{self._name}"
    def setSubsetString(self, string): return True
    def selectByExpression(self, expr): pass
    def selectedFeatureCount(self): return 0
    def triggerRepaint(self): pass


class QgsProcessingFeedback:
    def isCanceled(self): return False
    def setProgress(self, progress): pass
    def pushInfo(self, msg): pass
    def pushWarning(self, msg): pass
    def reportError(self, msg): pass


class QgsProcessingContext:
    def project(self):
        return QgsProject.instance()

    def transformContext(self):
        return MockGenericClass()


try:
    import qgis.core
    if hasattr(qgis.core, "QgsProcessingContext"):
        QgsProcessingContext = qgis.core.QgsProcessingContext
    if hasattr(qgis.core, "QgsProcessingFeedback"):
        QgsProcessingFeedback = qgis.core.QgsProcessingFeedback
    if hasattr(qgis.core, "QgsVectorLayer"):
        QgsVectorLayer = qgis.core.QgsVectorLayer
except Exception:
    pass


class QgsProcessingException(Exception):
    pass


class QgsSpatialIndex:
    def __init__(self, *args, **kwargs):
        self._features = {}

    def addFeature(self, feature):
        if hasattr(feature, "id"):
            self._features[feature.id()] = feature

    def addFeatures(self, features):
        for f in features:
            self.addFeature(f)

    def intersects(self, bbox):
        return list(self._features.keys())


class QgsProcessingAlgorithm:
    @classmethod
    def flags(cls): return 0
    @classmethod
    def group(cls): return "GMD Pipeline"
    @classmethod
    def groupId(cls): return "gmd_pipeline"

    def parameterAsLayerList(self, parameters, name, context):
        val = parameters.get(name, [])
        if isinstance(val, list):
            return val
        return [val]

    def parameterAsSource(self, parameters, name, context):
        val = parameters.get(name, None)
        if isinstance(val, QgsVectorLayer):
            return val
        return QgsVectorLayer(name="MockMaskSource")

    def parameterAsVectorLayer(self, parameters, name, context):
        val = parameters.get(name, None)
        if isinstance(val, QgsVectorLayer):
            return val
        return QgsVectorLayer(name="MockVectorLayer")

    def parameterAsEnum(self, parameters, name, context):
        return int(parameters.get(name, 0))

    def parameterAsDouble(self, parameters, name, context):
        return float(parameters.get(name, 0.0))

    def parameterAsString(self, parameters, name, context):
        return str(parameters.get(name, ""))

    def parameterAsBool(self, parameters, name, context):
        return bool(parameters.get(name, False))

    def parameterAsBoolean(self, parameters, name, context):
        return self.parameterAsBool(parameters, name, context)

    def parameterAsExtent(self, parameters, name, context, crs=None):
        class MockRect:
            def isEmpty(self): return False
            def combineExtentWith(self, rect): pass
        return MockRect()

    def parameterAsSink(self, parameters, name, context, fields, wkbType, crs):
        class MockSink:
            def addFeature(self, *args, **kwargs): pass
            def addFeatures(self, *args, **kwargs): return (True, [])
        return (MockSink(), "mock_dest_id")


class QgsProject:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = QgsProject()
        return cls._instance

    def mapLayers(self): return {}
    def __getattr__(self, name): return MockGenericClass()


class QgsApplication:
    _instance = None

    def __init__(self, *args, **kwargs):
        QgsApplication._instance = self

    @classmethod
    def instance(cls):
        return cls._instance

    def initQgis(self): pass
    def exitQgis(self): pass

    @staticmethod
    def processingRegistry():
        class MockRegistry:
            def addProvider(self, provider): pass
        return MockRegistry()


class QgsWkbTypes:
    Point = 1
    LineString = 2
    Polygon = 3
    MultiPoint = 4
    MultiLineString = 5
    MultiPolygon = 6

    PointGeometry = 0
    LineGeometry = 1
    PolygonGeometry = 2

    @staticmethod
    def displayString(wkb_type): return "Polygon"

    @staticmethod
    def geometryType(wkb_type): return 2  # PolygonGeometry

    @staticmethod
    def multiType(wkb_type): return 6

    @staticmethod
    def flatType(wkb_type): return 3


class MockQVariant:
    String = 1
    Int = 2
    Double = 3
    LongLong = 4
    DateTime = 5
    Date = 6
    Bool = 7

    def __init__(self, val=None): self.val = val


class MockQt(metaclass=MockMetaClass):
    Unchecked = 0
    Checked = 2
    CustomContextMenu = 1
    UserRole = 32
    Horizontal = 1
    Vertical = 2


class MockQCoreApplication:
    @staticmethod
    def translate(context, sourceText, disambiguation=None, n=-1):
        return sourceText


class MockQThread: pass
class MockQObject:
    def __init__(self, parent=None): pass


class MockQWidget(MockGenericClass):
    def __init__(self, parent=None): super().__init__()


class MockQDialog(MockQWidget): pass


class MockProcessing:
    @staticmethod
    def run(name, parameters, context=None, feedback=None, is_child_algorithm=False):
        # Return mock layer or dictionary depending on operation
        out_target = parameters.get("OUTPUT", "memory:")
        mock_layer = QgsVectorLayer(name=f"Result_{name}")
        return {
            "OUTPUT": out_target if out_target != "memory:" else mock_layer,
            "OUTPUT_LAYER": mock_layer
        }


_NATIVE_QGS_APP = None


def setup_qgis_mock_if_needed():
    """
    Checks for native QGIS installation. If real PyQGIS is available, initializes native
    QgsApplication and Processing framework. Otherwise, installs headless mock proxies.
    """
    import os
    global _NATIVE_QGS_APP

    try:
        import qgis.core
        if not hasattr(qgis.core, "MockGenericClass"):
            # Real PyQGIS detected — locate plugins directory if needed
            if hasattr(qgis.core, "__file__") and qgis.core.__file__:
                core_file = os.path.abspath(qgis.core.__file__)
                # qgis.core is inside <prefix>/python/qgis/core/__init__.py
                # Navigate up to <prefix>/python/
                qgis_python_dir = os.path.dirname(os.path.dirname(os.path.dirname(core_file)))
                plugins_dir = os.path.join(qgis_python_dir, "plugins")
                if os.path.exists(plugins_dir) and plugins_dir not in sys.path:
                    sys.path.insert(0, plugins_dir)

            if hasattr(qgis.core, "QgsApplication"):
                if qgis.core.QgsApplication.instance() is None:
                    if "QGIS_PREFIX_PATH" in os.environ:
                        qgis_prefix = os.environ["QGIS_PREFIX_PATH"]
                    elif os.path.exists("/usr/share/qgis/resources/srs.db"):
                        qgis_prefix = "/usr"
                    elif os.path.exists("/usr/local/share/qgis/resources/srs.db"):
                        qgis_prefix = "/usr/local"
                    elif hasattr(qgis.core, "__file__") and qgis.core.__file__:
                        qgis_prefix = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(qgis.core.__file__))))
                    else:
                        qgis_prefix = "/usr"

                    qgis.core.QgsApplication.setPrefixPath(qgis_prefix, True)
                    _NATIVE_QGS_APP = qgis.core.QgsApplication(sys.argv, True)
                    _NATIVE_QGS_APP.initQgis()

                    try:
                        import qgis.gui
                        if hasattr(qgis.gui, "QgsGui"):
                            qgis.gui.QgsGui.init()
                    except Exception:
                        pass

                try:
                    import processing
                    from processing.core.Processing import Processing
                    Processing.initialize()
                except Exception as e:
                    print(f"[QGIS Native Init Warning]: {e}")

            global QgsProcessingContext, QgsProcessingFeedback, QgsVectorLayer
            QgsProcessingContext = getattr(qgis.core, "QgsProcessingContext", QgsProcessingContext)
            QgsProcessingFeedback = getattr(qgis.core, "QgsProcessingFeedback", QgsProcessingFeedback)
            QgsVectorLayer = getattr(qgis.core, "QgsVectorLayer", QgsVectorLayer)
            return
    except ImportError:
        pass

    # Create dynamic mock modules for non-QGIS Python environment
        qgis_mod = DynamicMockModule("qgis")
        core_mod = DynamicMockModule("qgis.core")
        gui_mod = DynamicMockModule("qgis.gui")
        utils_mod = DynamicMockModule("qgis.utils")
        analysis_mod = DynamicMockModule("qgis.analysis")
        pyqt_mod = DynamicMockModule("qgis.PyQt")
        qtcore_mod = DynamicMockModule("qgis.PyQt.QtCore")
        qtgui_mod = DynamicMockModule("qgis.PyQt.QtWidgets")
        qtwidgets_mod = DynamicMockModule("qgis.PyQt.QtGui")

        # Explicit Core attributes
        core_mod.QgsPointXY = QgsPointXY
        core_mod.QgsPolygon = QgsPolygon
        core_mod.QgsGeometry = QgsGeometry
        core_mod.QgsField = QgsField
        core_mod.QgsFields = QgsFields
        core_mod.QgsFeature = QgsFeature
        core_mod.QgsVectorLayer = QgsVectorLayer
        core_mod.QgsSpatialIndex = QgsSpatialIndex
        core_mod.QgsProcessingFeedback = QgsProcessingFeedback
        core_mod.QgsProcessingContext = QgsProcessingContext
        core_mod.QgsProcessingException = QgsProcessingException
        core_mod.QgsProcessingAlgorithm = QgsProcessingAlgorithm
        core_mod.QgsProcessingLayerPostProcessorInterface = MockGenericClass
        core_mod.QgsProject = QgsProject
        core_mod.QgsApplication = QgsApplication
        core_mod.QgsWkbTypes = QgsWkbTypes

        # PyQt attributes
        class MockSignal:
            def emit(self, *args, **kwargs): pass
            def connect(self, *args, **kwargs): pass
            def disconnect(self, *args, **kwargs): pass

        qtcore_mod.QCoreApplication = MockQCoreApplication
        qtcore_mod.QThread = MockQThread
        qtcore_mod.QObject = MockQObject
        qtcore_mod.QVariant = MockQVariant
        qtcore_mod.Qt = MockQt
        qtcore_mod.pyqtSignal = lambda *args, **kwargs: MockSignal()

        qtgui_mod.QWidget = MockQWidget
        qtgui_mod.QDialog = MockQDialog

        pyqt_mod.QtCore = qtcore_mod
        pyqt_mod.QtWidgets = qtgui_mod
        pyqt_mod.QtGui = qtwidgets_mod

        qgis_mod.core = core_mod
        qgis_mod.gui = gui_mod
        qgis_mod.utils = utils_mod
        qgis_mod.analysis = analysis_mod
        qgis_mod.PyQt = pyqt_mod

        sys.modules["qgis"] = qgis_mod
        sys.modules["qgis.core"] = core_mod
        sys.modules["qgis.gui"] = gui_mod
        sys.modules["qgis.utils"] = utils_mod
        sys.modules["qgis.analysis"] = analysis_mod
        sys.modules["qgis.PyQt"] = pyqt_mod
        sys.modules["qgis.PyQt.QtCore"] = qtcore_mod
        sys.modules["qgis.PyQt.QtWidgets"] = qtgui_mod
        sys.modules["qgis.PyQt.QtGui"] = qtwidgets_mod

    # 2. PyQt5 standalone fallback
    if "PyQt5" not in sys.modules:
        pyqt5_mod = DynamicMockModule("PyQt5")
        pyqt5_qtcore_mod = DynamicMockModule("PyQt5.QtCore")
        pyqt5_qtgui_mod = DynamicMockModule("PyQt5.QtWidgets")
        pyqt5_gui_mod = DynamicMockModule("PyQt5.QtGui")

        pyqt5_qtcore_mod.QVariant = MockQVariant
        pyqt5_qtcore_mod.Qt = MockQt
        pyqt5_qtcore_mod.QCoreApplication = MockQCoreApplication
        pyqt5_qtcore_mod.QObject = MockQObject
        pyqt5_qtcore_mod.pyqtSignal = lambda *args, **kwargs: MockSignal()

        pyqt5_qtgui_mod.QWidget = MockQWidget
        pyqt5_qtgui_mod.QDialog = MockQDialog

        pyqt5_mod.QtCore = pyqt5_qtcore_mod
        pyqt5_mod.QtWidgets = pyqt5_qtgui_mod
        pyqt5_mod.QtGui = pyqt5_gui_mod

        sys.modules["PyQt5"] = pyqt5_mod
        sys.modules["PyQt5.QtCore"] = pyqt5_qtcore_mod
        sys.modules["PyQt5.QtWidgets"] = pyqt5_qtgui_mod
        sys.modules["PyQt5.QtGui"] = pyqt5_gui_mod

    # 3. processing module fallback
    if "processing" not in sys.modules or not hasattr(sys.modules["processing"], "gui"):
        proc_mod = DynamicMockModule("processing")
        proc_gui_mod = DynamicMockModule("processing.gui")
        proc_wrappers_mod = DynamicMockModule("processing.gui.wrappers")

        proc_mod.run = MockProcessing.run
        proc_mod.gui = proc_gui_mod
        proc_gui_mod.wrappers = proc_wrappers_mod

        sys.modules["processing"] = proc_mod
        sys.modules["processing.gui"] = proc_gui_mod
        sys.modules["processing.gui.wrappers"] = proc_wrappers_mod
