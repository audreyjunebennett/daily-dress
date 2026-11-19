import QtQuick

// Screen-space tools over a nearest-neighbor texture. No edits touch the PNG.
Rectangle {
    id: canvas
    objectName: "pixelCanvas"
    property string source
    property int gridSize: 64
    property real zoom: 1
    property bool panTool: false
    property bool selectTool: false
    property bool matchTool: false
    property var atlasGuides: []
    property point firstCell: Qt.point(-1, -1)
    property point lastCell: Qt.point(-1, -1)
    property point markedCell: Qt.point(-1, -1)
    readonly property bool hasSelection: firstCell.x >= 0
    signal paintCell(int x, int y, bool restore)
    signal strokeEnded()
    color: "#eee5f5"
    radius: 14
    clip: true

    function fit() {
        zoom = 1
        view.contentX = 0
        view.contentY = 0
    }
    function clearSelection() { firstCell = Qt.point(-1, -1) }
    function zoomBy(factor) { changeZoom(zoom * factor, width / 2, height / 2) }
    function changeZoom(next, x, y) {
        const u = (view.contentX + x - texture.x) / texture.width
        const v = (view.contentY + y - texture.y) / texture.height
        zoom = Math.max(1, Math.min(12, next))
        view.contentX = Math.max(0, Math.min(view.contentWidth - view.width, texture.x + u * texture.width - x))
        view.contentY = Math.max(0, Math.min(view.contentHeight - view.height, texture.y + v * texture.height - y))
    }

    Flickable {
        id: view
        anchors.fill: parent
        interactive: false
        boundsBehavior: Flickable.StopAtBounds
        contentWidth: Math.max(width, texture.width + 16)
        contentHeight: Math.max(height, texture.height + 16)
        Image {
            id: texture
            objectName: "pixelTexture"
            width: Math.max(1, Math.floor((Math.min(view.width, view.height) - 16) / canvas.gridSize) * canvas.gridSize) * canvas.zoom
            height: width
            x: (view.contentWidth - width) / 2
            y: (view.contentHeight - height) / 2
            source: canvas.source
            cache: false
            smooth: false
            fillMode: Image.Stretch

            Repeater {
                model: canvas.atlasGuides
                Rectangle {
                    required property var modelData
                    readonly property real unit: texture.width / canvas.gridSize
                    objectName: "atlasPartGuide"
                    x: modelData.x * unit
                    y: modelData.y * unit
                    width: modelData.width * unit
                    height: modelData.height * unit
                    color: "transparent"
                    border.width: 1
                    border.color: modelData.outer ? "#9b6bac" : "#71589a"
                    Rectangle {
                        x: 2; y: 2
                        width: guideLabel.implicitWidth + 8; height: guideLabel.implicitHeight + 2
                        radius: 4
                        color: modelData.outer ? "#f3def5" : "#ede2fa"
                        Text {
                            id: guideLabel
                            anchors.centerIn: parent
                            text: modelData.label + (modelData.outer ? " · outer" : "")
                            font.pixelSize: 10
                            color: "#4b326d"
                        }
                    }
                }
            }

            Rectangle {
                visible: canvas.markedCell.x >= 0 && canvas.markedCell.y >= 0
                x: canvas.markedCell.x * texture.width / canvas.gridSize
                y: canvas.markedCell.y * texture.height / canvas.gridSize
                width: texture.width / canvas.gridSize; height: width
                z: 1
                border.width: 2; border.color: "#ffffff"; color: "#82795ab6"
            }
            Rectangle {
                visible: canvas.hasSelection
                x: Math.min(canvas.firstCell.x, canvas.lastCell.x) * texture.width / canvas.gridSize
                y: Math.min(canvas.firstCell.y, canvas.lastCell.y) * texture.height / canvas.gridSize
                width: (Math.abs(canvas.firstCell.x - canvas.lastCell.x) + 1) * texture.width / canvas.gridSize
                height: (Math.abs(canvas.firstCell.y - canvas.lastCell.y) + 1) * texture.height / canvas.gridSize
                border.color: "#795ab6"; border.width: 2
                color: "#30795ab6"
            }
            Rectangle {
                visible: pointer.containsMouse && !pointer.panning && !canvas.panTool
                         && pointer.cell.x >= 0 && pointer.cell.y >= 0
                         && pointer.cell.x < canvas.gridSize && pointer.cell.y < canvas.gridSize
                x: pointer.cell.x * texture.width / canvas.gridSize
                y: pointer.cell.y * texture.height / canvas.gridSize
                width: texture.width / canvas.gridSize; height: width
                border.color: "white"; color: "#32795ab6"
            }
        }
    }
    MouseArea {
        id: pointer
        objectName: "pixelPointer"
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        property bool panning: false
        property bool selecting: false
        property bool restoring: false
        property bool matching: false
        property point previous
        property point cell: locate(mouseX, mouseY)
        cursorShape: panning ? Qt.ClosedHandCursor : canvas.panTool ? Qt.OpenHandCursor : Qt.CrossCursor
        function locate(x, y) {
            const p = mapToItem(texture, x, y)
            return Qt.point(Math.floor(p.x * canvas.gridSize / texture.width),
                            Math.floor(p.y * canvas.gridSize / texture.height))
        }
        function bounded(p) {
            return Qt.point(Math.max(0, Math.min(canvas.gridSize - 1, p.x)),
                            Math.max(0, Math.min(canvas.gridSize - 1, p.y)))
        }
        onPressed: function(event) {
            previous = Qt.point(event.x, event.y)
            panning = event.button === Qt.MiddleButton || (canvas.panTool && event.button === Qt.LeftButton)
            restoring = event.button === Qt.RightButton
            matching = !panning && !restoring && canvas.matchTool
            selecting = !panning && !restoring && canvas.selectTool
            const p = locate(event.x, event.y)
            if (selecting) {
                canvas.firstCell = bounded(p)
                canvas.lastCell = canvas.firstCell
            } else if (!panning) {
                canvas.paintCell(p.x, p.y, restoring)
            }
        }
        onPositionChanged: function(event) {
            if (!pressed) return
            if (panning) {
                view.contentX = Math.max(0, Math.min(view.contentWidth - view.width, view.contentX + previous.x - event.x))
                view.contentY = Math.max(0, Math.min(view.contentHeight - view.height, view.contentY + previous.y - event.y))
                previous = Qt.point(event.x, event.y)
            } else {
                const p = locate(event.x, event.y)
                if (selecting) canvas.lastCell = bounded(p)
                else if (!matching) canvas.paintCell(p.x, p.y, restoring)
            }
        }
        onReleased: { panning = false; selecting = false; canvas.strokeEnded() }
        onCanceled: { panning = false; selecting = false; canvas.strokeEnded() }
        onWheel: function(event) { canvas.changeZoom(canvas.zoom * Math.pow(1.2, event.angleDelta.y / 120), event.x, event.y) }
    }
}
