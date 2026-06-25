import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Controls.Material
import Qt.labs.settings
import Qt.labs.platform as Platform

import "." as UI
import "./elements" as UIElements

ApplicationWindow {
    id: applicationWindowSciHubEVA
    title: "Sci-Hub EVA"

    modality: Qt.ApplicationModal

    visible: true

    property int margin: 10
    property int theme: Material.theme

    width: columnLayoutApplication.implicitWidth + 2 * margin
    height: columnLayoutApplication.implicitHeight + 2 * margin
    minimumWidth: columnLayoutApplication.Layout.minimumWidth + 2 * margin
    minimumHeight: columnLayoutApplication.Layout.minimumHeight + 2 * margin
    maximumWidth: columnLayoutApplication.Layout.maximumWidth + 2 * margin
    maximumHeight: columnLayoutApplication.Layout.maximumHeight + 2 * margin

    signal openSaveToDir(string directory)
    signal systemOpenSaveToDir(string directory)
    signal showUIPreference()
    signal systemOpenLogFile()
    signal systemOpenLogDirectory()
    signal systemOpenDownloadLog()
    signal exportFailedQueries(string path)
    signal rampage(string query)
    signal pauseRampage()
    signal resumeRampage()

    property bool isRampaging: false
    property bool isPaused: false

    function setPaused(paused) {
        isPaused = paused
    }

    function setSaveToDir(directory) {
        textFieldSaveToDir.text = directory
    }

    function appendLog(message) {
        var style = "<style>a { color: " + Material.accent + "; }</style>"
        textAreaLogs.append(style + message)
    }

    function beforeRampage() {
        buttonRampage.enabled = false
        buttonLoadInputQueryList.enabled = false
        buttonOpenSaveToDir.enabled = false
        progressBarTotal.value = 0
        labelProgress.text = "0 / 0   ✓ 0   ✗ 0"
        listModelTasks.clear()
        isRampaging = true
        isPaused = false
    }

    function afterRampage() {
        buttonRampage.enabled = true
        buttonLoadInputQueryList.enabled = true
        buttonOpenSaveToDir.enabled = true
        isRampaging = false
        isPaused = false
    }

    function updateProgress(completed, total, successCount, failedCount) {
        progressBarTotal.value = total > 0 ? completed / total : 0
        labelProgress.text = completed + " / " + total + "   ✓ " + successCount + "   ✗ " + failedCount
    }

    function updateTaskRow(doi, mirror, speed, status) {
        for (var i = 0; i < listModelTasks.count; i++) {
            if (listModelTasks.get(i).doi === doi) {
                listModelTasks.set(i, { "doi": doi, "mirror": mirror, "speed": speed, "status": status })
                return
            }
        }
        listModelTasks.append({ "doi": doi, "mirror": mirror, "speed": speed, "status": status })
    }

    UI.About {
        id: dialogAbout
    }

    UIElements.Message {
        id: dialogMessage

        footer: DialogButtonBox {
            Button {
                id: buttonDialogMessageOK
                text: qsTr("OK")

                onClicked: dialogMessage.close()
            }
        }
    }

    Platform.FileDialog {
        id: fileDialogQueryList

        onAccepted: {
            var queryListURI = fileDialogQueryList.file.toString()

            switch (Qt.platform.os) {
            case "windows":
                queryListURI = queryListURI.replace(/^(file:\/{3})/, "")
                break
            default:
                queryListURI = queryListURI.replace(/^(file:\/{2})/, "")
                break
            }

            textFieldQuery.text = queryListURI
        }
    }

    Platform.FolderDialog {
        id: folderDialogSaveTo

        options: Platform.FolderDialog.ShowDirsOnly

        onAccepted: {
            var saveToURI = folderDialogSaveTo.folder.toString()

            switch (Qt.platform.os) {
            case "windows":
                saveToURI = saveToURI.replace(/^(file:\/{3})/, "")
                break
            default:
                saveToURI = saveToURI.replace(/^(file:\/{2})/, "")
                break
            }

            textFieldSaveToDir.text = saveToURI
            openSaveToDir(saveToURI)
        }
    }

    Platform.FileDialog {
        id: fileDialogExportFailedQueries

        fileMode: Platform.FileDialog.SaveFile
        defaultSuffix: "txt"

        onAccepted: {
            var failedQueriesURI = fileDialogExportFailedQueries.file.toString()

            switch (Qt.platform.os) {
            case "windows":
                failedQueriesURI = failedQueriesURI.replace(/^(file:\/{3})/, "")
                break
            default:
                failedQueriesURI = failedQueriesURI.replace(/^(file:\/{2})/, "")
                break
            }

            exportFailedQueries(failedQueriesURI)
        }
    }

    background: Image {
        source: {
            switch(Material.theme) {
            case Material.Light:
                "qrc:/images/SciHubEVA-background-light.png"
                break
            case Material.Dark:
                "qrc:/images/SciHubEVA-background-dark.png"
                break
            default:
                ""
                break
            }
        }
    }

    ColumnLayout {
        id: columnLayoutApplication

        anchors.fill: parent
        anchors.margins: margin

        focus: true

        GridLayout {
            Layout.fillHeight: true
            Layout.fillWidth: true

            rows: 2
            columns: 5

            Label {
                text: qsTr("Query: ")

                Layout.minimumWidth: 60
            }

            TextField {
                id: textFieldQuery
                placeholderText: qsTr("URL, PMID, DOI, Title or Query List File")

                implicitWidth: 300
                Layout.minimumWidth: 300
                Layout.fillWidth: true

                selectByMouse: true
            }

            Button {
                id: buttonRampage
                text: qsTr("Rampage")

                font.bold: false
                Layout.minimumWidth: implicitWidth
                Layout.minimumHeight: buttonAbout.implicitHeight
                Layout.fillWidth: true

                onClicked: {
                    if (textFieldSaveToDir.text.trim() === "") {
                        dialogMessage.messageType = "error"
                        dialogMessage.message = qsTr("Please choose save to directory first!")
                        dialogMessage.open()
                    } else if (textFieldQuery.text.trim() === "") {
                        dialogMessage.messageType = "error"
                        dialogMessage.message = qsTr("Please set the query!")
                        dialogMessage.open()
                    } else {
                        rampage(textFieldQuery.text.trim())
                    }
                }
            }

            Button {
                id: buttonLoadInputQueryList
                text: qsTr("Load")

                font.bold: false
                Layout.minimumWidth: implicitWidth
                Layout.minimumHeight: buttonAbout.implicitHeight
                Layout.fillWidth: true

                onClicked: fileDialogQueryList.open()
            }

            UIElements.IconButton {
                id: buttonAbout
                iconSource: "qrc:/images/icons/about.svg"

                onClicked: dialogAbout.open()
            }

            Label {
                text: qsTr("Save to: ")

                Layout.minimumWidth: 60
            }

            TextField {
                id: textFieldSaveToDir

                implicitWidth: 300
                Layout.minimumWidth: 300
                Layout.fillWidth: true

                readOnly: true
                selectByMouse: true
            }

            Button {
                id: buttonOpenSaveToDir
                text: qsTr("Open")

                font.bold: false
                Layout.minimumWidth: implicitWidth
                Layout.minimumHeight: buttonPreferences.implicitHeight
                Layout.fillWidth: true

                onClicked: folderDialogSaveTo.open()
            }

            Button {
                id: buttonShowSaveToDir
                text: qsTr("Show")

                font.bold: false
                Layout.minimumWidth: implicitWidth
                Layout.minimumHeight: buttonPreferences.implicitHeight
                Layout.fillWidth: true

                onClicked: systemOpenSaveToDir(textFieldSaveToDir.text.trim())
            }

            UIElements.IconButton {
                id: buttonPreferences
                iconSource: "qrc:/images/icons/preferences.svg"

                onClicked: {
                    showUIPreference()
                }
            }
        }

        // Progress row
        RowLayout {
            Layout.fillWidth: true

            ProgressBar {
                id: progressBarTotal
                Layout.fillWidth: true
                from: 0
                to: 1
                value: 0
            }

            Label {
                id: labelProgress
                text: "0 / 0   ✓ 0   ✗ 0"
                Layout.minimumWidth: 160
            }

            Button {
                id: buttonPause
                text: isPaused ? qsTr("Resume") : qsTr("Pause")
                visible: isRampaging
                enabled: isRampaging
                flat: true

                onClicked: {
                    if (isPaused) resumeRampage()
                    else pauseRampage()
                }
            }
        }

        // Task list
        ListModel {
            id: listModelTasks
        }

        ListView {
            id: listViewTasks
            Layout.fillWidth: true
            Layout.minimumHeight: 160
            Layout.preferredHeight: 200
            model: listModelTasks
            clip: true
            ScrollBar.vertical: UIElements.ScrollBar {}

            delegate: ItemDelegate {
                width: ListView.view.width

                contentItem: RowLayout {
                    spacing: 6

                    Label {
                        text: model.status === "success" ? "✓"
                            : model.status.startsWith("failed") ? "✗" : "⏳"
                        color: model.status === "success"
                            ? Material.color(Material.Green)
                            : model.status.startsWith("failed")
                                ? Material.color(Material.Red)
                                : Material.foreground
                        Layout.minimumWidth: 20
                    }

                    Label {
                        text: model.doi
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }

                    Label {
                        text: model.mirror || "—"
                        color: Material.accent
                        Layout.minimumWidth: 100
                    }

                    Label {
                        text: {
                            var s = model.status
                            if (s === "queued")      return qsTr("Waiting")
                            if (s === "resolving")   return qsTr("Resolving")
                            if (s === "downloading") return qsTr("Downloading")
                            if (s === "success")     return qsTr("Done")
                            if (s === "skipped")     return qsTr("Skipped")
                            if (s === "failed:NO_VALID_PDF") return qsTr("No PDF")
                            if (s === "failed:DDOS_GUARD")   return qsTr("Blocked")
                            if (s === "failed:CAPTCHA")      return qsTr("Captcha")
                            if (s.startsWith("failed"))      return qsTr("Failed")
                            return s
                        }
                        Layout.minimumWidth: 80
                    }
                }
            }
        }

        // Collapsible log area
        property bool logsExpanded: false

        RowLayout {
            Layout.fillWidth: true

            Label {
                id: labelLogs
                text: qsTr("Logs")
            }

            Button {
                flat: true
                text: applicationWindowSciHubEVA.logsExpanded ? qsTr("▲ Hide") : qsTr("▼ Show")
                onClicked: applicationWindowSciHubEVA.logsExpanded = !applicationWindowSciHubEVA.logsExpanded
            }
        }

        Flickable {
            id: flickableLogs

            visible: applicationWindowSciHubEVA.logsExpanded
            flickableDirection: Flickable.VerticalFlick

            Layout.minimumHeight: applicationWindowSciHubEVA.logsExpanded ? 120 : 0
            Layout.preferredHeight: applicationWindowSciHubEVA.logsExpanded ? 160 : 0
            Layout.fillWidth: true

            ScrollBar.vertical: UIElements.ScrollBar {
                id: scrollBarLogs
            }

            TextArea.flickable: TextArea {
                id: textAreaLogs

                textFormat: Text.RichText
                wrapMode: Text.WordWrap
                readOnly: true
                selectByMouse: true
                horizontalAlignment: Text.AlignLeft

                Layout.fillWidth: true

                onTextChanged: {
                    scrollBarLogs.position = 1.0 - scrollBarLogs.size
                }

                onLinkActivated: (link) => {
                    Qt.openUrlExternally(link)
                }

                MouseArea {
                    id: mouseAreaLogs

                    anchors.fill: parent

                    propagateComposedEvents: true
                    acceptedButtons: Qt.RightButton

                    onClicked: (mouse) => {
                        if (mouse.button === Qt.RightButton) {
                            menuLogs.open()
                        }
                    }

                    Platform.Menu {
                        id: menuLogs

                        Platform.MenuItem {
                            text: qsTr("Open log file")
                            onTriggered: systemOpenLogFile()
                        }

                        Platform.MenuItem {
                            text: qsTr("Open log directory")
                            onTriggered: systemOpenLogDirectory()
                        }

                        Platform.MenuItem {
                            text: qsTr("Open download records (CSV)")
                            onTriggered: systemOpenDownloadLog()
                        }

                        Platform.MenuItem {
                            text: qsTr("Export failed queries")
                            onTriggered: fileDialogExportFailedQueries.open()
                        }
                    }
                }
            }
        }

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Enter || event.key === Qt.Key_Return) {
                buttonRampage.clicked()
            }
        }
    }
}
