const BRIDGE_BASE = "http://127.0.0.1:8788";
const inFlightTabs = new Set();

async function postSnapshot(tabId, snapshot) {
  if (inFlightTabs.has(tabId)) return;
  inFlightTabs.add(tabId);
  try {
    const response = await fetch(`${BRIDGE_BASE}/snapshot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...snapshot, tab_id: tabId }),
      cache: "no-store",
    });
    if (!response.ok) return;

    const commandResponse = await fetch(
      `${BRIDGE_BASE}/command?tab_id=${encodeURIComponent(tabId)}`,
      { method: "GET", cache: "no-store" },
    );
    if (!commandResponse.ok) return;

    const payload = await commandResponse.json();
    if (payload?.command) {
      try {
        await chrome.tabs.sendMessage(tabId, {
          type: "ziren-command",
          command: payload.command,
        });
      } catch (_error) {
        // The tab may have navigated between the snapshot and the command.
      }
    }
  } catch (_error) {
    // Ziren Core may be stopped. The extension stays silent and retries later.
  } finally {
    inFlightTabs.delete(tabId);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "ziren-snapshot" || !sender.tab?.id) {
    return false;
  }

  postSnapshot(sender.tab.id, message.snapshot)
    .then(() => sendResponse({ ok: true }))
    .catch(() => sendResponse({ ok: false }));
  return true;
});
