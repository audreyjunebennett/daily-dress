import QtQuick
import QtWebEngine
import QtWebChannel

WebEngineView {
    id: surface
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
    property bool ready: false
    property bool failed: false
    property point hit: Qt.point(-1, -1)
    property real viewZoom: 1
    function forwardInput(kind, x, y, button) {
        if (ready)
            runJavaScript("window.ddViewportInput?.(" + JSON.stringify([kind, x, y, button]) + ")")
    }

    url: studio.viewportUrl
    backgroundColor: "transparent"
    enabled: editing
    activeFocusOnPress: false
    settings.localContentCanAccessRemoteUrls: false
    settings.javascriptCanOpenWindows: false
    profile: WebEngineProfile { offTheRecord: true }
    onRenderProcessTerminated: {
        failed = true
        ready = false
        hit = Qt.point(-1, -1)
        if (editing) studio.endPixelStroke()
    }
    onLoadingChanged: function(info) {
        if (info.status === WebEngineView.LoadFailedStatus) {
            failed = true
            ready = false
        }
    }
    onJavaScriptConsoleMessage: function(level, message, line, origin) {
        if (level === WebEngineView.ErrorMessageLevel)
            console.warn("Daily Dress 3D:", message, line)
    }
    onNavigationRequested: function(request) {
        if (request.url.toString() !== studio.viewportUrl.toString())
            request.reject()
    }

    webChannel: WebChannel {
        propertyUpdateInterval: 0
        registeredObjects: [host]
    }
    MouseArea {
        anchors.fill: parent
        z: 10
        visible: surface.editing
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
        cursorShape: pressedButtons & Qt.MiddleButton ? Qt.ClosedHandCursor : Qt.CrossCursor
        onPressed: function(event) {
            const pan = event.button === Qt.MiddleButton && (event.modifiers & Qt.ShiftModifier)
            const action = pan ? "pan" : surface.matchingColor && event.button === Qt.LeftButton ? "match" : "press"
            surface.forwardInput(action, event.x, event.y, event.button)
        }
        onPositionChanged: function(event) { surface.forwardInput("move", event.x, event.y, 0) }
        onReleased: surface.forwardInput("finish", 0, 0, 0)
        onCanceled: surface.forwardInput("finish", 0, 0, 0)
        onExited: surface.forwardInput("leave", 0, 0, 0)
        onWheel: function(event) { surface.forwardInput("wheel", event.x, event.y, event.angleDelta.y) }
    }
    QtObject {
        id: host
        WebChannel.id: "host"
        property string packet: {
            const raw = studio.viewportPacket
            if (!surface.editing) return raw
            if (!raw || studio.editorMode !== "pixels") return ""
            return studio.acceptsViewportEdits(JSON.parse(raw).token) ? raw : ""
        }
        property real yaw: studio.previewYaw
        property string mode: surface.previewMode
        property real wipe: surface.comparePosition
        property bool editable: surface.editing
        property bool idleAnimation: surface.idleAnimation
        property bool canPaint: surface.painting
        property string layer: surface.layerMode
        property string hiddenParts: surface.hiddenParts

        function surfaceReady(rendered) {
            surface.ready = rendered === true
            surface.failed = !surface.ready
            if (!surface.ready && surface.editing) studio.endPixelStroke()
        }
        function highlight(token, x, y) {
            if (surface.editing)
                surface.hit = studio.acceptsViewportEdits(token) ? Qt.point(x, y) : Qt.point(-1, -1)
        }
        function reportZoom(zoom) { surface.viewZoom = zoom }
        function paint(token, cells, restore) {
            if (surface.editing && surface.painting && surface.ready)
                studio.paintViewportCells(token, cells, surface.material, restore)
        }
        function matchColor(token, x, y) {
            if (surface.matchingColor && surface.painting && surface.ready && studio.acceptsViewportEdits(token))
                surface.colorMatched(studio.matchPixelColor(x, y, surface.material))
        }
        function review(token, cells, approve) {
            if (surface.editing && surface.painting && surface.ready && studio.acceptsViewportEdits(token))
                surface.reviewed(studio.reviewViewportCells(token, cells, surface.material, approve), approve)
        }
        function finish(token) {
            if (surface.editing) studio.endViewportStroke(token)
        }
        function stepHistory(undo) {
            if (!surface.editing || !surface.ready || studio.editorMode !== "pixels") return
            if (undo) studio.undo()
            else studio.redo()
        }
        function navigate(step) {
            if (surface.editing && surface.ready) studio.navigatePixels(step)
        }
    }
}
