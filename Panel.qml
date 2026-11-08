import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Model list. Every string from Ollama or ollama.com is rendered as plain text.
Panel {
  id: root
  moduleName: "io.github.john-c-houser-tech.ollama-launcher"
  ipcTarget: "io.github.john-c-houser-tech.ollama-launcher"

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  property var models: []
  property string error: ""
  property bool loading: false
  property string launchError: ""
  property int selectedIndex: 0
  property real lastMouseX: -1
  property real lastMouseY: -1
  property bool hoverArmed: false

  readonly property var credit: hostWidget ? hostWidget.credit : ({})
  readonly property string projectDir: hostWidget ? hostWidget.projectDir : "~/Projects"
  readonly property string helper: Qt.resolvedUrl("ollama-launcher").toString().replace(/^file:\/\//, "")
  readonly property color fg: root.bar ? root.bar.foreground : Color.foreground
  readonly property color dimmed: Qt.darker(fg, 1.4)
  readonly property string fontFamily: root.bar ? root.bar.fontFamily : Style.font.family

  onSelectedIndexChanged: if (typeof modelList !== "undefined" && modelList.count > 0)
    modelList.positionViewAtIndex(root.selectedIndex, ListView.Contain)

  function open() {
    root.controller.show()
    root.hoverArmed = false
    hoverArm.restart()
    root.launchError = ""
    refresh()
    if (hostWidget) hostWidget.refreshCredit(false)
  }
  function openFromHotkey() { open() }
  function close() { root.controller.hide() }
  function toggle() { root.opened ? close() : open() }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function refresh() {
    if (listProc.running) return
    root.loading = true
    var noFetch = hostWidget && hostWidget.fetchDescriptions === false
    listProc.command = ["python3", "-I", root.helper, "models"].concat(noFetch ? ["--no-descriptions"] : [])
    listProc.running = true
  }

  function launch(model) {
    if (!model || launchProc.running) return
    root.launchError = ""
    launchProc.command = ["python3", "-I", root.helper, "launch", String(model.name), root.projectDir]
    launchProc.running = true
  }

  function launchSelected() {
    if (root.models.length > 0) launch(root.models[root.selectedIndex])
  }

  function creditLine() {
    var c = root.credit || {}
    if (!hostWidget || hostWidget.showCredit === false) return ""
    if (c.ok !== true) return c.error ? "Ollama Cloud: " + c.error : "Ollama Cloud credit: checking…"
    var line = "Ollama Cloud: " + hostWidget.money(c.totalLeftUsd) + " left"
    if (Number(c.allowanceUsd) > 0) line += " of " + hostWidget.money(c.allowanceUsd)
    var day = hostWidget.resetDay(c.resetsAt)
    if (day) line += " · resets " + day
    if (Number(c.purchasedUsd) > 0) line += " · includes " + hostWidget.money(c.purchasedUsd) + " purchased"
    if (c.stale) line += " · last good reading"
    return line
  }

  Timer { id: hoverArm; interval: 800; onTriggered: root.hoverArmed = true }
  Timer { id: listDeadline; interval: 20000; onTriggered: if (listProc.running) { listProc.running = false; root.loading = false; root.error = "Timed out reading models." } }

  Process {
    id: listProc
    onRunningChanged: running ? listDeadline.restart() : listDeadline.stop()
    onExited: root.loading = false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        root.loading = false
        if (text.length > 1048576) { root.models = []; root.error = "Helper output too large."; return }
        try {
          var parsed = JSON.parse(text)
          root.models = Array.isArray(parsed.models) ? parsed.models.slice(0, 100) : []
          root.error = parsed.ok === true ? "" : String(parsed.error || "Couldn't list models.")
        } catch (e) {
          root.models = []
          root.error = "Couldn't read the helper's answer."
        }
        if (root.selectedIndex >= root.models.length) root.selectedIndex = Math.max(0, root.models.length - 1)
      }
    }
  }

  Process {
    id: launchProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var parsed = JSON.parse(text)
          if (parsed.ok === true) { root.close(); return }
          root.launchError = String(parsed.error || "Launch failed.").slice(0, 300)
        } catch (e) {
          root.launchError = "Launch failed."
        }
      }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: false
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(500))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (dy !== 0 && root.models.length > 0)
          root.selectedIndex = Math.max(0, Math.min(root.models.length - 1, root.selectedIndex + dy))
      }
      onReturnRequested: root.launchSelected()
      onActivateRequested: root.launchSelected()
      onTextKey: function(text) { if (text === "r") root.refresh() }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(6)

        // ---- Header: title and credit.
        Column {
          x: Style.space(16)
          width: parent.width - Style.space(32)
          topPadding: Style.space(10)
          bottomPadding: Style.space(4)
          spacing: Style.space(2)

          Text {
            width: parent.width
            text: "Local models"
            textFormat: Text.PlainText
            color: root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Text {
            width: parent.width
            visible: text !== ""
            text: root.creditLine()
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: root.dimmed
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        PanelSeparator { width: parent.width }

        // ---- Model rows.
        ListView {
          id: modelList
          width: parent.width
          height: Math.min(contentHeight, Style.space(520))
          clip: true
          spacing: Style.space(2)
          boundsBehavior: Flickable.StopAtBounds
          model: root.models

          delegate: Rectangle {
            id: row
            required property var modelData
            required property int index
            readonly property bool current: index === root.selectedIndex
            readonly property string warning: String(modelData.warning || "")

            width: modelList.width
            height: rowContent.implicitHeight + Style.space(16)
            radius: Style.cornerRadius
            color: (current || rowArea.containsMouse) ? Style.hoverFillFor(root.fg, Color.accent) : "transparent"

            Column {
              id: rowContent
              anchors.left: parent.left
              anchors.leftMargin: Style.space(16)
              anchors.right: parent.right
              anchors.rightMargin: Style.space(16)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(3)

              Row {
                width: parent.width
                spacing: Style.space(8)

                Text {
                  text: String(row.modelData.name || "")
                  textFormat: Text.PlainText
                  color: row.modelData.ready === true ? root.fg : root.dimmed
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: true
                }

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  visible: row.modelData.loaded === true
                  text: "in memory"
                  textFormat: Text.PlainText
                  color: Color.accent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }

              Text {
                width: parent.width
                visible: text !== ""
                text: String(row.modelData.description || "")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                maximumLineCount: row.current ? 4 : 2
                elide: Text.ElideRight
                color: root.dimmed
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                width: parent.width
                text: String(row.modelData.facts || "")
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                width: parent.width
                visible: row.warning !== ""
                text: "⚠ " + row.warning
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.bar ? root.bar.urgent : Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            MouseArea {
              id: rowArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onPositionChanged: function(mouse) {
                if (!root.hoverArmed) return
                var g = rowArea.mapToGlobal(mouse.x, mouse.y)
                if (g.x !== root.lastMouseX || g.y !== root.lastMouseY) {
                  root.lastMouseX = g.x
                  root.lastMouseY = g.y
                  root.selectedIndex = row.index
                }
              }
              onClicked: root.launch(row.modelData)
            }
          }
        }

        // ---- Empty, error and launch messages.
        Text {
          x: Style.space(16)
          width: parent.width - Style.space(32)
          visible: text !== ""
          text: root.loading && root.models.length === 0 ? "Reading models…"
            : (root.error !== "" ? root.error
            : (root.models.length === 0 ? "No local models. Pull one with: ollama pull <model>" : ""))
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: root.dimmed
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        Text {
          x: Style.space(16)
          width: parent.width - Style.space(32)
          visible: root.launchError !== ""
          text: root.launchError
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: root.bar ? root.bar.urgent : Color.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        PanelSeparator { width: parent.width }

        Item {
          width: parent.width
          height: footer.implicitHeight + Style.space(14)

          Text {
            id: footer
            anchors.left: parent.left
            anchors.leftMargin: Style.space(16)
            anchors.right: parent.right
            anchors.rightMargin: Style.space(16)
            anchors.verticalCenter: parent.verticalCenter
            text: "Click or ↵ opens opencode in " + root.projectDir + " · r refresh · esc"
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
            color: root.dimmed
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }
}
