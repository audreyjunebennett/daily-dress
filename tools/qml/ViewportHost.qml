import QtQuick

Item {
    id: host
    property bool requested: true
    property string previewMode: "Styled"
    property real comparePosition: .5
    property bool editing: false
    property bool idleAnimation: false
    property bool painting: true
    property string material: "hair"
    property string layerMode: "visible"
    property string hiddenParts: ""
    property bool matchingColor: false
    signal colorMatched(int count)
    signal reviewed(int count, bool approved)
    readonly property bool ready: loader.item ? loader.item.ready : false
    readonly property bool failed: loader.status === Loader.Error || (loader.item ? loader.item.failed : false)
    readonly property point hit: loader.item ? loader.item.hit : Qt.point(-1, -1)
    readonly property real viewZoom: loader.item ? loader.item.viewZoom : 1
    function control(action, factor) {
        if (loader.item) loader.item.forwardInput(action, 0, 0, factor)
    }
    function orbit(action, x, y) {
        if (ready) loader.item.forwardInput(action, x, y, 0)
    }
    function queueAction(action, value) {
        if (!ready) return false
        loader.item.forwardInput(action, 0, 0, value)
        return true
    }

    Loader {
        id: loader
        anchors.fill: parent
        active: studio.viewportAvailable && host.requested
        source: active ? "StudioViewport.qml" : ""
        opacity: host.ready ? 1 : 0
        onLoaded: {
            item.objectName = host.editing ? "editWebViewport" : "previewWebViewport"
            item.previewMode = Qt.binding(function() { return host.previewMode })
            item.comparePosition = Qt.binding(function() { return host.comparePosition })
            item.editing = Qt.binding(function() { return host.editing })
            item.idleAnimation = Qt.binding(function() { return host.idleAnimation })
            item.painting = Qt.binding(function() { return host.painting })
            item.material = Qt.binding(function() { return host.material })
            item.layerMode = Qt.binding(function() { return host.layerMode })
            item.hiddenParts = Qt.binding(function() { return host.hiddenParts })
            item.matchingColor = Qt.binding(function() { return host.matchingColor })
            item.colorMatched.connect(function(count) { host.colorMatched(count) })
            item.reviewed.connect(function(count, approved) { host.reviewed(count, approved) })
        }
    }
}
