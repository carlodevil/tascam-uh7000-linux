import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 1120
    height: 720
    minimumWidth: 900
    minimumHeight: 620
    title: "UH-7000 Control · Unofficial"
    color: "#111315"
    font.family: "Segoe UI"
    font.pixelSize: 13

    property color panel: "#22262a"
    property color panelRaised: "#2d3237"
    property color border: "#4b5157"
    property color accent: "#d9a521"
    property color safe: "#45b97c"
    property color danger: "#e65b5b"
    property color textMain: "#f0f2f4"
    property color textMuted: "#aeb4ba"

    palette.window: panel
    palette.windowText: textMain
    palette.base: "#111315"
    palette.alternateBase: panelRaised
    palette.text: textMain
    palette.button: panelRaised
    palette.buttonText: textMain
    palette.highlight: accent
    palette.highlightedText: "#111315"

    background: Rectangle {
        gradient: Gradient {
            GradientStop { position: 0; color: "#30353a" }
            GradientStop { position: 0.14; color: "#202428" }
            GradientStop { position: 1; color: "#111315" }
        }
    }

    header: ColumnLayout {
        spacing: 0
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 52
            color: "#191c1f"
            border.color: window.border
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                Label {
                    text: "UH-7000 CONTROL"
                    color: window.textMain
                    font.pixelSize: 20
                    font.bold: true
                    font.letterSpacing: 1.4
                }
                Label {
                    text: "UNOFFICIAL LINUX PANEL"
                    color: window.textMuted
                    font.pixelSize: 11
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    implicitWidth: statusLabel.implicitWidth + 24
                    implicitHeight: 30
                    radius: 4
                    color: uh7000.connected ? "#15382a" : "#421f22"
                    border.color: uh7000.connected ? window.safe : window.danger
                    Label {
                        id: statusLabel
                        anchors.centerIn: parent
                        text: uh7000.statusText
                        color: window.textMain
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 44
            color: uh7000.safetyReady ? "#173428" : "#493717"
            border.color: uh7000.safetyReady ? window.safe : window.accent
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                Label {
                    text: uh7000.safetyReady
                        ? "Playback safety gates passed"
                        : "Playback locked: direct monitoring, attenuation, and baseline must be verified"
                    color: window.textMain
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Button { text: "Refresh"; onClicked: uh7000.refresh() }
            }
        }
        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { text: "INTERFACE" }
            TabButton { text: "MIXER" }
            TabButton { text: "EFFECTS" }
        }
    }

    StackLayout {
        anchors.fill: parent
        anchors.margins: 20
        currentIndex: tabs.currentIndex

        ScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: 16
                GroupBox {
                    title: "Device status"
                    Layout.fillWidth: true
                    GridLayout {
                        columns: 2
                        anchors.fill: parent
                        Label { text: "Connection"; color: window.textMuted }
                        Label { text: uh7000.statusText; color: window.textMain }
                        Label { text: "USB topology"; color: window.textMuted }
                        Label { text: "4 playback / 6 capture · S24_3LE"; color: window.textMain }
                        Label { text: "Feedback"; color: window.textMuted }
                        Label { text: "Explicit endpoint 0x85 required"; color: window.textMain }
                    }
                }
                GroupBox {
                    title: "Interface settings"
                    Layout.fillWidth: true
                    GridLayout {
                        columns: 2
                        anchors.fill: parent
                        Label { text: "Mixer mode" }
                        ComboBox { model: ["Multitrack", "Stereo Mix"]; enabled: uh7000.hardwareControlsVerified }
                        Label { text: "Audio performance" }
                        ComboBox { model: ["Safe", "High", "Normal", "Low", "Lowest"]; currentIndex: 2; enabled: uh7000.hardwareControlsVerified }
                        Label { text: "Sample clock source" }
                        ComboBox { model: ["Automatic", "Internal"]; enabled: uh7000.hardwareControlsVerified }
                        Label { text: "Auto power save" }
                        Switch { text: checked ? "30 min" : "Off"; checked: true; enabled: uh7000.hardwareControlsVerified }
                    }
                }
                GroupBox {
                    title: "Direct monitoring / passthrough"
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        Label {
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                            text: "Input-to-output monitoring can close a feedback loop during self-loopback tests. Its state must be read back before playback is unlocked."
                            color: window.accent
                        }
                        Switch {
                            text: "Enable direct monitoring"
                            checked: false
                            enabled: uh7000.hardwareControlsVerified
                        }
                    }
                }
            }
        }

        ScrollView {
            contentWidth: mixerRow.implicitWidth
            RowLayout {
                id: mixerRow
                spacing: 8
                Repeater {
                    model: ["ANALOG 1", "ANALOG 2", "DIGITAL 1", "DIGITAL 2", "COMPUTER 1", "COMPUTER 2", "COMPUTER 3", "COMPUTER 4", "MASTER"]
                    delegate: Rectangle {
                        required property string modelData
                        Layout.preferredWidth: 104
                        Layout.fillHeight: true
                        radius: 4
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            Label { text: modelData; Layout.alignment: Qt.AlignHCenter; font.bold: true; color: window.textMain }
                            Rectangle {
                                Layout.preferredWidth: 10
                                Layout.fillHeight: true
                                Layout.alignment: Qt.AlignHCenter
                                color: "#0b0d0e"
                                border.color: window.border
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    height: 1
                                    color: window.safe
                                }
                            }
                            Slider { from: 12; to: -127; value: 0; orientation: Qt.Vertical; Layout.preferredHeight: 220; enabled: uh7000.hardwareControlsVerified }
                            Label { text: "0.0 dB"; Layout.alignment: Qt.AlignHCenter; color: window.textMuted }
                            RowLayout {
                                Layout.alignment: Qt.AlignHCenter
                                ToolButton { text: "S"; enabled: uh7000.hardwareControlsVerified }
                                ToolButton { text: "M"; enabled: uh7000.hardwareControlsVerified }
                            }
                        }
                    }
                }
            }
        }

        ScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: 14
                GroupBox {
                    title: "Dynamics"
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        TabBar {
                            Layout.fillWidth: true
                            Repeater {
                                model: ["COMPRESSOR", "NOISE SUPPRESSOR", "DE-ESSER", "EXCITER", "EQ", "LIMITER / LOW CUT"]
                                TabButton { required property string modelData; text: modelData; enabled: uh7000.hardwareControlsVerified }
                            }
                        }
                        Label {
                            text: "Effect controls unlock after their USB payload and readback are verified in isolated captures."
                            color: window.textMuted
                        }
                    }
                }
                GroupBox {
                    title: "Reverb"
                    Layout.fillWidth: true
                    GridLayout {
                        columns: 2
                        anchors.fill: parent
                        Label { text: "Type" }
                        ComboBox { model: ["Hall", "Room", "Live", "Studio", "Plate"]; enabled: uh7000.hardwareControlsVerified }
                        Label { text: "Pre-delay" }
                        Slider { from: 0; to: 100; value: 42; enabled: uh7000.hardwareControlsVerified }
                        Label { text: "Reverb time" }
                        Slider { from: 0.1; to: 10; value: 2.7; enabled: uh7000.hardwareControlsVerified }
                    }
                }
            }
        }
    }
}
