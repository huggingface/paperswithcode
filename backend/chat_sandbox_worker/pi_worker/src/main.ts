import readline from "node:readline";
import { PiWorker } from "./agent.js";
import { MAX_TURN_FRAME_BYTES, parseRunTurn } from "./turn_protocol.js";

const PREFIX = "@@PWC_CHAT_V1@@";
const MAX_FRAME_BYTES = MAX_TURN_FRAME_BYTES;
const persistent = process.env.PWC_CHAT_PERSISTENT_AGENT === "1";

function emit(requestId: string, event: Record<string, unknown>): void {
  const frame = JSON.stringify({ v: 1, request_id: requestId, ...event });
  if (Buffer.byteLength(frame) > MAX_FRAME_BYTES) throw new Error("Pi worker frame is too large");
  process.stdout.write(`${PREFIX}${frame}\n`);
}

const worker = new PiWorker(emit);
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
let chain = worker.initialize();

if (persistent) chain = chain.then(() => emit("startup", { type: "worker_ready" }));

input.on("line", (line) => {
  if (!line.startsWith(PREFIX) || Buffer.byteLength(line) > MAX_FRAME_BYTES + PREFIX.length) return;
  let decoded: Record<string, unknown>;
  try {
    decoded = JSON.parse(line.slice(PREFIX.length)) as Record<string, unknown>;
  } catch {
    return;
  }
  if (decoded.type === "cancel" && typeof decoded.request_id === "string") {
    void worker.cancel(decoded.request_id);
    return;
  }
  chain = chain
    .then(async () => {
      const requestId = typeof decoded.request_id === "string" ? decoded.request_id : "invalid";
      try {
        await worker.run(parseRunTurn(decoded));
      } catch {
        emit(requestId, { type: "error", code: "invalid_request", message: "The research run failed." });
        emit(requestId, { type: "worker_done", status: "complete" });
      }
    })
    .finally(() => {
      if (!persistent) input.close();
    });
});

input.on("close", () => {
  void chain.finally(() => {
    process.exitCode = 0;
  });
});
