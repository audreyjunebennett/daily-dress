import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1440; height: 900
    minimumWidth: 980; minimumHeight: 680
    visible: true
    title: "Daily Dress · Local Styling Studio"
    color: "#fffaf7"
    font.family: "Segoe UI"
    font.pixelSize: 14
    property color ink: "#42394b"
    property color muted: "#83798d"
    property color accent: "#795ab6"
    property color line: "#eee6f2"
    property bool inspectorOpen: true
    property string activeMaterial: "hair"
    onActiveMaterialChanged: {
        if (inspectorScroll && inspectorScroll.contentItem)
            inspectorScroll.contentItem.contentY = 0
    }
    property bool eyePlacementOpen: false
    readonly property bool showMaterialCounts: inspectorOpen && !activeWorkspace
        && (activeMaterial === "outfit" || activeMaterial === "accessory")
    onShowMaterialCountsChanged: studio.setMaterialInspection(showMaterialCounts)
    property string viewMode: "Compare"
    property real comparePosition: .5
    readonly property string activeWorkspace: studio.editorMode
    property bool assigningCategories: false
    property string assignmentTag: ""
    readonly property color assignmentHighlight: "#ecdef8"
    readonly property bool sortingKeysEnabled: studio.hasSkins && !activeWorkspace && !categoryDialog.visible
        && !(activeFocusItem instanceof TextInput || activeFocusItem instanceof TextEdit)
    function sortSkin(status) {
        carousel.cancelFlick()
        studio.setStatus(status)
    }
    onActiveWorkspaceChanged: { if (!activeWorkspace) Qt.callLater(function() { carousel.forceActiveFocus() }) }
    // Explicit light palette: Windows dark-mode defaults otherwise make input
    // text nearly white on our deliberately pale custom field backgrounds.
    palette.text: ink
    palette.base: "#f7f3fb"
    palette.button: "#f7f3fb"
    palette.buttonText: ink
    palette.highlight: accent
    palette.highlightedText: "#ffffff"
    palette.window: "#fffafd"
    palette.windowText: ink
    palette.toolTipBase: "#fffafd"
    palette.toolTipText: ink

    component LabelText: Text { color: window.ink; font.pixelSize: 14 }
    component Caption: Text { color: window.muted; font.pixelSize: 12; font.weight: Font.DemiBold }
    component SoftPopupSurface: Rectangle {
        color: "#fffafd"
        border.color: "#e4d6ef"
        radius: 13
    }
    component SoftTip: ToolTip {
        id: tip
        objectName: "studioHelpTip"
        delay: 450
        timeout: 5000
        margins: 10
        padding: 8
        horizontalPadding: 12
        width: Math.min(310, window.width - 20, measure.advanceWidth + leftPadding + rightPadding)
        x: parent ? (parent.width - width) / 2 : 0
        y: parent && parent.mapToItem(window.contentItem, 0, 0).y < height + 16 ? parent.height + 6 : -height - 6
        font.pixelSize: 13
        TextMetrics { id: measure; text: tip.text; font: tip.font }
        contentItem: Text {
            text: tip.text
            textFormat: Text.PlainText
            font: tip.font
            color: window.ink
            wrapMode: Text.Wrap
            lineHeight: 1.15
        }
        background: SoftPopupSurface { color: "#faf3ff"; radius: 11 }
    }
    component SoftCombo: ComboBox {
        id: combo
        implicitWidth: 140
        implicitHeight: 38
        padding: 8
        leftPadding: 11
        rightPadding: 27
        hoverEnabled: true
        background: Rectangle {
            radius: 11
            color: combo.down ? "#ece1f7" : combo.hovered ? "#f4ecfb" : "#f7f1fc"
            border.color: combo.visualFocus ? window.accent : "#e9def2"
            border.width: combo.visualFocus ? 2 : 1
        }
        contentItem: Text {
            text: combo.displayText
            textFormat: Text.PlainText
            color: combo.enabled ? window.ink : window.muted
            font: combo.font
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        indicator: Text {
            text: combo.popup.visible ? "▴" : "▾"
            color: combo.enabled ? window.accent : window.muted
            font.pixelSize: 15
            x: combo.width - width - 10
            y: (combo.height - height) / 2
        }
        delegate: ItemDelegate {
            id: choice
            required property int index
            objectName: "studioDropdownChoice" + index
            width: ListView.view.width
            height: 34
            text: combo.textAt(index)
            highlighted: combo.highlightedIndex === index
            hoverEnabled: true
            horizontalPadding: 8
            contentItem: Text {
                text: choice.text
                textFormat: Text.PlainText
                font.family: combo.font.family
                font.pixelSize: combo.font.pixelSize
                font.weight: choice.index === combo.currentIndex ? Font.DemiBold : Font.Normal
                color: choice.index === combo.currentIndex ? window.accent : window.ink
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: 8
                color: choice.down ? "#e6d8f4" : choice.highlighted || choice.hovered ? "#eee4f8"
                       : choice.index === combo.currentIndex ? "#f6effb" : "transparent"
            }
        }
        popup: Popup {
            objectName: "studioDropdownList"
            y: combo.height + 4
            width: combo.width
            height: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 248, window.height - 20)
            margins: 10
            padding: 5
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.delegateModel
                currentIndex: combo.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator {}
            }
            background: SoftPopupSurface {}
        }
    }
    component Pill: Button {
        id: pill
        property bool active: false
        padding: 10
        horizontalPadding: 14
        background: Rectangle {
            radius: 17
            color: pill.down ? "#ded0f2" : pill.active ? "#e9dff8" : pill.hovered ? "#f4eefb" : "transparent"
            Behavior on color { ColorAnimation { duration: 110 } }
        }
        contentItem: Text {
            text: pill.text; color: pill.active ? window.accent : window.ink
            font.pixelSize: 14; font.weight: pill.active ? Font.DemiBold : Font.Normal
            opacity: pill.enabled ? 1 : .4
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
    }
    component EditorClose: ToolButton {
        id: closeButton
        text: "×"
        Accessible.name: "Close editor"
        hoverEnabled: true
        implicitWidth: 32
        implicitHeight: 32
        padding: 0
        onClicked: studio.closeEditor()
        background: Rectangle {
            radius: width / 2
            color: closeButton.down ? "#ded0f2" : closeButton.hovered ? "#e6d8f4" : "#eee5f8"
            border.width: closeButton.visualFocus ? 2 : 1
            border.color: closeButton.visualFocus ? window.accent : "#dacbec"
        }
        contentItem: Text {
            text: closeButton.text
            color: window.accent
            font.pixelSize: 20
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        SoftTip { text: "Close editor"; visible: closeButton.hovered }
    }
    component CompareDivider: MouseArea {
        property real fraction: .5
        signal moved(real position)
        x: parent.width * fraction - 12
        width: 24; height: parent.height
        cursorShape: Qt.SplitHCursor
        onPositionChanged: function(mouse) {
            if (pressed) moved(Math.max(.05, Math.min(.95, mapToItem(parent, mouse.x, mouse.y).x / parent.width)))
        }
        Rectangle { x: 11; width: 2; height: parent.height; color: window.accent; opacity: .6 }
        Rectangle {
            x: 2; y: parent.height / 2 - 17; width: 20; height: 34
            radius: 10; color: "#ffffff"; border.color: window.accent
            Text { anchors.centerIn: parent; text: "↔"; color: window.accent }
        }
    }
    component ArmModelPicker: SoftCombo {
        Accessible.name: "Arm model"
        readonly property var options: [{label: "Auto", key: "auto"}, {label: "Slim", key: "slim"},
                                        {label: "Regular", key: "classic"}]
        textRole: "label"
        valueRole: "key"
        model: options
        currentIndex: options.findIndex(option => option.key === studio.selectedArmModel)
        displayText: "Arms: " + currentText
        onActivated: studio.setArmModel(currentValue)
        SoftTip { text: "Arm width for this skin · Slim is 3 pixels, Regular is 4"; visible: parent.hovered }
    }
    component ColorSlider: Slider {
        id: control
        property color startColor: "#ffffff"
        property color middleColor: "#9a73bd"
        property color endColor: "#000000"
        property bool rainbow: false
        function mix(a, b, amount) {
            return Qt.rgba(a.r + (b.r - a.r) * amount, a.g + (b.g - a.g) * amount, a.b + (b.b - a.b) * amount, 1)
        }
        implicitHeight: 28
        background: Rectangle {
            x: control.leftPadding; y: control.topPadding + control.availableHeight / 2 - height / 2
            width: control.availableWidth; height: 10; radius: 5
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: control.rainbow ? "#ed626b" : control.startColor }
                GradientStop { position: .17; color: control.rainbow ? "#f1d252" : control.mix(control.startColor, control.middleColor, .34) }
                GradientStop { position: .33; color: control.rainbow ? "#66c779" : control.mix(control.startColor, control.middleColor, .66) }
                GradientStop { position: .5; color: control.rainbow ? "#60c7cd" : control.middleColor }
                GradientStop { position: .67; color: control.rainbow ? "#6c8ce0" : control.mix(control.middleColor, control.endColor, .34) }
                GradientStop { position: .83; color: control.rainbow ? "#c875d1" : control.mix(control.middleColor, control.endColor, .66) }
                GradientStop { position: 1; color: control.rainbow ? "#ed626b" : control.endColor }
            }
        }
        handle: Rectangle {
            x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
            y: control.topPadding + control.availableHeight / 2 - height / 2
            width: 18; height: 18; radius: 9
            color: "#ffffff"; border.color: window.accent; border.width: 2
        }
        onPressedChanged: { if (pressed) studio.beginStyleEdit(); else studio.endStyleEdit() }
    }
    component Toggle: CheckBox {
        id: control
        implicitHeight: 30
        spacing: 9
        indicator: Rectangle {
            x: control.leftPadding; y: control.topPadding + control.availableHeight / 2 - height / 2
            width: 20; height: 20; radius: 6
            color: control.checked ? window.accent : "#ffffff"
            border.color: control.checked ? window.accent : "#d8cce1"
            opacity: control.enabled ? 1 : .45
            Rectangle { visible: control.checked; x: 4; y: 10; width: 6; height: 2; rotation: 45; color: "white" }
            Rectangle { visible: control.checked; x: 8; y: 8; width: 9; height: 2; rotation: -48; color: "white" }
        }
        contentItem: Text {
            text: control.text; color: window.ink; font.pixelSize: 14
            leftPadding: control.indicator.width + control.spacing
            verticalAlignment: Text.AlignVCenter; opacity: control.enabled ? 1 : .45
        }
    }
    component RecentSwatches: Row {
        required property string colorKey
        spacing: 5
        Repeater {
            model: studio.recentColors
            Rectangle {
                required property string modelData
                width: 21; height: 21; radius: 7
                color: modelData; border.color: "#24000000"
                SoftTip { text: modelData; visible: recentHover.hovered }
                HoverHandler { id: recentHover }
                TapHandler { onTapped: studio.setColor(colorKey, modelData) }
            }
        }
    }
    component SwatchField: RowLayout {
        id: swatch
        required property string colorKey
        required property string hex
        property bool readOnlyHex: false
        Rectangle {
            width: 34; height: 34; radius: 10; color: swatch.hex || "transparent"
            border.color: "#18000000"
            TapHandler { onTapped: studio.chooseColor(swatch.colorKey) }
            HoverHandler { id: pickerHover }
            SoftTip { text: "Choose a color"; visible: pickerHover.hovered }
        }
        TextField {
            objectName: swatch.colorKey === "hairColor" ? "hairHex" : swatch.colorKey === "skinColor" ? "skinHex" : swatch.colorKey + "Hex"
            property bool edited: false
            property string draftSkin: ""
            Layout.fillWidth: true; Layout.minimumWidth: 72
            text: swatch.hex
            readOnly: swatch.readOnlyHex
            selectByMouse: true
            color: window.ink; selectionColor: window.accent; selectedTextColor: "white"
            onTextEdited: { edited = true; draftSkin = studio.styleSkinKey }
            onEditingFinished: {
                if (edited) {
                    edited = false
                    if (draftSkin === studio.styleSkinKey) studio.setColor(swatch.colorKey, text)
                    text = Qt.binding(function() { return swatch.hex })
                }
            }
            background: Rectangle { radius: 12; color: "#f7f3fb" }
        }
    }
    component HslSliders: ColumnLayout {
        id: hsl
        required property string colorKey
        readonly property var channels: colorKey === "hairColor"
            ? ({hue: studio.styleOptions.hairHue, saturation: studio.styleOptions.hairSaturation, lightness: studio.styleOptions.hairLightness})
            : (studio.colorChannels[colorKey] || ({hue: 0, saturation: 0, lightness: 0}))
        spacing: 2
        Repeater {
            model: ["Hue", "Saturation", "Lightness"]
            ColumnLayout {
                required property int index
                required property string modelData
                readonly property string channel: modelData.toLowerCase()
                Layout.fillWidth: true
                spacing: 0
                Caption { text: modelData }
                ColorSlider {
                    objectName: hsl.colorKey === "hairColor" && index === 0 ? "hairHue" : ""
                    Layout.fillWidth: true; from: 0; to: index === 0 ? 360 : 100
                    value: hsl.channels[channel]
                    rainbow: index === 0
                    startColor: index === 1 ? "#bbbbbb" : "#111111"
                    middleColor: Qt.hsla(hsl.channels.hue / 360, index === 1 ? .5 : hsl.channels.saturation / 100, .5, 1)
                    endColor: index === 1 ? Qt.hsla(hsl.channels.hue / 360, 1, .5, 1) : "white"
                    onMoved: studio.setColorChannel(hsl.colorKey, channel, value)
                }
            }
        }
    }
    component MaterialPane: ColumnLayout {
        id: tint
        required property string material
        readonly property string colorKey: material + "Color"
        readonly property string enabledKey: material + "Enabled"
        readonly property bool skinTone: material === "skin"
        readonly property bool fromReference: skinTone && studio.styleOptions.skinMode === "reference"
        readonly property bool hasTarget: skinTone ? studio.styleOptions.skinTargetAvailable
                                                   : material !== "hair" || studio.styleOptions.hairTargetAvailable
        readonly property string target: ({"hair":"hair color", "skin":"skin tone", "outfit":"outfit color", "accessory":"accessory color"})[material] || ""
        readonly property string applyLabel: ({"hair":"Recolor hair", "skin":"Apply skin tone", "outfit":"Recolor outfit", "accessory":"Recolor accessories"})[material] || ""
        spacing: 5

        Toggle {
            text: tint.applyLabel
            checked: tint.hasTarget && (studio.styleOptions[tint.enabledKey] || false)
            enabled: studio.hasSkins && tint.hasTarget
            onToggled: studio.setStyleToggle(tint.enabledKey, checked)
        }
        SoftCombo {
            objectName: "skinMode"
            visible: tint.skinTone
            Layout.fillWidth: true
            model: ["Use reference face tone", "Use custom skin tone"]
            currentIndex: studio.styleOptions.skinMode === "reference" ? 0 : 1
            onActivated: studio.setSkinMode(currentIndex === 0 ? "reference" : "custom")
        }
        Caption {
            visible: tint.fromReference && !studio.hasReference
            text: "Set a style reference to match its face tone."
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        Caption {
            visible: studio.hasSkins && studio.materialCounts[tint.material] === 0
                     && (tint.material === "outfit" || tint.material === "accessory")
            text: "No matching pixels · try Edit Color Areas"
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        SwatchField {
            Layout.fillWidth: true
            colorKey: tint.colorKey; hex: studio.styleOptions[colorKey] || ""
            readOnlyHex: tint.fromReference
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 2
            Pill {
                id: pickButton
                objectName: "pickMaterialColor"
                text: "Pick " + tint.target + "…"
                active: true; horizontalPadding: 7; padding: 7
                enabled: studio.hasSkins
                onClicked: studio.openColorSampler(tint.colorKey)
                contentItem: Row {
                    spacing: 5
                    Image { source: "icons/eyedropper.svg"; width: 16; height: 16; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: pickButton.text; color: window.accent; font.pixelSize: 14; font.weight: Font.DemiBold }
                }
                SoftTip { text: "Set " + tint.target + " from a pixel on this skin"; visible: parent.hovered }
            }
            Item { Layout.fillWidth: true }
            Pill {
                id: wheelButton
                objectName: "materialColorWheel"
                text: "Choose " + tint.target
                enabled: studio.hasSkins
                padding: 6; horizontalPadding: 7
                onClicked: studio.chooseColor(tint.colorKey)
                contentItem: Item {
                    implicitWidth: 23; implicitHeight: 23
                    Image { anchors.fill: parent; source: "icons/color-wheel.svg" }
                }
                SoftTip { text: wheelButton.text; visible: wheelButton.hovered }
            }
        }
        RecentSwatches {
            colorKey: tint.colorKey
            visible: studio.hasSkins && studio.recentColors.length > 0
        }
    }
    Component {
        id: colorInspector
        MaterialPane { material: window.activeMaterial }
    }
    Component {
        id: eyesInspector
        ColumnLayout {
            spacing: 5
            Toggle { text: "Use styled eyes"; checked: studio.styleOptions.eyesEnabled; enabled: studio.hasEyeReference; onToggled: studio.setStyleToggle("eyesEnabled", checked) }
            Caption { text: "Eye source: " + studio.eyeReferenceName; Layout.fillWidth: true; elide: Text.ElideRight }
            SoftCombo {
                Layout.fillWidth: true
                model: ["Change eye source…", "Selected skin’s eyes", "Style reference’s eyes", "Soft lashes preset",
                        ...(studio.hasLegacyEyes ? ["Legacy saved eyes"] : [])]
                onActivated: {
                    if (currentIndex > 0) studio.setEyeSource(["selected", "reference", "preset", "legacy"][currentIndex - 1])
                    currentIndex = 0
                }
                SoftTip { text: "Choosing eyes does not change hair or skin tone"; visible: parent.hovered }
            }
            RowLayout {
                spacing: 3
                Pill { objectName: "designEyes"; text: "Design Eyes"; active: true; horizontalPadding: 8; padding: 7; enabled: studio.hasSkins; onClicked: studio.openEyes() }
                Pill { text: "Placement " + (window.eyePlacementOpen ? "▾" : "▸"); horizontalPadding: 6; padding: 7; onClicked: window.eyePlacementOpen = !window.eyePlacementOpen }
            }
            Toggle { visible: window.eyePlacementOpen; text: "Show over bangs"; checked: studio.styleOptions.eyesOverBangs; enabled: studio.hasEyeReference; onToggled: studio.setStyleToggle("eyesOverBangs", checked) }
            Toggle { visible: window.eyePlacementOpen; text: "Keep 3D lashes"; checked: studio.styleOptions.keep3DLashes; enabled: studio.hasEyeReference; onToggled: studio.setStyleToggle("keep3DLashes", checked) }
        }
    }
    component PixelNeighbor: Item {
        id: side
        required property int direction
        property var neighbor
        readonly property string label: direction < 0 ? "Previous skin" : "Next skin"
        signal navigate()
        Pill {
            objectName: side.direction < 0 ? "previousPixelSkin" : "nextPixelSkin"
            visible: !!side.neighbor
            width: side.width; height: Math.min(side.height, 142)
            anchors.verticalCenter: parent.verticalCenter
            text: side.label
            verticalPadding: 6; horizontalPadding: 4
            onClicked: side.navigate()
            contentItem: Row {
                spacing: 0
                layoutDirection: side.direction < 0 ? Qt.LeftToRight : Qt.RightToLeft
                opacity: parent.hovered || parent.visualFocus ? 1 : .52
                Behavior on opacity { NumberAnimation { duration: 110 } }
                Text {
                    width: 24
                    text: side.direction < 0 ? "‹" : "›"
                    color: window.accent; font.pixelSize: 38
                    horizontalAlignment: Text.AlignHCenter
                    anchors.verticalCenter: parent.verticalCenter
                }
                Image {
                    width: Math.min(72, Math.max(25, parent.width - 24))
                    height: Math.min(114, side.height - 12)
                    anchors.verticalCenter: parent.verticalCenter
                    source: side.neighbor ? side.neighbor.thumbnail : ""
                    fillMode: Image.PreserveAspectFit
                    smooth: false
                }
            }
            SoftTip { text: side.neighbor ? side.label + " · " + side.neighbor.name : ""; visible: parent.hovered }
        }
    }
    Component {
        id: pixelWorkspace
        ColumnLayout {
            id: editor
            readonly property bool modalOpen: resetCorrections.visible || assignAll.visible
            property string material: "hair"
            property string tool: "paint"
            property bool baseVisible: true
            property bool outerVisible: true
            readonly property string layerMode: baseVisible ? (outerVisible ? "visible" : "base")
                                                            : (outerVisible ? "outer" : "none")
            property bool showTexture: false
            property bool viewportFailed: false
            property bool compare: true
            property real comparePosition: window.comparePosition
            property bool showGuides: true
            property var hiddenParts: []
            property string matchNotice: ""
            readonly property bool use3D: studio.viewportAvailable && !studio.samplingColor && !showTexture && !viewportFailed
            property var materialNames: ["Hair", "Skin", "Eyes", "Outfit", "Accessories", "Ignore"]
            property var materialKeys: ["hair", "skin", "eyes", "outfit", "accessory", "ignore"]
            property var materialColors: ["#da5daa", "#f7b580", "#5be2d3", "#59a1eb", "#f6cc52", "#505050"]
            readonly property string skinKey: studio.styleSkinKey
            onSkinKeyChanged: { if (pixels) pixels.clearSelection(); matchNotice = "" }
            function queueHistory(undo) { return use3D && fixViewport.queueAction(undo ? "undo" : "redo", 0) }
            function navigate(step) {
                if (!use3D || !fixViewport.queueAction("navigate", step)) studio.navigatePixels(step)
            }
            function finishMatch(count) {
                if (count < 0) return
                matchNotice = "Marked " + count + (count === 1 ? " matching pixel as " : " matching pixels as ")
                              + materialNames[materialKeys.indexOf(material)] + "."
                matchNoticeTimer.restart()
            }
            Timer { id: matchNoticeTimer; interval: 4500; onTriggered: editor.matchNotice = "" }
            spacing: 3
            RowLayout {
                Layout.rightMargin: 28
                LabelText {
                    objectName: "pixelWorkspaceTitle"
                    text: studio.samplingColor ? "Pick " + studio.samplingTarget : "Edit Color Areas"
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Caption { text: studio.selectedName; Layout.maximumWidth: 250; elide: Text.ElideRight }
                Caption { visible: !studio.samplingColor; text: studio.correctionCount + " corrected" }
                Pill {
                    visible: studio.samplingTarget === "hair color" || studio.samplingTarget === "skin tone"
                    text: "Use detected " + studio.samplingTarget
                    onClicked: {
                        const sampled = studio.samplingTarget === "hair color" ? studio.sampleHair() : studio.sampleSkinTone()
                        if (sampled) studio.closeEditor()
                    }
                }
                Pill {
                    objectName: "fixPixels3D"
                    visible: studio.viewportAvailable && !studio.samplingColor && !editor.viewportFailed
                    text: editor.use3D ? "Show texture" : "Show 3D"
                    active: editor.use3D
                    onClicked: {
                        studio.endPixelStroke()
                        if (editor.tool !== "match") editor.tool = "paint"
                        editor.showTexture = editor.use3D
                    }
                }
                Pill {
                    objectName: "editorCompare"
                    visible: editor.use3D
                    text: "Compare"; active: editor.compare
                    onClicked: { studio.endPixelStroke(); editor.compare = !editor.compare }
                    SoftTip { text: "Original on the left, styled on the right"; visible: parent.hovered }
                }
                Pill {
                    objectName: "paintSkinMode"
                    visible: !studio.samplingColor
                    text: studio.texturePainting ? "Color Areas" : "Paint Skin"
                    active: studio.texturePainting
                    onClicked: {
                        editor.tool = "paint"
                        editor.matchNotice = ""
                        studio.setTexturePainting(!studio.texturePainting)
                    }
                }
                Pill {
                    objectName: "pixelZoomOut"; text: "−"; horizontalPadding: 8
                    enabled: editor.use3D ? fixViewport.ready && fixViewport.viewZoom > .65 : pixels.zoom > 1
                    onClicked: editor.use3D ? fixViewport.control("zoom", 1 / 1.5) : pixels.zoomBy(1 / 1.5)
                    SoftTip { text: "Zoom out"; visible: parent.hovered }
                }
                Pill {
                    objectName: "pixelZoomIn"; text: "+"; horizontalPadding: 8
                    enabled: editor.use3D ? fixViewport.ready && fixViewport.viewZoom < 3 : pixels.zoom < 12
                    onClicked: editor.use3D ? fixViewport.control("zoom", 1.5) : pixels.zoomBy(1.5)
                    SoftTip { text: "Zoom in"; visible: parent.hovered }
                }
                Pill {
                    objectName: "pixelFit"; text: "Fit"
                    enabled: !editor.use3D || fixViewport.ready
                    onClicked: editor.use3D ? fixViewport.control("fit", 0) : pixels.fit()
                }
            }
            RowLayout {
                visible: !studio.samplingColor
                spacing: 3
                Repeater {
                    model: studio.texturePainting ? [] : editor.materialNames
                    delegate: Pill {
                        required property int index
                        required property string modelData
                        text: modelData; horizontalPadding: 8; padding: 6
                        active: editor.material === editor.materialKeys[index]
                        onClicked: {
                            editor.material = editor.materialKeys[index]
                            editor.matchNotice = ""
                            if (editor.tool !== "match") editor.tool = "paint"
                        }
                        contentItem: Row {
                            spacing: 4
                            Rectangle { width: 8; height: 8; radius: 4; color: editor.materialColors[index]; anchors.verticalCenter: parent.verticalCenter }
                            LabelText { text: modelData }
                        }
                    }
                }
                Rectangle {
                    visible: !studio.texturePainting
                    Layout.preferredWidth: 1; Layout.preferredHeight: 20
                    Layout.leftMargin: 4; Layout.rightMargin: 4
                    color: window.line
                }
                Pill {
                    id: matchButton
                    visible: !studio.texturePainting
                    objectName: "matchPixelColor"
                    text: "Match color"
                    checkable: true
                    checked: editor.tool === "match"
                    active: checked
                    enabled: !editor.use3D || fixViewport.ready
                    horizontalPadding: 9; padding: 7
                    onClicked: {
                        studio.endPixelStroke()
                        editor.matchNotice = ""
                        editor.tool = checked ? "match" : "paint"
                    }
                    background: Rectangle {
                        radius: height / 2
                        color: matchButton.checked ? "#ded0f4"
                             : matchButton.hovered ? "#eee1f8" : "#f7eefc"
                        border.color: matchButton.checked || matchButton.visualFocus ? window.accent : "#dfcbed"
                        border.width: matchButton.visualFocus ? 2 : 1
                    }
                    contentItem: Row {
                        spacing: 5
                        Image {
                            objectName: "matchWandIcon"
                            source: "icons/magic-wand.svg"
                            width: 17; height: 17
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: matchButton.text
                            color: "#614395"
                            font.pixelSize: 13; font.weight: Font.DemiBold
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        opacity: matchButton.enabled ? 1 : .45
                    }
                    SoftTip {
                        text: "Pick exact color matches. Click again to return to the brush."
                        visible: matchButton.hovered
                    }
                }
                Pill {
                    objectName: "texturePaintColor"
                    visible: studio.texturePainting
                    text: "Paint color " + studio.textureColor
                    onClicked: studio.chooseTextureColor()
                }
                Pill {
                    objectName: "savePaintedSkin"
                    visible: studio.texturePainting
                    enabled: studio.hasTextureDraft
                    text: "Save As New Skin"
                    active: true
                    onClicked: studio.saveTextureAs()
                }
                Pill {
                    objectName: "revertPaintedSkin"
                    visible: studio.texturePainting
                    enabled: studio.hasTextureDraft
                    text: "Revert to Original"
                    onClicked: studio.revertTextureDraft()
                }
                Pill {
                    objectName: "mirrorPixels"
                    text: "Mirror"; checkable: true; active: checked
                    horizontalPadding: 8; padding: 7
                    onToggled: studio.setMirrorPixels(checked)
                    SoftTip { text: "Mirror brush edits across the character"; visible: parent.hovered }
                }
                Pill {
                    objectName: "approveVisiblePixels"
                    visible: editor.use3D && !studio.texturePainting
                    enabled: fixViewport.ready
                    text: "Looks good!"
                    onClicked: fixViewport.queueAction("approve", 0)
                    SoftTip { text: "Approve visible " + editor.material + " pixels from this angle"; visible: parent.hovered }
                }
                Pill {
                    objectName: "unapproveVisiblePixels"
                    visible: editor.use3D && !studio.texturePainting
                    enabled: fixViewport.ready
                    text: "Undo approval"
                    onClicked: fixViewport.queueAction("unapprove", 0)
                    SoftTip { text: "Remove approval for visible " + editor.material + " pixels"; visible: parent.hovered }
                }
                ArmModelPicker {
                    objectName: "pixelArmModel"
                    visible: !studio.samplingColor
                    Layout.preferredWidth: 112
                }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                visible: !studio.samplingColor && !studio.texturePainting
                Caption { text: "BODY SHADING" }
                SoftCombo {
                    objectName: "bodyShadingBase"
                    Layout.preferredWidth: 215
                    property var bases: studio.shadingBases.filter(item => item.key !== studio.selectedSkinKey)
                    property var keys: ["", ...bases.map(item => item.key)]
                    model: ["Original shading", ...bases.map(item => item.name)]
                    currentIndex: Math.max(0, keys.indexOf(studio.styleOptions.shadingBase))
                    onActivated: studio.useShadingBase(keys[currentIndex])
                }
                Caption {
                    visible: !studio.shadingBases.length
                    text: "Mark a skin as a shading base in the wardrobe to use it here."
                }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                PixelNeighbor {
                    visible: !studio.samplingColor
                    Layout.preferredWidth: Math.min(124, editor.width * .105); Layout.fillHeight: true
                    direction: -1; neighbor: studio.pixelNeighbors.previous
                    onNavigate: editor.navigate(-1)
                }
                ColumnLayout {
                    visible: editor.use3D
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 3
                    Caption { text: "LAYERS" }
                    Toggle {
                        objectName: "baseLayerVisible"
                        text: "Base"; checked: editor.baseVisible
                        onToggled: { studio.endPixelStroke(); editor.baseVisible = checked }
                    }
                    Toggle {
                        objectName: "outerLayerVisible"
                        text: "Outer"; checked: editor.outerVisible
                        onToggled: { studio.endPixelStroke(); editor.outerVisible = checked }
                    }
                }
                PixelCanvas {
                    id: pixels
                    visible: !editor.use3D
                    Layout.fillWidth: true; Layout.fillHeight: true
                    source: studio.editorSource
                    atlasGuides: editor.showGuides && !studio.samplingColor ? studio.atlasGuides : []
                    matchTool: editor.tool === "match"
                    panTool: editor.tool === "pan"; selectTool: editor.tool === "select"
                    onPaintCell: function(x, y, restore) {
                        if (matchTool && !restore) editor.finishMatch(studio.matchPixelColor(x, y, editor.material))
                        else studio.paintPixel(x, y, editor.material, restore)
                    }
                    onStrokeEnded: studio.endPixelStroke()
                }
                Image {
                    visible: !studio.samplingColor && !editor.use3D
                    Layout.preferredWidth: Math.min(140, editor.width * .23); Layout.fillHeight: true
                    source: studio.stageSource; cache: false; smooth: false; fillMode: Image.PreserveAspectFit
                    SoftTip { text: "Live styled preview"; visible: liveHover.hovered }
                    HoverHandler { id: liveHover }
                }
                Rectangle {
                    visible: editor.use3D
                    Layout.fillWidth: true; Layout.fillHeight: true
                    radius: 14
                    color: "#eee5f5"
                    ViewportHost {
                        id: fixViewport
                        objectName: "fixViewport"
                        anchors.fill: parent
                        requested: !studio.samplingColor && !editor.viewportFailed
                        editing: true
                        painting: !editor.modalOpen
                        matchingColor: editor.tool === "match"
                        previewMode: editor.compare ? "Compare" : "Styled"
                        comparePosition: editor.comparePosition
                        material: editor.material
                        layerMode: editor.layerMode
                        hiddenParts: editor.hiddenParts.join(",")
                        onColorMatched: function(count) { editor.finishMatch(count) }
                        onReviewed: function(count, approved) {
                            if (count < 0) return
                            editor.matchNotice = (approved ? "Approved " : "Unapproved ") + count + " visible " + editor.material + " pixels."
                            matchNoticeTimer.restart()
                        }
                        onFailedChanged: if (failed) editor.viewportFailed = true
                    }
                    CompareDivider {
                        objectName: "editorCompareHandle"
                        visible: editor.compare && fixViewport.ready
                        z: 2
                        fraction: editor.comparePosition
                        onMoved: function(position) { editor.comparePosition = position }
                    }
                    Caption {
                        visible: !fixViewport.ready
                        width: parent.width - 20
                        anchors.centerIn: parent
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        text: "Starting the 3D view…"
                    }
                }
                ColumnLayout {
                    objectName: "editorBodyParts"
                    visible: editor.use3D
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 3
                    Caption { text: "BODY PARTS" }
                    Repeater {
                        model: ["Head", "Torso", "Right arm", "Left arm", "Right leg", "Left leg"]
                        Toggle {
                            required property string modelData
                            objectName: "bodyPart" + modelData
                            text: modelData; checked: !editor.hiddenParts.includes(modelData)
                            onToggled: {
                                studio.endPixelStroke()
                                editor.hiddenParts = checked ? editor.hiddenParts.filter(part => part !== modelData)
                                                             : [...editor.hiddenParts, modelData]
                            }
                        }
                    }
                    Pill {
                        text: "Show all"; enabled: editor.hiddenParts.length > 0
                        horizontalPadding: 5; padding: 5
                        onClicked: editor.hiddenParts = []
                    }
                }
                PixelNeighbor {
                    visible: !studio.samplingColor
                    Layout.preferredWidth: Math.min(124, editor.width * .105); Layout.fillHeight: true
                    direction: 1; neighbor: studio.pixelNeighbors.next
                    onNavigate: editor.navigate(1)
                }
            }
            RowLayout {
                visible: !studio.samplingColor
                spacing: 3
                Pill {
                    objectName: "atlasGuideToggle"
                    visible: !editor.use3D; text: "Part labels"; horizontalPadding: 8; padding: 6
                    active: editor.showGuides
                    onClicked: editor.showGuides = !editor.showGuides
                }
                Pill { visible: !editor.use3D; text: "Pan"; horizontalPadding: 8; padding: 6; active: editor.tool === "pan"; onClicked: editor.tool = active ? "paint" : "pan" }
                Pill { visible: !editor.use3D; text: "Select area"; horizontalPadding: 8; padding: 6; active: editor.tool === "select"; onClicked: editor.tool = active ? "paint" : "select" }
                SoftCombo {
                    visible: !editor.use3D
                    Layout.preferredWidth: 110
                    model: ["All masks", ...editor.materialNames, "Automatic only", "Texture only"]
                    onActivated: studio.setMaskFilter(["all", ...editor.materialKeys, "auto", "none"][currentIndex])
                    SoftTip { text: "Filter mask colors; white corner marks indicate manual edits"; visible: parent.hovered }
                }
                Item { Layout.fillWidth: true }
                Pill {
                    objectName: "duplicateLook"
                    text: "Duplicate look"
                    visible: !studio.samplingColor && !studio.texturePainting
                    onClicked: studio.duplicateLook()
                    SoftTip { text: "Make another editable look from this skin"; visible: parent.hovered }
                }
                Pill {
                    objectName: "setAllPixels"
                    text: "Set all to " + editor.materialNames[editor.materialKeys.indexOf(editor.material)] + "…"
                    visible: !studio.samplingColor && !studio.texturePainting
                    onClicked: assignAll.open()
                }
                Pill {
                    visible: !editor.use3D && !studio.texturePainting
                    text: "Revert area"; horizontalPadding: 6; padding: 6
                    enabled: pixels.hasSelection && studio.correctionCount > 0
                    onClicked: { resetCorrections.all = false; resetCorrections.open() }
                }
                Pill {
                    objectName: "resetAllPixels"; text: "Revert all fixes"; horizontalPadding: 6; padding: 6
                    visible: !studio.texturePainting
                    enabled: studio.correctionCount > 0
                    onClicked: { resetCorrections.all = true; resetCorrections.open() }
                }
            }
            Caption {
                text: studio.editorError || (studio.samplingColor ? "Click a visible pixel to set the " + studio.samplingTarget + "."
                       : studio.texturePainting ? "Left-drag paints · Right-click restores the original color · Save As keeps your edits"
                       : editor.matchNotice ? editor.matchNotice
                       : editor.tool === "match" ? "Pick a pixel to mark every exact match on this skin as "
                                                  + editor.materialNames[editor.materialKeys.indexOf(editor.material)] + "."
                       : editor.use3D ? "Left-drag marks · Right-click restores auto · Middle-drag rotates · Shift + middle-drag pans · Scroll zooms"
                       : "Left paints · Right restores auto · Scroll zooms · Middle-drag pans")
                elide: Text.ElideRight; Layout.fillWidth: true
            }
            Dialog {
                id: assignAll
                anchors.centerIn: Overlay.overlay
                title: "Set all to " + editor.materialNames[editor.materialKeys.indexOf(editor.material)] + "?"
                modal: true
                standardButtons: Dialog.Ok | Dialog.Cancel
                LabelText { text: "This replaces material assignments on both layers. You can undo it in one step." }
                onAccepted: {
                    const count = studio.setAllPixels(editor.material)
                    if (count >= 0) {
                        editor.tool = "paint"
                        editor.matchNotice = "Assigned " + count + " pixels to "
                                             + editor.materialNames[editor.materialKeys.indexOf(editor.material)] + "."
                        matchNoticeTimer.restart()
                    }
                }
            }
            Dialog {
                id: resetCorrections
                objectName: "resetPixelDialog"
                property bool all: false
                anchors.centerIn: Overlay.overlay
                title: all ? "Reset all corrections?" : "Reset selected corrections?"
                modal: true
                standardButtons: Dialog.Ok | Dialog.Cancel
                LabelText { text: "These pixels will return to automatic detection." }
                onAccepted: {
                    if (all) studio.resetPixels(0, 0, 63, 63)
                    else studio.resetPixels(pixels.firstCell.x, pixels.firstCell.y, pixels.lastCell.x, pixels.lastCell.y)
                    pixels.clearSelection()
                }
            }
        }
    }
    Component {
        id: eyeWorkspace
        ColumnLayout {
            id: eyeEditor
            readonly property bool modalOpen: designName.visible
            property string material: "iris"
            readonly property string colorKey: ({iris:"irisColor", liner:"linerColor", white:"whiteColor"})[material] || "irisColor"
            readonly property string colorLabel: ({iris:"Iris color", liner:"Liner and lash color", white:"Eye white color"})[material] || ""
            spacing: 3
            RowLayout {
                Layout.rightMargin: 28
                LabelText { text: "Design Eyes"; font.bold: true }
                Item { Layout.fillWidth: true }
                Caption { text: studio.eyeReferenceName; elide: Text.ElideRight; Layout.preferredWidth: Math.min(eyeEditor.width * .38, 190) }
                Pill { text: "−"; horizontalPadding: 8; enabled: eyesCanvas.zoom > 1; onClicked: eyesCanvas.zoomBy(1 / 1.5); SoftTip { text: "Zoom out"; visible: parent.hovered } }
                Pill { text: "+"; horizontalPadding: 8; enabled: eyesCanvas.zoom < 12; onClicked: eyesCanvas.zoomBy(1.5); SoftTip { text: "Zoom in"; visible: parent.hovered } }
                Pill { text: "Fit"; onClicked: eyesCanvas.fit() }
            }
            RowLayout {
                Caption { text: "PAINT WITH" }
                Repeater {
                    model: [{key: "iris", name: "Iris"}, {key: "liner", name: "Liner & lashes"},
                            {key: "white", name: "Whites"}, {key: "eraser", name: "Eraser"}]
                    Pill {
                        required property var modelData
                        text: modelData.name; active: eyeEditor.material === modelData.key
                        padding: 6; horizontalPadding: 8
                        onClicked: eyeEditor.material = modelData.key
                    }
                }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                PixelCanvas {
                    id: eyesCanvas
                    Layout.fillWidth: true; Layout.fillHeight: true
                    gridSize: 8; source: studio.editorSource
                    onPaintCell: function(x, y, restore) { studio.paintEye(x, y, eyeEditor.material, restore) }
                    onStrokeEnded: studio.endEyeStroke()
                }
                Item {
                    Layout.preferredWidth: Math.min(130, eyeEditor.width * .22)
                    Layout.maximumWidth: Layout.preferredWidth; Layout.fillWidth: false; Layout.fillHeight: true
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width; spacing: 6
                        Image {
                            width: parent.width; height: width
                            source: studio.styledFaceSource; cache: false; smooth: false; fillMode: Image.PreserveAspectFit
                        }
                        Caption { text: "On this skin"; anchors.horizontalCenter: parent.horizontalCenter }
                    }
                }
                ScrollView {
                    id: eyeColorsScroll
                    visible: eyeEditor.material !== "eraser"
                    Layout.preferredWidth: 172; Layout.fillHeight: true
                    clip: true; contentWidth: availableWidth
                    ColumnLayout {
                        width: eyeColorsScroll.availableWidth; spacing: 4
                        Caption { text: eyeEditor.colorLabel }
                        SwatchField {
                            Layout.fillWidth: true
                            colorKey: eyeEditor.colorKey; hex: studio.eyeColors[colorKey] || ""
                        }
                        HslSliders {
                            Layout.fillWidth: true
                            colorKey: eyeEditor.colorKey
                        }
                        Pill {
                            text: "Restore source color"
                            horizontalPadding: 6
                            onClicked: studio.resetEyeColor(eyeEditor.colorKey)
                        }
                    }
                }
            }
            RowLayout {
                spacing: 5
                Toggle { text: "Mirror eyes"; checked: studio.styleOptions.eyeMirror; onToggled: studio.setStyleToggle("eyeMirror", checked) }
                Item { Layout.fillWidth: true }
                SoftCombo {
                    Layout.preferredWidth: 145
                    model: ["Load design…", ...studio.eyeDesignNames]
                    onActivated: { if (currentIndex > 0) studio.loadEyeDesign(currentText); currentIndex = 0 }
                }
                Pill { text: "Save design…"; horizontalPadding: 7; onClicked: designName.open() }
            }
            Caption { text: studio.editorError || "Paint in the eye band · Right restores reference · Scroll to zoom"; elide: Text.ElideRight; Layout.fillWidth: true }
            Dialog {
                id: designName
                title: "Name this eye design"
                anchors.centerIn: Overlay.overlay
                modal: true
                standardButtons: Dialog.Save | Dialog.Cancel
                onOpened: { designField.text = ""; designField.forceActiveFocus() }
                onAccepted: studio.saveEyeDesign(designField.text)
                TextField { id: designField; placeholderText: "e.g. Rose sparkle"; maximumLength: 60; onAccepted: designName.accept() }
            }
        }
    }
    function stepHistory(undo) {
        if (studio.editorMode === "pixels" && workspaceLoader.item && workspaceLoader.item.queueHistory(undo)) return
        if (undo) studio.undo()
        else studio.redo()
    }
    Shortcut { sequences: [StandardKey.Undo]; onActivated: window.stepHistory(true) }
    Shortcut { sequences: [StandardKey.Redo]; onActivated: window.stepHistory(false) }
    Shortcut { sequence: "1"; enabled: window.sortingKeysEnabled; autoRepeat: false; onActivated: window.sortSkin("favorite") }
    Shortcut { sequence: "2"; enabled: window.sortingKeysEnabled; autoRepeat: false; onActivated: window.sortSkin("keep") }
    Shortcut { sequence: "3"; enabled: window.sortingKeysEnabled; autoRepeat: false; onActivated: window.sortSkin("maybe") }
    Shortcut { sequence: "4"; enabled: window.sortingKeysEnabled; autoRepeat: false; onActivated: window.sortSkin("remove") }
    Shortcut {
        sequence: "Escape"
        enabled: studio.editorMode !== "" && workspaceLoader.item !== null && !workspaceLoader.item.modalOpen
        onActivated: studio.closeEditor()
    }
    Connections {
        target: studio
        function syncCarousel() {
            if (studio.editorMode === "" && carousel.currentIndex !== studio.selectedIndex)
                carousel.currentIndex = studio.selectedIndex
        }
        function onSelectionChanged() { Qt.callLater(syncCarousel) }
        function onEditorChanged() { Qt.callLater(syncCarousel) }
    }

    header: Rectangle {
        height: 70; color: "#ffffff"
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24; spacing: 20
            Text { text: "Daily Dress"; color: window.accent; font.pixelSize: 25; font.weight: Font.Bold }
            Rectangle { width: 1; height: 28; color: window.line }
            ColumnLayout {
                spacing: 1; Layout.maximumWidth: 240
                LabelText { text: studio.wardrobeName; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                Caption { text: studio.wardrobeInfo }
            }
            Pill { text: "Change wardrobe…"; visible: !window.activeWorkspace; onClicked: studio.chooseSource() }
            Item { Layout.fillWidth: true }
            Caption { text: studio.statusText; color: "#4b826b" }
            Pill { objectName: "studioUndo"; text: "Undo"; enabled: studio.canUndo; onClicked: window.stepHistory(true); SoftTip { text: "Ctrl+Z"; visible: parent.hovered } }
            Pill { objectName: "studioRedo"; text: "Redo"; enabled: studio.canRedo; onClicked: window.stepHistory(false); SoftTip { text: "Ctrl+Y"; visible: parent.hovered } }
            Pill { text: window.inspectorOpen ? "Hide inspector" : "Inspector"; visible: !window.activeWorkspace; onClicked: window.inspectorOpen = !window.inspectorOpen }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: window.line }
    }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 16
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 18
            Item {
                id: stage
                objectName: "stage"
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                Rectangle {
                    objectName: "stageCard"
                    anchors.fill: parent
                    anchors.topMargin: window.activeWorkspace ? 6 : 0
                    anchors.rightMargin: window.activeWorkspace ? 6 : 0
                    radius: 26
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#f3edfc" }
                        GradientStop { position: 1; color: "#faf6ff" }
                    }
                }
                Item {
                anchors.fill: parent
                visible: studio.editorMode === ""
                enabled: visible
                Column {
                    x: 24; y: 21; spacing: 5
                    width: openPixelsButton.visible ? Math.max(0, openPixelsButton.x - x - 12) : stage.width - 120
                    Caption { text: window.viewMode === "Compare" ? "COMPARE · ORIGINAL LEFT / STYLED RIGHT" : window.viewMode.toUpperCase() + " PREVIEW"; color: window.accent; width: parent.width; elide: Text.ElideRight }
                    Text {
                        id: stageName
                        text: studio.selectedName; color: window.ink; font.pixelSize: 20; font.weight: Font.DemiBold
                        width: parent.width; elide: Text.ElideRight
                        HoverHandler { id: stageNameHover }
                        SoftTip { text: stageName.text; visible: stageName.truncated && stageNameHover.hovered }
                    }
                }
                Rectangle {
                    visible: studio.hasSkins
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: stage.height - 77
                    width: Math.min(230, stage.width * .35); height: 24
                    radius: width / 2; color: "#dccfe9"; opacity: .55
                }
                Item {
                    id: previewFrame
                    property real zoom: 1
                    z: 1
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: window.height < 760 ? 58 : 76
                    width: parent.width - 64
                    height: parent.height - (window.height < 760 ? 117 : 140)
                    scale: zoom
                    transformOrigin: Item.Bottom
                    ViewportHost {
                        id: gpuPreview
                        objectName: "gpuPreview"
                        anchors.fill: parent
                        requested: studio.hasSkins
                        idleAnimation: studio.editorMode === "" && window.visible
                        previewMode: window.viewMode
                        comparePosition: window.comparePosition
                        onReadyChanged: studio.useViewportPreview(ready)
                    }
                    Image {
                        id: stageImage; objectName: "stageImage"
                        anchors.fill: parent
                        visible: !gpuPreview.ready
                        source: studio.hasSkins ? (window.viewMode === "Original" ? studio.originalSource : studio.stageSource) : ""
                        cache: false; smooth: false; mipmap: false; fillMode: Image.PreserveAspectFit
                    }
                    Item {
                        visible: window.viewMode === "Compare" && !gpuPreview.ready
                        width: parent.width * window.comparePosition; height: parent.height; clip: true
                        Image {
                            width: previewFrame.width; height: previewFrame.height
                            source: studio.hasSkins ? studio.originalSource : ""
                            cache: false; smooth: false; mipmap: false; fillMode: Image.PreserveAspectFit
                        }
                    }
                    CompareDivider {
                        objectName: "compareHandle"
                        visible: window.viewMode === "Compare"
                        fraction: window.comparePosition
                        onMoved: function(position) { window.comparePosition = position }
                    }
                }
                Text {
                    visible: !studio.hasSkins
                    anchors.centerIn: parent
                    text: studio.selectedMeta
                    color: window.muted; font.pixelSize: 18
                }
                MouseArea {
                    anchors.fill: parent
                    property real lastX: 0
                    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    onPressed: function(mouse) {
                        lastX = mouse.x
                        hint.visible = false
                        gpuPreview.orbit("orbitStart", mouse.x, mouse.y)
                    }
                    onPositionChanged: function(mouse) {
                        if (!pressed) return
                        if (gpuPreview.ready) gpuPreview.orbit("move", mouse.x, mouse.y)
                        else { studio.rotate((mouse.x - lastX) * .7); lastX = mouse.x }
                    }
                    onReleased: gpuPreview.orbit("finish", 0, 0)
                    onCanceled: gpuPreview.orbit("finish", 0, 0)
                    onDoubleClicked: { studio.resetView(); gpuPreview.control("resetView", 0); previewFrame.zoom = 1 }
                    onWheel: function(wheel) {
                        previewFrame.zoom = Math.max(.65, Math.min(1.45, previewFrame.zoom + wheel.angleDelta.y / 1200))
                    }
                }
                Caption {
                    id: hint; text: "Drag to turn · Scroll to zoom"
                    anchors.left: parent.left; anchors.leftMargin: 24; anchors.top: parent.top; anchors.topMargin: 78
                    Timer { interval: 6500; running: true; onTriggered: hint.visible = false }
                }
                Pill {
                    text: "Reset view"
                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16
                    onClicked: { studio.resetView(); gpuPreview.control("resetView", 0); previewFrame.zoom = 1 }
                }
                Pill {
                    id: openPixelsButton
                    objectName: "fixPixels"
                    text: "Edit Color Areas"
                    active: true
                    visible: studio.hasSkins
                    z: 2
                    anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top
                    anchors.topMargin: 12
                    onClicked: studio.openPixels()
                    SoftTip { text: "Paint corrections to automatic material detection"; visible: parent.hovered }
                }
                ArmModelPicker {
                    objectName: "stageArmModel"
                    visible: studio.hasSkins
                    width: 112
                    anchors.right: parent.right; anchors.top: parent.top
                    anchors.topMargin: 54; anchors.rightMargin: 16
                }
                Row {
                    z: 2; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 9
                    Repeater {
                            model: ["Original", "Compare", "Styled"]
                        delegate: Pill {
                            required property string modelData
                            text: modelData; active: window.viewMode === modelData
                            onClicked: window.viewMode = modelData
                        }
                    }
                }
                Caption {
                    z: 2; anchors.right: parent.right; anchors.rightMargin: 20; anchors.bottom: parent.bottom; anchors.bottomMargin: 19
                    text: studio.previewError || (studio.previewBusy ? "Updating preview…" : "")
                    color: studio.previewError ? "#ad5275" : window.muted
                    width: Math.min(240, parent.width / 3); elide: Text.ElideRight
                    horizontalAlignment: Text.AlignRight
                }
                }
                Loader {
                    id: workspaceLoader
                    anchors.fill: parent; anchors.margins: 12
                    active: studio.editorMode !== ""
                    sourceComponent: studio.editorMode === "eyes" ? eyeWorkspace : pixelWorkspace
                    onLoaded: item.forceActiveFocus()
                }
                EditorClose {
                    objectName: studio.editorMode === "eyes" ? "leaveEyes" : "leavePixels"
                    visible: window.activeWorkspace
                    z: 3
                    anchors.top: parent.top
                    anchors.right: parent.right
                }
            }
            Rectangle {
                id: inspector
                objectName: "inspector"
                visible: window.inspectorOpen && !window.activeWorkspace
                Layout.preferredWidth: window.width < 1150 ? 245 : 285
                Layout.fillHeight: true
                radius: 24; color: "#ffffff"; border.color: window.line
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 15
                    spacing: 6
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: referenceCard.implicitHeight + 14
                            radius: 14; color: "#f7f1fc"; border.color: "#ede3f6"
                            ColumnLayout {
                                id: referenceCard
                                width: parent.width - 16; x: 8; y: 7; spacing: 3
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 4
                                    Caption { text: "STYLE REFERENCE"; color: window.accent }
                                    Item { Layout.fillWidth: true }
                                    Caption {
                                        visible: studio.hasSkins && !studio.hasReference
                                        text: studio.selectedMeta
                                        font.pixelSize: 10
                                    }
                                    Image {
                                        id: referencePortrait
                                        objectName: "referencePortrait"
                                        visible: studio.hasReference
                                        source: studio.referenceSource
                                        Layout.preferredWidth: 29; Layout.preferredHeight: 36
                                        fillMode: Image.PreserveAspectFit; smooth: false
                                        Accessible.name: studio.referenceFilename
                                        HoverHandler { id: referencePortraitHover }
                                        SoftTip { text: studio.referenceFilename; visible: referencePortraitHover.hovered }
                                    }
                                    ToolButton {
                                        objectName: "applyReferenceHair"
                                        visible: studio.referenceHairColor !== ""
                                        Layout.preferredWidth: 15; Layout.preferredHeight: 15
                                        Accessible.name: "Use reference hair color on this skin"
                                        onClicked: studio.useReferenceHair()
                                        background: Rectangle { radius: 5; color: studio.referenceHairColor || "transparent" }
                                        SoftTip { text: "Use reference hair color on this skin"; visible: parent.hovered }
                                    }
                                    Rectangle {
                                        visible: studio.referenceSkinColor !== ""
                                        width: 15; height: 15; radius: 5
                                        color: studio.referenceSkinColor || "transparent"
                                        SoftTip { text: "Reference skin tone " + studio.referenceSkinColor; visible: refSkinHover.hovered }
                                        HoverHandler { id: refSkinHover }
                                    }
                                }
                                Caption {
                                    Layout.fillWidth: true; wrapMode: Text.Wrap; font.weight: Font.Normal
                                    visible: !studio.hasReference || !studio.referenceHairColor
                                    text: !studio.hasReference ? "Choose a shared reference for hair and skin tone."
                                          : "No hair color detected on this reference."
                                }
                                Pill {
                                    objectName: "useStyleReference"
                                    text: "Use selected skin as reference"
                                    Layout.fillWidth: true
                                    active: true; padding: 6; horizontalPadding: 5
                                    enabled: studio.hasSkins
                                    SoftTip { text: "Use this palette when a skin is set to match the reference"; delay: 650; visible: parent.hovered }
                                    onClicked: studio.setReference()
                                }
                            }
                        }
                        GridLayout {
                            objectName: "materialSelector"
                            Layout.fillWidth: true
                            columns: 3
                            columnSpacing: 3; rowSpacing: 3
                            Repeater {
                                model: [{key:"hair", name:"Hair"}, {key:"eyes", name:"Eyes"}, {key:"skin", name:"Skin tone"},
                                        {key:"outfit", name:"Outfit"}, {key:"accessory", name:"Accessories"}]
                                Pill {
                                    required property var modelData
                                    objectName: modelData.key + "MaterialTab"
                                    Layout.fillWidth: true
                                    Layout.columnSpan: modelData.key === "accessory" ? 2 : 1
                                    text: modelData.name
                                    active: window.activeMaterial === modelData.key
                                    padding: 5; horizontalPadding: 7
                                    onClicked: window.activeMaterial = modelData.key
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: window.line }
                        ScrollView {
                            id: inspectorScroll
                            objectName: "inspectorScroll"
                            Layout.fillWidth: true; Layout.fillHeight: true
                            contentWidth: availableWidth
                            clip: true
                            Loader {
                                objectName: "materialEditor"
                                width: inspectorScroll.availableWidth
                                sourceComponent: window.activeMaterial === "eyes" ? eyesInspector : colorInspector
                            }
                        }
                }
            }
        }

        Rectangle {
            id: tray
            objectName: "wardrobeTray"
            visible: !window.activeWorkspace
            Layout.fillWidth: true; Layout.preferredHeight: window.height < 760 ? 242 : 277
            color: "#fffdfb"; radius: 24; border.color: window.line
            ColumnLayout {
                anchors.fill: parent; anchors.topMargin: 10; spacing: 2
                RowLayout {
                    Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18
                    Layout.minimumHeight: 49; Layout.maximumHeight: 49
                    spacing: 8
                    Pill {
                        objectName: "reviewUnsorted"
                        text: studio.reviewMode ? "‹ Back to wardrobe" : "Review Unsorted"
                        active: true; horizontalPadding: 12
                        enabled: !window.activeWorkspace
                        onClicked: {
                            carousel.cancelFlick()
                            studio.toggleReview()
                            carousel.forceActiveFocus()
                        }
                        SoftTip { text: "Review all undecided skins · 1 Favorite, 2 Keep, 3 Maybe, 4 Remove"; delay: 550; visible: parent.hovered }
                    }
                    Caption {
                        objectName: "reviewProgress"
                        visible: studio.reviewMode
                        text: studio.reviewReviewed + " reviewed · " + studio.reviewRemaining + " left"
                    }
                    ProgressBar {
                        id: reviewMeter
                        visible: studio.reviewMode && studio.reviewReviewed + studio.reviewRemaining > 0
                        Layout.preferredWidth: 88
                        Layout.preferredHeight: 5
                        to: Math.max(1, studio.reviewReviewed + studio.reviewRemaining)
                        value: studio.reviewReviewed
                        padding: 0
                        background: Rectangle { radius: 3; color: "#eee5f6" }
                        contentItem: Item {
                            Rectangle { width: parent.width * reviewMeter.visualPosition; height: parent.height; radius: 3; color: "#a788cb" }
                        }
                    }
                    Item { visible: studio.reviewMode; Layout.fillWidth: true }
                    Flickable {
                    visible: !studio.reviewMode
                    Layout.fillWidth: true; Layout.fillHeight: true
                    contentWidth: filterRow.implicitWidth; contentHeight: height
                    clip: true; flickableDirection: Flickable.HorizontalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    RowLayout {
                    id: filterRow
                    spacing: 4
                    Rectangle {
                        Layout.leftMargin: 4
                        implicitWidth: modeButtons.implicitWidth + 6
                        implicitHeight: modeButtons.implicitHeight + 6
                        radius: height / 2
                        color: window.assigningCategories ? window.assignmentHighlight : "#f5f1f7"
                        border.color: window.assigningCategories ? "#c8afe4" : "#e5dbec"
                        Behavior on color { ColorAnimation { duration: 125 } }
                        Row {
                            id: modeButtons
                            anchors.centerIn: parent
                            spacing: 2
                            Pill {
                                id: filterMode
                                text: "Filter"; width: 68
                                active: !window.assigningCategories
                                background: Rectangle {
                                    radius: height / 2
                                    color: filterMode.active ? "#ffffff" : "transparent"
                                }
                                onClicked: window.assigningCategories = false
                            }
                            Pill {
                                id: assignMode
                                text: "Assign"; width: 68
                                active: window.assigningCategories
                                background: Rectangle {
                                    radius: height / 2
                                    color: assignMode.active ? "#ffffff" : "transparent"
                                }
                                onClicked: {
                                    if (window.assigningCategories) return
                                    window.assigningCategories = true
                                    window.assignmentTag = studio.tagFilter || ""
                                    if (studio.tagFilter) studio.setFilter("tag:" + studio.tagFilter)
                                }
                            }
                        }
                    }
                    TextField {
                        objectName: "wardrobeSearch"
                        Layout.preferredWidth: window.width < 1150 ? 128 : 184
                        placeholderText: "Search skins…"; selectByMouse: true
                        onTextEdited: studio.setSearch(text)
                        background: Rectangle { radius: 15; color: "#f5f1f7"; border.color: parent.activeFocus ? window.accent : "transparent" }
                    }
                    Repeater {
                        model: [...(window.assigningCategories ? [] : ["All", "Kept", "Favorites", "Maybe", "Unsorted", "Removed"]),
                                ...studio.categories.map(item => "tag:" + item.key)]
                        delegate: Pill {
                            id: filterButton
                            required property string modelData
                            text: tagKey ? studio.categories.find(item => item.key === tagKey)?.name || "" : modelData
                            horizontalPadding: window.width < 1150 ? 7 : 11
                            padding: 6
                            background: Rectangle {
                                radius: 7
                                color: filterButton.active ? "#efe8f8" : filterButton.hovered ? "#f7f3fb" : "transparent"
                                border.color: filterButton.active ? "#dfd2ef" : "transparent"
                            }
                            readonly property string statusKey: ({"Kept":"kept", "Favorites":"favorite", "Maybe":"maybe", "Unsorted":"unsorted", "Removed":"remove"})[modelData] || ""
                            readonly property string tagKey: modelData.startsWith("tag:") ? modelData.slice(4) : ""
                            active: window.assigningCategories ? window.assignmentTag === tagKey :
                                modelData === "All" ? !studio.statusFilter && !studio.tagFilter :
                                (statusKey !== "" ? studio.statusFilter === statusKey : studio.tagFilter === tagKey)
                            onClicked: {
                                if (window.assigningCategories) window.assignmentTag = tagKey
                                else studio.setFilter(modelData)
                            }
                        }
                    }
                    }
                    }
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 4
                    Caption {
                        text: studio.selectionHeld ? "DECISION · OUTSIDE FILTER" : "DECISION"
                        Layout.rightMargin: 7
                        SoftTip { text: "This skin stays selected until you browse to another skin or change the filter."; visible: studio.selectionHeld && heldHover.hovered }
                        HoverHandler { id: heldHover }
                    }
                    Repeater {
                        model: [["♥ Favorite", "favorite"], ["Keep", "keep"], ["? Maybe", "maybe"], ["Remove", "remove"]]
                        delegate: Pill {
                            required property var modelData
                            required property int index
                            text: (studio.reviewMode ? (index + 1) + " · " : "") + modelData[0]
                            active: studio.selectedStatus === modelData[1]
                            enabled: studio.hasSkins && !window.activeWorkspace
                            onClicked: { window.sortSkin(modelData[1]); carousel.forceActiveFocus() }
                            SoftTip { text: "Shortcut: " + (index + 1); visible: parent.hovered }
                        }
                    }
                    Pill {
                        text: "Unsort"; horizontalPadding: 8
                        visible: !studio.reviewMode && studio.hasSkins && studio.selectedStatus !== "unsorted"
                        enabled: !window.activeWorkspace
                        onClicked: { window.sortSkin("unsorted"); carousel.forceActiveFocus() }
                        SoftTip { text: "Clear this decision"; visible: parent.hovered }
                    }
                    Rectangle { width: 1; height: 24; color: window.line; Layout.leftMargin: 11; Layout.rightMargin: 8 }
                    Caption {
                        visible: window.assigningCategories && !studio.reviewMode
                        text: window.assignmentTag
                              ? "CLICK SKINS TO ASSIGN " + (studio.categories.find(item => item.key === window.assignmentTag)?.name || "").toUpperCase()
                              : "CHOOSE A CATEGORY TO ASSIGN"
                    }
                    Pill { text: "+ Category"; onClicked: categoryDialog.showEditor("", "") }
                    Pill {
                        objectName: "markShadingBase"
                        visible: !studio.reviewMode
                        enabled: studio.hasSkins
                        active: studio.shadingBases.some(item => item.key === studio.selectedSkinKey)
                        text: active ? "✓ Shading base" : "Mark as shading base"
                        onClicked: studio.toggleShadingBase()
                        SoftTip {
                            text: "Use this skin’s body highlights and shadows as a template."
                            visible: parent.hovered
                        }
                    }
                    Pill {
                        text: "Rename…"
                        visible: window.assigningCategories && !studio.reviewMode
                        enabled: !!window.assignmentTag && window.assignmentTag !== "other"
                        onClicked: categoryDialog.showEditor(window.assignmentTag,
                            studio.categories.find(item => item.key === window.assignmentTag)?.name || "")
                    }
                    Dialog {
                        id: categoryDialog
                        property string key: ""
                        anchors.centerIn: Overlay.overlay
                        modal: true
                        title: key ? "Rename category" : "New category"
                        function showEditor(categoryKey, name) {
                            key = categoryKey
                            categoryName.text = name
                            categoryError.text = ""
                            open()
                            categoryName.forceActiveFocus()
                            categoryName.selectAll()
                        }
                        function save() {
                            categoryError.text = studio.saveCategory(key, categoryName.text)
                            if (!categoryError.text) close()
                        }
                        ColumnLayout {
                            TextField { id: categoryName; placeholderText: "Category name"; maximumLength: 40; onAccepted: categoryDialog.save() }
                            LabelText { id: categoryError; visible: !!text }
                            Row {
                                Pill { text: "Cancel"; onClicked: categoryDialog.close() }
                                Pill { text: "Save"; active: true; onClicked: categoryDialog.save() }
                            }
                        }
                    }
                }
                Item {
                    id: carouselArea
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    ListView {
                        id: carousel
                        objectName: "carousel"
                        anchors.fill: parent
                        orientation: ListView.Horizontal
                        model: studio.wardrobe
                        spacing: 12
                        Component.onCompleted: currentIndex = studio.selectedIndex
                        clip: true
                        focus: true
                        boundsBehavior: Flickable.DragAndOvershootBounds
                        flickDeceleration: 1550
                        maximumFlickVelocity: 2600
                        snapMode: ListView.SnapToItem
                        preferredHighlightBegin: (width - 124) / 2
                        preferredHighlightEnd: (width + 124) / 2
                        highlightRangeMode: ListView.StrictlyEnforceRange
                        highlightMoveDuration: 220
                        highlightResizeDuration: 180
                        cacheBuffer: 150
                        add: Transition { NumberAnimation { properties: "opacity,scale"; from: 0; to: 1; duration: 170; easing.type: Easing.OutCubic } }
                        remove: Transition { NumberAnimation { properties: "opacity,scale"; to: 0; duration: 150; easing.type: Easing.InCubic } }
                        displaced: Transition { NumberAnimation { properties: "x"; duration: 180; easing.type: Easing.OutCubic } }
                        // Filtering can move the ListView's index without user
                        // input. Only let a real gesture change the selection.
                        onCurrentIndexChanged: {
                            if (dragging || flicking) {
                                carousel.forceActiveFocus()
                                studio.selectVisible(currentIndex)
                            }
                        }
                        Keys.onLeftPressed: studio.selectVisible(studio.selectedIndex - 1)
                        Keys.onRightPressed: studio.selectVisible(studio.selectedIndex + 1)
                        WheelHandler {
                            target: null
                            onWheel: function(event) {
                                const delta = Math.abs(event.angleDelta.y) > Math.abs(event.angleDelta.x) ? event.angleDelta.y : event.angleDelta.x
                                if (delta !== 0) {
                                    carousel.forceActiveFocus()
                                    studio.selectVisible(studio.selectedIndex + (delta > 0 ? -1 : 1))
                                }
                                event.accepted = true
                            }
                        }
                        delegate: Item {
                            id: card
                            required property int index
                            required property string skinName
                            required property string skinFilename
                            required property string skinStatus
                            required property string category
                            required property string thumbnail
                            required property bool isReference
                            width: 124; height: window.height < 760 ? 146 : 166
                            readonly property real distance: Math.abs(x + width / 2 - carousel.contentX - carousel.width / 2)
                            readonly property real edge: Math.min(1, distance / Math.max(1, carousel.width * .47))
                            readonly property bool selected: index === carousel.currentIndex
                            readonly property bool assigned: window.assigningCategories && !studio.reviewMode
                                && !!window.assignmentTag && category === window.assignmentTag
                            z: selected ? 2 : 1
                            Item {
                                anchors.fill: parent
                                // Bottom-facing perspective: the middle is LOWER (a shallow U).
                                // Selection lifts only six pixels from that curved baseline.
                                transform: Translate { y: (window.height < 760 ? 19 : 23) - 16 * card.edge * card.edge - (card.selected ? 6 : 0) - (hover.hovered ? 2 : 0)
                                    Behavior on y { NumberAnimation { duration: 125; easing.type: Easing.OutCubic } }
                                }
                                scale: 1 - .075 * card.edge + (card.selected ? .025 : 0)
                                opacity: 1 - .25 * card.edge
                                Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                                Rectangle {
                                    x: 2; y: card.selected ? 7 : 4; width: parent.width - 4; height: parent.height - 13
                                    radius: 18; color: "#0c79668a"
                                }
                                Rectangle {
                                    anchors.fill: parent; anchors.bottomMargin: 13
                                    radius: 17; color: card.assigned ? window.assignmentHighlight : card.selected ? "#faf3ff" : "#ffffff"
                                    Behavior on color { ColorAnimation { duration: 120 } }
                                    border.color: card.selected ? window.accent : card.assigned ? "#c8afe4" : "#eee5f2"
                                    border.width: card.selected ? 2 : 1
                                }
                                Image { x: 25; y: 9; width: 74; height: window.height < 760 ? 87 : 107; source: card.thumbnail; fillMode: Image.PreserveAspectFit; smooth: false; mipmap: false }
                                Text {
                                    x: 10; y: window.height < 760 ? 103 : 123; width: 104; text: card.skinName
                                    elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
                                    color: window.ink; font.pixelSize: 12; font.weight: Font.DemiBold
                                }
                                Text {
                                    x: 99; y: 8
                                    text: ({"favorite":"♥", "keep":"✓", "maybe":"?", "remove":"×"})[card.skinStatus] || ""
                                    opacity: text ? 1 : 0
                                    Behavior on opacity { NumberAnimation { duration: 120 } }
                                    color: card.skinStatus === "favorite" ? "#c55b86" : card.skinStatus === "keep" ? "#4b826b" : window.muted
                                    font.pixelSize: 17
                                }
                                Text { x: 9; y: 8; visible: card.isReference; text: "✦"; color: window.accent; font.pixelSize: 16 }
                                Text { x: 9; y: 28; visible: card.assigned; text: "✓"; color: window.accent; font.pixelSize: 15 }
                                HoverHandler { id: hover }
                                SoftTip { text: card.skinFilename; delay: 650; visible: hover.hovered && !carousel.moving }
                                TapHandler {
                                    onTapped: {
                                        carousel.forceActiveFocus()
                                        studio.selectVisible(card.index)
                                        if (window.assigningCategories && !studio.reviewMode && window.assignmentTag)
                                            studio.setTag(window.assignmentTag)
                                    }
                                }
                            }
                        }
                    }
                    Caption {
                        visible: !studio.hasSkins; anchors.centerIn: parent
                        text: studio.reviewMode ? studio.selectedName : "No matches. Try another filter or choose a wardrobe."
                    }
                }
            }
        }
    }
}
