# Embedded Sidebar apps

Register an HTTP(S) URL using the existing external-link settings and choose to
open it inside PrintOps. Ordinary links that open in a new tab keep their existing
behavior. Embedded pages can opt into the protocol below to follow the current
PrintOps theme and request navigation in the host. Pages that do not implement
it continue to display normally; PrintOps cannot restyle their content.

## Protocol

Messages are plain objects sent with `window.postMessage`. The protocol uses
only these PrintOps names; there are no upstream message aliases.

| Direction | Message | Meaning |
| --- | --- | --- |
| Host → app | `{ type: 'printops:theme', mode, style, background, accent, canNavigate: true }` | Current visual settings and navigation support |
| App → host | `{ type: 'printops:theme-request' }` | Ask for the current theme |
| App → host | `{ type: 'printops:navigate', path: '/queue?batch=12#pending' }` | Navigate the host through its normal router |

`mode` is the resolved `light` or `dark` value, including when PrintOps follows
the operating system. `style`, `background` and `accent` are the active theme's
names from the PrintOps theme settings. Theme messages are sent after iframe
load, when active visual settings change, and on an accepted request. They
contain no account information, credentials or API secrets.

The host sends to the exact origin derived from the registered HTTP(S) URL,
including a nondefault port. A malformed URL, embedded credentials, whitespace,
backslash or control character disables the message bridge. Both incoming message
types require the current iframe's `contentWindow` and the exact registered
origin. A sibling frame, old iframe, lookalike origin or redirect to a different
origin cannot use the bridge. Redirected apps must be registered at their final
origin if they need it.

Navigation paths must be strings of at most 512 characters, beginning with one
`/`. Protocol-relative paths, backslashes and control characters are rejected,
as are paths that parse off-origin or normalize to a `//` prefix. Valid query
strings and fragments are retained. Existing route and API permissions still
apply: `canNavigate` announces protocol support, not access to every page.

## App example

Configure the exact host origin for your installation, rather than deriving it
from untrusted incoming messages:

```js
const printOpsOrigin = 'http://localhost:8000'; // Your configured PrintOps origin.

window.addEventListener('message', (event) => {
  if (event.source !== window.parent || event.origin !== printOpsOrigin) return;
  const theme = event.data;
  if (!theme || theme.type !== 'printops:theme') return;
  if (theme.mode === 'light' || theme.mode === 'dark') {
    document.documentElement.style.colorScheme = theme.mode;
  }
  // Apply your own styles for theme.style, theme.background and theme.accent.
  // Enable your navigation control when theme.canNavigate === true.
});

window.parent.postMessage({ type: 'printops:theme-request' }, printOpsOrigin);

function openQueue() {
  window.parent.postMessage(
    { type: 'printops:navigate', path: '/queue?batch=12#pending' },
    printOpsOrigin,
  );
}
```

## Registration and session lifecycle

Reading a registered link requires `external_links:read` when authentication is
enabled. PrintOps waits for verified authentication state and a successful link
lookup before displaying the embedded app. A missing, deleted or inaccessible
link uses the existing link-not-found state; pending lookups use the existing
loading state. A failed revalidation removes the old frame and its authority.

A change of account, credentials, link ID or registered URL replaces the frame.
Credential changes include automatic token renewal: the link is fetched again
and the embedded app reloads, so its unsaved in-memory state can be lost. This
small registration query has no cache after leaving the page or losing access.
This prevents cached links or reused numeric account IDs from granting a new
session authority. The existing iframe sandbox remains unchanged.

No printer commands or notifications are part of this protocol.
