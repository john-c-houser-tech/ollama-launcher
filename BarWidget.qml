import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Bar face: rocket glyph plus Ollama Cloud credit left. Click opens the model
// list (Panel.qml). The credit is fetched here so the bar can show it without
// the panel open; the panel reads it through `credit`. Every monitor's bar
// asks, but the helper answers from a shared, locked cache.
BarWidget {
  id: root
  moduleName: "io.github.john-c-houser-tech.ollama-launcher"

  readonly property string helper: Qt.resolvedUrl("ollama-launcher").toString().replace(/^file:\/\//, "")
  readonly property string projectDir: String(setting("projectDir", "~/Projects") || "~/Projects")
  readonly property int creditMinutes: Math.max(5, Math.min(120, Math.floor(Number(setting("creditRefreshMinutes", 15)) || 15)))
  readonly property bool showCredit: isOn(setting("showCredit", "On"))
  readonly property bool fetchDescriptions: isOn(setting("fetchDescriptions", "On"))

  property var credit: ({})

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function isOn(value) {
    var text = String(value).toLowerCase()
    return !(value === false || text === "off" || text === "false" || text === "0" || text === "no")
  }

  function money(value, decimals) {
    var n = Number(value)
    if (!isFinite(n)) return ""
    var digits = decimals === undefined ? 2 : decimals
    var amount = digits === 0 ? Math.trunc(Math.abs(n)) : Math.abs(n)
    return (n < 0 ? "-" : "") + "$" + I18n.formatNumber(amount, digits)
  }

  function resetDay(iso) {
    var d = new Date(String(iso || ""))
    return isNaN(d.getTime()) ? "" : d.toLocaleDateString(Qt.locale(I18n.formatLocale), "MMM d")
  }

  function barLabel() {
    var glyph = ""
    if (root.vertical || !root.showCredit || root.credit.ok !== true) return glyph
    return glyph + " " + root.money(root.credit.totalLeftUsd, 0)
  }

  // Dimmed when the reading is stale or missing, so an old number never
  // passes for a current one.
  readonly property bool creditCurrent: root.credit.ok === true && root.credit.stale !== true

  function tooltip() {
    if (!root.showCredit) return "Ollama Launcher: click for local models"
    var c = root.credit
    if (c.ok !== true) return (c.error ? "Ollama Cloud: " + c.error : "Ollama Cloud credit: checking…") + "\nClick for local models"
    var line = "Ollama Cloud: " + root.money(c.totalLeftUsd) + " left"
    if (Number(c.allowanceUsd) > 0) line += " of " + root.money(c.allowanceUsd) + " allowance"
    var day = root.resetDay(c.resetsAt)
    if (day) line += " · resets " + day
    if (c.stale) line += "\nStale: last good reading " + root.resetDay(c.checkedAt) + ". " + c.error
    return line + "\nClick for local models"
  }

  function refreshCredit() {
    if (!root.showCredit || creditProc.running) return
    creditProc.killed = false
    creditProc.command = ["python3", "-I", "-B", root.helper, "credit"]
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
  onShowCreditChanged: if (showCredit) refreshCredit()
  Component.onCompleted: refreshCredit()

  Timer {
    interval: root.creditMinutes * 60 * 1000
    running: root.showCredit
    repeat: true
    onTriggered: root.refreshCredit()
  }

  Timer {
    id: creditDeadline
    interval: 30000
    onTriggered: if (creditProc.running) {
      creditProc.killed = true
      creditProc.running = false
      root.credit = Object.assign({}, root.credit, { stale: root.credit.ok === true, error: "ollama.com took too long to answer." })
    }
  }

  Process {
    id: creditProc
    property bool killed: false
    onRunningChanged: running ? creditDeadline.restart() : creditDeadline.stop()
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (creditProc.killed) return
        if (text.length > 65536) {
          root.credit = Object.assign({}, root.credit, { stale: root.credit.ok === true, error: "The helper's answer was too large." })
          return
        }
        try {
          var parsed = JSON.parse(text)
          if (parsed && typeof parsed === "object") root.credit = parsed
        } catch (e) {
          root.credit = Object.assign({}, root.credit, { stale: root.credit.ok === true, error: "Couldn't read the helper's answer." })
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
    foreground: {
      var fg = root.bar ? root.bar.barForeground : Color.foreground
      return root.showCredit && !root.creditCurrent ? Qt.darker(fg, 1.6) : fg
    }
    tooltipText: root.tooltip()
    onPressed: function(mouseButton) { if (mouseButton === Qt.LeftButton) root.togglePanel() }
  }
}
