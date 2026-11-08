import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Bar face: rocket glyph plus Ollama Cloud credit left. Click opens the model
// list (Panel.qml). The credit is fetched here so the bar can show it without
// the panel open; the panel reads it through `credit`.
BarWidget {
  id: root
  moduleName: "io.github.john-c-houser-tech.ollama-launcher"

  readonly property string helper: Qt.resolvedUrl("ollama-launcher").toString().replace(/^file:\/\//, "")
  readonly property string projectDir: String(setting("projectDir", "~/Projects") || "~/Projects")
  readonly property int creditMinutes: Math.max(5, Math.min(120, Math.floor(Number(setting("creditRefreshMinutes", 15)) || 15)))
  readonly property bool showCredit: String(setting("showCredit", "On")) !== "Off"
  readonly property bool fetchDescriptions: String(setting("fetchDescriptions", "On")) !== "Off"

  property var credit: ({})

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function money(value) {
    var n = Number(value)
    return isFinite(n) ? "$" + n.toFixed(2) : ""
  }

  function resetDay(iso) {
    var d = new Date(String(iso || ""))
    return isNaN(d.getTime()) ? "" : d.toLocaleDateString(Qt.locale(), "MMM d")
  }

  function barLabel() {
    var glyph = ""
    if (root.vertical || !root.showCredit || root.credit.ok !== true) return glyph
    return glyph + " $" + Math.floor(Number(root.credit.totalLeftUsd) || 0)
  }

  function tooltip() {
    if (!root.showCredit) return "Ollama Launcher: click for local models"
    var c = root.credit
    if (c.ok !== true) return (c.error ? "Ollama Cloud: " + c.error : "Ollama Cloud credit: checking…") + "\nClick for local models"
    var line = "Ollama Cloud: " + root.money(c.totalLeftUsd) + " left"
    if (Number(c.allowanceUsd) > 0) line += " of " + root.money(c.allowanceUsd) + " monthly"
    var day = root.resetDay(c.resetsAt)
    if (day) line += " · resets " + day
    if (c.stale) line += "\n(last good reading; " + c.error + ")"
    return line + "\nClick for local models"
  }

  function refreshCredit(force) {
    if (!root.showCredit || creditProc.running) return
    creditProc.command = ["python3", "-I", root.helper, "credit"].concat(force ? ["--force"] : [])
    creditProc.running = true
  }

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }
  function togglePanel() { if (root.opened) root.close(); else root.open() }

  function injectPanel() {
    var panel = panelLoader.item
    if (!panel) return
    if ("bar" in panel) panel.bar = root.bar
    if ("anchorItem" in panel) panel.anchorItem = button
    if ("hostWidget" in panel) panel.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  onBarChanged: injectPanel()
  onShowCreditChanged: if (showCredit) refreshCredit(false)
  Component.onCompleted: refreshCredit(false)

  Timer {
    interval: root.creditMinutes * 60 * 1000
    running: root.showCredit
    repeat: true
    onTriggered: root.refreshCredit(false)
  }

  Process {
    id: creditProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (text.length > 65536) return
        try {
          var parsed = JSON.parse(text)
          if (parsed && typeof parsed === "object") root.credit = parsed
        } catch (e) {
          root.credit = ({ ok: false, error: "couldn't read the helper's answer" })
        }
      }
    }
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onStatusChanged: if (status === Loader.Error) console.warn("ollama-launcher: Panel.qml failed to load")
    onLoaded: { root.injectPanel(); Qt.callLater(root.injectPanel) }
  }

  WidgetButton {
    id: button
    bar: root.bar
    text: root.barLabel()
    fontSize: Style.font.body
    horizontalMargin: root.vertical ? Style.space(2) : Style.space(4)
    tooltipText: root.tooltip()
    onPressed: function(mouseButton) { if (mouseButton === Qt.LeftButton) root.togglePanel() }
  }
}
