# Recipe: Censorship-resistant file sharing with Logos Storage (Codex) + Logos Messaging (Waku)

**Components:** `logos-storage` (Codex) + `logos-messaging` (Waku)
**Pattern:** Codex stores the bytes and returns a CID; Waku broadcasts the *small* CID + metadata so
peers can discover and fetch it. **Waku is the coordination/transport layer for metadata — never the
big payload.** (Based on the CypherShare reference app.)

Pinned: `@codex-storage/sdk-js@^0.1.3`, `@waku/sdk@^0.0.36` (do **not** use legacy `js-waku`).

## 1. Store the file in Codex → get a CID
The Codex node REST API: `POST /data` returns a CID; `GET /data/{cid}/network` fetches across the
network. The JS SDK wraps this. **The SDK returns a Go-style `SafeValue` (error-as-value) — do NOT
wrap it in try/catch;** check the result instead.

```ts
import { Codex } from "@codex-storage/sdk-js";

const codex = new Codex("http://localhost:8080");
const res = await codex.data.upload(file).result;   // SafeValue, not a throw
if (res.error) { console.error(res.data); return; }
const cid = res.data;                                // share THIS, not the bytes
```

## 2. Broadcast the CID + metadata over Waku
```ts
import { createLightNode, Protobuf } from "@waku/sdk";

const node = await createLightNode({ defaultBootstrap: true });
await node.start();

const ContentTopic = "/logos-copilot/1/fileshare/proto";
const Msg = new Protobuf.MessageType("FileMsg", {
  sender: "string", filename: "string", filesize: "uint64", cid: "string",
});

const encoder = node.createEncoder({ contentTopic: ContentTopic });
await node.lightPush.send(encoder, {
  payload: Msg.toBinary({ sender, filename: file.name, filesize: file.size, cid }),
});
```

## 3. Receive: subscribe to Waku, then fetch from Codex
```ts
const decoder = node.createDecoder({ contentTopic: ContentTopic });
await node.filter.subscribe([decoder], (wakuMsg) => {
  const { cid, filename } = Msg.fromBinary(wakuMsg.payload);
  // pull the actual bytes from Codex by CID:
  // GET http://localhost:8080/data/{cid}/network
});
```

## Pitfalls
- Don't push file bytes through Waku — only the CID + metadata.
- `@waku/sdk`, not `js-waku` (legacy). `@codex-storage/sdk-js` is still the npm name even though the
  repo moved to `logos-storage/logos-storage-js`.
- Codex SDK uses `SafeValue` — check `.error`, don't try/catch.

## Sources
- `logos-storage/logos-storage-js` (SDK + `openapi.yaml`), `logos-messaging/logos-delivery-js`
- Codex REST: `https://api.codex.storage`
